#!/usr/bin/env python3
"""dedupe.py — 机械去重与合并依据登记（sysrev-search-screen）。

对 result.records 做确定性重复检测（与题面"去重"方向对应）：
  1. DOI 归一化后完全一致            → merge_basis=doi_exact（可直接合并）
  2. 标题归一化后完全一致            → merge_basis=title_exact（可直接合并）
  3. 标题相似度 ≥ 0.90（difflib）    → merge_basis=title_similar（疑似重复，
                                        conflicts 登记为 escalated，交人工确认，
                                        不静默合并——防"不同研究因标题相似被误合并"）

归一化规则（防 isalpha 汉字陷阱）：小写 + 去空白 + 去标点；不使用 str.isalpha
判词（汉字 isalpha 为 True 会误伤），统一用正则字符类处理，中英文同一口径。
合并保留规则（确定性）：正式发表(published) > 有 DOI > 标题更长者 > 序号靠前者。

键归属：本脚本只写 records[].duplicate_of / records[].merge_basis，
并向 result.conflicts 追加 kind=duplicate_versions 条目（不碰其他键）。

用法：
    python3 dedupe.py --result /app/output/result.json [--apply] \
        [--report /app/work/dedupe_report.json] [--threshold 0.90]
退出码恒为 0（结论记在报告 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys

PUNCT_RE = re.compile(r"[\s\-_/\\.,;:!?\"'`~()\[\]{}<>@#\$%\^&\*\+=\|，。；：！？、（）【】《》""''·…—]+", re.UNICODE)


def norm_title(s):
    """标题归一化：小写 + 去空白/标点。不使用 isalpha（汉字 isalpha=True 的陷阱）。"""
    return PUNCT_RE.sub("", str(s or "").lower())


def norm_doi(s):
    d = str(s or "").lower().strip()
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", d)
    return d


def detect(records, threshold):
    """返回去重发现列表 [(dup_idx, canon_idx, basis, similarity)]，确定性顺序。"""
    n = len(records)
    titles = [norm_title(r.get("title")) for r in records]
    dois = [norm_doi(r.get("doi")) for r in records if r.get("doi")]
    doi_list = [norm_doi(r.get("doi")) if r.get("doi") else None for r in records]
    seen = []
    for i in range(n):
        if records[i].get("duplicate_of"):
            continue
        for j in range(i + 1, n):
            if records[j].get("duplicate_of"):
                continue
            basis, sim = None, 0.0
            if doi_list[i] and doi_list[j] and doi_list[i] == doi_list[j]:
                basis, sim = "doi_exact", 1.0
            elif titles[i] and titles[j] and titles[i] == titles[j]:
                basis, sim = "title_exact", 1.0
            else:
                if titles[i] and titles[j]:
                    ratio = difflib.SequenceMatcher(None, titles[i], titles[j]).ratio()
                    if ratio >= threshold:
                        basis, sim = "title_similar", round(ratio, 4)
            if basis:
                canon_i, dup_i = rank_canonical(records[i], records[j], i, j)
                seen.append({"duplicate": dup_i, "canonical": canon_i,
                             "merge_basis": basis, "similarity": sim})
    return seen


def rank_canonical(a, b, ia, ib):
    """确定性保留规则：published > 有 DOI > 标题长 > 序号小。返回 (canonical_idx, duplicate_idx)。"""
    def score(rec, idx):
        return (1 if rec.get("venue_type") == "published" else 0,
                1 if rec.get("doi") else 0,
                len(str(rec.get("title") or "")),
                -idx)
    if score(a, ia) >= score(b, ib):
        return ia, ib
    return ib, ia


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--apply", action="store_true",
                        help="把 duplicate_of/merge_basis 写回 records 并登记 conflicts")
        ap.add_argument("--report", default="/app/work/dedupe_report.json")
        ap.add_argument("--threshold", type=float, default=0.90)
        args = ap.parse_args()
    except Exception as e:
        print("[dedupe] 参数解析失败（已降级）: %s" % e)
        return 0

    try:
        if not os.path.exists(args.result):
            print("[dedupe] result.json 不存在: %s（不中断交付）" % args.result)
            _dump(args.report, {"verdict": "FAIL", "problems": ["result.json 不存在"], "pairs": []})
            return 0
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except Exception as e:
        print("[dedupe] result.json 读取失败: %s（不中断交付）" % e)
        _dump(args.report, {"verdict": "FAIL", "problems": ["读取失败: %s" % e], "pairs": []})
        return 0

    problems = []
    records = [r for r in ((res.get("result") or {}).get("records") or []) if isinstance(r, dict)]
    pairs = detect(records, args.threshold)
    for p in pairs:
        print("  pair: dup=%s <- canon=%s  basis=%s  sim=%s"
              % (records[p["duplicate"]].get("record_id"),
                 records[p["canonical"]].get("record_id"),
                 p["merge_basis"], p["similarity"]))

    if args.apply:
        inner = res.get("result") or {}
        conflicts = inner.setdefault("conflicts", [])
        recs_raw = inner.setdefault("records", [])
        have = {str(c.get("kind")) + "|" + ",".join(str(x) for x in (c.get("record_ids") or []))
                for c in conflicts if isinstance(c, dict)}
        for p in pairs:
            dup, canon = records[p["duplicate"]], records[p["canonical"]]
            rid_d, rid_c = str(dup.get("record_id")), str(canon.get("record_id"))
            # 定位真实索引（records 可能被过滤过）
            for raw in recs_raw:
                if str(raw.get("record_id")) == rid_d and not raw.get("duplicate_of"):
                    raw["duplicate_of"] = rid_c
                    raw["merge_basis"] = p["merge_basis"]
                    break
            if p["merge_basis"] == "title_similar":
                resolution = "escalated"
                note = "标题相似（%.2f）疑似重复，须人工确认后才能合并" % p["similarity"]
            else:
                resolution = "merged"
                note = "合并依据=%s（确定性保留规则：published > 有DOI > 标题长 > 序号小）" % p["merge_basis"]
            key = "duplicate_versions|%s,%s" % (rid_d, rid_c)
            if key not in have:
                conflicts.append({"record_ids": [rid_d, rid_c], "kind": "duplicate_versions",
                                  "resolution": resolution,
                                  "arbitration": {"basis": note, "decided_by": "scripts/dedupe.py"},
                                  "evidence": note + "；similarity=%s" % p["similarity"]})
        try:
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
            print("[dedupe] 已写回 %d 组重复判定（--apply）" % len(pairs))
        except Exception as e:
            problems.append("写回 result.json 失败: %s" % e)

    rep = {"verdict": "FAIL" if problems else "PASS", "problems": problems,
           "pairs": [{"duplicate": records[p["duplicate"]].get("record_id"),
                      "canonical": records[p["canonical"]].get("record_id"),
                      "merge_basis": p["merge_basis"], "similarity": p["similarity"]}
                     for p in pairs],
           "threshold": args.threshold, "records_scanned": len(records)}
    _dump(args.report, rep)
    print("[dedupe] 扫描 %d 条题录，发现 %d 组疑似重复（threshold=%.2f）"
          % (len(records), len(pairs), args.threshold))
    for p in problems:
        print("  WARN: %s" % p)
    return 0


def _dump(path, obj):
    if not path:
        return
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[dedupe] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
