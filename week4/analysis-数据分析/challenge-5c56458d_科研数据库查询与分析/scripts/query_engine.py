#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""query_engine.py — 结构化查询构建与内存执行（对 case.json 数据集做查询模拟，不连真实数据库）。
键归属：result.queries / result.query_results / result.query_log / result.boundary_registry 归本脚本。
退出码恒 0；失败写入 run_status，不中断交付。
"""
import argparse, json, os, sys, time

MARKER = "sci-db-query-analyze-v1"
MISSING_TOKENS = {"", "na", "n/a", "null", "none", "nan", "未知", "缺失"}
VALID_OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "nin", "contains", "between", "isnull", "notnull"}
VALID_FNS = {"count", "sum", "avg", "min", "max", "nunique"}


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
    if v is None:
        return True
    if isinstance(v, str) and v.strip().lower() in MISSING_TOKENS:
        return True
    return False


def to_num(v):
    try:
        if isinstance(v, bool):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def load_rows(case, dataset_id):
    """从 case.json 按 dataset_id 找数据集并取行（兼容 list[dict] 与矩阵）。"""
    raw = first_key(case, ["datasets", "tables", "snapshots", "data", "sources"], [])
    if isinstance(raw, dict):
        raw = [{"dataset_id": k, **(v if isinstance(v, dict) else {"rows": v})} for k, v in raw.items()]
    for ds in raw if isinstance(raw, list) else []:
        if not isinstance(ds, dict):
            continue
        did = first_key(ds, ["dataset_id", "id", "name", "table", "table_name"])
        if did != dataset_id:
            continue
        rows = first_key(ds, ["rows", "records", "data", "samples"])
        cols = first_key(ds, ["columns", "fields", "schema"]) or []
        if isinstance(rows, dict) and "columns" in rows:
            cols = rows["columns"]; rows = rows.get("rows", [])
        if isinstance(rows, list) and rows and isinstance(rows[0], list):
            if not cols:
                cols = ["col_%d" % i for i in range(len(rows[0]))]
            rows = [dict(zip(cols, r)) for r in rows]
        return rows or []
    return None  # dataset not found


def match_op(value, op, target):
    if op == "isnull":
        return is_missing(value)
    if op == "notnull":
        return not is_missing(value)
    if is_missing(value):
        return False  # 缺失值不参与普通过滤，由 boundary 登记兜底
    if op == "in":
        return value in target if isinstance(target, list) else value == target
    if op == "nin":
        return value not in target if isinstance(target, list) else value != target
    if op == "contains":
        return str(target).lower() in str(value).lower()
    if op == "between":
        t = target if isinstance(target, list) and len(target) == 2 else None
        nv, n0, n1 = to_num(value), to_num(t[0]), to_num(t[1])
        return None not in (nv, n0, n1) and n0 <= nv <= n1
    a, b = to_num(value), to_num(target)
    if a is None or b is None:  # 非数值退化到字符串比较
        a, b = str(value), str(target)
    return {"eq": a == b, "ne": a != b, "gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]


def agg_value(fn, values):
    vals = [v for v in values if not is_missing(v)]
    if fn == "count":
        return len(values)
    if fn == "nunique":
        return len(set(map(str, vals)))
    nums = [to_num(v) for v in vals]
    nums = [n for n in nums if n is not None]
    if fn == "sum":
        return sum(nums)
    if fn == "avg":
        return round(sum(nums) / len(nums), 6) if nums else None
    if fn == "min":
        return min(vals, key=lambda v: (to_num(v) is None, to_num(v) if to_num(v) is not None else str(v))) if vals else None
    if fn == "max":
        return max(vals, key=lambda v: (to_num(v) is None, to_num(v) if to_num(v) is not None else str(v))) if vals else None
    return None


def run_query(q, rows, log, boundary):
    """执行单条查询，返回 query_results 条目。rows=None 表示数据集不存在。"""
    qr = {"query_id": q.get("query_id"), "row_count": 0, "groups": [], "aggregates": {}, "empty": True, "status": "ok", "notes": []}
    for f in (q.get("filters") or []):
        if f.get("op") not in VALID_OPS:
            qr["status"], qr["notes"] = "error", qr["notes"] + ["illegal op: %s" % f.get("op")]
            return qr
    for ag in (q.get("aggregations") or []):
        if ag.get("fn") not in VALID_FNS:
            qr["status"], qr["notes"] = "error", qr["notes"] + ["illegal fn: %s" % ag.get("fn")]
            return qr
    if rows is None:
        qr["status"], qr["notes"] = "error", qr["notes"] + ["dataset not found: %s" % q.get("dataset_id")]
        boundary.append({"ref": q.get("query_id"), "kind": "dataset_not_found", "note": qr["notes"][0]})
        return qr
    sel = list(rows)
    for f in (q.get("filters") or []):
        col = f.get("column")
        miss = sum(1 for r in sel if is_missing(r.get(col)))
        if miss:
            boundary.append({"ref": "%s#filter:%s" % (q.get("query_id"), col), "kind": "missing_values",
                             "note": "%d rows missing '%s' excluded from filter" % (miss, col)})
        sel = [r for r in sel if match_op(r.get(col), f.get("op"), f.get("value"))]
    gb = q.get("group_by") or []
    qr["row_count"], qr["empty"] = len(sel), len(sel) == 0
    if qr["empty"]:
        boundary.append({"ref": q.get("query_id"), "kind": "empty_result",
                         "note": "query returned 0 rows after filters; registered, not silently dropped"})
    aggs = q.get("aggregations") or []
    def agg_row(sub):
        return {a.get("alias") or "%s(%s)" % (a.get("fn"), a.get("column")): agg_value(a.get("fn"), [r.get(a.get("column")) for r in sub] if (a.get("column") and a.get("column") != "*") else sub) for a in aggs}
    if gb:
        keys = sorted(set(tuple(str(r.get(c)) for c in gb) for r in sel), key=lambda t: tuple("" if v in ("None",) else v for v in t))
        for k in keys:
            sub = [r for r in sel if tuple(str(r.get(c)) for c in gb) == k]
            g = {"key": dict(zip(gb, k)), "count": len(sub)}
            g.update(agg_row(sub))
            qr["groups"].append(g)
    qr["aggregates"] = agg_row(sel)
    return qr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--emit-into", action="store_true")
    a = ap.parse_args()
    info = {"script": "query_engine", "marker_hit": marker_hit(), "exit": 0, "executed": 0, "errors": 0}
    try:
        with open(a.result, "r", encoding="utf-8") as f:
            result = json.load(f)
        with open(a.case, "r", encoding="utf-8") as f:
            case = json.load(f)
        queries = result.get("result", {}).get("queries") or []
        boundary, log = [], []
        seq = len(result.get("result", {}).get("query_log") or [])
        qrs = []
        for q in queries:
            seq += 1
            log.append({"seq": seq, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "query_id": q.get("query_id"),
                        "action": "issued", "detail": {"dataset_id": q.get("dataset_id"),
                        "filters": q.get("filters"), "group_by": q.get("group_by"), "aggregations": q.get("aggregations")}})
            rows = load_rows(case, q.get("dataset_id"))
            qr = run_query(q, rows, log, boundary)
            qrs.append(qr)
            seq += 1
            log.append({"seq": seq, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "query_id": q.get("query_id"),
                        "action": "executed", "detail": {"row_count": qr["row_count"], "status": qr["status"]}})
            info["executed"] += 1
            if qr["status"] != "ok":
                info["errors"] += 1
        r = result.setdefault("result", {})
        # 键归属纪律：boundary_registry 由本脚本写，但保留 Agent 手工登记（kind 以 manual_ 开头）
        manual = [b for b in (r.get("boundary_registry") or []) if str(b.get("kind", "")).startswith("manual_")]
        r["query_results"], r["boundary_registry"], r["query_log"] = qrs, manual + boundary, log
        r["coverage"]["queries_total"] = len(queries)
        r["coverage"]["empty_results"] = sum(1 for x in qrs if x["empty"])
        r["coverage"]["boundary_registered"] = len(r["boundary_registry"])
        answered = set()
        for x in qrs:
            qid = next((q.get("question_id") for q in queries if q.get("query_id") == x["query_id"]), None)
            if qid and (x["row_count"] > 0 or x["status"] == "ok"):
                answered.add(qid)
        r["coverage"]["answered_questions"] = len(answered)
        nq = max(1, len(r.get("query_scope", {}).get("questions") or [1]))
        r["coverage"]["ratio"] = round(len(answered) / nq, 4)
        if info["errors"]:
            r["run_status"] = {"state": "partial", "reason": "%d query errors; see query_results[].notes" % info["errors"], "manual_takeover": []}
        with open(a.result, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        info["error"] = str(e)
    print(json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
