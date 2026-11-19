#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stat_recompute.py — 聚合数值独立复算（不 import query_engine，独立实现过滤与聚合）。
复算：row_count / 聚合值 / 分组守恒（组计数和=总行数，组 sum 和=总体 sum）。
键归属：result.recompute 归本脚本。退出码恒 0。
"""
import argparse, json, os, sys

MARKER = "sci-db-query-analyze-v1"
MISSING_TOKENS = {"", "na", "n/a", "null", "none", "nan", "未知", "缺失"}
TOL = 1e-6


def marker_hit():
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "SKILL.md"), "r", encoding="utf-8") as f:
            return MARKER in f.read()
    except Exception:
        return False


def first_key(d, keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] not in (None, "", []):
            return d[k]
    return default


def is_missing(v):
    return v is None or (isinstance(v, str) and v.strip().lower() in MISSING_TOKENS)


def to_num(v):
    try:
        return None if isinstance(v, bool) else float(v)
    except (TypeError, ValueError):
        return None


def load_rows(case, dataset_id):
    raw = first_key(case, ["datasets", "tables", "snapshots", "data", "sources"], [])
    if isinstance(raw, dict):
        raw = [{"dataset_id": k, **(v if isinstance(v, dict) else {"rows": v})} for k, v in raw.items()]
    for ds in raw if isinstance(raw, list) else []:
        if isinstance(ds, dict) and first_key(ds, ["dataset_id", "id", "name", "table", "table_name"]) == dataset_id:
            rows = first_key(ds, ["rows", "records", "data", "samples"])
            cols = first_key(ds, ["columns", "fields", "schema"]) or []
            if isinstance(rows, dict) and "columns" in rows:
                cols = rows["columns"]; rows = rows.get("rows", [])
            if isinstance(rows, list) and rows and isinstance(rows[0], list):
                if not cols:
                    cols = ["col_%d" % i for i in range(len(rows[0]))]
                rows = [dict(zip(cols, r)) for r in rows]
            return rows or []
    return None


def refilter(rows, filters):
    sel = list(rows)
    for f in (filters or []):
        op, col, tv = f.get("op"), f.get("column"), f.get("value")

        def keep(r):
            v = r.get(col)
            if op == "isnull":
                return is_missing(v)
            if op == "notnull":
                return not is_missing(v)
            if is_missing(v):
                return False
            if op == "in":
                return v in tv if isinstance(tv, list) else v == tv
            if op == "nin":
                return v not in tv if isinstance(tv, list) else v != tv
            if op == "contains":
                return str(tv).lower() in str(v).lower()
            if op == "between":
                nv, n0, n1 = to_num(v), to_num(tv[0]) if isinstance(tv, list) and len(tv) == 2 else None, to_num(tv[1]) if isinstance(tv, list) and len(tv) == 2 else None
                return None not in (nv, n0, n1) and n0 <= nv <= n1
            a, b = to_num(v), to_num(tv)
            if a is None or b is None:
                a, b = str(v), str(tv)
            return {"eq": a == b, "ne": a != b, "gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]
        sel = [r for r in sel if keep(r)]
    return sel


def recompute_agg(fn, col, sub):
    vals = [r.get(col) for r in sub] if (col and col != "*") else sub
    if fn == "count":
        return float(len(vals))
    if fn == "nunique":
        return float(len(set(map(str, [v for v in vals if not is_missing(v)]))))
    nums = [n for n in (to_num(v) for v in vals if not is_missing(v)) if n is not None]
    if fn == "sum":
        return float(sum(nums))
    if fn == "avg":
        return float(sum(nums) / len(nums)) if nums else None
    if fn == "min":
        return min(nums) if nums else None
    if fn == "max":
        return max(nums) if nums else None
    return None


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    try:
        return abs(float(a) - float(b)) <= TOL
    except (TypeError, ValueError):
        return str(a) == str(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", required=True)
    a = ap.parse_args()
    info = {"script": "stat_recompute", "marker_hit": marker_hit(), "exit": 0, "checks": 0, "fails": 0}
    try:
        with open(a.result, "r", encoding="utf-8") as f:
            result = json.load(f)
        with open(a.case, "r", encoding="utf-8") as f:
            case = json.load(f)
        r = result.get("result", {})
        queries = {q.get("query_id"): q for q in (r.get("queries") or [])}
        checks = []
        for qr in (r.get("query_results") or []):
            qid = qr.get("query_id")
            q = queries.get(qid) or {}
            rows = load_rows(case, q.get("dataset_id"))
            if rows is None:
                checks.append({"query_id": qid, "kind": "dataset", "ok": False, "detail": "dataset not found: %s" % q.get("dataset_id")})
                continue
            sel = refilter(rows, q.get("filters"))
            checks.append({"query_id": qid, "kind": "row_count", "ok": close(len(sel), qr.get("row_count")),
                           "detail": "recomputed=%d reported=%s" % (len(sel), qr.get("row_count"))})
            if qr.get("status") != "ok":
                checks.append({"query_id": qid, "kind": "skipped_error_query", "ok": True, "detail": "query status=%s，复算跳过聚合项" % qr.get("status")})
                continue
            for alias, reported in (qr.get("aggregates") or {}).items():
                ok = False
                detail = "alias=%s reported=%s" % (alias, reported)
                for a_ in (q.get("aggregations") or []):
                    if (a_.get("alias") or "%s(%s)" % (a_.get("fn"), a_.get("column"))) == alias:
                        v = recompute_agg(a_.get("fn"), a_.get("column"), sel)
                        ok = close(v, reported)
                        detail += " recomputed=%s" % v
                        break
                checks.append({"query_id": qid, "kind": "aggregate", "ok": ok, "detail": detail})
            gb = q.get("group_by") or []
            if gb and qr.get("groups") is not None:
                gsum = sum(g.get("count", 0) for g in qr["groups"])
                ok1 = close(gsum, len(sel)) and close(gsum, qr.get("row_count"))
                checks.append({"query_id": qid, "kind": "group_conservation_count", "ok": ok1,
                               "detail": "group_count_sum=%d recomputed_rows=%d reported=%s" % (gsum, len(sel), qr.get("row_count"))})
                for a_ in (q.get("aggregations") or []):
                    alias = a_.get("alias") or "%s(%s)" % (a_.get("fn"), a_.get("column"))
                    if a_.get("fn") in ("sum", "count"):
                        gsum_v = sum(to_num(g.get(alias)) or 0.0 for g in qr["groups"])
                        total = recompute_agg(a_.get("fn"), a_.get("column"), sel)
                        ok2 = close(gsum_v, total)
                        checks.append({"query_id": qid, "kind": "group_conservation_%s" % a_.get("fn"), "ok": ok2,
                                       "detail": "group_sum(%s)=%s overall=%s" % (alias, gsum_v, total)})
        r["recompute"] = {"computed_by": "stat_recompute.py", "checks": checks, "all_ok": all(c["ok"] for c in checks)}
        with open(a.result, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        info["checks"] = len(checks)
        info["fails"] = sum(1 for c in checks if not c["ok"])
    except Exception as e:
        info["error"] = str(e)
    print(json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
