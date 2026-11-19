"""w4kit — shared source-bound core for ALL week4 tracks (stdlib only).

Every week4 case is an organizer-provided LOCAL material task: read the actual
files, produce a structured artifact whose every claim/field/record points back
to a source locator, and report honest status/uncertainty. No live remote calls,
no fabricated data. This module is the common substrate the per-track engines
import; it never imports matplotlib/numpy at module load so validation and result
assembly work in a minimal environment (stats helpers import numpy lazily).

Conventions
-----------
* evidence locator = {source_id, paragraph_id?, page?, quote?, table?, field?}
* record status    = reported | not_reported | source_conflict | extraction_failed
                     | inferred | insufficient_evidence
* result status    = success | partial | failed | stuck
* build_result() echoes EVERY original output_contract key and adds case_id,
  status, sources, uncertainty, change_log, provenance, validation.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import json
import math
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

IR_VERSION = "1.0"
SKILL_VERSION = "4.0.0"

VALID_STATUS = {"success", "partial", "failed", "stuck"}
RECORD_STATUS = {
    "reported", "not_reported", "source_conflict", "extraction_failed",
    "inferred", "insufficient_evidence", "supported", "partially_supported",
    "contradicted", "unknown",
}


# ── basic io ────────────────────────────────────────────────────────────────

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def read_text(path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


# ── case loading ────────────────────────────────────────────────────────────

def load_case(input_dir="/input") -> dict:
    input_dir = Path(input_dir)
    case = {}
    cp = input_dir / "case.json"
    if cp.exists():
        case = load_json(cp)
    task_md = ""
    tp = input_dir / "task.md"
    if tp.exists():
        task_md = tp.read_text(encoding="utf-8", errors="replace")
    case_id = (case.get("case_id") or case.get("id") or case.get("caseId")
               or os.environ.get("CASE_ID") or "unknown-case")
    contract = (case.get("output_contract") or case.get("outputContract")
                or case.get("outputs") or {})
    return {"case_id": str(case_id), "raw": case, "task_md": task_md,
            "output_contract": contract, "input_dir": str(input_dir)}


def list_materials(input_dir="/input") -> list:
    input_dir = Path(input_dir)
    out = []
    if not input_dir.exists():
        return out
    for p in sorted(input_dir.rglob("*")):
        if p.is_file():
            out.append({"path": str(p), "name": p.name,
                        "bytes": p.stat().st_size, "ext": p.suffix.lower()})
    return out


def find_input(input_dir, *names) -> str | None:
    """Locate a named workorder/material file under input (recursive)."""
    input_dir = Path(input_dir)
    for n in names:
        direct = input_dir / n
        if direct.exists():
            return str(direct)
        hits = list(input_dir.rglob(n))
        if hits:
            return str(hits[0])
    return None


# ── evidence & sources ──────────────────────────────────────────────────────

def evidence(source_id, paragraph_id=None, quote=None, page=None,
             table=None, field=None) -> dict:
    ev = {"source_id": source_id}
    if paragraph_id is not None:
        ev["paragraph_id"] = paragraph_id
    if page is not None:
        ev["page"] = page
    if quote is not None:
        ev["quote"] = quote
    if table is not None:
        ev["table"] = table
    if field is not None:
        ev["field"] = field
    return ev


def check_sources(ir: dict) -> list:
    """Every evidence locator must reference a registered source id."""
    errors = []
    ids = {s.get("id") for s in ir.get("sources", []) if s.get("id")}
    def walk(o):
        if isinstance(o, dict):
            if "source_id" in o and o["source_id"] not in ids:
                errors.append(f"evidence references unknown source '{o['source_id']}'")
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk({k: v for k, v in ir.items() if k != "sources"})
    return errors


# ── tabular data ────────────────────────────────────────────────────────────

def read_table(path) -> list:
    path = Path(path)
    if path.suffix.lower() == ".json":
        data = load_json(path)
        if isinstance(data, dict):
            for key in ("data", "rows", "records", "table"):
                if isinstance(data.get(key), list):
                    return data[key]
            cols = {k: v for k, v in data.items() if isinstance(v, list)}
            if cols:
                n = max(len(v) for v in cols.values())
                return [{k: (v[i] if i < len(v) else None) for k, v in cols.items()}
                        for i in range(n)]
        return data if isinstance(data, list) else []
    delim = "\t" if path.suffix.lower() in (".tsv", ".tab") else ","
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=delim))


def to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    m = re.match(r"^[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
    return float(m.group(0)) if m else None


def sqlite_tables(db_path) -> list:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        return [r[0] for r in rows]
    finally:
        con.close()


def sqlite_query(db_path, sql, params=()) -> dict:
    """Read-only SELECT execution. Returns columns+rows; refuses non-SELECT."""
    s = sql.strip().lstrip("(").lstrip().upper()
    if not (s.startswith("SELECT") or s.startswith("WITH") or s.startswith("PRAGMA")):
        raise ValueError("only read-only SELECT/WITH/PRAGMA queries are allowed")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = con.execute(sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [list(r) for r in cur.fetchall()]
        return {"columns": cols, "rows": rows, "row_count": len(rows)}
    finally:
        con.close()


# ── safe arithmetic (AST whitelist; no arbitrary eval) ──────────────────────

_BIN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
        ast.Pow: lambda a, b: a ** b, ast.Mod: lambda a, b: a % b,
        ast.FloorDiv: lambda a, b: a // b}
_UN = {ast.USub: lambda a: -a, ast.UAdd: lambda a: a}
_FN = {"sqrt": math.sqrt, "exp": math.exp, "log": math.log, "ln": math.log,
       "log10": math.log10, "abs": abs, "sin": math.sin, "cos": math.cos,
       "tan": math.tan, "floor": math.floor, "ceil": math.ceil}


def _ev(node, env):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in env:
            return float(env[node.id])
        if node.id in _FN:
            return _FN[node.id]
        if node.id in ("pi", "e"):
            return math.pi if node.id == "pi" else math.e
        raise ValueError(f"unknown symbol {node.id}")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_ev(node.left, env), _ev(node.right, env))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
        return _UN[type(node.op)](_ev(node.operand, env))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = _FN.get(node.func.id)
        if fn and 1 <= len(node.args) <= 2:
            return fn(*[_ev(a, env) for a in node.args])
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in ("min", "max") and node.args:
        vals = [_ev(a, env) for a in node.args]
        return min(vals) if node.func.id == "min" else max(vals)
    raise ValueError("unsupported expression")


def safe_eval(expr: str, env: dict) -> float:
    return _ev(ast.parse(expr, mode="eval").body, env)


# ── descriptive statistics (numpy lazy; stdlib fallback) ────────────────────

def describe(values) -> dict:
    nums = [to_float(v) for v in values]
    nums = [x for x in nums if x is not None and not math.isnan(x)]
    n = len(nums)
    if n == 0:
        return {"n": 0, "missing": len(values)}
    mean = sum(nums) / n
    var = sum((x - mean) ** 2 for x in nums) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    s = sorted(nums)
    def quantile(q):
        if n == 1:
            return s[0]
        pos = (n - 1) * q
        lo = int(math.floor(pos)); hi = int(math.ceil(pos))
        return s[lo] + (s[hi] - s[lo]) * (pos - lo)
    return {"n": n, "missing": len(values) - n, "mean": mean, "sd": sd,
            "var": var, "min": s[0], "max": s[-1],
            "q25": quantile(0.25), "median": quantile(0.5),
            "q75": quantile(0.75), "sum": sum(nums)}


def correlation(xs, ys) -> float | None:
    pairs = [(to_float(a), to_float(b)) for a, b in zip(xs, ys)]
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    n = len(pairs)
    if n < 2:
        return None
    mx = sum(a for a, _ in pairs) / n
    my = sum(b for _, b in pairs) / n
    cov = sum((a - mx) * (b - my) for a, b in pairs)
    vx = sum((a - mx) ** 2 for a, _ in pairs)
    vy = sum((b - my) ** 2 for _, b in pairs)
    if vx == 0 or vy == 0:
        return None
    return cov / math.sqrt(vx * vy)


def linreg(xs, ys) -> dict | None:
    pairs = [(to_float(a), to_float(b)) for a, b in zip(xs, ys)]
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    n = len(pairs)
    if n < 2:
        return None
    mx = sum(a for a, _ in pairs) / n
    my = sum(b for _, b in pairs) / n
    sxx = sum((a - mx) ** 2 for a, _ in pairs)
    if sxx == 0:
        return None
    sxy = sum((a - mx) * (b - my) for a, b in pairs)
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_res = sum((b - (slope * a + intercept)) ** 2 for a, b in pairs)
    ss_tot = sum((b - my) ** 2 for _, b in pairs)
    r2 = 1 - ss_res / ss_tot if ss_tot else None
    return {"n": n, "slope": slope, "intercept": intercept, "r2": r2}


# ── record normalization & dedup (search / library) ─────────────────────────

def normalize_doi(doi) -> str | None:
    if not doi:
        return None
    s = str(doi).strip().lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s)
    s = re.sub(r"^doi:\s*", "", s)
    s = s.strip().rstrip(".")
    return s or None


def normalize_title(t) -> str:
    if not t:
        return ""
    s = str(t).lower()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _title_sim(a, b) -> float:
    ta, tb = set(normalize_title(a).split()), set(normalize_title(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def dedup_records(records: list) -> dict:
    """Group records by DOI exact match then fuzzy title+year. Returns merged
    clusters with provenance (which input records merged) and conflict notes.
    Never silently drops a record; every input id appears in exactly one cluster.
    """
    clusters = []
    by_doi = {}
    for i, r in enumerate(records):
        rid = r.get("id", f"rec{i}")
        doi = normalize_doi(r.get("doi"))
        placed = False
        if doi and doi in by_doi:
            by_doi[doi]["members"].append(rid)
            by_doi[doi]["records"].append(r)
            placed = True
        else:
            for c in clusters:
                rep = c["records"][0]
                same_year = (r.get("year") and rep.get("year")
                             and str(r["year"]) == str(rep["year"]))
                if _title_sim(r.get("title", ""), rep.get("title", "")) >= 0.85 \
                        and (same_year or not r.get("year") or not rep.get("year")):
                    c["members"].append(rid)
                    c["records"].append(r)
                    c["match"] = "fuzzy_title_year"
                    placed = True
                    break
        if not placed:
            c = {"cluster_id": f"C{len(clusters)+1:03d}", "members": [rid],
                 "records": [r], "match": "doi" if doi else "singleton"}
            clusters.append(c)
            if doi:
                by_doi[doi] = c
    # field-level conflicts within a cluster
    for c in clusters:
        conflicts = []
        for fld in ("title", "year", "journal", "authors"):
            vals = []
            for r in c["records"]:
                v = r.get(fld)
                if v and str(v) not in vals:
                    vals.append(str(v))
            if len(vals) > 1:
                conflicts.append({"field": fld, "values": vals})
        c["conflicts"] = conflicts
        c["n_members"] = len(c["members"])
    return {"n_input": len(records), "n_clusters": len(clusters),
            "n_duplicates_removed": len(records) - len(clusters),
            "clusters": clusters}


# ── result.json assembly (preserves output_contract) ────────────────────────

def build_result(case: dict, ir: dict, outputs: list, status: str,
                 validation=None, extra=None, notes="") -> dict:
    contract = case.get("output_contract") or {}
    result = {}
    by_role, by_name = {}, {}
    for o in outputs:
        by_role.setdefault(o.get("role", o.get("format", "")), o)
        by_name.setdefault(o.get("name", ""), o)

    def fill_key(key):
        kl = key.lower()
        for role in ("json", "result", "md", "markdown", "csv", "svg", "png",
                     "pdf", "docx", "pptx", "tex", "html", "txt"):
            if role in kl and role in by_role:
                return by_role[role].get("path")
        if "result" in kl or "json" in kl or "meta" in kl:
            return "result.json"
        return None

    if isinstance(contract, dict):
        for key, spec in contract.items():
            filled = fill_key(key)
            if filled:
                result[key] = filled
            elif isinstance(spec, dict) and "default" in spec:
                result[key] = spec["default"]
            else:
                result[key] = {"_contract_spec": spec,
                               "_status": "see artifacts/provenance"}
    elif isinstance(contract, list):
        result["output_contract"] = contract

    result["case_id"] = case.get("case_id")
    result["status"] = status if status in VALID_STATUS else "partial"
    result["skill_version"] = SKILL_VERSION
    result["kind"] = ir.get("kind")
    result["generated_at"] = utc_now()
    result["artifacts"] = outputs
    result["sources"] = ir.get("sources", [])
    result["uncertainty"] = ir.get("uncertainty", [])
    result["change_log"] = ir.get("provenance", {}).get("changes", [])
    result["provenance"] = ir.get("provenance", {})
    if validation is not None:
        result["validation"] = validation
    if extra:
        result.update(extra)
    if notes:
        result["notes"] = notes
    if status in ("partial", "failed", "stuck"):
        result["limits"] = ir.get("uncertainty", []) or [
            {"item": "see notes", "reason": notes or "incomplete"}]
    return result


def write_result(out_dir, result) -> str:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "result.json"
    write_json(path, result)
    return str(path)


def base_ir(case: dict, kind: str) -> dict:
    """Skeleton IR every engine starts from; agent fills domain fields."""
    return {"ir_version": IR_VERSION, "case_id": case.get("case_id"),
            "kind": kind, "sources": [], "uncertainty": [],
            "provenance": {"pipeline": "material -> IR -> validate -> artifact -> result",
                           "changes": []}}