#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（cov-gap-audit）。

同一输入跑两遍：正常模式（四组机械校验全部开启）与退化模式（--ablate all，
关闭分母口径 / 遗漏登记完备 / 补检真实收益 / 证据回证四组检查），逐项对照
可观测指标（全部实测，不臆造）：

  1. denominator_missed  分母/覆盖率口径违规漏检数（防"以结果定义分母"）
  2. attribution_missed  遗漏登记/归因违规漏检数（防"把没找到当作不相关"与归因泛泛）
  3. supplement_missed   补检空转/口径违规漏检数（防"补检空转"）
  4. evidence_missed     证据回证缺失漏检数
  5. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（注入领域化污染：篡改覆盖率为 1.0、清空遗漏登记、归因清空、补检空转、清空
证据链；正常模式须抓到，退出码恒 0）。

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
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3  # 追问轮次折算：每轮最多消化 3 条人工条目


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
    """独立复算四类客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    reg = [r for r in (inner.get("miss_registry") or []) if isinstance(r, dict)]
    supp = inner.get("supplementary") if isinstance(inner.get("supplementary"), dict) else {}
    refset = inner.get("reference_set") if isinstance(inner.get("reference_set"), dict) else {}
    cov = inner.get("coverage") if isinstance(inner.get("coverage"), dict) else {}
    qids = {str(q.get("query_id")) for q in (inner.get("queries") or []) if isinstance(q, dict) and q.get("query_id")}

    denom, attr, suppl, evid = [], [], [], []
    if refset.get("frozen") is not True or not str(refset.get("frozen_at") or "").strip():
        denom.append("reference_set 未冻结")
    included_n = sum(1 for it in items if it.get("ref_status") == "included")
    hit_n = sum(1 for it in items if it.get("hit_status") == "hit")
    miss_n = sum(1 for it in items if it.get("hit_status") == "miss")
    if included_n:
        exp = round(hit_n / included_n, 4)
        if cov.get("coverage_rate") != exp:
            denom.append("coverage_rate=%r 复算期望 %s" % (cov.get("coverage_rate"), exp))
        exp_miss = round(miss_n / included_n, 4)
        if cov.get("miss_rate") != exp_miss:
            denom.append("miss_rate 复算不符")
    if cov.get("total_reference") != len(items):
        denom.append("total_reference 与条目数不符")
    if cov.get("denominator_basis") not in ("frozen_reference_set", None):
        denom.append("denominator_basis 非法")
    if cov.get("coverage_rate") == 1.0 and miss_n > 0:
        denom.append("rate=1.0 但有 miss")

    reg_by = {}
    for r in reg:
        reg_by.setdefault(str(r.get("ref_id")), []).append(r)
    miss_ids = {str(it.get("ref_id")) for it in items if it.get("hit_status") == "miss"}
    for rid in sorted(miss_ids):
        es = reg_by.get(rid) or []
        if len(es) != 1:
            attr.append("%s 登记缺失或重复" % rid)
            continue
        e = es[0]
        att = e.get("attribution") if isinstance(e.get("attribution"), dict) else {}
        if e.get("category") not in ("synonym_gap", "field_narrow", "time_window",
                                     "source_gap", "identifier_anomaly", "other"):
            attr.append("%s category 非法" % rid)
        if not all(str(att.get(k) or "").strip() for k in ("query_id", "field", "source_db", "reason")):
            attr.append("%s 归因不完整" % rid)
        if str(att.get("query_id") or "") not in qids:
            attr.append("%s query_id 不存在于查询清单" % rid)
    for rid in reg_by:
        if rid not in miss_ids:
            attr.append("%s 错登记" % rid)

    supp_q = [q for q in (supp.get("queries") or []) if isinstance(q, dict)]
    all_hits = []
    for q in supp_q:
        for h in (q.get("new_hits") or []):
            all_hits.append(str(h))
            if str(h) not in miss_ids:
                suppl.append("%s new_hits 含非 miss %r" % (q.get("query_id"), h))
    if supp.get("effective") is True and len(set(all_hits)) == 0:
        suppl.append("补检空转：effective=true 但新增命中 0")
    if supp.get("new_hits_total") is not None and supp.get("new_hits_total") != len(set(all_hits)):
        suppl.append("new_hits_total 与复算不符")
    if included_n:
        exp_post = round((hit_n + len(set(all_hits))) / included_n, 4)
        if supp.get("post_coverage_rate") != exp_post:
            suppl.append("post_coverage_rate 复算不符")
    for r in (supp.get("residual_misses") or []):
        if isinstance(r, dict):
            rid = str(r.get("ref_id") or "")
            if rid not in miss_ids or rid in set(all_hits) or not str(r.get("explanation") or "").strip():
                suppl.append("残余遗漏 %r 违规" % rid)

    claim_ids = {str(c.get("source_id") or "") for c in claims}
    for it in items:
        if it.get("hit_status") == "hit":
            rid = str(it.get("ref_id"))
            if not str(it.get("rationale") or "").strip() or not str(it.get("evidence_quote") or "").strip() \
               or rid not in claim_ids:
                evid.append(rid)
    return {"denominator": denom, "attribution": attr,
            "supplement": suppl, "evidence": evid}


def count_caught(report, idx, n_items):
    """按 self_check 三元组统计被校验层捕获的违规数。"""
    d = sum(1 for k in ("reference_set.frozen", "coverage.basis", "coverage.total_reference",
                        "coverage.included_unavailable", "coverage.hit_miss", "coverage.rate_recompute")
            if caught(idx, k))
    a = sum(1 for i in range(n_items) if caught(idx, "items[%d].miss_registered" % i))
    s = sum(1 for k in ("supplement.effective_consistency", "supplement.post_rate")
            if caught(idx, k))
    s += sum(1 for k in list(idx) if (k.startswith("supplement.new_hits_valid")
                                      or k.startswith("supplement.residual_")) and caught(idx, k))
    e = sum(1 for i in range(n_items) if caught(idx, "items[%d].evidence_backed" % i))
    return d, a, s, e


def mode_metrics(res, report, label):
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    gt = objective_violations(res)
    d_caught, a_caught, s_caught, e_caught = count_caught(report, idx, len(items))
    disabled = set(report.get("disabled_checks") or [])
    d_missed = len(gt["denominator"]) if "denominator" in disabled else max(len(gt["denominator"]) - d_caught, 0)
    a_missed = len(gt["attribution"]) if "attribution" in disabled else max(len(gt["attribution"]) - a_caught, 0)
    s_missed = len(gt["supplement"]) if "supplement" in disabled else max(len(gt["supplement"]) - s_caught, 0)
    e_missed = len(gt["evidence"]) if "evidence" in disabled else max(len(gt["evidence"]) - e_caught, 0)

    unjudged = sum(1 for it in items if it.get("judged") is not True)
    manual_items = unjudged + d_missed + a_missed + s_missed + e_missed
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
            "denominator_violations_objective": len(gt["denominator"]),
            "denominator_missed": d_missed,
            "attribution_violations_objective": len(gt["attribution"]),
            "attribution_missed": a_missed,
            "supplement_violations_objective": len(gt["supplement"]),
            "supplement_missed": s_missed,
            "evidence_violations_objective": len(gt["evidence"]),
            "evidence_missed": e_missed,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"unjudged": unjudged, "denominator_missed": d_missed,
                                        "attribution_missed": a_missed, "supplement_missed": s_missed,
                                        "evidence_missed": e_missed},
            "steps_count": checks_executed + steps_done,
            "steps_detail": {"checks_executed": checks_executed,
                             "checks_disabled": len(report.get("disabled_checks") or []),
                             "flow_steps_total": len(steps_field),
                             "flow_steps_done": steps_done},
            "clarification_rounds": rounds,
        },
    }


def inject_pollution(res):
    """在副本上注入领域化污染（不触碰交付文件本身）。返回 (polluted, plan)。"""
    p = copy.deepcopy(res or {})
    inner = p.setdefault("result", {})
    plan = []
    cov = inner.get("coverage") if isinstance(inner.get("coverage"), dict) else None
    if cov is not None and cov.get("coverage_rate") is not None:
        cov["coverage_rate"] = 1.0
        plan.append("coverage_rate 篡改为 1.0（模拟『以结果定义分母』）")
    reg = inner.get("miss_registry") or []
    if reg:
        dropped = reg.pop(0)
        plan.append("清空 %s 的遗漏登记（遗漏未登记）" % dropped.get("ref_id"))
    for it in (inner.get("items") or []):
        if isinstance(it, dict) and it.get("hit_status") == "miss":
            it["matched_by"] = None
            it["evidence_quote"] = None
            plan.append("%s 命中证据与匹配方式清空（证据链断裂）" % it.get("ref_id"))
            break
    supp = inner.get("supplementary") if isinstance(inner.get("supplementary"), dict) else None
    if supp is not None:
        for q in (supp.get("queries") or []):
            if isinstance(q, dict):
                q["new_hits"] = []
        if supp.get("effective") is not None or supp.get("queries"):
            supp["effective"] = True
            plan.append("补检 new_hits 清空且 effective=true（补检空转反例）")
    if p.get("claims"):
        p["claims"] = []
        plan.append("清空 claims（证据链缺失）")
    if not plan:
        plan.append("（无可注入位置：结构不完整）")
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
        ap.add_argument("--ledger", default="/app/work/coverage_ledger.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 gain_evidence 写入 result.json 的 result.gain_evidence")
        ap.add_argument("--inject-pollution", action="store_true",
                        help="额外生成污染副本做反例自测")
        try:
            args = ap.parse_args()
        except SystemExit:
            print("[gain_probe] 参数解析失败（argparse error，按契约退出码 0）")
            return 0
    except Exception as e:
        print("[gain_probe] 参数初始化失败: %s" % e)
        return 0

    t0 = time.time()
    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[gain_probe] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    ledger = load_json(args.ledger) if os.path.exists(args.ledger) else None
    ledger_state = "enforced" if isinstance(ledger, dict) else "not_found"

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state, ledger_state=ledger_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state, ledger_state=ledger_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("denominator_missed", "attribution_missed", "supplement_missed",
                  "evidence_missed", "manual_review_items", "steps_count",
                  "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "denominator_missed", "mechanism": "分母口径校验（参考集冻结、分母=included、"
         "coverage_rate=hit/included 机械复算、rate=1.0 与 miss 矛盾检测）",
         "formula": "客观违规数 − 被校验层捕获数（退化模式=客观违规数）", "higher_is_better": False,
         "degrade_effect": "关闭后覆盖率被篡改（如以结果定义分母得 1.0）不再可检出"},
        {"metric": "attribution_missed", "mechanism": "遗漏登记完备性校验（每条 miss 恰一条登记、"
         "category 枚举、attribution 四元组完整且 query_id 可回溯到查询清单）",
         "formula": "客观违规数 − 被校验层捕获数（退化模式=客观违规数）", "higher_is_better": False,
         "degrade_effect": "关闭后遗漏可被划掉不登记、归因泛泛不落到查询式/字段/来源"},
        {"metric": "supplement_missed", "mechanism": "补检真实收益校验（new_hits⊆miss、查询式不与原查询"
         "重复、effective 与实际一致、post 覆盖率复算、残余遗漏有解释）",
         "formula": "客观违规数 − 被校验层捕获数（退化模式=客观违规数）", "higher_is_better": False,
         "degrade_effect": "关闭后补检空转（换同义词重跑却报告遗漏下降）不再可检出"},
        {"metric": "evidence_missed", "mechanism": "claims 证据链回证（hit 条目 evidence_quote 逐字回证；"
         "coverage_rate/miss_rate/post 数字回证，显式字符类定界、DOI 内嵌数字排除）",
         "formula": "无回证的 hit 条目数 + 未回证数字数", "higher_is_better": False,
         "degrade_effect": "关闭后证据链缺失与数字无回证不再判 FAIL"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 未判定条目合计",
         "formula": "unjudged + 四类漏检", "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count", "mechanism": "七步线性流程 + 机械校验三元组自检",
         "formula": "校验层已执行检查项数 + 流程层已完成步骤数", "higher_is_better": None,
         "degrade_effect": "关闭检查项会减少执行计数，但换来漏检——步骤少不等于质量高"},
        {"metric": "clarification_rounds", "mechanism": "把人工核对条目按每轮 %d 条打包（公式随记录落盘）"
         % ROUND_BATCH,
         "formula": "ceil(manual_review_items / %d)" % ROUND_BATCH,
         "higher_is_better": False,
         "degrade_effect": "人工条目越多，回原文/回问所需的轮次越多"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "退化模式关闭四组检查（denominator/attribution/supplement/evidence），枚举、结构守卫、"
        "coverage.judged 汇总、verdict 一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "四类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
        "coverage_ledger.json 缺失 → coverage_ledger 闸门记 not_found，分母口径不得宣称已核对。",
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
                  "coverage_ledger_state": ledger_state,
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
                           ablate="none", case_state=case_state, ledger_state=ledger_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state, ledger_state=ledger_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "denominator_missed": pm_n["metrics"]["denominator_missed"],
                            "attribution_missed": pm_n["metrics"]["attribution_missed"],
                            "supplement_missed": pm_n["metrics"]["supplement_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "denominator_missed": pm_d["metrics"]["denominator_missed"],
                              "attribution_missed": pm_d["metrics"]["attribution_missed"],
                              "supplement_missed": pm_d["metrics"]["supplement_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "denominator_missed": pm_d["metrics"]["denominator_missed"]
                                      - pm_n["metrics"]["denominator_missed"],
                "attribution_missed": pm_d["metrics"]["attribution_missed"]
                                      - pm_n["metrics"]["attribution_missed"],
                "supplement_missed": pm_d["metrics"]["supplement_missed"]
                                     - pm_n["metrics"]["supplement_missed"],
                "evidence_missed": pm_d["metrics"]["evidence_missed"]
                                   - pm_n["metrics"]["evidence_missed"],
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
        "items_total": len([it for it in ((res.get("result") or {}).get("items") or [])
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
