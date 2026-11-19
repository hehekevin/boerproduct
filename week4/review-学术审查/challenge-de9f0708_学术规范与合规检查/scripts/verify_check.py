#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（paper-compliance-audit 学术规范与合规检查）。

对 result.json 做五组机械校验（与题面机检点逐项对应）：
  A. 定位可回证：每条 confirmed 发现必须有非空 location（原文位置）与逐字
     quote，且 quote（空白归一化后）必须出现在 case.json 实际稿件文本中；
     引文不在原文 = 定位失据，直接判 FAIL。
  B. 三类区分与严重度口径一致：compliance_rubric 必须判定前声明（declared_at
     非空、categories 三类与 severity_levels 三级文本齐全）；category 只能取
     三类之一；机械映射 substantive_issue⇒critical/major、norm_missing⇒major/
     minor、norm_violation⇒major/minor——口径声明后不得调整。
  C. 格式规则依据绑定 + 声明机检一致性：norm_missing/norm_violation 发现必须
     引用事前声明 format_rules 中的 rule_id（判"不合规"必须有可核对依据）；
     substantive_issue 必须给出对照依据 evidence；declaration_audit 中
     detected=false 的必备声明必须有一条 norm_missing 发现或豁免登记。
  D. 证据链完备：每条 confirmed 发现必须在 claims[] 有 source_id 对应条目，
     quote 在 claim evidence 中逐字回证；已判定发现必须有 revision_suggestion。
  E. 待复核与误报抑制：pending 必须有 pending_reason 并登记进 pending_review
     （含 needed_action）；suppressed 必须登记进 suppressed[] 且 rule_id 存在
     于 suppression_rules（误报抑制规则必须事前声明）。
另外始终开启：枚举合法性、coverage 一致性（八分面覆盖与 unchecked 空则
verdict 才能是 audited）、verdict/run_status 一致性、steps 可执行、契约字段。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；declaration_audit/coverage/unchecked 归 decl_audit.py，
gain_evidence/efficiency 归 gain_probe.py，其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--ledger /app/work/compliance_rubric.json] [--out /app/work/verify_check.json] [--ablate all]
    --ablate: none | all | location,rubric,rules,evidence,pending 子集
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

FACETS = ("data_availability", "ethics", "conflict_of_interest", "author_contributions",
          "funding", "copyright_license", "reference_format", "duplicate_publication")
CATEGORIES = ("norm_missing", "norm_violation", "substantive_issue")
SEVERITIES = ("critical", "major", "minor")
STATUSES = ("confirmed", "pending", "suppressed")
MANU_KEYS = ("manuscript", "paper", "document", "full_text", "text", "body", "content")
NORM_CATEGORIES = ("norm_missing", "norm_violation")


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


def category_mapping_bad(cat, sev):
    """三类区分 × 严重度机械映射。返回违规描述或 None。"""
    if cat == "substantive_issue" and sev not in ("critical", "major"):
        return "substantive_issue ⇒ critical/major"
    if cat in ("norm_missing", "norm_violation") and sev not in ("major", "minor"):
        return "%s ⇒ major/minor" % cat
    return None


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
    for g in ("location", "rubric", "rules", "evidence", "pending"):
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
    rules = [r for r in (inner.get("format_rules") or []) if isinstance(r, dict)]
    rule_ids = {str(r.get("rule_id")) for r in rules}
    fp_rules = [r for r in (inner.get("suppression_rules") or []) if isinstance(r, dict)]
    fp_ids = {str(r.get("rule_id")) for r in fp_rules}
    cov = inner.get("coverage") or {}
    unchecked = inner.get("unchecked") or []
    rubric = inner.get("compliance_rubric") or {}
    decl_audit = inner.get("declaration_audit") or {}
    src = manuscript_text(case)

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "rubric_ledger", "state": ledger_state,
                            "note": "" if ledger_state == "enforced" else "/app/work/compliance_rubric.json 台账缺失，下游不得宣称已核对"})
    cov_state = "enforced" if cov.get("facet_counts") else "not_found"
    report["gates"].append({"gate": "decl_audit_output", "state": "enforced" if decl_audit.get("items") else "not_found",
                            "note": "" if decl_audit.get("items") else "decl_audit.py 未回写声明机检，下游不得宣称已核对"})
    report["gates"].append({"gate": "coverage_audit_output", "state": cov_state,
                            "note": "" if cov_state == "enforced" else "coverage 未回填（decl_audit.py 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启，不属于消融组） ----
    for i, f in enumerate(findings):
        fid = f.get("finding_id") or "findings[%d]" % i
        if f.get("facet") not in FACETS:
            report["problems"].append("%s facet 枚举非法: %r（须八分面之一）" % (fid, f.get("facet")))
        if f.get("category") not in CATEGORIES:
            report["problems"].append("%s category 枚举非法: %r（须 norm_missing/norm_violation/substantive_issue）" % (fid, f.get("category")))
        if f.get("severity") not in SEVERITIES:
            report["problems"].append("%s severity 枚举非法: %r（须 critical/major/minor）" % (fid, f.get("severity")))
        if f.get("status") not in STATUSES:
            report["problems"].append("%s status 枚举非法: %r（须 confirmed/pending/suppressed）" % (fid, f.get("status")))
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

    # ---- B. 三类区分与严重度口径一致 ----
    cats = rubric.get("categories") or {}
    levels = rubric.get("severity_levels") or {}
    declared = bool(str(rubric.get("declared_at") or "").strip()) \
        and all(str(cats.get(k) or "").strip() for k in CATEGORIES) \
        and all(str(levels.get(k) or "").strip() for k in SEVERITIES)
    add("compliance_rubric.declared", "三类区分与三级严重度口径判定前声明（declared_at + categories + levels 非空）",
        not off("rubric"), (not off("rubric")) and declared)
    if not off("rubric") and not declared:
        report["problems"].append("compliance_rubric 未事前声明（declared_at 为空或 categories 三类/levels 三级文本缺失）")
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        bad = category_mapping_bad(f.get("category"), f.get("severity"))
        ok = bad is None
        add("findings[%d].category_mapping" % i, "三类×严重度映射（substantive⇒critical/major；norm_missing/norm_violation⇒major/minor）",
            not off("rubric"), (not off("rubric")) and ok)
        if not off("rubric") and not ok:
            report["problems"].append("%s 违反三类区分口径映射（%s，实际 category=%s severity=%s）" % (fid, bad, f.get("category"), f.get("severity")))

    # ---- C. 格式规则依据绑定 + 声明机检一致性 ----
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        if f.get("category") in NORM_CATEGORIES:
            ok = str(f.get("rule_id") or "") in rule_ids
            add("findings[%d].rule_bound" % i, "norm_missing/norm_violation ⇒ rule_id 须在事前声明的 format_rules 内",
                not off("rules"), (not off("rules")) and ok)
            if not off("rules") and not ok:
                report["problems"].append("%s category=%s 但 rule_id 缺失或不在事前声明 format_rules 内（依据绑定失败）"
                                          % (fid, f.get("category")))
        if f.get("category") == "substantive_issue":
            ok = bool(str(f.get("evidence") or "").strip())
            add("findings[%d].substantive_evidence" % i, "substantive_issue ⇒ 对照依据 evidence 非空",
                not off("rules"), (not off("rules")) and ok)
            if not off("rules") and not ok:
                report["problems"].append("%s category=substantive_issue 但对照依据 evidence 为空" % fid)

    decl_items = [d for d in (decl_audit.get("items") or []) if isinstance(d, dict)]
    decl_ok_all = True
    decl_problems = []
    for d in decl_items:
        did = str(d.get("decl_id") or "")
        if d.get("detected") is False:
            covered = any(f.get("facet") == did and f.get("category") == "norm_missing"
                          for f in findings) \
                or ("decl:%s" % did in {str(c.get("scope")) for c in (inner.get("clearances") or [])
                                        if isinstance(c, dict)}) \
                or any(did in str(g) for g in (inner.get("material_gaps") or []))
            if not covered:
                decl_ok_all = False
                decl_problems.append("机检判缺失的声明 %s 无对应 norm_missing 发现，也无 clearances/material_gaps 豁免登记" % did)
    add("declaration_audit.consistency", "机检 detected=false 的必备声明 ⇒ norm_missing 发现或豁免登记",
        not off("rules"), (not off("rules")) and decl_ok_all)
    if not off("rules"):
        report["problems"].extend(decl_problems)

    # ---- D. 证据链完备 + claims 回证 ----
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
        if not off("evidence") and not str(f.get("revision_suggestion") or "").strip():
            report["problems"].append("%s 已判定但 revision_suggestion 为空" % fid)

    # ---- E. 待复核与误报抑制登记 ----
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
                 and all(str(s.get("rule_id")) in fp_ids for s in rec)
            add("findings[%d].suppression_registered" % i, "suppressed ⇒ 登记 suppressed[]（rule_id 须在事前规则表内）",
                not off("pending"), (not off("pending")) and ok)
            if not off("pending") and not ok:
                report["problems"].append("%s 标 suppressed 但 suppressed[] 未登记或 rule_id 不在 suppression_rules" % fid)

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
    cleared_scopes = {str(c.get("scope")) for c in (inner.get("clearances") or [])
                      if isinstance(c, dict) and c.get("scope")}
    zero_facets = [k for k in FACETS if sum(1 for f in findings if f.get("facet") == k) == 0]
    unexcused = [k for k in zero_facets
                 if "facet:%s" % k not in cleared_scopes
                 and not any(str(u.get("scope")) == "facet:%s" % k for u in unchecked
                             if isinstance(u, dict))]
    if unexcused:
        report["problems"].append("分面 %s 零发现且未登记豁免（clearances/unchecked），须补查或登记已查清"
                                  % ",".join(unexcused))

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


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--ledger", default="/app/work/compliance_rubric.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | location,rubric,rules,evidence,pending 子集")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 self_check/gates/unbacked_numbers/validator_verdict 回写 result.json")
        args = ap.parse_args()
    except SystemExit as e:
        print("[verify_check] 参数解析失败（argparse 退出码 %s，已降级为 exit 0）" % e)
        return 0
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
    inner = res.get("result") or {}
    report["gates"].append({"gate": "decl_audit_output",
                            "state": "enforced" if (inner.get("declaration_audit") or {}).get("items") else "not_found",
                            "note": "" if (inner.get("declaration_audit") or {}).get("items")
                            else "decl_audit.py 未回写声明机检，下游不得宣称已核对"})
    report["gates"].append({"gate": "coverage_audit_output",
                            "state": "enforced" if (inner.get("coverage") or {}).get("facet_counts") else "not_found",
                            "note": "" if (inner.get("coverage") or {}).get("facet_counts")
                            else "decl_audit.py 未回写 coverage，下游不得宣称已核对"})
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
