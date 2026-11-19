#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（xling-lit-recall）。

对 result.json 做五组可消融机械校验 + 恒开基础校验（与题面机检点逐项对应）：
  A. termmap 术语映射有据：每条 term_map 必须有 entry_id/源词/目标词/语种/
     variant_type 枚举/evidence_quote 逐字证据（证据位置可解析时机械核对回证）；
     queries.built_from 引用的 entry_id 必须存在。
  B. cluster 跨语言版本归并：duplicate_of ⇒ clusters 登记 merged/escalated 且
     正本一致；簇成员（非正本）必须指回正本；同题同版疑似精确重复未归并 → 判违规；
     escalated 必须进待复核。
  C. coverage 覆盖矩阵一致：矩阵行集合 = 目标语种 ∪ 已判定记录语种（unknown/other
     除外）；每行 queries_issued = 该语种检索式数、records_found/kept/pending/
     excluded = items 按语种与标签计数；目标语种无检索式又无 gap_note → 判违规。
  D. evidence 理由完备性：已判定条目必有 rationale；keep 必有 evidence_quote；
     keep/pending 的 evidence_quote 必须在 claims 证据链中逐字回证；keep/pending 的
     fused_score 数字必须出现在 claim text/quote 中（**标识符内嵌数字不作回证命中，
     区间端点保留**），未回证数字列入 unbacked_numbers 并判 FAIL。
  E. pending 待复核登记：label=pending 必须登记进 pending_review（含 reason 与
     needed_action）；ambiguities 中 needs_review 的歧义必须进待复核。
  恒开：枚举合法性（含 body_language 必须已登记——目标语种或覆盖矩阵行）、rubric
  事前权重复算排序、coverage 汇总一致性、verdict 一致性、steps 可执行、契约字段。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；gain_evidence / efficiency 归 gain_probe.py，
queries 归 build_queries.py，ranking / fused_score / rank 归 score_rank.py，
其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--rubric /app/work/rubric.json] [--out /app/work/verify_check.json] [--ablate all]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

REL = ("direct", "indirect", "irrelevant")
LAB = ("keep", "pending", "exclude")
CONF = ("high", "medium", "low")
VERSION = ("original", "translation", "abstract_only", "bilingual", "unknown")
VTYPE = ("synonym", "abbreviation", "transliteration", "localized", "variant_spelling")
WK = ("relevance", "crosslang", "recency")
LANG_FREE = {"unknown", "other"}


# ------------------------------------------------------------------ 工具
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（保留大小写：术语与证据逐字比对需要）。"""
    return re.sub(r"\s+", "", str(s or ""))


def weights_ok(rubric):
    w = (rubric or {}).get("weights") or {}
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


def num_backed(value, texts):
    """数字回证：标识符内嵌数字不命中（如 V01 的 01），区间端点保留（如 0.91-0.95）。

    用边界正则：数字前后不得是字母/数字/点/下划线；前后为连字符等分隔符仍算命中
    （保区间端点）。空白已归一。
    """
    s = str(round(float(value), 4))
    try:
        pat = re.compile(r"(?<![0-9A-Za-z_.])" + re.escape(s) + r"(?![0-9A-Za-z])")
    except Exception:
        return False
    return any(pat.search(norm(t)) for t in texts if t)


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


def loc_value(case, location):
    """解析 evidence_location（candidates[i].title|abstract 等常见排布）取原文。"""
    if not isinstance(case, dict):
        return None
    m = re.match(r"^([A-Za-z_]+)\[(\d+)\](?:\.([A-Za-z_]+))?$", str(location or "").strip())
    if not m:
        return None
    arr = case.get(m.group(1))
    if not isinstance(arr, list) or int(m.group(2)) >= len(arr):
        return None
    entry = arr[int(m.group(2))]
    fld = m.group(3)
    if fld is None:
        return entry
    return entry.get(fld) if isinstance(entry, dict) else None


# ------------------------------------------------------------------ 主分析
def analyze(res, case, ablate="none", case_state="enforced", rubric_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ("termmap", "cluster", "coverage", "evidence", "pending"):
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
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    clusters = inner.get("clusters") or []
    term_map = inner.get("term_map") or []
    queries = inner.get("queries") or []
    ambigs = inner.get("ambiguities") or []
    matrix = inner.get("coverage_matrix") or []
    rq = inner.get("research_question") or {}
    targets = [str(x) for x in (rq.get("target_languages") or [])]
    ranking = inner.get("ranking") or {}
    cov = inner.get("coverage") or {}
    rubric = inner.get("rubric") or {}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "rubric_ledger", "state": rubric_state,
                            "note": "" if rubric_state == "enforced" else "/app/work/rubric.json 台账缺失，下游不得宣称已核对"})
    ranking_state = "enforced" if ranking.get("ordered_ids") else "not_found"
    report["gates"].append({"gate": "ranking_recompute", "state": ranking_state,
                            "note": "" if ranking_state == "enforced" else "ranking 未回填（score_rank.py 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（恒开） ----
    for i, it in enumerate(items):
        iid = it.get("item_id") or "items[%d]" % i
        if it.get("relevance") is not None and it.get("relevance") not in REL:
            report["problems"].append("%s relevance 枚举非法: %r（须 direct/indirect/irrelevant）" % (iid, it.get("relevance")))
        if it.get("label") not in LAB:
            report["problems"].append("%s label 枚举非法: %r（须 keep/pending/exclude）" % (iid, it.get("label")))
        if it.get("confidence") is not None and it.get("confidence") not in CONF:
            report["problems"].append("%s confidence 枚举非法: %r" % (iid, it.get("confidence")))
        if it.get("version") not in VERSION:
            report["problems"].append("%s version 枚举非法: %r（须 original/translation/abstract_only/bilingual/unknown）" % (iid, it.get("version")))

    # ---- 语种登记（恒开）：body_language 必须是目标语种 / unknown / other / 覆盖矩阵行 ----
    registered = set(targets) | LANG_FREE | {str(m.get("language")) for m in matrix if isinstance(m, dict) and m.get("language")}
    for i, it in enumerate(items):
        iid = it.get("item_id") or "items[%d]" % i
        bl = it.get("body_language")
        if bl is not None:
            ok = str(bl) in registered
            add("items[%d].language_registered" % i, "语种标注须已登记（目标语种/覆盖矩阵/unknown）", True, ok)
            if not ok:
                report["problems"].append("%s body_language=%r 未登记（既非目标语种也不在覆盖矩阵）——新语种必须先登记，不得静默新增" % (iid, bl))

    # ---- A. 术语映射有据 ----
    entry_ids = set()
    n_term = 0
    for j, e in enumerate(term_map):
        if not isinstance(e, dict):
            continue
        eid = str(e.get("entry_id") or "term_map[%d]" % j)
        entry_ids.add(eid)
        ok = (bool(str(e.get("source_term") or "").strip())
              and bool(str(e.get("target_term") or "").strip())
              and bool(str(e.get("source_lang") or "").strip())
              and bool(str(e.get("target_lang") or "").strip())
              and e.get("variant_type") in VTYPE)
        add("term_map[%d].fields" % j, "术语映射字段齐 + variant_type 枚举合法", not off("termmap"), ok)
        if not off("termmap"):
            if not ok:
                report["problems"].append("%s 术语映射字段缺失或 variant_type 非法（须 %s）" % (eid, "/".join(VTYPE)))
                n_term += 1
            q = str(e.get("evidence_quote") or "").strip()
            if not q:
                report["problems"].append("%s 术语映射无逐字证据（evidence_quote 空）——映射必须有据" % eid)
                n_term += 1
            else:
                src = loc_value(case, e.get("evidence_location"))
                if src is not None and norm(q) not in norm(src):
                    report["problems"].append("%s 的 evidence_quote 在 %s 中无逐字回证" % (eid, e.get("evidence_location")))
                    n_term += 1
    if not off("termmap"):
        for q in queries:
            if not isinstance(q, dict):
                continue
            bad = [str(x) for x in (q.get("built_from") or []) if str(x) not in entry_ids]
            if bad:
                report["problems"].append("%s built_from 引用不存在的 entry_id: %s" % (q.get("query_id"), ",".join(bad)))
                n_term += 1

    # ---- B. 跨语言版本归并 ----
    n_clu = 0
    cluster_by_member = {}
    for c in clusters:
        if not isinstance(c, dict):
            continue
        for mid in (c.get("member_ids") or []):
            cluster_by_member.setdefault(str(mid), []).append(c)
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        dup = it.get("duplicate_of")
        if dup:
            recs = cluster_by_member.get(iid, [])
            resolved = bool(recs) and any(str(c.get("resolution")) in ("merged", "escalated") for c in recs)
            canon_ok = any(str(c.get("canonical_id")) == str(dup) for c in recs)
            ok = resolved and canon_ok
            add("items[%d].cluster_recorded" % i, "duplicate_of ⇒ clusters 登记 merged/escalated 且正本一致", not off("cluster"), ok)
            if not off("cluster") and not ok:
                if not resolved:
                    report["problems"].append("%s 标记 duplicate_of 但 clusters 未登记 merged/escalated 处置" % iid)
                elif not canon_ok:
                    report["problems"].append("%s 的 duplicate_of=%s 与所在簇正本不一致" % (iid, dup))
                n_clu += 1
        # 簇成员（非正本）必须指回正本
        recs = cluster_by_member.get(iid, [])
        for c in recs:
            members = [str(x) for x in (c.get("member_ids") or [])]
            canon = str(c.get("canonical_id") or "")
            if iid != canon and canon in members and not dup:
                if not off("cluster"):
                    report["problems"].append("%s 在簇 %s 中非正本但未设 duplicate_of 指回正本" % (iid, c.get("cluster_id")))
                    n_clu += 1
    # 疑似精确重复未归并（同题同版，机械检测；题面夹具"explicit exact duplicate"）
    if not off("cluster"):
        seen = {}
        for i, it in enumerate(items):
            tk = norm(it.get("title")).casefold()
            ver = str(it.get("version"))
            if not tk:
                continue
            kk = (tk, ver)
            if kk in seen:
                a, b = seen[kk], str(it.get("item_id") or i)
                if not (items[seen[kk]].get("duplicate_of") or it.get("duplicate_of")):
                    report["problems"].append("%s 与 %s 同题同版本（疑似精确重复）但均未归并（duplicate_of 空）——不得重复计数" % (a, b))
                    n_clu += 1
            else:
                seen[kk] = i

    # ---- C. 覆盖矩阵一致 ----
    n_cov = 0
    if not off("coverage"):
        lang_counter = {}
        for it in items:
            bl = str(it.get("body_language") or "")
            if bl and bl not in LANG_FREE:
                lab = str(it.get("label") or "")
                d = lang_counter.setdefault(bl, {"records_found": 0, "kept": 0, "pending": 0, "excluded": 0})
                d["records_found"] += 1
                if lab == "keep":
                    d["kept"] += 1
                elif lab == "pending":
                    d["pending"] += 1
                elif lab == "exclude":
                    d["excluded"] += 1
        qcount = {}
        for q in queries:
            if isinstance(q, dict) and q.get("language"):
                qcount[str(q["language"])] = qcount.get(str(q["language"]), 0) + 1
        expect_langs = set(targets) | set(lang_counter)
        rows = {}
        for m in matrix:
            if isinstance(m, dict) and m.get("language"):
                rows[str(m["language"])] = m
        missing_rows = sorted(expect_langs - set(rows))
        if missing_rows:
            report["problems"].append("coverage_matrix 缺少语种行: %s（每个目标语种与已判定语种都要有一行）" % ",".join(missing_rows))
            n_cov += 1
        for i, (lang, m) in enumerate(sorted(rows.items())):
            exp_q = qcount.get(lang, 0)
            d = lang_counter.get(lang, {"records_found": 0, "kept": 0, "pending": 0, "excluded": 0})
            checks = [("queries_issued", exp_q), ("records_found", d["records_found"]),
                      ("kept", d["kept"]), ("pending", d["pending"]), ("excluded", d["excluded"])]
            ok = all(isinstance(m.get(k), int) and m.get(k) == v for k, v in checks)
            add("coverage_matrix[%d].%s" % (i, lang),
                "矩阵行与检索式数/条目计数机械一致", True, ok)
            if not ok:
                bad = ["%s=%s(期望 %s)" % (k, m.get(k), v) for k, v in checks
                       if not (isinstance(m.get(k), int) and m.get(k) == v)]
                report["problems"].append("coverage_matrix 语种 %s 计数不一致: %s" % (lang, "; ".join(bad)))
                n_cov += 1
            if lang in targets and exp_q == 0 and not str(m.get("gap_note") or "").strip():
                report["problems"].append("目标语种 %s 无检索式且 gap_note 为空——不静默漏语种" % lang)
                n_cov += 1

    # ---- D. 理由完备性 + claims 回证 ----
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    n_evi = 0
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        lab = it.get("label")
        if lab is None:
            continue
        if not off("evidence") and not str(it.get("rationale") or "").strip():
            report["problems"].append("%s 已判定但 rationale 为空（理由完备性）" % iid)
            n_evi += 1
        if not off("evidence") and lab == "keep" and not it.get("criteria_hit"):
            report["problems"].append("%s 标 keep 但未命中任何纳入标准（criteria_hit 空）" % iid)
            n_evi += 1
        if not off("evidence") and lab == "exclude" and not it.get("excluded_by"):
            report["problems"].append("%s 标 exclude 但未命中任何排除标准（excluded_by 空）" % iid)
            n_evi += 1
        if not off("evidence") and lab == "keep" and not str(it.get("evidence_quote") or "").strip():
            report["problems"].append("%s 标 keep 但无摘要证据（evidence_quote 空）" % iid)
            n_evi += 1
        if not off("evidence") and lab in ("keep", "pending"):
            cl = claim_idx.get(iid) or claim_idx.get("items[%d]" % i) or []
            quote = norm(it.get("evidence_quote"))
            q_backed = any(quote and quote in norm(e.get("quote"))
                           for c in cl for e in (c.get("evidence") or [])) if quote else bool(cl)
            if not q_backed:
                report["problems"].append("%s 的 evidence_quote 在 claims 证据链中无逐字回证" % iid)
                n_evi += 1
            if isinstance(it.get("fused_score"), (int, float)):
                texts = [c.get("text") for c in cl] + [e.get("quote") for c in cl
                                                       for e in (c.get("evidence") or [])]
                if not num_backed(it["fused_score"], texts):
                    report["unbacked_numbers"].append(
                        {"item": "items[%d].fused_score" % i, "value": str(round(float(it["fused_score"]), 4)),
                         "reason": "keep/pending 条目 fused_score 未出现在任何 claim text/quote 中"
                                   "（标识符内嵌数字不作回证，区间端点保留）"})

    # ---- E. 待复核登记 ----
    n_pen = 0
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        if it.get("label") == "pending":
            reg = [p for p in pending_reg if str(p.get("item_id")) == iid]
            ok = bool(reg) and all(str(p.get("reason") or "").strip() for p in reg) \
                 and all(str(p.get("needed_action") or "").strip() for p in reg)
            add("items[%d].pending_registered" % i, "pending ⇒ 登记入 pending_review", not off("pending"), ok)
            if not off("pending") and not ok:
                report["problems"].append("%s 标 pending 但未登记进 pending_review（缺 reason/needed_action）" % iid)
                n_pen += 1
    if not off("pending"):
        reg_ids = {str(p.get("item_id")) for p in pending_reg}
        for a in ambigs:
            if not isinstance(a, dict):
                continue
            aid = str(a.get("ambiguity_id") or "")
            if str(a.get("resolution")) == "needs_review" and aid not in reg_ids:
                report["problems"].append("歧义 %s 标 needs_review 但未登记进 pending_review" % aid)
                n_pen += 1
        for c in clusters:
            if isinstance(c, dict) and str(c.get("resolution")) == "escalated":
                for mid in (c.get("member_ids") or []):
                    if str(mid) not in reg_ids:
                        report["problems"].append("簇 %s 处置为 escalated 但成员 %s 未进 pending_review" % (c.get("cluster_id"), mid))
                        n_pen += 1

    # ---- 排序依据可追溯（恒开） ----
    weights = weights_ok(rubric)
    if weights is None:
        report["problems"].append("rubric 权重未事前声明或非法（relevance/crosslang/recency 三项 0-1 数值且合计=1.0，declared_at 必填）")
    else:
        if not (rubric.get("declared_at") or "").strip():
            report["problems"].append("rubric.declared_at 为空（权重须在任何排序前声明）")
        add("rubric.weights_sum", "三项权重合计=1.0", True, True)
        mism = 0
        for i, it in enumerate(items):
            if not it.get("factors"):
                continue
            s = fused(weights, it.get("factors"))
            stored = it.get("fused_score")
            ok = s is not None and isinstance(stored, (int, float)) and abs(s - float(stored)) <= 1e-6
            add("items[%d].fused_recompute" % i, "rubric 权重机械复算", True, ok)
            if not ok:
                mism += 1
                report["problems"].append("%s fused_score 复算不符（期望 %s，实际 %s）"
                                          % (it.get("item_id"), s, stored))
        scored = [(str(it.get("item_id")), fused(weights, it["factors"]),
                   float(it["factors"].get("recency") or 0.0))
                  for it in items if it.get("factors")]
        ordered = [p for p, _s, _r in sorted(scored, key=lambda t: (-t[1], -t[2], t[0]))]
        got_ids = list(ranking.get("ordered_ids") or [])
        if got_ids and got_ids != ordered:
            report["problems"].append("ranking.ordered_ids 与机械复算顺序不一致（期望 %s…）" % ordered[:6])
            add("ranking.order_recompute", "期望顺序逐位对照", True, False)
        else:
            add("ranking.order_recompute", "期望顺序逐位对照", True, True)
        ranks = sorted(it.get("rank") for it in items if isinstance(it.get("rank"), int))
        if got_ids and ranks and ranks != list(range(1, len(ranks) + 1)):
            report["problems"].append("items[].rank 非连续名次序列 %s" % ranks[:8])

    # ---- 覆盖面汇总一致性（恒开） ----
    judged = [it for it in items if it.get("judged") is True]
    lab_count = {k: sum(1 for it in items if it.get("label") == k) for k in LAB}
    if cov:
        exp = {"total_candidates": len(items), "judged_items": len(judged),
               "keep": lab_count["keep"], "pending": lab_count["pending"], "exclude": lab_count["exclude"]}
        bad = [k for k, v in exp.items() if isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("coverage 汇总与实际条目不符: %s" % bad)

    # ---- verdict 一致性（恒开） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "retrieved" and len(judged) != len(items):
        report["problems"].append("verdict=retrieved 但存在未判定条目（judged=false）")
    if verdict == "partially_retrieved" and (not items or len(judged) == len(items)):
        report["problems"].append("verdict=partially_retrieved 但判定进度与之矛盾（全判完应 retrieved，空集应 not_retrieved）")
    if verdict == "not_retrieved" and judged:
        report["problems"].append("verdict=not_retrieved 但存在已判定条目")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in ("success", "partial", "unable_to_determine", "refused"):
        report["problems"].append("run_status.state 枚举非法或缺失: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") and not str(rs.get("reason") or "").strip():
        report["problems"].append("run_status 非 success 但 reason 为空")

    # ---- steps（恒开） ----
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
    report["objective_counts"] = {"termmap": n_term, "cluster": n_clu, "coverage": n_cov,
                                  "evidence": n_evi, "pending": n_pen}
    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--rubric", default="/app/work/rubric.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | termmap,cluster,coverage,evidence,pending 子集")
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
    rub = load_json(args.rubric) if os.path.exists(args.rubric) else None
    rubric_state = "enforced" if isinstance(rub, dict) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state, rubric_state=rubric_state)
    report["gates"].append({"gate": "score_rank_output",
                            "state": "enforced" if ((res.get("result") or {}).get("ranking") or {}).get("ordered_ids")
                            else "not_found",
                            "note": "" if ((res.get("result") or {}).get("ranking") or {}).get("ordered_ids")
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
        print("[verify_check] PASS（ablate=%s，执行检查项 %d 条）"
              % (args.ablate, sum(1 for s in report["self_check"] if s.get("applied"))))
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
