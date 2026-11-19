#!/usr/bin/env python3
"""score_rank.py — 相关性打分与确定性排序引擎（sci-file-retrieval）。

从 result.json 读取 result.query_plan.scoring（事前声明的三因子权重）与
result.hits[].factors（仅 label=hit 的条目），机械复算
fused_score = w_term*term_match + w_meta*metadata_match + w_cont*content_match
（保留4位小数），按平局规则（fused_score 降序 → content_match 降序 → hit_id 升序）
**按查询**产出稳定可复现的排序：写 result.ranking.per_query（ordered_hits /
ties / top_k / k_value）与 hits[].fused_score、hits[].rank（查询内名次）。
同分条目全部记入 ties，不静默破坏平局。判定词表匹配用子串/集合运算，
不用 str.isalpha 分词（避免汉字被误判为英文词的陷阱）。

**键归属**：本脚本只写 result.ranking、hits[].fused_score、hits[].rank；
其余键一律不碰（多脚本禁写同一键）。

用法：
    python3 score_rank.py --result /app/output/result.json [--k 10] [--dry-run]
    --dry-run 只打印对照不写盘；--k 为每查询 top-k（缺省取该查询 hit 数）。
退出码恒为 0（结论记在 stdout 与报告，不中断交付）。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys

WEIGHT_KEYS = ("term_match", "metadata_match", "content_match")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path, obj):
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        print("[score_rank] 写盘失败 %s: %s" % (path, e))
        return False


def weights_ok(scoring):
    w = (scoring or {}).get("weights") or {}
    vals = []
    for k in WEIGHT_KEYS:
        v = w.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            return None
        vals.append(float(v))
    if abs(sum(vals) - 1.0) > 1e-6:
        return None
    return vals


def fused(weights, factors):
    """机械融合：返回 round(w·f, 4)；任一因子缺失返回 None。"""
    if not isinstance(factors, dict):
        return None
    vals = []
    for k in WEIGHT_KEYS:
        v = factors.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return None
        vals.append(float(v))
    return round(sum(wi * vi for wi, vi in zip(weights, vals)), 4)


def rank_hits(hits, weights):
    """复算 hit 条目分数 + 按查询确定性排序。返回 (problems, updates, per_query)。"""
    problems, updates = [], {}
    by_q = {}
    for h in hits:
        if not isinstance(h, dict):
            continue
        if h.get("label") != "hit":
            continue
        qid = str(h.get("query_id") or "")
        s = fused(weights, h.get("factors"))
        if s is None:
            problems.append("%s 因子缺失或非法（term_match/metadata_match/"
                            "content_match 须为 0-1 数值）" % h.get("hit_id"))
            continue
        updates[h.get("hit_id")] = {"fused_score": s}
        by_q.setdefault(qid, []).append(
            (str(h.get("hit_id")), s,
             float((h.get("factors") or {}).get("content_match") or 0.0)))

    per_query = []
    for qid in sorted(by_q):
        ordered = sorted(by_q[qid], key=lambda t: (-t[1], -t[2], t[0]))
        ties = {}
        for hid, s, _c in ordered:
            ties.setdefault(s, []).append(hid)
        tie_groups = [{"fused_score": s, "hit_ids": ids,
                       "rule": "content_match 降序 → hit_id 升序"}
                      for s, ids in sorted(ties.items(), reverse=True)
                      if len(ids) > 1]
        ranked, rank_no, prev = [], 0, None
        for i, (hid, s, _c) in enumerate(ordered, 1):
            rank_no = rank_no if prev is not None and s == prev else i
            ranked.append({"hit_id": hid, "fused_score": s, "rank": rank_no})
            prev = s
        per_query.append({"query_id": qid,
                          "ordered_hits": [r["hit_id"] for r in ranked],
                          "ties": tie_groups, "ranked": ranked})
    return problems, updates, per_query


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--k", type=int, default=None,
                        help="每查询 top-k（缺省取该查询 hit 条数）")
        ap.add_argument("--dry-run", action="store_true", help="只打印对照，不写盘")
        args = ap.parse_args()
    except Exception as e:
        print("[score_rank] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[score_rank] FAIL: result.json 不存在/不可解析/无 result 对象: %s"
              "（不中断交付）" % args.result)
        return 0

    inner = res["result"]
    scoring = (inner.get("query_plan") or {}).get("scoring") or {}
    weights = weights_ok(scoring)
    if weights is None:
        print("[score_rank] FAIL: 检索式权重未声明/非法（三因子 0-1 数值且合计=1.0）。"
              "排序前必须先在 result.query_plan 与 /app/work/query_plan.json 事前声明。")
        return 0

    hits = inner.get("hits") or []
    problems, updates, per_query = rank_hits(hits, weights)
    q_hit_count = {}
    for h in hits:
        if isinstance(h, dict) and h.get("label") == "hit":
            q_hit_count[str(h.get("query_id"))] = \
                q_hit_count.get(str(h.get("query_id")), 0) + 1

    ranking_out = []
    for pq in per_query:
        k_value = args.k if args.k is not None else q_hit_count.get(pq["query_id"], 0)
        ranking_out.append({"query_id": pq["query_id"],
                            "ordered_hits": pq["ordered_hits"],
                            "ties": pq["ties"],
                            "top_k": pq["ordered_hits"][:max(k_value, 0)],
                            "k_value": k_value})

    print("[score_rank] 权重 term_match=%.2f metadata_match=%.2f "
          "content_match=%.2f | 已复算 %d 条命中"
          % (weights[0], weights[1], weights[2], len(updates)))
    for pq in per_query:
        print("  query %s：" % pq["query_id"])
        for r in pq["ranked"]:
            print("    #%02d  %s  fused=%s" % (r["rank"], r["hit_id"],
                                               r["fused_score"]))
        if pq["ties"]:
            print("    平局组 %d 组（同分按 content_match 降序、hit_id 升序破平）"
                  % len(pq["ties"]))
    for p in problems:
        print("  WARN: %s" % p)

    if args.dry_run:
        print("[score_rank] dry-run：不写盘。")
        return 0
    if problems and not updates:
        print("[score_rank] FAIL: 无任何命中条目可复算（见 WARN），不写盘。")
        return 0

    changed = copy.deepcopy(res)
    ch_inner = changed["result"]
    for h in ch_inner.get("hits") or []:
        u = updates.get(h.get("hit_id") if isinstance(h, dict) else None)
        if isinstance(h, dict) and u:
            h["fused_score"] = u["fused_score"]
            qid = str(h.get("query_id"))
            rk = next((r["rank"] for pq in per_query if pq["query_id"] == qid
                       for r in pq["ranked"] if r["hit_id"] == h.get("hit_id")),
                      None)
            h["rank"] = rk
    ch_inner["ranking"] = {"per_query": ranking_out,
                           "weights": dict(zip(WEIGHT_KEYS, weights)),
                           "tie_break": (scoring.get("tie_break")
                                         or ["fused_score 降序",
                                             "content_match 降序",
                                             "hit_id 升序"]),
                           "declared_at": scoring.get("declared_at")}
    if save_json(args.result, changed):
        print("[score_rank] 已回写 ranking / fused_score / rank → %s" % args.result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[score_rank] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
