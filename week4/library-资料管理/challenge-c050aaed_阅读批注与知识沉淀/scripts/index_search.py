#!/usr/bin/env python3
"""index_search.py — 检索索引与主题统计引擎（read-note-harvest，Step 3 必做）。

从 result.json 读取已判定的批注、知识卡片与主题，机械构建可检索索引并产出
主题统计，同时用 --query 演示一次真实检索（命中数、命中条目、召回不足处置），
全部确定性可复现。**关键词切分不使用 str.isalpha()**（汉字 isalpha 返回 True，
会造成中英混切陷阱），改用 ord() 显式区分 ASCII 词 / CJK 二元组。

**键归属**：本脚本只写 result.retrieval 与 result.theme_stats 两个键；
其余键一律不碰（多脚本禁写同一键）。

用法：
    python3 index_search.py --result /app/output/result.json [--query "术语"] [--k 5] [--dry-run]
    --dry-run 只打印对照不写盘。
退出码恒为 0（结论记在 report verdict 字段与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys


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
        print("[index_search] 写盘失败 %s: %s" % (path, e))
        return False


def is_ascii_letter(ch):
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ch.isdigit()


def is_cjk(ch):
    """CJK 统一表意文字区间（不含兼容区，显式码位判断，不用 isalpha）。"""
    o = ord(ch)
    return 0x4E00 <= o <= 0x9FFF


def tokenize(text):
    """确定性切词：连续 ASCII 字母数字 → 词；连续 CJK → 二元组（单字落单保留）。"""
    toks, buf = [], []
    for ch in str(text or ""):
        if is_ascii_letter(ch):
            buf.append(ch.lower())
        else:
            if buf:
                toks.append("".join(buf))
                buf = []
    if buf:
        toks.append("".join(buf))
    cjk_run = []
    for ch in str(text or ""):
        if is_cjk(ch):
            cjk_run.append(ch)
        else:
            if len(cjk_run) >= 2:
                toks.extend("".join(pair) for pair in zip(cjk_run, cjk_run[1:]))
            elif len(cjk_run) == 1:
                toks.append(cjk_run[0])
            cjk_run = []
    if len(cjk_run) >= 2:
        toks.extend("".join(pair) for pair in zip(cjk_run, cjk_run[1:]))
    elif len(cjk_run) == 1:
        toks.append(cjk_run[0])
    return toks


def build_entries(anns, cards):
    """确定性生成检索条目（卡片 + 批注），排序按 ref_id 升序。"""
    entries = []
    for i, c in enumerate(cards):
        entries.append({
            "entry_id": "card-%s" % (c.get("card_id") or i),
            "kind": "card", "ref_id": str(c.get("card_id") or i),
            "text": str(c.get("point") or ""),
            "theme_ids": [str(x) for x in (c.get("theme_ids") or [])],
            "ann_type": None,
            "source_ref": str(c.get("source") or ""),
            "keywords": sorted(set(tokenize(c.get("point")))),
        })
    for i, a in enumerate(anns):
        if a.get("judged") is not True:
            continue
        entries.append({
            "entry_id": "ann-%s" % (a.get("ann_id") or i),
            "kind": "annotation", "ref_id": str(a.get("ann_id") or i),
            "text": str(a.get("note_text") or ""),
            "theme_ids": [],
            "ann_type": a.get("ann_type"),
            "source_ref": str(a.get("locator") or ""),
            "keywords": sorted(set(tokenize(a.get("note_text")))),
        })
    entries.sort(key=lambda e: str(e["entry_id"]))
    return entries


def query_index(entries, query, k):
    """确定性检索：关键词重合计数（无重合计 0），平局按 entry_id 升序。"""
    qtoks = tokenize(query)
    hits = []
    for e in entries:
        overlap = [t for t in qtoks if t in set(e["keywords"])]
        if overlap:
            hits.append({"entry_id": e["entry_id"], "kind": e["kind"],
                         "ref_id": e["ref_id"], "matched_terms": sorted(set(overlap)),
                         "score": len(overlap)})
    hits.sort(key=lambda h: (-h["score"], str(h["entry_id"])))
    top = hits[:max(k, 0)]
    low_recall_note = ("召回不足处置：命中 0 条时须登记进 result.material_gaps 或"
                       "换词重试，不得凭空补条目；误召回由 matched_terms 人工复核。"
                       ) if not top else None
    return {"query": query, "hits_total": len(hits), "top_k": top,
            "k_value": k, "low_recall_note": low_recall_note}


def theme_stats(themes, anns, cards):
    """确定性主题统计：每主题批注数/类型分布/卡片数（归纳规模的机械证据）。"""
    type_of = {str(a.get("ann_id") or i): a.get("ann_type")
               for i, a in enumerate(anns)}
    out = []
    for i, t in enumerate(themes):
        members = [str(x) for x in (t.get("member_anns") or [])]
        dist = {}
        for m in members:
            at = type_of.get(m)
            if at:
                dist[at] = dist.get(at, 0) + 1
        n_cards = sum(1 for c in cards
                      if str(t.get("theme_id")) in [str(x) for x in (c.get("theme_ids") or [])])
        out.append({"theme_id": str(t.get("theme_id") or i),
                    "label": str(t.get("label") or ""),
                    "ann_count": len(members),
                    "type_distribution": dict(sorted(dist.items())),
                    "card_count": n_cards})
    out.sort(key=lambda s: (-s["ann_count"], s["theme_id"]))
    return out


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--query", default=None, help="检索演示查询词（建议取材料核心术语）")
        ap.add_argument("--k", type=int, default=5)
        ap.add_argument("--dry-run", action="store_true", help="只打印对照，不写盘")
        args = ap.parse_args()
    except Exception as e:
        print("[index_search] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[index_search] FAIL: result.json 不存在/不可解析/无 result 对象: %s（不中断交付）"
              % args.result)
        return 0

    inner = res["result"]
    anns = [a for a in (inner.get("annotations") or []) if isinstance(a, dict)]
    cards = [c for c in (inner.get("cards") or []) if isinstance(c, dict)]
    themes = [t for t in (inner.get("themes") or []) if isinstance(t, dict)]

    entries = build_entries(anns, cards)
    stats = theme_stats(themes, anns, cards)

    print("[index_search] 检索条目 %d 条（卡片 %d + 已判定批注 %d）| 主题 %d 个"
          % (len(entries), len(cards),
             sum(1 for e in entries if e["kind"] == "annotation"), len(stats)))
    for s in stats:
        print("  theme %s  %s  ann=%d  cards=%d  types=%s"
              % (s["theme_id"], s["label"][:20], s["ann_count"], s["card_count"],
                 s["type_distribution"]))

    q_demo = None
    if args.query:
        q_demo = query_index(entries, args.query, args.k)
        print("  查询 %r → 命中 %d 条，top：%s" % (args.query, q_demo["hits_total"],
              [h["entry_id"] for h in q_demo["top_k"]]))
        if q_demo["low_recall_note"]:
            print("  %s" % q_demo["low_recall_note"])

    if args.dry_run:
        print("[index_search] dry-run：不写盘。")
        return 0

    changed = copy.deepcopy(res)
    ch_inner = changed["result"]
    ch_inner["retrieval"] = {
        "index_size": len(entries),
        "entries": entries,
        "tokenize_note": "ASCII 词 + CJK 二元组（ord 显式码位判断，不用 isalpha 以避开汉字陷阱）；"
                         "确定性切词，同输入重复运行逐位一致。",
        "recall_policy": "命中 0 条记召回不足（low_recall_note 给出处置）；"
                         "误召回依赖 matched_terms 人工复核；索引只含已判定条目。",
        "query_demo": q_demo,
    }
    ch_inner["theme_stats"] = stats
    if save_json(args.result, changed):
        print("[index_search] 已回写 retrieval / theme_stats → %s" % args.result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[index_search] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
