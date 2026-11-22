#!/usr/bin/env python3
"""coverage_measure.py — 检索覆盖率测量脚本（机械匹配）。
对 reference_set 每条与 retrieved_records 做标识符精确匹配(doi/pmid) + 标题归一化匹配，
计算覆盖/遗漏，写回 result.matches/coverage_metrics。退出码恒 0。"""
import argparse, json, os, sys, re

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def norm_title(s):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", (s or "").lower())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", default="/app/work/coverage.json")
    ap.add_argument("--emit-into", action="store_true")
    args = ap.parse_args()
    try:
        case = load(args.case)
        res = load(args.result)
        result = res.get("result", {}) if isinstance(res.get("result"), dict) else {}

        refset = case.get("reference_set", {})
        refs = refset.get("items", []) if isinstance(refset, dict) else (refset or [])
        retrieved = case.get("retrieved_records", []) or []

        # 建立检索结果标识符索引
        def ids_of(r):
            ident = r.get("identifiers", {}) or {}
            return {"doi": ident.get("doi"), "pmid": ident.get("pmid"), "title": r.get("title"), "year": r.get("year")}

        ret_idx = [ids_of(r) for r in retrieved]

        matches = []
        misses = []
        for ref in refs:
            rid = ref.get("ref_id")
            ri = ids_of(ref)
            hit = None
            basis = None
            # 1) DOI/PMID 精确
            for rr in ret_idx:
                if ri["doi"] and rr["doi"] and ri["doi"] == rr["doi"]:
                    hit = True; basis = "doi_equal"; break
                if ri["pmid"] and rr["pmid"] and ri["pmid"] == rr["pmid"]:
                    hit = True; basis = "pmid_equal"; break
            # 2) 标题归一化
            if not hit:
                for j, rr in enumerate(ret_idx):
                    if norm_title(ri["title"]) == norm_title(rr["title"]) and ri["title"]:
                        if ri["year"] and rr["year"] and ri["year"] == rr["year"]:
                            hit = True; basis = "title_year_equal"; break
                        hit = True; basis = "title_equal"; break
            if hit:
                matches.append({"ref_id": rid, "hit": True, "basis": basis})
            else:
                misses.append({"ref_id": rid, "hit": False})

        total = len(refs)
        hit_n = len(matches)
        miss_n = len(misses)
        coverage = (hit_n / total) if total else None
        result["matches"] = matches
        # 保留缺失引用缺失 reason 待模型补
        existing_misses = {m.get("ref_id") for m in result.get("misses", [])}
        for m in misses:
            if m["ref_id"] not in existing_misses:
                result["misses"] = result.get("misses", []) + [{"ref_id": m["ref_id"], "miss_reason": None, "evidence": ""}]
        result["coverage_metrics"] = {"reference_total": total, "hit": hit_n, "miss": miss_n, "coverage_rate": coverage, "miss_rate": (1 - coverage) if coverage is not None else None}
        res["result"] = result if isinstance(res.get("result"), dict) else res

        if args.emit_into:
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        report = {"reference_total": total, "hit": hit_n, "miss": miss_n, "coverage_rate": coverage}
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False)
        print(json.dumps(report, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
    sys.exit(0)

if __name__ == "__main__":
    main()