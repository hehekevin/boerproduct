#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（argchain-review 论文逻辑与论证审查）。

对 result.json 做五组机械校验（与题面机检点逐项对应）：
  A. 定位可回证（location）：每条 confirmed 发现与每个链节点必须有非空
     location 与逐字 quote，且 quote（空白归一化后）必须出现在 case.json
     实际稿件文本中；引文不在原文 = 定位失据，直接判 FAIL。
  B. 分类口径一致（taxonomy）：issue_taxonomy 六类口径必须判定前声明
     （declared_at + types 非空）；issue_type 必在六类枚举内；severity_rubric
     三级口径声明；suggestion ⇒ minor；fact_error ⇒ critical/major。
  C. 强度匹配登记（strength）：strength_scale 必须判定前声明；核心结论须有
     strength_matches 登记；verdict=overstated 必须有对应发现；claim_strength
     =C3 而 evidence_strength 低于 E3 且 verdict=supported 判违规。
  D. 论证链节点完备（chain）：每条链必须有 premise 与 conclusion 节点；
     finding.chain_ref 若给出必须指向存在的节点。
  E. 待复核与误报抑制（pending）：pending 必须有 pending_reason 并登记进
     pending_review（含 needed_action）；suppressed 必须登记进 suppressed[]
     且 rule_id 存在于 suppression_rules（误报抑制规则必须事前声明）。
另外始终开启：枚举合法性、coverage 一致性、verdict/run_status 一致性、
steps 可执行、契约字段。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；coverage/unchecked/chain_audit 归 chain_audit.py，
gain_evidence/efficiency 归 gain_probe.py，其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--ledger /app/work/rubrics.json] [--out /app/work/verify_check.json] [--ablate all]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

FACETS = ("argument_chain", "strength_match", "rebuttal_coverage", "cross_section",
          "fact_check", "integrity_norms")
ISSUE_TYPES = ("broken_chain", "circular_reasoning", "correlation_causation",
               "over_extrapolation", "strength_mismatch", "missing_rebuttal")
CATEGORIES = ("fact_error", "insufficient_evidence", "norm_issue", "suggestion")
SEVERITIES = ("critical", "major", "minor")
STATUSES = ("confirmed", "pending", "suppressed")
ROLES = ("hypothesis", "premise", "reasoning", "conclusion")
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


def _declared(block, level_keys):
    levels = (block or {}).get("levels") or (block or {}).get("types") or {}
    ok_keys = all(str(levels.get(k) or "").strip() for k in level_keys)
    return bool(str((block or {}).get("declared_at") or "").strip()) and ok_keys


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
    for g in ("location", "taxonomy", "strength", "chain", "pending"):
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
    chains = [c for c in (inner.get("argument_chains") or []) if isinstance(c, dict)]
    matches = [m for m in (inner.get("strength_matches") or []) if isinstance(m, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    suppressed_reg = [s for s in (inner.get("suppressed") or []) if isinstance(s, dict)]
    rules = [r for r in (inner.get("suppression_rules") or []) if isinstance(r, dict)]
    rule_ids = {str(r.get("rule_id")) for r in rules}
    cov = inner.get("coverage") or {}
    unchecked = inner.get("unchecked") or []
    taxo = inner.get("issue_taxonomy") or {}
    scale = inner.get("strength_scale") or {}
    rubric = inner.get("severity_rubric") or {}
    src = manuscript_text(case)

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "rubrics_ledger", "state": ledger_state,
                            "note": "" if ledger_state == "enforced" else "/app/work/rubrics.json 台账缺失，下游不得宣称已核对"})
    cov_state = "enforced" if cov.get("facet_counts") else "not_found"
    report["gates"].append({"gate": "chain_audit_output", "state": cov_state,
                            "note": "" if cov_state == "enforced" else "coverage 未回填（chain_audit.py 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启，不属于消融组） ----
    for i, f in enumerate(findings):
        fid = f.get("finding_id") or "findings[%d]" % i
        if f.get("facet") not in FACETS:
            report["problems"].append("%s facet 枚举非法: %r（须六项之一）" % (fid, f.get("facet")))
        if f.get("issue_type") not in ISSUE_TYPES:
            report["problems"].append("%s issue_type 枚举非法: %r（须六类之一）" % (fid, f.get("issue_type")))
        if f.get("category") not in CATEGORIES:
            report["problems"].append("%s category 枚举非法: %r（须 fact_error/insufficient_evidence/norm_issue/suggestion）" % (fid, f.get("category")))
        if f.get("severity") not in SEVERITIES:
            report["problems"].append("%s severity 枚举非法: %r（须 critical/major/minor）" % (fid, f.get("severity")))
        if f.get("status") not in STATUSES:
            report["problems"].append("%s status 枚举非法: %r（须 confirmed/pending/suppressed）" % (fid, f.get("status")))
        if f.get("status") == "suppressed" and not f.get("suppressed_by"):
            report["problems"].append("%s status=suppressed 但 suppressed_by 为空" % fid)

    # ---- A. 定位可回证（findings + 链节点） ----
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
    for ci, ch in enumerate(chains):
        for ni, node in enumerate(ch.get("nodes") or []):
            if not isinstance(node, dict):
                continue
            q = norm(node.get("quote"))
            in_src = bool(src) and len(q) >= 6 and q in src
            ok_loc = bool(str(node.get("location") or "").strip())
            ok = in_src and ok_loc
            add("chains[%d].nodes[%d].location_backed" % (ci, ni),
                "链节点 quote 逐字回证于稿件原文 + location 非空",
                not off("location"), (not off("location")) and ok)
            if not off("location") and not ok:
                report["problems"].append("chains[%d].%s 节点引文不可回证或 location 为空"
                                          % (ci, node.get("node_id") or ni))

    # ---- B. 分类口径一致（taxonomy + severity rubric） ----
    taxo_decl = _declared(taxo, ISSUE_TYPES)
    add("issue_taxonomy.declared", "六类问题口径判定前声明（declared_at + types 非空）",
        not off("taxonomy"), (not off("taxonomy")) and taxo_decl)
    if not off("taxonomy") and not taxo_decl:
        report["problems"].append("issue_taxonomy 未事前声明（declared_at 为空或 types 缺六类定义）")
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
        # 分类口径一致：issue_type 与 facet 交叉校验（strength_mismatch 须落在强度分面）
        it, fc = f.get("issue_type"), f.get("facet")
        xok = not (it == "strength_mismatch" and fc not in ("strength_match", "fact_check"))
        add("findings[%d].taxonomy_cross" % i, "issue_type 与 facet 交叉一致（strength_mismatch 须落在强度分面）",
            not off("taxonomy"), (not off("taxonomy")) and xok)
        if not off("taxonomy") and not xok:
            report["problems"].append("%s 分类口径交叉违规：issue_type=strength_mismatch 但 facet=%s" % (fid, fc))

    # ---- C. 强度匹配登记 ----
    scale_decl = (bool(str(scale.get("declared_at") or "").strip())
                  and all(str((scale.get("evidence_levels") or {}).get(k) or "").strip() for k in ("E3", "E2", "E1", "E0"))
                  and all(str((scale.get("claim_levels") or {}).get(k) or "").strip() for k in ("C3", "C2", "C1"))
                  and bool(str(scale.get("rule") or "").strip()))
    add("strength_scale.declared", "双侧强度标尺判定前声明（declared_at + levels + rule 非空）",
        not off("strength"), (not off("strength")) and scale_decl)
    if not off("strength") and not scale_decl:
        report["problems"].append("strength_scale 未事前声明（declared_at/levels/rule 缺失）")
    matched_fids = {str(m.get("finding_id")) for m in matches if m.get("finding_id")}
    valid_verdicts = ("supported", "overstated", "understated", "pending")
    for i, m in enumerate(matches):
        mid = str(m.get("match_id") or i)
        ok_verdict = m.get("verdict") in valid_verdicts
        ok_levels = str(m.get("claim_strength") or "") in ("C3", "C2", "C1") and \
            str(m.get("evidence_strength") or "") in ("E3", "E2", "E1", "E0")
        ok_basis = bool(str(m.get("basis") or "").strip())
        ok = ok_verdict and ok_levels and ok_basis
        add("strength_matches[%d].fields" % i, "强度判定字段齐（verdict 枚举 + 双侧等级 + basis）",
            not off("strength"), (not off("strength")) and ok)
        if not off("strength") and not ok:
            report["problems"].append("强度登记 %s 字段违规（verdict=%r claim=%r evidence=%r basis 空=%s）"
                                      % (mid, m.get("verdict"), m.get("claim_strength"),
                                         m.get("evidence_strength"), not ok_basis))
        # C3 结论配 E3 以下证据却判 supported ⇒ 口径违规
        bad_map = (str(m.get("claim_strength")) == "C3"
                   and str(m.get("evidence_strength")) in ("E2", "E1", "E0")
                   and m.get("verdict") == "supported")
        add("strength_matches[%d].mapping_rule" % i, "C3 须 E3（C3 配 E2 以下不得判 supported）",
            not off("strength"), (not off("strength")) and not bad_map)
        if not off("strength") and bad_map:
            report["problems"].append("强度登记 %s 违反标尺规则：C3 结论配 %s 却判 supported"
                                      % (mid, m.get("evidence_strength")))
    overstated_fids = {str(m.get("finding_id")) for m in matches if m.get("verdict") == "overstated"}
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        if f.get("issue_type") == "strength_mismatch" and f.get("status") == "confirmed":
            ok = fid in matched_fids
            add("findings[%d].strength_registered" % i,
                "confirmed 的强度不匹配发现 ⇒ strength_matches 登记", not off("strength"),
                (not off("strength")) and ok)
            if not off("strength") and not ok:
                report["problems"].append("%s issue_type=strength_mismatch 但 strength_matches 未登记" % fid)
        if fid in overstated_fids and f.get("status") != "confirmed":
            report["problems"].append("强度登记 verdict=overstated 指向 %s，但该发现非 confirmed" % fid)
    # 核心结论须有强度登记（以结论句字面线索机械识别：建议/表明/证明/导致/表明因果的表述）
    concl_terms = ("建议", "表明", "证明", "导致", "提升", "改善", "提高", "支持", "证实")
    for i, f in enumerate(findings):
        if f.get("facet") != "strength_match" or f.get("status") != "confirmed":
            continue
        text = str(f.get("quote") or "")
        if any(t in text for t in concl_terms) and str(f.get("finding_id") or "") not in matched_fids:
            report["problems"].append("%s 涉及结论强度表述但 strength_matches 未登记" % (f.get("finding_id") or i))

    # ---- D. 论证链节点完备 ----
    for ci, ch in enumerate(chains):
        cid = str(ch.get("chain_id") or ci)
        nodes = [n for n in (ch.get("nodes") or []) if isinstance(n, dict)]
        roles = {str(n.get("role") or "") for n in nodes}
        bad_roles = roles - set(ROLES)
        if bad_roles:
            report["problems"].append("链 %s 存在非法节点角色: %s" % (cid, ",".join(sorted(bad_roles))))
        need_premise = not ("premise" in roles or "hypothesis" in roles)
        need_concl = "conclusion" not in roles
        ok = (not need_premise) and (not need_concl) and len(nodes) >= 2
        add("chains[%d].node_complete" % ci,
            "链节点完备（≥2 节点，含 premise/hypothesis 与 conclusion，角色枚举合法）",
            not off("chain"), (not off("chain")) and ok)
        if not off("chain") and not ok:
            if need_premise:
                report["problems"].append("链 %s 缺 premise/hypothesis 节点（论证链节点完备性违规）" % cid)
            if need_concl:
                report["problems"].append("链 %s 缺 conclusion 节点（论证链节点完备性违规）" % cid)
            if len(nodes) < 2:
                report["problems"].append("链 %s 节点数 <2（不足以构成论证链）" % cid)
    node_ids = {str(n.get("node_id")) for ch in chains
                for n in (ch.get("nodes") or []) if isinstance(n, dict) and n.get("node_id")}
    for i, f in enumerate(findings):
        ref = f.get("chain_ref")
        if ref:
            ok = str(ref) in node_ids
            add("findings[%d].chain_ref" % i, "chain_ref 须指向存在的链节点",
                not off("chain"), (not off("chain")) and ok)
            if not off("chain") and not ok:
                report["problems"].append("%s chain_ref=%r 指向不存在的链节点" % (f.get("finding_id") or i, ref))

    # ---- E. 证据链 + 待复核与误报抑制登记 ----
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        st = f.get("status")
        if st == "confirmed":
            cl = claim_idx.get(fid) or []
            quote = norm(f.get("quote"))
            backed = any(quote and quote in norm(e.get("quote"))
                         for c in cl for e in (c.get("evidence") or []))
            add("findings[%d].claim_backed" % i, "confirmed ⇒ claims 逐字回证",
                not off("pending"), (not off("pending")) and backed)
            if not off("pending") and not backed:
                report["problems"].append("%s confirmed 但 claims 证据链无逐字回证" % fid)
            if not off("pending") and f.get("category") == "fact_error" and not str(f.get("evidence") or "").strip():
                report["problems"].append("%s category=fact_error 但对照依据 evidence 为空" % fid)
            if not off("pending") and not str(f.get("revision_suggestion") or "").strip():
                report["problems"].append("%s 已判定但 revision_suggestion 为空" % fid)
        if st == "pending":
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
        ic = cov.get("issue_type_counts") or {}
        reali = {k: sum(1 for f in findings if f.get("issue_type") == k) for k in ISSUE_TYPES
                 if isinstance(ic.get(k), int)}
        badi = [k for k, v in reali.items() if ic.get(k) != v]
        if badi:
            report["problems"].append("coverage.issue_type_counts 与实际不符: %s" % badi)
    cleared = {str(c.get("scope")) for c in (inner.get("clearances") or [])
               if isinstance(c, dict) and c.get("scope")}
    zero_facets = [k for k in FACETS
                   if sum(1 for f in findings if f.get("facet") == k) == 0
                   and "facet:%s" % k not in cleared]
    if zero_facets and not unchecked:
        report["problems"].append("分面 %s 零发现但 unchecked 为空且未登记 clearances 豁免（须登记豁免或补查）"
                                  % ",".join(zero_facets))

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
        ap.add_argument("--ledger", default="/app/work/rubrics.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | location,taxonomy,strength,chain,pending 子集")
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
    cov_state = "enforced" if ((res.get("result") or {}).get("coverage") or {}).get("facet_counts") else "not_found"
    report["gates"].append({"gate": "chain_audit_output", "state": cov_state,
                            "note": "" if cov_state == "enforced" else "chain_audit.py 未回写 coverage，下游不得宣称已核对"})
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
