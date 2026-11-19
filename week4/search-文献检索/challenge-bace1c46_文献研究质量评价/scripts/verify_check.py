#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（lit-quality-appraise / 文献研究质量评价）。

对 result.json 做五组机械校验（与题面机检点逐项对应，问题串带标签前缀供
gain_probe 按组计数）：
  A. [coverage] 清单项覆盖：每篇文献的 appraisals 必须覆盖量表声明的全部 domain；
     每条 judged=true，或 unassessable 有 abstain_reason、not_applicable 有 na_reason。
  B. [grading] 分级口径一致：grade 必须 == grading_rules.grade_map[judgment]；
     bias_direction 对负面判定必填；按 penalty_map/thresholds/abstain_rule/direction_rule
     机械复算每篇 penalty_total 与 risk_of_bias，与 risk_summary（grade_rollup.py 产出）
     逐项对照。
  C. [evidence] 证据定位可回证：adequate/concerns/inadequate 必须有 evidence_quote，
     且逐字（空白归一化后子串匹配）出现在 claims 证据链中，并能在 case.json 的
     来源文本中找到；unreported/unassessable 允许 quote 为空但须给定位说明。
     penalty_total 数字未回证列入 unbacked_numbers 判 FAIL。
  D. [defect] 缺陷与报告不全区分：category 必须 == category_map[judgment]
     （inadequate⇒design_flaw；unreported⇒reporting_gap），跨类矛盾判 FAIL。
  E. [pending] 弃权登记：unassessable 条目必须登记进 pending_review（reason+needed_action）。

键归属（多脚本禁写同一键）：本脚本只写顶层 self_check / gates / unbacked_numbers /
validator_verdict 四键；risk_summary 归 grade_rollup.py；gain_evidence / efficiency 归
gain_probe.py；其余归 build_skeleton.py + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
防汉字陷阱：全程不做 .isalpha()/.isalnum() 判定，token 校验一律用显式正则
（反斜杠 w 字符类，含 CJK）或精确枚举匹配；引文匹配只做空白归一化。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--rubric /app/work/grading_rules.json] [--out 报告路径] [--ablate none|all|组列表]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

JUD = ("adequate", "concerns", "inadequate", "unreported", "not_applicable", "unassessable")
GRADES = ("high", "medium", "low", "uncertain")
CATS = ("design_flaw", "reporting_gap", "none")
DIRS = ("favors_conclusion", "against_conclusion", "unclear", "none")
PTYPES = ("rct", "cohort", "cross_sectional", "case_control", "systematic_review", "other", "unknown")
NEG = ("concerns", "inadequate", "unreported")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（不做 isalpha/isalnum——对汉字串不可靠；只折叠空白）。"""
    return re.sub(r"\s+", "", str(s or ""))


def checklist_id_ok(s):
    # 显式正则（\w 含 CJK），兼容 DS-01 与自编号量表；不用 isalpha
    return bool(re.match(r"^[\w]{2,6}-\d{1,3}$", str(s or ""), re.UNICODE))


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


def build_doc_index(case):
    """从 case.json 收集来源文本：{doc_id: 全文拼接文本}。键兼容 papers/documents 等。"""
    idx = {}
    if not isinstance(case, dict):
        return idx
    for key in ("papers", "documents", "articles", "materials", "studies", "records"):
        v = case.get(key)
        if not isinstance(v, list):
            continue
        for e in v:
            if not isinstance(e, dict):
                continue
            did = str(e.get("doc_id") or e.get("id") or e.get("paper_id") or "")
            if not did:
                continue
            chunks = []
            for tk in ("title", "abstract", "fulltext", "text", "body", "methods", "results"):
                val = e.get(tk)
                if isinstance(val, str):
                    chunks.append(val)
                elif isinstance(val, dict):
                    for sv in val.values():
                        if isinstance(sv, str):
                            chunks.append(sv)
            idx[did] = "\n".join(chunks)
    return idx


def rules_ok(rules):
    """校验 grading_rules 可机械执行：四个映射键齐全且 judgment 全覆盖。"""
    if not isinstance(rules, dict):
        return None
    need = ("grade_map", "category_map", "penalty_map", "thresholds")
    if not all(k in rules for k in need):
        return None
    for j in JUD:
        if j not in rules.get("grade_map", {}) or j not in rules.get("category_map", {}) \
                or j not in rules.get("penalty_map", {}):
            return None
    if not str(rules.get("declared_at") or "").strip():
        return None
    return rules


def rollup(paper, rules):
    """按事前规则机械复算单篇汇总。返回 dict 或 None（规则缺失）。"""
    if rules is None:
        return None
    gm, cm = rules["grade_map"], rules["category_map"]
    pm, th = rules["penalty_map"], rules["thresholds"]
    total, abstained = 0, 0
    counts = {"high": 0, "medium": 0, "low": 0, "uncertain": 0, "none_grade": 0}
    dirs = []
    for a in paper.get("appraisals") or []:
        if not isinstance(a, dict):
            continue
        j = a.get("judgment")
        total += int(pm.get(j, 0) or 0)
        g = a.get("grade")
        counts[str(g) if g in GRADES else "none_grade"] += 1
        if j == "unassessable":
            abstained += 1
        if a.get("bias_direction") in ("favors_conclusion", "against_conclusion"):
            dirs.append(a["bias_direction"])
    band = "unknown"
    for name in ("low", "some_concerns", "high"):
        rng = th.get(name) or []
        if len(rng) == 2 and rng[0] <= total <= rng[1]:
            band = {"low": "low", "some_concerns": "medium", "high": "high"}[name]
            break
    risk = band
    if abstained >= 2 or (abstained >= 1 and band == "low"):
        risk = "uncertain"
    if any(d == "against_conclusion" for d in dirs):
        direction = "against_conclusion"
    elif any(d == "favors_conclusion" for d in dirs):
        direction = "favors_conclusion"
    else:
        direction = "unclear"
    return {"paper_id": paper.get("paper_id"), "penalty_total": total,
            "risk_of_bias": risk, "band_raw": band, "abstained": abstained,
            "grade_counts": counts, "direction": direction}


# ------------------------------------------------------------------ 主分析
def analyze(res, case, ablate="none", case_state="enforced", rules_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "unbacked_evidence": [], "disabled_checks": [],
              "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ("coverage", "grading", "evidence", "defect", "pending"):
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("[structure] result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    papers = [p for p in (inner.get("papers") or []) if isinstance(p, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    rules = rules_ok(inner.get("grading_rules") or {})
    checklist = inner.get("checklist") or {}
    domains_req = [str(d) for d in (checklist.get("domains") or [])
                   if isinstance(d, str)] if isinstance(checklist, dict) else []
    risk_summary = inner.get("risk_summary") or {}
    per_paper = {str(p.get("paper_id")): p for p in (risk_summary.get("per_paper") or [])
                 if isinstance(p, dict)}
    doc_index = build_doc_index(case)

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "rules_ledger", "state": rules_state if rules else "invalid",
                            "note": "" if rules else "/app/work/grading_rules.json 台账缺失或非法，下游不得宣称已核对"})
    rs_state = "enforced" if (risk_summary.get("per_paper") is not None
                              and isinstance(risk_summary.get("per_paper"), list)
                              and risk_summary.get("per_paper")) else "not_found"
    report["gates"].append({"gate": "grade_rollup", "state": rs_state,
                            "note": "" if rs_state == "enforced" else "risk_summary 未回填（grade_rollup.py 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启） ----
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)

    def quote_backed(q, source_id):
        nq = norm(q)
        if not nq:
            return False
        for c in claim_idx.get(source_id, []) + claim_idx.get("*", []):
            for e in (c.get("evidence") or []):
                if nq and nq in norm(e.get("quote")):
                    return True
        return False

    def quote_in_source(q):
        nq = norm(q)
        if not nq:
            return False
        for _did, text in doc_index.items():
            if nq in norm(text):
                return True
        return False

    def per_appraisal(i, j, key):
        return "papers[%d].appraisals[%d].%s" % (i, j, key)

    n_jud = n_abst = n_dflaw = n_rgap = n_na = 0
    for i, paper in enumerate(papers):
        pid = str(paper.get("paper_id") or "papers[%d]" % i)
        if paper.get("paper_type") is not None and paper.get("paper_type") not in PTYPES:
            report["problems"].append("[enum] %s paper_type 枚举非法: %r" % (pid, paper.get("paper_type")))
        aps = [a for a in (paper.get("appraisals") or []) if isinstance(a, dict)]

        # ---- A. 清单项覆盖 ----
        cov_domains = set()
        for j, a in enumerate(aps):
            jd = a.get("judgment")
            cov_domains.add(str(a.get("domain") or ""))
            judged_ok = (jd in JUD) and (
                jd == "unassessable" and str(a.get("abstain_reason") or "").strip()
                or jd == "not_applicable" and str(a.get("na_reason") or "").strip()
                or jd not in ("unassessable", "not_applicable"))
            ok = add(per_appraisal(i, j, "item_complete"),
                     "judged 且有理由（或弃权/不适用说明）", True, bool(judged_ok) or a.get("judged") is not True)
            if not off("coverage") and not ok and a.get("judged") is True:
                report["problems"].append("[coverage] %s/%s 判 judged=true 但缺少完成要素（judgment 非法或弃权/不适用无说明）"
                                          % (pid, a.get("checklist_id")))
                add(per_appraisal(i, j, "item_complete"), "judged 且有理由", True, False)
            if jd == "unassessable":
                n_abst += 1
            elif jd == "not_applicable":
                n_na += 1
            elif jd in ("adequate", "concerns", "inadequate", "unreported"):
                n_jud += 1
            if jd == "inadequate" or jd == "concerns":
                n_dflaw += 1 if jd == "inadequate" else 0
            if jd == "unreported":
                n_rgap += 1
        if not off("coverage") and domains_req:
            missing = [d for d in domains_req if d not in cov_domains]
            ok = not missing
            add("papers[%d].domain_coverage" % i, "量表 domain 全覆盖", True, ok)
            if missing:
                report["problems"].append("[coverage] %s 缺少 domain: %s（量表要求 %s）"
                                          % (pid, ",".join(missing), ",".join(domains_req)))
        if not off("coverage") and not aps and paper.get("judged") is True:
            report["problems"].append("[coverage] %s 标 judged=true 但 appraisals 为空" % pid)

        # ---- B. 分级口径一致 ----
        for j, a in enumerate(aps):
            jd = a.get("judgment")
            g_exp = rules["grade_map"].get(jd) if rules else None
            g_ok = (g_exp == a.get("grade")) if rules else None
            add(per_appraisal(i, j, "grade_consistency"), "grade == grade_map[judgment]",
                not off("grading"), bool(g_ok) if rules else None)
            if not off("grading") and rules and g_exp != a.get("grade"):
                report["problems"].append("[grading] %s/%s grade=%r 与 grade_map[%s]=%r 不符（分级口径漂移）"
                                          % (pid, a.get("checklist_id"), a.get("grade"), jd, g_exp))
            if not off("grading") and rules and jd in NEG and \
                    a.get("bias_direction") not in ("favors_conclusion", "against_conclusion", "unclear"):
                report["problems"].append("[grading] %s/%s 负面判定但 bias_direction 缺失/非法: %r"
                                          % (pid, a.get("checklist_id"), a.get("bias_direction")))
            if not off("grading") and rules and jd in NEG and not checklist_id_ok(a.get("checklist_id")):
                report["problems"].append("[grading] %s checklist_id 非法: %r（须形如 XX-01，不做 isalpha 判定）"
                                          % (pid, a.get("checklist_id")))

        # ---- C. 证据定位可回证 ----
        for j, a in enumerate(aps):
            jd = a.get("judgment")
            q_needed = jd in ("adequate", "concerns", "inadequate")
            q = a.get("evidence_quote")
            ok = True
            if not off("evidence"):
                if q_needed and not str(q or "").strip():
                    report["problems"].append("[evidence] %s/%s judgment=%s 但 evidence_quote 为空"
                                              % (pid, a.get("checklist_id"), jd))
                    ok = False
                if not str(a.get("rationale") or "").strip() and jd != "not_applicable":
                    report["problems"].append("[evidence] %s/%s rationale 为空（每条判断须附理由）"
                                              % (pid, a.get("checklist_id")))
                    ok = False
                if str(q or "").strip():
                    backed = quote_backed(q, pid) or quote_backed(q, "*")
                    in_src = quote_in_source(q) if doc_index else True
                    if not backed:
                        report["problems"].append("[evidence] %s/%s 的 evidence_quote 在 claims 证据链中无逐字回证"
                                                  % (pid, a.get("checklist_id")))
                        report["unbacked_evidence"].append(
                            {"item": per_appraisal(i, j, "evidence_quote"), "reason": "claims 无回证"})
                        ok = False
                    if doc_index and not in_src:
                        report["problems"].append("[evidence] %s/%s 的 evidence_quote 在 case.json 来源文本中不存在（不得转述或编造）"
                                                  % (pid, a.get("checklist_id")))
                        report["unbacked_evidence"].append(
                            {"item": per_appraisal(i, j, "evidence_quote"), "reason": "来源文本无此句"})
                        ok = False
                elif q_needed:
                    add(per_appraisal(i, j, "evidence_backed"), "quote 非空且逐字回证", not off("evidence"), False)
                    continue
            add(per_appraisal(i, j, "evidence_backed"), "quote 非空且逐字回证", not off("evidence"), ok)

        # ---- D. 缺陷与报告不全区分 ----
        for j, a in enumerate(aps):
            jd = a.get("judgment")
            c_exp = rules["category_map"].get(jd) if rules else None
            c_ok = (c_exp == a.get("category")) if rules else None
            add(per_appraisal(i, j, "category_consistency"), "category == category_map[judgment]",
                not off("defect"), bool(c_ok) if rules else None)
            if not off("defect") and rules and c_exp != a.get("category"):
                report["problems"].append("[defect] %s/%s category=%r 与 category_map[%s]=%r 不符"
                                          % (pid, a.get("checklist_id"), a.get("category"), jd, c_exp))
            if not off("defect") and rules and jd == "inadequate" and a.get("category") == "reporting_gap":
                report["problems"].append("[defect] %s/%s 判 inadequate 却归 reporting_gap（设计缺陷≠报告不全）" % (pid, a.get("checklist_id")))
            if not off("defect") and rules and jd == "unreported" and a.get("category") == "design_flaw":
                report["problems"].append("[defect] %s/%s 判 unreported 却归 design_flaw（报告不全≠设计缺陷）" % (pid, a.get("checklist_id")))

        # ---- E. 弃权登记 ----
        for j, a in enumerate(aps):
            if a.get("judgment") == "unassessable":
                reg = [p for p in pending_reg if str(p.get("paper_id")) == pid
                       and str(p.get("checklist_id")) == str(a.get("checklist_id"))]
                ok = bool(reg) and all(str(p.get("reason") or "").strip() for p in reg) \
                     and all(str(p.get("needed_action") or "").strip() for p in reg)
                add(per_appraisal(i, j, "pending_registered"), "unassessable ⇒ 登记 pending_review",
                    not off("pending"), ok)
                if not off("pending") and not ok:
                    report["problems"].append("[pending] %s/%s 弃权(unassessable)但未登记进 pending_review（缺 reason/needed_action）"
                                              % (pid, a.get("checklist_id")))

        # ---- 汇总复算 ----
        r = rollup(paper, rules)
        stored = per_paper.get(pid)
        if not off("grading") and rules:
            if stored is None:
                report["problems"].append("[grading] %s 在 risk_summary.per_paper 缺失（grade_rollup.py 未跑或漏篇）" % pid)
            elif r is not None:
                ok = (stored.get("penalty_total") == r["penalty_total"]
                      and stored.get("risk_of_bias") == r["risk_of_bias"]
                      and stored.get("direction") == r["direction"])
                add("papers[%d].rollup_recompute" % i, "penalty/risk/direction 机械复算一致", True, ok)
                if not ok:
                    report["problems"].append("[grading] %s 汇总复算不符（期望 penalty=%s risk=%s dir=%s，实际 %s/%s/%s）"
                                              % (pid, r["penalty_total"], r["risk_of_bias"], r["direction"],
                                                 stored.get("penalty_total"), stored.get("risk_of_bias"),
                                                 stored.get("direction")))
            # penalty 数字回证
            if r is not None:
                sstr = str(r["penalty_total"])
                backed = any(sstr in norm(c.get("text")) or
                             any(sstr in norm(e.get("quote")) for e in (c.get("evidence") or []))
                             for c in claim_idx.get(pid, []))
                if not backed:
                    report["unbacked_numbers"].append(
                        {"item": "papers[%s].penalty_total" % pid, "value": sstr,
                         "reason": "penalty_total 未出现在该篇任何 claim text/evidence quote 中"})
            if not off("evidence") and not claim_idx.get(pid):
                report["problems"].append("[evidence] %s 无任何 claim（每篇文献须有可复核的证据链条目）" % pid)

    # ---- 覆盖面汇总（始终开启） ----
    cov = inner.get("coverage") or {}
    if cov:
        exp = {"papers_total": len(papers), "items_total": sum(len(p.get("appraisals") or []) for p in papers)}
        bad = [k for k, v in exp.items() if isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("[structure] coverage 汇总与实际不符: %s" % bad)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    all_judged = all(p.get("judged") is True and (p.get("appraisals") or [])
                     for p in papers) if papers else False
    any_judged = any(p.get("judged") is True and (p.get("appraisals") or []) for p in papers)
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("[grading] verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "appraised" and papers and not all_judged:
        report["problems"].append("[grading] verdict=appraised 但存在未判定/空评篇目")
    if verdict == "partially_appraised" and all_judged:
        report["problems"].append("[grading] verdict=partially_appraised 但全部篇目已判定（应为 appraised）")
    if verdict == "not_appraised" and any_judged:
        report["problems"].append("[grading] verdict=not_appraised 但存在已判定篇目")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in ("success", "partial", "unable_to_determine", "refused"):
        report["problems"].append("[enum] run_status.state 枚举非法或缺失: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") and \
            not str(rs.get("reason") or "").strip():
        report["problems"].append("[enum] run_status 非 success 但 reason 为空")

    # ---- steps（始终开启） ----
    steps = inner.get("steps") or []
    if not steps:
        report["problems"].append("[structure] steps 为空（须给出他人可重跑的步骤）")
    elif not any(str(s.get("command") or "").strip() for s in steps if isinstance(s, dict)):
        report["problems"].append("[structure] steps 无任何可执行 command")

    # ---- 契约字段 ----
    if case_state == "enforced":
        for fname in contract_fields(case):
            if fname not in res:
                report["problems"].append("[contract] 缺少 output_contract 字段: %s" % fname)

    if report["unbacked_numbers"]:
        report["problems"].append("[evidence] 存在 %d 个未回证数字（见 unbacked_numbers）" % len(report["unbacked_numbers"]))
    if report["unbacked_evidence"]:
        report["problems"].append("[evidence] 存在 %d 条不可回证证据（见 unbacked_evidence）" % len(report["unbacked_evidence"]))
    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--rubric", default="/app/work/grading_rules.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | coverage,grading,evidence,defect,pending 子集")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 self_check/gates/unbacked_*/validator_verdict 回写 result.json")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        msg = "result.json 不存在或不可解析: %s（不中断交付）" % args.result
        print("[verify_check] FAIL: %s" % msg)
        _dump(args.out, {"verdict": "FAIL", "problems": [msg], "self_check": [], "gates": [],
                         "unbacked_numbers": [], "unbacked_evidence": [], "ablate": args.ablate})
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    rules = load_json(args.rubric) if os.path.exists(args.rubric) else None
    rules_state = "enforced" if isinstance(rules, dict) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state, rules_state=rules_state)
    report["gates"].append({"gate": "rollup_output",
                            "state": "enforced" if (res.get("result") or {}).get("risk_summary")
                            else "not_found",
                            "note": "" if (res.get("result") or {}).get("risk_summary")
                            else "grade_rollup.py 未回写 risk_summary，下游不得宣称已核对"})
    _dump(args.out, report)

    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict):
                cur["self_check"] = report.get("self_check") or []
                cur["gates"] = report.get("gates") or []
                cur["unbacked_numbers"] = report.get("unbacked_numbers") or []
                cur["unbacked_evidence"] = report.get("unbacked_evidence") or []
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
