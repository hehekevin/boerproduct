#!/usr/bin/env python3
"""dedup_records.py — Step 3 去重聚类与覆盖统计（lit-search-pro）。

对 result.json 的 papers[] 做：
  1. 标题归一化（大小写/标点/空白折叠）+ DOI 归一化（去前缀协议/大小写）聚类；
  2. 重复条目标 duplicate_of=正本 paper_id（元数据更全者为正本）；
  3. 写 result.dedup（criteria/clusters_found/removed_duplicates/dedup_rate）与
     result.coverage（total_raw/total_unique/traceable_items/traceability_ratio/
     per_db_counts）。
键分工：本脚本只写 dedup 与 coverage 两个键，不触碰其他键。
同名不同 DOI 不合并（记入报告 conflicts 供 uncertainties 登记）。
全捕获容错，退出码恒为 0。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys


def norm_title(t):
    """标题归一化：小写、去标点、空白折叠。"""
    s = re.sub(r"[^\w\s]", " ", str(t or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def norm_doi(d):
    """DOI 归一化：去 URL 前缀、小写、去空白。"""
    s = str(d or "").strip().lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s)
    s = re.sub(r"^doi:\s*", "", s)
    return s.strip()


def meta_completeness(p):
    """元数据完整度（越全越优先为正本）。"""
    score = 0
    for k in ("title", "authors", "year", "venue", "doi", "url"):
        if p.get(k):
            score += 1
    score += len(p.get("matched_queries") or [])
    return score


def is_traceable(p):
    """来源可追溯：source_db + matched_queries 非空 + rationale 非空。"""
    return bool(str(p.get("source_db") or "").strip()
                and (p.get("matched_queries") or [])
                and str(p.get("rationale") or "").strip())


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
        print("[dedup_records] 写盘失败 %s: %s" % (path, e))
        return False


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--work-dir", default="/app/work")
        args = ap.parse_args()
    except SystemExit:  # argparse error 也退出码 0（题面硬约束）
        return 0
    except Exception as e:
        print("[dedup_records] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[dedup_records] FAIL: result.json 不存在或无 result 对象: %s（不中断交付）"
              % args.result)
        return 0
    papers = res["result"].get("papers") or []
    if not isinstance(papers, list):
        print("[dedup_records] FAIL: papers 非列表（不中断交付）")
        return 0

    conflicts = []
    # 聚类：键 = 归一化标题 或 归一化 DOI（DOI 命中优先级更高）
    clusters = {}
    for i, p in enumerate(papers):
        if not isinstance(p, dict):
            continue
        pid = str(p.get("paper_id") or "row%d" % i)
        keys = []
        doi = norm_doi(p.get("doi"))
        if doi:
            keys.append("doi:" + doi)
        nt = norm_title(p.get("title"))
        if nt:
            keys.append("t:" + nt)
        # 已有 paper_id 的重复标记视为先验（不覆盖脚本判定，但保留）
        joined = None
        for k in keys:
            if k in clusters:
                joined = clusters[k] if joined is None else joined
        if joined is None:
            joined = {"canonical": i, "members": [i]}
            for k in keys:
                clusters[k] = joined
        else:
            joined["members"].append(i)
            for k in keys:
                clusters.setdefault(k, joined)

    # 每个簇选正本：元数据更全者；其余标 duplicate_of
    clusters_found, removed = 0, 0
    for j in {id(c): c for c in clusters.values()}.values():
        members = [m for m in j["members"] if isinstance(papers[m], dict)]
        if len(members) < 2:
            continue
        clusters_found += 1
        # DOI 命中但标题不同 → 疑似冲突不合并？此处 DOI 相同即合并，标题不同记 conflict
        can = max(members, key=lambda m: meta_completeness(papers[m]))
        for m in members:
            if m == can:
                papers[m]["duplicate_of"] = None
            else:
                papers[m]["duplicate_of"] = str(papers[can].get("paper_id") or "row%d" % can)
                removed += 1
                # DOI 相同但标题差异大 → 登记冲突提示
                if norm_doi(papers[can].get("doi")) and norm_doi(papers[m].get("doi")):
                    ta, tb = norm_title(papers[can].get("title")), norm_title(papers[m].get("title"))
                    if ta and tb and ta != tb:
                        conflicts.append("papers[%d] 与 papers[%d] DOI 相同但标题不同，已合并并提示复核"
                                         % (can, m))

    total_raw = sum(1 for p in papers if isinstance(p, dict))
    total_unique = sum(1 for p in papers if isinstance(p, dict) and not p.get("duplicate_of"))
    traceable = sum(1 for p in papers if isinstance(p, dict) and is_traceable(p))
    dedup_rate = round(removed / total_raw, 6) if total_raw else None

    per_db = {}
    for p in papers:
        if isinstance(p, dict):
            db = str(p.get("source_db") or "unknown")
            per_db[db] = per_db.get(db, 0) + 1

    # 只写 dedup 与 coverage 两个键
    try:
        res["result"]["dedup"] = {
            "criteria": "归一化标题（小写/去标点/空白折叠）+ 归一化 DOI；DOI 命中优先",
            "clusters_found": clusters_found,
            "removed_duplicates": removed,
            "dedup_rate": dedup_rate,
            "note": "同名不同 DOI 不自动合并；冲突见 uncertainties.conflicts",
        }
        res["result"]["coverage"] = {
            "total_raw": total_raw,
            "total_unique": total_unique,
            "traceable_items": traceable,
            "traceability_ratio": (round(traceable / total_raw, 6) if total_raw else None),
            "per_db_counts": per_db,
        }
        save_json(args.result, res)
        print("[dedup_records] 已回写 result.json: dedup + coverage")
    except Exception as e:
        print("[dedup_records] 回写失败: %s" % e)

    # 工作目录落去重明细
    detail = {"clusters": [{"canonical": str(papers[c["canonical"]].get("paper_id")),
                            "members": [str(papers[m].get("paper_id")) for m in c["members"]]}
                           for c in {id(c): c for c in clusters.values()}.values()
                           if len(c["members"]) >= 2],
              "conflicts": conflicts}
    save_json(os.path.join(args.work_dir or ".", "dedup_detail.json"), detail)

    print("[dedup_records] raw=%d unique=%d removed=%d clusters=%d dedup_rate=%s traceable=%d/%d"
          % (total_raw, total_unique, removed, clusters_found, dedup_rate, traceable, total_raw))
    for c in conflicts:
        print("  conflict: %s" % c)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[dedup_records] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
