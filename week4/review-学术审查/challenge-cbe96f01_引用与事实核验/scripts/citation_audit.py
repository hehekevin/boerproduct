#!/usr/bin/env python3
"""citation_audit.py — 引用标记机械审计（cite-fact-verify 编造引用识别）。

从稿件正文提取引用标记（[n] 编号式与 Author（Year）作者-年份式），与参考文献表
的标记键机械比对，产出三类确定性结果并回写 result.citation_audit：
  markers_in_text      正文出现的全部引用标记
  reference_ids        参考文献表登记的标记键
  fabricated_markers   正文有、参考文献表无（编造引用候选）
  uncited_refs         参考文献表有、正文未引（未引用文献）
扫描结果是机械候选清单，供 Agent 复核与 citation_fabrication 发现对齐；
不直接下"编造"结论，也不改动 findings。校验器（verify_check.py）会把
citation_fabrication 发现的 cite_marker 与本扫描结果比对，防止冒充。

**键归属**：本脚本只写 result.citation_audit 一个键。
退出码恒为 0（结论记在 stdout 与报告，不中断交付）。
用法：
    python3 citation_audit.py --result /app/output/result.json --case /input/case.json --emit-into
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

MANU_KEYS = ("manuscript", "paper", "document", "full_text", "text", "body", "content")
REF_KEYS = ("references", "refs", "bibliography")

BRACKET_RE = re.compile(r"\[(\d{1,3}(?:\s*[,，、]\s*\d{1,3})*)\]")
AUTHOR_YEAR_RE = re.compile(
    r"([A-Z][A-Za-z\-]{1,24})(?:\s*(?:与|and|&)\s*([A-Z][A-Za-z\-]{1,24}))?\s*[（(]\s*((?:19|20)\d{2})\s*[）)]")


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
        print("[citation_audit] 写盘失败 %s: %s" % (path, e))
        return False


def manuscript_root(case):
    if not isinstance(case, dict):
        return None
    for k in MANU_KEYS:
        if isinstance(case.get(k), (dict, list, str)):
            return case[k]
    return {k: v for k, v in case.items() if k != "output_contract"}


def body_text(case):
    """稿件正文文本（剔除参考文献表键，避免把文献表自身计入正文引用）。"""
    root = manuscript_root(case)
    if root is None:
        return ""
    if isinstance(root, str):
        return root
    stripped = {}
    for k, v in (root.items() if isinstance(root, dict) else []):
        if k in REF_KEYS:
            continue
        stripped[k] = v
    buf = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            buf.append(o)

    walk(stripped if stripped else root)
    return "".join(buf)


def extract_text_markers(text):
    """正文引用标记：[n] / [n,m] 展开为单个标记 + Author（Year）作者-年份键。"""
    markers = []
    for m in BRACKET_RE.finditer(text or ""):
        for n in re.split(r"\s*[,，、]\s*", m.group(1)):
            if n.strip():
                markers.append("[%s]" % n.strip())
    for m in AUTHOR_YEAR_RE.finditer(text or ""):
        markers.append("%s_%s" % (m.group(1).upper(), m.group(3)))
    return markers


def extract_ref_keys(refs):
    """参考文献表标记键：优先 ref_id 字段，降级从文献文本中提取。"""
    keys = []
    if not isinstance(refs, list):
        return keys
    for r in refs:
        if isinstance(r, dict):
            rid = str(r.get("ref_id") or "").strip()
            if rid:
                keys.append(rid)
            else:
                keys.extend(extract_text_markers(str(r.get("text") or ""))[:1])
        elif isinstance(r, str):
            keys.extend(extract_text_markers(r)[:1])
    return keys


def refs_list(case):
    root = manuscript_root(case)
    if isinstance(root, dict):
        for k in REF_KEYS:
            if isinstance(root.get(k), list):
                return root[k]
    return []


def audit(res, case):
    text = body_text(case)
    markers = extract_text_markers(text)
    ref_keys = extract_ref_keys(refs_list(case))
    marker_set, ref_set = set(markers), set(ref_keys)
    n_bracket = sum(1 for m in markers if m.startswith("["))
    n_ay = len(markers) - n_bracket
    return {
        "markers_in_text": sorted(marker_set),
        "reference_ids": ref_keys,
        "fabricated_markers": sorted(marker_set - ref_set),
        "uncited_refs": sorted(ref_set - marker_set),
        "marker_style_counts": {"bracket_numeric": n_bracket, "author_year": n_ay},
        "scan_note": "机械比对正文引用标记与参考文献表；fabricated_markers 为编造引用候选，"
                     "须由 Agent 逐条复核后才能写入 findings（facet=citation_fabrication，"
                     "cite_marker 须命中本清单，verify_check 强制）。",
    }


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 citation_audit 回写 result.json 的 result.citation_audit")
        args = ap.parse_args()
    except Exception as e:
        print("[citation_audit] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[citation_audit] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)
    result = audit(res, case if isinstance(case, dict) else {})

    if args.out:
        save_json(args.out, {"citation_audit": result})
    if args.emit_into:
        cur = load_json(args.result)
        if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
            cur["result"]["citation_audit"] = result
            save_json(args.result, cur)

    print("[citation_audit] 正文标记 %d 个 | 参考文献表 %d 条 | 编造候选 %s | 未引用文献 %s"
          % (len(result["markers_in_text"]), len(result["reference_ids"]),
             result["fabricated_markers"] or "无", result["uncited_refs"] or "无"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[citation_audit] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
