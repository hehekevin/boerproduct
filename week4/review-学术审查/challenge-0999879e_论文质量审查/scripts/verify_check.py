#!/usr/bin/env python3
"""verify_check.py — 业务校验器（paper-fact-citation-audit 两分面审查）。

对 result.json 做机械校验并兼任结构守卫（合并 schema 校验到本脚本，脚本数
砍到 3）：
  A. 定位可回证：每条 confirmed 发现必须有非空 location 与逐字 quote，且
     quote（空白归一化后，长度≥6）必须出现在 case.json 实际稿件文本中。
  B. 严重度口径：severity_rubric 三级口径必须判定前声明；suggestion ⇒ minor；
     fact_error ⇒ critical/major。
  C. 证据链：每条 confirmed 发现必须在 claims[] 有 source_id 对应且 evidence
     逐字回证 quote；fact_error/citation_mismatch 必须有对照依据 evidence；
     已判定发现必须有 revision_suggestion。
  D. 两分面覆盖：findings 非空；任一面零发现须在 unchecked 登记原因；coverage
     计数与实际一致。
  E. 契约完整性（结构守卫）：顶层含 output_contract 全部字段 + 业务必填键；
     每条 finding 子字段齐备。
始终开启：枚举合法性、verdict/run_status 一致性、steps 可执行、闸门 case_contract。
回写顶层 self_check / gates / unbacked_numbers / validator_verdict。**键归属**：
本脚本只写这四个顶层键；gain_evidence/efficiency 归 gain_probe.py。

退出码恒为 0（结论记在报告 verdict 与 stdout）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--out /app/work/verify_check.json] [--ablate all] [--emit-into]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

FACETS = ("fact_check", "citation_support", "method_design", "stat_reporting", "argument_chain", "integrity_norms")
CATEGORIES = ("fact_error", "citation_mismatch", "insufficient_evidence", "norm_issue", "suggestion")
SEVERITIES = ("critical", "major", "minor")
STATUSES = ("confirmed", "pending")
RUN_STATES = ("success", "partial", "unable_to_determine", "refused", None)
MANU_KEYS = ("manuscript", "paper", "document", "full_text", "text", "body", "content")

RESULT_REQUIRED = [
    "material_gaps", "environment", "manuscript_overview", "severity_rubric",
    "findings", "facet_coverage", "review_report", "clearances", "steps",
    "run_status", "verdict", "verdict_basis",
]
FINDING_REQUIRED = ["finding_id", "source_ref", "section_id", "location", "facet",
                    "category", "severity", "quote", "evidence", "revision_suggestion",
                    "status", "pending_reason", "judged"]
TOP_REQUIRED = ["case_id", "status", "result", "claims", "uncertainties", "changelog"]


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def manuscript_text(case):
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


def analyze(res, case, ablate="none", case_state="enforced"):
    report = {"verdict": "PASS", "problems": [], "self_check": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ("location", "severity", "evidence", "coverage"):
        if off(g):
            report["disabled_checks"].append(g)

    # ---- E. 结构守卫（契约字段，始终开启） ----
    if not isinstance(res, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        return report
    if not res.get("case_id"):
        report["problems"].append("缺少 case_id")
    for fname in TOP_REQUIRED:
        if fname not in res:
            report["problems"].append("缺少顶层契约字段: %s" % fname)
    if case_state == "enforced":
        for fname in contract_fields(case):
            if fname not in res:
                report["problems"].append("缺少 output_contract 字段: %s" % fname)

    inner = res.get("result")
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        return report
    for fname in RESULT_REQUIRED:
        if fname not in inner:
            report["problems"].append("缺少业务字段: result.%s" % fname)

    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    cov = inner.get("facet_coverage") or []
    unchecked = inner.get("unchecked") or []
    rubric = inner.get("severity_rubric") or {}
    review_report = inner.get("review_report") or ""
    src = manuscript_text(case)

    # ---- 闸门 ----
    report["gates"] = [{"gate": "case_contract", "state": case_state,
                        "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"}]

    # ---- 枚举合法性 + 子字段齐备（始终开启） ----
    for i, f in enumerate(findings):
        fid = f.get("finding_id") or "findings[%d]" % i
        if f.get("facet") not in FACETS:
            report["problems"].append("%s facet 枚举非法: %r（须 fact_check/citation_support）" % (fid, f.get("facet")))
        if f.get("category") not in CATEGORIES:
            report["problems"].append("%s category 枚举非法: %r" % (fid, f.get("category")))
        if f.get("severity") not in SEVERITIES:
            report["problems"].append("%s severity 枚举非法: %r" % (fid, f.get("severity")))
        if f.get("status") not in STATUSES:
            report["problems"].append("%s status 枚举非法: %r（须 confirmed/pending）" % (fid, f.get("status")))
        for sf in FINDING_REQUIRED:
            if sf not in f:
                report["problems"].append("%s 缺少子字段: %s" % (fid, sf))

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

    # ---- B. 严重度口径 ----
    levels = rubric.get("levels") or {}
    declared = bool(str(rubric.get("declared_at") or "").strip()) and \
        all(str(levels.get(k) or "").strip() for k in SEVERITIES)
    add("severity_rubric.declared", "三级口径判定前声明",
        not off("severity"), (not off("severity")) and declared)
    if not off("severity") and not declared:
        report["problems"].append("severity_rubric 未事前声明")
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        cat, sev = f.get("category"), f.get("severity")
        bad = None
        if cat == "suggestion" and sev != "minor":
            bad = "suggestion ⇒ minor"
        if cat == "fact_error" and sev not in ("critical", "major"):
            bad = "fact_error ⇒ critical/major"
        ok = bad is None
        add("findings[%d].severity_rule" % i, "分级口径映射",
            not off("severity"), (not off("severity")) and ok)
        if not off("severity") and not ok:
            report["problems"].append("%s 违反严重度口径（%s）" % (fid, bad))

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
        if not off("evidence") and f.get("category") in ("fact_error", "citation_mismatch", "norm_issue") \
                and not str(f.get("evidence") or "").strip():
            report["problems"].append("%s 缺对照依据 evidence" % fid)
        if not off("evidence") and not str(f.get("revision_suggestion") or "").strip():
            report["problems"].append("%s 已判定但 revision_suggestion 为空" % fid)

    # ---- D. 六分面覆盖 + 成文报告（始终开启） ----
    real_fc = {k: sum(1 for f in findings if f.get("facet") == k) for k in FACETS}
    covered_facets = set()
    for c in cov:
        if isinstance(c, dict) and c.get("facet") in FACETS:
            covered_facets.add(c["facet"])
    # 每个分面要么有 finding，要么在 facet_coverage 里登记 checked_no_issue
    for k in FACETS:
        has_finding = real_fc.get(k, 0) > 0
        if not has_finding and k not in covered_facets:
            report["problems"].append("分面 %s 未覆盖（既无 finding 也未在 facet_coverage 登记）" % k)
    # 成文报告
    if len(str(review_report).strip()) < 200:
        report["problems"].append("review_report 缺失或不足 200 字（须成文审查报告嵌入 result）")
    # 计数一致性
    for c in cov:
        if isinstance(c, dict) and c.get("facet") in FACETS:
            if isinstance(c.get("count"), int) and c["count"] != real_fc.get(c["facet"], 0):
                report["problems"].append("facet_coverage[%s].count 与实际不符" % c["facet"])

    # ---- verdict/run_status 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    judged = sum(1 for f in findings if f.get("judged") is True)
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "audited" and (unchecked or judged != len(findings) or not findings):
        report["problems"].append("verdict=audited 但与 findings/unchecked 进度矛盾")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in RUN_STATES:
        report["problems"].append("run_status.state 枚举非法: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") and not str(rs.get("reason") or "").strip():
        report["problems"].append("run_status 非 success 但 reason 为空")

    # ---- steps（始终开启） ----
    steps = inner.get("steps") or []
    if not steps:
        report["problems"].append("steps 为空")
    elif not any(str(s.get("command") or "").strip() for s in steps if isinstance(s, dict)):
        report["problems"].append("steps 无任何可执行 command")

    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | location,severity,evidence,coverage 子集")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 self_check/gates/unbacked_numbers/validator_verdict 回写 result.json")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        _dump(args.out, {"verdict": "FAIL", "problems": ["result.json 不存在或不可解析: %s" % args.result],
                         "self_check": [], "gates": [], "unbacked_numbers": [], "ablate": args.ablate})
        print("[verify_check] FAIL: result.json 不存在或不可解析（不中断交付）: %s" % args.result)
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"

    report = analyze(res, case if isinstance(case, dict) else {}, ablate=args.ablate, case_state=case_state)
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
        print("[verify_check] PASS（ablate=%s，检查项 %d 条）" % (args.ablate, len(report["self_check"])))
    else:
        print("[verify_check] FAIL（%d 处，不中断交付；ablate=%s）:" % (len(report["problems"]), args.ablate))
        for p in report["problems"][:30]:
            print("  - %s" % p)
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