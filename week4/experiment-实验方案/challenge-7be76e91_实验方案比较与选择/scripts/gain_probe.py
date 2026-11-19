#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（exp-plan-compare，实验方案比较与选择）。

同一输入跑两遍：正常模式（六组机械校验全部开启）与退化模式（--ablate all，
关闭权重声明 / 口径统一 / 依据回证 / 总分复算 / 敏感性 / 选择登记六组检查），
逐项对照可观测指标（全部实测，不臆造）：

  1. rubric_missed        权重声明违规漏检数（权重非法/未事前声明未捕获）
  2. comparability_missed 口径统一违规漏检数（缺维度定义/打分格子缺要素未捕获）
  3. evidence_missed      依据回证漏检数（evidence_ref 断链/数字无回证未捕获）
  4. ranking_missed       总分复算违规漏检数（fused_score 篡改未捕获）
  5. sensitivity_missed   敏感性缺失/复算不符漏检数
  6. choice_missed        选择/放弃登记违规漏检数（弃选理由缺失未捕获）
  另计 manual_review_items 与 clarification_rounds（每轮 3 条折算）。

支持 --inject-pollution 生成污染副本做反例自测（注入：总分篡改、依据缺失、
权重声明破坏、敏感性清空、放弃理由清空——正常模式须抓到，退出码恒 0）。

**本脚本只产出对照证据；退化模式仅用于增益对照，不得用于交付自检。**
用法：
    python3 gain_probe.py --result /app/output/result.json --case /input/case.json \
        --work-dir /app/work --emit-into [--inject-pollution]
退出码：恒为 0（结论记在 verdict 字段与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from verify_check import analyze  # noqa: E402
    from score_plan import WEIGHT_KEYS, compute_sensitivity, fused, scored_pairs, weights_ok  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check/score_plan: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3  # 追问轮次折算：每轮最多消化 3 条人工条目
GROUPS = ("rubric", "comparability", "evidence", "ranking", "sensitivity", "choice")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path, obj):
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        print("[gain_probe] 写盘失败 %s: %s" % (path, e))
        return False


def check_index(report):
    out = {}
    for s in report.get("self_check") or []:
        if isinstance(s, dict) and s.get("item"):
            out[s["item"]] = s
    return out


def caught(idx, key):
    e = idx.get(key)
    return bool(e and e.get("applied") and e.get("match") is False)


def objective_violations(res):
    """独立复算六组客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    rubric = inner.get("rubric") or {}
    comp = inner.get("comparability") or {}
    versions = [v for v in (inner.get("plan_versions") or []) if isinstance(v, dict)]
    ranking = inner.get("plan_ranking") or {}
    sens = inner.get("sensitivity") or {}
    choice = inner.get("final_choice") or {}
    risks = [r for r in (inner.get("risks") or []) if isinstance(r, dict)]
    protocol = [s for s in (inner.get("protocol") or []) if isinstance(s, dict)]
    claims = res.get("claims") if isinstance(res.get("claims"), list) else []

    rub, cmp_, evid, rank_, sens_, cho = [], [], [], [], [], []

    w = weights_ok(rubric)
    if w is None:
        rub.append("rubric 权重非法或未声明（五维非负数值合计=1.0）")
    if not str(rubric.get("declared_at") or "").strip():
        rub.append("declared_at 为空（未事前声明）")

    dims = [d for d in (comp.get("dimensions") or []) if isinstance(d, dict)]
    dim_names = {str(d.get("dim") or "") for d in dims}
    if not set(WEIGHT_KEYS).issubset(dim_names) \
            or any(not str(d.get("definition") or "").strip() for d in dims):
        cmp_.append("五维口径定义未逐条声明")
    for i, v in enumerate(versions):
        pid = str(v.get("plan_id") or "plan_versions[%d]" % i)
        fd = v.get("factors_detail") if isinstance(v.get("factors_detail"), dict) else {}
        for k in WEIGHT_KEYS:
            c = fd.get(k)
            ok = (isinstance(c, dict)
                  and isinstance(c.get("score"), (int, float))
                  and not isinstance(c.get("score"), bool)
                  and 0.0 <= float(c.get("score")) <= 1.0
                  and str(c.get("basis") or "").strip()
                  and str(c.get("evidence_ref") or "").strip())
            if not ok:
                cmp_.append("%s.factors_detail.%s 缺要素" % (pid, k))

    claim_ids = {str(c.get("claim_id") or "") for c in claims}
    for i, v in enumerate(versions):
        pid = str(v.get("plan_id") or "plan_versions[%d]" % i)
        fd = v.get("factors_detail") if isinstance(v.get("factors_detail"), dict) else {}
        for k in WEIGHT_KEYS:
            c = fd.get(k) if isinstance(fd.get(k), dict) else {}
            ref = str(c.get("evidence_ref") or "")
            cl = next((x for x in claims if str(x.get("claim_id") or "") == ref), None)
            if not (cl and any(isinstance(e, dict) and str(e.get("quote") or "").strip()
                               for e in (cl.get("evidence") or []))):
                evid.append("%s.factors_detail.%s 依据回证断裂" % (pid, k))
    if not risks or any(not str(r.get(k) or "").strip() for r in risks
                        for k in ("failure_mode", "judge_criterion", "stop_loss")):
        evid.append("risks 缺失或不完整")
    corpus = ""
    try:
        corpus = json.dumps(claims, ensure_ascii=False) if claims else ""
    except Exception:
        corpus = ""
    for i, s in enumerate(protocol):
        for p in (s.get("params") or []) if isinstance(s.get("params"), list) else []:
            if isinstance(p, dict) and isinstance(p.get("value"), (int, float)):
                if corpus and str(p["value"]) not in corpus:
                    evid.append("protocol[%d] 参数值 %s 未回证" % (i, p["value"]))

    if w is not None:
        for i, v in enumerate(versions):
            pid = str(v.get("plan_id") or "plan_versions[%d]" % i)
            s = fused(w, v.get("factors"))
            if s is None or not isinstance(v.get("fused_score"), (int, float)) \
                    or abs(s - float(v["fused_score"])) > 1e-6:
                rank_.append("%s fused_score 复算不符或缺失" % pid)
        expect_order = [p for p, _s, _r in sorted(
            scored_pairs(versions, w), key=lambda t: (-t[1], -t[2], t[0]))]
        got = list(ranking.get("ordered_ids") or [])
        if expect_order and got and got != expect_order:
            rank_.append("plan_ranking.ordered_ids 与复算顺序不一致")

    if len(scored_pairs(versions, w)) >= 2 if w else len(versions) >= 2:
        expect = compute_sensitivity(versions, w) if w else {}
        if not (sens.get("available") and sens.get("variants")):
            sens_.append("敏感性分析缺失或 variants 为空")
        elif expect.get("available"):
            got_v = {str(x.get("variant")): x for x in (sens.get("variants") or [])
                     if isinstance(x, dict)}
            mism = [x["variant"] for x in (expect.get("variants") or [])
                    if got_v.get(x["variant"], {}).get("winner_id") != x["winner_id"]]
            if mism:
                sens_.append("%d 个变体 winner 与复算不符（首例 %s）" % (len(mism), mism[0]))
            if bool(sens.get("overall_stable")) != bool(expect.get("overall_stable")):
                sens_.append("overall_stable 与复算不符")

    scored_ids = {str(p) for p, _s, _r in (scored_pairs(versions, w) if w else [])}
    top = (ranking.get("ordered_ids") or [None])[0]
    chosen = str(choice.get("chosen_id") or "")
    if not chosen or (top is not None and chosen != str(top)):
        cho.append("chosen_id 缺失或与排序第 1 不一致")
    if not (choice.get("choice_reasons") or []):
        cho.append("choice_reasons 为空")
    rejected = [r for r in (choice.get("rejected") or []) if isinstance(r, dict)]
    miss = [pid for pid in scored_ids if pid != chosen and not any(
        str(r.get("plan_id") or "") == pid
        and str(r.get("rejection_reason") or "").strip() for r in rejected)]
    if miss:
        cho.append("落选方案缺放弃理由登记: %s" % ",".join(miss))
    return {"rubric": rub, "comparability": cmp_, "evidence": evid,
            "ranking": rank_, "sensitivity": sens_, "choice": cho}


def count_caught(report, idx):
    """按 self_check 三元组统计被校验层捕获的违规数（分组）。"""
    def grp(prefixes):
        n = 0
        for key, e in idx.items():
            if any(key.startswith(p) for p in prefixes) and e.get("applied") \
                    and e.get("match") is False:
                n += 1
        return n
    return {"rubric": grp(("rubric.",)),
            "comparability": grp(("comparability.",)),
            "evidence": grp(("evidence.",)),
            "ranking": grp(("plan_versions[", "plan_ranking.")),
            "sensitivity": grp(("sensitivity.",)),
            "choice": grp(("choice.",))}


def mode_metrics(res, report, label):
    idx = check_index(report)
    gt = objective_violations(res)
    caught_d = count_caught(report, idx)
    disabled = set(report.get("disabled_checks") or [])

    missed = {}
    for g in GROUPS:
        if g in disabled:
            missed[g] = len(gt[g])  # 关闭后全部漏检
        else:
            missed[g] = max(len(gt[g]) - caught_d.get(g, 0), 0)

    manual_items = sum(missed.values())
    checks_executed = sum(1 for s in (report.get("self_check") or [])
                          if isinstance(s, dict) and s.get("applied"))
    steps_field = (res.get("result") or {}).get("steps") or []
    steps_done = sum(1 for s in steps_field if isinstance(s, dict)
                     and str(s.get("status") or "done").lower() in ("done", "ok", "completed"))
    rounds = int(math.ceil(manual_items / float(ROUND_BATCH))) if manual_items else 0

    return {
        "mode": label,
        "ablate": report.get("ablate"),
        "verdict": report.get("verdict"),
        "problems": len(report.get("problems") or []),
        "metrics": {
            "rubric_missed": missed["rubric"],
            "comparability_missed": missed["comparability"],
            "evidence_missed": missed["evidence"],
            "ranking_missed": missed["ranking"],
            "sensitivity_missed": missed["sensitivity"],
            "choice_missed": missed["choice"],
            "violations_objective": {g: len(gt[g]) for g in gt},
            "manual_review_items": manual_items,
            "steps_count": checks_executed + steps_done,
            "steps_detail": {"checks_executed": checks_executed,
                             "checks_disabled": len(report.get("disabled_checks") or []),
                             "flow_steps_total": len(steps_field),
                             "flow_steps_done": steps_done},
            "clarification_rounds": rounds,
        },
    }


def inject_pollution(res):
    """在副本上注入污染（不触碰交付文件本身）。返回 (polluted, plan)。"""
    p = copy.deepcopy(res or {})
    inner = p.setdefault("result", {})
    plan = []
    # 污染1：总分篡改
    versions = inner.get("plan_versions") or []
    if versions and isinstance(versions[0], dict) \
            and isinstance(versions[0].get("fused_score"), (int, float)):
        versions[0]["fused_score"] = round(float(versions[0]["fused_score"]) + 0.1234, 4)
        plan.append("plan_versions[0].fused_score 篡改 +0.1234（总分与复算不一致）")
    # 污染2：依据缺失
    if p.get("claims"):
        p["claims"] = []
        plan.append("清空 claims（打分依据回证全部断裂）")
    # 污染3：权重声明破坏
    rub = inner.get("rubric") or {}
    if isinstance(rub.get("weights"), dict):
        rub["weights"]["risk_control"] = None
        plan.append("rubric.weights.risk_control 置 None（权重声明破坏）")
    # 污染4：敏感性清空
    if inner.get("sensitivity"):
        inner["sensitivity"] = {"available": None, "note": "已污染清空"}
        plan.append("清空 result.sensitivity（敏感性分析缺失）")
    # 污染5：放弃理由清空
    fc = inner.get("final_choice") or {}
    if fc.get("rejected"):
        fc["rejected"] = []
        plan.append("清空 final_choice.rejected（放弃理由登记缺失）")
    if not plan:
        plan.append("（无可注入位置：比较要素为空）")
    return p, plan


def count_files(root):
    n = 0
    try:
        for _dirpath, _dirnames, filenames in os.walk(root):
            n += len(filenames)
    except Exception:
        pass
    return n


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--marker", default="/app/work/skill_marker.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 gain_evidence 写入 result.json 的 result.gain_evidence")
        ap.add_argument("--inject-pollution", action="store_true",
                        help="额外生成污染副本做反例自测")
        args = ap.parse_args()
    except Exception as e:
        print("[gain_probe] 参数解析失败（已降级）: %s" % e)
        return 0

    t0 = time.time()
    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[gain_probe] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    rub_path = os.path.join(args.work_dir or ".", "rubric.json")
    rub = load_json(rub_path) if os.path.exists(rub_path) else None
    rubric_state = "enforced" if isinstance(rub, dict) else "not_found"
    marker = load_json(args.marker)
    marker_state = "enforced" if isinstance(marker, dict) and marker.get("all_present") else "not_found"

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state,
                         rubric_state=rubric_state, marker_state=marker_state, ledger=rub)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state,
                           rubric_state=rubric_state, marker_state=marker_state, ledger=rub)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("rubric_missed", "comparability_missed", "evidence_missed",
                  "ranking_missed", "sensitivity_missed", "choice_missed",
                  "manual_review_items", "steps_count", "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "rubric_missed", "mechanism": "权重事前声明检查（五维非负数值合计=1.0、"
         "declared_at 必填、与 rubric.json 台账一致）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后权重事后篡改、声明缺失不再判 FAIL，排序口径失去可辩护性"},
        {"metric": "comparability_missed", "mechanism": "比较口径统一检查（五维定义逐条声明，"
         "每方案×每维度 score+basis+evidence_ref 齐备）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后缺依据的打分格子不再判 FAIL，比较矩阵退化成主观罗列"},
        {"metric": "evidence_missed", "mechanism": "打分依据回证（evidence_ref 须指向带非空 "
         "quote 的 claim；protocol 数值参数逐字回证；risks 含判据止损）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后无出处的分数、无判据的风险不再判 FAIL"},
        {"metric": "ranking_missed", "mechanism": "总分机械复算（fused_score 与 rubric 权重"
         "线性组合逐位对照、ordered_ids 与复算顺序对照）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后总分篡改、排序手工改动不再被检出"},
        {"metric": "sensitivity_missed", "mechanism": "敏感性分析存在且逐变体 winner 可复算"
         "（±0.05~0.20 权重扰动网格）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后敏感性分析可以整体缺席，选择结论的稳健性失去量化证据"},
        {"metric": "choice_missed", "mechanism": "选择与放弃登记（chosen_id==第 1 名、"
         "全部落选方案有非空放弃理由、选择理由非空）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后可以只报 winner 不给弃选理由，选择失去可辩护性"},
        {"metric": "manual_review_items", "mechanism": "六组漏检合计需人工核对条目",
         "formula": "六组 missed 之和", "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐项核对的条目增加"},
        {"metric": "steps_count", "mechanism": "七步线性流程 + 机械校验三元组自检",
         "formula": "校验层已执行检查项数 + 流程层已完成步骤数", "higher_is_better": None,
         "degrade_effect": "关闭检查项会减少执行计数，但换来漏检——步骤少不等于质量高"},
        {"metric": "clarification_rounds", "mechanism": "把人工核对条目按每轮 %d 条打包"
         "（公式随记录落盘）" % ROUND_BATCH,
         "formula": "ceil(manual_review_items / %d)" % ROUND_BATCH,
         "higher_is_better": False,
         "degrade_effect": "人工条目越多，回问/返工所需的轮次越多"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "退化模式关闭六组检查（rubric/comparability/evidence/ranking/sensitivity/choice），"
        "completeness 汇总一致性、verdict 一致性等基础检查仍开启，因此退化侧漏检数是下界"
        "而非最坏情形。",
        "六组违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
        "rubric 未事前声明时排序/敏感性复算真值不可得，相关漏检记 0 但属『无法判定』而非『无违规』。",
        "把 --ablate 的退化结果当作交付自检结论即为误用。",
        "污染反例自测只在副本上注入，原 result.json 不被修改。",
    ]

    gain_evidence = {
        "probe_version": "1.0",
        "probe_tool": "scripts/gain_probe.py",
        "case_id": res.get("case_id"),
        "input": {"result_path": os.path.abspath(args.result),
                  "case_path": os.path.abspath(args.case),
                  "case_contract_state": case_state,
                  "same_input_for_both_runs": True,
                  "run_order": ["normal", "degraded"],
                  "note": "两遍均读取同一份 result.json 内容（深拷贝传入校验函数，不做原地修改）"},
        "runs": [m_normal, m_degraded],
        "delta_normal_minus_degraded": delta,
        "mechanism_to_metric_map": mechanism_map,
        "boundaries": boundaries,
        "failure_conditions": failure_conditions,
        "interpretation_rule": "delta>0 且指标为 lower_is_better 时表示机制带来增益"
                               "（漏检减少）；delta=0 表示该指标在本输入上无区分度。",
    }

    if args.inject_pollution:
        polluted, plan = inject_pollution(res)
        p_path = os.path.join(args.work_dir or ".", "gain_probe_polluted.json")
        save_json(p_path, polluted)
        p_normal = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                           ablate="none", case_state=case_state,
                           rubric_state=rubric_state, marker_state=marker_state, ledger=rub)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state,
                        rubric_state=rubric_state, marker_state=marker_state, ledger=rub)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "rubric_missed": pm_n["metrics"]["rubric_missed"],
                            "comparability_missed": pm_n["metrics"]["comparability_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "ranking_missed": pm_n["metrics"]["ranking_missed"],
                            "sensitivity_missed": pm_n["metrics"]["sensitivity_missed"],
                            "choice_missed": pm_n["metrics"]["choice_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "rubric_missed": pm_d["metrics"]["rubric_missed"],
                              "comparability_missed": pm_d["metrics"]["comparability_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "ranking_missed": pm_d["metrics"]["ranking_missed"],
                              "sensitivity_missed": pm_d["metrics"]["sensitivity_missed"],
                              "choice_missed": pm_d["metrics"]["choice_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                g: pm_d["metrics"]["%s_missed" % g] - pm_n["metrics"]["%s_missed" % g]
                for g in GROUPS},
            "problems": (len(p_deg.get("problems") or [])
                         - len(p_normal.get("problems") or [])),
            "caught_by_normal_mode": bool(p_normal.get("problems")),
            "note": "污染仅注入副本；正常模式须抓到污染项，退化模式漏检属预期。",
        }

    elapsed = round(time.time() - t0, 4)
    try:
        size_bytes = os.path.getsize(args.result)
    except Exception:
        size_bytes = None
    efficiency = {
        "collected_by": "scripts/gain_probe.py（自动采集）",
        "wall_clock_seconds_total": elapsed,
        "result_bytes": size_bytes,
        "input_files_scanned": count_files(os.path.dirname(os.path.abspath(args.case))),
        "checker_runs": 2,
        "checker_checks_executed_normal": m_normal["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_executed_degraded": m_degraded["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_disabled_degraded": m_degraded["metrics"]["steps_detail"]["checks_disabled"],
        "candidates_total": len((res.get("result") or {}).get("plan_versions") or []),
        "manual_review_items_normal": m_normal["metrics"]["manual_review_items"],
        "manual_review_items_degraded": m_degraded["metrics"]["manual_review_items"],
        "clarification_rounds_normal": m_normal["metrics"]["clarification_rounds"],
        "clarification_rounds_degraded": m_degraded["metrics"]["clarification_rounds"],
        "model_requests": None,
        "model_requests_note": "模型请求数由 Agent 侧记录（不可由本脚本采集），"
                               "交付前按实际请求次数回填；缺失时保持 null，不得臆造。",
        "reproduce": "python3 /skills/weekly-skill/scripts/gain_probe.py "
                     "--result /app/output/result.json --case /input/case.json "
                     "--work-dir /app/work --emit-into --inject-pollution",
    }

    out_path = args.out or os.path.join(args.work_dir or ".", "gain_evidence.json")
    save_json(out_path, {"gain_evidence": gain_evidence, "efficiency": efficiency})

    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
                cur["result"]["gain_evidence"] = gain_evidence
                cur["result"]["efficiency"] = efficiency
                save_json(args.result, cur)
        except Exception as e:
            print("[gain_probe] 回写 result.json 失败: %s" % e)

    print("[gain_probe] 正常模式 verdict=%s ｜ 退化模式 verdict=%s"
          % (m_normal["verdict"], m_degraded["verdict"]))
    for name in delta_keys:
        a, b = m_normal["metrics"].get(name), m_degraded["metrics"].get(name)
        print("  %-24s normal=%s  degraded=%s  delta=%s" % (name, a, b, delta.get(name)))
    if "pollution_selftest" in gain_evidence:
        ps = gain_evidence["pollution_selftest"]
        print("  污染反例: caught_by_normal_mode=%s（注入 %d 项）"
              % (ps["caught_by_normal_mode"], len(ps["injected"])))
    print("[gain_probe] 证据落盘: %s" % os.path.abspath(out_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[gain_probe] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
