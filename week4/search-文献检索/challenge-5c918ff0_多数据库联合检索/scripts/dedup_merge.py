#!/usr/bin/env python3
"""dedup_merge.py — 多库联合检索去重合并脚本（机械）。
对 responses 各库 records 展平，DOI 精确 + 标题归一化匹配去重，写回 result.duplicates。
退出码恒 0。"""
import argparse, json, os, sys, re

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def norm(s):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", (s or "").lower())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", default="/app/work/dedup.json")
    ap.add_argument("--emit-into", action="store_true")
    args = ap.parse_args()
    try:
        case = load(args.case)
        res = load(args.result)
        result = res.get("result", {}) if isinstance(res.get("result"), dict) else {}
        # 展平所有 records
        all_recs = []
        for resp in case.get("responses", []):
            db = resp.get("db_id", "unknown")
            for r in resp.get("records", []):
                ident = r.get("identifiers", {}) or r
                all_recs.append({
                    "key": f"{db}:{r.get('record_id', r.get('title','')[:20])}",
                    "db": db, "title": r.get("title"), "year": r.get("year"),
                    "doi": ident.get("doi") if isinstance(ident, dict) else r.get("doi"),
                    "authors": r.get("authors") or r.get("author"),
                })

        # 贪心聚类：DOI 精确优先，否则标题归一化+年份
        clusters = []
        used = set()
        for i, a in enumerate(all_recs):
            if i in used: continue
            cluster = [a]
            used.add(i)
            for j, b in enumerate(all_recs):
                if j in used or i == j: continue
                match = None
                if a["doi"] and b["doi"] and a["doi"] == b["doi"]:
                    match = "doi_exact"
                elif a["title"] and norm(a["title"]) == norm(b["title"]) and norm(a["title"]):
                    if a["year"] and b["year"] and a["year"] == b["year"]:
                        match = "title_year_match"
                    else:
                        match = "title_match"
                if match:
                    cluster.append(b)
                    used.add(j)
            if len(cluster) > 1:
                clusters.append({
                    "cluster_id": f"C{len(clusters)+1}",
                    "kept_record": cluster[0]["key"],
                    "duplicate_records": [c["key"] for c in cluster[1:]],
                    "match": "doi_exact" if any(c["doi"] for c in cluster) else "title_match",
                    "basis": f"merge {len(cluster)} records"
                })
        result["duplicates"] = clusters
        result["summary"] = {"raw_total": len(all_recs), "deduped_total": len(all_recs) - sum(len(c["duplicate_records"]) for c in clusters), "clusters": len(clusters)}
        res["result"] = result
        if args.emit_into:
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result["summary"], f, ensure_ascii=False)
        print(json.dumps(result["summary"], ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
    sys.exit(0)

if __name__ == "__main__":
    main()