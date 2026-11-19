#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（sci-file-retrieval）。

对 result.json 做四类机械校验（与题面机检点逐项对应）：
  A. 检索式一致性（grounding）：每个 query 在 query_plan.per_query 必须有检索式
     （requirement_mapping 非空）；hit 必须 matched_terms 非空且每一项都在该查询
     的声明词表（keywords+synonyms+content_terms）内；query 声明了
     metadata_filters 时 hit 必须 filters_applied 非空且为声明子集；
     no_hit 必须写 no_match_reason；pending 必须写 pending_reason。
  B. 排序可复算（ranking）：按 query_plan.scoring 事前权重机械复算 fused_score
     与期望顺序，与 hits[].fused_score、ranking.per_query 逐位对照；查询内名次
     连续；平局组须登记。
  C. 证据回证（evidence）：hit 的 evidence_quote 必须逐字（空白归一化后子串）
     出现在 case.json 中该文件的内容字段里；hit/pending 的证据必须在 claims 链
     中有逐字回证；fused_score 数字必须出现在对应 claim text/quote 中，
     未回证数字列入 unbacked_numbers 并判 FAIL。
  D. 登记完备（registry）：label=pending 必须登记进 pending_review（含 reason
     与 needed_action）；某查询 hit 数为 0 必须登记进 no_result_queries（空结果
     登记）；受限文件必须登记进 restricted_files（含 reason）；duplicate_of /
     冲突升级必须登记 conflicts。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；gain_evidence / efficiency 归 gain_probe.py，
ranking / fused_score / rank 归 score_rank.py，其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--query-plan /app/work/query_plan.json] [--out /app/work/verify_check.json] \
        [--ablate all]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

LAB = ("hit", "pending", "no_hit")
REL = ("high", "medium", "low")
CONF = ("high", "medium", "low")
WK = ("term_match", "metadata_match", "content_match")
CONTENT_KEYS = ("content", "content_summary", "summary", "abstract", "text",
                "excerpt", "snippet", "description", "ocr_text", "body", "preview")
FID_KEYS = ("file_id", "doc_id", "id", "uid", "name", "filename", "path")
LIB_KEYS = ("files", "documents", "library", "inventory", "materials",
            "records", "resources", "file_list")


# ------------------------------------------------------------------ 工具
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（保留大小写与汉字原样，不做 isalpha 分词以免汉字陷阱）。"""
    return re.sub(r"\s+", "", str(s or ""))


def weights_ok(scoring):
    w = (scoring or {}).get("weights") or {}
    vals = []
    for k in WK:
        v = w.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            return None
        vals.append(float(v))
    if abs(sum(vals) - 1.0) > 1e-6:
        return None
    return vals


def fused(weights, factors):
    if not isinstance(factors, dict):
        return None
    vals = []
    for k in WK:
        v = factors.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return None
        vals.append(float(v))
    return round(sum(wi * vi for wi, vi in zip(weights, vals)), 4)


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


def build_content_map(case):
    """从 case.json 构造 file 标识 → 归一化内容 的映射（多键兼容，含一层嵌套包装）。"""
    cmap = {}
    if not isinstance(case, dict):
        return cmap
    for key in LIB_KEYS:
        v = case.get(key)
        arrs = []
        if isinstance(v, list):
            arrs.append(v)
        elif isinstance(v, dict):
            arrs.extend(v2 for v2 in v.values() if isinstance(v2, list))
        for arr in arrs:
            for e in arr:
                if not isinstance(e, dict):
                    continue
                content = None
                for ck in CONTENT_KEYS:
                    if e.get(ck):
                        content = str(e[ck])
                        break
                if not content:
                    continue
                nc = norm(content)
                for ik in FID_KEYS:
                    if e.get(ik):
                        cmap.setdefault(str(e[ik]), nc)
                t = e.get("title")
                if t:
                    cmap.setdefault(str(t), nc)
            if cmap:
                break
        if cmap:
            break
    return cmap


def plan_vocab(plan_entry):
    """检索式词表：keywords + synonyms + content_terms（归一化集合）。"""
    vocab = set()
    for k in ("keywords", "synonyms", "content_terms"):
        v = plan_entry.get(k) or []
        if isinstance(v, list):
            vocab.update(norm(x) for x in v if str(x).strip())
    return vocab


# ------------------------------------------------------------------ 主分析
def analyze(res, case, ablate="none", case_state="enforced",
            plan_state="not_found", case_content_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ("grounding", "ranking", "evidence", "registry"):
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    hits = [h for h in (inner.get("hits") or []) if isinstance(h, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = inner.get("pending_review") or []
    no_result = inner.get("no_result_queries") or []
    restricted = inner.get("restricted_files") or []
    conflicts = inner.get("conflicts") or []
    queries = inner.get("queries") or []
    plan = inner.get("query_plan") or {}
    plan_entries = {str(p.get("query_id")): p
                    for p in (plan.get("per_query") or []) if isinstance(p, dict)}
    ranking = inner.get("ranking") or {}
    cov = inner.get("coverage") or {}
    scoring = plan.get("scoring") or {}
    cmap = build_content_map(case) if case else {}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced"
                            else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "query_plan_ledger", "state": plan_state,
                            "note": "" if plan_state == "enforced"
                            else "/app/work/query_plan.json 台账缺失，下游不得宣称已核对"})
    report["gates"].append({"gate": "case_content_verbatim", "state": case_content_state,
                            "note": "" if case_content_state == "enforced"
                            else "case.json 文件内容不可得，逐字回证退化为 claims 链回证，"
                                 "下游不得宣称已对照原文"})
    rk_state = "enforced" if ranking.get("per_query") else "not_found"
    report["gates"].append({"gate": "ranking_recompute", "state": rk_state,
                            "note": "" if rk_state == "enforced"
                            else "ranking 未回填（score_rank.py 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启） ----
    for i, h in enumerate(hits):
        hid = h.get("hit_id") or "hits[%d]" % i
        if h.get("label") not in LAB:
            report["problems"].append("%s label 枚举非法: %r（须 hit/pending/no_hit）"
                                      % (hid, h.get("label")))
        if h.get("relevance") is not None and h.get("relevance") not in REL:
            report["problems"].append("%s relevance 枚举非法: %r（须 high/medium/low）"
                                      % (hid, h.get("relevance")))
        if h.get("confidence") is not None and h.get("confidence") not in CONF:
            report["problems"].append("%s confidence 枚举非法: %r" % (hid, h.get("confidence")))

    # ---- A. 检索式一致性 ----
    n_gnd = 0
    for i, h in enumerate(hits):
        hid = str(h.get("hit_id") or i)
        lab = h.get("label")
        pe = plan_entries.get(str(h.get("query_id")))
        if not off("grounding"):
            ok = bool(pe and norm(pe.get("requirement_mapping")))
            add("hits[%d].plan_declared" % i, "查询已声明检索式且映射有据", True, ok)
            if not ok:
                report["problems"].append("%s 所属查询 %s 未在 query_plan.per_query "
                                          "声明检索式（requirement_mapping 空）"
                                          % (hid, h.get("query_id")))
                n_gnd += 1
            if lab == "hit":
                terms = [norm(t) for t in (h.get("matched_terms") or []) if str(t).strip()]
                ok_t = bool(terms)
                if ok_t and pe:
                    vocab = plan_vocab(pe)
                    ok_t = all(t in vocab for t in terms)
                add("hits[%d].grounding" % i, "hit ⇒ matched_terms 非空且全在声明词表内",
                    True, ok_t)
                if not ok_t:
                    report["problems"].append("%s 标 hit 但 matched_terms 为空或不在 "
                                              "query_plan 声明词表内（检索式无据）" % hid)
                    n_gnd += 1
                ok_q = bool(str(h.get("evidence_quote") or "").strip())
                add("hits[%d].quote_present" % i, "hit ⇒ evidence_quote 非空", True, ok_q)
                if not ok_q:
                    report["problems"].append("%s 标 hit 但 evidence_quote 为空" % hid)
                    n_gnd += 1
                declared_filters = [norm(x) for x in (pe.get("metadata_filters") or [])
                                    ] if pe else []
                applied = [norm(x) for x in (h.get("filters_applied") or [])]
                if declared_filters:
                    ok_f = bool(applied) and all(a in declared_filters for a in applied)
                    add("hits[%d].filters_executed" % i,
                        "声明过滤条件 ⇒ hit 必须执行且为声明子集", True, ok_f)
                    if not ok_f:
                        report["problems"].append("%s 所在查询声明了 metadata_filters，"
                                                  "但该 hit 未执行过滤或超出声明范围" % hid)
                        n_gnd += 1
            if lab == "no_hit" and not str(h.get("no_match_reason") or "").strip():
                report["problems"].append("%s 标 no_hit 但 no_match_reason 为空" % hid)
                n_gnd += 1
            if lab == "pending" and not str(h.get("pending_reason") or "").strip():
                report["problems"].append("%s 标 pending 但 pending_reason 为空" % hid)
                n_gnd += 1

    # ---- B. 排序可复算 ----
    weights = weights_ok(scoring)
    if not off("ranking"):
        if weights is None:
            report["problems"].append("检索式权重未事前声明或非法（三因子 0-1 数值且"
                                      "合计=1.0，declared_at 必填）")
        else:
            if not norm(scoring.get("declared_at")):
                report["problems"].append("query_plan.scoring.declared_at 为空"
                                          "（权重须在任何排序前声明）")
            add("query_plan.weights_sum", "三因子权重合计=1.0", True, True)
        if weights is not None:
            by_q = {}
            for gi, h in enumerate(hits):
                if h.get("label") == "hit" and h.get("factors"):
                    by_q.setdefault(str(h.get("query_id")), []).append((gi, h))
            for pq in (ranking.get("per_query") or []):
                qid = str(pq.get("query_id"))
                qhits = by_q.get(qid) or []
                scored = [(str(h.get("hit_id")), fused(weights, h["factors"]),
                           float((h["factors"] or {}).get("content_match") or 0.0))
                          for _gi, h in qhits]
                exp_order = [p for p, _s, _c in
                             sorted(scored, key=lambda t: (-t[1], -t[2], t[0]))]
                got = list(pq.get("ordered_hits") or [])
                ok = (got == exp_order) if exp_order else bool(got)
                add("ranking.order[%s]" % qid, "期望顺序逐位对照", True, ok)
                if exp_order and got and got != exp_order:
                    report["problems"].append("query %s 的 ordered_hits 与机械复算顺序"
                                              "不一致（期望 %s…）" % (qid, exp_order[:6]))
                mism = 0
                for gi, h in qhits:
                    s = fused(weights, h["factors"])
                    stored = h.get("fused_score")
                    ok_s = s is not None and isinstance(stored, (int, float)) \
                        and abs(s - float(stored)) <= 1e-6
                    add("hits[%d].fused_recompute" % gi, "三因子权重机械复算", True, ok_s)
                    if not ok_s:
                        mism += 1
                        report["problems"].append("%s fused_score 复算不符（期望 %s，实际 %s）"
                                                  % (h.get("hit_id"), s, stored))
                ranks = sorted(h.get("rank") for _gi, h in qhits
                               if isinstance(h.get("rank"), int))
                if got and ranks and ranks != list(range(1, len(ranks) + 1)):
                    report["problems"].append("query %s 的 hits[].rank 非连续名次序列 %s"
                                              % (qid, ranks[:8]))

    # ---- C. 证据回证 ----
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    for i, h in enumerate(hits):
        hid = str(h.get("hit_id") or i)
        lab = h.get("label")
        if lab is None:
            continue
        if not off("evidence") and not str(h.get("rationale") or "").strip():
            report["problems"].append("%s 已判定但 rationale 为空（理由完备性）" % hid)
        if not off("evidence") and lab == "hit":
            cl = claim_idx.get(hid) or []
            quote = norm(h.get("evidence_quote"))
            # C1: 与 case.json 文件内容逐字对照（内容可得时）
            if case_content_state == "enforced":
                fcontent = cmap.get(str(h.get("file_id")))
                if fcontent is not None:
                    ok_c = bool(quote) and quote in fcontent
                    add("hits[%d].quote_in_source" % i, "evidence_quote 逐字出现在"
                        "该文件 case.json 内容中", True, ok_c)
                    if not ok_c:
                        report["problems"].append("%s 的 evidence_quote 未在 case.json "
                                                  "该文件内容中逐字找到（证据不在原文）" % hid)
            # C2: claims 链回证
            q_backed = any(quote and quote in norm(e.get("quote"))
                           for c in cl for e in (c.get("evidence") or [])) \
                if quote else bool(cl)
            add("hits[%d].evidence_backed" % i, "hit 证据在 claims 链逐字回证", True, q_backed)
            if not q_backed:
                report["problems"].append("%s 的 evidence_quote 在 claims 证据链中无逐字回证"
                                          % hid)
            # C3: 分数数字回证
            if isinstance(h.get("fused_score"), (int, float)):
                sstr = str(round(float(h["fused_score"]), 4))
                n_backed = any(sstr in norm(c.get("text")) or sstr in norm(e.get("quote"))
                               for c in cl for e in (c.get("evidence") or []))
                if not n_backed:
                    report["unbacked_numbers"].append(
                        {"item": "hits[%d].fused_score" % i, "value": sstr,
                         "reason": "hit 条目 fused_score 未出现在任何 claim text/quote 中"})

    # ---- D. 登记完备 ----
    for i, h in enumerate(hits):
        hid = str(h.get("hit_id") or i)
        if not off("registry") and h.get("label") == "pending":
            reg = [p for p in pending_reg if isinstance(p, dict)
                   and str(p.get("hit_id")) == hid]
            ok = bool(reg) and all(str(p.get("reason") or "").strip() for p in reg) \
                 and all(str(p.get("needed_action") or "").strip() for p in reg)
            add("hits[%d].pending_registered" % i, "pending ⇒ 登记入 pending_review",
                True, ok)
            if not ok:
                report["problems"].append("%s 标 pending 但未登记进 pending_review"
                                          "（缺 reason/needed_action）" % hid)
        if h.get("duplicate_of"):
            rec = [c for c in conflicts if isinstance(c, dict)
                   and hid in [str(x) for x in (c.get("item_ids") or [])]]
            resolved = bool(rec) and any(str(c.get("resolution")) in ("merged", "escalated")
                                         for c in rec)
            add("hits[%d].conflict_recorded" % i,
                "duplicate_of ⇒ conflicts 登记 merged/escalated", True, resolved)
            if not off("registry") and not resolved:
                report["problems"].append("%s 标记 duplicate_of 但 conflicts 未登记 "
                                          "merged/escalated 处置" % hid)
            if not off("registry") and any(str(c.get("resolution")) == "escalated"
                                           for c in rec):
                if not any(str(p.get("hit_id")) == hid for p in pending_reg
                           if isinstance(p, dict)):
                    report["problems"].append("%s 冲突升级(escalated)但未进入 pending_review"
                                              % hid)

    # 空结果登记：某查询 hit 数为 0 ⇒ no_result_queries 登记
    if not off("registry"):
        for q in queries:
            qid = str(q.get("query_id") if isinstance(q, dict) else q)
            n_hits = sum(1 for h in hits if str(h.get("query_id")) == qid
                         and h.get("label") == "hit")
            if n_hits == 0:
                reg = [r for r in no_result if isinstance(r, dict)
                       and str(r.get("query_id")) == qid]
                ok = bool(reg) and all(str(r.get("reason") or "").strip() for r in reg)
                add("registry.no_result[%s]" % qid, "零命中查询 ⇒ no_result_queries 登记"
                    "（空结果登记）", True, ok)
                if not ok:
                    report["problems"].append("查询 %s 零命中但未登记进 no_result_queries"
                                              "（空结果须登记）" % qid)
        # 受限文件登记
        lib_files = ((inner.get("library") or {}).get("files") or [])
        rids = set()
        for lf in lib_files:
            if isinstance(lf, dict) and lf.get("restricted"):
                rids.add(str(lf.get("file_id")))
        for h in hits:
            if h.get("restricted"):
                rids.add(str(h.get("file_id")))
        for rid in sorted(rids):
            reg = [r for r in restricted if isinstance(r, dict)
                   and str(r.get("file_id")) == rid]
            ok = bool(reg) and all(str(r.get("reason") or "").strip() for r in reg)
            add("registry.restricted[%s]" % rid, "受限文件 ⇒ restricted_files 登记"
                "（含 reason）", True, ok)
            if not ok:
                report["problems"].append("受限文件 %s 未登记进 restricted_files"
                                          "（权限受限须登记，不脑补）" % rid)

    # ---- 覆盖面汇总一致性（始终开启） ----
    judged = [h for h in hits if h.get("judged") is True]
    lab_count = {k: sum(1 for h in hits if h.get("label") == k) for k in LAB}
    if cov:
        exp = {"total_pairs": len(hits), "judged_pairs": len(judged),
               "hit": lab_count["hit"], "pending": lab_count["pending"],
               "no_hit": lab_count["no_hit"]}
        bad = [k for k, v in exp.items() if isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("coverage 汇总与实际条目不符: %s" % bad)
        pq_cov = cov.get("per_query") or {}
        for qid in sorted({str(h.get("query_id")) for h in hits}):
            qh = [h for h in hits if str(h.get("query_id")) == qid]
            got = pq_cov.get(qid) or {}
            exp_q = {"total": len(qh),
                     "hit": sum(1 for h in qh if h.get("label") == "hit"),
                     "pending": sum(1 for h in qh if h.get("label") == "pending"),
                     "no_hit": sum(1 for h in qh if h.get("label") == "no_hit")}
            badq = [k for k, v in exp_q.items()
                    if isinstance(got.get(k), int) and got[k] != v]
            if badq:
                report["problems"].append("coverage.per_query[%s] 与实际不符: %s"
                                          % (qid, badq))

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "searched" and len(judged) != len(hits):
        report["problems"].append("verdict=searched 但存在未判定条目（judged=false）")
    if verdict == "partially_searched" and len(judged) == len(hits) and hits:
        report["problems"].append("verdict=partially_searched 但全部条目已判定"
                                  "（应为 searched）")
    if verdict == "not_searched" and judged:
        report["problems"].append("verdict=not_searched 但存在已判定条目")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in ("success", "partial", "unable_to_determine", "refused"):
        report["problems"].append("run_status.state 枚举非法或缺失: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") \
            and not str(rs.get("reason") or "").strip():
        report["problems"].append("run_status 非 success 但 reason 为空")

    # ---- steps（始终开启） ----
    steps = inner.get("steps") or []
    if not steps:
        report["problems"].append("steps 为空（检索日志须给出他人可重跑的步骤）")
    elif not any(str(s.get("command") or "").strip() for s in steps if isinstance(s, dict)):
        report["problems"].append("steps 无任何可执行 command")

    # ---- 契约字段（闸门 enforced 时） ----
    if case_state == "enforced":
        for fname in contract_fields(case):
            if isinstance(res, dict) and fname not in res:
                report["problems"].append("缺少 output_contract 字段: %s" % fname)

    if report["unbacked_numbers"]:
        report["problems"].append("存在 %d 个未回证数字（见 unbacked_numbers）"
                                  % len(report["unbacked_numbers"]))
    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    report["counters"] = {"grounding_violations": n_gnd}
    return report


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--query-plan", default="/app/work/query_plan.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | grounding,ranking,evidence,registry 子集")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 self_check/gates/unbacked_numbers/validator_verdict "
                             "回写 result.json")
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
    cmap = build_content_map(case if isinstance(case, dict) else {})
    case_content_state = "enforced" if cmap else "not_found"
    qp = load_json(args.query_plan) if os.path.exists(args.query_plan) else None
    plan_state = "enforced" if isinstance(qp, dict) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state,
                     plan_state=plan_state, case_content_state=case_content_state)
    report["gates"].append({"gate": "score_rank_output",
                            "state": "enforced" if ((res.get("result") or {})
                                                    .get("ranking") or {}).get("per_query")
                            else "not_found",
                            "note": "" if ((res.get("result") or {})
                                           .get("ranking") or {}).get("per_query")
                            else "score_rank.py 未回写 ranking，下游不得宣称已核对"})
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
