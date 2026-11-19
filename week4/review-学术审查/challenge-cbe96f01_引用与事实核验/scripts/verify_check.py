#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（cite-fact-verify 引用与事实核验）。

对 result.json 做六组机械校验（与题面机检点逐项对应）：
  A. 引用逐字回证：每条 confirmed 发现必须有非空 location 与逐字 quote，且
     quote（空白归一化后）必须出现在 case.json 实际稿件文本中；引文不在
     原文 = 定位失据，直接判 FAIL。
  B. 严重度分级口径：severity_rubric 三级口径必须判定前声明（declared_at），
     suggestion ⇒ minor；fact_error ⇒ critical/major；声明后不得调整。
  C. 证据链完备：每条 confirmed 发现必须在 claims[] 有 source_id 对应条目，
     quote 在 claim evidence 中逐字回证；fact_error 必须给出对照依据；
     已判定发现必须有 revision_suggestion。
  D. 待复核与误报抑制：pending 必须有 pending_reason 并登记进 pending_review
     （含 needed_action）；suppressed 必须登记进 suppressed[] 且 rule_id 存在
     于事前 suppression_rules。
  E. 引用规则：citation_state ∈ 四态枚举；facet=citation_support 须给
     citation_state；citation_state=cannot_determine ⇒ status 必须 pending
     （读不到被引文献不得冒充已核对）；cite_marker 须回证参考文献表
     （citation_fabrication 的 cite_marker 须命中 citation_audit 的
     fabricated_markers 机械候选，防止冒充编造引用）。
  F. 数值回证：numeric_claims[].value（+unit）空白归一化后须逐字出现在稿件
     原文；facet=numeric_consistency 须给 numeric_claims（数值不得凭空冒充）。
另外始终开启：枚举合法性、coverage 一致性（unchecked 空且全部判定 verdict 才
能是 audited）、verdict/run_status 一致性、steps 可执行、契约字段。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；coverage/unchecked 归 coverage_audit.py，
citation_audit 归 citation_audit.py，numeric_audit 归 numeric_audit.py，
gain_evidence/efficiency 归 gain_probe.py，其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--ledger /app/work/severity_rubric.json] [--out /app/work/verify_check.json] \
        [--ablate none|all|location,severity,evidence,pending,citation,numeric]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from citation_audit import extract_ref_keys, extract_text_markers, refs_list  # noqa: E402
    CITE_HELPERS = True
except Exception:
    CITE_HELPERS = False

FACETS = ("citation_support", "citation_fabrication", "fact_consistency",
          "numeric_consistency", "source_reliability", "evidence_locus")
CATEGORIES = ("fact_error", "insufficient_evidence", "norm_issue", "suggestion")
SEVERITIES = ("critical", "major", "minor")
STATUSES = ("confirmed", "pending", "suppressed")
CITE_STATES = ("fully_supported", "partially_supported", "unsupported", "cannot_determine")
MANU_KEYS = ("manuscript", "paper", "document", "full_text", "text", "body", "content")


# ------------------------------------------------------------------ 工具
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


# ------------------------------------------------------------------ 主分析
def analyze(res, case, ablate="none", case_state="enforced", ledger_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ("location", "severity", "evidence", "pending", "citation", "numeric"):
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

    # 引用真值：优先 result.citation_audit（机械扫描输出），缺失时独立复算
    cite_audit = inner.get("citation_audit") or {}
    if CITE_HELPERS and isinstance(case, dict):
        ind_markers = set(extract_text_markers(manuscript_body_raw(case)))
        ind_refs = set(extract_ref_keys(refs_list(case)))
        ind_fab = ind_markers - ind_refs
    else:
        ind_markers, ind_refs, ind_fab = set(), set(), set()
    ref_ids = set(cite_audit.get("reference_ids") or []) or ind_refs
    fab_markers = set(cite_audit.get("fabricated_markers") or []) or ind_fab
    cite_enforced = bool(ref_ids) or bool(fab_markers)
    num_audit = inner.get("numeric_audit") or {}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "severity_ledger", "state": ledger_state,
                            "note": "" if ledger_state == "enforced" else "/app/work/severity_rubric.json 台账缺失，下游不得宣称已核对"})
    cov_state = "enforced" if cov.get("facet_counts") else "not_found"
    report["gates"].append({"gate": "coverage_audit_output", "state": cov_state,
                            "note": "" if cov_state == "enforced" else "coverage 未回填（coverage_audit.py 未跑），下游不得宣称已核对"})
    cite_state = "enforced" if ("fabricated_markers" in cite_audit or cite_enforced) else "not_found"
    report["gates"].append({"gate": "citation_audit_output", "state": cite_state,
                            "note": "" if cite_state == "enforced" else "citation_audit 未回填，编造引用识别退化为独立复算，下游谨慎宣称已核对"})
    num_state = "enforced" if num_audit.get("inventory_per_section") else "not_found"
    report["gates"].append({"gate": "numeric_audit_output", "state": num_state,
                            "note": "" if num_state == "enforced" else "numeric_audit 未回填，数值复算底账缺失，下游不得宣称已复算"})

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
        if f.get("status") == "suppressed" and not f.get("suppressed_by"):
            report["problems"].append("%s status=suppressed 但 suppressed_by 为空" % fid)

    # ---- A. 引用逐字回证（定位可回证） ----
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
                    report["problems"].append("%s quote 不在稿件原文中或过短（引用逐字回证失败）" % fid)
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

    # ---- E. 引用规则（四态/不可判定⇒pending/标记回证参考文献表） ----
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        viols = []
        cs = f.get("citation_state")
        if cs is not None and str(cs).strip() and cs not in CITE_STATES:
            viols.append("citation_state 枚举非法: %r（须四态之一）" % cs)
        if f.get("facet") == "citation_support" and not (cs and str(cs).strip()):
            viols.append("facet=citation_support 但 citation_state 缺失（须四态之一）")
        if cs == "cannot_determine" and f.get("status") != "pending":
            viols.append("citation_state=cannot_determine 但 status=%r（读不到被引文献必须 pending，不得冒充已核对）" % f.get("status"))
        m = f.get("cite_marker")
        if m and str(m).strip():
            m = str(m).strip()
            if f.get("facet") == "citation_fabrication":
                if cite_enforced and m not in fab_markers:
                    viols.append("cite_marker %s 不在编造引用机械候选中（冒充编造引用）" % m)
                if f.get("status") == "confirmed" and cite_enforced and m in ref_ids:
                    viols.append("cite_marker %s 实际存在于参考文献表（编造引用判定与扫描结果矛盾）" % m)
            elif f.get("status") == "confirmed" and cite_enforced and ref_ids and m not in ref_ids:
                viols.append("cite_marker %s 不在参考文献表（confirmed 引用须回证文献表）" % m)
        ok = not viols
        add("findings[%d].citation_rules" % i,
            "引用规则（四态枚举/不可判定⇒pending/cite_marker 回证参考文献表或编造候选）",
            not off("citation"), (not off("citation")) and ok)
        if not off("citation"):
            for v in viols:
                report["problems"].append("%s %s" % (fid, v))

    # ---- F. 数值回证 ----
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        viols = []
        nc = f.get("numeric_claims") or []
        if f.get("facet") == "numeric_consistency" and not nc:
            viols.append("facet=numeric_consistency 但 numeric_claims 为空（数值证据不得凭空）")
        for j, c in enumerate(nc if isinstance(nc, list) else []):
            if not isinstance(c, dict):
                continue
            v = norm(str(c.get("value") or "") + str(c.get("unit") or ""))
            if not v:
                viols.append("numeric_claims[%d] value 为空" % j)
            elif not src or v not in src:
                viols.append("numeric_claims[%d] 数值 '%s' 不在稿件原文（数值回证失败）" % (j, v))
        ok = not viols
        add("findings[%d].numeric_backed" % i, "numeric_claims 逐字回证于稿件原文",
            not off("numeric"), (not off("numeric")) and ok)
        if not off("numeric"):
            for v in viols:
                report["problems"].append("%s %s" % (fid, v))

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
    zero_facets = [k for k in FACETS if sum(1 for f in findings if f.get("facet") == k) == 0]
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


def manuscript_body_raw(case):
    """稿件正文原始文本（剔除参考文献表键），供标记独立复算。"""
    if not isinstance(case, dict):
        return ""
    root = None
    for k in MANU_KEYS:
        if isinstance(case.get(k), (dict, list, str)):
            root = case[k]
            break
    if root is None:
        root = {k: v for k, v in case.items() if k != "output_contract"}
    if isinstance(root, dict):
        root = {k: v for k, v in root.items() if k not in ("references", "refs", "bibliography")}
    buf = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            buf.append(o)

    walk(root)
    return "".join(buf)


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--ledger", default="/app/work/severity_rubric.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | location,severity,evidence,pending,citation,numeric 子集")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 self_check/gates/unbacked_numbers/validator_verdict 回写 result.json")
        args = ap.parse_args()
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
    report["gates"].append({"gate": "coverage_audit_output",
                            "state": "enforced" if ((res.get("result") or {}).get("coverage") or {}).get("facet_counts")
                            else "not_found",
                            "note": "" if ((res.get("result") or {}).get("coverage") or {}).get("facet_counts")
                            else "coverage_audit.py 未回写 coverage，下游不得宣称已核对"})
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
