#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（trend-frontier-analyst）。

对 result.json 做四组机械校验（与题面机检点逐项对应）：
  A. consistency 主题-归属一致性：judged 条目的 topic_id 须与按事前关键词簇机械
     重算的归属一致；matched_keyword 须属于该簇词表；relevance=irrelevant 不得有
     topic_id；judged 但 topic_id=null 须有 pending_reason 并登记 pending_review；
     representative_ids ⊆ 该主题 item_ids 且代表作有逐字证据。
  B. trend 趋势判定可复算：clustering_policy / trend_policy 须事前声明
     （declared_at 非空、簇非空、window start_year<=end_year）；topics[].yearly_counts、
     early_avg/late_avg、growth_rate、stage 全部按 items + window + 事前阈值机械复算
     逐项对照（growth 容差 1e-3）；0 条目主题 stage 须为 no_evidence。
  C. evidence 证据回证：judged 条目 rationale 非空；core/related 条目须有
     evidence_quote + evidence_location；每主题须有 claims 回证：代表作 evidence_quote
     逐字出现在 claim evidence quote 中（空白归一化子串匹配）、growth_rate 数字与
     stage 出现在 claim text/quote 中，未回证数字列入 unbacked_numbers 判 FAIL；
     gap.status=identified 须有 search_scope 与逐条带 quote 的 exclusion_evidence
     （空白须有排除证据，不得把"没检索到"当空白）。
  D. registry 登记完整性：source_registry 非空且每条目有 source_ref；unassigned
     judged 条目登记 pending_review；coverage 汇总与实际条目一致；extrapolation
     外推边界已登记（rule 非空）；verdict 与判定进度一致；steps 有可执行 command。

**键归属**：本脚本只写 self_check / gates / unbacked_numbers / validator_verdict
四个顶层键；topics / coverage / extrapolation 归 trend_engine.py；
gain_evidence / efficiency 归 gain_probe.py；其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--policy /app/work/trend_policy.json] [--out /app/work/verify_check.json] [--ablate all]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from trend_engine import (STAGES, assign_topic, build_coverage, growth_of,
                              norm_text, stage_of, thresholds_of, year_of,
                              yearly_counts)  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[verify_check] 无法导入 trend_engine: %s" % e)
    sys.exit(0)

REL = ("core", "related", "irrelevant")
CONF = ("high", "medium", "low")
VENUE = ("preprint", "published", "unknown")
VERDICTS = ("analyzed", "partially_analyzed", "not_analyzed", "cannot_verify")


def norm(s):
    """空白归一化（子串回证用，不做大小写折叠以免影响引文语义）。"""
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


def analyze(res, case, ablate="none", case_state="enforced", policy_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ("consistency", "trend", "evidence", "registry"):
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    topics = [t for t in (inner.get("topics") or []) if isinstance(t, dict)]
    gaps = [g for g in (inner.get("gaps") or []) if isinstance(g, dict)]
    pending_reg = inner.get("pending_review") or []
    registry = inner.get("source_registry") or []
    cov = inner.get("coverage") or {}
    clustering = inner.get("clustering_policy") or {}
    trend_policy = inner.get("trend_policy") or {}
    clusters = clustering.get("clusters") or []
    window = trend_policy.get("window") or {}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "policy_ledger", "state": policy_state,
                            "note": "" if policy_state == "enforced" else "/app/work/trend_policy.json 台账缺失，下游不得宣称已核对"})
    topic_state = "enforced" if topics else "not_found"
    report["gates"].append({"gate": "trend_engine_output", "state": topic_state,
                            "note": "" if topic_state == "enforced" else "topics 未回填（trend_engine.py 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启） ----
    for i, it in enumerate(items):
        iid = it.get("item_id") or "items[%d]" % i
        if it.get("relevance") is not None and it.get("relevance") not in REL:
            report["problems"].append("%s relevance 枚举非法: %r（须 core/related/irrelevant）" % (iid, it.get("relevance")))
        if it.get("confidence") is not None and it.get("confidence") not in CONF:
            report["problems"].append("%s confidence 枚举非法: %r" % (iid, it.get("confidence")))
        if it.get("venue_type") not in VENUE:
            report["problems"].append("%s venue_type 枚举非法: %r（须 preprint/published/unknown）" % (iid, it.get("venue_type")))
    for t in topics:
        if t.get("stage") not in STAGES:
            report["problems"].append("topic %s stage 枚举非法: %r（须 emerging/mature/declining/no_evidence）"
                                      % (t.get("topic_id"), t.get("stage")))
    for g in gaps:
        if g.get("status") not in ("identified", "not_verified"):
            report["problems"].append("gap %s status 枚举非法: %r（须 identified/not_verified）"
                                      % (g.get("gap_id"), g.get("status")))

    # ---- A. 主题-归属一致性 ----
    for i, it in enumerate(items):
        iid = it.get("item_id") or "items[%d]" % i
        if it.get("judged") is not True:
            continue
        tid = it.get("topic_id")
        if not off("consistency") and tid:
            exp_tid, exp_kw = assign_topic(it, clusters)
            ok = (exp_tid == str(tid))
            add("items[%d].topic_assignment_recompute" % i, "topic_id 按事前关键词簇机械重算", True, ok)
            if not ok:
                report["problems"].append("%s topic_id=%r 与机械重算 %r 不符（归属不可复算）"
                                          % (iid, tid, exp_tid))
            elif not off("consistency"):
                kws = [str(k) for k in _cluster_keywords(clusters, tid)]
                if it.get("matched_keyword") and it.get("matched_keyword") not in kws:
                    report["problems"].append("%s matched_keyword=%r 不在该簇词表内"
                                              % (iid, it.get("matched_keyword")))
        if not off("consistency") and not tid:
            ok = bool(str(it.get("pending_reason") or "").strip())
            add("items[%d].unassigned_reasoned" % i, "judged 且未归属 ⇒ 有 pending_reason", True, ok)
            if not ok:
                report["problems"].append("%s judged 但 topic_id 为空且无 pending_reason" % iid)
        if not off("consistency") and it.get("relevance") == "irrelevant" and tid:
            report["problems"].append("%s relevance=irrelevant 却有 topic_id=%r（跨级矛盾）" % (iid, tid))

    if not off("consistency"):
        for t in topics:
            member_ids = set(str(x) for x in (t.get("item_ids") or []))
            for rid in (t.get("representative_ids") or []):
                rep = next((it for it in items if str(it.get("item_id")) == str(rid)), None)
                ok = bool(rep) and str(rep.get("topic_id") or "") == str(t.get("topic_id")) \
                     and bool(str(rep.get("evidence_quote") or "").strip())
                add("topic[%s].representative_binding" % t.get("topic_id"),
                    "代表作 ∈ 主题成员且证据齐备", True, ok)
                if not ok:
                    report["problems"].append("topic %s 代表作 %r 绑定失效（不在成员内/无逐字证据）"
                                              % (t.get("topic_id"), rid))

    # ---- B. 趋势判定可复算 ----
    if not off("trend"):
        ok_cl = bool(str(clustering.get("declared_at") or "").strip()) and bool(clusters)
        add("clustering_policy.declared", "聚类口径事前声明（declared_at + 簇非空）", True, ok_cl)
        if not ok_cl:
            report["problems"].append("clustering_policy 未事前声明或 clusters 为空（须在任何判定前声明）")
        ok_tp = bool(str(trend_policy.get("declared_at") or "").strip())
        add("trend_policy.declared", "趋势口径事前声明（declared_at）", True, ok_tp)
        if not ok_tp:
            report["problems"].append("trend_policy.declared_at 为空（阈值/窗口须在任何分级前声明）")
        S, E = window.get("start_year"), window.get("end_year")
        ok_w = isinstance(S, int) and isinstance(E, int) and S <= E
        add("trend_policy.window", "start_year<=end_year 且为整数", True, ok_w)
        if not ok_w:
            report["problems"].append("trend_policy.window 非法: %r" % window)
        em_th, de_th = thresholds_of(trend_policy)
        for ti, t in enumerate(topics):
            tid = str(t.get("topic_id") or ti)
            counts = yearly_counts(items, tid, window) if ok_w else {}
            exp_counts = {str(y): int(counts.get(y, 0)) for y in range(int(S), int(E) + 1)} if ok_w else {}
            got_counts = {str(k): int(v) for k, v in (t.get("yearly_counts") or {}).items()}
            ok_c = ok_w and got_counts == exp_counts
            add("topics[%d].yearly_counts_recompute" % ti, "年度发文量按 items+window 机械复算", True, ok_c)
            if not ok_c:
                report["problems"].append("topic %s yearly_counts 与复算不符（存 %s / 算 %s）"
                                          % (tid, got_counts, exp_counts))
            if ok_w:
                g = growth_of(counts, window)
                gr = t.get("growth_rate")
                ok_g = isinstance(gr, (int, float)) and abs(float(gr) - g["growth_rate"]) <= 1e-3
                add("topics[%d].growth_recompute" % ti, "growth_rate=(late_avg-early_avg)/early_avg 复算", True, ok_g)
                if not ok_g:
                    report["problems"].append("topic %s growth_rate=%r 与复算 %s 不符"
                                              % (tid, gr, g["growth_rate"]))
                ok_e = isinstance(t.get("early_avg"), (int, float)) and isinstance(t.get("late_avg"), (int, float)) \
                       and abs(float(t.get("early_avg")) - g["early_avg"]) <= 1e-3 \
                       and abs(float(t.get("late_avg")) - g["late_avg"]) <= 1e-3
                if not ok_e:
                    report["problems"].append("topic %s early_avg/late_avg 与复算不符" % tid)
                exp_stage = stage_of(g["growth_rate"], em_th, de_th) if t.get("total_count") else "no_evidence"
                ok_s = t.get("stage") == exp_stage
                add("topics[%d].stage_recompute" % ti, "stage 按事前阈值机械复算", True, ok_s)
                if not ok_s:
                    report["problems"].append("topic %s stage=%r 与阈值复算 %r 不符（分级不一致）"
                                              % (tid, t.get("stage"), exp_stage))

    # ---- C. 证据链 + claims 数字回证 ----
    claim_by_topic = {}
    for c in claims:
        claim_by_topic.setdefault(str(c.get("source_id") or ""), []).append(c)
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        if it.get("judged") is not True:
            continue
        if not off("evidence") and not str(it.get("rationale") or "").strip():
            report["problems"].append("%s 已判定但 rationale 为空" % iid)
        if not off("evidence") and it.get("relevance") in ("core", "related"):
            ok = bool(str(it.get("evidence_quote") or "").strip()
                      and str(it.get("evidence_location") or "").strip())
            add("items[%d].quote_location" % i, "core/related ⇒ evidence_quote + location", True, ok)
            if not ok:
                report["problems"].append("%s relevance=%r 但缺 evidence_quote/evidence_location"
                                          % (iid, it.get("relevance")))
        if not off("evidence") and it.get("topic_id"):
            cl = claim_by_topic.get(str(it.get("topic_id"))) or []
            if not cl:
                report["problems"].append("%s 已归属主题 %s 但该主题无 claims 回证" % (iid, it.get("topic_id")))

    if not off("evidence"):
        for ti, t in enumerate(topics):
            tid = str(t.get("topic_id") or ti)
            cl = claim_by_topic.get(tid) or []
            if not cl:
                add("topics[%d].claim_backed" % ti, "每主题须有 claims 回证（证据绑定）", True, False)
                report["problems"].append("topic %s 无 claims 回证（趋势结论缺证据绑定）" % tid)
                continue
            quotes = [norm(e.get("quote")) for c in cl for e in (c.get("evidence") or [])]
            texts = [norm(c.get("text")) for c in cl] + quotes
            miss_reps = []
            for rid in (t.get("representative_ids") or []):
                rep = next((it for it in items if str(it.get("item_id")) == str(rid)), None)
                q = norm((rep or {}).get("evidence_quote"))
                if q and q not in quotes:
                    miss_reps.append(rid)
            add("topics[%d].rep_quote_in_claim" % ti, "代表作 evidence_quote 在 claim 中逐字回证", True,
                not miss_reps)
            for rid in miss_reps:
                report["problems"].append("topic %s 代表作 %s 的证据未在 claims 中逐字回证" % (tid, rid))
            if isinstance(t.get("growth_rate"), (int, float)):
                gstr = str(round(float(t["growth_rate"]), 2))
                backed = any(gstr in tx for tx in texts)
                if not backed:
                    report["unbacked_numbers"].append(
                        {"item": "topics[%d].growth_rate" % ti, "value": gstr,
                         "reason": "主题增速数字未出现在任何 claim text/quote 中"})
            stage_ok = any(norm(t.get("stage")) in tx for tx in texts)
            if not stage_ok:
                report["problems"].append("topic %s 的 stage=%r 未在 claims 中出现（分级结论无回证）"
                                          % (tid, t.get("stage")))

    if not off("evidence"):
        for gi, g in enumerate(gaps):
            gid = str(g.get("gap_id") or gi)
            if g.get("status") == "identified":
                ex = [e for e in (g.get("exclusion_evidence") or []) if isinstance(e, dict)]
                ok = bool(str(g.get("search_scope") or "").strip()) and ex \
                     and all(str(e.get("quote") or "").strip() and str(e.get("source_ref") or "").strip()
                             for e in ex)
                add("gaps[%d].exclusion_evidence" % gi, "空白主张 ⇒ 检索范围 + 排除证据逐条带 quote", True, ok)
                if not ok:
                    report["problems"].append("gap %s 标 identified 但缺 search_scope 或排除证据（"
                                              "不得把检索遗漏当研究空白）" % gid)
            else:
                ok = bool(str(g.get("reason") or "").strip())
                add("gaps[%d].not_verified_reason" % gi, "not_verified ⇒ reason 非空", True, ok)
                if not ok:
                    report["problems"].append("gap %s 标 not_verified 但 reason 为空" % gid)

    # ---- D. 登记完整性 ----
    if not off("registry") and items and not registry:
        report["problems"].append("source_registry 为空（检索范围须登记来源清单）")
    if not off("registry"):
        for i, it in enumerate(items):
            if not str(it.get("source_ref") or "").strip():
                report["problems"].append("%s 缺 source_ref（来源定位）"
                                          % (it.get("item_id") or "items[%d]" % i))
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        if not off("registry") and it.get("judged") is True and not it.get("topic_id"):
            in_reg = any(str(p.get("item_id")) == iid for p in pending_reg if isinstance(p, dict))
            add("items[%d].unassigned_registered" % i, "judged 未归属 ⇒ 登记 pending_review", True, in_reg)
            if not in_reg:
                report["problems"].append("%s judged 但未归属且未登记进 pending_review" % iid)

    extrap = inner.get("extrapolation") or {}
    if not off("registry"):
        ok_x = bool(str(extrap.get("rule") or "").strip()) and isinstance(extrap.get("allowed"), bool)
        add("extrapolation.registered", "趋势外推边界已登记（allowed + rule 非空）", True, ok_x)
        if not ok_x:
            report["problems"].append("extrapolation 未登记外推边界（allowed/rule 缺失）")

    # ---- coverage 一致性（始终开启） ----
    if cov:
        exp = build_coverage(items, topics)
        bad = [k for k, v in exp.items() if v is not None and isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("coverage 汇总与实际条目不符: %s" % bad)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps_field = inner.get("material_gaps") or []
    judged_n = sum(1 for it in items if it.get("judged") is True)
    if verdict == "cannot_verify" and not gaps_field:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "analyzed" and items and judged_n != len(items):
        report["problems"].append("verdict=analyzed 但存在未判定条目（judged=false）")
    if verdict == "partially_analyzed" and items and judged_n == len(items):
        report["problems"].append("verdict=partially_analyzed 但全部条目已判定（应为 analyzed）")
    if verdict == "not_analyzed" and judged_n:
        report["problems"].append("verdict=not_analyzed 但存在已判定条目")
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


def _cluster_keywords(clusters, tid):
    for cl in clusters or []:
        if isinstance(cl, dict) and str(cl.get("topic_id")) == str(tid):
            return cl.get("keywords") or []
    return []


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--policy", default="/app/work/trend_policy.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | consistency,trend,evidence,registry 子集")
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
    pol = load_json(args.policy) if os.path.exists(args.policy) else None
    policy_state = "enforced" if isinstance(pol, dict) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state, policy_state=policy_state)
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


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


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
