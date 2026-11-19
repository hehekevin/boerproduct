#!/usr/bin/env python3
"""classify_engine.py — 机械分类引擎（lit-classify）。

从 result.json 读取事前声明的 result.taxonomy（或 /app/work/taxonomy.json），
对每条条目做机械归类：
  1. 关键词命中打分：节点 keywords 在条目原文（case.json title/abstract 等）
     中做不区分大小写的子串计数，取命中最多的节点为建议路径；margin=前两名
     命中差，给出置信度建议（margin≥2 → high，=1 → medium，0/无命中 → low）。
  2. key_signature 同键判定：优先 DOI（doi:<值>），否则归一化标题+年份，
     否则退回 source_ref；同键条目分组并核对建议路径是否一致。
  3. 写回 result.consistency.key_groups 与 items[].mechanical（建议值，仅供
     Agent 采纳/复核，不直接冒充最终判定）。

**键归属**：本脚本只写 result.consistency 与 items[].mechanical；其余键一律
不碰（多脚本禁写同一键）。中文按原文子串匹配，不用 isalpha 判字（汉字陷阱）。
退出码恒为 0（结论记在 stdout，不中断交付）。
用法：
    python3 classify_engine.py --result /app/output/result.json --case /input/case.json \
        --work-dir /app/work [--dry-run]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from verify_check import load_json, norm, node_ids, source_text  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[classify_engine] 无法导入 verify_check: %s" % e)
    sys.exit(0)

CANDIDATE_KEYS = ("files", "documents", "records", "items", "materials",
                  "papers", "entries", "literature", "corpus", "results")


def save_json(path, obj):
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        print("[classify_engine] 写盘失败 %s: %s" % (path, e))
        return False


def flatten_nodes(taxonomy):
    """展开全部节点：[{node_id, path, dim_id, keywords}]。"""
    out = []
    for dim in (taxonomy or {}).get("dimensions") or []:
        for nd in (dim or {}).get("nodes") or []:
            if isinstance(nd, dict) and nd.get("node_id"):
                kws = [str(k) for k in (nd.get("keywords") or []) if str(k).strip()]
                out.append({"node_id": str(nd["node_id"]),
                            "path": str(nd.get("path") or nd["node_id"]),
                            "dim_id": str((dim or {}).get("dim_id") or ""),
                            "keywords": kws})
    return out


def keyword_hits(nodes, text):
    """关键词命中计数（两侧空白归一化后子串匹配；中文原样匹配）。

    注意：关键词与文本都先做 norm()（去空白）再比较——带空格的英文词组
    （如 deep learning）在去空白文本中才能命中；不用 isalpha 判字（汉字陷阱）。
    """
    t = norm(text).lower()
    hits = []
    for nd in nodes:
        n = sum(1 for kw in nd["keywords"] if norm(kw).lower() and norm(kw).lower() in t)
        hits.append((nd, n))
    return hits


def confidence_suggest(top, second):
    if top <= 0:
        return "low"
    if top - second >= 2:
        return "high"
    if top - second == 1:
        return "medium"
    return "low"


def key_signature(it, src_text):
    """同键判定键：doi 优先，其次归一化标题+年份，最后 source_ref。"""
    fields = it.get("fields") if isinstance(it.get("fields"), dict) else {}
    doi = str(fields.get("doi") or "").strip()
    if doi:
        return "doi:" + doi.lower()
    title = norm(re.sub(r"[^\w\u4e00-\u9fff]+", "", str(it.get("title") or "")).lower())
    year = str(fields.get("year") or "").strip()
    if title:
        return "title:" + title + ("@" + year if year else "")
    return "ref:" + str(it.get("source_ref") or it.get("item_id") or "")


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--dry-run", action="store_true", help="只打印建议，不写盘")
        args = ap.parse_args()
    except Exception as e:
        print("[classify_engine] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[classify_engine] FAIL: result.json 不存在/不可解析/无 result 对象: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)
    inner = res["result"]

    # 体系来源：result.taxonomy 事前声明优先，其次 /app/work/taxonomy.json
    taxonomy = inner.get("taxonomy") or {}
    if not (taxonomy.get("dimensions") or []):
        tax_file = load_json(os.path.join(args.work_dir or ".", "taxonomy.json"))
        if isinstance(tax_file, dict):
            taxonomy = tax_file
    nodes = flatten_nodes(taxonomy)
    if not nodes:
        print("[classify_engine] FAIL: 分类体系未声明（taxonomy.dimensions 为空）。"
              "必须先在 result.taxonomy 与 /app/work/taxonomy.json 声明多级体系。")
        return 0

    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    mech, groups = {}, {}
    for it in items:
        src = source_text(case if isinstance(case, dict) else {},
                          it.get("source_ref"), str(it.get("item_id") or ""))
        text = src if src is not None else str(it.get("title") or "")
        hits = keyword_hits(nodes, text)
        ranked = sorted(hits, key=lambda t: (-t[1], t[0]["node_id"]))
        top_nd, top_n = ranked[0]
        second_n = ranked[1][1] if len(ranked) > 1 else 0
        suggestion = top_nd["node_id"] if top_n > 0 else None
        mech[str(it.get("item_id"))] = {
            "suggested_path": suggestion,
            "suggested_path_label": top_nd["path"] if top_n > 0 else None,
            "keyword_hits": top_n,
            "margin": top_n - second_n,
            "confidence_suggestion": confidence_suggest(top_n, second_n),
            "note": "机械关键词命中建议，仅供 Agent 采纳/复核；最终判定须引用原文依据",
        }
        key = key_signature(it, text)
        it["_key"] = key
        it["_path"] = suggestion
        groups.setdefault(key, []).append(it)

    key_groups = []
    for key, members in sorted(groups.items()):
        paths = sorted({str(m.get("_path")) for m in members if m.get("_path")})
        key_groups.append({"key": key,
                           "item_ids": [str(m.get("item_id")) for m in members],
                           "suggested_paths": paths,
                           "same": len(paths) <= 1,
                           "rule": "doi > 归一化标题+年份 > source_ref"})

    print("[classify_engine] 体系节点 %d 个（%d 维）| 条目 %d 条 | 同键组 %d 组"
          % (len(nodes), len(taxonomy.get("dimensions") or []), len(items), len(key_groups)))
    for it in items:
        m = mech.get(str(it.get("item_id")) or "") or {}
        print("  %s  建议=%s  hits=%s margin=%s conf=%s key=%s"
              % (it.get("item_id"), m.get("suggested_path"), m.get("keyword_hits"),
                 m.get("margin"), m.get("confidence_suggestion"),
                 str(it.get("_key"))[:48]))
    n_diff = sum(1 for g in key_groups if not g["same"])
    if n_diff:
        print("  WARN: %d 组同键条目建议路径不一致（须 conflicts 登记 merged/escalated）" % n_diff)

    if args.dry_run:
        print("[classify_engine] dry-run：不写盘。")
        return 0

    changed = copy.deepcopy(res)
    ch_inner = changed["result"]
    for it in ch_inner.get("items") or []:
        if isinstance(it, dict):
            it.pop("_key", None)
            it.pop("_path", None)
            m = mech.get(str(it.get("item_id") or ""))
            if m is not None:
                it["mechanical"] = m
    ch_inner["consistency"] = {"key_groups": key_groups,
                               "note": "classify_engine.py 按 key_signature 分组；"
                                       "same=false 的组须在 conflicts 登记处置"}
    if save_json(args.result, changed):
        print("[classify_engine] 已回写 consistency.key_groups / items[].mechanical → %s" % args.result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[classify_engine] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
