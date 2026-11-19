#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（deep-research-loop）。

对 result.json 做四组机械校验（与题面机检点逐项对应）：
  A. plan    计划事前声明：plan.declared_at 非空、子问题编号唯一/证据需求非空、
     依赖引用存在且无环、convergence.rule 已声明、plan_audit.state=declared、
     findings[].sq_ids 与 iterations[].sq_ids_targeted 必须落在计划子问题集合内、
     依赖未满足不得先出结论（depends_on 的子问题须已有结论）。
  B. trace   迭代轮次留痕可回放：iterations 非空、round_id 顺序编号、每轮有
     sq_ids_targeted/queries_run/synthesis_note/artifacts_ref/status、全部结论
     的 source_ids 必须出现在某轮 sources_found 中（检索留痕可回放）、末轮
     next_action 已记录。
  C. evidence 结论-证据对齐：strength/kind 枚举、strength=strong 须 ≥2 个带
     quote+location 的来源、material_fact 须有来源、unverified 不得带来源、
     带来源结论的每条 quote 必须在 claims 证据链逐字回证（空白归一化子串匹配），
     未回证列入 unbacked_numbers 并判 FAIL；divergent_views 双方并陈且有来源。
  D. registry 未决问题登记：unanswered/partially_answered 的子问题必须登记进
     open_questions（含 reason+needed_action）；handling=unresolved 的分歧必须
     指向 open_question_ref。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；plan_audit 归 plan_audit.py，coverage/strength_summary
归 coverage_calc.py，gain_evidence/efficiency 归 gain_probe.py。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--out /app/work/verify_check.json] [--ablate none|all|plan,trace,evidence,registry] [--emit-into]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

STRENGTHS = ("strong", "moderate", "weak", "unverified")
KINDS = ("material_fact", "inference", "uncertain")
ITER_STATUS = ("done", "failed_with_record", "skipped")
HANDLING = ("presented_side_by_side", "weighed", "unresolved")
VERDICTS = ("synthesized", "partially_synthesized", "not_synthesized", "cannot_verify")
GROUPS = ("plan", "trace", "evidence", "registry")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（不做大小写折叠/不用 isalpha，避免中文与数字误伤）。"""
    return re.sub(r"\s+", "", str(s or ""))


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


def find_cycle(sqs):
    ids = [str(s.get("sq_id")) for s in sqs if s.get("sq_id")]
    graph = {}
    for s in sqs:
        sid = str(s.get("sq_id") or "")
        graph[sid] = [str(d) for d in (s.get("depends_on") or []) if str(d) in ids]
    state = {}

    def dfs(n):
        state[n] = 1
        for m in graph.get(n, []):
            if state.get(m) == 1:
                return True
            if state.get(m, 0) == 0 and dfs(m):
                return True
        state[n] = 2
        return False

    return any(dfs(n) for n in graph if state.get(n, 0) == 0)


# ------------------------------------------------------------------ 主分析
def analyze(res, case, ablate="none", case_state="enforced"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    def off(g):
        return ablate == "all" or g in str(ablate).split(",")

    for g in GROUPS:
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    plan = inner.get("plan") or {}
    plan_audit = inner.get("plan_audit") or {}
    sqs = [s for s in (plan.get("sub_questions") or []) if isinstance(s, dict)]
    sq_ids = [str(s.get("sq_id")) for s in sqs if s.get("sq_id")]
    sq_set = set(sq_ids)
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    iterations = [r for r in (inner.get("iterations") or []) if isinstance(r, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    open_qs = [q for q in (inner.get("open_questions") or []) if isinstance(q, dict)]
    divergent = [v for v in (inner.get("divergent_views") or []) if isinstance(v, dict)]
    cov = inner.get("coverage") or {}
    strengths = inner.get("strength_summary") or {}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced"
                            else "case.json 缺失/不可读，下游不得宣称已核对"})
    pa_state = str(plan_audit.get("state") or "missing")
    plan_gate = "enforced" if pa_state == "declared" else "not_found"
    report["gates"].append({"gate": "plan_ledger", "state": plan_gate,
                            "note": "" if plan_gate == "enforced"
                            else "计划未通过 plan_audit 事前审计（state=%s），下游不得宣称已按计划推进" % pa_state})
    trace_gate = "enforced" if iterations and all(str(r.get("artifacts_ref") or "").strip()
                                                  for r in iterations) else "not_found"
    report["gates"].append({"gate": "iteration_replay", "state": trace_gate,
                            "note": "" if trace_gate == "enforced"
                            else "迭代轮次留痕不全（无 artifacts_ref），下游不得宣称过程可回放"})
    chain_gate = "enforced" if claims else "not_found"
    report["gates"].append({"gate": "findings_chain", "state": chain_gate,
                            "note": "" if chain_gate == "enforced"
                            else "claims 证据链为空，结论无法回链，下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启，不属于消融组） ----
    for i, f in enumerate(findings):
        fid = f.get("finding_id") or "findings[%d]" % i
        if f.get("strength") not in STRENGTHS:
            report["problems"].append("%s strength 枚举非法: %r（须 strong/moderate/weak/unverified）"
                                      % (fid, f.get("strength")))
        if f.get("kind") not in KINDS:
            report["problems"].append("%s kind 枚举非法: %r（须 material_fact/inference/uncertain）"
                                      % (fid, f.get("kind")))
    for i, r in enumerate(iterations):
        if r.get("status") is not None and r.get("status") not in ITER_STATUS:
            report["problems"].append("iterations[%d] status 枚举非法: %r" % (i, r.get("status")))
    for i, v in enumerate(divergent):
        if v.get("handling") is not None and v.get("handling") not in HANDLING:
            report["problems"].append("divergent_views[%d] handling 枚举非法: %r" % (i, v.get("handling")))

    # ---- A. 计划事前声明 ----
    add("plan.declared_before_iterations", "plan.declared_at 非空且 convergence.rule 已声明",
        not off("plan"), False)
    if not off("plan"):
        ok_a = bool(str(plan.get("declared_at") or "").strip()) and \
            bool(str((plan.get("convergence") or {}).get("rule") or "").strip())
        report["self_check"][-1]["match"] = ok_a
        if not ok_a:
            report["problems"].append("计划未事前声明（declared_at/convergence.rule 为空）——"
                                      "计划必须在任何检索迭代之前写定")
        if not sqs:
            report["problems"].append("plan.sub_questions 为空（未拆出可独立检索的子问题）")
        seen = set()
        for i, s in enumerate(sqs):
            sid = str(s.get("sq_id") or "sub_questions[%d]" % i)
            add("plan.sub_questions[%d].declared" % i, "sq_id/text/evidence_needs/search_queries 非空",
                not off("plan"),
                bool(str(s.get("text") or "").strip()) and bool(str(s.get("evidence_needs") or "").strip())
                and bool(s.get("search_queries")))
            if sid in seen:
                report["problems"].append("子问题编号重复: %s" % sid)
            seen.add(sid)
            if not str(s.get("evidence_needs") or "").strip():
                report["problems"].append("%s evidence_needs 为空（证据需求未声明）" % sid)
            for d in (s.get("depends_on") or []):
                if str(d) not in sq_set:
                    report["problems"].append("%s depends_on 引用不存在的子问题: %s" % (sid, d))
        if sqs and find_cycle(sqs):
            report["problems"].append("子问题依赖存在环（依赖必须是有向无环图）")
        if pa_state != "declared":
            report["problems"].append("plan_audit.state=%s（计划未通过事前审计）" % pa_state)
        # 对齐：findings/iterations 引用的子问题必须落在计划内
        for i, f in enumerate(findings):
            unknown = [str(x) for x in (f.get("sq_ids") or []) if str(x) not in sq_set]
            add("findings[%d].sq_in_plan" % i, "sq_ids ⊆ 计划子问题集合",
                not off("plan"), not unknown and bool(f.get("sq_ids")))
            if unknown:
                report["problems"].append("%s sq_ids 超出计划子问题集合: %s"
                                          % (f.get("finding_id") or i, unknown))
        for i, r in enumerate(iterations):
            unknown = [str(x) for x in (r.get("sq_ids_targeted") or []) if str(x) not in sq_set]
            add("iterations[%d].sq_in_plan" % i, "sq_ids_targeted ⊆ 计划子问题集合",
                not off("plan"), not unknown)
            if unknown:
                report["problems"].append("iterations[%d] sq_ids_targeted 超出计划集合: %s"
                                          % (i, unknown))
        # 依赖顺序：sq 有结论但其依赖尚无任何结论 → 先出结论
        has_finding = set()
        for f in findings:
            has_finding.update(str(x) for x in (f.get("sq_ids") or []))
        dep_map = {str(s.get("sq_id")): [str(d) for d in (s.get("depends_on") or [])]
                   for s in sqs if s.get("sq_id")}
        for sid in sorted(dep_map):
            for d in dep_map[sid]:
                if sid in has_finding and d not in has_finding:
                    report["problems"].append("依赖未满足先出结论: %s 有结论但依赖 %s 无结论" % (sid, d))
                    break

    # ---- B. 迭代轮次留痕可回放 ----
    trace_ok = not off("trace")
    if not off("trace"):
        if not iterations:
            report["problems"].append("iterations 为空（逐轮检索-综合-缺口迭代无留痕，不可回放）")
        else:
            for i, r in enumerate(iterations):
                exp_id = "R%d" % (i + 1)
                ok_round = str(r.get("round_id") or "") == exp_id
                add("iterations[%d].round_id_sequential" % i, "round_id 顺序编号 %s" % exp_id,
                    True, ok_round)
                if not ok_round:
                    report["problems"].append("iterations[%d].round_id=%r 不符顺序编号（期望 %s）"
                                              % (i, r.get("round_id"), exp_id))
                ok_full = bool(r.get("sq_ids_targeted")) and bool(r.get("queries_run")) \
                    and bool(str(r.get("synthesis_note") or "").strip()) \
                    and bool(str(r.get("artifacts_ref") or "").strip())
                add("iterations[%d].trace_complete" % i,
                    "queries_run/synthesis_note/artifacts_ref/sq_ids_targeted 非空", True, ok_full)
                if not ok_full:
                    trace_ok = False
                    report["problems"].append("iterations[%d] 留痕不全（缺 queries_run/"
                                              "synthesis_note/artifacts_ref/sq_ids_targeted）"
                                              % i)
            last = iterations[-1] or {}
            if not str(last.get("next_action") or "").strip():
                report["problems"].append("末轮 next_action 为空（收敛/继续/截断未记录，无法判断停止依据）")
                trace_ok = False
    trace_srcs = set()
    for r in iterations:
        trace_srcs.update(str(x) for x in (r.get("sources_found") or []))
    for i, f in enumerate(findings):
        srcs = [str(s.get("source_id")) for s in (f.get("sources") or [])
                if isinstance(s, dict) and s.get("source_id")]
        unknown = [x for x in srcs if x not in trace_srcs]
        add("findings[%d].source_in_trace" % i, "来源必须出现在某轮 sources_found", not off("trace"),
            not unknown)
        if unknown and not off("trace"):
            trace_ok = False
            report["problems"].append("%s 来源 %s 未出现在任何迭代轮次的 sources_found（检索留痕缺口）"
                                      % (f.get("finding_id") or i, unknown))
    add("trace.replayable", "迭代轮次留痕完整可回放（留痕齐全 + 来源可回放 + 末轮收敛记录）",
        not off("trace"), trace_ok)

    # ---- C. 结论-证据对齐 ----
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    for i, f in enumerate(findings):
        fid = str(f.get("finding_id") or i)
        srcs = [s for s in (f.get("sources") or []) if isinstance(s, dict)]
        quoted = [s for s in srcs if str(s.get("quote") or "").strip()
                  and str(s.get("location") or "").strip()]
        if not off("evidence"):
            if not str(f.get("text") or "").strip():
                report["problems"].append("%s 结论 text 为空" % fid)
            if not (f.get("sq_ids") or []):
                report["problems"].append("%s sq_ids 为空（结论未对齐子问题）" % fid)
            add("findings[%d].strength_min_sources" % i,
                "strong⇒≥2 带引文来源；moderate⇒≥1；unverified⇒无来源", True,
                (len(quoted) >= 2 if f.get("strength") == "strong"
                 else len(quoted) >= 1 if f.get("strength") == "moderate"
                 else len(srcs) == 0 if f.get("strength") == "unverified" else True))
            if f.get("strength") == "strong" and len(quoted) < 2:
                report["problems"].append("%s strength=strong 但带 quote+location 的来源只有 %d 个（须≥2）"
                                          % (fid, len(quoted)))
            if f.get("strength") == "moderate" and len(quoted) < 1:
                report["problems"].append("%s strength=moderate 但无带 quote 的来源" % fid)
            if f.get("strength") == "unverified" and srcs:
                report["problems"].append("%s strength=unverified 却携带来源（强度标注矛盾）" % fid)
            if f.get("kind") == "material_fact" and not srcs:
                report["problems"].append("%s kind=material_fact 但无来源（材料事实必须回链来源）" % fid)
            # claims 逐字回证
            cl = claim_idx.get(fid) or []
            all_quote_ok = True
            for j, s in enumerate(srcs):
                q = norm(s.get("quote"))
                if not q:
                    continue
                ok_q = any(q in norm(e.get("quote")) for cc in cl for e in (cc.get("evidence") or []))
                if not ok_q:
                    all_quote_ok = False
                    report["problems"].append("%s 来源 %s 的引文在 claims 证据链中无逐字回证"
                                              % (fid, s.get("source_id")))
                    report["unbacked_numbers"].append(
                        {"item": "findings[%d].sources[%d].quote" % (i, j),
                         "value": str(s.get("quote"))[:60],
                         "reason": "结论引文未在 claim evidence 中逐字回证"})
            add("findings[%d].claim_backed" % i, "每条来源引文在 claims 逐字回证", True,
                (all_quote_ok if srcs else True))
    for i, v in enumerate(divergent):
        if not off("evidence"):
            views = [x for x in (v.get("views") or []) if isinstance(x, dict)]
            ok_v = len(views) >= 2 and all(str(x.get("claim") or "").strip()
                                           and (x.get("source_ids") or []) for x in views)
            add("divergent_views[%d].side_by_side" % i, "分歧观点双方并陈且各带来源", True, ok_v)
            if not ok_v:
                report["problems"].append("divergent_views[%d] 未满足并陈要求（双方 claim+source_ids 齐备）" % i)

    # ---- D. 未决问题登记 ----
    per_sq = {}
    for f in findings:
        for sid in (f.get("sq_ids") or []):
            per_sq.setdefault(str(sid), []).append(str(f.get("strength")))
    oq_sq_refs = set()
    for q in open_qs:
        oq_sq_refs.update(str(x) for x in (q.get("related_sq_ids") or []))
    if not off("registry"):
        for sid in sorted(set(sq_ids)):
            sts = per_sq.get(sid, [])
            needs_reg = (not sts) or not any(x in ("strong", "moderate") for x in sts)
            reg = needs_reg and sid in oq_sq_refs
            add("sub_questions.%s.registered" % sid,
                "unanswered/partially ⇒ open_questions 登记", True, reg)
            if needs_reg and not reg:
                report["problems"].append("子问题 %s 无中等及以上强度结论但未登记进 open_questions" % sid)
        for i, q in enumerate(open_qs):
            ok_q = str(q.get("oq_id") or "").strip() and str(q.get("question") or "").strip() \
                and str(q.get("reason") or "").strip() and str(q.get("needed_action") or "").strip()
            add("open_questions[%d].complete" % i, "oq_id/question/reason/needed_action 非空",
                True, bool(ok_q))
            if not ok_q:
                report["problems"].append("open_questions[%d] 缺 oq_id/question/reason/needed_action" % i)
        oq_ids = {str(q.get("oq_id")) for q in open_qs if q.get("oq_id")}
        for i, v in enumerate(divergent):
            if v.get("handling") == "unresolved":
                ref = str(v.get("open_question_ref") or "")
                ok_r = ref in oq_ids
                add("divergent_views[%d].unresolved_registered" % i,
                    "unresolved 分歧 ⇒ 指向 open_questions", True, ok_r)
                if not ok_r:
                    report["problems"].append("divergent_views[%d] handling=unresolved 但未指向有效 open_question_ref" % i)

    # ---- 覆盖面/强度汇总一致性（始终开启） ----
    ans = sum(1 for sid in sq_ids if any(x in ("strong", "moderate") for x in per_sq.get(sid, [])))
    par = sum(1 for sid in sq_ids
              if per_sq.get(sid) and not any(x in ("strong", "moderate") for x in per_sq[sid]))
    una = len(sq_ids) - ans - par
    exp_cov = {"sub_questions_total": len(sq_ids), "answered": ans,
               "partially_answered": par, "unanswered": una,
               "findings_total": len(findings), "iterations_count": len(iterations)}
    if cov:
        bad = [k for k, v in exp_cov.items() if isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("coverage 汇总与实际不符: %s" % bad)
    exp_strength = {k: sum(1 for f in findings if f.get("strength") == k) for k in STRENGTHS}
    if strengths:
        bad2 = [k for k, v in exp_strength.items()
                if isinstance(strengths.get(k), int) and strengths[k] != v]
        if bad2:
            report["problems"].append("strength_summary 与实际结论不符: %s" % bad2)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    n_total = len(sq_ids)
    if verdict == "synthesized" and n_total and ans != n_total:
        report["problems"].append("verdict=synthesized 但 answered(%d) < 子问题总数(%d)" % (ans, n_total))
    if verdict == "partially_synthesized" and not (0 < ans < n_total):
        report["problems"].append("verdict=partially_synthesized 但 answered=%d/total=%d（应 synthesized 或 not）"
                                  % (ans, n_total))
    if verdict == "not_synthesized" and findings:
        report["problems"].append("verdict=not_synthesized 但存在结论 findings")
    if verdict == "cannot_verify" and (not gaps or findings):
        report["problems"].append("verdict=cannot_verify 须 material_gaps 非空且无结论")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in ("success", "partial", "unable_to_determine", "refused"):
        report["problems"].append("run_status.state 枚举非法或缺失: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") \
            and not str(rs.get("reason") or "").strip():
        report["problems"].append("run_status 非 success 但 reason 为空")

    # ---- steps（始终开启） ----
    steps = inner.get("steps") or []
    if not steps:
        report["problems"].append("steps 为空（须给出他人可复跑的步骤记录）")
    elif not any(str(s.get("command") or "").strip() for s in steps if isinstance(s, dict)):
        report["problems"].append("steps 无任何可执行 command")

    # ---- 契约字段（闸门 enforced 时） ----
    if case_state == "enforced":
        for fname in contract_fields(case):
            if isinstance(res, dict) and fname not in res:
                report["problems"].append("缺少 output_contract 字段: %s" % fname)

    if report["unbacked_numbers"]:
        report["problems"].append("存在 %d 处未回证引文（见 unbacked_numbers）" % len(report["unbacked_numbers"]))
    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | plan,trace,evidence,registry 子集")
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

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state)
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
