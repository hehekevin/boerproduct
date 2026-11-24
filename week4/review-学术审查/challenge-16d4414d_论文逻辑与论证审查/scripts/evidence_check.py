#!/usr/bin/env python3
"""evidence_check.py — 证据支撑核查的机械校验与覆盖计数（evidence-support-review）。

对 result.json 做三组机械校验（与题面机检点逐项对应）：
  A. 定位可回证：每条 confirmed 发现与每条主张的 quote 空白归一化后必须逐字
     出现在 case.json 实际稿件原文中，且 location 非空；引文不在原文 = 定位失据。
  B. 口径一致：evidence_scale / severity_rubric / issue_taxonomy 三口径须判定前
     声明；issue_type/severity/category/claim_strength/evidence_strength/judge
     枚举合法；suggestion⇒minor；fact_error⇒critical/major；C3 须 E3（C3 配
     E2 以下判 supported 即违规范）；judge=overstated 须有对应 confirmed
     strength_mismatch 发现。
  C. 登记一致：pending 须登记进 pending_review（reason+needed_action）；
     suppressed 须登记进 suppressed[] 且 rule_id 在事前规则表内；coverage 汇总
     与实际 findings 一致。

始终开启：枚举合法性、coverage 一致性、verdict/run_status 一致性、步骤可执行、
契约字段。所有检查项产出三元组 {item, template_value, applied, match} 回写
result.json 的 self_check / gates / validator_verdict 四键，并回写
coverage/unchecked 两键（本脚本承担计数职责）。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 evidence_check.py --result /app/output/result.json \
        --case /input/case.json [--ledger /app/work/rubrics.json] \
        [--out /app/work/evidence_check.json] [--ablate all] [--emit-into]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

DIMENSIONS = ("claim_extraction", "evidence_support", "reasoning_chain",
              "section_coherence", "severity")
ISSUE_TYPES = ("no_evidence", "insufficient_evidence", "strength_mismatch",
               "citation_unsupported", "overgeneralization", "reasoning_gap", "incoherent")
CATEGORIES = ("fact_error", "insufficient_evidence", "norm_issue", "suggestion")
SEVERITIES = ("critical", "major", "minor")
STATUSES = ("confirmed", "pending", "suppressed")
CLAIM_STRS = ("C3", "C2", "C1")
EVID_STRS = ("E3", "E2", "E1", "E0")
JUDGES = ("supported", "overstated", "understated", "pending")
MANU_KEYS = ("manuscript", "paper", "document", "full_text", "text", "body", "content")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（不做大小写折叠，保持原文逐字比对语义）。"""
    return re.sub(r"\s+", "", str(s or ""))


def en_words(s):
    """英文词数：正则统计，规避 isalpha 的汉字误计陷阱。"""
    return len(re.findall(r"[A-Za-z]+", str(s or "")))


def collect_text(o):
    buf = []

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            buf.append(x)
    walk(o)
    return "".join(buf)


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


def _declared(block, level_keys):
    levels = (block or {}).get("levels") or (block or {}).get("types") or {}
    ok_keys = all(str(levels.get(k) or "").strip() for k in level_keys)
    return bool(str((block or {}).get("declared_at") or "").strip()) and ok_keys


def compute_coverage(res, case):
    inner = (res or {}).get("result") or {}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    overview = inner.get("manuscript_overview") or {}
    sections = [s for s in (overview.get("sections") or []) if isinstance(s, dict)]
    clearances = {str(c.get("scope")) for c in (inner.get("clearances") or [])
                  if isinstance(c, dict) and c.get("scope")}
    issue_counts = {k: 0 for k in ISSUE_TYPES}
    cat_counts = {k: 0 for k in CATEGORIES}
    sev_counts = {k: 0 for k in SEVERITIES}
    status_counts = {k: 0 for k in STATUSES}
    per_section = {}
    judged = 0
    for f in findings:
        if f.get("issue_type") in issue_counts:
            issue_counts[f.get("issue_type")] += 1
        if f.get("category") in cat_counts:
            cat_counts[f.get("category")] += 1
        if f.get("severity") in sev_counts:
            sev_counts[f.get("severity")] += 1
        if f.get("status") in status_counts:
            status_counts[f.get("status")] += 1
        if f.get("judged") is True:
            judged += 1
        sid = str(f.get("section_id") or "")
        if sid:
            per_section[sid] = per_section.get(sid, 0) + 1
    sections_with = sum(1 for s in sections if per_section.get(str(s.get("section_id")), 0) > 0)

    unchecked = []
    for s in sections:
        sid = str(s.get("section_id") or "")
        if sid and per_section.get(sid, 0) == 0 and "section:%s" % sid not in clearances:
            unchecked.append({"scope": "section:%s" % sid,
                              "reason": "该章节无主张/发现且未登记豁免，须确认是否覆盖审查（本技能聚焦摘要+结果，其余章节可登记豁免）"})

    coverage = {
        "total_sections": len(sections),
        "sections_with_findings": sections_with,
        "total_findings": len(findings),
        "judged": judged,
        "confirmed": status_counts["confirmed"],
        "pending": status_counts["pending"],
        "suppressed": status_counts["suppressed"],
        "issue_type_counts": issue_counts,
        "category_counts": cat_counts,
        "severity_counts": sev_counts,
        "per_section": dict(sorted(per_section.items())),
        "manuscript_stats": {"chars": len(collect_text(case if isinstance(case, dict) else {})),
                             "en_words": en_words(collect_text(case if isinstance(case, dict) else {})),
                             "note": "字符数按全部 case 文本计；英文词数用正则统计（规避 isalpha 汉字陷阱）"},
        "note": "由 evidence_check.py 机械计数生成；unchecked 非空时 verdict 不得为 audited。",
    }
    return coverage, unchecked


def analyze(res, case, ablate="none", case_state="enforced", ledger_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ("location", "taxonomy", "strength", "pending"):
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
    claims = [c for c in (inner.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    suppressed_reg = [s for s in (inner.get("suppressed") or []) if isinstance(s, dict)]
    rules = [r for r in (inner.get("suppression_rules") or []) if isinstance(r, dict)]
    rule_ids = {str(r.get("rule_id")) for r in rules}
    cov = inner.get("coverage") or {}
    unchecked = inner.get("unchecked") or []
    taxo = inner.get("issue_taxonomy") or {}
    scale = inner.get("evidence_scale") or {}
    rubric = inner.get("severity_rubric") or {}
    src = manuscript_text(case)

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "rubrics_ledger", "state": ledger_state,
                            "note": "" if ledger_state == "enforced" else "/app/work/rubrics.json 台账缺失，下游不得宣称已核对"})
    cov_state = "enforced" if cov.get("issue_type_counts") else "not_found"
    report["gates"].append({"gate": "coverage_output", "state": cov_state,
                            "note": "" if cov_state == "enforced" else "coverage 未回填（evidence_check 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启） ----
    for i, f in enumerate(findings):
        fid = f.get("finding_id") or "findings[%d]" % i
        if f.get("dimension") not in DIMENSIONS:
            report["problems"].append("%s dimension 枚举非法或缺失: %r（须五维之一）" % (fid, f.get("dimension")))
        if f.get("issue_type") not in ISSUE_TYPES:
            report["problems"].append("%s issue_type 枚举非法: %r（须五类之一）" % (fid, f.get("issue_type")))
        if f.get("category") not in CATEGORIES:
            report["problems"].append("%s category 枚举非法: %r（须 fact_error/insufficient_evidence/norm_issue/suggestion）" % (fid, f.get("category")))
        if f.get("severity") not in SEVERITIES:
            report["problems"].append("%s severity 枚举非法: %r（须 critical/major/minor）" % (fid, f.get("severity")))
        if f.get("status") not in STATUSES:
            report["problems"].append("%s status 枚举非法: %r（须 confirmed/pending/suppressed）" % (fid, f.get("status")))
        if f.get("status") == "suppressed" and not f.get("suppressed_by"):
            report["problems"].append("%s status=suppressed 但 suppressed_by 为空" % fid)

    # ---- A. 定位可回证（findings + claims） ----
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
    for i, c in enumerate(claims):
        cid = str(c.get("claim_id") or i)
        q = norm(c.get("quote"))
        in_src = bool(src) and len(q) >= 6 and q in src
        ok_loc = bool(str(c.get("location") or "").strip())
        ok = in_src and ok_loc
        add("claims[%d].location_backed" % i, "主张 quote 逐字回证于稿件原文 + location 非空",
            not off("location"), (not off("location")) and ok)
        if not off("location") and not ok:
            if not in_src:
                report["problems"].append("主张 %s quote 不在稿件原文中或过短（定位可回证失败）" % cid)
            if not ok_loc:
                report["problems"].append("主张 %s location（原文位置）为空" % cid)

    # ---- B. 口径一致（taxonomy + severity rubric + evidence scale） ----
    taxo_decl = _declared(taxo, ISSUE_TYPES)
    add("issue_taxonomy.declared", "五类问题口径判定前声明（declared_at + types 非空）",
        not off("taxonomy"), (not off("taxonomy")) and taxo_decl)
    if not off("taxonomy") and not taxo_decl:
        report["problems"].append("issue_taxonomy 未事前声明（declared_at 为空或 types 缺五类定义）")
    rub_decl = _declared(rubric, SEVERITIES)
    add("severity_rubric.declared", "三级口径判定前声明（declared_at + levels 非空）",
        not off("taxonomy"), (not off("taxonomy")) and rub_decl)
    if not off("taxonomy") and not rub_decl:
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
            not off("taxonomy"), (not off("taxonomy")) and ok)
        if not off("taxonomy") and not ok:
            report["problems"].append("%s 违反严重度口径（%s，实际 category=%s severity=%s）" % (fid, bad, cat, sev))

    # ---- evidence scale 声明 + claims 字段 + C3须E3 ----
    scale_decl = (bool(str(scale.get("declared_at") or "").strip())
                  and all(str((scale.get("evidence_levels") or {}).get(k) or "").strip() for k in EVID_STRS)
                  and all(str((scale.get("claim_levels") or {}).get(k) or "").strip() for k in CLAIM_STRS)
                  and bool(str(scale.get("rule") or "").strip()))
    add("evidence_scale.declared", "双侧强度标尺判定前声明（declared_at + levels + rule 非空）",
        not off("strength"), (not off("strength")) and scale_decl)
    if not off("strength") and not scale_decl:
        report["problems"].append("evidence_scale 未事前声明（declared_at/levels/rule 缺失）")

    query = "（本技能聚焦摘要+结果的核心主张，逐条判断证据有无与强度是否足够）"
    for i, c in enumerate(claims):
        cid = str(c.get("claim_id") or i)
        ok_levels = str(c.get("claim_strength") or "") in CLAIM_STRS and \
            str(c.get("evidence_strength") or "") in EVID_STRS
        ok_judge = str(c.get("judge") or "") in JUDGES
        ok_basis = bool(str(c.get("judge_basis") or "").strip())
        ok = ok_levels and ok_judge and ok_basis
        add("claims[%d].fields" % i, "主张强度字段齐（claim_strength + evidence_strength + judge + judge_basis）",
            not off("strength"), (not off("strength")) and ok)
        if not off("strength") and not ok:
            report["problems"].append("主张 %s 字段违规（claim=%r evidence=%r judge=%r basis 空=%s）"
                                      % (cid, c.get("claim_strength"), c.get("evidence_strength"),
                                         c.get("judge"), not ok_basis))
        bad_map = (str(c.get("claim_strength")) == "C3"
                   and str(c.get("evidence_strength")) in ("E2", "E1", "E0")
                   and c.get("judge") == "supported")
        add("claims[%d].mapping_rule" % i, "C3 须 E3（C3 配 E2 以下不得判 supported）",
            not off("strength"), (not off("strength")) and not bad_map)
        if not off("strength") and bad_map:
            report["problems"].append("主张 %s 违反标尺规则：C3 结论配 %s 却判 supported"
                                      % (cid, c.get("evidence_strength")))

    # 每条 confirmed 主张须有对应发现举证某类问题（C3/E2、E0、引用不支持等）
    for i, c in enumerate(claims):
        cid = str(c.get("claim_id") or i)
        fid = str(c.get("finding_id") or "")
        j = c.get("judge")
        cs, es = str(c.get("claim_strength") or ""), str(c.get("evidence_strength") or "")
        e0 = es == "E0"
        should_have = (j == "overstated") or (e0 and j != "pending")
        found = [f for f in findings if str(f.get("finding_id") or "") == fid
                 and f.get("status") == "confirmed"]
        ok = (not should_have) or bool(found)
        add("claims[%d].finding_link" % i, "证据不足/结论过强的主张须有 confirmed 发现举证",
            not off("strength"), (not off("strength")) and ok)
        if not off("strength") and not ok:
            report["problems"].append("主张 %s（%s/%s）证据不足或结论过强但无 confirmed 发现举证（finding_id=%r，%s）"
                                      % (cid, cs, es, fid, query))
    # 反过来：issue_type=strength_mismatch 的 confirmed 发现须有主张登记（claim_id）
    claim_ids = {str(c.get("claim_id") or "") for c in claims}
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        if f.get("issue_type") == "strength_mismatch" and f.get("status") == "confirmed":
            ref = str(f.get("claim_id") or "")
            ok = bool(ref) and ref in claim_ids
            add("findings[%d].claim_registered" % i,
                "confirmed 的强度不匹配发现 ⇒ 有主张登记（claim_id）",
                not off("strength"), (not off("strength")) and ok)
            if not off("strength") and not ok:
                report["problems"].append("%s issue_type=strength_mismatch 但 claim_id 未指向任何主张" % fid)

    # ---- C. 登记一致（pending / suppressed / coverage） ----
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        st = f.get("status")
        if st == "pending":
            reg = [p for p in pending_reg if str(p.get("finding_id")) == fid]
            ok = bool(reg) and all(str(p.get("reason") or "").strip() for p in reg) \
                 and all(str(p.get("needed_action") or "").strip() for p in reg) \
                 and bool(str(f.get("pending_reason") or "").strip())
            add("findings[%d].pending_registered" % i, "pending ⇒ 登记 pending_review（reason+needed_action）",
                not off("pending"), (not off("pending")) and ok)
            if not off("pending") and not ok:
                report["problems"].append("%s 标 pending 但未登记/缺 reason 或 needed_action/pending_reason" % fid)
        if st == "suppressed":
            rec = [s for s in suppressed_reg if str(s.get("finding_id")) == fid]
            ok = bool(rec) and all(str(s.get("reason") or "").strip() for s in rec) \
                 and all(str(s.get("rule_id")) in rule_ids for s in rec)
            add("findings[%d].suppression_registered" % i, "suppressed ⇒ 登记 suppressed[]（rule_id 须在事前规则表内）",
                not off("pending"), (not off("pending")) and ok)
            if not off("pending") and not ok:
                report["problems"].append("%s 标 suppressed 但 suppressed[] 未登记或 rule_id 不在 suppression_rules" % fid)

    # coverage 一致性（始终开启）
    status_count = {k: sum(1 for f in findings if f.get("status") == k) for k in STATUSES}
    if cov:
        exp = {"total_findings": len(findings), "judged": sum(1 for f in findings if f.get("judged") is True),
               "confirmed": status_count["confirmed"], "pending": status_count["pending"],
               "suppressed": status_count["suppressed"]}
        bad = [k for k, v in exp.items() if isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("coverage 汇总与实际 findings 不符: %s" % bad)
        ic = cov.get("issue_type_counts") or {}
        reali = {k: sum(1 for f in findings if f.get("issue_type") == k) for k in ISSUE_TYPES
                 if isinstance(ic.get(k), int)}
        badi = [k for k, v in reali.items() if ic.get(k) != v]
        if badi:
            report["problems"].append("coverage.issue_type_counts 与实际不符: %s" % badi)

    # 五维度覆盖 + 成文报告（始终开启）
    dim_cov = inner.get("dimension_coverage") or []
    real_dim = {k: sum(1 for f in findings if f.get("dimension") == k) for k in DIMENSIONS}
    covered_dims = {c.get("dimension") for c in dim_cov if isinstance(c, dict)}
    for k in DIMENSIONS:
        has_finding = real_dim.get(k, 0) > 0
        if not has_finding and k not in covered_dims:
            report["problems"].append("维度 %s 未覆盖（既无 finding 也未在 dimension_coverage 登记）" % k)
    for c in dim_cov:
        if isinstance(c, dict) and c.get("dimension") in DIMENSIONS:
            if isinstance(c.get("count"), int) and c["count"] != real_dim.get(c["dimension"], 0):
                report["problems"].append("dimension_coverage[%s].count 与实际不符" % c["dimension"])
    review_report = inner.get("review_report") or ""
    if len(str(review_report).strip()) < 200:
        report["problems"].append("review_report 缺失或不足 200 字（须成文审查报告嵌入 result）")

    # verdict 一致性（始终开启）
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    judged = sum(1 for f in findings if f.get("judged") is True)
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "audited" and (unchecked or judged != len(findings) or not findings):
        report["problems"].append("verdict=audited 但存在 unchecked 项或未判定发现或 findings 为空")
    if verdict == "partially_audited" and judged == len(findings) and findings and not unchecked:
        report["problems"].append("verdict=partially_audited 但全部发现已判定且无 unchecked（应为 audited）")
    if verdict == "not_audited" and judged:
        report["problems"].append("verdict=not_audited 但存在已判定发现")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in ("success", "partial", "unable_to_determine", "refused"):
        report["problems"].append("run_status.state 枚举非法或缺失: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") and not str(rs.get("reason") or "").strip():
        report["problems"].append("run_status 非 success 但 reason 为空")

    # steps（始终开启）
    steps = inner.get("steps") or []
    if not steps:
        report["problems"].append("steps 为空（须给出他人可重跑的步骤）")
    elif not any(str(s.get("command") or "").strip() for s in steps if isinstance(s, dict)):
        report["problems"].append("steps 无任何可执行 command")

    # 契约字段（闸门 enforced 时）
    if case_state == "enforced":
        for fname in contract_fields(case):
            if isinstance(res, dict) and fname not in res:
                report["problems"].append("缺少 output_contract 字段: %s" % fname)

    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--ledger", default="/app/work/rubrics.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | location,taxonomy,strength,pending 子集")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 self_check/gates/validator_verdict/coverage/unchecked 回写 result.json")
        args = ap.parse_args()
    except Exception as e:
        print("[evidence_check] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        msg = "result.json 不存在或不可解析: %s（不中断交付）" % args.result
        print("[evidence_check] FAIL: %s" % msg)
        _dump(args.out, {"verdict": "FAIL", "problems": [msg], "self_check": [],
                         "gates": [], "ablate": args.ablate})
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    led = load_json(args.ledger) if os.path.exists(args.ledger) else None
    ledger_state = "enforced" if isinstance(led, dict) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state, ledger_state=ledger_state)
    _dump(args.out, report)

    coverage, unchecked = compute_coverage(res, case if isinstance(case, dict) else {})
    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict):
                cur["self_check"] = report.get("self_check") or []
                cur["gates"] = report.get("gates") or []
                cur["validator_verdict"] = report.get("verdict")
                if isinstance(cur.get("result"), dict):
                    cur["result"]["coverage"] = coverage
                    cur["result"]["unchecked"] = unchecked
                with open(args.result, "w", encoding="utf-8") as f:
                    json.dump(cur, f, ensure_ascii=False, indent=1)
            elif isinstance(cur, dict) and not isinstance(cur.get("result"), dict):
                print("[evidence_check] 回写跳过：result 非对象")
        except Exception as e:
            print("[evidence_check] 回写 result.json 失败: %s" % e)

    if report["verdict"] == "PASS":
        print("[evidence_check] PASS（ablate=%s，检查项 %d 条全部 applied）"
              % (args.ablate, len(report["self_check"])))
    else:
        print("[evidence_check] FAIL（%d 处，不中断交付；ablate=%s）:"
              % (len(report["problems"]), args.ablate))
        for p in report["problems"][:30]:
            print("  - %s" % p)
        if len(report["problems"]) > 30:
            print("  ... 共 %d 处" % len(report["problems"]))
    print("[evidence_check] findings=%d（confirmed=%d pending=%d suppressed=%d）| 章节 %d/%d 有发现 | unchecked=%d"
          % (coverage["total_findings"], coverage["confirmed"], coverage["pending"],
             coverage["suppressed"], coverage["sections_with_findings"], coverage["total_sections"],
             len(unchecked)))
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
        print("[evidence_check] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)