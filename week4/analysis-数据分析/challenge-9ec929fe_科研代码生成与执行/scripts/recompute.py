#!/usr/bin/env python3
"""recompute.py — 数值独立复算器（sci-code-exec）。

从 case.json 的**原始数据**出发，按 result.json 中事前声明的 cleaning_rules
独立复算每条 stats（与生成分析代码分开实现——同一套数字算两遍，防"跑通了但
算错了"的静默错误）。复算结果写入 result.json 的 `recompute` 键（仅此键）。

支持数据形态：csv_inline（content 内联 CSV）、file（CSV 路径，相对 --input-root
或绝对路径）、sqlite（path + table）。支持清洗规则：dropna / dedup / filter /
clip / impute（按 rule_id 顺序应用）。支持统计：count / count_missing / mean /
sum / min / max / group_mean / group_count。

数值比对：abs_diff <= tolerance（默认 1e-6，浮点均值另加相对容差）。
复算不符 → mismatches 非空且 verdict=FAIL（Agent 须修代码重跑，不得改数凑数）；
数据不可读 → verdict=UNABLE 并提示登记 material_gaps。

退出码恒为 0（结论记在 recompute.verdict 与 stdout，不中断交付）。
防汉字陷阱：全程不做 .isalpha()/.isalnum() 判定；字段匹配用精确字符串比较。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import sqlite3
import sys

MISSING = {"", "na", "n/a", "null", "none", "-", "nan"}
STAT_TYPES = ("count", "count_missing", "mean", "sum", "min", "max",
              "group_mean", "group_count")
TOL = 1e-6


def to_num(v):
    try:
        f = float(str(v).strip())
        return f if math.isfinite(f) else None
    except Exception:
        return None


def is_missing(v):
    return str(v or "").strip().lower() in MISSING


def load_rows(case, input_root):
    """返回 {dataset_id: {"raw": [row], "note": str}}；raw 行为 {字段: 原始字符串}。"""
    out = {}
    if not isinstance(case, dict):
        return out
    for key in ("datasets", "data", "tables", "data_files", "sources"):
        v = case.get(key)
        if not isinstance(v, list):
            continue
        for i, e in enumerate(v):
            if not isinstance(e, dict):
                continue
            name = str(e.get("name") or e.get("id") or "ds-%02d" % (i + 1))
            fmt = str(e.get("format") or ("sqlite" if e.get("table") else "unknown"))
            rows, note = [], ""
            try:
                if fmt == "csv_inline" and isinstance(e.get("content"), str):
                    rows = list(csv.DictReader(io.StringIO(e["content"])))
                elif fmt in ("file", "csv") and e.get("path"):
                    path = str(e["path"])
                    if not os.path.isabs(path):
                        path = os.path.join(input_root or ".", path)
                    with open(path, "r", encoding="utf-8-sig") as f:
                        rows = list(csv.DictReader(f))
                elif fmt == "sqlite" and e.get("path"):
                    path = str(e["path"])
                    if not os.path.isabs(path):
                        path = os.path.join(input_root or ".", path)
                    conn = sqlite3.connect(path)
                    try:
                        table = str(e.get("table") or name)
                        cur = conn.execute("SELECT * FROM %s" % _safe_table(table))
                        cols = [d[0] for d in cur.description]
                        rows = [dict(zip(cols, ["" if x is None else str(x) for x in r]))
                                for r in cur.fetchall()]
                    finally:
                        conn.close()
                else:
                    note = "不支持的数据形态: %s" % fmt
            except Exception as ex:
                note = "读取失败: %s" % ex
            out[name] = {"raw": rows, "note": note}
        break
    return out


def _safe_table(t):
    # 表名只允许字母/数字/下划线（显式正则，不用 isalnum——对汉字串不可靠）
    import re
    if not re.match(r"^[A-Za-z0-9_]+$", str(t or "")):
        raise ValueError("非法表名: %r" % t)
    return t


def apply_rules(rows, rules):
    """按 rule_id 顺序应用清洗规则，返回 (clean_rows, per_rule_affected)。"""
    rows = [dict(r) for r in rows]
    affected = {}
    for rule in rules or []:
        rid = str((rule or {}).get("rule_id") or "?")
        act = str(rule.get("action") or "")
        field = str(rule.get("target_field") or "")
        params = rule.get("params") or {}
        before = len(rows)
        if act == "dropna" and field:
            rows = [r for r in rows if not is_missing(r.get(field))]
        elif act == "dedup" and field:
            seen, keep = set(), []
            for r in rows:
                k = str(r.get(field) or "")
                if k in seen:
                    continue
                seen.add(k)
                keep.append(r)
            rows = keep
        elif act == "filter" and field:
            vals = set(str(x) for x in (params.get("values") or []))
            if vals:
                rows = [r for r in rows if str(r.get(field) or "") in vals]
        elif act == "clip" and field:
            lo, hi = params.get("low"), params.get("high")
            for r in rows:
                num = to_num(r.get(field))
                if num is not None:
                    c = min(max(num, lo), hi) if (lo is not None and hi is not None) else num
                    if lo is not None and num < lo:
                        c = lo
                    if hi is not None and num > hi:
                        c = hi
                    r[field] = repr(c)
        elif act == "impute" and field:
            fill = params.get("value")
            for r in rows:
                if is_missing(r.get(field)):
                    r[field] = str(fill)
        affected[rid] = before - len(rows)
    return rows, affected


def compute_stat(stat, raw_rows, clean_rows):
    """按 stat.type 从数据复算一个数值。返回 (value, n_rows, error_note)。"""
    st = str((stat or {}).get("type") or "")
    params = stat.get("params") or {}
    if st not in STAT_TYPES:
        return None, None, "未知统计类型: %s" % st
    if st == "count_missing":
        field = str(params.get("field") or stat.get("source_field") or "")
        return sum(1 for r in raw_rows if is_missing(r.get(field))), len(raw_rows), ""
    if st == "count":
        return len(clean_rows), len(clean_rows), ""
    field = str(params.get("field") or stat.get("source_field") or "")
    if st in ("mean", "sum", "min", "max"):
        vals = [to_num(r.get(field)) for r in clean_rows if not is_missing(r.get(field))]
        vals = [v for v in vals if v is not None]
        if not vals:
            return None, 0, "无可用数值（字段 %s）" % field
        n = len(vals)
        return (sum(vals) / n if st == "mean" else sum(vals) if st == "sum"
                else min(vals) if st == "min" else max(vals)), n, ""
    if st in ("group_mean", "group_count"):
        vf = str(params.get("value_field") or field)
        gf = str(params.get("group_field") or "")
        gv = str(params.get("group") or "")
        sub = [r for r in clean_rows if str(r.get(gf) or "") == gv]
        if st == "group_count":
            return len(sub), len(sub), ""
        vals = [to_num(r.get(vf)) for r in sub if not is_missing(r.get(vf))]
        vals = [v for v in vals if v is not None]
        if not vals:
            return None, 0, "组 %s=%s 无可用数值（字段 %s）" % (gf, gv, vf)
        return sum(vals) / len(vals), len(vals), ""
    return None, None, "未实现的统计类型"


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--input-root", default="/input")
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--emit-into", action="store_true")
        args = ap.parse_args()
    except Exception as e:
        print("[recompute] 参数解析失败（已降级）: %s" % e)
        return 0

    problems = []
    marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")
    marker_hit = os.path.exists(marker)
    if not marker_hit:
        problems.append("定位标志未命中（脚本未与 SKILL.md 同包），仍继续复算")

    case = None
    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except Exception as e:
        problems.append("case.json 读取失败: %s" % e)

    res = None
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except Exception as e:
        problems.append("result.json 读取失败: %s" % e)

    inner = (res or {}).get("result") if isinstance(res, dict) else None
    stats = [s for s in ((inner or {}).get("stats") or []) if isinstance(s, dict)]
    rules = ((inner or {}).get("cleaning_rules") or {}).get("rules") or []

    data = load_rows(case if isinstance(case, dict) else {}, args.input_root)
    sources, unreadable = [], []
    for name, info in data.items():
        sources.append({"dataset_id": name, "rows": len(info["raw"]),
                        "note": info["note"] or "ok"})
        if info["note"]:
            unreadable.append(name)

    per_stat, mismatches = [], []
    for st in stats:
        sid = str(st.get("stat_id") or "?")
        ds_name = str(st.get("source") or "")
        # 数据源：stat.source 指定；未指定时若只有一个数据集则用它
        if ds_name and ds_name in data:
            ds = data[ds_name]
        elif len(data) == 1:
            ds = list(data.values())[0]
        else:
            per_stat.append({"stat_id": sid, "declared_value": st.get("value"),
                             "recomputed_value": None, "abs_diff": None,
                             "tolerance": TOL, "matched": False,
                             "verdict": "UNABLE", "note": "stat.source 未指定或数据集缺失"})
            mismatches.append(sid)
            continue
        if ds["note"]:
            per_stat.append({"stat_id": sid, "declared_value": st.get("value"),
                             "recomputed_value": None, "abs_diff": None,
                             "tolerance": TOL, "matched": False,
                             "verdict": "UNABLE", "note": "数据不可读: %s" % ds["note"]})
            mismatches.append(sid)
            continue
        clean_rows, affected = apply_rules(ds["raw"], rules)
        val, n, err = compute_stat(st, ds["raw"], clean_rows)
        declared = to_num(st.get("value"))
        matched = None
        if err:
            matched, verdict = False, "UNABLE"
        elif declared is None or val is None:
            matched, verdict = False, "MISMATCH"
        else:
            diff = abs(declared - val)
            tol = max(TOL, TOL * max(abs(declared), abs(val)))
            matched, verdict = diff <= tol, ("PASS" if diff <= tol else "MISMATCH")
        entry = {"stat_id": sid, "declared_value": st.get("value"),
                 "recomputed_value": (round(val, 9) if isinstance(val, float) else val),
                 "abs_diff": (round(abs(declared - val), 12)
                              if (declared is not None and val is not None and not err) else None),
                 "tolerance": TOL, "matched": matched, "verdict": verdict,
                 "n_rows": n, "rules_affected_rows": affected, "note": err}
        per_stat.append(entry)
        if verdict in ("MISMATCH",):
            mismatches.append(sid)

    if unreadable:
        verdict = "UNABLE"
        problems.append("数据不可读: %s（请登记 material_gaps）" % ",".join(unreadable))
    elif mismatches:
        verdict = "FAIL"
    elif stats:
        verdict = "PASS"
    else:
        verdict = "UNABLE"
        problems.append("stats 为空（result.stats 未回填），复算无从进行")

    recompute = {"computed_by": "scripts/recompute.py", "tolerance": TOL,
                 "data_sources": sources, "per_stat": per_stat,
                 "mismatches": mismatches, "verdict": verdict,
                 "note": ("独立复算完成；FAIL 时须修代码重跑，不得改数凑数"
                          if verdict == "FAIL" else "")}
    wrote = False
    if isinstance(res, dict) and isinstance(inner, dict):
        try:
            inner["recompute"] = recompute
            d = os.path.dirname(args.result)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
            wrote = True
        except Exception as e:
            problems.append("回写 result.json 失败: %s" % e)
    print("[recompute] verdict=%s | stats=%d | mismatches=%d | 数据集=%d | marker_hit=%s | 回写result=%s"
          % (verdict, len(stats), len(mismatches), len(sources), marker_hit, wrote))
    for p in per_stat:
        print("  %-6s declared=%s recomputed=%s -> %s%s"
              % (p["stat_id"], p["declared_value"], p["recomputed_value"], p["verdict"],
                 (" (%s)" % p["note"] if p.get("note") else "")))
    for pr in problems:
        print("  WARN: %s" % pr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[recompute] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
