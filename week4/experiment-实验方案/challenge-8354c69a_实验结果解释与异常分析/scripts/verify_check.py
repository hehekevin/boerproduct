#!/usr/bin/env python3
"""verify_check.py — Step 6 主校验器（exp-result-explain）。

八组校验（问题串带组标签）：[enum] 枚举与映射、[coverage] 五分面覆盖、
[alignment] 对齐口径一致、[pairing] 异常-原因配对、[evidence] 解释回证与数字
回证、[recheck] 复核可执行性、[anomaly_check] 复算对照、[structure]/[contract]
结构与契约。报告 verdict（PASS/FAIL）+ problems；退出码恒为 0，绝不中断交付。
--emit-into 时把 self_check / gates / unbacked_numbers / unbacked_evidence /
validator_verdict 写回 result.json（仅这五个键归本脚本）。

用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--rules /app/work/judge_rules.json] [--out /app/work/verify_check.json] [--emit-into]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

JUDGMENTS = {"supported", "concerns", "inadequate", "unreported", "not_applicable", "unassessable"}
RUN_STATES = {"success", "partial", "unable_to_determine", "refused"}
DOMAINS_REQUIRED = ["trend", "anomaly", "cause", "recheck", "followup"]
RESULT_REQUIRED = [
    "material_gaps", "environment", "analysis_scope", "checklist", "judge_rules",
    "analyses", "trend_anomaly_check", "explain_summary", "coverage", "pending_review",
    "steps", "run_status", "verdict", "verdict_basis", "gain_evidence", "efficiency",
]
TOP_REQUIRED = ["case_id", "status", "result", "claims", "uncertainties", "changelog"]
NUM_RE = re.compile(r"(?<![\w.])(\d+\.\d+|\d+)(?![\w])")


def contract_fields(case):
    try:
        oc = case.get("output_contract") if isinstance(case, dict) else None
        if oc is None:
            return []
        if isinstance(oc, dict):
            for key in ("fields", "required_fields", "result.json", "result"):
                v = oc.get(key)
                if isinstance(v, list):
                    return [str(x) for x in v]
            return [str(k) for k in oc.keys()]
        if isinstance(oc, list):
            return [str(x) for x in oc]
    except Exception:
        pass
    return []


def load_rules(path, result):
    rules = None
    try:
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                rules = json.load(f)
    except Exception:
        rules = None
    if not isinstance(rules, dict):
        rules = (result.get("result") or {}).get("judge_rules") or {}
    return rules


def has_evidence(item):
    if not isinstance(item, dict):
        return False
    return bool(str(item.get("evidence_quote") or "").strip()) and bool(str(item.get("evidence_location") or "").strip())


def check(result, case, rules, case_text):
    """返回 (problems, unbacked_numbers, unbacked_evidence)。"""
    P, UB_NUM, UB_EV = [], [], []
    inner = result.get("result") if isinstance(result, dict) else None
    if not isinstance(inner, dict):
        P.append("[structure] result 应为对象")
        return P, UB_NUM, UB_EV
    rules = rules or inner.get("judge_rules") or {}
    grade_map = rules.get("grade_map") or {}
    category_map = rules.get("category_map") or {}
    verdicts = rules.get("alignment_verdicts") or ["supported", "partially_supported", "not_supported", "unassessable"]
    anomaly_types = set(rules.get("anomaly_types") or ["outlier", "jump", "plateau"])
    cause_cats = set(rules.get("cause_categories") or ["instrument", "operation", "sample", "environment", "unknown"])
    vague_words = [str(w).lower() for w in (rules.get("vague_recheck_words") or ["检查数据质量", "check data quality"])]

    # ---- [enum] 枚举与映射 ----
    analyses = inner.get("analyses") or []
    for a in analyses:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("analysis_id") or "?")
        align = a.get("alignment") or {}
        v = align.get("verdict")
        if v is not None and v not in verdicts:
            P.append("[%s][enum] alignment.verdict=%s 非法" % (aid, v))
        for x in a.get("anomalies") or []:
            if isinstance(x, dict) and x.get("anomaly_type") not in anomaly_types:
                P.append("[%s][enum] anomaly_type=%s 非法" % (aid, x.get("anomaly_type")))
        for x in a.get("causes") or []:
            if isinstance(x, dict) and x.get("category") not in cause_cats:
                P.append("[%s][enum] cause.category=%s 非法" % (aid, x.get("category")))
        for ap in a.get("appraisals") or []:
            if not isinstance(ap, dict):
                continue
            j = ap.get("judgment")
            if j not in JUDGMENTS:
                P.append("[%s][enum] judgment=%s 非法" % (aid, j))
                continue
            if ap.get("grade") != grade_map.get(j):
                P.append("[%s][enum] grade=%s 与 grade_map[%s]=%s 不符"
                         % (aid, ap.get("grade"), j, grade_map.get(j)))
            if ap.get("category") != category_map.get(j):
                P.append("[%s][enum] category=%s 与 category_map[%s]=%s 不符"
                         % (aid, ap.get("category"), j, category_map.get(j)))
            if j in {"concerns", "inadequate", "unreported"} and \
                    str(ap.get("bias_direction") or "") not in {"against_conclusion", "favors_conclusion"}:
                P.append("[%s][enum] 负面判定 bias_direction 非法/缺失" % aid)
        rs = inner.get("run_status") or {}
        if rs.get("state") is not None and rs.get("state") not in RUN_STATES:
            P.append("[enum] run_status.state=%s 非法" % rs.get("state"))

    # ---- [coverage] 五分面覆盖 ----
    for a in analyses:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("analysis_id") or "?")
        appraisals = a.get("appraisals") or []
        seen = {str(x.get("domain")) for x in appraisals if isinstance(x, dict)}
        for d in DOMAINS_REQUIRED:
            if d not in seen:
                P.append("[%s][coverage] 缺分面 %s" % (aid, d))
        for x in appraisals:
            if not isinstance(x, dict):
                continue
            j = x.get("judgment")
            if j not in JUDGMENTS:
                continue
            if j in {"unassessable", "not_applicable"} and not str(x.get("abstain_reason") or x.get("na_reason") or "").strip():
                P.append("[%s][coverage] %s 判 %s 但缺 abstain/na 说明" % (aid, x.get("checklist_id"), j))
            if j in {"supported", "concerns", "inadequate"} and not str(x.get("evidence_quote") or "").strip():
                P.append("[%s][coverage] %s 判 %s 但缺 evidence_quote" % (aid, x.get("checklist_id"), j))
            if not str(x.get("rationale") or "").strip():
                P.append("[%s][coverage] %s 缺 rationale" % (aid, x.get("checklist_id")))
        if a.get("judged") is not True and not any(
                x.get("judgment") == "unassessable" for x in appraisals if isinstance(x, dict)):
            P.append("[%s][coverage] judged!=true 且无弃权说明" % aid)

    # ---- [alignment] 对齐口径一致 ----
    pending_ids = {str(x.get("analysis_id")) for x in (inner.get("pending_review") or []) if isinstance(x, dict)}
    es = {str(x.get("analysis_id")): x for x in ((inner.get("explain_summary") or {}).get("per_analysis") or [])
          if isinstance(x, dict)}
    for a in analyses:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("analysis_id") or "?")
        align = a.get("alignment") or {}
        v = align.get("verdict")
        if not str(align.get("basis") or "").strip():
            P.append("[%s][alignment] verdict 缺 basis" % aid)
        if v and not str(align.get("evidence_quote") or "").strip():
            P.append("[%s][alignment] verdict 缺 evidence_quote" % aid)
        neg = any(x.get("judgment") in {"inadequate", "unreported"} for x in (a.get("appraisals") or []) if isinstance(x, dict))
        unass = any(x.get("judgment") == "unassessable" for x in (a.get("appraisals") or []) if isinstance(x, dict))
        if v == "supported" and (neg or unass):
            P.append("[%s][alignment] verdict=supported 但存在负面/弃权条目（口径矛盾）" % aid)
        if v == "unassessable" and aid not in pending_ids:
            P.append("[%s][alignment] verdict=unassessable 未登记 pending_review" % aid)
        e = es.get(aid)
        if e is not None and e.get("alignment_consistent") is False:
            P.append("[%s][alignment] explain_summary 判 alignment_consistent=false" % aid)

    # ---- [pairing] 异常-原因配对 ----
    for a in analyses:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("analysis_id") or "?")
        anom_ids = {str(x.get("anomaly_id")) for x in (a.get("anomalies") or [])
                    if isinstance(x, dict) and x.get("anomaly_id")}
        bound = {}
        for c in a.get("causes") or []:
            if isinstance(c, dict) and c.get("anomaly_id"):
                bound[str(c.get("anomaly_id"))] = bound.get(str(c.get("anomaly_id")), 0) + 1
        for i in anom_ids:
            if bound.get(i, 0) < 1:
                P.append("[%s][pairing] 异常 %s 无绑定 cause" % (aid, i))
        for c in a.get("causes") or []:
            if isinstance(c, dict) and c.get("anomaly_id") and str(c.get("anomaly_id")) not in anom_ids:
                P.append("[%s][pairing] cause %s 回指不存在的 anomaly_id=%s"
                         % (aid, c.get("cause_id"), c.get("anomaly_id")))
        e = es.get(aid)
        if e is not None and e.get("pairing_complete") is False:
            P.append("[%s][pairing] explain_summary 判 pairing_complete=false" % aid)

    # ---- [evidence] 解释回证 ----
    def ev_check(aid, kind, item):
        if not isinstance(item, dict):
            return
        q = str(item.get("evidence_quote") or "").strip()
        if not q:
            P.append("[%s][evidence] %s/%s 缺 evidence_quote" % (aid, kind, item.get("anomaly_id") or item.get("cause_id") or item.get("recheck_id") or item.get("followup_id") or "top"))
            return
        if q not in case_text:
            P.append("[%s][evidence] %s/%s 引文无逐字回证" % (aid, kind, item.get("anomaly_id") or item.get("cause_id") or "top"))
            UB_EV.append({"analysis_id": aid, "kind": kind, "quote": q[:120]})

    for a in analyses:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("analysis_id") or "?")
        ev_check(aid, "trend", a.get("trend") or {})
        ev_check(aid, "alignment", a.get("alignment") or {})
        for x in a.get("anomalies") or []:
            ev_check(aid, "anomaly", x)
        for x in a.get("causes") or []:
            ev_check(aid, "cause", x)
        for x in a.get("rechecks") or []:
            ev_check(aid, "recheck", x)
        for x in a.get("followups") or []:
            ev_check(aid, "followup", x)

    # claims 数字回证
    rec_json = json.dumps(inner.get("trend_anomaly_check") or {}, ensure_ascii=False)
    rec_nums = [float(m) for m in re.findall(r"-?\d+\.\d+|-?\d+", rec_json)]
    for c in result.get("claims") or []:
        if not isinstance(c, dict):
            continue
        text = str(c.get("text") or "")
        for m in NUM_RE.finditer(text):
            tok = m.group(1)
            fval = float(tok)
            if tok in case_text:
                continue
            backed = any(abs(fval - r) <= max(0.005 * abs(r), 0.005 * max(abs(fval), 1.0)) for r in rec_nums)
            if not backed:
                UB_NUM.append({"claim_id": c.get("claim_id"), "number": tok})
                P.append("[evidence] claim %s 数字 %s 未回证（case 文本与复算均无）" % (c.get("claim_id"), tok))

    # ---- [recheck] 复核可执行性 ----
    for a in analyses:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("analysis_id") or "?")
        for r in a.get("rechecks") or []:
            if not isinstance(r, dict):
                continue
            rid = str(r.get("recheck_id") or "recheck")
            action = str(r.get("action") or "").strip()
            four = bool(action) and bool(str(r.get("target_file") or "").strip()) \
                and (bool(str(r.get("target_field") or "").strip()) or bool(str(r.get("method") or "").strip())) \
                and bool(str(r.get("expected_outcome") or "").strip())
            vague = any(w in action.lower() for w in vague_words)
            if r.get("executable") is True and (not four or vague):
                P.append("[%s][recheck] %s 标 executable=true 但四要素缺失或空话" % (aid, rid))
            if not four:
                P.append("[%s][recheck] %s 四要素不齐（action/target_file/target_field或method/expected_outcome）" % (aid, rid))

    # ---- [anomaly_check] 复算对照 ----
    tac = inner.get("trend_anomaly_check") or {}
    pd_map = {str(x.get("analysis_id")): x for x in (tac.get("per_dataset") or []) if isinstance(x, dict)}
    for a in analyses:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("analysis_id") or "?")
        e = pd_map.get(aid)
        if e is None:
            P.append("[%s][anomaly_check] trend_anomaly_check 缺该组复算（未跑 Step 3？）" % aid)
        elif e.get("status") == "ok" and e.get("match") is not True:
            for d in e.get("diffs") or []:
                P.append("[%s][anomaly_check] %s" % (aid, d))
        elif e.get("status") == "unavailable":
            mg = inner.get("material_gaps") or []
            if aid not in json.dumps(mg, ensure_ascii=False):
                P.append("[%s][anomaly_check] 复算 unavailable 但 material_gaps 未登记" % aid)

    # ---- [structure]/[contract] ----
    if not inner.get("steps"):
        P.append("[structure] steps 为空")
    cov = inner.get("coverage") or {}
    try:
        items = sum(len(a.get("appraisals") or []) for a in analyses if isinstance(a, dict))
        judged = sum(1 for a in analyses for x in (a.get("appraisals") or [])
                     if isinstance(x, dict) and x.get("judged") is True)
        if cov.get("datasets_total") != len(analyses):
            P.append("[structure] coverage.datasets_total=%s 与 analyses 数 %d 不符" % (cov.get("datasets_total"), len(analyses)))
        if cov.get("items_total") != items:
            P.append("[structure] coverage.items_total=%s 与实际 %d 不符" % (cov.get("items_total"), items))
        if cov.get("judged_items") != judged:
            P.append("[structure] coverage.judged_items=%s 与实际 %d 不符" % (cov.get("judged_items"), judged))
    except Exception as e:
        P.append("[structure] coverage 核对异常: %s" % e)
    v = inner.get("verdict")
    if v == "audited" and any(not a.get("judged") for a in analyses if isinstance(a, dict)):
        P.append("[structure] verdict=audited 但存在未判定组")
    if v == "cannot_verify" and not inner.get("material_gaps"):
        P.append("[structure] verdict=cannot_verify 但 material_gaps 为空")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in (None, "success") and not rs.get("reason"):
        P.append("[structure] run_status 非 success 但缺 reason")
    if not result.get("case_id"):
        P.append("[contract] 缺 case_id")
    for f in TOP_REQUIRED:
        if f not in result:
            P.append("[contract] 缺顶层字段: %s" % f)
    for f in RESULT_REQUIRED:
        if f not in inner:
            P.append("[contract] 缺业务字段: result.%s" % f)
    for f in contract_fields(case):
        if f not in result:
            P.append("[contract] 缺 output_contract 字段: %s" % f)
    return P, UB_NUM, UB_EV


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--rules", default=None)
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")
    marker_hit = os.path.exists(marker)
    problems, result, case = [], {}, {}
    gates = []

    try:
        if os.path.exists(args.result):
            with open(args.result, "r", encoding="utf-8") as f:
                result = json.load(f)
        else:
            problems.append("[contract] result.json 不存在")
            gates.append({"gate": "result_exists", "state": "not_found", "note": args.result})
    except Exception as e:
        problems.append("[contract] result.json 读取失败: %s" % e)
        gates.append({"gate": "result_exists", "state": "invalid", "note": str(e)})
    try:
        if os.path.exists(args.case):
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
            gates.append({"gate": "case_contract", "state": "enforced", "note": ""})
        else:
            gates.append({"gate": "case_contract", "state": "not_found", "note": args.case})
    except Exception as e:
        gates.append({"gate": "case_contract", "state": "invalid", "note": str(e)})
    if not marker_hit:
        gates.append({"gate": "skill_marker", "state": "not_found", "note": "脚本未与 SKILL.md 同包"})
    else:
        gates.append({"gate": "skill_marker", "state": "enforced", "note": ""})

    case_text = ""
    try:
        case_text = json.dumps(case, ensure_ascii=False)
    except Exception:
        case_text = ""

    UB_NUM, UB_EV = [], []
    if result:
        try:
            rules = load_rules(args.rules, result)
            problems, UB_NUM, UB_EV = check(result, case, rules, case_text)
        except Exception as e:
            problems.append("[structure] 校验器内部异常: %s" % e)

    verdict = "PASS" if not problems else "FAIL"
    report = {"ok": not problems, "verdict": verdict, "problems": problems,
              "counts": {"problems": len(problems), "unbacked_numbers": len(UB_NUM),
                         "unbacked_evidence": len(UB_EV)}}
    try:
        if args.out:
            d = os.path.dirname(args.out)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass

    if args.emit_into and result:
        try:
            result["validator_verdict"] = verdict      # 仅以下键归 verify_check.py
            result["self_check"] = [{"item": "verify_check 八组校验", "template_value": "verdict=PASS",
                                     "applied": True, "match": verdict == "PASS"}]
            result["unbacked_numbers"] = UB_NUM
            result["unbacked_evidence"] = UB_EV
            result["gates"] = gates
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[verify_check] 回写失败: %s" % e)

    print("[verify_check] verdict=%s（问题 %d 处，退出码恒 0）| marker_hit=%s"
          % (verdict, len(problems), marker_hit))
    for p in problems[:40]:
        print("  - %s" % p)
    if len(problems) > 40:
        print("  ... 共 %d 处" % len(problems))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[verify_check] 未预期异常（已降级）: %s" % e)
        sys.exit(0)
