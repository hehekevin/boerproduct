#!/usr/bin/env python3
r"""verify_check.py — 业务逻辑校验器（stat-analysis-audit / 统计分析与结果解读）。

对 result.json 做七组机械校验（与题面机检点逐项对应，问题串带标签前缀供
gain_probe 按组计数）：
  A. [coverage] 清单覆盖：每组分析的 appraisals 必须覆盖六分面全部 domain
     （data_quality/descriptive/test_choice/effect_ci/interpretation/causal_claim）；
     每条 judged=true，或 unassessable 有 abstain_reason、not_applicable 有 na_reason。
  B. [grading] 解读分级一致：grade == claim_rules.grade_map[judgment]；
     claim_strength 不得超过 claim_rules.strength_map[design_type] 允许强度
     （过强结论降级）；负面判定必填 bias_direction；按 penalty_map/thresholds/
     abstain_rule/direction_rule 机械复算，与 interpret_summary（interpret_rollup.py
     产出）逐项对照。
  C. [evidence] 数值与证据回证：adequate 类判定（supported/concerns/inadequate）必须
     有 evidence_quote，且逐字出现在 claims 证据链并在 case.json 来源文本中存在；
     claimed 统计量数字（mean/sd/分位数）未在 claim text/quote 回证列入
     unbacked_numbers 判 FAIL。
  D. [defect] 缺陷分类一致：category == category_map[judgment]
     （inadequate⇒method_error；unreported⇒reporting_gap），跨类混淆判 FAIL。
  E. [recompute] 统计量复算一致：stat_recompute.per_dataset 中 match=false 的组判
     FAIL（claimed 与原始数据复算不符）；test_check.method_mismatch 同样判 FAIL。
  F. [causal] 因果表述约束：观察性/相关性设计 + claim 文本命中因果动词 ⇒ FAIL
     （相关≠因果）；与 interpret_summary.causal_ok=false 交叉核对。
  G. [pending] 弃权登记：unassessable 条目必须登记进 pending_review（reason+needed_action）。

键归属（多脚本禁写同一键）：本脚本只写顶层 self_check / gates / unbacked_numbers /
unbacked_evidence / validator_verdict 五键；stat_recompute 归 stat_recompute.py；
interpret_summary 归 interpret_rollup.py；gain_evidence / efficiency 归 gain_probe.py；
其余归 build_skeleton.py + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
防汉字陷阱：全程不做 .isalpha()/.isalnum() 判定，token 校验一律用显式正则
（\w 字符类含 CJK）或精确枚举匹配；引文匹配只做空白归一化。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--rubric /app/work/claim_rules.json] [--out 报告路径] [--ablate none|all|组列表]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

JUD = ("supported", "concerns", "inadequate", "unreported", "not_applicable", "unassessable")
GRADES = ("high", "medium", "low", "uncertain")
CATS = ("method_error", "reporting_gap", "interpretation_risk", "none")
DIRS = ("favors_conclusion", "against_conclusion", "unclear", "none")
DESIGNS = ("experimental", "quasi_experimental", "observational", "correlational", "unknown")
STRENGTHS = ("causal", "associative", "descriptive", "insufficient")
STRENGTH_ORDER = {"descriptive": 0, "insufficient": 0, "associative": 1, "causal": 2}
NEG = ("concerns", "inadequate", "unreported")
POS_QUOTE = ("supported", "concerns", "inadequate")


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
    # 显式正则（\w 含 CJK），兼容 DQ-01 与自编号清单；不用 isalpha
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
    """从 case.json 收集来源文本：{doc_id: 全文拼接文本}。键兼容 datasets 等。"""
    idx = {}
    if not isinstance(case, dict):
        return idx
    for key in ("datasets", "records", "data", "tables", "studies", "materials",
                "documents", "papers", "articles"):
        v = case.get(key)
        if not isinstance(v, list):
            continue
        for e in v:
            if not isinstance(e, dict):
                continue
            did = str(e.get("dataset_id") or e.get("doc_id") or e.get("id") or e.get("name") or "")
            if not did:
                continue
            chunks = []
            for tk in ("title", "description", "abstract", "text", "body", "methods",
                       "results", "notes", "data_dictionary", "task", "report"):
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
    """校验 claim_rules 可机械执行：四个映射键齐全且 judgment 全覆盖 + declared_at。"""
    if not isinstance(rules, dict):
        return None
    need = ("strength_map", "causal_verbs", "penalty_map", "thresholds")
    if not all(k in rules for k in need):
        return None
    for j in JUD:
        if j not in rules.get("penalty_map", {}):
            return None
    if not str(rules.get("declared_at") or "").strip():
        return None
    return rules


def rollup(analysis, rules):
    """按事前规则机械复算单组分析汇总。返回 dict 或 None（规则缺失）。"""
    if rules is None:
        return None
    pm, th = rules["penalty_map"], rules["thresholds"]
    sm = rules.get("strength_map") or {}
    total, abstained = 0, 0
    counts = {"high": 0, "medium": 0, "low": 0, "uncertain": 0, "none_grade": 0}
    dirs = []
    claim = analysis.get("claim") or {}
    text_low = str(claim.get("text") or "").lower()
    design = str(analysis.get("design_type") or "unknown")
    allowed = sm.get(design) or sm.get("unknown") or "descriptive"
    claimed_strength = str(claim.get("claim_strength") or "").strip().lower()
    overclaim = bool(claimed_strength and claimed_strength in STRENGTH_ORDER
                     and allowed in STRENGTH_ORDER
                     and STRENGTH_ORDER[claimed_strength] > STRENGTH_ORDER[allowed])
    verbs = [str(v) for v in (rules.get("causal_verbs") or [])]
    found = [v for v in verbs if v.lower() in text_low]
    observational = design in ("observational", "correlational", "quasi_experimental")
    causal_ok = not (observational and found)
    for ap in analysis.get("appraisals") or []:
        if not isinstance(ap, dict):
            continue
        j = ap.get("judgment")
        total += int(pm.get(j, 0) or 0)
        g = ap.get("grade")
        counts[str(g) if g in GRADES else "none_grade"] += 1
        if j == "unassessable":
            abstained += 1
        if ap.get("bias_direction") in ("favors_conclusion", "against_conclusion"):
            dirs.append(ap["bias_direction"])
    band = "unknown"
    for name in ("low", "some_concerns", "high"):
        rng = th.get(name) or []
        if len(rng) == 2 and rng[0] <= total <= rng[1]:
            band = {"low": "low", "some_concerns": "medium", "high": "high"}[name]
            break
    overall = band
    if abstained >= 2 or (abstained >= 1 and band == "low"):
        overall = "uncertain"
    if any(d == "against_conclusion" for d in dirs):
        direction = "against_conclusion"
    elif any(d == "favors_conclusion" for d in dirs):
        direction = "favors_conclusion"
    else:
        direction = "unclear"
    return {"analysis_id": analysis.get("analysis_id"), "penalty_total": total,
            "overall": overall, "band_raw": band, "abstained": abstained,
            "grade_counts": counts, "direction": direction, "overclaim": overclaim,
            "strength_allowed": allowed, "strength_claimed": claimed_strength or None,
            "strength_final": allowed if overclaim else (claimed_strength or allowed),
            "causal_verbs_found": found, "causal_ok": causal_ok}


def stat_numbers(analysis):
    """claimed 统计量数字集合（mean/sd/分位数/n），供数值回证。"""
    out = []
    desc = analysis.get("descriptive") or {}
    for k in ("n_claimed", "mean_claimed", "sd_claimed"):
        v = desc.get(k)
        if v is not None:
            out.append((k, v))
    for k, v in (desc.get("quantiles_claimed") or {}).items():
        if v is not None:
            out.append((k, v))
    return out


def num_backed(v, text_norm):
    for cand in (str(v), "%.4g" % float(v) if _is_num(v) else "", "%.6g" % float(v) if _is_num(v) else ""):
        if cand and norm(cand) and norm(cand) in text_norm:
            return True
    return False


def _is_num(v):
    try:
        float(v)
        return True
    except Exception:
        return False


def claimed_map(analysis):
    """claimed 统计量（*_claimed 命名 → 复算键名归一化）。"""
    desc = analysis.get("descriptive") or {}
    qc = desc.get("quantiles_claimed") or {}
    if not isinstance(qc, dict):
        qc = {}
    return {"n": desc.get("n_claimed"), "mean": desc.get("mean_claimed"),
            "variance": desc.get("variance_claimed"), "stdev": desc.get("sd_claimed"),
            "p25": qc.get("p25"), "p50": qc.get("p50"), "p75": qc.get("p75")}


def rel_diff_ok(a, b, tol):
    try:
        a, b = float(a), float(b)
    except Exception:
        return False
    denom = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / denom <= tol


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
    for g in ("coverage", "grading", "evidence", "defect", "recompute", "causal", "pending"):
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("[structure] result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    analyses = [a for a in (inner.get("analyses") or []) if isinstance(a, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    rules = rules_ok(inner.get("claim_rules") or {})
    checklist = inner.get("checklist") or {}
    domains_req = [str(d) for d in (checklist.get("domains") or [])
                   if isinstance(d, str)] if isinstance(checklist, dict) else []
    interpret_summary = inner.get("interpret_summary") or {}
    per_interp = {str(p.get("analysis_id")): p for p in (interpret_summary.get("per_analysis") or [])
                  if isinstance(p, dict)}
    stat_rc = inner.get("stat_recompute") or {}
    per_stat = {str(p.get("analysis_id")): p for p in (stat_rc.get("per_dataset") or [])
                if isinstance(p, dict)}
    doc_index = build_doc_index(case)

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "rules_ledger", "state": rules_state if rules else "invalid",
                            "note": "" if rules else "/app/work/claim_rules.json 台账缺失或非法，下游不得宣称已核对"})
    st_state = "enforced" if (per_stat and stat_rc.get("all_match") is not None) else "not_found"
    report["gates"].append({"gate": "stat_recompute", "state": st_state,
                            "note": "" if st_state == "enforced" else "stat_recompute.py 未回填，下游不得宣称已核对"})
    is_state = "enforced" if per_interp else "not_found"
    report["gates"].append({"gate": "interpret_rollup", "state": is_state,
                            "note": "" if is_state == "enforced" else "interpret_summary 未回填（interpret_rollup.py 未跑），下游不得宣称已核对"})

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
        return "analyses[%d].appraisals[%d].%s" % (i, j, key)

    n_jud = n_abst = 0
    for i, ana in enumerate(analyses):
        aid = str(ana.get("analysis_id") or "analyses[%d]" % i)
        if ana.get("design_type") is not None and ana.get("design_type") not in DESIGNS:
            report["problems"].append("[enum] %s design_type 枚举非法: %r" % (aid, ana.get("design_type")))
        claim = ana.get("claim") or {}
        if claim.get("claim_strength") is not None and claim.get("claim_strength") not in STRENGTHS:
            report["problems"].append("[enum] %s claim_strength 枚举非法: %r" % (aid, claim.get("claim_strength")))
        aps = [a for a in (ana.get("appraisals") or []) if isinstance(a, dict)]

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
                                          % (aid, a.get("checklist_id")))
                add(per_appraisal(i, j, "item_complete"), "judged 且有理由", True, False)
            if jd == "unassessable":
                n_abst += 1
            elif jd in ("supported", "concerns", "inadequate", "unreported"):
                n_jud += 1
        if not off("coverage") and domains_req:
            missing = [d for d in domains_req if d not in cov_domains]
            ok = not missing
            add("analyses[%d].domain_coverage" % i, "六分面 domain 全覆盖", True, ok)
            if missing:
                report["problems"].append("[coverage] %s 缺少 domain: %s（清单要求 %s）"
                                          % (aid, ",".join(missing), ",".join(domains_req)))
        if not off("coverage") and not aps and ana.get("judged") is True:
            report["problems"].append("[coverage] %s 标 judged=true 但 appraisals 为空" % aid)

        # ---- B. 解读分级一致 ----
        for j, a in enumerate(aps):
            jd = a.get("judgment")
            g_exp = rules["grade_map"].get(jd) if rules else None
            g_ok = (g_exp == a.get("grade")) if rules else None
            add(per_appraisal(i, j, "grade_consistency"), "grade == grade_map[judgment]",
                not off("grading"), bool(g_ok) if rules else None)
            if not off("grading") and rules and g_exp != a.get("grade"):
                report["problems"].append("[grading] %s/%s grade=%r 与 grade_map[%s]=%r 不符（分级口径漂移）"
                                          % (aid, a.get("checklist_id"), a.get("grade"), jd, g_exp))
            if not off("grading") and rules and jd in NEG and \
                    a.get("bias_direction") not in ("favors_conclusion", "against_conclusion", "unclear"):
                report["problems"].append("[grading] %s/%s 负面判定但 bias_direction 缺失/非法: %r"
                                          % (aid, a.get("checklist_id"), a.get("bias_direction")))
            if not off("grading") and rules and jd in NEG and not checklist_id_ok(a.get("checklist_id")):
                report["problems"].append("[grading] %s checklist_id 非法: %r（须形如 DQ-01，不做 isalpha 判定）"
                                          % (aid, a.get("checklist_id")))
        # 结论强度 vs 设计类型允许强度（过强结论降级）
        if not off("grading") and rules:
            r = rollup(ana, rules)
            allowed = r["strength_allowed"] if r else None
            cs = claim.get("claim_strength")
            if cs and allowed and cs in STRENGTH_ORDER and allowed in STRENGTH_ORDER:
                ok = STRENGTH_ORDER[cs] <= STRENGTH_ORDER[allowed]
                add("analyses[%d].strength_match" % i, "claim_strength ≤ strength_map[design_type]",
                    True, ok)
                if not ok:
                    report["problems"].append("[grading] %s 结论过强：claim_strength=%s 超过 design_type=%s 允许的 %s（须降级）"
                                              % (aid, cs, ana.get("design_type"), allowed))

        # ---- C. 数值与证据回证 ----
        for j, a in enumerate(aps):
            jd = a.get("judgment")
            q_needed = jd in POS_QUOTE
            q = a.get("evidence_quote")
            ok = True
            if not off("evidence"):
                if q_needed and not str(q or "").strip():
                    report["problems"].append("[evidence] %s/%s judgment=%s 但 evidence_quote 为空"
                                              % (aid, a.get("checklist_id"), jd))
                    ok = False
                if not str(a.get("rationale") or "").strip() and jd != "not_applicable":
                    report["problems"].append("[evidence] %s/%s rationale 为空（每条判断须附理由）"
                                              % (aid, a.get("checklist_id")))
                    ok = False
                if str(q or "").strip():
                    backed = quote_backed(q, aid) or quote_backed(q, "*")
                    in_src = quote_in_source(q) if doc_index else True
                    if not backed:
                        report["problems"].append("[evidence] %s/%s 的 evidence_quote 在 claims 证据链中无逐字回证"
                                                  % (aid, a.get("checklist_id")))
                        report["unbacked_evidence"].append(
                            {"item": per_appraisal(i, j, "evidence_quote"), "reason": "claims 无回证"})
                        ok = False
                    if doc_index and not in_src:
                        report["problems"].append("[evidence] %s/%s 的 evidence_quote 在 case.json 来源文本中不存在（不得转述或编造）"
                                                  % (aid, a.get("checklist_id")))
                        report["unbacked_evidence"].append(
                            {"item": per_appraisal(i, j, "evidence_quote"), "reason": "来源文本无此句"})
                        ok = False
                elif q_needed:
                    add(per_appraisal(i, j, "evidence_backed"), "quote 非空且逐字回证", not off("evidence"), False)
                    continue
            add(per_appraisal(i, j, "evidence_backed"), "quote 非空且逐字回证", not off("evidence"), ok)

        # ---- D. 缺陷分类一致 ----
        for j, a in enumerate(aps):
            jd = a.get("judgment")
            c_exp = rules["category_map"].get(jd) if rules else None
            c_ok = (c_exp == a.get("category")) if rules else None
            add(per_appraisal(i, j, "category_consistency"), "category == category_map[judgment]",
                not off("defect"), bool(c_ok) if rules else None)
            if not off("defect") and rules and c_exp != a.get("category"):
                report["problems"].append("[defect] %s/%s category=%r 与 category_map[%s]=%r 不符"
                                          % (aid, a.get("checklist_id"), a.get("category"), jd, c_exp))
            if not off("defect") and rules and jd == "inadequate" and a.get("category") == "reporting_gap":
                report["problems"].append("[defect] %s/%s 判 inadequate 却归 reporting_gap（方法误用≠报告不全）" % (aid, a.get("checklist_id")))
            if not off("defect") and rules and jd == "unreported" and a.get("category") == "method_error":
                report["problems"].append("[defect] %s/%s 判 unreported 却归 method_error（报告不全≠方法误用）" % (aid, a.get("checklist_id")))

        # ---- E. 统计量复算一致 ----
        st = per_stat.get(aid)
        if not off("recompute"):
            if st is None:
                add("analyses[%d].stat_recompute" % i, "stat_recompute 覆盖本组", True, False)
                report["problems"].append("[recompute] %s 在 stat_recompute.per_dataset 缺失（stat_recompute.py 未跑或漏组）" % aid)
            else:
                ok = st.get("match") is not False and st.get("status") != "error"
                add("analyses[%d].stat_recompute" % i, "claimed 统计量与复算一致（容差内）", True, ok)
                if st.get("status") == "error":
                    report["problems"].append("[recompute] %s 复算异常: %s" % (aid, str(st.get("note"))[:120]))
                elif st.get("match") is False:
                    report["problems"].append("[recompute] %s claimed 统计量与原始数据复算不符: %s"
                                              % (aid, json.dumps(st.get("diffs") or {}, ensure_ascii=False)[:160]))
                # 现场比对：claimed vs 落盘复算值（防止 stat_recompute 跑后 claimed 被改动）
                rec = st.get("recomputed") or {}
                if rec and st.get("status") == "ok":
                    tol = float(stat_rc.get("tolerance") or 1e-6)
                    cm = claimed_map(ana)
                    bad = [k for k, rv in rec.items()
                           if cm.get(k) is not None and _is_num(cm[k]) and _is_num(rv)
                           and not rel_diff_ok(cm[k], rv, tol)]
                    ok2 = not bad
                    add("analyses[%d].stat_live_diff" % i, "claimed 与落盘复算值现场比对一致", True, ok2)
                    if bad:
                        report["problems"].append("[recompute] %s claimed 与 stat_recompute 复算值不符: %s（容差 %g）"
                                                  % (aid, ",".join(bad), tol))
                tc = st.get("test_check") or {}
                if tc.get("method_mismatch"):
                    report["problems"].append("[recompute] %s 检验选择与假设不符（期望 %s/%s，登记 %s/%s）"
                                              % (aid, tc.get("expected_family"), ",".join(tc.get("expected_names") or []),
                                                 (ana.get("test_registration") or {}).get("test_family"),
                                                 (ana.get("test_registration") or {}).get("test_name")))

        # ---- F. 因果表述约束 ----
        if not off("causal") and rules:
            verbs = [str(v) for v in (rules.get("causal_verbs") or [])]
            text_low = str(claim.get("text") or "").lower()
            found = [v for v in verbs if v.lower() in text_low]
            observational = str(ana.get("design_type")) in ("observational", "correlational", "quasi_experimental")
            ok = not (observational and found)
            add("analyses[%d].causal_constraint" % i, "观察性/相关性设计不得使用因果动词", True, ok)
            if not ok:
                report["problems"].append("[causal] %s design_type=%s 但 claim 命中因果动词 %s（相关≠因果）"
                                          % (aid, ana.get("design_type"), ",".join(found)))
            if per_interp:
                ip = per_interp.get(aid)
                if ip is not None and ip.get("causal_ok") is False and ok:
                    report["problems"].append("[causal] %s interpret_summary.causal_ok=false 但校验层独立扫描未见违规（两实现不一致）" % aid)

        # ---- G. 弃权登记 ----
        for j, a in enumerate(aps):
            if a.get("judgment") == "unassessable":
                reg = [p for p in pending_reg if str(p.get("analysis_id")) == aid
                       and str(p.get("checklist_id")) == str(a.get("checklist_id"))]
                ok = bool(reg) and all(str(p.get("reason") or "").strip() for p in reg) \
                     and all(str(p.get("needed_action") or "").strip() for p in reg)
                add(per_appraisal(i, j, "pending_registered"), "unassessable ⇒ 登记 pending_review",
                    not off("pending"), ok)
                if not off("pending") and not ok:
                    report["problems"].append("[pending] %s/%s 弃权(unassessable)但未登记进 pending_review（缺 reason/needed_action）"
                                              % (aid, a.get("checklist_id")))

        # ---- 汇总复算对照 ----
        if not off("grading") and rules:
            r = rollup(ana, rules)
            stored = per_interp.get(aid)
            if stored is None:
                report["problems"].append("[grading] %s 在 interpret_summary.per_analysis 缺失（interpret_rollup.py 未跑或漏组）" % aid)
            elif r is not None:
                ok = (stored.get("penalty_total") == r["penalty_total"]
                      and stored.get("overall") == r["overall"]
                      and stored.get("overclaim") == r["overclaim"])
                add("analyses[%d].rollup_recompute" % i, "penalty/overall/overclaim 机械复算一致", True, ok)
                if not ok:
                    report["problems"].append("[grading] %s 解读汇总复算不符（期望 penalty=%s overall=%s overclaim=%s，实际 %s/%s/%s）"
                                              % (aid, r["penalty_total"], r["overall"], r["overclaim"],
                                                 stored.get("penalty_total"), stored.get("overall"),
                                                 stored.get("overclaim")))
            # claimed 统计量数字回证
            if not off("evidence") and r is not None:
                _cl = claim_idx.get(aid, []) + claim_idx.get("*", [])
                cnorm = norm(" ".join([norm(c.get("text")) for c in _cl] +
                                      [norm(e.get("quote")) for c in _cl
                                       for e in (c.get("evidence") or [])]))
                for key, v in stat_numbers(ana):
                    if _is_num(v) and not num_backed(v, cnorm):
                        report["unbacked_numbers"].append(
                            {"item": "analyses[%s].%s" % (aid, key), "value": str(v),
                             "reason": "claimed 统计量未出现在该组任何 claim text/evidence quote 中"})
            if not off("evidence") and not claim_idx.get(aid):
                report["problems"].append("[evidence] %s 无任何 claim（每组分析须有可复核的证据链条目）" % aid)

    # ---- 数值回证 FAIL 汇总 ----
    if report["unbacked_numbers"]:
        report["problems"].append("[evidence] 存在 %d 个未回证数字（见 unbacked_numbers）" % len(report["unbacked_numbers"]))
    if report["unbacked_evidence"]:
        report["problems"].append("[evidence] 存在 %d 条不可回证证据（见 unbacked_evidence）" % len(report["unbacked_evidence"]))

    # ---- 覆盖面汇总（始终开启） ----
    cov = inner.get("coverage") or {}
    if cov:
        exp = {"datasets_total": len(analyses),
               "items_total": sum(len(a.get("appraisals") or []) for a in analyses)}
        bad = [k for k, v in exp.items() if isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("[structure] coverage 汇总与实际不符: %s" % bad)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    all_judged = all(a.get("judged") is True and (a.get("appraisals") or [])
                     for a in analyses) if analyses else False
    any_judged = any(a.get("judged") is True and (a.get("appraisals") or []) for a in analyses)
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("[grading] verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "audited" and analyses and not all_judged:
        report["problems"].append("[grading] verdict=audited 但存在未判定/空评分析组")
    if verdict == "partially_audited" and all_judged:
        report["problems"].append("[grading] verdict=partially_audited 但全部分析组已判定（应为 audited）")
    if verdict == "not_audited" and any_judged:
        report["problems"].append("[grading] verdict=not_audited 但存在已判定分析组")
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

    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--rubric", default="/app/work/claim_rules.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | coverage,grading,evidence,defect,recompute,causal,pending 子集")
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
    inner = res.get("result") or {}
    report["gates"].append({"gate": "interpret_output",
                            "state": "enforced" if (inner.get("interpret_summary") or {}).get("per_analysis")
                            else "not_found",
                            "note": "" if (inner.get("interpret_summary") or {}).get("per_analysis")
                            else "interpret_rollup.py 未回写 interpret_summary，下游不得宣称已核对"})
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
