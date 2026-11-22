#!/usr/bin/env python3
"""citation_scan.py — 带引用标号结论句候选机械提取（cite-support-check，极简单点）。

从稿件正文定位带引用标号（[n] 编号式或 Author（Year）作者-年份式）的句子，产出
候选结论句清单（candidate_sentences），并与参考文献表机械比对得到引用标记底账
（markers_in_text / reference_ids / unknown_markers）。扫描只产机械候选，供 Agent
逐条判定为 citation_checks；不直接下四档结论，也不改动 findings。

**键归属**：本脚本只写 result.citation_scan 一个键。
退出码恒为 0（结论记在 stdout 与报告，不中断交付）。

用法：
    python3 citation_scan.py --result /app/output/result.json --case /input/case.json --emit-into
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
SENT_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])\s*")


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
        print("[citation_scan] 写盘失败 %s: %s" % (path, e))
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


def extract_markers(text):
    """正文引用标记：[n] 展开单个 + Author（Year）作者-年份键。"""
    markers = []
    for m in BRACKET_RE.finditer(text or ""):
        for n in re.split(r"\s*[,，、]\s*", m.group(1)):
            if n.strip():
                markers.append("[%s]" % n.strip())
    for m in AUTHOR_YEAR_RE.finditer(text or ""):
        markers.append("%s_%s" % (m.group(1).upper(), m.group(3)))
    return markers


def extract_ref_keys(refs):
    keys = []
    if not isinstance(refs, list):
        return keys
    for r in refs:
        if isinstance(r, dict):
            rid = str(r.get("ref_id") or "").strip()
            if rid:
                keys.append(rid)
            else:
                keys.extend(extract_markers(str(r.get("text") or ""))[:1])
        elif isinstance(r, str):
            keys.extend(extract_markers(r)[:1])
    return keys


def refs_list(case):
    root = manuscript_root(case)
    if isinstance(root, dict):
        for k in REF_KEYS:
            if isinstance(root.get(k), list):
                return root[k]
    return []


def section_sentences(case):
    """按章节产出（section_id, section_name, source_ref, 句子列表）。"""
    root = manuscript_root(case)
    out = []
    if isinstance(root, str):
        out.append(("S0", "", "manuscript", root))
        return out
    if isinstance(root, dict):
        for sk in ("sections", "chapters", "parts"):
            v = root.get(sk)
            if isinstance(v, list) and v:
                for i, s in enumerate(v):
                    if isinstance(s, dict):
                        sid = s.get("section_id") or s.get("id") or ("S%d" % (i + 1))
                        name = s.get("name") or s.get("title") or ""
                        text = s.get("text") or s.get("content") or ""
                        src = "manuscript.%s[%d]" % (sk, i)
                        out.append((str(sid), str(name), src, text))
                    elif isinstance(s, str):
                        out.append(("S%d" % (i + 1), "", "manuscript.%s[%d]" % (sk, i), s))
                break
    if not out:
        # 无分段时回退整文，按句拆
        text = body_text(case)
        out.append(("S0", "", "manuscript", text))
    return out


def candidate_sentences(case):
    """带引用标号的句子候选：句子文本 + 命中标记 + 章节位置。"""
    candidates = []
    for sid, name, src, text in section_sentences(case):
        if not text:
            continue
        sentences = [x.strip() for x in SENT_SPLIT_RE.split(text) if x.strip()]
        for j, sent in enumerate(sentences):
            markers = extract_markers(sent)
            if markers:
                candidates.append({
                    "section_id": sid,
                    "section_name": name,
                    "source_ref": src,
                    "sentence_index": j + 1,
                    "location": "%s %s 第 %d 句" % (sid, name or "正文", j + 1),
                    "quote": sent,
                    "markers": sorted(set(markers)),
                })
    return candidates


def scan(res, case):
    text = body_text(case)
    all_markers = extract_markers(text)
    ref_keys = extract_ref_keys(refs_list(case))
    marker_set, ref_set = set(all_markers), set(ref_keys)
    cands = candidate_sentences(case)
    return {
        "candidate_sentences": cands,
        "candidate_count": len(cands),
        "markers_in_text": sorted(marker_set),
        "reference_ids": ref_keys,
        "unknown_markers": sorted(marker_set - ref_set),
        "uncited_refs": sorted(ref_set - marker_set),
        "scan_note": "机械提取带引用标号的结论句候选与引用标记底账；candidate_sentences 供 Agent 逐条判定入 citation_checks；unknown_markers 为正文有、参考文献表无的标记。",
    }


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 citation_scan 回写 result.json 的 result.citation_scan")
        args = ap.parse_args()
    except Exception as e:
        print("[citation_scan] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[citation_scan] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)
    result = scan(res, case if isinstance(case, dict) else {})

    if args.out:
        save_json(args.out, {"citation_scan": result})
    if args.emit_into:
        cur = load_json(args.result)
        if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
            cur["result"]["citation_scan"] = result
            save_json(args.result, cur)

    print("[citation_scan] 候选结论句 %d 条 | 正文标记 %d 个 | 参考文献表 %d 条 | 表外标记 %s | 未引用文献 %s"
          % (len(result["candidate_sentences"]), len(result["markers_in_text"]),
             len(result["reference_ids"]), result["unknown_markers"] or "无",
             result["uncited_refs"] or "无"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[citation_scan] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)