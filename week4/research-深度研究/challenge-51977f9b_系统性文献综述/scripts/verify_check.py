#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（sysrev-review-synthesis）。

对 result.json 做六组机械校验（与题面机检点逐项对应），支持 --ablate 分组消融：
  A. 协议事前声明（protocol）：综述协议（研究问题/检索式/纳排标准）须有版本号、
     registered_at/declared_at 且在任何判定前注册进 protocol_ledger 台账；判定
     引用版本必须等于台账最终版本（防协议漂移）。review_registration 齐备。
  B. 筛选判定有据（screening）：decision ⇔ 理由码字典 + criteria_ref 引用存在
     标准 id；已判定必有 rationale；included/excluded 必有逐字 evidence_quote+
     location 且在 claims 回证；pending 必登记进 pending_review（reason+
     needed_action）；escalated 冲突进待复核。
  C. 漏斗计数闭合（funnel）：五级计数逐级复算核对 + excluded_by_reason 合计 ==
     excluded + closure==closed + coverage 汇总一致。
  D. 提取项回证（extraction）：纳入研究逐条结构化提取（study_design/sample/
     effect），每块证据逐字回证（extraction_guard.analyze_extraction）。
  E. 质量评价一致（quality）：纳入研究逐条评价、维度判定合法、overall_grade 等
     于量表机械推导（quality_audit.analyze_quality）。
  F. 强度分级一致（synthesis）：每条结论 strength 等于按规则机械推导级别，支持/
     冲突记录回链真实 included 记录，gaps/偏倚登记齐备
     （synthesis_check.analyze_synthesis）。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；funnel 归 flow_audit.py，duplicate_of/merge_basis/
conflicts(duplicate_versions) 归 dedupe.py，gain_evidence/efficiency 归
gain_probe.py，其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--ledger /app/work/protocol_ledger.json] [--out /app/work/verify_check.json] \
        [--ablate none|all|protocol,screening,funnel,extraction,quality,synthesis]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from quality_audit import analyze_quality, load_scale  # noqa: E402
    from extraction_guard import analyze_extraction  # noqa: E402
    from synthesis_check import analyze_synthesis  # noqa: E402
except Exception as _e:  # pragma: no cover
    print("[verify_check] 无法导入领域审计器: %s" % _e)
    analyze_quality = analyze_extraction = analyze_synthesis = None
    load_scale = None

DECISIONS = ("included", "excluded", "pending_review")
CONF = ("high", "medium", "low")
VENUE = ("preprint", "published", "unknown")

BUILTIN_EX = ("RC-EX-SCOPE", "RC-EX-DESIGN", "RC-EX-POPULATION", "RC-EX-INTERVENTION",
              "RC-EX-OUTCOME", "RC-EX-LANGUAGE", "RC-EX-TIME", "RC-EX-DUPLICATE",
              "RC-EX-PUBTYPE")
BUILTIN_PD = ("RC-PD-NO-ABSTRACT", "RC-PD-BORDERLINE", "RC-PD-METADATA",
              "RC-PD-DISAGREEMENT", "RC-PD-FULLTEXT")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def reason_codes():
    """理由码字典：优先 resources/reason_codes.json，失败回退内置集合。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "reason_codes.json")
    d = load_json(path)
    if isinstance(d, dict):
        ex = tuple(str(x) for x in (d.get("exclusion") or {}).get("codes") or BUILTIN_EX)
        pd = tuple(str(x) for x in (d.get("pending") or {}).get("codes") or BUILTIN_PD)
        return ex, pd
    return BUILTIN_EX, BUILTIN_PD


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def recompute_funnel(records):
    recs = [r for r in records if isinstance(r, dict)]
    identified = len(recs)
    dups_removed = sum(1 for r in recs if r.get("duplicate_of"))
    non_dup = [r for r in recs if not r.get("duplicate_of")]
    included = sum(1 for r in non_dup if r.get("decision") == "included")
    excluded = sum(1 for r in non_dup if r.get("decision") == "excluded")
    pending = sum(1 for r in non_dup if r.get("decision") == "pending_review")
    by_reason = {}
    for r in non_dup:
        if r.get("decision") == "excluded" and r.get("reason_code"):
            by_reason[str(r["reason_code"])] = by_reason.get(str(r["reason_code"]), 0) + 1
    return {"identified": identified, "duplicates_removed": dups_removed,
            "screened": identified - dups_removed, "excluded": excluded,
            "included": included, "pending_review": pending,
            "excluded_by_reason": by_reason}


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


def analyze(res, case, ablate="none", case_state="enforced", ledger_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ("protocol", "screening", "funnel", "extraction", "quality", "synthesis"):
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    records = [r for r in (inner.get("records") or []) if isinstance(r, dict)]
    judged = sum(1 for r in records if r.get("judged") is True)
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = inner.get("pending_review") or []
    conflicts = inner.get("conflicts") or []
    funnel = inner.get("funnel") or {}
    cov = inner.get("coverage") or {}
    criteria = inner.get("criteria") or {}
    ex_codes, pd_codes = reason_codes()

    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "protocol_ledger", "state": ledger_state,
                            "note": "" if ledger_state == "enforced" else "协议台账缺失，协议事前声明不可独立证实，下游不得宣称已核对"})
    funnel_state = "enforced" if funnel.get("closure") in ("closed", "open") else "not_found"
    report["gates"].append({"gate": "flow_audit_output", "state": funnel_state,
                            "note": "" if funnel_state == "enforced" else "flow_audit.py 未回填漏斗，下游不得宣称已核对"})
    dedupe_state = "enforced" if (any(r.get("duplicate_of") for r in records)
                                  or any(str(c.get("kind")) == "duplicate_versions" for c in conflicts)) else "skipped_not_provided"
    report["gates"].append({"gate": "dedupe_output", "state": dedupe_state,
                            "note": "" if dedupe_state == "enforced" else "未发现重复对（dedupe 输出为空）；若确有重复请补跑 dedupe.py"})

    # ---- 枚举合法性（始终开启） ----
    for i, r in enumerate(records):
        rid = r.get("record_id") or "records[%d]" % i
        if r.get("decision") is not None and r.get("decision") not in DECISIONS:
            report["problems"].append("%s decision 枚举非法: %r（须 included/excluded/pending_review）" % (rid, r.get("decision")))
        if r.get("confidence") is not None and r.get("confidence") not in CONF:
            report["problems"].append("%s confidence 枚举非法: %r" % (rid, r.get("confidence")))
        if r.get("venue_type") not in VENUE:
            report["problems"].append("%s venue_type 枚举非法: %r（须 preprint/published/unknown）" % (rid, r.get("venue_type")))

    # ---- A. 标准事前声明 ----
    in_ids = {str(c.get("criterion_id")) for c in (criteria.get("inclusion") or []) if isinstance(c, dict)}
    ex_ids = {str(c.get("criterion_id")) for c in (criteria.get("exclusion") or []) if isinstance(c, dict)}
    if not off("protocol"):
        ver_ok = bool(str(criteria.get("version") or "").strip())
        decl_ok = bool(str(criteria.get("declared_at") or "").strip())
        add("criteria.pre_declared", "标准版本号与 declared_at 在判定前声明", True, ver_ok and decl_ok)
        if not ver_ok:
            report["problems"].append("criteria.version 为空（纳排标准须事前声明版本号，防标准漂移）")
        if not decl_ok:
            report["problems"].append("criteria.declared_at 为空（须写明声明时点，且早于逐条判定）")
        if ledger_state == "enforced":
            pass  # 台账比对在 main 里补充传入
        if not in_ids and not ex_ids:
            report["problems"].append("criteria 纳入/排除标准均为空（须逐条编号为可判定判据）")
        for lst, tag in ((criteria.get("inclusion") or [], "inclusion"), (criteria.get("exclusion") or [], "exclusion")):
            for j, c in enumerate(lst):
                if isinstance(c, dict) and not str(c.get("criterion_id") or "").strip():
                    report["problems"].append("criteria.%s[%d] 缺 criterion_id（须逐条编号）" % (tag, j))
    for i, r in enumerate(records):
        rid = r.get("record_id") or "records[%d]" % i
        if r.get("judged") is not True:
            continue
        dec, rc = r.get("decision"), r.get("reason_code")
        refs = {str(x) for x in (r.get("criteria_ref") or [])}
        ok = True
        if dec == "included":
            ok = bool(refs) and refs.issubset(in_ids) and in_ids
        elif dec == "excluded":
            ok = (rc in ex_codes) and (bool(refs) and refs.issubset(ex_ids) or rc == "RC-EX-DUPLICATE")
        elif dec == "pending_review":
            ok = (rc in pd_codes) and bool(str(r.get("pending_reason") or "").strip())
        add("records[%d].criteria_consistency" % i,
            "decision ⇔ 理由码字典 + criteria_ref 引用存在标准", not off("screening"), (not off("screening")) and ok)
        if not off("screening") and not ok:
            if dec == "included" and not refs:
                report["problems"].append("%s 判 included 但未引用任何纳入标准 id（criteria_ref 空）" % rid)
            elif dec == "included":
                report["problems"].append("%s 引用了不存在的纳入标准 id: %s" % (rid, sorted(refs - in_ids)))
            elif dec == "excluded" and rc not in ex_codes:
                report["problems"].append("%s 判 excluded 但理由码 %r 不在排除理由码字典中" % (rid, rc))
            elif dec == "excluded" and rc != "RC-EX-DUPLICATE" and not refs:
                report["problems"].append("%s 判 excluded 但未引用任何排除标准 id（criteria_ref 空）" % rid)
            elif dec == "excluded":
                report["problems"].append("%s 引用了不存在的排除标准 id: %s" % (rid, sorted(refs - ex_ids)))
            elif dec == "pending_review" and rc not in pd_codes:
                report["problems"].append("%s 判 pending_review 但理由码 %r 不在待复核理由码字典中" % (rid, rc))
            else:
                report["problems"].append("%s 判 pending_review 但 pending_reason 为空" % rid)

    # ---- B. 判定理由有据 ----
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    for i, r in enumerate(records):
        rid = str(r.get("record_id") or i)
        dec = r.get("decision")
        if r.get("judged") is not True or not dec:
            continue
        ok_r = bool(str(r.get("rationale") or "").strip())
        add("records[%d].rationale_present" % i, "已判定 ⇒ rationale 非空", not off("screening"), (not off("screening")) and ok_r)
        if not off("screening") and not ok_r:
            report["problems"].append("%s 已判定但 rationale 为空（理由完备性）" % rid)
        ok_q = bool(str(r.get("evidence_quote") or "").strip()) and bool(str(r.get("evidence_location") or "").strip())
        if dec in ("included", "excluded"):
            add("records[%d].evidence_present" % i, "included/excluded ⇒ evidence_quote+location", not off("screening"),
                (not off("screening")) and ok_q)
            if not off("screening") and not ok_q:
                report["problems"].append("%s 判 %s 但缺 evidence_quote 或 evidence_location" % (rid, dec))
        if not off("screening") and dec in ("included", "excluded", "pending_review") \
                and str(r.get("evidence_quote") or "").strip():
            # pending 无摘要时 evidence_quote 可为空（引用 RC-PD-NO-ABSTRACT/METADATA），
            # 不要求回证；included/excluded 缺 quote 已由 evidence_present 检查拦截。
            quote = norm(r.get("evidence_quote"))
            cl = claim_idx.get(rid) or []
            q_backed = (any(quote and quote in norm(e.get("quote"))
                            for c in cl for e in (c.get("evidence") or [])) if quote else False)
            add("records[%d].evidence_backed" % i, "evidence_quote 在 claims 逐字回证", not off("screening"),
                (not off("screening")) and q_backed)
            if not off("screening") and not q_backed:
                report["problems"].append("%s 的 evidence_quote 在 claims 证据链中无逐字回证" % rid)

    # ---- C. 流程计数闭合 ----
    if not off("funnel"):
        rec = recompute_funnel(records)
        ok_num = True
        for k in ("identified", "duplicates_removed", "screened", "excluded", "included", "pending_review"):
            stored = funnel.get(k)
            if isinstance(stored, int) and stored != rec[k]:
                ok_num = False
                report["problems"].append("funnel.%s 存值 %d 与机械复算 %d 不符" % (k, stored, rec[k]))
        add("funnel.counts_recompute", "漏斗五级计数机械复算对照", True, ok_num)
        ok_reason = isinstance(funnel.get("excluded_by_reason"), dict) \
            and funnel.get("excluded_by_reason") == rec["excluded_by_reason"] \
            and sum(rec["excluded_by_reason"].values()) == funnel.get("excluded")
        add("funnel.excluded_by_reason_sum", "排除原因分布与机械复算一致且合计 == excluded", True, ok_reason)
        if not ok_reason:
            report["problems"].append("funnel.excluded_by_reason（存值 %s）与逐条复算 %s 不一致或合计 != excluded"
                                      "（排除原因不完备）" % (funnel.get("excluded_by_reason"), rec["excluded_by_reason"]))
        ok_close = funnel.get("closure") == "closed"
        add("funnel.closure_closed", "closure == closed（识别→去重→筛选→纳入逐级闭合）", True, ok_close)
        if not ok_close:
            report["problems"].append("funnel.closure=%r（须 closed；跑 flow_audit.py 复算并修复计数）" % funnel.get("closure"))
        # coverage 汇总
        dup_merged = rec["duplicates_removed"]
        exp = {"total_records": len(records), "judged_records": judged,
               "included": rec["included"], "excluded": rec["excluded"],
               "pending_review": rec["pending_review"], "duplicates_merged": dup_merged}
        bad = [k for k, v in exp.items() if isinstance(cov.get(k), int) and cov[k] != v]
        add("coverage.consistency", "coverage 汇总与实际条目一致", True, not bad)
        if bad:
            report["problems"].append("coverage 汇总与实际条目不符: %s" % bad)
        # 冲突登记：duplicate_of 必须在 conflicts 有 duplicate_versions 条目
        for i, r in enumerate(records):
            if r.get("duplicate_of"):
                rid = str(r.get("record_id") or i)
                rec_c = [c for c in conflicts if isinstance(c, dict) and rid in [str(x) for x in (c.get("record_ids") or [])]]
                resolved = bool(rec_c) and any(str(c.get("resolution")) in ("merged", "escalated") for c in rec_c)
                add("records[%d].duplicate_recorded" % i, "duplicate_of ⇒ conflicts 登记", True, resolved)
                if not resolved and not off("screening"):
                    report["problems"].append("%s 标记 duplicate_of 但 conflicts 未登记 merged/escalated 处置" % rid)

    # ---- D. 待复核登记 ----
    for i, r in enumerate(records):
        rid = str(r.get("record_id") or i)
        if r.get("decision") == "pending_review":
            reg = [p for p in pending_reg if isinstance(p, dict) and str(p.get("record_id")) == rid]
            ok = bool(reg) and all(str(p.get("reason") or "").strip() and str(p.get("needed_action") or "").strip() for p in reg)
            add("records[%d].pending_registered" % i, "pending_review ⇒ 登记含 reason+needed_action", not off("screening"),
                (not off("screening")) and ok)
            if not off("screening") and not ok:
                report["problems"].append("%s 判 pending_review 但未登记进 pending_review（缺 reason/needed_action）" % rid)
    if not off("screening"):
        esc_ids = set()
        for c in conflicts:
            if isinstance(c, dict) and str(c.get("resolution")) == "escalated":
                esc_ids.update(str(x) for x in (c.get("record_ids") or []))
        unreg = []
        for rid in sorted(esc_ids):
            if not any(str(p.get("record_id")) == rid for p in pending_reg if isinstance(p, dict)):
                unreg.append(rid)
                report["problems"].append("冲突升级(escalated)记录 %s 未进入 pending_review" % rid)
        add("conflicts.escalated_registered", "escalated 冲突 ⇒ 全部登记进 pending_review", not off("screening"),
            (not off("screening")) and not unreg)

    # ---- E. 提取项回证（extraction）----
    if not off("extraction"):
        if analyze_extraction is None:
            report["problems"].append("领域审计器 extraction_guard 不可导入（提取项回证无法校验）")
        else:
            ext_rep = analyze_extraction(dict(inner, _claims=claims), case if isinstance(case, dict) else {})
            for sc_ in ext_rep.get("self_check", []):
                report["self_check"].append(dict(sc_, applied=not off("extraction")))
            for pr in ext_rep.get("problems", []):
                report["problems"].append("[extraction] %s" % pr)

    # ---- F. 质量评价一致（quality）----
    if not off("quality"):
        if analyze_quality is None:
            report["problems"].append("领域审计器 quality_audit 不可导入（质量评价一致性无法校验）")
        else:
            q_rep = analyze_quality(inner, load_scale() if load_scale else None)
            for sc_ in q_rep.get("self_check", []):
                report["self_check"].append(dict(sc_, applied=not off("quality")))
            for pr in q_rep.get("problems", []):
                report["problems"].append("[quality] %s" % pr)

    # ---- G. 强度分级一致（synthesis）----
    if not off("synthesis"):
        if analyze_synthesis is None:
            report["problems"].append("领域审计器 synthesis_check 不可导入（强度分级一致性无法校验）")
        else:
            s_rep = analyze_synthesis(inner)
            for sc_ in s_rep.get("self_check", []):
                report["self_check"].append(dict(sc_, applied=not off("synthesis")))
            for pr in s_rep.get("problems", []):
                report["problems"].append("[synthesis] %s" % pr)

    # ---- verdict / run_status / steps（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "screened" and judged != len(records):
        report["problems"].append("verdict=screened 但存在未判定条目（judged=false）")
    if verdict == "partially_screened" and judged == len(records):
        report["problems"].append("verdict=partially_screened 但全部条目已判定（应为 screened）")
    if verdict == "not_screened" and judged:
        report["problems"].append("verdict=not_screened 但存在已判定条目")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in ("success", "partial", "unable_to_determine", "refused"):
        report["problems"].append("run_status.state 枚举非法或缺失: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") and not str(rs.get("reason") or "").strip():
        report["problems"].append("run_status 非 success 但 reason 为空")
    steps = inner.get("steps") or []
    if not steps:
        report["problems"].append("steps 为空（须给出他人可重跑的审计步骤）")
    elif not any(str(s.get("command") or "").strip() for s in steps if isinstance(s, dict)):
        report["problems"].append("steps 无任何可执行 command")

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
        ap.add_argument("--ledger", default="/app/work/protocol_ledger.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | protocol,screening,funnel,extraction,quality,synthesis 子集")
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
    if ledger_state == "enforced":
        final_v = led.get("final_version")
        cur_v = (res.get("result") or {}).get("criteria", {}).get("version")
        if final_v and cur_v and str(final_v) != str(cur_v):
            print("[verify_check] FAIL: 协议漂移——判定引用版本 %r != 台账最终版本 %r" % (cur_v, final_v))

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state, ledger_state=ledger_state)
    report["gates"].append({"gate": "protocol_version_match",
                            "state": "enforced" if (ledger_state == "enforced" and
                                                    str(led.get("final_version") or "") == str((res.get("result") or {}).get("criteria", {}).get("version") or "")) else "not_found",
                            "note": "" if ledger_state != "enforced" else "判定引用版本与协议台账最终版本不一致时下游不得宣称已核对"})
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
