#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（topic-novelty-audit）。

同一输入跑两遍：正常模式（四组机械校验全部开启）与退化模式（--ablate all，
关闭要素覆盖 / 口径与复算 / 评估回证 / 登记完备性四组检查），逐项对照
可观测指标（全部实测，不臆造）：

  1. structure_missed    要素违规漏检数（四要素缺空未登记 / 可行性缺 status+basis）
  2. scoring_missed      口径与复算漏检数（口径未声明 / 分数复算不符 / 分级矛盾）
  3. evidence_missed     评估回证漏检数（对照结论无引文回证 / claims 链缺失）
  4. review_missed       登记漏项数（uncertain/缺口/冲突升级未进 human_review）
  5. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（正常模式须抓到污染项，退出码恒 0）。

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
    from verify_check import analyze, fused, weights_ok, ELEMENTS, FEAS_KEYS  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3  # 追问轮次折算：每轮最多消化 3 条人工条目
WK = ("novelty", "feasibility", "evidence")


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


def _need_review(it):
    need = []
    if it.get("novelty_grade") == "uncertain":
        need.append("grade=uncertain")
    if it.get("missing_elements"):
        need.append("missing_elements")
    feas = it.get("feasibility") or {}
    for fk in FEAS_KEYS:
        if isinstance(feas.get(fk), dict) and str(feas.get(fk).get("status") or "") in ("missing", "assumption"):
            need.append("feasibility.%s" % fk)
    if it.get("feasibility_verdict") in ("infeasible", "uncertain"):
        need.append("feasibility_verdict")
    return need


def objective_violations(res):
    """独立复算四类客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    props = [it for it in (inner.get("proposals") or []) if isinstance(it, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    human_reg = [h for h in (inner.get("human_review") or []) if isinstance(h, dict)]
    conflicts = inner.get("conflicts") or []
    struct, scoring_bad, evid, review = [], [], [], []

    import re

    def norm(s):
        return re.sub(r"\s+", "", str(s or ""))

    claim_ids = {str(c.get("source_id") or "") for c in claims}
    quote_bank = norm(" ".join(str(e.get("quote") or "") for c in claims
                               for e in (c.get("evidence") or [])))
    for i, it in enumerate(props):
        pid = str(it.get("proposal_id") or i)
        if it.get("judged") is True:
            st = it.get("structure") or {}
            miss = [str(x) for x in (it.get("missing_elements") or [])]
            for el in ELEMENTS:
                if not str(st.get(el) or "").strip() and el not in miss:
                    struct.append("%s.%s" % (pid, el))
            feas = it.get("feasibility") or {}
            for fk in FEAS_KEYS:
                fv = feas.get(fk) if isinstance(feas.get(fk), dict) else {}
                if not (isinstance(fv, dict) and str(fv.get("status") or "").strip() in
                        ("sufficient", "partial", "missing", "assumption")
                        and str(fv.get("basis") or "").strip()):
                    struct.append("%s.feasibility.%s" % (pid, fk))
            ncs_all = [nc for nc in (it.get("novelty_claims") or []) if isinstance(nc, dict)]
            if pid not in claim_ids and not ncs_all:
                # 无任何 novelty_claim 时校验层没有可回证的引文条目——
                # 此情形单独计一条证据违规（有 novelty_claim 的由下方逐条覆盖）
                evid.append("%s(claims 链缺失)" % pid)
            for j, nc in enumerate(ncs_all):
                if not isinstance(nc, dict) or nc.get("overlap") == "uncertain" or not nc.get("overlap"):
                    continue
                q = norm(nc.get("evidence_quote"))
                if not (str(nc.get("closest_work_id") or "").strip() and q and q in quote_bank):
                    evid.append("%s.novelty_claims[%d]" % (pid, j))
        ovs = [str(nc.get("overlap")) for nc in (it.get("novelty_claims") or [])
               if isinstance(nc, dict) and nc.get("overlap")]
        grade = it.get("novelty_grade")
        if grade and ovs:
            if "covered" in ovs and grade != "not_novel":
                scoring_bad.append("%s(covered 却分级 %s)" % (pid, grade))
            if grade in ("breakthrough", "strong") and "none" not in ovs:
                scoring_bad.append("%s(%s 无 none 陈述)" % (pid, grade))
            if grade == "not_novel" and not it.get("duplicate_of"):
                scoring_bad.append("%s(not_novel 未标 duplicate_of)" % pid)
        need = _need_review(it)
        if need and not any(str(h.get("proposal_id")) == pid for h in human_reg):
            review.append("%s(%s)" % (pid, ",".join(need)))
        if it.get("duplicate_of"):
            rec = [c for c in conflicts if isinstance(c, dict)
                   and pid in [str(x) for x in (c.get("item_ids") or [c.get("item_id")])]]
            if not any(str(c.get("resolution")) in ("flagged", "escalated") for c in rec):
                review.append("%s(duplicate_of 未处置)" % pid)

    weights = weights_ok(inner.get("rubric") or {})
    if weights is not None:
        for it in props:
            if not it.get("factors"):
                continue
            s = fused(weights, it.get("factors"))
            stored = it.get("fused_score")
            if s is not None and isinstance(stored, (int, float)) and abs(s - float(stored)) > 1e-6:
                scoring_bad.append("%s(score %s vs %s)" % (it.get("proposal_id"), s, stored))
        scored = [(str(it.get("proposal_id")), fused(weights, it.get("factors")),
                   float((it.get("factors") or {}).get("novelty") or 0.0))
                  for it in props if it.get("factors")]
        exp_order = [p for p, _s, _n in sorted(scored, key=lambda t: (-t[1], -t[2], t[0]))]
        got_order = list((inner.get("ranking") or {}).get("ordered_ids") or [])
        if got_order and exp_order and got_order != exp_order:
            scoring_bad.append("ordered_ids 与复算顺序不一致")
    return {"structure": struct, "scoring": scoring_bad, "evidence": evid, "review": review}


def count_caught(res, report, idx):
    """按 self_check 三元组统计被校验层捕获的违规数。"""
    inner = (res or {}).get("result") or {}
    props = [it for it in (inner.get("proposals") or []) if isinstance(it, dict)]
    s = 0
    for i in range(len(props)):
        keys = ["proposals[%d].element_%s" % (i, el) for el in ELEMENTS] + \
               ["proposals[%d].feas_%s" % (i, fk) for fk in FEAS_KEYS]
        if any(caught(idx, k) for k in keys):
            s += 1
    r = sum(1 for i in range(len(props)) if caught(idx, "proposals[%d].fused_recompute" % i)
            or caught(idx, "proposals[%d].grade_consistency" % i))
    if caught(idx, "ranking.order_recompute"):
        r += 1
    e = sum(1 for i in range(len(props))
            for j in range(20) if caught(idx, "proposals[%d].novelty_backed[%d]" % (i, j)))
    v = sum(1 for i in range(len(props))
            if caught(idx, "proposals[%d].human_review_registered" % i)
            or caught(idx, "proposals[%d].conflict_recorded" % i))
    return s, r, e, v


def mode_metrics(res, report, label):
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    props = [it for it in (inner.get("proposals") or []) if isinstance(it, dict)]
    gt = objective_violations(res)
    s_c, r_c, e_c, v_c = count_caught(res, report, idx)

    disabled = set(report.get("disabled_checks") or [])
    s_missed = max(len(gt["structure"]) - s_c, 0) if "structure" not in disabled else len(gt["structure"])
    r_missed = max(len(gt["scoring"]) - r_c, 0) if "scoring" not in disabled else len(gt["scoring"])
    e_missed = max(len(gt["evidence"]) - e_c, 0) if "evidence" not in disabled else len(gt["evidence"])
    v_missed = max(len(gt["review"]) - v_c, 0) if "review" not in disabled else len(gt["review"])

    missing_factors = sum(1 for it in props if it.get("judged") is True and not it.get("factors"))
    unjudged = sum(1 for it in props if it.get("judged") is not True)
    manual_items = missing_factors + unjudged + s_missed + r_missed + e_missed + v_missed

    checks_executed = sum(1 for s in (report.get("self_check") or [])
                          if isinstance(s, dict) and s.get("applied"))
    steps_field = inner.get("steps") or []
    steps_done = sum(1 for s in steps_field if isinstance(s, dict)
                     and str(s.get("status") or "done").lower() in ("done", "ok", "completed"))
    rounds = int(math.ceil(manual_items / float(ROUND_BATCH))) if manual_items else 0

    return {
        "mode": label,
        "ablate": report.get("ablate"),
        "verdict": report.get("verdict"),
        "problems": len(report.get("problems") or []),
        "metrics": {
            "structure_violations_objective": len(gt["structure"]),
            "structure_caught": s_c,
            "structure_missed": s_missed,
            "scoring_violations_objective": len(gt["scoring"]),
            "scoring_caught": r_c,
            "scoring_missed": r_missed,
            "evidence_violations_objective": len(gt["evidence"]),
            "evidence_caught": e_c,
            "evidence_missed": e_missed,
            "review_violations_objective": len(gt["review"]),
            "review_caught": v_c,
            "review_missed": v_missed,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"missing_factors": missing_factors,
                                        "unjudged": unjudged,
                                        "structure_missed": s_missed,
                                        "scoring_missed": r_missed,
                                        "evidence_missed": e_missed,
                                        "review_missed": v_missed},
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
    props = [it for it in (inner.get("proposals") or []) if isinstance(it, dict)]
    # 1. 要素缺失未登记
    for it in props:
        if it.get("judged") is True:
            it.setdefault("structure", {})["method"] = None
            plan.append("%s 清空 structure.method 且不登记 missing_elements" % it.get("proposal_id"))
            break
    # 2. covered 却标 breakthrough + 引文清空
    for it in props:
        ncs = [nc for nc in (it.get("novelty_claims") or []) if isinstance(nc, dict)]
        if ncs and it.get("judged") is True:
            ncs[0]["overlap"] = "covered"
            ncs[0]["evidence_quote"] = None
            ncs[0]["closest_work_id"] = None
            it["novelty_grade"] = "breakthrough"
            plan.append("%s 首条 novelty_claim 改 covered、清空引文并标 breakthrough" % it.get("proposal_id"))
            break
    # 3. 口径声明清空
    if isinstance(inner.get("rubric"), dict):
        inner["rubric"]["declared_at"] = ""
        plan.append("rubric.declared_at 清空（口径未事前声明）")
    # 4. 清空 human_review
    if inner.get("human_review"):
        inner["human_review"] = []
        plan.append("清空 human_review（登记丢失）")
    # 5. 清空 claims
    p["claims"] = []
    plan.append("清空 claims（评估回证链缺失）")
    if not plan:
        plan.append("（无可注入位置：proposals 为空）")
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
        ap.add_argument("--rubric", default="/app/work/rubric.json")
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
    rub = load_json(args.rubric) if os.path.exists(args.rubric) else None
    rubric_state = "enforced" if isinstance(rub, dict) else "not_found"

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state, rubric_state=rubric_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state, rubric_state=rubric_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("structure_missed", "scoring_missed", "evidence_missed",
                  "review_missed", "manual_review_items", "steps_count",
                  "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "structure_missed", "mechanism": "要素覆盖一致性检查（四要素非空或登记"
         " missing_elements、可行性 status+basis 齐备）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后要素缺空未登记、可行性前提缺来源不再被判 FAIL，选题结构化退化为自述"},
        {"metric": "scoring_missed", "mechanism": "口径事前声明核对 + fused_score 机械复算 +"
         " 期望顺序逐位对照 + 分级一致性（covered⇒not_novel、breakthrough/strong⇒有 none 陈述）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后口径可事后调整、分数被篡改或分级矛盾不再可检出"},
        {"metric": "evidence_missed", "mechanism": "评估回证（每条 novelty_claim 须有"
         " closest_work_id + 引文在 claims 证据链逐字回证；fused_score 数字须出现在 claim text/quote）",
         "formula": "无回证的对照结论/条目数", "higher_is_better": False,
         "degrade_effect": "关闭后证据链缺失不再判 FAIL，『新颖』『可行』退化为无据断言"},
        {"metric": "review_missed", "mechanism": "登记完备性检查（grade=uncertain、缺要素、"
         "可行性 missing/assumption、冲突升级 ⇒ human_review；duplicate_of ⇒ conflicts）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后不确定与缺口可静默漏登记，人工复核入口丢失"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 缺因子（仅已评估计）+ 未评估条目合计",
         "formula": "missing_factors(judged) + unjudged + 四类漏检", "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count", "mechanism": "七步线性流程 + 机械校验三元组自检",
         "formula": "校验层已执行检查项数 + 流程层已完成步骤数", "higher_is_better": None,
         "degrade_effect": "关闭检查项会减少执行计数，但换来漏检——步骤少不等于质量高"},
        {"metric": "clarification_rounds", "mechanism": "把人工核对条目按每轮 %d 条打包"
         "（公式随记录落盘）" % ROUND_BATCH,
         "formula": "ceil(manual_review_items / %d)" % ROUND_BATCH,
         "higher_is_better": False,
         "degrade_effect": "人工条目越多，回原文/回问所需的轮次越多"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "退化模式关闭四组检查（structure/scoring/evidence/review），枚举、结构守卫、"
        "coverage 汇总一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "四类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "新颖性对照仅覆盖输入 known_works 清单范围；『新颖』不作外部新颖性断言。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
        "rubric 未事前声明时排序复算真值不可得，scoring_missed 记 0 但属『无法判定』而非『无违规』。",
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
                           ablate="none", case_state=case_state, rubric_state=rubric_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state, rubric_state=rubric_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "structure_missed": pm_n["metrics"]["structure_missed"],
                            "scoring_missed": pm_n["metrics"]["scoring_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "review_missed": pm_n["metrics"]["review_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "structure_missed": pm_d["metrics"]["structure_missed"],
                              "scoring_missed": pm_d["metrics"]["scoring_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "review_missed": pm_d["metrics"]["review_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "structure_missed": pm_d["metrics"]["structure_missed"]
                                    - pm_n["metrics"]["structure_missed"],
                "scoring_missed": pm_d["metrics"]["scoring_missed"]
                                  - pm_n["metrics"]["scoring_missed"],
                "evidence_missed": pm_d["metrics"]["evidence_missed"]
                                   - pm_n["metrics"]["evidence_missed"],
                "review_missed": pm_d["metrics"]["review_missed"]
                                 - pm_n["metrics"]["review_missed"],
                "problems": (len(p_deg.get("problems") or [])
                             - len(p_normal.get("problems") or [])),
            },
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
        "proposals_total": len([it for it in ((res.get("result") or {}).get("proposals") or [])
                                if isinstance(it, dict)]),
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
        print("  %-22s normal=%s  degraded=%s  delta=%s" % (name, a, b, delta.get(name)))
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
