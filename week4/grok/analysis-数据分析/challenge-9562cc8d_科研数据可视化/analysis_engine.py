"""analysis_engine.py — shared deterministic engine for the ANALYSIS track.

Kinds: data_cleaning | stats_analysis | data_viz | code_gen_exec |
       multi_step_analysis | db_query_analysis

Contract (ENGINE_CONVENTION.md):
  validate_ir(ir) -> {ok, errors, warnings}
  build(ir, case, out_dir) -> outputs[]  (also writes provenance.json, report.md,
                                          _summary.json)
  compute_status(ir, validation, summary) -> success|partial|failed

Every computed number is recomputed from the ACTUAL registered input files
(csv/tsv/json tables or sqlite databases). Nothing is pre-baked: the agent reads
the organizer material, fills the IR, this engine validates + computes + exports.
Stdlib only for core computation; matplotlib is OPTIONAL (PNG preview) with an
honest fallback to editable SVG. Databases are opened READ-ONLY (mode=ro); a
provided .sql dump is restored into a working copy under the output dir and the
original file is never modified.
"""
from __future__ import annotations

import csv
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import w4kit

IR_VERSION = w4kit.IR_VERSION
KINDS = {"data_cleaning", "stats_analysis", "data_viz", "code_gen_exec",
         "multi_step_analysis", "db_query_analysis"}
OP_TYPES = {"flag_missing", "dedup", "unit_convert", "outlier_flag",
            "type_cast", "rename_column", "drop_rows"}
STAT_TYPES = {"describe", "compare_groups", "correlation", "regression"}
CHART_TYPES = {"scatter", "line", "bar", "histogram", "box"}
STEP_KINDS = {"load", "clean", "stats", "viz", "query", "interpret"}
META_STATUS = {"reported", "inferred", "not_reported", "source_conflict",
               "extraction_failed", "insufficient_evidence"}
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9",
           "#D55E00", "#F0E442", "#000000"]  # Okabe-Ito, colorblind safe


# ── path / data loading ─────────────────────────────────────────────────────

def _resolve(ir, case, rel):
    if not rel:
        return None
    p = Path(str(rel))
    if p.is_absolute():
        return p if p.exists() else None
    for b in (ir.get("_ir_dir"), (case or {}).get("input_dir"), "."):
        if b and (Path(b) / p).exists():
            return Path(b) / p
    return None


def _dataset(ir, did):
    return next((d for d in ir.get("datasets", [])
                 if d.get("dataset_id") == did), None)


def _source(ir, sid):
    return next((s for s in ir.get("sources", []) if s.get("id") == sid), None)


def _load_all(ir, case, out_dir, outputs, prov):
    """Load every registered dataset from its ACTUAL file. Honest on failure."""
    ctx = {}
    for ds in ir.get("datasets", []):
        did = ds.get("dataset_id")
        sid = ds.get("source_id")
        entry = {"dataset_id": did, "source_id": sid, "rows": [], "columns": [],
                 "status": "ok", "sha256": None, "path": None, "n_rows": 0,
                 "kind": "table"}
        rel = ds.get("path") or (_source(ir, sid) or {}).get("path")
        f = _resolve(ir, case, rel)
        if ds.get("rows") is not None and f is None:
            entry["rows"] = ds["rows"]
            entry["columns"] = ds.get("columns") or (
                list(ds["rows"][0].keys()) if ds["rows"] else [])
            entry["status"] = "ir_inline"
            entry["n_rows"] = len(ds["rows"])
        elif f is None:
            entry["status"] = "file_not_found"
        else:
            entry["path"] = str(f)
            try:
                entry["sha256"] = w4kit.sha256_file(f)
                if f.suffix.lower() in (".db", ".sqlite", ".sqlite3", ".sql"):
                    entry["kind"] = "database"
                    entry["status"] = "ok"
                else:
                    rows = w4kit.read_table(f)
                    entry["rows"] = rows
                    entry["columns"] = ds.get("columns") or (
                        list(rows[0].keys()) if rows else [])
                    entry["n_rows"] = len(rows)
                    if not rows:
                        entry["status"] = "empty_table"
            except Exception as e:
                entry["status"] = f"read_failed: {type(e).__name__}: {e}"
        claimed = ds.get("sha256")
        if claimed and entry["sha256"] and claimed.lower() != entry["sha256"]:
            entry["hash_mismatch"] = {"claimed": claimed, "actual": entry["sha256"]}
        if ds.get("columns") and entry["rows"]:
            actual = set(entry["rows"][0].keys())
            missing = [c for c in ds["columns"] if c not in actual]
            if missing:
                entry["column_mismatch"] = missing
        ctx[did] = entry
        prov.append({"artifact": "dataset_load", "item": did, "source_id": sid,
                     "locator": {"path": entry["path"], "sha256": entry["sha256"],
                                 "status": entry["status"], "n_rows": entry["n_rows"]}})
    return ctx


def _col(rows, name):
    return [r.get(name) for r in rows]


def _nums(rows, name):
    vals = [w4kit.to_float(v) for v in _col(rows, name)]
    return [v for v in vals if v is not None and not math.isnan(v)]


def _ev_ds(ctx, did, column=None, rows_used=None):
    e = ctx.get(did, {})
    ev = {"source_id": e.get("source_id"), "dataset_id": did}
    if column:
        ev["column"] = column
    if rows_used is not None:
        ev["n_rows_used"] = rows_used
    if e.get("path"):
        ev["path"] = e["path"]
    return ev


def _write_csv(path, columns, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})
    return str(path)


def _r(x, nd=6):
    if x is None:
        return None
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return round(float(x), nd)


# ── stdlib inferential math (regularized incomplete beta, NR continued frac) ─

def _betacf(a, b, x):
    FPMIN = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, 201):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < FPMIN:
            d = FPMIN
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < FPMIN:
            d = FPMIN
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < 3e-12:
            break
    return h


def _betainc(a, b, x):
    """Regularized incomplete beta I_x(a,b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_p2(t, df):
    """Two-sided p-value for Student t."""
    if df <= 0:
        return None
    return _betainc(df / 2.0, 0.5, df / (df + t * t))


def f_p(f, d1, d2):
    if f <= 0 or d1 <= 0 or d2 <= 0:
        return 1.0
    return _betainc(d2 / 2.0, d1 / 2.0, d2 / (d2 + d1 * f))


def t_crit(alpha, df):
    """Two-sided critical t: P(|T|>t)=alpha, by bisection on t_p2."""
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_p2(mid, df) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _shape(vals):
    n = len(vals)
    if n < 3:
        return {"skewness": None, "excess_kurtosis": None}
    m = sum(vals) / n
    s2 = sum((x - m) ** 2 for x in vals) / n
    if s2 == 0:
        return {"skewness": 0.0, "excess_kurtosis": 0.0}
    s = math.sqrt(s2)
    skew = sum((x - m) ** 3 for x in vals) / n / s ** 3
    kurt = sum((x - m) ** 4 for x in vals) / n / s ** 4 - 3.0
    return {"skewness": skew, "excess_kurtosis": kurt}


def _ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _mannwhitney(a, b):
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return None
    allv = a + b
    ranks = _ranks(allv)
    r1 = sum(ranks[:n1])
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u = min(u1, u2)
    n = n1 + n2
    ties = {}
    for v in allv:
        ties[v] = ties.get(v, 0) + 1
    tie_term = sum(t ** 3 - t for t in ties.values())
    var = n1 * n2 / 12.0 * ((n + 1) - tie_term / (n * (n - 1)))
    if var <= 0:
        return {"U": u, "z": None, "p": None,
                "note": "zero variance; test undefined"}
    z = (u - n1 * n2 / 2.0) / math.sqrt(var)
    p = 2.0 * (1.0 - norm_cdf(abs(z)))
    return {"U": u, "z": z, "p": min(1.0, p),
            "note": "normal approximation with tie correction; exact small-sample "
                    "distribution not computed (stdlib)"}


def _welch(a, b):
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return None
    m1, m2 = sum(a) / n1, sum(b) / n2
    v1 = sum((x - m1) ** 2 for x in a) / (n1 - 1)
    v2 = sum((x - m2) ** 2 for x in b) / (n2 - 1)
    se = math.sqrt(v1 / n1 + v2 / n2)
    if se == 0:
        return {"mean_diff": m1 - m2, "t": None, "df": None, "p": None,
                "note": "zero standard error"}
    t = (m1 - m2) / se
    df = (v1 / n1 + v2 / n2) ** 2 / (
        (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    p = t_p2(t, df)
    sp = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    d = (m1 - m2) / sp if sp > 0 else None
    tc = t_crit(0.05, df)
    return {"mean_diff": m1 - m2, "se_diff": se, "t": t, "df": df, "p": p,
            "cohens_d": d, "ci95_mean_diff": [m1 - m2 - tc * se, m1 - m2 + tc * se],
            "variance_ratio_F": (v1 / v2) if v2 > 0 else None,
            "variance_ratio_p": f_p(v1 / v2, n1 - 1, n2 - 1) if v2 > 0 else None}


def _anova(groups):
    k = len(groups)
    ns = [len(g) for g in groups]
    n = sum(ns)
    if k < 2 or any(x < 2 for x in ns):
        return None
    grand = sum(sum(g) for g in groups) / n
    ssb = sum(len(g) * (sum(g) / len(g) - grand) ** 2 for g in groups)
    ssw = sum(sum((x - sum(g) / len(g)) ** 2 for x in g) for g in groups)
    d1, d2 = k - 1, n - k
    if ssw == 0:
        return {"F": None, "p": None, "note": "zero within-group variance"}
    F = (ssb / d1) / (ssw / d2)
    return {"F": F, "df_between": d1, "df_within": d2, "p": f_p(F, d1, d2),
            "eta_squared": ssb / (ssb + ssw),
            "note": "one-way ANOVA; post-hoc pairwise tests NOT performed"}


def _pearson_full(xs, ys):
    pairs = [(w4kit.to_float(a), w4kit.to_float(b)) for a, b in zip(xs, ys)]
    pairs = [(a, b) for a, b in pairs
             if a is not None and b is not None
             and not math.isnan(a) and not math.isnan(b)]
    n = len(pairs)
    r = w4kit.correlation([a for a, _ in pairs], [b for _, b in pairs])
    if r is None or n < 3:
        return {"r": r, "n": n, "status": "insufficient_evidence"}
    t = r * math.sqrt((n - 2) / (1 - r * r)) if abs(r) < 1 else float("inf")
    p = t_p2(t, n - 2) if abs(r) < 1 else 0.0
    z = math.atanh(max(-0.999999, min(0.999999, r)))
    se = 1.0 / math.sqrt(n - 3)
    return {"r": r, "n": n, "t": t, "df": n - 2, "p": p,
            "ci95_fisher_z": [math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se)]}


# ── cleaning ────────────────────────────────────────────────────────────────

def _norm_key(v):
    return re.sub(r"\s+", " ", str(v if v is not None else "").strip()).casefold()


def _run_cleaning(ir, case, ctx, out_dir, outputs, prov, ops=None, prefix=""):
    ops = ops if ops is not None else ir.get("cleaning", {}).get("operations", [])
    log, op_status = [], []
    cleaned = {}
    for did, e in ctx.items():
        if e["kind"] == "table" and e["rows"]:
            cleaned[did] = [dict(r) for r in e["rows"]]
    for op in ops:
        oid = op.get("op_id", "?")
        typ = op.get("type")
        did = op.get("dataset_id")
        st = {"op_id": oid, "type": typ, "dataset_id": did, "status": "done",
              "n_changes": 0}
        rows = cleaned.get(did)
        if rows is None:
            st["status"] = "failed"
            st["reason"] = f"dataset '{did}' not loaded (status={ctx.get(did, {}).get('status')})"
            op_status.append(st)
            continue
        params = op.get("params", {})
        col = op.get("column")
        ev = op.get("evidence") or _ev_ds(ctx, did, col)
        try:
            if typ == "flag_missing":
                sent = {str(k): v for k, v in params.get("sentinel_map", {}).items()}
                default = params.get("default_label", "missing_entry")
                cols = op.get("columns") or ([col] if col else list(rows[0].keys()))
                for ci, c in enumerate(cols):
                    for ri, r in enumerate(rows):
                        raw = r.get(c)
                        s = "" if raw is None else str(raw).strip()
                        num = w4kit.to_float(raw)
                        if s in sent or (s == "" and "" in sent) or (
                                s == "" and params.get("blank_is_missing", True)):
                            label = sent.get(s, default)
                            if s == "0" or num == 0:
                                continue  # true zero is NOT missing
                            log.append({"op_id": oid, "dataset_id": did, "row": ri,
                                        "column": c, "original": raw, "new": None,
                                        "action": "flag_missing", "label": label,
                                        "rule": op.get("rule", "sentinel->missing"),
                                        "evidence": ev})
                            r[c] = None
                            st["n_changes"] += 1
            elif typ == "dedup":
                keys = params.get("key_columns") or op.get("columns") or []
                if not keys:
                    raise ValueError("dedup requires params.key_columns (real primary key)")
                keep = params.get("keep", "first")
                seen, kept, removed = {}, [], []
                for ri, r in enumerate(rows):
                    k = tuple(_norm_key(r.get(c)) for c in keys)
                    if k in seen:
                        prev = seen[k]
                        drop = ri if keep == "first" else prev
                        winner = prev if keep == "first" else ri
                        removed.append({"op_id": oid, "dataset_id": did,
                                        "row": drop, "kept_row": winner,
                                        "key": dict(zip(keys, k)),
                                        "dropped_record": rows[drop],
                                        "action": "dedup_remove",
                                        "rule": op.get("rule", f"keep={keep} on {keys}"),
                                        "reason": op.get("reason", "duplicate primary key"),
                                        "evidence": ev})
                        if keep == "last":
                            kept = [x for x in kept if x is not rows[prev]]
                            kept.append(r)
                            seen[k] = ri
                    else:
                        seen[k] = ri
                        kept.append(r)
                cleaned[did] = kept
                log.extend(removed)
                st["n_changes"] = len(removed)
                st["n_groups"] = len(seen)
            elif typ == "unit_convert":
                factor = w4kit.safe_eval(str(params.get("factor_expr", "1")), {})
                uc = params.get("unit_column")
                from_u, to_u = params.get("from_unit"), params.get("to_unit")
                for ri, r in enumerate(rows):
                    if uc and from_u and _norm_key(r.get(uc)) != _norm_key(from_u):
                        continue
                    num = w4kit.to_float(r.get(col))
                    if num is None:
                        continue
                    new = num * factor
                    log.append({"op_id": oid, "dataset_id": did, "row": ri,
                                "column": col, "original": r.get(col), "new": new,
                                "action": "unit_convert", "factor": factor,
                                "from_unit": from_u, "to_unit": to_u,
                                "inverse_expr": f"value / ({params.get('factor_expr', '1')})",
                                "rule": op.get("rule", "linear unit conversion"),
                                "evidence": ev})
                    r[col] = new
                    if uc and to_u:
                        r[uc] = to_u
                    st["n_changes"] += 1
            elif typ == "outlier_flag":
                vals = _nums(rows, col)
                method = params.get("method", "iqr")
                lo = hi = None
                if method == "iqr":
                    d = w4kit.describe(vals)
                    k = float(params.get("k", 1.5))
                    lo, hi = d["q25"] - k * (d["q75"] - d["q25"]), d["q75"] + k * (d["q75"] - d["q25"])
                elif method == "zscore":
                    d = w4kit.describe(vals)
                    thr = float(params.get("threshold", 3.0))
                    if d["sd"] > 0:
                        lo, hi = d["mean"] - thr * d["sd"], d["mean"] + thr * d["sd"]
                elif method == "bounds":
                    lo, hi = params.get("min"), params.get("max")
                action = params.get("action", "flag")
                keep_rows = []
                for ri, r in enumerate(rows):
                    num = w4kit.to_float(r.get(col))
                    out = num is not None and (
                        (lo is not None and num < lo) or (hi is not None and num > hi))
                    if out:
                        log.append({"op_id": oid, "dataset_id": did, "row": ri,
                                    "column": col, "original": r.get(col),
                                    "new": None if action == "remove" else r.get(col),
                                    "action": f"outlier_{action}",
                                    "bounds": [lo, hi], "method": method,
                                    "rule": op.get("rule", f"{method} outlier rule"),
                                    "reason": op.get("reason", "outside diagnostic bounds"),
                                    "evidence": ev})
                        st["n_changes"] += 1
                        if action == "remove":
                            continue
                    keep_rows.append(r)
                cleaned[did] = keep_rows
                st["bounds"] = [lo, hi]
            elif typ == "type_cast":
                to = params.get("to", "float")
                for ri, r in enumerate(rows):
                    raw = r.get(col)
                    if raw is None or str(raw).strip() == "":
                        continue
                    try:
                        if to == "float":
                            new = w4kit.to_float(raw)
                            if new is None:
                                raise ValueError("not numeric")
                        elif to == "int":
                            new = int(float(str(raw).replace(",", "")))
                        else:
                            new = str(raw).strip()
                    except (ValueError, TypeError):
                        log.append({"op_id": oid, "dataset_id": did, "row": ri,
                                    "column": col, "original": raw, "new": raw,
                                    "action": "cast_failed", "status": "extraction_failed",
                                    "rule": op.get("rule", f"cast to {to}"), "evidence": ev})
                        st["n_changes"] += 1
                        continue
                    if str(new) != str(raw):
                        log.append({"op_id": oid, "dataset_id": did, "row": ri,
                                    "column": col, "original": raw, "new": new,
                                    "action": "type_cast", "to": to,
                                    "rule": op.get("rule", f"cast to {to}"), "evidence": ev})
                        r[col] = new
                        st["n_changes"] += 1
            elif typ == "rename_column":
                mapping = params.get("mapping", {})
                for old, new in mapping.items():
                    for r in rows:
                        if old in r:
                            r[new] = r.pop(old)
                    log.append({"op_id": oid, "dataset_id": did, "column": old,
                                "new_column": new, "action": "rename_column",
                                "rule": op.get("rule", "dictionary alignment"),
                                "evidence": ev})
                    st["n_changes"] += 1
            elif typ == "drop_rows":
                expr = params.get("where")
                if not expr:
                    raise ValueError("drop_rows requires params.where (safe_eval expression)")
                kept = []
                for ri, r in enumerate(rows):
                    env = {k: w4kit.to_float(v) for k, v in r.items()
                           if w4kit.to_float(v) is not None}
                    try:
                        drop = bool(w4kit.safe_eval(expr, env))
                    except Exception:
                        drop = False
                    if drop:
                        log.append({"op_id": oid, "dataset_id": did, "row": ri,
                                    "dropped_record": r, "action": "drop_rows",
                                    "rule": expr, "reason": op.get("reason", "explicit rule"),
                                    "evidence": ev})
                        st["n_changes"] += 1
                    else:
                        kept.append(r)
                cleaned[did] = kept
            else:
                st["status"] = "failed"
                st["reason"] = f"unknown op type '{typ}'"
        except Exception as e:
            st["status"] = "failed"
            st["reason"] = f"{type(e).__name__}: {e}"
        op_status.append(st)
        prov.append({"artifact": f"{prefix}cleaning_log.json", "item": oid,
                     "source_id": ctx.get(did, {}).get("source_id"),
                     "locator": {"dataset_id": did, "type": typ, "status": st["status"]}})

    # quality report recomputed FROM the cleaned tables (consistency self-check)
    quality, mismatches = {}, []
    for did, rows in cleaned.items():
        cols = list(rows[0].keys()) if rows else ctx.get(did, {}).get("columns", [])
        per_col = {}
        for c in cols:
            vals = [r.get(c) for r in rows]
            n_missing = sum(1 for v in vals
                            if v is None or str(v).strip() == "")
            nums = [w4kit.to_float(v) for v in vals]
            nums = [x for x in nums if x is not None]
            per_col[c] = {"n_rows": len(rows), "n_missing": n_missing,
                          "missing_rate": _r(n_missing / len(rows), 4) if rows else None,
                          "n_numeric": len(nums)}
        flags = [l for l in log if l["dataset_id"] == did]
        n_flag = sum(1 for l in flags if l["action"] == "flag_missing")
        n_out = sum(1 for l in flags if l["action"].startswith("outlier"))
        n_conv = sum(1 for l in flags if l["action"] == "unit_convert")
        n_dup = sum(1 for l in flags if l["action"] == "dedup_remove")
        quality[did] = {"n_rows_before": ctx.get(did, {}).get("n_rows", 0),
                        "n_rows_after": len(rows), "columns": per_col,
                        "n_missing_flagged": n_flag, "n_outliers_flagged": n_out,
                        "n_unit_conversions": n_conv, "n_duplicates_removed": n_dup,
                        "n_cast_failures": sum(1 for l in flags if l["action"] == "cast_failed")}
        # consistency: report numbers must equal recomputation from cleaned rows
        recomputed_missing = sum(v["n_missing"] for v in per_col.values())
        declared_missing = sum(1 for r in rows for c in cols
                               if r.get(c) is None or str(r.get(c)).strip() == "")
        if recomputed_missing != declared_missing:
            mismatches.append({"dataset_id": did, "field": "n_missing",
                               "report": recomputed_missing, "recomputed": declared_missing})
        if quality[did]["n_rows_before"] - n_dup != len(rows) and any(
                l["action"] in ("dedup_remove", "drop_rows", "outlier_remove")
                for l in flags):
            n_drop = sum(1 for l in flags if l["action"] in (
                "dedup_remove", "drop_rows", "outlier_remove"))
            if quality[did]["n_rows_before"] - n_drop != len(rows):
                mismatches.append({"dataset_id": did, "field": "row_count",
                                   "expected": quality[did]["n_rows_before"] - n_drop,
                                   "actual": len(rows)})
    # export cleaned tables + original snapshots + log
    for did, rows in cleaned.items():
        cols = list(rows[0].keys()) if rows else ctx.get(did, {}).get("columns", [])
        p = _write_csv(out_dir / f"{prefix}cleaned_{did}.csv", cols, rows)
        outputs.append({"name": f"{prefix}cleaned_{did}.csv", "path": p,
                        "format": "csv", "role": "csv"})
        e = ctx.get(did, {})
        if e.get("path") and e["kind"] == "table":
            snap = out_dir / f"{prefix}original_{did}{Path(e['path']).suffix}"
            try:
                shutil.copyfile(e["path"], snap)
                outputs.append({"name": snap.name, "path": str(snap),
                                "format": "csv", "role": "original_snapshot"})
            except OSError:
                pass
        ctx[did]["rows"] = rows  # downstream steps see cleaned data
        ctx[did]["n_rows"] = len(rows)
        ctx[did]["cleaned"] = True
    result = {"operations": op_status, "changes": log, "quality": quality,
              "consistency_check": {"ok": not mismatches, "mismatches": mismatches},
              "n_operations": len(op_status),
              "n_failed_ops": sum(1 for o in op_status if o["status"] != "done"),
              "n_changes": len(log)}
    w4kit.write_json(out_dir / f"{prefix}cleaning_log.json", result)
    outputs.append({"name": f"{prefix}cleaning_log.json",
                    "path": str(out_dir / f"{prefix}cleaning_log.json"),
                    "format": "json", "role": "json"})
    return result


# ── statistics ──────────────────────────────────────────────────────────────

def _run_stats(ir, case, ctx, out_dir, outputs, prov, analyses=None, prefix=""):
    analyses = analyses if analyses is not None else ir.get("stats", {}).get("analyses", [])
    results = []
    for a in analyses:
        aid = a.get("analysis_id", "?")
        typ = a.get("type")
        did = a.get("dataset_id")
        e = ctx.get(did, {})
        rows = e.get("rows", [])
        res = {"analysis_id": aid, "type": typ, "dataset_id": did,
               "status": "computed", "interpretation": a.get("interpretation"),
               "assumptions": list(a.get("assumptions", [])),
               "evidence": _ev_ds(ctx, did, a.get("column") or a.get("columns"))}
        if not rows or e.get("status") in ("file_not_found",) or str(
                e.get("status", "")).startswith("read_failed"):
            res["status"] = "insufficient_evidence"
            res["reason"] = f"dataset not usable: {e.get('status')}"
            results.append(res)
            continue
        try:
            if typ == "describe":
                col = a.get("column")
                vals = _col(rows, col)
                d = w4kit.describe(vals)
                res["describe"] = d
                res["shape"] = _shape(_nums(rows, col))
                if d["n"] >= 2 and d["sd"] is not None:
                    se = d["sd"] / math.sqrt(d["n"])
                    tc = t_crit(0.05, d["n"] - 1)
                    res["mean_ci95"] = [d["mean"] - tc * se, d["mean"] + tc * se]
                    res["se_mean"] = se
                res["evidence"] = _ev_ds(ctx, did, col, d["n"])
                res["assumptions"].append(
                    f"missing/non-numeric excluded pairwise: {d.get('missing', 0)} of "
                    f"{len(vals)} cells; NO imputation performed")
                if d["n"] == 0:
                    res["status"] = "insufficient_evidence"
                res["auto_summary"] = (
                    f"{col}: n={d['n']}, mean={_r(d.get('mean'))}, sd={_r(d.get('sd'))}, "
                    f"median={_r(d.get('median'))}, range=[{_r(d.get('min'))}, {_r(d.get('max'))}]")
            elif typ == "compare_groups":
                col, gcol = a.get("column"), a.get("group_column")
                gvals = sorted({_norm_key(v) for v in _col(rows, gcol)
                                if v is not None and str(v).strip() != ""})
                groups = {}
                for g in gvals:
                    groups[g] = [w4kit.to_float(r.get(col)) for r in rows
                                 if _norm_key(r.get(gcol)) == g]
                    groups[g] = [x for x in groups[g] if x is not None]
                res["groups"] = {g: w4kit.describe(v) for g, v in groups.items()}
                res["n_groups"] = len(groups)
                if len(groups) < 2 or any(len(v) < 2 for v in groups.values()):
                    res["status"] = "insufficient_evidence"
                    res["reason"] = "need >=2 groups with >=2 numeric observations each"
                elif len(groups) == 2:
                    (g1, v1), (g2, v2) = list(groups.items())
                    w = _welch(v1, v2)
                    res["welch_t"] = w
                    res["evidence"] = _ev_ds(ctx, did, col, len(v1) + len(v2))
                    shapes = {g: _shape(v) for g, v in groups.items()}
                    res["shape_by_group"] = shapes
                    nonnormal = any(s.get("skewness") is not None and
                                    (abs(s["skewness"]) > 1 or
                                     abs(s["excess_kurtosis"]) > 2)
                                    for s in shapes.values())
                    res["assumptions"].append(
                        "independence assumed from study design (verify against data dictionary)")
                    res["assumptions"].append(
                        "normality screened via skewness/excess-kurtosis (|skew|>1 or "
                        "|kurt|>2 flags concern); formal Shapiro-Wilk NOT available in stdlib")
                    if nonnormal or a.get("method") == "mannwhitney":
                        res["mannwhitney"] = _mannwhitney(v1, v2)
                        res["assumptions"].append(
                            "non-normality flagged or nonparametric requested: "
                            "Mann-Whitney U (normal approximation) also reported")
                    if w and w.get("variance_ratio_p") is not None and w["variance_ratio_p"] < 0.05:
                        res["assumptions"].append(
                            "variance ratio F-test p<0.05: heteroscedastic; Welch (not Student) used")
                    if w:
                        res["auto_summary"] = (
                            f"{g1} vs {g2}: mean diff={_r(w['mean_diff'])} "
                            f"(95% CI [{_r(w['ci95_mean_diff'][0])}, {_r(w['ci95_mean_diff'][1])}]), "
                            f"Welch t={_r(w['t'])}, df={_r(w['df'], 2)}, p={_r(w['p'])}, "
                            f"Cohen's d={_r(w['cohens_d'])}")
                else:
                    av = _anova(list(groups.values()))
                    res["anova"] = av
                    res["assumptions"].append(
                        ">2 groups: one-way ANOVA used (NOT a two-sample t-test); "
                        "post-hoc comparisons not performed")
                    if av:
                        res["auto_summary"] = (
                            f"ANOVA F({av['df_between']},{av['df_within']})={_r(av['F'])}, "
                            f"p={_r(av['p'])}, eta^2={_r(av['eta_squared'])}")
            elif typ == "correlation":
                cx, cy = (a.get("columns") or [a.get("x"), a.get("y")])[:2]
                xs, ys = _col(rows, cx), _col(rows, cy)
                if a.get("method") == "spearman":
                    pairs = [(w4kit.to_float(x), w4kit.to_float(y))
                             for x, y in zip(xs, ys)]
                    pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
                    rx = _ranks([p[0] for p in pairs])
                    ry = _ranks([p[1] for p in pairs])
                    full = _pearson_full(rx, ry)
                    full["method"] = "spearman (Pearson on average-tie ranks)"
                else:
                    full = _pearson_full(xs, ys)
                    full["method"] = "pearson"
                res["correlation"] = full
                res["evidence"] = _ev_ds(ctx, did, [cx, cy], full.get("n"))
                if full.get("status") == "insufficient_evidence" or full.get("r") is None:
                    res["status"] = "insufficient_evidence"
                    res["reason"] = "fewer than 3 complete pairs or zero variance"
                else:
                    res["assumptions"].append(
                        "Pearson assumes linearity + interval scale; outliers can dominate r "
                        "(inspect scatter before trusting)")
                    res["auto_summary"] = (
                        f"{cx} vs {cy}: r={_r(full['r'])} (n={full['n']}, p={_r(full.get('p'))}, "
                        f"95% CI [{_r(full['ci95_fisher_z'][0])}, {_r(full['ci95_fisher_z'][1])}])")
            elif typ == "regression":
                cx, cy = (a.get("columns") or [a.get("x"), a.get("y")])[:2]
                xs, ys = _col(rows, cx), _col(rows, cy)
                lr = w4kit.linreg(xs, ys)
                if lr is None:
                    res["status"] = "insufficient_evidence"
                    res["reason"] = "fewer than 2 complete pairs or zero x variance"
                else:
                    pairs = [(w4kit.to_float(x), w4kit.to_float(y))
                             for x, y in zip(xs, ys)]
                    pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
                    n = lr["n"]
                    resid = [y - (lr["slope"] * x + lr["intercept"]) for x, y in pairs]
                    s2 = sum(e2 ** 2 for e2 in resid) / (n - 2) if n > 2 else 0.0
                    mx = sum(x for x, _ in pairs) / n
                    sxx = sum((x - mx) ** 2 for x, _ in pairs)
                    se_slope = math.sqrt(s2 / sxx) if sxx > 0 and n > 2 else None
                    res["regression"] = dict(lr)
                    res["regression"]["residual_sd"] = math.sqrt(s2) if n > 2 else None
                    if se_slope:
                        t = lr["slope"] / se_slope
                        tc = t_crit(0.05, n - 2)
                        res["regression"].update({
                            "se_slope": se_slope, "t_slope": t, "df": n - 2,
                            "p_slope": t_p2(t, n - 2),
                            "ci95_slope": [lr["slope"] - tc * se_slope,
                                           lr["slope"] + tc * se_slope]})
                    res["evidence"] = _ev_ds(ctx, did, [cx, cy], n)
                    res["assumptions"].append(
                        "OLS assumes linear relation, independent errors, homoscedasticity; "
                        "residual diagnostics not plotted here")
                    res["auto_summary"] = (
                        f"{cy} = {_r(lr['slope'])}*{cx} + {_r(lr['intercept'])}; "
                        f"R^2={_r(lr['r2'])}, n={n}"
                        + (f", slope p={_r(res['regression'].get('p_slope'))}"
                           if se_slope else ""))
            else:
                res["status"] = "failed"
                res["reason"] = f"unknown analysis type '{typ}'"
        except Exception as ex:
            res["status"] = "failed"
            res["reason"] = f"{type(ex).__name__}: {ex}"
        if not res.get("interpretation"):
            res["interpretation_gap"] = "agent interpretation missing (human_confirm)"
        results.append(res)
        prov.append({"artifact": f"{prefix}stats_results.json", "item": aid,
                     "source_id": e.get("source_id"),
                     "locator": {"dataset_id": did, "type": typ,
                                 "column": a.get("column") or a.get("columns"),
                                 "status": res["status"]}})
    # multiplicity: Holm adjustment within declared families
    fams = {}
    for a, r in zip(analyses, results):
        fam = a.get("family")
        p = None
        for key in ("welch_t", "correlation", "anova", "regression"):
            blk = r.get(key) or {}
            p = blk.get("p") or blk.get("p_slope")
            if p is not None:
                break
        if fam and p is not None:
            fams.setdefault(fam, []).append((r, p))
    for fam, items in fams.items():
        ordered = sorted(items, key=lambda t: t[1])
        m = len(ordered)
        running = 0.0
        for i, (r, p) in enumerate(ordered):
            adj = min(1.0, max(running, (m - i) * p))
            running = adj
            r["p_adjusted_holm"] = adj
            r["family"] = fam
        for r, _ in items:
            r.setdefault("assumptions", []).append(
                f"multiplicity: Holm adjustment across family '{fam}' ({m} tests)")
    out = {"analyses": results, "n_analyses": len(results),
           "n_insufficient": sum(1 for r in results if r["status"] == "insufficient_evidence"),
           "n_failed": sum(1 for r in results if r["status"] == "failed"),
           "n_interpretation_gaps": sum(1 for r in results if r.get("interpretation_gap"))}
    w4kit.write_json(out_dir / f"{prefix}stats_results.json", out)
    outputs.append({"name": f"{prefix}stats_results.json",
                    "path": str(out_dir / f"{prefix}stats_results.json"),
                    "format": "json", "role": "json"})
    return out


# ── charts (stdlib SVG, every glyph data-bound; optional matplotlib PNG) ────

def _ticks(lo, hi, n=5):
    if hi <= lo:
        hi = lo + 1.0
    span = hi - lo
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = mag
    for m in (1, 2, 2.5, 5, 10):
        if raw <= mag * m:
            step = mag * m
            break
    v = math.ceil(lo / step) * step
    out = []
    while v <= hi + step * 1e-6:
        out.append(round(v, 10))
        v += step
    return out


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _svg_el(tag, attrs, content=None):
    a = " ".join(f'{k}="{_esc(v)}"' for k, v in attrs.items() if v is not None)
    if content is None:
        return f"<{tag} {a}/>"
    return f"<{tag} {a}>{_esc(content)}</{tag}>"


def _chart_data(chart, rows):
    """Resolve chart rows -> series structure + data_map (glyph -> source rows)."""
    ctype = chart["chart_type"]
    x, y = chart.get("x"), chart.get("y")
    gb = chart.get("group_by")
    agg = chart.get("aggregate", "mean")
    data_map, series, skipped = [], [], 0
    if ctype in ("scatter", "line"):
        groups = {}
        for ri, r in enumerate(rows):
            xv, yv = w4kit.to_float(r.get(x)), w4kit.to_float(r.get(y))
            if xv is None or yv is None:
                skipped += 1
                continue
            g = str(r.get(gb)) if gb else "all"
            groups.setdefault(g, []).append((ri, xv, yv))
        for g, pts in groups.items():
            if ctype == "line":
                pts = sorted(pts, key=lambda t: t[1])
            series.append({"name": g, "points": pts})
            for ri, xv, yv in pts:
                data_map.append({"glyph_id": f"{chart['chart_id']}-p{len(data_map)}",
                                 "dataset_id": chart.get("dataset_id"), "row_index": ri,
                                 "series": g, "x": xv, "y": yv,
                                 "x_column": x, "y_column": y})
    elif ctype == "bar":
        groups = {}
        for ri, r in enumerate(rows):
            g = str(r.get(x)) if r.get(x) is not None else "(missing)"
            groups.setdefault(g, []).append(ri)
        for g, idxs in groups.items():
            if y and agg != "count":
                vals = [w4kit.to_float(rows[i].get(y)) for i in idxs]
                vals = [v for v in vals if v is not None]
                if not vals:
                    skipped += len(idxs)
                    continue
                d = w4kit.describe(vals)
                val = {"mean": d["mean"], "sum": d["sum"],
                       "median": d["median"], "count": float(d["n"])}[agg]
                err = None
                eb = chart.get("error_bars")
                if eb in ("sd", "se", "ci95") and d["n"] >= 2:
                    err = d["sd"] if eb == "sd" else d["sd"] / math.sqrt(d["n"])
                    if eb == "ci95":
                        err = t_crit(0.05, d["n"] - 1) * d["sd"] / math.sqrt(d["n"])
                series.append({"name": g, "value": val, "n": d["n"], "err": err,
                               "err_kind": eb, "rows": idxs})
            else:
                series.append({"name": g, "value": float(len(idxs)), "n": len(idxs),
                               "err": None, "err_kind": None, "rows": idxs})
            data_map.append({"glyph_id": f"{chart['chart_id']}-b{len(data_map)}",
                             "dataset_id": chart.get("dataset_id"), "row_indices": idxs,
                             "category": g, "value": series[-1]["value"],
                             "aggregate": agg if y else "count", "y_column": y})
    elif ctype == "histogram":
        vals = [(ri, w4kit.to_float(r.get(x))) for ri, r in enumerate(rows)]
        vals = [(ri, v) for ri, v in vals if v is not None]
        skipped = len(rows) - len(vals)
        bins = int(chart.get("bins", 8))
        if vals:
            lo = min(v for _, v in vals)
            hi = max(v for _, v in vals)
            if hi == lo:
                hi = lo + 1
            width = (hi - lo) / bins
            counts = [[] for _ in range(bins)]
            for ri, v in vals:
                k = min(bins - 1, int((v - lo) / width))
                counts[k].append(ri)
            for k, idxs in enumerate(counts):
                series.append({"name": f"[{lo + k * width:g}, {lo + (k + 1) * width:g})",
                               "value": float(len(idxs)), "n": len(idxs),
                               "lo": lo + k * width, "hi": lo + (k + 1) * width,
                               "rows": idxs})
                data_map.append({"glyph_id": f"{chart['chart_id']}-h{k}",
                                 "dataset_id": chart.get("dataset_id"),
                                 "row_indices": idxs, "bin": k,
                                 "count": len(idxs), "x_column": x})
    elif ctype == "box":
        gcol = gb or x
        groups = {}
        for ri, r in enumerate(rows):
            g = str(r.get(gcol)) if r.get(gcol) is not None else "(missing)"
            v = w4kit.to_float(r.get(y)) if y else w4kit.to_float(r.get(x))
            if v is None:
                skipped += 1
                continue
            groups.setdefault(g, []).append((ri, v))
        for g, pts in groups.items():
            vals = [v for _, v in pts]
            d = w4kit.describe(vals)
            series.append({"name": g, "stats": d, "rows": [ri for ri, _ in pts]})
            data_map.append({"glyph_id": f"{chart['chart_id']}-x{len(data_map)}",
                             "dataset_id": chart.get("dataset_id"),
                             "row_indices": [ri for ri, _ in pts], "category": g,
                             "quartiles": {k: d[k] for k in ("min", "q25", "median", "q75", "max")},
                             "value_column": y or x})
    return series, data_map, skipped


def _render_svg(chart, series, data_map):
    W = float(chart.get("width_mm", 180))
    H = float(chart.get("height_mm", 120))
    L, R, T, B = 22, 8, 14, 20
    pw, ph = W - L - R, H - T - B
    ctype = chart["chart_type"]
    els = []
    # gather y values
    ys = []
    if ctype in ("scatter", "line"):
        ys = [p[2] for s in series for p in s["points"]]
    elif ctype in ("bar", "histogram"):
        ys = [s["value"] + (s.get("err") or 0) for s in series] + [0]
    elif ctype == "box":
        ys = [s["stats"][k] for s in series for k in ("min", "max")]
    if not ys:
        ys = [0, 1]
    ylo, yhi = min(ys), max(ys)
    if ctype in ("bar", "histogram"):
        ylo = min(0, ylo)
    pad = (yhi - ylo) * 0.05 or 1
    ylo -= pad
    yhi += pad
    if ctype in ("bar", "histogram"):
        ylo = 0 if min(ys) >= 0 else ylo
    ytk = _ticks(ylo, yhi)
    ylo, yhi = min(ylo, ytk[0]), max(yhi, ytk[-1])

    def Y(v):
        return T + ph - (v - ylo) / (yhi - ylo) * ph

    # axes + grid + ticks
    els.append(_svg_el("line", {"x1": L, "y1": T + ph, "x2": L + pw, "y2": T + ph,
                                "stroke": "#000", "stroke-width": 0.4, "id": "axis-x"}))
    els.append(_svg_el("line", {"x1": L, "y1": T, "x2": L, "y2": T + ph,
                                "stroke": "#000", "stroke-width": 0.4, "id": "axis-y"}))
    for v in ytk:
        yy = Y(v)
        els.append(_svg_el("line", {"x1": L, "y1": yy, "x2": L + pw, "y2": yy,
                                    "stroke": "#ddd", "stroke-width": 0.2}))
        els.append(_svg_el("text", {"x": L - 2, "y": yy, "font-size": "7pt",
                                    "text-anchor": "end", "dominant-baseline": "middle",
                                    "font-family": "DejaVu Sans, Arial, sans-serif"}, f"{v:g}"))
    els.append(_svg_el("text", {"x": L + pw / 2, "y": H - 4, "font-size": "8pt",
                                "text-anchor": "middle",
                                "font-family": "DejaVu Sans, Arial, sans-serif",
                                "id": "x-label"}, chart.get("x_label", chart.get("x", ""))))
    els.append(_svg_el("text", {"x": 4, "y": T + ph / 2, "font-size": "8pt",
                                "text-anchor": "middle", "transform": f"rotate(-90 4 {T + ph / 2})",
                                "font-family": "DejaVu Sans, Arial, sans-serif",
                                "id": "y-label"}, chart.get("y_label", chart.get("y", ""))))
    els.append(_svg_el("text", {"x": L + pw / 2, "y": 7, "font-size": "9pt",
                                "text-anchor": "middle", "font-weight": "bold",
                                "font-family": "DejaVu Sans, Arial, sans-serif",
                                "id": "title"}, chart.get("title", chart["chart_id"])))
    dm = {d["glyph_id"]: d for d in data_map}
    gid = 0
    if ctype in ("scatter", "line"):
        xs = [p[1] for s in series for p in s["points"]]
        xlo, xhi = min(xs), max(xs)
        xpad = (xhi - xlo) * 0.05 or 1
        xlo -= xpad
        xhi += xpad
        xtk = _ticks(xlo, xhi)
        xlo, xhi = min(xlo, xtk[0]), max(xhi, xtk[-1])

        def X(v):
            return L + (v - xlo) / (xhi - xlo) * pw
        for v in xtk:
            xx = X(v)
            els.append(_svg_el("line", {"x1": xx, "y1": T + ph, "x2": xx, "y2": T + ph + 1.5,
                                        "stroke": "#000", "stroke-width": 0.3}))
            els.append(_svg_el("text", {"x": xx, "y": T + ph + 5, "font-size": "7pt",
                                        "text-anchor": "middle",
                                        "font-family": "DejaVu Sans, Arial, sans-serif"}, f"{v:g}"))
        for si, s in enumerate(series):
            color = PALETTE[si % len(PALETTE)]
            if ctype == "line" and len(s["points"]) > 1:
                d = "M " + " L ".join(f"{X(p[1]):.3f} {Y(p[2]):.3f}" for p in s["points"])
                els.append(_svg_el("path", {"d": d, "fill": "none", "stroke": color,
                                            "stroke-width": 0.6,
                                            "data-series": s["name"],
                                            "id": f"{chart['chart_id']}-line{si}"}))
            for ri, xv, yv in s["points"]:
                g = f"{chart['chart_id']}-p{gid}"
                gid += 1
                els.append(_svg_el("circle", {"cx": X(xv), "cy": Y(yv), "r": 1.3,
                                              "fill": color, "fill-opacity": 0.85,
                                              "stroke": "#fff", "stroke-width": 0.2,
                                              "id": g, "data-series": s["name"],
                                              "data-row": ri, "data-x": xv, "data-y": yv,
                                              "data-source": dm.get(g, {}).get("dataset_id")}))
    elif ctype in ("bar", "histogram"):
        n = len(series)
        bw = pw / max(n, 1) * 0.7
        for si, s in enumerate(series):
            color = PALETTE[si % len(PALETTE)] if ctype == "bar" else "#0072B2"
            if ctype == "histogram":
                x0 = L + (s["lo"] - min(ss["lo"] for ss in series)) / (
                    max(ss["hi"] for ss in series) - min(ss["lo"] for ss in series)) * pw
                x1 = L + (s["hi"] - min(ss["lo"] for ss in series)) / (
                    max(ss["hi"] for ss in series) - min(ss["lo"] for ss in series)) * pw
                cx, w = x0, x1 - x0
            else:
                cx = L + (si + 0.5) * pw / n - bw / 2
                w = bw
            g = f"{chart['chart_id']}-b{gid}"
            gid += 1
            y0 = Y(s["value"])
            els.append(_svg_el("rect", {"x": cx, "y": y0, "width": w,
                                        "height": T + ph - y0, "fill": color,
                                        "fill-opacity": 0.85, "stroke": "#000",
                                        "stroke-width": 0.2, "id": g,
                                        "data-category": s["name"], "data-value": s["value"],
                                        "data-rows": ",".join(map(str, s["rows"])),
                                        "data-source": dm.get(g, {}).get("dataset_id")}))
            if s.get("err"):
                xm = cx + w / 2
                els.append(_svg_el("line", {"x1": xm, "y1": Y(s["value"] - s["err"]),
                                            "x2": xm, "y2": Y(s["value"] + s["err"]),
                                            "stroke": "#000", "stroke-width": 0.4,
                                            "data-error-kind": s["err_kind"],
                                            "data-rows": ",".join(map(str, s["rows"]))}))
            els.append(_svg_el("text", {"x": cx + w / 2, "y": T + ph + 5, "font-size": "6.5pt",
                                        "text-anchor": "middle",
                                        "font-family": "DejaVu Sans, Arial, sans-serif"},
                               s["name"][:18]))
    elif ctype == "box":
        n = len(series)
        for si, s in enumerate(series):
            d = s["stats"]
            cx = L + (si + 0.5) * pw / n
            bw = pw / max(n, 1) * 0.4
            color = PALETTE[si % len(PALETTE)]
            g = f"{chart['chart_id']}-x{gid}"
            gid += 1
            els.append(_svg_el("line", {"x1": cx, "y1": Y(d["min"]), "x2": cx,
                                        "y2": Y(d["max"]), "stroke": "#000",
                                        "stroke-width": 0.4, "data-rows": ",".join(map(str, s["rows"]))}))
            els.append(_svg_el("rect", {"x": cx - bw / 2, "y": Y(d["q75"]), "width": bw,
                                        "height": max(Y(d["q25"]) - Y(d["q75"]), 0.1),
                                        "fill": color, "fill-opacity": 0.6,
                                        "stroke": "#000", "stroke-width": 0.3, "id": g,
                                        "data-category": s["name"],
                                        "data-median": d["median"],
                                        "data-rows": ",".join(map(str, s["rows"])),
                                        "data-source": dm.get(g, {}).get("dataset_id")}))
            els.append(_svg_el("line", {"x1": cx - bw / 2, "y1": Y(d["median"]),
                                        "x2": cx + bw / 2, "y2": Y(d["median"]),
                                        "stroke": "#000", "stroke-width": 0.7}))
            els.append(_svg_el("text", {"x": cx, "y": T + ph + 5, "font-size": "6.5pt",
                                        "text-anchor": "middle",
                                        "font-family": "DejaVu Sans, Arial, sans-serif"},
                               s["name"][:18]))
    # legend (matches series names exactly)
    if len(series) > 1 and ctype in ("scatter", "line", "box"):
        for si, s in enumerate(series):
            ly = T + 3 + si * 5
            els.append(_svg_el("rect", {"x": L + pw - 28, "y": ly - 1.5, "width": 3,
                                        "height": 3, "fill": PALETTE[si % len(PALETTE)],
                                        "data-series": s["name"]}))
            els.append(_svg_el("text", {"x": L + pw - 24, "y": ly, "font-size": "6.5pt",
                                        "dominant-baseline": "middle",
                                        "font-family": "DejaVu Sans, Arial, sans-serif",
                                        "data-series": s["name"]}, s["name"][:20]))
    caption = chart.get("caption")
    if caption:
        els.append(_svg_el("text", {"x": L, "y": H - 11, "font-size": "6pt",
                                    "text-anchor": "start", "fill": "#444",
                                    "font-family": "DejaVu Sans, Arial, sans-serif",
                                    "id": "caption"}, caption[:110]))
    body = "\n".join(els)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:g}mm" height="{H:g}mm" '
            f'viewBox="0 0 {W:g} {H:g}">\n'
            f'<title>{_esc(chart.get("title", chart["chart_id"]))}</title>\n'
            f'<desc>Source-bound chart; every data glyph carries data-row/data-rows '
            f'attributes tracing to the registered dataset. Editable text and layers.</desc>\n'
            f'<rect x="0" y="0" width="{W:g}" height="{H:g}" fill="#ffffff" id="background"/>\n'
            f'<g id="chart-{_esc(chart["chart_id"])}">\n{body}\n</g>\n</svg>\n')


def _try_png(chart, series, path):
    """Optional matplotlib PNG. Honest fallback: return None if unavailable."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    try:
        fig, ax = plt.subplots(figsize=(7.1, 4.7), dpi=300)
        ctype = chart["chart_type"]
        if ctype in ("scatter", "line"):
            for si, s in enumerate(series):
                xs = [p[1] for p in s["points"]]
                ys = [p[2] for p in s["points"]]
                if ctype == "scatter":
                    ax.scatter(xs, ys, s=14, label=s["name"],
                               color=PALETTE[si % len(PALETTE)])
                else:
                    ax.plot(xs, ys, "-o", ms=3, label=s["name"],
                            color=PALETTE[si % len(PALETTE)])
        elif ctype in ("bar", "histogram"):
            names = [s["name"] for s in series]
            vals = [s["value"] for s in series]
            errs = [s.get("err") or 0 for s in series]
            ax.bar(range(len(names)), vals, yerr=errs if any(errs) else None,
                   color=[PALETTE[i % len(PALETTE)] for i in range(len(names))],
                   capsize=2)
            ax.set_xticks(range(len(names)))
            ax.set_xticklabels(names, rotation=45, ha="right", fontsize=7)
        elif ctype == "box":
            data = [[v for _, v in s["rows_vals"]] if "rows_vals" in s else
                    [s["stats"]["min"], s["stats"]["q25"], s["stats"]["median"],
                     s["stats"]["q75"], s["stats"]["max"]] for s in series]
            ax.boxplot(data, labels=[s["name"] for s in series])
        ax.set_xlabel(chart.get("x_label", chart.get("x", "")))
        ax.set_ylabel(chart.get("y_label", chart.get("y", "")))
        ax.set_title(chart.get("title", chart["chart_id"]), fontsize=10)
        if len(series) > 1 and ctype in ("scatter", "line"):
            ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(path, dpi=300)
        plt.close(fig)
        return str(path)
    except Exception:
        try:
            plt.close("all")
        except Exception:
            pass
        return None


def _run_charts(ir, case, ctx, out_dir, outputs, prov, charts=None, prefix=""):
    charts = charts if charts is not None else ir.get("charts", [])
    results = []
    for ch in charts:
        cid = ch.get("chart_id", "?")
        did = ch.get("dataset_id")
        e = ctx.get(did, {})
        rows = e.get("rows", [])
        res = {"chart_id": cid, "chart_type": ch.get("chart_type"),
               "dataset_id": did, "status": "rendered",
               "rationale": ch.get("rationale"), "caption": ch.get("caption"),
               "evidence": _ev_ds(ctx, did, ch.get("x"))}
        if not rows:
            res["status"] = "insufficient_evidence"
            res["reason"] = f"dataset empty or unreadable: {e.get('status')}"
            results.append(res)
            continue
        try:
            series, data_map, skipped = _chart_data(ch, rows)
            if not series:
                res["status"] = "insufficient_evidence"
                res["reason"] = "no plottable numeric rows after missing exclusion"
                results.append(res)
                continue
            svg = _render_svg(ch, series, data_map)
            sp = out_dir / f"{prefix}chart_{cid}.svg"
            sp.write_text(svg, encoding="utf-8")
            outputs.append({"name": sp.name, "path": str(sp), "format": "svg", "role": "svg"})
            res["n_glyphs"] = len(data_map)
            res["n_rows_skipped_missing"] = skipped
            res["series_names"] = [s["name"] for s in series]
            res["data_map"] = data_map
            png = _try_png(ch, series, out_dir / f"{prefix}chart_{cid}.png")
            if png:
                outputs.append({"name": Path(png).name, "path": png,
                                "format": "png", "role": "png"})
                res["png_status"] = "rendered (matplotlib, 300 dpi)"
            else:
                res["png_status"] = ("matplotlib unavailable or render failed; "
                                     "editable SVG is the authoritative artifact")
            if skipped:
                res["status"] = "partial"
                res["reason"] = f"{skipped} rows skipped (missing/non-numeric); see data_map"
            for g in data_map:
                prov.append({"artifact": sp.name, "item": g["glyph_id"],
                             "source_id": e.get("source_id"),
                             "locator": {"dataset_id": did,
                                         "row_index": g.get("row_index"),
                                         "row_indices": g.get("row_indices")}})
        except Exception as ex:
            res["status"] = "failed"
            res["reason"] = f"{type(ex).__name__}: {ex}"
        results.append(res)
    out = {"charts": results, "n_charts": len(results),
           "n_failed": sum(1 for r in results if r["status"] == "failed"),
           "n_insufficient": sum(1 for r in results if r["status"] == "insufficient_evidence"),
           "n_partial": sum(1 for r in results if r["status"] == "partial"),
           "n_glyphs_total": sum(r.get("n_glyphs", 0) for r in results)}
    w4kit.write_json(out_dir / f"{prefix}charts.json", out)
    outputs.append({"name": f"{prefix}charts.json", "path": str(out_dir / f"{prefix}charts.json"),
                    "format": "json", "role": "json"})
    return out


# ── code generation & execution ─────────────────────────────────────────────

_DANGER = re.compile(r"os\.system|subprocess|shutil\.rmtree|__import__|"
                     r"\beval\s*\(|\bexec\s*\(|socket|requests\.|urllib")


def _run_code(ir, case, ctx, out_dir, outputs, prov, prefix=""):
    code = ir.get("code", {})
    spec = code.get("spec", {})
    gen = code.get("generated", {})
    exec_cfg = code.get("exec", {})
    checks = code.get("checks", [])
    work = out_dir / f"{prefix}_code_work"
    work.mkdir(parents=True, exist_ok=True)
    # resolve generated source
    source = gen.get("source")
    if not source and gen.get("path"):
        f = _resolve(ir, case, gen["path"])
        if f:
            source = w4kit.read_text(f)
    result = {"spec": spec, "status": "executed", "checks": [],
              "execution_log": {}, "results": None}
    if not source:
        result["status"] = "failed"
        result["reason"] = "code.generated.source or .path required (agent writes real code)"
        w4kit.write_json(out_dir / f"{prefix}code_results.json", result)
        outputs.append({"name": f"{prefix}code_results.json",
                        "path": str(out_dir / f"{prefix}code_results.json"),
                        "format": "json", "role": "json"})
        return result
    code_path = out_dir / f"{prefix}analysis_code.py"
    code_path.write_text(source, encoding="utf-8")
    outputs.append({"name": code_path.name, "path": str(code_path),
                    "format": "py", "role": "code"})
    dangers = sorted(set(_DANGER.findall(source)))
    result["static_scan"] = {"warnings": dangers,
                             "note": "review flagged patterns before trusting execution"}
    mode = exec_cfg.get("mode", "subprocess")
    env_extra = dict(exec_cfg.get("env", {}))
    # pull actual cells from datasets into env when requested
    for name, ref in (exec_cfg.get("env_from_dataset") or {}).items():
        e = ctx.get(ref.get("dataset_id"), {})
        rows = e.get("rows", [])
        ri = int(ref.get("row", 0))
        if 0 <= ri < len(rows):
            env_extra[name] = rows[ri].get(ref.get("column"))
    t0 = time.time()
    if mode == "safe_eval":
        vals = {}
        errs = []
        for ex in exec_cfg.get("expressions", []):
            try:
                vals[ex["name"]] = w4kit.safe_eval(ex["expr"], env_extra)
            except Exception as e:
                errs.append({"name": ex.get("name"), "expr": ex.get("expr"),
                             "error": str(e)})
        result["results"] = vals
        result["execution_log"] = {
            "mode": "safe_eval (AST whitelist, w4kit)", "expressions": exec_cfg.get("expressions", []),
            "env": {k: v for k, v in env_extra.items()}, "errors": errs,
            "duration_s": _r(time.time() - t0, 3),
            "python": sys.version.split()[0], "platform": platform.platform()}
        if errs:
            result["status"] = "partial"
    else:
        timeout = float(exec_cfg.get("timeout_s", 120))
        cmd = [sys.executable, "-I", "-B", str(code_path.resolve())]
        run_env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                       ANALYSIS_INPUT=str(Path(case.get("input_dir", ".")).resolve()),
                       ANALYSIS_DATA=json.dumps(
                           {d: (str(Path(e["path"]).resolve()) if e.get("path") else None)
                            for d, e in ctx.items()}, ensure_ascii=False))
        try:
            proc = subprocess.run(cmd, cwd=str(work.resolve()), env=run_env,
                                  capture_output=True, text=True, timeout=timeout)
            stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            stdout, stderr, rc = "", f"timeout after {timeout}s", -1
        except Exception as e:
            stdout, stderr, rc = "", f"{type(e).__name__}: {e}", -1
        result["execution_log"] = {
            "mode": "subprocess (python -I -B, isolated)", "command": cmd,
            "cwd": str(work.resolve()), "exit_code": rc, "duration_s": _r(time.time() - t0, 3),
            "stdout": stdout[-20000:], "stderr": stderr[-20000:],
            "python": sys.version.split()[0], "platform": platform.platform()}
        # results: results.json in work dir, else last JSON line of stdout
        rj = work / "results.json"
        parsed = None
        if rj.exists():
            try:
                parsed = w4kit.load_json(rj)
            except Exception:
                pass
        if parsed is None:
            for line in reversed(stdout.strip().splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        parsed = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
        result["results"] = parsed
        if rc != 0:
            result["status"] = "failed"
            result["reason"] = f"exit code {rc}; see execution_log.stderr"
        elif parsed is None:
            result["status"] = "partial"
            result["reason"] = "code ran but produced no results.json / JSON stdout line"
    # verification checks against expected values (safe_eval over results env)
    env = dict(env_extra)
    if isinstance(result["results"], dict):
        for k, v in result["results"].items():
            if isinstance(v, (int, float)):
                env[k] = v
            elif isinstance(v, dict):
                for k2, v2 in v.items():
                    if isinstance(v2, (int, float)):
                        env[f"{k}_{k2}"] = v2
    for did, e in ctx.items():
        env[f"n_rows_{did}"] = e.get("n_rows", 0)
    n_pass = n_fail = 0
    for ck in checks:
        cid = ck.get("check_id", "?")
        cr = {"check_id": cid, "description": ck.get("description"),
              "expr": ck.get("expr"), "expected": ck.get("expected")}
        try:
            actual = w4kit.safe_eval(ck["expr"], env)
            tol = float(ck.get("tolerance", 1e-6))
            ok = abs(actual - float(ck["expected"])) <= tol
            cr.update({"actual": actual, "tolerance": tol,
                       "status": "pass" if ok else "fail"})
            n_pass += ok
            n_fail += (not ok)
        except Exception as e:
            cr.update({"status": "error", "error": str(e)})
            n_fail += 1
        result["checks"].append(cr)
    result["verification"] = {"n_checks": len(checks), "n_pass": n_pass,
                              "n_fail": n_fail,
                              "ok": n_fail == 0 and len(checks) > 0}
    if n_fail and result["status"] == "executed":
        result["status"] = "partial"
    prov.append({"artifact": code_path.name, "item": "generated_code",
                 "source_id": (ir.get("sources") or [{}])[0].get("id"),
                 "locator": {"spec": spec.get("task"), "mode": mode}})
    w4kit.write_json(out_dir / f"{prefix}code_results.json", result)
    outputs.append({"name": f"{prefix}code_results.json",
                    "path": str(out_dir / f"{prefix}code_results.json"),
                    "format": "json", "role": "json"})
    w4kit.write_json(out_dir / f"{prefix}execution_log.json", result["execution_log"])
    outputs.append({"name": f"{prefix}execution_log.json",
                    "path": str(out_dir / f"{prefix}execution_log.json"),
                    "format": "json", "role": "exec_log_json"})
    return result


# ── database query & analysis (READ-ONLY) ───────────────────────────────────

def _db_path(ir, case, ctx, ds, out_dir):
    """Real .db -> use read-only. Provided .sql dump -> restore working copy."""
    e = ctx.get(ds.get("dataset_id"), {})
    p = e.get("path")
    if not p:
        return None, "db file not found"
    p = Path(p)
    if p.suffix.lower() == ".sql":
        work = out_dir / "_db_work"
        work.mkdir(parents=True, exist_ok=True)
        copy = work / (p.stem + ".db")
        if not copy.exists():
            import sqlite3
            con = sqlite3.connect(str(copy))
            try:
                con.executescript(w4kit.read_text(p))
                con.commit()
            finally:
                con.close()
        return str(copy), ("working copy restored from provided SQL dump; "
                           "original dump never modified; queries run mode=ro")
    return str(p), "organizer database opened read-only (mode=ro); never written"


def _run_queries(ir, case, ctx, out_dir, outputs, prov, queries=None, prefix=""):
    queries = queries if queries is not None else ir.get("queries", [])
    results, log, schema = [], [], {}
    for q in queries:
        qid = q.get("query_id", "?")
        did = q.get("dataset_id")
        ds = _dataset(ir, did) or {}
        res = {"query_id": qid, "question": q.get("question"), "sql": q.get("sql"),
               "params": q.get("params", []), "dataset_id": did,
               "interpretation": q.get("interpretation"), "status": "ok"}
        t0 = time.time()
        dbp, note = _db_path(ir, case, ctx, ds, out_dir)
        res["db_note"] = note
        if dbp is None:
            res["status"] = "failed"
            res["error"] = note
            results.append(res)
            log.append({"query_id": qid, "status": "failed", "error": note})
            continue
        try:
            if did not in schema:
                tables = w4kit.sqlite_tables(dbp)
                schema[did] = {"tables": {t: w4kit.sqlite_query(
                    dbp, f"PRAGMA table_info({t})")["rows"] for t in tables},
                    "db_path": dbp, "note": note}
            sql = q.get("sql", "")
            params = tuple(q.get("params", []))
            n_ph = sql.count("?")
            if n_ph != len(params):
                raise ValueError(f"placeholder count {n_ph} != params {len(params)}")
            out = w4kit.sqlite_query(dbp, sql, params)
            max_rows = int(q.get("max_rows", 500))
            truncated = out["row_count"] > max_rows
            res.update({"columns": out["columns"], "row_count": out["row_count"],
                        "rows": out["rows"][:max_rows], "truncated": truncated,
                        "duration_s": _r(time.time() - t0, 4),
                        "evidence": {"source_id": ds.get("source_id"),
                                     "dataset_id": did, "db": dbp, "sql": sql,
                                     "params": list(params)}})
            if not res.get("interpretation"):
                res["interpretation_gap"] = "agent interpretation missing (human_confirm)"
            if out["row_count"] == 0:
                res["empty_result_note"] = "query returned 0 rows; verify filters/keys"
            cp = _write_csv(out_dir / f"{prefix}query_{qid}.csv", out["columns"],
                            [dict(zip(out["columns"], r)) for r in out["rows"][:max_rows]])
            outputs.append({"name": Path(cp).name, "path": cp, "format": "csv", "role": "csv"})
            # join-inflation sanity warning
            joins = len(re.findall(r"\bJOIN\b", sql, re.I))
            if joins and not re.search(r"\bON\b|\bWHERE\b", sql, re.I):
                res["join_warning"] = "multi-table query without ON/WHERE: row inflation risk"
            prov.append({"artifact": Path(cp).name, "item": qid,
                         "source_id": ds.get("source_id"),
                         "locator": {"db": dbp, "sql": sql, "params": list(params),
                                     "row_count": out["row_count"]}})
        except Exception as e:
            res["status"] = "failed"
            res["error"] = f"{type(e).__name__}: {e}"
            res["duration_s"] = _r(time.time() - t0, 4)
        results.append(res)
        log.append({"query_id": qid, "sql": q.get("sql"), "params": q.get("params", []),
                    "status": res["status"], "row_count": res.get("row_count"),
                    "error": res.get("error"), "duration_s": res.get("duration_s"),
                    "db": dbp, "read_only": True})
    out = {"queries": results, "schema": schema, "query_log": log,
           "n_queries": len(results),
           "n_failed": sum(1 for r in results if r["status"] == "failed"),
           "n_empty": sum(1 for r in results if r.get("row_count") == 0),
           "n_interpretation_gaps": sum(1 for r in results if r.get("interpretation_gap")),
           "n_join_warnings": sum(1 for r in results if r.get("join_warning"))}
    w4kit.write_json(out_dir / f"{prefix}query_results.json", out)
    outputs.append({"name": f"{prefix}query_results.json",
                    "path": str(out_dir / f"{prefix}query_results.json"),
                    "format": "json", "role": "json"})
    w4kit.write_json(out_dir / f"{prefix}query_log.json", log)
    outputs.append({"name": f"{prefix}query_log.json",
                    "path": str(out_dir / f"{prefix}query_log.json"),
                    "format": "json", "role": "query_log_json"})
    return out


# ── multi-step orchestration ────────────────────────────────────────────────

def _run_steps(ir, case, ctx, out_dir, outputs, prov):
    steps = ir.get("steps", [])
    done, failed = {}, set()
    step_results = []
    for st in steps:
        sid = st.get("step_id", "?")
        skind = st.get("kind")
        deps = st.get("depends_on", [])
        prefix = f"step_{sid}_"
        sr = {"step_id": sid, "kind": skind, "depends_on": deps, "status": "done",
              "inputs": [], "outputs": []}
        blocked = [d for d in deps if d in failed or d not in done]
        if blocked:
            sr["status"] = "skipped"
            sr["reason"] = f"upstream step(s) not completed: {blocked}"
            failed.add(sid)
            step_results.append(sr)
            continue
        n_out_before = len(outputs)
        payload = st.get("payload", {})
        try:
            if skind == "load":
                for did in payload.get("dataset_ids", list(ctx.keys())):
                    e = ctx.get(did, {})
                    sr["inputs"].append({"dataset_id": did, "sha256": e.get("sha256"),
                                         "n_rows": e.get("n_rows"), "status": e.get("status")})
                    if e.get("status") not in ("ok", "ir_inline"):
                        sr["status"] = "partial"
                        sr.setdefault("issues", []).append(f"{did}: {e.get('status')}")
            elif skind == "clean":
                part = _run_cleaning(ir, case, ctx, out_dir, outputs, prov,
                                     ops=payload.get("operations", []), prefix=prefix)
                sr["summary"] = {k: part[k] for k in ("n_operations", "n_failed_ops", "n_changes")}
                sr["consistency_ok"] = part["consistency_check"]["ok"]
                if part["n_failed_ops"] or not part["consistency_check"]["ok"]:
                    sr["status"] = "partial"
            elif skind == "stats":
                part = _run_stats(ir, case, ctx, out_dir, outputs, prov,
                                  analyses=payload.get("analyses", []), prefix=prefix)
                sr["summary"] = {k: part[k] for k in ("n_analyses", "n_insufficient", "n_failed")}
                done_metrics = {}
                for r in part["analyses"]:
                    for key in ("describe", "welch_t", "correlation", "regression", "anova"):
                        if isinstance(r.get(key), dict):
                            for mk, mv in r[key].items():
                                if isinstance(mv, (int, float)):
                                    done_metrics[f"{r['analysis_id']}.{mk}"] = mv
                sr["metrics"] = done_metrics
                if part["n_insufficient"] or part["n_failed"]:
                    sr["status"] = "partial"
            elif skind == "viz":
                part = _run_charts(ir, case, ctx, out_dir, outputs, prov,
                                   charts=payload.get("charts", []), prefix=prefix)
                sr["summary"] = {k: part[k] for k in ("n_charts", "n_failed",
                                                      "n_insufficient", "n_partial")}
                if part["n_failed"] or part["n_insufficient"]:
                    sr["status"] = "partial"
            elif skind == "query":
                part = _run_queries(ir, case, ctx, out_dir, outputs, prov,
                                    queries=payload.get("queries", []), prefix=prefix)
                sr["summary"] = {k: part[k] for k in ("n_queries", "n_failed", "n_empty")}
                if part["n_failed"]:
                    sr["status"] = "partial"
            elif skind == "interpret":
                text = payload.get("text", "")
                claims = payload.get("claims", [])
                all_metrics = {}
                for prev in step_results:
                    all_metrics.update(prev.get("metrics", {}))
                checked = []
                for cl in claims:
                    ref = cl.get("metric")
                    actual = all_metrics.get(ref)
                    ok = (actual is not None and
                          abs(float(cl.get("value", 0)) - float(actual)) <=
                          float(cl.get("tolerance", 1e-4)))
                    checked.append({"metric": ref, "claimed": cl.get("value"),
                                    "computed": actual, "status": "pass" if ok else "fail"})
                sr["backfill_check"] = checked
                sr["text"] = text
                if not text:
                    sr["status"] = "partial"
                    sr["reason"] = "interpretation text missing"
                elif any(c["status"] == "fail" for c in checked):
                    sr["status"] = "partial"
                    sr["reason"] = "report numbers do not match computed metrics"
            else:
                sr["status"] = "failed"
                sr["reason"] = f"unknown step kind '{skind}'"
        except Exception as e:
            sr["status"] = "failed"
            sr["reason"] = f"{type(e).__name__}: {e}"
        sr["outputs"] = [o["name"] for o in outputs[n_out_before:]]
        if sr["status"] in ("failed",):
            failed.add(sid)
        done[sid] = sr["status"]
        prov.append({"artifact": "pipeline", "item": sid,
                     "source_id": (ir.get("sources") or [{}])[0].get("id"),
                     "locator": {"kind": skind, "depends_on": deps, "status": sr["status"],
                                 "outputs": sr["outputs"]}})
        step_results.append(sr)
    out = {"steps": step_results, "n_steps": len(step_results),
           "n_failed": sum(1 for s in step_results if s["status"] == "failed"),
           "n_skipped": sum(1 for s in step_results if s["status"] == "skipped"),
           "n_partial": sum(1 for s in step_results if s["status"] == "partial"),
           "n_backfill_fail": sum(1 for s in step_results
                                  for c in s.get("backfill_check", []) if c["status"] == "fail")}
    w4kit.write_json(out_dir / "pipeline.json", out)
    outputs.append({"name": "pipeline.json", "path": str(out_dir / "pipeline.json"),
                    "format": "json", "role": "json"})
    return out


# ── validation ──────────────────────────────────────────────────────────────

def validate_ir(ir: dict) -> dict:
    errors, warnings = [], []
    if ir.get("ir_version") != IR_VERSION:
        errors.append(f"ir_version must be {IR_VERSION}")
    if not ir.get("case_id"):
        errors.append("case_id required")
    kind = ir.get("kind")
    if kind not in KINDS:
        errors.append(f"unknown kind '{kind}' (expected one of {sorted(KINDS)})")
    sources = ir.get("sources", [])
    sids = [s.get("id") for s in sources]
    if not sources:
        errors.append("sources[] empty: register every actual input file used")
    if len(sids) != len(set(sids)):
        errors.append("duplicate source ids")
    for s in sources:
        if not s.get("path"):
            errors.append(f"source {s.get('id')}: path required (actual file location)")
    errors += w4kit.check_sources(ir)
    datasets = ir.get("datasets", [])
    dids = [d.get("dataset_id") for d in datasets]
    if not datasets:
        errors.append("datasets[] empty: register the actual data table(s)/database(s)")
    if len(dids) != len(set(dids)):
        errors.append("duplicate dataset_id")
    dset = set(dids)
    for d in datasets:
        did = d.get("dataset_id", "?")
        if d.get("source_id") not in set(sids):
            errors.append(f"dataset {did}: source_id not registered in sources[]")
        if not d.get("path") and d.get("rows") is None:
            errors.append(f"dataset {did}: path (actual file) or inline rows required")

    def _chk_ds(ref, where):
        if ref and ref not in dset:
            errors.append(f"{where}: dataset_id '{ref}' not registered")

    if kind == "data_cleaning":
        ops = ir.get("cleaning", {}).get("operations", [])
        if not ops:
            errors.append("data_cleaning requires cleaning.operations[]")
        oids = [o.get("op_id") for o in ops]
        if len(oids) != len(set(oids)):
            errors.append("duplicate op_id")
        for o in ops:
            oid = o.get("op_id", "?")
            if o.get("type") not in OP_TYPES:
                errors.append(f"op {oid}: invalid type '{o.get('type')}'")
            _chk_ds(o.get("dataset_id"), f"op {oid}")
            if o.get("type") in ("dedup", "drop_rows", "outlier_flag") and not o.get("reason"):
                warnings.append(f"op {oid}: destructive/diagnostic op without reason")
            if o.get("type") == "dedup" and not o.get("params", {}).get("key_columns"):
                errors.append(f"op {oid}: dedup requires params.key_columns (real primary key)")
            if o.get("type") == "unit_convert":
                p = o.get("params", {})
                if not p.get("factor_expr"):
                    errors.append(f"op {oid}: unit_convert requires params.factor_expr")
                if not (p.get("from_unit") and p.get("to_unit")):
                    warnings.append(f"op {oid}: unit_convert without from/to unit labels")
    elif kind == "stats_analysis":
        analyses = ir.get("stats", {}).get("analyses", [])
        if not analyses:
            errors.append("stats_analysis requires stats.analyses[]")
        for a in analyses:
            aid = a.get("analysis_id", "?")
            if a.get("type") not in STAT_TYPES:
                errors.append(f"analysis {aid}: invalid type '{a.get('type')}'")
            _chk_ds(a.get("dataset_id"), f"analysis {aid}")
            if a.get("type") == "describe" and not a.get("column"):
                errors.append(f"analysis {aid}: describe requires column")
            if a.get("type") == "compare_groups" and not (
                    a.get("column") and a.get("group_column")):
                errors.append(f"analysis {aid}: compare_groups requires column + group_column")
            if a.get("type") in ("correlation", "regression") and not (
                    a.get("columns") or (a.get("x") and a.get("y"))):
                errors.append(f"analysis {aid}: {a['type']} requires columns [x, y]")
            if not a.get("interpretation"):
                warnings.append(f"analysis {aid}: no agent interpretation (will be flagged)")
    elif kind == "data_viz":
        charts = ir.get("charts", [])
        if not charts:
            errors.append("data_viz requires charts[]")
        cids = [c.get("chart_id") for c in charts]
        if len(cids) != len(set(cids)):
            errors.append("duplicate chart_id")
        for c in charts:
            cid = c.get("chart_id", "?")
            if c.get("chart_type") not in CHART_TYPES:
                errors.append(f"chart {cid}: invalid chart_type '{c.get('chart_type')}'")
            _chk_ds(c.get("dataset_id"), f"chart {cid}")
            if not c.get("x"):
                errors.append(f"chart {cid}: x column required")
            if c.get("chart_type") in ("scatter", "line") and not c.get("y"):
                errors.append(f"chart {cid}: {c['chart_type']} requires y column")
            if not c.get("caption"):
                warnings.append(f"chart {cid}: no caption (units/error-bar definition)")
    elif kind == "code_gen_exec":
        code = ir.get("code", {})
        if not code.get("spec"):
            errors.append("code_gen_exec requires code.spec (task + inputs)")
        gen = code.get("generated", {})
        if not (gen.get("source") or gen.get("path")):
            errors.append("code.generated.source or .path required (real runnable code)")
        if not code.get("checks"):
            warnings.append("code.checks[] empty: results will not be verified against expected")
        for ck in code.get("checks", []):
            if not (ck.get("expr") and ck.get("expected") is not None):
                errors.append(f"check {ck.get('check_id', '?')}: expr + expected required")
    elif kind == "db_query_analysis":
        queries = ir.get("queries", [])
        if not queries:
            errors.append("db_query_analysis requires queries[]")
        for q in queries:
            qid = q.get("query_id", "?")
            if not q.get("sql"):
                errors.append(f"query {qid}: sql required")
            _chk_ds(q.get("dataset_id"), f"query {qid}")
            s = (q.get("sql") or "").strip().lstrip("(").lstrip().upper()
            if s and not (s.startswith("SELECT") or s.startswith("WITH") or s.startswith("PRAGMA")):
                errors.append(f"query {qid}: only read-only SELECT/WITH/PRAGMA allowed")
            if not q.get("interpretation"):
                warnings.append(f"query {qid}: no agent interpretation (will be flagged)")
    elif kind == "multi_step_analysis":
        steps = ir.get("steps", [])
        if not steps:
            errors.append("multi_step_analysis requires steps[]")
        seen = set()
        for st in steps:
            sid = st.get("step_id", "?")
            if st.get("kind") not in STEP_KINDS:
                errors.append(f"step {sid}: invalid kind '{st.get('kind')}'")
            for d in st.get("depends_on", []):
                if d not in seen:
                    errors.append(f"step {sid}: depends_on '{d}' must be an earlier step")
            seen.add(sid)
    if not ir.get("provenance", {}).get("pipeline"):
        ir.setdefault("provenance", {})["pipeline"] = \
            "actual material -> IR -> validate -> compute -> artifact -> result"
    return {"ok": not errors, "errors": errors, "warnings": warnings}


# ── provenance / report / build ─────────────────────────────────────────────

def _provenance(ir, ctx, items, parts):
    return {"pipeline": ir.get("provenance", {}).get("pipeline"),
            "generated_at": w4kit.utc_now(),
            "sources": [{"id": s.get("id"), "path": s.get("path"),
                         "sha256": next((e.get("sha256") for e in ctx.values()
                                         if e.get("source_id") == s.get("id")), None),
                         "description": s.get("description")}
                        for s in ir.get("sources", [])],
            "datasets": {d: {"status": e.get("status"), "n_rows": e.get("n_rows"),
                             "sha256": e.get("sha256"), "path": e.get("path"),
                             "cleaned": e.get("cleaned", False)}
                         for d, e in ctx.items()},
            "items": items,
            "changes": ir.get("provenance", {}).get("changes", [])}


def _report_md(ir, case, ctx, parts, prov):
    kind = ir.get("kind")
    L = [f"# Analysis report — {kind}", f"", f"case_id: `{case.get('case_id')}`",
         f"generated: {w4kit.utc_now()}  ", ""]
    L.append("## Data inventory (actual files)")
    L.append("| dataset | source | status | rows | sha256 (first 12) |")
    L.append("|---|---|---|---|---|")
    for d, e in ctx.items():
        L.append(f"| {d} | {e.get('source_id')} | {e.get('status')} | {e.get('n_rows')} | "
                 f"{(e.get('sha256') or '')[:12]} |")
    L.append("")
    if "cleaning" in parts:
        c = parts["cleaning"]
        L.append("## Cleaning")
        L.append(f"- operations: {c['n_operations']} (failed: {c['n_failed_ops']}), "
                 f"logged changes: {c['n_changes']}")
        L.append(f"- report/table consistency self-check: "
                 f"{'OK' if c['consistency_check']['ok'] else 'MISMATCH — see cleaning_log.json'}")
        for did, q in c["quality"].items():
            L.append(f"- {did}: rows {q['n_rows_before']} → {q['n_rows_after']}; "
                     f"missing flagged {q['n_missing_flagged']}, outliers {q['n_outliers_flagged']}, "
                     f"unit conversions {q['n_unit_conversions']}, duplicates removed {q['n_duplicates_removed']}")
        L.append("- original snapshots preserved; every change carries row locator + rule + evidence")
        L.append("")
    if "stats" in parts:
        L.append("## Statistical results (recomputed from data)")
        for r in parts["stats"]["analyses"]:
            L.append(f"### {r['analysis_id']} ({r['type']}) — {r['status']}")
            if r.get("auto_summary"):
                L.append(f"- computed: {r['auto_summary']}")
            if r.get("interpretation"):
                L.append(f"- interpretation (agent): {r['interpretation']}")
            for a in r.get("assumptions", []):
                L.append(f"- assumption/caveat: {a}")
            if r.get("reason"):
                L.append(f"- gap: {r['reason']}")
            L.append("")
    if "charts" in parts:
        L.append("## Charts (every glyph traces to data rows)")
        for r in parts["charts"]["charts"]:
            L.append(f"- {r['chart_id']} ({r['chart_type']}): {r['status']}, "
                     f"glyphs={r.get('n_glyphs', 0)}, skipped_missing={r.get('n_rows_skipped_missing', 0)}")
            if r.get("rationale"):
                L.append(f"  - chart choice rationale: {r['rationale']}")
            if r.get("caption"):
                L.append(f"  - caption: {r['caption']}")
            L.append(f"  - PNG: {r.get('png_status', 'n/a')}")
        L.append("")
    if "code" in parts:
        c = parts["code"]
        L.append("## Code generation & execution")
        L.append(f"- status: {c['status']}; mode: {c['execution_log'].get('mode')}")
        L.append(f"- exit code: {c['execution_log'].get('exit_code', 'n/a')}")
        v = c.get("verification", {})
        L.append(f"- verification: {v.get('n_pass', 0)}/{v.get('n_checks', 0)} checks passed")
        for ck in c.get("checks", []):
            L.append(f"  - {ck['check_id']}: {ck['status']} "
                     f"(actual={ck.get('actual')}, expected={ck.get('expected')})")
        L.append("")
    if "queries" in parts:
        L.append("## Database queries (read-only)")
        for r in parts["queries"]["queries"]:
            L.append(f"### {r['query_id']} — {r['status']}")
            L.append(f"- question: {r.get('question')}")
            L.append(f"- sql: `{r.get('sql')}` params={r.get('params')}")
            L.append(f"- rows: {r.get('row_count', 'n/a')}"
                     + (" (truncated in json; full csv exported)" if r.get("truncated") else ""))
            if r.get("interpretation"):
                L.append(f"- interpretation (agent): {r['interpretation']}")
            if r.get("error"):
                L.append(f"- error: {r['error']}")
            L.append("")
    if "steps" in parts:
        L.append("## Pipeline steps")
        for s in parts["steps"]["steps"]:
            L.append(f"- {s['step_id']} ({s['kind']}): {s['status']}"
                     + (f" — {s['reason']}" if s.get("reason") else ""))
            if s.get("backfill_check"):
                for c in s["backfill_check"]:
                    L.append(f"  - backfill {c['metric']}: claimed {c['claimed']} vs "
                             f"computed {c['computed']} → {c['status']}")
        L.append("")
    L.append("## Uncertainty & limits")
    unc = ir.get("uncertainty", [])
    if unc:
        for u in unc:
            L.append(f"- {u.get('item')}: {u.get('reason')} (handling: {u.get('handling', 'human_confirm')})")
    else:
        L.append("- none declared by agent; engine gaps (if any) are listed above")
    L.append("")
    L.append("## Reproducibility")
    L.append("- rerun: `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> "
             "--input /input --out /app/output`")
    L.append("- provenance.json maps every artifact item to source file + locator; "
             "dataset sha256 recorded at load time")
    return "\n".join(L)


def build(ir: dict, case: dict, out_dir) -> list:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs, prov = [], []
    ctx = _load_all(ir, case, out_dir, outputs, prov)
    kind = ir.get("kind")
    parts = {}
    if kind == "data_cleaning":
        parts["cleaning"] = _run_cleaning(ir, case, ctx, out_dir, outputs, prov)
    elif kind == "stats_analysis":
        parts["stats"] = _run_stats(ir, case, ctx, out_dir, outputs, prov)
    elif kind == "data_viz":
        parts["charts"] = _run_charts(ir, case, ctx, out_dir, outputs, prov)
    elif kind == "code_gen_exec":
        parts["code"] = _run_code(ir, case, ctx, out_dir, outputs, prov)
    elif kind == "db_query_analysis":
        parts["queries"] = _run_queries(ir, case, ctx, out_dir, outputs, prov)
    elif kind == "multi_step_analysis":
        parts["steps"] = _run_steps(ir, case, ctx, out_dir, outputs, prov)
    prov_obj = _provenance(ir, ctx, prov, parts)
    w4kit.write_json(out_dir / "provenance.json", prov_obj)
    outputs.append({"name": "provenance.json", "path": str(out_dir / "provenance.json"),
                    "format": "json", "role": "provenance_json"})
    md = _report_md(ir, case, ctx, parts, prov_obj)
    (out_dir / "report.md").write_text(md, encoding="utf-8")
    outputs.append({"name": "report.md", "path": str(out_dir / "report.md"),
                    "format": "md", "role": "md"})
    # summary for honest status
    summary = {"n_datasets": len(ctx),
               "n_datasets_unusable": sum(1 for e in ctx.values()
                                          if e["status"] not in ("ok", "ir_inline")),
               "n_column_mismatches": sum(1 for e in ctx.values() if e.get("column_mismatch")),
               "n_hash_mismatches": sum(1 for e in ctx.values() if e.get("hash_mismatch"))}
    if "cleaning" in parts:
        c = parts["cleaning"]
        summary.update({"n_operations": c["n_operations"], "n_failed_ops": c["n_failed_ops"],
                        "n_changes": c["n_changes"],
                        "n_consistency_mismatches": len(c["consistency_check"]["mismatches"])})
    if "stats" in parts:
        s = parts["stats"]
        summary.update({"n_analyses": s["n_analyses"], "n_insufficient": s["n_insufficient"],
                        "n_failed_stats": s["n_failed"],
                        "n_interpretation_gaps": s["n_interpretation_gaps"]})
    if "charts" in parts:
        c = parts["charts"]
        summary.update({"n_charts": c["n_charts"], "n_failed_charts": c["n_failed"],
                        "n_insufficient_charts": c["n_insufficient"],
                        "n_partial_charts": c["n_partial"], "n_glyphs": c["n_glyphs_total"]})
    if "code" in parts:
        c = parts["code"]
        summary.update({"code_status": c["status"],
                        "n_checks_failed": c.get("verification", {}).get("n_fail", 0),
                        "n_checks": c.get("verification", {}).get("n_checks", 0)})
    if "queries" in parts:
        q = parts["queries"]
        summary.update({"n_queries": q["n_queries"], "n_failed_queries": q["n_failed"],
                        "n_empty_queries": q["n_empty"],
                        "n_query_interpretation_gaps": q["n_interpretation_gaps"],
                        "n_join_warnings": q["n_join_warnings"]})
    if "steps" in parts:
        s = parts["steps"]
        summary.update({"n_steps": s["n_steps"], "n_failed_steps": s["n_failed"],
                        "n_skipped_steps": s["n_skipped"], "n_partial_steps": s["n_partial"],
                        "n_backfill_fail": s["n_backfill_fail"]})
    (out_dir / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False),
                                           encoding="utf-8")
    return outputs


def compute_status(ir: dict, validation: dict, summary: dict) -> str:
    if validation.get("errors"):
        return "partial"
    gap_keys = ("n_datasets_unusable", "n_column_mismatches", "n_hash_mismatches",
                "n_failed_ops", "n_consistency_mismatches", "n_insufficient",
                "n_failed_stats", "n_interpretation_gaps", "n_failed_charts",
                "n_insufficient_charts", "n_partial_charts", "n_checks_failed",
                "n_failed_queries", "n_empty_queries", "n_query_interpretation_gaps",
                "n_join_warnings", "n_failed_steps", "n_skipped_steps",
                "n_partial_steps", "n_backfill_fail")
    if any(summary.get(k) for k in gap_keys):
        return "partial"
    if summary.get("code_status") in ("failed", "partial"):
        return "partial"
    if ir.get("uncertainty"):
        return "partial"
    return "success"