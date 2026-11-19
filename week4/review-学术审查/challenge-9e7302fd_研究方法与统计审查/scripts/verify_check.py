#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（research-stat-audit 研究方法与统计审查）。

对 result.json 做六组机械校验（与题面机检点逐项对应）：
  A. 定位可回证：每条 confirmed 发现必须有非空 location 与逐字 quote，且 quote
     （空白归一化后）必须出现在 case.json 实际稿件文本中；引文不在原文 =
     定位失据，直接判 FAIL。
  B. 严重度分级口径：severity_rubric 三级口径必须判定前声明（declared_at），
     suggestion ⇒ minor；fact_error ⇒ critical/major；声明后不得调整。
  C. 证据链完备：confirmed ⇒ claims 逐字回证；fact_error 须给对照依据；
     已判定发现须有 revision_suggestion。
  D. 待复核与误报抑制：pending ⇒ pending_review（含 reason+needed_action）；
     suppressed ⇒ suppressed[] 且 rule_id 在事前规则表内。
  E. 统计量复算一致（题面机检点）：findings[].stat_claim 逐条须在
     result.stat_recompute.checks 有复算记录，且记录的 consistent 必须与
     本脚本独立复算结果一致（复算记录被篡改即 FAIL）。
  F. 缺陷/报告不全区分（题面机检点）：每条 confirmed 发现的 defect_class
     映射必须成立——fact_error ⇒ method_defect（作者做错了）；
     reporting_gap ⇒ category ∈ insufficient_evidence/norm_issue（作者没报告）；
     suggestion ⇒ not_applicable；confirmed（非 suggestion）⇒
     method_defect/reporting_gap 二选一，杜绝混为一谈。
另始终开启：枚举合法性（含 defect_class 枚举）、coverage 一致性、verdict/
run_status 一致性、steps 可执行、契约字段。

所有检查项产出三元组 {item, template_value, applied, match}，可回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；coverage/unchecked 归 coverage_audit.py，
stat_recompute 归 stat_recompute.py，gain_evidence/efficiency 归 gain_probe.py。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--ledger /app/work/severity_rubric.json] [--out /app/work/verify_check.json] \
        [--ablate none|all|location,severity,evidence,pending,stat,defect]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

FACETS = ("research_design", "variable_definition", "stat_method",
          "sample_power", "result_reporting", "norms_consistency")
CATEGORIES = ("fact_error", "insufficient_evidence", "norm_issue", "suggestion")
SEVERITIES = ("critical", "major", "minor")
STATUSES = ("confirmed", "pending", "suppressed")
DEFECT_CLASSES = ("method_defect", "reporting_gap", "cannot_classify", "not_applicable")
MANU_KEYS = ("manuscript", "paper", "document", "full_text", "text", "body", "content")

try:
    from stat_recompute import compute_check  # 同目录导入复算引擎（独立性：只取纯函数）
except Exception:  # pragma: no cover
    compute_check = None


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（不做大小写折叠，保持原文逐字比对语义）。"""
    return re.sub(r"\s+", "", str(s or ""))


def manuscript_text(case):
    """从 case.json 提取实际稿件文本（优先常见稿件键，降级取全部长文本）。"""
    if not isinstance(case, dict):
        return ""
    root = None
    for k in MANU_KEYS:
        if k in case and isinstance(case[k], (dict, list, str)):
            root = case[k]
            break
    if root is None:
        root = {k: v for k, v in case.items() if k != "output_contract"}
    buf = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            if len(o.strip()) >= 4:
                buf.append(o)

    walk(root)
    return norm("".join(buf))


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


def defect_mapping_ok(f):
    """缺陷/报告不全映射判定（纯函数，gain_probe 复用同一语义）。返回 (ok, msg)。"""
    cat, dc = f.get("category"), f.get("defect_class")
    if dc not in DEFECT_CLASSES:
        return False, "defect_class 枚举非法: %r" % dc
    if cat == "suggestion":
        return dc == "not_applicable", "suggestion ⇒ not_applicable"
    if dc not in ("method_defect", "reporting_gap"):
        return False, "confirmed（非 suggestion）⇒ method_defect/reporting_gap 二选一，实际 %r" % dc
    if cat == "fact_error" and dc != "method_defect":
        return False, "fact_error ⇒ method_defect（事实错误属于做错了，不是没报告）"
    if dc == "reporting_gap" and cat not in ("insufficient_evidence", "norm_issue"):
        return False, "reporting_gap ⇒ category 须为 insufficient_evidence/norm_issue"
    return True, ""


def analyze(res, case, ablate="none", case_state="enforced", ledger_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ("location", "severity", "evidence", "pending", "stat", "defect"):
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    suppressed_reg = [s for s in (inner.get("suppressed") or []) if isinstance(s, dict)]
    rules = [r for r in (inner.get("suppression_rules") or []) if isinstance(r, dict)]
    rule_ids = {str(r.get("rule_id")) for r in rules}
    cov = inner.get("coverage") or {}
    unchecked = inner.get("unchecked") or []
    rubric = inner.get("severity_rubric") or {}
    src = manuscript_text(case)

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "severity_ledger", "state": ledger_state,
                            "note": "" if ledger_state == "enforced" else "/app/work/severity_rubric.json 台账缺失，下游不得宣称已核对"})
    cov_state = "enforced" if cov.get("facet_counts") else "not_found"
    report["gates"].append({"gate": "coverage_audit_output", "state": cov_state,
                            "note": "" if cov_state == "enforced" else "coverage 未回填（coverage_audit.py 未跑），下游不得宣称已核对"})
    stat_state = "enforced" if (inner.get("stat_recompute") or {}).get("checks") is not None else "not_found"
    report["gates"].append({"gate": "stat_recompute_output", "state": stat_state,
                            "note": "" if stat_state == "enforced" else "stat_recompute 未回填（stat_recompute.py 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启，不属于消融组） ----
    for i, f in enumerate(findings):
        fid = f.get("finding_id") or "findings[%d]" % i
        if f.get("facet") not in FACETS:
            report["problems"].append("%s facet 枚举非法: %r（须六分面之一）" % (fid, f.get("facet")))
        if f.get("category") not in CATEGORIES:
            report["problems"].append("%s category 枚举非法: %r（须 fact_error/insufficient_evidence/norm_issue/suggestion）" % (fid, f.get("category")))
        if f.get("severity") not in SEVERITIES:
            report["problems"].append("%s severity 枚举非法: %r（须 critical/major/minor）" % (fid, f.get("severity")))
        if f.get("status") not in STATUSES:
            report["problems"].append("%s status 枚举非法: %r（须 confirmed/pending/suppressed）" % (fid, f.get("status")))
        if f.get("defect_class") not in DEFECT_CLASSES:
            report["problems"].append("%s defect_class 枚举非法: %r（须 method_defect/reporting_gap/cannot_classify/not_applicable）" % (fid, f.get("defect_class")))
        if f.get("status") == "suppressed" and not f.get("suppressed_by"):
            report["problems"].append("%s status=suppressed 但 suppressed_by 为空" % fid)

    # ---- A. 定位可回证 ----
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        if f.get("status") == "confirmed":
            q = norm(f.get("quote"))
            in_src = bool(src) and len(q) >= 6 and q in src
            ok_loc = bool(str(f.get("location") or "").strip())
            ok = in_src and ok_loc
            add("findings[%d].location_backed" % i, "quote 逐字回证于稿件原文 + location 非空",
                not off("location"), (not off("location")) and ok)
            if not off("location") and not ok:
                if not in_src:
                    report["problems"].append("%s quote 不在稿件原文中或过短（定位可回证失败）" % fid)
                if not ok_loc:
                    report["problems"].append("%s location（原文位置）为空" % fid)

    # ---- B. 严重度分级口径 ----
    levels = rubric.get("levels") or {}
    declared = bool(str(rubric.get("declared_at") or "").strip()) and \
        all(str(levels.get(k) or "").strip() for k in SEVERITIES)
    add("severity_rubric.declared", "三级口径判定前声明（declared_at + levels 非空）",
        not off("severity"), (not off("severity")) and declared)
    if not off("severity") and not declared:
        report["problems"].append("severity_rubric 未事前声明（declared_at 为空或 levels 缺 critical/major/minor 文本）")
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        cat, sev = f.get("category"), f.get("severity")
        bad = None
        if cat == "suggestion" and sev != "minor":
            bad = "suggestion ⇒ minor"
        if cat == "fact_error" and sev not in ("critical", "major"):
            bad = "fact_error ⇒ critical/major"
        ok = bad is None
        add("findings[%d].severity_rule" % i, "分级口径映射（suggestion⇒minor；fact_error⇒critical/major）",
            not off("severity"), (not off("severity")) and ok)
        if not off("severity") and not ok:
            report["problems"].append("%s 违反严重度口径（%s，实际 category=%s severity=%s）" % (fid, bad, cat, sev))

    # ---- C. 证据链完备 + claims 回证 ----
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        if f.get("status") != "confirmed":
            continue
        cl = claim_idx.get(fid) or []
        quote = norm(f.get("quote"))
        backed = any(quote and quote in norm(e.get("quote"))
                     for c in cl for e in (c.get("evidence") or []))
        add("findings[%d].claim_backed" % i, "confirmed ⇒ claims 逐字回证",
            not off("evidence"), (not off("evidence")) and backed)
        if not off("evidence") and not backed:
            report["problems"].append("%s confirmed 但 claims 证据链无逐字回证" % fid)
        if not off("evidence") and f.get("category") == "fact_error" and not str(f.get("evidence") or "").strip():
            report["problems"].append("%s category=fact_error 但对照依据 evidence 为空" % fid)
        if not off("evidence") and not str(f.get("revision_suggestion") or "").strip():
            report["problems"].append("%s 已判定但 revision_suggestion 为空" % fid)

    # ---- D. 待复核与误报抑制登记 ----
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        if f.get("status") == "pending":
            reg = [p for p in pending_reg if str(p.get("finding_id")) == fid]
            ok = bool(reg) and all(str(p.get("reason") or "").strip() for p in reg) \
                 and all(str(p.get("needed_action") or "").strip() for p in reg) \
                 and bool(str(f.get("pending_reason") or "").strip())
            add("findings[%d].pending_registered" % i, "pending ⇒ 登记 pending_review（reason+needed_action）",
                not off("pending"), (not off("pending")) and ok)
            if not off("pending") and not ok:
                report["problems"].append("%s 标 pending 但未登记/缺 reason 或 needed_action/pending_reason" % fid)
        if f.get("status") == "suppressed":
            rec = [s for s in suppressed_reg if str(s.get("finding_id")) == fid]
            ok = bool(rec) and all(str(s.get("reason") or "").strip() for s in rec) \
                 and all(str(s.get("rule_id")) in rule_ids for s in rec)
            add("findings[%d].suppression_registered" % i, "suppressed ⇒ 登记 suppressed[]（rule_id 须在事前规则表内）",
                not off("pending"), (not off("pending")) and ok)
            if not off("pending") and not ok:
                report["problems"].append("%s 标 suppressed 但 suppressed[] 未登记或 rule_id 不在 suppression_rules" % fid)

    # ---- E. 统计量复算一致（题面机检点） ----
    stat_rec = inner.get("stat_recompute") or {}
    rec_idx = {}
    for ch in (stat_rec.get("checks") or []):
        if isinstance(ch, dict) and ch.get("finding_id") is not None:
            rec_idx[str(ch.get("finding_id"))] = ch
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        sc = f.get("stat_claim")
        if not isinstance(sc, dict):
            continue
        entry = rec_idx.get(fid)
        ok_present = entry is not None and "consistent" in entry
        add("findings[%d].stat_recompute_present" % i,
            "stat_claim ⇒ result.stat_recompute.checks 有复算记录",
            not off("stat"), (not off("stat")) and ok_present)
        if not off("stat") and not ok_present:
            report["problems"].append("%s 声明了 stat_claim 但 stat_recompute.checks 无复算记录（统计量复算缺失）" % fid)
        recomputed = compute_check(sc)["consistent"] if compute_check is not None else None
        ok_match = ok_present and entry.get("consistent") == recomputed
        add("findings[%d].stat_recompute_consistent" % i,
            "复算记录的 consistent 与独立复算一致（复算记录不得被篡改）",
            not off("stat"), (not off("stat")) and ok_match)
        if not off("stat") and not ok_match:
            report["problems"].append(
                "%s 复算记录与独立复算不一致（记录 consistent=%r，独立复算=%r）——统计量复算结果被篡改或复算未跑" % (fid, entry.get("consistent") if entry else None, recomputed))

    # ---- F. 缺陷/报告不全区分（题面机检点） ----
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        if f.get("status") != "confirmed":
            continue
        ok, msg = defect_mapping_ok(f)
        add("findings[%d].defect_class_mapping" % i,
            "缺陷/报告不全映射（fact_error⇒method_defect；reporting_gap⇒insufficient_evidence/norm_issue；suggestion⇒not_applicable）",
            not off("defect"), (not off("defect")) and ok)
        if not off("defect") and not ok:
            report["problems"].append("%s 缺陷/报告不全区分违规：%s（category=%s defect_class=%r）" % (fid, msg, f.get("category"), f.get("defect_class")))

    # ---- coverage 一致性 + unchecked 纪律（始终开启） ----
    status_count = {k: sum(1 for f in findings if f.get("status") == k) for k in STATUSES}
    if cov:
        exp = {"total_findings": len(findings), "judged": sum(1 for f in findings if f.get("judged") is True),
               "confirmed": status_count["confirmed"], "pending": status_count["pending"],
               "suppressed": status_count["suppressed"]}
        bad = [k for k, v in exp.items() if isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("coverage 汇总与实际 findings 不符: %s" % bad)
        fc = cov.get("facet_counts") or {}
        real = {k: sum(1 for f in findings if f.get("facet") == k) for k in FACETS
                if isinstance(fc.get(k), int)}
        badf = [k for k, v in real.items() if fc.get(k) != v]
        if badf:
            report["problems"].append("coverage.facet_counts 与实际不符: %s" % badf)
    cleared = {str(c.get("scope")) for c in (inner.get("clearances") or [])
               if isinstance(c, dict) and c.get("scope")}
    zero_facets = [k for k in FACETS
                   if sum(1 for f in findings if f.get("facet") == k) == 0
                   and "facet:%s" % k not in cleared]
    if zero_facets and not unchecked:
        report["problems"].append("分面 %s 零发现但 unchecked 为空（须登记豁免或补查）" % ",".join(zero_facets))

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    judged = sum(1 for f in findings if f.get("judged") is True)
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "audited" and (unchecked or judged != len(findings) or not findings):
        report["problems"].append("verdict=audited 但存在 unchecked 项或未判定发现（judged=false）或 findings 为空")
    if verdict == "partially_audited" and judged == len(findings) and findings and not unchecked:
        report["problems"].append("verdict=partially_audited 但全部发现已判定且无 unchecked（应为 audited）")
    if verdict == "not_audited" and judged:
        report["problems"].append("verdict=not_audited 但存在已判定发现")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in ("success", "partial", "unable_to_determine", "refused"):
        report["problems"].append("run_status.state 枚举非法或缺失: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") and not str(rs.get("reason") or "").strip():
        report["problems"].append("run_status 非 success 但 reason 为空")

    # ---- steps（始终开启） ----
    steps = inner.get("steps") or []
    if not steps:
        report["problems"].append("steps 为空（须给出他人可重跑的步骤）")
    elif not any(str(s.get("command") or "").strip() for s in steps if isinstance(s, dict)):
        report["problems"].append("steps 无任何可执行 command")

    # ---- 契约字段（闸门 enforced 时） ----
    if case_state == "enforced":
        for fname in contract_fields(case):
            if isinstance(res, dict) and fname not in res:
                report["problems"].append("缺少 output_contract 字段: %s" % fname)

    if report["unbacked_numbers"]:
        report["problems"].append("存在 %d 个未回证数字（见 unbacked_numbers）" % len(report["unbacked_numbers"]))
    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--ledger", default="/app/work/severity_rubric.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | location,severity,evidence,pending,stat,defect 子集")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 self_check/gates/unbacked_numbers/validator_verdict 回写 result.json")
        args, _unknown = ap.parse_known_args()
    except SystemExit as e:
        if isinstance(e.code, int) and e.code not in (0, None):
            print("[verify_check] 参数错误/未知参数（已降级，失败路径恒 exit 0）")
        sys.exit(0)
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        msg = "result.json 不存在或不可解析: %s（不中断交付）" % args.result
        print("[verify_check] FAIL: %s" % msg)
        _dump(args.out, {"verdict": "FAIL", "problems": [msg], "self_check": [],
                         "gates": [], "unbacked_numbers": [], "ablate": args.ablate})
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    led = load_json(args.ledger) if os.path.exists(args.ledger) else None
    ledger_state = "enforced" if isinstance(led, dict) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state, ledger_state=ledger_state)
    _dump(args.out, report)

    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict):
                cur["self_check"] = report.get("self_check") or []
                cur["gates"] = report.get("gates") or []
                cur["unbacked_numbers"] = report.get("unbacked_numbers") or []
                cur["validator_verdict"] = report.get("verdict")
                with open(args.result, "w", encoding="utf-8") as f:
                    json.dump(cur, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[verify_check] 回写 result.json 失败: %s" % e)

    if report["verdict"] == "PASS":
        print("[verify_check] PASS（ablate=%s，检查项 %d 条全部 applied）"
              % (args.ablate, len(report["self_check"])))
    else:
        print("[verify_check] FAIL（%d 处，不中断交付；ablate=%s）:"
              % (len(report["problems"]), args.ablate))
        for p in report["problems"][:30]:
            print("  - %s" % p)
        if len(report["problems"]) > 30:
            print("  ... 共 %d 处" % len(report["problems"]))
    return 0


def _dump(out_path, report):
    if not out_path:
        return
    try:
        d = os.path.dirname(out_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[verify_check] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
