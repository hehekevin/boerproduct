#!/usr/bin/env python3
"""build_queries.py — 逐语种检索式机械构建（xling-lit-recall）。

从 result.json 的 result.term_map 机械展开逐语种检索式：每个目标语种汇集
该语种全部术语（源词按 source_lang、目标词按 target_lang 归位），去重
（大小写折叠）后按字符串序拼成 `"词1" OR "词2"`，写 result.queries[]
（query_id / language / query_string / built_from 引用 entry_id / term_count）。
不引入任何模型判断——检索式完全由有据术语映射机械派生，可独立复核。

**键归属**：本脚本只写 result.queries；其余键一律不碰（多脚本禁写同一键）。

用法：
    python3 build_queries.py --result /app/output/result.json [--dry-run]
退出码恒为 0（结论记在 stdout 与 result.queries，不中断交付）。
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
        print("[build_queries] 写盘失败 %s: %s" % (path, e))
        return False


def key(term):
    """去重键：大小写折叠 + 空白归一（显式字符处理思路，不依赖 isalpha）。"""
    return "".join(str(term or "").split()).casefold()


def build_queries(term_map):
    """从 term_map 机械派生逐语种检索式。返回 (queries, problems)。"""
    problems = []
    buckets = {}  # language -> {term_key: (term, [entry_ids])}
    for i, e in enumerate(term_map or []):
        if not isinstance(e, dict):
            continue
        eid = str(e.get("entry_id") or "entries[%d]" % i)
        pairs = [(e.get("source_lang"), e.get("source_term")),
                 (e.get("target_lang"), e.get("target_term"))]
        for lang, term in pairs:
            if not str(term or "").strip():
                problems.append("%s 术语为空（lang=%r），已跳过该侧" % (eid, lang))
                continue
            if not str(lang or "").strip():
                problems.append("%s 语种为空（term=%r），已跳过该侧" % (eid, term))
                continue
            lang, term = str(lang), str(term)
            b = buckets.setdefault(lang, {})
            if key(term) in b:
                b[key(term)][1].append(eid)
            else:
                b[key(term)] = [term, [eid]]

    queries = []
    for lang in sorted(buckets):
        terms = sorted(buckets[lang].values(), key=lambda tv: tv[0])
        qid = "Q-%s-01" % lang
        queries.append({
            "query_id": qid,
            "language": lang,
            "query_string": " OR ".join('"%s"' % t for t, _ids in terms),
            "built_from": sorted({eid for _t, ids in terms for eid in ids}),
            "term_count": len(terms),
            "built_by": "scripts/build_queries.py（term_map 机械派生）",
            "status": "built",
        })
    return queries, problems


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--dry-run", action="store_true", help="只打印对照，不写盘")
        args = ap.parse_args()
    except Exception as e:
        print("[build_queries] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[build_queries] FAIL: result.json 不存在/不可解析/无 result 对象: %s（不中断交付）"
              % args.result)
        return 0
    term_map = res["result"].get("term_map") or []
    if not term_map:
        print("[build_queries] FAIL: result.term_map 为空——请先在 Step 1 填写有据术语映射；"
              "不虚构检索式。")
        return 0

    queries, problems = build_queries(term_map)
    print("[build_queries] 从 %d 条术语映射机械派生 %d 个语种检索式"
          % (len(term_map), len(queries)))
    for q in queries:
        print("  %s  %s  built_from=%s" % (q["query_id"], q["query_string"][:80],
                                           ",".join(q["built_from"])[:60]))
    for p in problems:
        print("  WARN: %s" % p)
    if not queries:
        print("[build_queries] FAIL: 无可用语种检索式（见 WARN），不写盘。")
        return 0

    if args.dry_run:
        print("[build_queries] dry-run：不写盘。")
        return 0

    changed = copy.deepcopy(res)
    changed["result"]["queries"] = queries
    if save_json(args.result, changed):
        print("[build_queries] 已回写 result.queries → %s" % args.result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[build_queries] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
