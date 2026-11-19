"""experiment_engine — deterministic source-bound engine for the week4 EXPERIMENT track.

Covers all five experiment workorder kinds over organizer-provided LOCAL material
(real scientific sources, prospective resource/price/booking contracts, versioned
candidate plans, finite parameter domains, actual result tables):

  protocol_design   objective -> hypothesis/variables/steps/controls/params/risks
                    + optimization suggestions; coverage of the six rubric elements
  feasibility       per-item equipment/reagent/time/safety/budget/ethics review vs
                    actual inventory; feasible/risk/blocker verdicts + overall score
  param_optimize    recommended value + feasible range + rationale per parameter;
                    reported optimum vs inferred suggestion; safe_eval numeric checks
  protocol_compare  candidates x criteria matrix with per-cell locators; min-max
                    normalization + weighted score + ranking + weight sensitivity
  result_anomaly    expected vs observed (tolerance arithmetic), replicate stats,
                    IQR outlier flags, ranked candidate causes (never facts), actions

The Agent reads the ACTUAL /input material and fills the IR; this engine validates,
computes and builds editable artifacts. Every verdict/number carries a source
locator (source_id + paragraph_id/field/table + quote). Nothing is fabricated:
missing information is not_reported / insufficient_evidence + human_confirm,
reported vs inferred is distinguished, and evidence quotes are verified against
the actual paragraph text when the source file is readable.

API:  validate_ir(ir) -> {ok, errors, warnings}
      build(ir, case, out_dir) -> outputs[]   (w4kit artifact descriptors)
      compute_status(ir, validation, summary) -> success | partial

Stdlib only; imports w4kit (shared core, copied next to this file).
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import w4kit

IR_VERSION = "1.0"
KINDS = {"protocol_design", "feasibility", "param_optimize",
         "protocol_compare", "result_anomaly"}
ITEM_STATUS = {"reported", "inferred", "not_reported", "source_conflict",
               "extraction_failed", "insufficient_evidence"}
VERDICTS = {"feasible", "risk", "blocker", "not_reported"}
FEAS_CATEGORIES = {"equipment", "reagent", "time", "safety", "budget",
                   "ethics", "personnel", "other"}
CONTROL_TYPES = {"blank", "positive", "negative", "dose_gradient", "other"}
VAR_ROLES = {"independent", "dependent", "confounder", "controlled"}
SUPPORT = {"supported", "partially_supported", "contradicted", "unknown"}
SUPPORT_WEIGHT = {"supported": 3, "partially_supported": 1, "unknown": 0,
                  "contradicted": -1}
DIRECTIONS = {"higher_better", "lower_better"}


# ── small helpers ───────────────────────────────────────────────────────────

def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _num(v):
    return w4kit.to_float(v)


def _evs(e) -> list:
    """Normalize evidence (dict | list[dict] | None) to a list of locator dicts."""
    if isinstance(e, dict):
        return [e]
    if isinstance(e, list):
        return [x for x in e if isinstance(x, dict)]
    return []


def _has_ev(e) -> bool:
    return any(x.get("source_id") for x in _evs(e))


def _resolve(ir: dict, case: dict, rel):
    if not rel:
        return None
    p = Path(rel)
    if p.is_absolute():
        return p if p.exists() else None
    for b in (ir.get("_ir_dir"), (case or {}).get("input_dir"), "."):
        if b and (Path(b) / p).exists():
            return Path(b) / p
    return None


def _source(ir, sid):
    return next((s for s in ir.get("sources", []) if s.get("id") == sid), None)


def _paragraphs(text: str) -> list:
    out = []
    for i, block in enumerate(re.split(r"\n\s*\n", text)):
        t = block.strip()
        if t:
            out.append({"id": f"p{i + 1}", "text": t})
    return out


def _doc_paragraphs(ir, case, doc) -> list:
    if doc.get("paragraphs"):
        return [{"id": p.get("id", f"p{i + 1}"), "text": p.get("text", "")}
                for i, p in enumerate(doc["paragraphs"])]
    src = _source(ir, doc.get("source_id")) or {}
    f = _resolve(ir, case, doc.get("content_path") or doc.get("path") or src.get("path"))
    if f is not None and f.is_file() and f.suffix.lower() in (
            ".txt", ".md", ".text", ".csv", ".tsv", ".json", ".log"):
        try:
            return _paragraphs(w4kit.read_text(f))
        except OSError:
            return []
    return []


def _quote_issues(ir, case, ev: dict, paras_by_src: dict) -> str | None:
    """Verify a quote against actual paragraph text. Returns issue string or None."""
    quote, pid = ev.get("quote"), ev.get("paragraph_id")
    if not quote or not pid:
        return None
    paras = paras_by_src.get(ev.get("source_id"))
    if not paras:
        return None  # unreadable/binary source: cannot verify, not an error
    par = next((p for p in paras if p["id"] == pid), None)
    if par is None:
        return f"paragraph '{pid}' not found in source '{ev.get('source_id')}'"
    if _norm(quote) not in _norm(par["text"]):
        return f"quote not found in paragraph '{pid}' of '{ev.get('source_id')}'"
    return None


def _range_pair(r):
    """Accept [lo,hi] or {min,max} -> (lo,hi) floats or (None,None)."""
    if isinstance(r, (list, tuple)) and len(r) == 2:
        return _num(r[0]), _num(r[1])
    if isinstance(r, dict):
        return _num(r.get("min", r.get("lo"))), _num(r.get("max", r.get("hi")))
    return None, None


def _walk_claims(obj, path="$"):
    """Yield (json-path, evidence-dict) for every locator embedded in an artifact."""
    if isinstance(obj, dict):
        if obj.get("source_id") and ("quote" in obj or "paragraph_id" in obj
                                     or "field" in obj or "table" in obj
                                     or set(obj) <= {"source_id", "page"}):
            yield path, obj
        for k, v in obj.items():
            yield from _walk_claims(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_claims(v, f"{path}[{i}]")


# ── validation ──────────────────────────────────────────────────────────────

def _check_status_evidence(where, status, ev, errors, warnings, *,
                           allow_no_ev=("not_reported", "extraction_failed",
                                        "insufficient_evidence")):
    if status and status not in ITEM_STATUS:
        errors.append(f"{where}: invalid status '{status}'")
    if status in ("reported", "source_conflict") and not _has_ev(ev):
        errors.append(f"{where}: status {status} requires an evidence locator")
    if status == "inferred":
        if not _has_ev(ev):
            warnings.append(f"{where}: inferred without evidence locator")
    if status in allow_no_ev and not _has_ev(ev):
        warnings.append(f"{where}: {status} (gap flagged, not fabricated)")


def _validate_design(ir, errors, warnings):
    obj = ir.get("objective") or {}
    if not obj.get("statement"):
        errors.append("objective.statement required (the research goal)")
    if not obj.get("hypothesis"):
        warnings.append("objective.hypothesis missing: goal not yet testable")
    design = ir.get("design") or {}
    steps = design.get("steps") or ir.get("steps") or []
    if not steps:
        errors.append("design.steps[] empty: a protocol needs executable steps")
    sids = []
    for st in steps:
        sid = st.get("step_id", "?")
        sids.append(sid)
        if not st.get("action"):
            errors.append(f"step {sid}: action text required")
        if not _has_ev(st.get("evidence")):
            warnings.append(f"step {sid}: no evidence locator (design basis untraceable)")
        for p in st.get("parameters", []):
            lo, hi = _range_pair(p.get("range"))
            v = _num(p.get("value"))
            if lo is not None and hi is not None and lo > hi:
                errors.append(f"step {sid} param {p.get('name')}: range lo>hi")
            if v is not None and lo is not None and hi is not None and not (lo <= v <= hi):
                warnings.append(f"step {sid} param {p.get('name')}: value {v} outside range [{lo},{hi}]")
            if not p.get("unit"):
                warnings.append(f"step {sid} param {p.get('name')}: no unit")
        for eq in st.get("equipment", []):
            if not eq.get("model") and not eq.get("spec"):
                warnings.append(f"step {sid} equipment {eq.get('name')}: no model/spec")
    if len(sids) != len(set(sids)):
        errors.append("duplicate step_id")
    controls = design.get("controls") or ir.get("controls") or []
    if not controls:
        warnings.append("design.controls[] empty: no confounder exclusion designed")
    ctypes = set()
    for c in controls:
        if c.get("type") not in CONTROL_TYPES:
            errors.append(f"control {c.get('control_id', '?')}: type must be one of {sorted(CONTROL_TYPES)}")
        ctypes.add(c.get("type"))
        if not c.get("purpose"):
            warnings.append(f"control {c.get('control_id', '?')}: purpose (which confounder it excludes) missing")
        if not _has_ev(c.get("evidence")):
            warnings.append(f"control {c.get('control_id', '?')}: no evidence locator")
    if controls and ctypes <= {"blank"}:
        warnings.append("only blank control(s): consider positive/negative/gradient controls")
    for v in ir.get("variables", []):
        if v.get("role") not in VAR_ROLES:
            errors.append(f"variable {v.get('name', '?')}: role must be one of {sorted(VAR_ROLES)}")
        if not v.get("operational_definition"):
            warnings.append(f"variable {v.get('name', '?')}: no operational definition")
    for o in design.get("optimizations") or ir.get("optimizations") or []:
        if not o.get("suggestion"):
            errors.append(f"optimization {o.get('id', '?')}: suggestion required")
        _check_status_evidence(f"optimization {o.get('id', '?')}",
                               o.get("status", "inferred"), o.get("evidence"),
                               errors, warnings)
        if not o.get("rationale"):
            warnings.append(f"optimization {o.get('id', '?')}: rationale missing")
    for r in ir.get("risks", []):
        if not r.get("failure_mode"):
            errors.append(f"risk {r.get('id', '?')}: failure_mode required")
        if not r.get("criterion") and not r.get("stop_loss"):
            warnings.append(f"risk {r.get('id', '?')}: no judgement criterion / stop-loss")


def _validate_feasibility(ir, errors, warnings):
    items = ir.get("items") or []
    if not items:
        errors.append("items[] empty: feasibility review needs protocol requirement items")
    inv = ir.get("inventory") or []
    iids = [i.get("id") for i in inv]
    if len(iids) != len(set(iids)):
        errors.append("duplicate inventory id")
    invset = set(iids)
    if not inv:
        warnings.append("inventory[] empty: availability cannot be verified (not_reported)")
    for it in items:
        iid = it.get("item_id", "?")
        if it.get("category") not in FEAS_CATEGORIES:
            errors.append(f"item {iid}: category must be one of {sorted(FEAS_CATEGORIES)}")
        if not it.get("requirement"):
            errors.append(f"item {iid}: requirement text required (quote the protocol)")
        if not _has_ev(it.get("evidence")):
            warnings.append(f"item {iid}: no evidence locator for the requirement")
        if it.get("inventory_id") and it["inventory_id"] not in invset:
            errors.append(f"item {iid}: inventory_id '{it['inventory_id']}' not registered")
        if it.get("verdict") and it["verdict"] not in VERDICTS:
            errors.append(f"item {iid}: invalid verdict '{it['verdict']}'")
        for f in ("needed_qty", "available_qty", "needed_hours", "window_hours",
                  "needed_cost", "budget_cap"):
            if it.get(f) is not None and _num(it.get(f)) is None:
                errors.append(f"item {iid}: {f} must be numeric")
    for iv in inv:
        if not iv.get("name"):
            errors.append(f"inventory {iv.get('id', '?')}: name required")
        if not _has_ev(iv.get("evidence")):
            warnings.append(f"inventory {iv.get('id', '?')}: no evidence locator")


def _validate_params(ir, errors, warnings):
    params = ir.get("params") or []
    if not params:
        errors.append("params[] empty: parameter optimization needs key parameters")
    names = []
    limits = {l.get("param"): l for l in ir.get("limits") or []}
    for p in params:
        nm = p.get("name", "?")
        names.append(nm)
        if p.get("recommended") is None and p.get("source_optimum") is None:
            errors.append(f"param {nm}: recommended or source_optimum required")
        st = p.get("status", "inferred")
        _check_status_evidence(f"param {nm}", st, p.get("evidence"), errors, warnings)
        if st == "reported" and p.get("source_optimum") is None:
            warnings.append(f"param {nm}: status reported but no source_optimum quoted")
        if not p.get("rationale"):
            warnings.append(f"param {nm}: rationale missing")
        lo, hi = _range_pair(p.get("range"))
        if lo is not None and hi is not None and lo > hi:
            errors.append(f"param {nm}: range lo>hi")
        rec = _num(p.get("recommended"))
        if rec is not None and lo is not None and hi is not None and not (lo <= rec <= hi):
            warnings.append(f"param {nm}: recommended {rec} outside feasible range [{lo},{hi}]")
        lim = limits.get(nm)
        if lim:
            llo, lhi = _range_pair(lim.get("range") or [lim.get("min"), lim.get("max")])
            if rec is not None and llo is not None and lhi is not None and not (llo <= rec <= lhi):
                warnings.append(f"param {nm}: recommended {rec} outside device/material limit [{llo},{lhi}]")
        if not p.get("unit"):
            warnings.append(f"param {nm}: no unit")
    if len(names) != len(set(names)):
        errors.append("duplicate param name")
    for l in ir.get("limits") or []:
        if not _has_ev(l.get("evidence")):
            warnings.append(f"limit {l.get('param', '?')}: no evidence (device manual / material spec)")
    for c in ir.get("numeric_checks") or []:
        if not c.get("expr"):
            errors.append(f"numeric_check {c.get('id', '?')}: expr required")
    for o in ir.get("observations") or []:
        if o.get("param") not in names:
            warnings.append(f"observation references unknown param '{o.get('param')}'")
        if not _has_ev(o.get("evidence")):
            warnings.append("observation without evidence locator (data row untraceable)")


def _comparison(ir) -> dict:
    comp = ir.get("comparison") or {}
    criteria = comp.get("criteria") or ir.get("criteria") or []
    candidates = comp.get("candidates") or ir.get("candidates") or []
    weights = comp.get("weights") or ir.get("weights") or {}
    matrix = comp.get("matrix") if comp.get("matrix") is not None else ir.get("matrix")
    cells = []
    if isinstance(matrix, list):
        cells = [c for c in matrix if isinstance(c, dict)]
    elif isinstance(matrix, dict):
        for cid, row in matrix.items():
            if isinstance(row, dict):
                for cand, cell in row.items():
                    if isinstance(cell, dict):
                        cells.append(dict(cell, criterion_id=cid, candidate_id=cand))
                    else:
                        cells.append({"criterion_id": cid, "candidate_id": cand,
                                      "value": cell, "status": "reported"})
    return {"criteria": criteria, "candidates": candidates,
            "weights": weights, "cells": cells}


def _validate_compare(ir, errors, warnings):
    comp = _comparison(ir)
    criteria, candidates, cells = comp["criteria"], comp["candidates"], comp["cells"]
    if not criteria:
        errors.append("comparison.criteria[] empty")
    if len(candidates) < 2:
        errors.append("comparison needs >=2 candidates (versioned plans)")
    cids = [c.get("id") for c in criteria]
    candids = [c.get("id") for c in candidates]
    if len(cids) != len(set(cids)):
        errors.append("duplicate criterion id")
    if len(candids) != len(set(candids)):
        errors.append("duplicate candidate id")
    for c in criteria:
        if c.get("direction") not in DIRECTIONS:
            errors.append(f"criterion {c.get('id', '?')}: direction must be higher_better/lower_better")
        w = _num(c.get("weight", comp["weights"].get(c.get("id"))))
        if w is None or w < 0:
            errors.append(f"criterion {c.get('id', '?')}: weight must be numeric >=0")
    for cand in candidates:
        if not cand.get("source_id") and not cand.get("protocol_id"):
            warnings.append(f"candidate {cand.get('id', '?')}: no source_id/protocol_id")
    pids = {p.get("id") for p in ir.get("protocols", [])}
    for cand in candidates:
        if cand.get("protocol_id") and cand["protocol_id"] not in pids:
            errors.append(f"candidate {cand.get('id')}: protocol_id '{cand['protocol_id']}' not registered")
    seen = set()
    for cell in cells:
        key = (cell.get("criterion_id"), cell.get("candidate_id"))
        if key in seen:
            errors.append(f"duplicate matrix cell {key}")
        seen.add(key)
        if cell.get("criterion_id") not in cids:
            errors.append(f"matrix cell references unknown criterion '{cell.get('criterion_id')}'")
        if cell.get("candidate_id") not in candids:
            errors.append(f"matrix cell references unknown candidate '{cell.get('candidate_id')}'")
        st = cell.get("status", "reported")
        _check_status_evidence(f"cell {key}", st, cell.get("evidence"), errors, warnings)
        if st in ("reported", "inferred") and _num(cell.get("value")) is None \
                and _num(cell.get("score")) is None:
            warnings.append(f"cell {key}: non-numeric value without score (excluded from weighting)")
    missing = [(cid, cand) for cid in cids for cand in candids if (cid, cand) not in seen]
    for cid, cand in missing:
        warnings.append(f"matrix missing cell ({cid},{cand}): treated as not_reported")


def _validate_anomaly(ir, errors, warnings):
    results = ir.get("results") or []
    if not results:
        errors.append("results[] empty: interpretation needs the actual metrics")
    for r in results:
        m = r.get("metric", "?")
        if r.get("observed") is None:
            errors.append(f"result {m}: observed value(s) required")
        if not _has_ev(r.get("evidence")):
            warnings.append(f"result {m}: no evidence locator (data file/field)")
        if r.get("expected") is None:
            warnings.append(f"result {m}: expected value not reported (within-tolerance unknown)")
        tol = r.get("tolerance")
        if tol is not None and _num(tol) is None and not isinstance(tol, dict):
            errors.append(f"result {m}: tolerance must be numeric or {{abs,pct}}")
    for a in ir.get("anomalies") or []:
        aid = a.get("id", "?")
        if not a.get("observation"):
            errors.append(f"anomaly {aid}: observation required")
        causes = a.get("candidate_causes") or []
        if not causes:
            warnings.append(f"anomaly {aid}: no candidate causes (insufficient_evidence)")
        for c in causes:
            sup = c.get("support", "unknown")
            if sup not in SUPPORT:
                errors.append(f"anomaly {aid} cause '{c.get('cause', '?')}': support must be one of {sorted(SUPPORT)}")
            if sup in ("supported", "partially_supported", "contradicted") and not _has_ev(c.get("evidence")):
                errors.append(f"anomaly {aid} cause '{c.get('cause', '?')}': support={sup} requires evidence (never assert a cause as fact without data)")
            if not c.get("cause"):
                errors.append(f"anomaly {aid}: cause text required")
        if not a.get("action"):
            warnings.append(f"anomaly {aid}: corrective action missing")


_KIND_VALIDATORS = {
    "protocol_design": _validate_design,
    "feasibility": _validate_feasibility,
    "param_optimize": _validate_params,
    "protocol_compare": _validate_compare,
    "result_anomaly": _validate_anomaly,
}


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
            errors.append(f"source {s.get('id', '?')}: path required (the actual file)")
    errors += w4kit.check_sources(ir)
    dids = [d.get("id", d.get("document_id")) for d in ir.get("documents", [])]
    if len(dids) != len(set(dids)):
        errors.append("duplicate document id")
    pids = [p.get("id") for p in ir.get("protocols", [])]
    if len(pids) != len(set(pids)):
        errors.append("duplicate protocol id")
    for p in ir.get("protocols", []):
        if not p.get("source_id"):
            warnings.append(f"protocol {p.get('id', '?')}: no source_id")
    if kind in _KIND_VALIDATORS:
        try:
            _KIND_VALIDATORS[kind](ir, errors, warnings)
        except Exception as e:  # malformed IR: honest error, never crash
            errors.append(f"kind validation crashed on malformed IR: {type(e).__name__}: {e}")
    if not ir.get("provenance", {}).get("pipeline"):
        ir.setdefault("provenance", {})["pipeline"] = \
            "actual material -> IR -> validate -> compute -> artifact -> result"
    return {"ok": not errors, "errors": errors, "warnings": warnings}


# ── kind builders (deterministic computation) ───────────────────────────────

def _build_design(ir, case):
    obj = ir.get("objective") or {}
    design = ir.get("design") or {}
    steps_in = design.get("steps") or ir.get("steps") or []
    steps, violations, total_min, total_cost = [], [], 0.0, 0.0
    have_time = have_cost = have_eq = have_range = False
    groups = {}
    for st in steps_in:
        params = []
        for p in st.get("parameters", []):
            lo, hi = _range_pair(p.get("range"))
            v = _num(p.get("value"))
            in_range = None
            if v is not None and lo is not None and hi is not None:
                in_range = lo <= v <= hi
                have_range = True
                if not in_range:
                    violations.append({"step_id": st.get("step_id"),
                                       "param": p.get("name"), "value": v,
                                       "range": [lo, hi]})
            params.append(dict(p, in_range=in_range))
        dur = _num(st.get("duration_min"))
        if dur is not None:
            have_time = True
            g = st.get("parallel_group")
            if g:
                groups[g] = max(groups.get(g, 0.0), dur)
            else:
                total_min += dur
        cost = _num(st.get("cost"))
        if cost is not None:
            have_cost = True
            total_cost += cost
        if st.get("equipment") or st.get("reagents"):
            have_eq = True
        steps.append(dict(st, parameters=params))
    total_min += sum(groups.values())
    controls = design.get("controls") or ir.get("controls") or []
    optimizations = design.get("optimizations") or ir.get("optimizations") or []
    variables = ir.get("variables", [])
    risks = ir.get("risks", [])
    budget_cap = _num(obj.get("budget_cap"))
    coverage = {
        "hypothesis_variables": bool(obj.get("hypothesis")) and bool(variables),
        "controls": bool(controls),
        "equipment_materials": have_eq,
        "time_cost": have_time or have_cost,
        "parameter_ranges": have_range,
        "risks_anomalies": bool(risks),
    }
    confirmations = list(ir.get("confirmations") or [])
    for o in optimizations:
        if o.get("status", "inferred") == "inferred":
            confirmations.append({"item": f"optimization {o.get('id')}",
                                  "reason": "inferred suggestion, not a reported fact",
                                  "handling": "human_confirm"})
    if budget_cap is not None and have_cost and total_cost > budget_cap:
        confirmations.append({"item": "budget", "reason": f"estimated cost {total_cost} exceeds cap {budget_cap}",
                              "handling": "human_confirm"})
    artifact = {
        "kind": "protocol_design", "objective": obj, "variables": variables,
        "steps": steps, "controls": controls, "optimizations": optimizations,
        "risks": risks,
        "totals": {"duration_min": total_min if have_time else None,
                   "cost": total_cost if have_cost else None,
                   "budget_cap": budget_cap,
                   "parallel_groups": groups,
                   "assumption": "sequential steps; steps sharing parallel_group run concurrently (max duration)"},
        "coverage": coverage,
        "n_coverage_missing": sum(1 for v in coverage.values() if not v),
        "range_violations": violations,
        "confirmations": confirmations,
    }
    summary = {"n_steps": len(steps), "n_controls": len(controls),
               "n_optimizations": len(optimizations), "n_risks": len(risks),
               "n_coverage_missing": artifact["n_coverage_missing"],
               "n_range_violations": len(violations),
               "n_confirmations": len(confirmations),
               "total_duration_min": artifact["totals"]["duration_min"],
               "total_cost": artifact["totals"]["cost"]}
    return artifact, summary


def _feas_verdict(item, inv):
    cat = item.get("category")
    if item.get("available") is False or (inv and inv.get("available") is False):
        return "blocker", "explicitly unavailable in inventory", {}
    if item.get("spec_gap"):
        return "risk", f"spec gap: {item['spec_gap']}", {}
    needed = _num(item.get("needed_qty") or item.get("needed_hours") or item.get("needed_cost"))
    avail = _num(item.get("available_qty") or item.get("window_hours") or item.get("budget_cap"))
    if avail is None and inv:
        avail = _num(inv.get("available_qty") or inv.get("capacity"))
    detail = {}
    if needed is not None and avail is not None:
        detail = {"needed": needed, "available": avail}
        if needed > avail:
            detail["shortfall"] = needed - avail
            return "blocker", f"need {needed} > available {avail}", detail
        if avail > 0 and needed / avail > 0.9:
            detail["utilization"] = needed / avail
            return "risk", f"utilization {needed / avail:.0%} of capacity (little margin)", detail
        return "feasible", f"need {needed} <= available {avail}", detail
    if cat in ("safety", "ethics"):
        approved = item.get("approved", (inv or {}).get("approved"))
        if approved is True:
            return "feasible", "approval reported", detail
        return "risk", "safety/ethics approval not confirmed", dict(detail, human_confirm=True)
    if item.get("available") is True or (inv and inv.get("available") is True):
        return "feasible", "availability reported (no quantity arithmetic possible)", detail
    return "not_reported", "no inventory evidence for this requirement", dict(detail, human_confirm=True)


def _build_feasibility(ir, case):
    inv_list = ir.get("inventory") or []
    inv_by_id = {i.get("id"): i for i in inv_list}
    inv_by_name = {_norm(i.get("name")): i for i in inv_list}
    items_out = []
    for it in ir.get("items") or []:
        inv = inv_by_id.get(it.get("inventory_id"))
        if inv is None and it.get("name"):
            inv = inv_by_name.get(_norm(it.get("name")))
        verdict, reason, detail = _feas_verdict(it, inv)
        entry = dict(it)
        entry["verdict"] = verdict
        entry["reason"] = reason
        entry["detail"] = detail
        entry["matched_inventory"] = (inv or {}).get("id")
        if it.get("verdict") and it["verdict"] != verdict:
            entry["agent_verdict"] = it["verdict"]
            entry["verdict_note"] = "engine recomputed verdict from inventory arithmetic; agent verdict kept for review"
        if detail.get("human_confirm") or verdict == "not_reported":
            entry["handling"] = "human_confirm"
        items_out.append(entry)
    n = len(items_out)
    counts = {v: sum(1 for i in items_out if i["verdict"] == v) for v in VERDICTS}
    score = (counts["feasible"] + 0.5 * counts["risk"]) / n if n else None
    if counts["blocker"]:
        overall = "blocked"
    elif n and counts["not_reported"] == n:
        overall = "insufficient_evidence"
    elif score is not None and score >= 0.8:
        overall = "feasible"
    elif score is not None and score >= 0.5:
        overall = "conditional"
    elif score is not None:
        overall = "high_risk"
    else:
        overall = "insufficient_evidence"
    confirmations = list(ir.get("confirmations") or [])
    for i in items_out:
        if i.get("handling") == "human_confirm":
            confirmations.append({"item": i.get("item_id"),
                                  "reason": i["reason"], "handling": "human_confirm"})
    artifact = {
        "kind": "feasibility", "protocol_id": ir.get("protocol_id"),
        "items": items_out, "inventory": inv_list,
        "counts": counts, "feasibility_score": score, "overall": overall,
        "score_rule": "(n_feasible + 0.5*n_risk) / n_items; not_reported counts as 0",
        "blockers": [i["item_id"] for i in items_out if i["verdict"] == "blocker"],
        "risks": [i["item_id"] for i in items_out if i["verdict"] == "risk"],
        "not_reported": [i["item_id"] for i in items_out if i["verdict"] == "not_reported"],
        "confirmations": confirmations,
    }
    summary = {"n_items": n, "n_feasible": counts["feasible"], "n_risk": counts["risk"],
               "n_blocker": counts["blocker"], "n_not_reported": counts["not_reported"],
               "feasibility_score": score, "overall": overall,
               "n_confirmations": len(confirmations)}
    return artifact, summary


def _build_params(ir, case):
    limits = {l.get("param"): l for l in ir.get("limits") or []}
    obs_by_param = {}
    for o in ir.get("observations") or []:
        obs_by_param.setdefault(o.get("param"), []).append(o)
    params_out = []
    for p in ir.get("params") or []:
        nm = p.get("name")
        lo, hi = _range_pair(p.get("range"))
        rec = _num(p.get("recommended"))
        checks = {}
        if rec is not None and lo is not None and hi is not None:
            checks["in_range"] = lo <= rec <= hi
        lim = limits.get(nm)
        if lim:
            llo, lhi = _range_pair(lim.get("range") or [lim.get("min"), lim.get("max")])
            if rec is not None and llo is not None and lhi is not None:
                checks["in_limits"] = llo <= rec <= lhi
                checks["limit_range"] = [llo, lhi]
        entry = dict(p)
        entry["checks"] = checks
        obs = obs_by_param.get(nm, [])
        nums = [(o, _num(o.get("response"))) for o in obs]
        nums = [(o, r) for o, r in nums if r is not None]
        if nums:
            direction = p.get("response_direction", "higher_better")
            best = (max if direction == "higher_better" else min)(nums, key=lambda t: t[1])
            entry["observed_best"] = {"value": _num(best[0].get("value")),
                                      "response": best[1],
                                      "evidence": best[0].get("evidence"),
                                      "n_observations": len(nums)}
            entry["response_stats"] = w4kit.describe([r for _, r in nums])
        params_out.append(entry)
    checks_out = []
    for c in ir.get("numeric_checks") or []:
        env = {k: _num(v) for k, v in (c.get("env") or {}).items()}
        env = {k: v for k, v in env.items() if v is not None}
        try:
            val = w4kit.safe_eval(c["expr"], env)
            ok = True
            if c.get("min") is not None:
                ok = ok and val >= _num(c["min"])
            if c.get("max") is not None:
                ok = ok and val <= _num(c["max"])
            if c.get("equals") is not None:
                ok = ok and abs(val - _num(c["equals"])) <= _num(c.get("tolerance", 1e-9))
            checks_out.append(dict(c, value=val, status="pass" if ok else "fail"))
        except Exception as e:
            checks_out.append(dict(c, value=None, status="error", reason=str(e)))
    cost = ir.get("cost") or {}
    cost_out = None
    if cost:
        per, ntr = _num(cost.get("per_trial")), _num(cost.get("n_trials"))
        total = per * ntr if per is not None and ntr is not None else None
        cap = _num(cost.get("budget"))
        cost_out = {"per_trial": per, "n_trials": ntr, "total": total, "budget": cap,
                    "within_budget": (total <= cap) if total is not None and cap is not None else None}
    confirmations = list(ir.get("confirmations") or [])
    for p in params_out:
        if p.get("status", "inferred") == "inferred":
            confirmations.append({"item": f"param {p.get('name')}",
                                  "reason": "inferred suggestion (not a reported optimum); verify by pilot run",
                                  "handling": "human_confirm"})
        if p.get("checks", {}).get("in_range") is False or p.get("checks", {}).get("in_limits") is False:
            confirmations.append({"item": f"param {p.get('name')} range",
                                  "reason": "recommended value outside feasible range / device limit",
                                  "handling": "human_confirm"})
    artifact = {"kind": "param_optimize", "params": params_out,
                "limits": ir.get("limits") or [], "numeric_checks": checks_out,
                "cost": cost_out, "search_strategy": ir.get("search_strategy"),
                "confirmations": confirmations}
    summary = {"n_params": len(params_out),
               "n_reported_optimum": sum(1 for p in params_out if p.get("status") == "reported"),
               "n_inferred": sum(1 for p in params_out if p.get("status", "inferred") == "inferred"),
               "n_range_violations": sum(1 for p in params_out
                                         if p.get("checks", {}).get("in_range") is False
                                         or p.get("checks", {}).get("in_limits") is False),
               "n_checks_failed": sum(1 for c in checks_out if c["status"] != "pass"),
               "n_confirmations": len(confirmations)}
    return artifact, summary


def _norm_cells(comp):
    """Attach normalized numeric score to each cell; returns cells + coverage."""
    criteria = {c.get("id"): c for c in comp["criteria"]}
    by_crit = {}
    for cell in comp["cells"]:
        by_crit.setdefault(cell.get("criterion_id"), []).append(cell)
    cells_out = []
    for cid, crit in criteria.items():
        row = by_crit.get(cid, [])
        vals = []
        for cell in row:
            v = _num(cell.get("value"))
            if v is None:
                v = _num(cell.get("score"))
            if v is not None and cell.get("status", "reported") in ("reported", "inferred"):
                vals.append(v)
        lo, hi = (min(vals), max(vals)) if vals else (None, None)
        for cell in row:
            v = _num(cell.get("value"))
            if v is None:
                v = _num(cell.get("score"))
            norm = None
            if v is not None and cell.get("status", "reported") in ("reported", "inferred"):
                if hi == lo:
                    norm = 0.5
                else:
                    norm = (v - lo) / (hi - lo)
                    if crit.get("direction") == "lower_better":
                        norm = 1.0 - norm
            cells_out.append(dict(cell, normalized=norm))
    return cells_out


def _weighted_scores(comp, cells_out, weight_override=None):
    criteria = comp["criteria"]
    weights = {}
    for c in criteria:
        w = _num(c.get("weight", comp["weights"].get(c.get("id"), 1)))
        weights[c.get("id")] = w if w is not None else 1.0
    if weight_override:
        weights.update(weight_override)
    wsum = sum(weights.values()) or 1.0
    weights = {k: v / wsum for k, v in weights.items()}
    candids = [c.get("id") for c in comp["candidates"]]
    cellmap = {(c.get("criterion_id"), c.get("candidate_id")): c for c in cells_out}
    scores, coverage = {}, {}
    for cand in candids:
        s, covered = 0.0, 0
        for cid in weights:
            cell = cellmap.get((cid, cand))
            if cell and cell.get("normalized") is not None:
                s += weights[cid] * cell["normalized"]
                covered += 1
        scores[cand] = s
        coverage[cand] = covered / len(weights) if weights else 0.0
    return scores, coverage, weights


def _build_compare(ir, case):
    comp = _comparison(ir)
    cells_out = _norm_cells(comp)
    scores, coverage, weights = _weighted_scores(comp, cells_out)
    ranking = sorted(scores, key=lambda c: (-scores[c], c))
    rec = ranking[0] if ranking else None
    margin = (scores[ranking[0]] - scores[ranking[1]]) if len(ranking) > 1 else None
    tradeoffs = []
    for c in comp["criteria"]:
        cid = c.get("id")
        row = [x for x in cells_out if x.get("criterion_id") == cid
               and x.get("normalized") is not None]
        if row:
            best = max(row, key=lambda x: x["normalized"])
            tradeoffs.append({"criterion_id": cid, "winner": best.get("candidate_id"),
                              "value": best.get("value"), "evidence": best.get("evidence")})
        else:
            tradeoffs.append({"criterion_id": cid, "winner": None,
                              "status": "not_reported"})
    sensitivity = []
    for c in comp["criteria"]:
        cid = c.get("id")
        for factor in (1.2, 0.8):
            ov = {cid: weights[cid] * factor}
            s2, _, _ = _weighted_scores(comp, cells_out, ov)
            win = max(s2, key=lambda k: (s2[k], )) if s2 else None
            if win != rec:
                sensitivity.append({"criterion_id": cid, "weight_factor": factor,
                                    "winner_flips_to": win})
    confirmations = list(ir.get("confirmations") or [])
    if margin is not None and margin < 0.05:
        confirmations.append({"item": "recommendation",
                              "reason": f"score margin {margin:.3f} < 0.05: choice is weight-sensitive",
                              "handling": "human_confirm"})
    for cand, cov in coverage.items():
        if cov < 0.6:
            confirmations.append({"item": f"candidate {cand}",
                                  "reason": f"matrix coverage {cov:.0%} < 60%: score unreliable",
                                  "handling": "human_confirm"})
    cellmap = {(c.get("criterion_id"), c.get("candidate_id")): c for c in cells_out}
    matrix = []
    for c in comp["criteria"]:
        for cand in comp["candidates"]:
            cell = cellmap.get((c.get("id"), cand.get("id")))
            matrix.append(cell or {"criterion_id": c.get("id"),
                                   "candidate_id": cand.get("id"),
                                   "value": None, "status": "not_reported",
                                   "normalized": None})
    artifact = {"kind": "protocol_compare",
                "criteria": comp["criteria"], "candidates": comp["candidates"],
                "weights_normalized": weights, "matrix": matrix,
                "scores": scores, "coverage": coverage, "ranking": ranking,
                "recommendation": rec, "score_margin": margin,
                "tradeoffs": tradeoffs, "weight_sensitivity_flips": sensitivity,
                "method": "min-max normalization per criterion (lower_better inverted); weighted sum; weights renormalized to sum 1",
                "confirmations": confirmations}
    summary = {"n_candidates": len(comp["candidates"]), "n_criteria": len(comp["criteria"]),
               "n_cells": len(comp["cells"]),
               "n_not_reported": sum(1 for m in matrix if m.get("status") == "not_reported"),
               "recommendation": rec, "score_margin": margin,
               "n_weight_flips": len(sensitivity), "n_confirmations": len(confirmations)}
    return artifact, summary


def _outliers_iqr(values):
    d = w4kit.describe(values)
    if d.get("n", 0) < 4:
        return [], "n<4: IQR outlier rule not applied (insufficient replicates)"
    q25, q75 = d["q25"], d["q75"]
    iqr = q75 - q25
    lo, hi = q25 - 1.5 * iqr, q75 + 1.5 * iqr
    flags = [v for v in (_num(x) for x in values)
             if v is not None and (v < lo or v > hi)]
    return flags, f"IQR rule: outside [{lo:.4g}, {hi:.4g}] (1.5*IQR); inferred flag, not a confirmed error"


def _build_anomaly(ir, case):
    results_out = []
    for r in ir.get("results") or []:
        obs = r.get("observed")
        obs_list = obs if isinstance(obs, list) else [obs]
        nums = [x for x in (_num(v) for v in obs_list) if x is not None]
        entry = dict(r)
        entry["stats"] = w4kit.describe(nums) if nums else {"n": 0}
        mean = entry["stats"].get("mean")
        exp = _num(r.get("expected"))
        tol = r.get("tolerance")
        tol_abs = _num(tol) if not isinstance(tol, dict) else _num(tol.get("abs"))
        tol_pct = _num(tol.get("pct")) if isinstance(tol, dict) else None
        deviation = (mean - exp) if mean is not None and exp is not None else None
        within = None
        if deviation is not None and (tol_abs is not None or tol_pct is not None):
            within = True
            if tol_abs is not None:
                within = within and abs(deviation) <= tol_abs
            if tol_pct is not None and exp is not None:
                within = within and abs(deviation) <= abs(exp) * tol_pct / 100.0
        entry["deviation"] = deviation
        entry["within_tolerance"] = within
        if within is None:
            entry["within_note"] = "expected or tolerance not reported; cannot judge (not fabricated)"
        if len(nums) >= 2:
            flags, rule = _outliers_iqr(nums)
            entry["outlier_flags"] = flags
            entry["outlier_rule"] = rule
        series = r.get("series")
        if isinstance(series, list) and len(series) >= 2:
            xs = [p.get("x") for p in series if isinstance(p, dict)]
            ys = [p.get("y") for p in series if isinstance(p, dict)]
            lr = w4kit.linreg(xs, ys)
            if lr:
                entry["trend"] = dict(lr, direction="increasing" if lr["slope"] > 0
                                      else "decreasing" if lr["slope"] < 0 else "flat")
        results_out.append(entry)
    anomalies_out = []
    for a in ir.get("anomalies") or []:
        causes = []
        for c in a.get("candidate_causes") or []:
            sup = c.get("support", "unknown")
            entry = dict(c)
            entry["status"] = c.get("status", "inferred" if sup != "unknown" else "insufficient_evidence")
            if sup in ("supported", "partially_supported") and not _has_ev(c.get("evidence")):
                entry["status"] = "insufficient_evidence"
            causes.append(entry)
        causes.sort(key=lambda c: -SUPPORT_WEIGHT.get(c.get("support", "unknown"), 0))
        for i, c in enumerate(causes):
            c["rank"] = i + 1
        anomalies_out.append(dict(a, candidate_causes=causes,
                                  note="candidate causes ranked by evidence support; none is asserted as confirmed fact"))
    confirmations = list(ir.get("confirmations") or [])
    for a in anomalies_out:
        for c in a["candidate_causes"]:
            if c.get("status") == "insufficient_evidence":
                confirmations.append({"item": f"anomaly {a.get('id')} cause '{c.get('cause')}'",
                                      "reason": "no supporting evidence in material",
                                      "handling": "human_confirm"})
    artifact = {"kind": "result_anomaly", "results": results_out,
                "anomalies": anomalies_out,
                "follow_up": ir.get("follow_up") or [],
                "unexplained": ir.get("unexplained") or [],
                "confirmations": confirmations}
    summary = {"n_results": len(results_out),
               "n_out_of_tolerance": sum(1 for r in results_out if r.get("within_tolerance") is False),
               "n_within_unknown": sum(1 for r in results_out if r.get("within_tolerance") is None),
               "n_anomalies": len(anomalies_out),
               "n_outlier_flags": sum(len(r.get("outlier_flags", [])) for r in results_out),
               "n_insufficient_evidence": sum(1 for a in anomalies_out for c in a["candidate_causes"]
                                              if c.get("status") == "insufficient_evidence"),
               "n_confirmations": len(confirmations)}
    return artifact, summary


_KIND_BUILDERS = {
    "protocol_design": _build_design,
    "feasibility": _build_feasibility,
    "param_optimize": _build_params,
    "protocol_compare": _build_compare,
    "result_anomaly": _build_anomaly,
}
_ARTIFACT_NAME = {
    "protocol_design": "protocol_design.json",
    "feasibility": "feasibility.json",
    "param_optimize": "param_optimize.json",
    "protocol_compare": "protocol_compare.json",
    "result_anomaly": "result_anomaly.json",
}


# ── provenance + report ─────────────────────────────────────────────────────

def _provenance(ir, case, artifact):
    sources = []
    for s in ir.get("sources", []):
        f = _resolve(ir, case, s.get("path"))
        entry = dict(s)
        if f is not None and f.is_file():
            try:
                entry["sha256"] = w4kit.sha256_file(f)
                entry["file_status"] = "ok"
            except OSError as e:
                entry["file_status"] = f"read_failed: {e}"
        else:
            entry["file_status"] = "file_not_found"
        sources.append(entry)
    claims = [{"claim_path": p, **ev} for p, ev in _walk_claims(artifact)]
    return {"pipeline": ir.get("provenance", {}).get("pipeline"),
            "generated_at": w4kit.utc_now(), "sources": sources,
            "n_claims": len(claims), "claims": claims,
            "changes": ir.get("provenance", {}).get("changes", [])}


def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, (list, dict)):
        return str(v)
    return str(v)


def _ev_ref(ev) -> str:
    evs = _evs(ev)
    if not evs:
        return "no locator"
    parts = []
    for e in evs[:2]:
        loc = e.get("source_id", "?")
        if e.get("paragraph_id"):
            loc += f"#{e['paragraph_id']}"
        if e.get("field"):
            loc += f".{e['field']}"
        if e.get("table"):
            loc += f"[{e['table']}]"
        parts.append(loc)
    return "; ".join(parts)


def _report_md(ir, case, artifact, prov, summary) -> str:
    kind = ir.get("kind")
    L = [f"# Experiment report — {kind}", "",
         f"- case_id: `{case.get('case_id')}`",
         f"- generated_at: {w4kit.utc_now()}",
         f"- kind: `{kind}`  (editable artifact; regenerate via assemble.py)",
         "", "## Summary", ""]
    for k, v in summary.items():
        L.append(f"- {k}: {_fmt(v)}")
    L += ["", "## Main result", ""]
    if kind == "protocol_design":
        L.append(f"Objective: {artifact['objective'].get('statement', '—')}")
        L.append(f"Hypothesis: {artifact['objective'].get('hypothesis', 'not reported')}")
        L += ["", "| step | action | duration(min) | params | evidence |", "|-|-|-|-|-|"]
        for st in artifact["steps"]:
            ps = ", ".join(f"{p.get('name')}={_fmt(p.get('value'))}{p.get('unit') or ''}"
                           for p in st.get("parameters", []))
            L.append(f"| {st.get('step_id')} | {st.get('action')} | {_fmt(st.get('duration_min'))} | {ps} | {_ev_ref(st.get('evidence'))} |")
        L += ["", "### Controls", ""]
        for c in artifact["controls"]:
            L.append(f"- {c.get('control_id')} ({c.get('type')}): {c.get('purpose')} [{_ev_ref(c.get('evidence'))}]")
        L += ["", "### Optimizations (reported vs inferred)", ""]
        for o in artifact["optimizations"]:
            L.append(f"- [{o.get('status', 'inferred')}] {o.get('suggestion')} — {o.get('rationale', '')} [{_ev_ref(o.get('evidence'))}]")
        L += ["", "### Risks & stop-loss", ""]
        for r in artifact["risks"]:
            L.append(f"- {r.get('failure_mode')}: criterion={r.get('criterion', '—')}, stop_loss={r.get('stop_loss', '—')}, alternative={r.get('alternative', '—')}")
        L += ["", f"Coverage of six elements: {artifact['coverage']}",
              f"Range violations: {artifact['range_violations']}"]
    elif kind == "feasibility":
        L += [f"Overall: **{artifact['overall']}**  score={_fmt(artifact['feasibility_score'])} ({artifact['score_rule']})", "",
              "| item | category | requirement | verdict | reason | evidence |", "|-|-|-|-|-|-|"]
        for i in artifact["items"]:
            L.append(f"| {i.get('item_id')} | {i.get('category')} | {i.get('requirement')} | {i['verdict']} | {i['reason']} | {_ev_ref(i.get('evidence'))} |")
        L += ["", f"Blockers: {artifact['blockers']}", f"Risks: {artifact['risks']}",
              f"Not reported (human_confirm): {artifact['not_reported']}"]
    elif kind == "param_optimize":
        L += ["| param | current | recommended | range | unit | status | checks | evidence |", "|-|-|-|-|-|-|-|-|"]
        for p in artifact["params"]:
            L.append(f"| {p.get('name')} | {_fmt(p.get('current'))} | {_fmt(p.get('recommended'))} | {_fmt(p.get('range'))} | {p.get('unit') or '—'} | {p.get('status', 'inferred')} | {p.get('checks')} | {_ev_ref(p.get('evidence'))} |")
            if p.get("observed_best"):
                L.append(f"  - best observed: value={_fmt(p['observed_best']['value'])}, response={_fmt(p['observed_best']['response'])} (n={p['observed_best']['n_observations']})")
        L += ["", "### Numeric checks (safe_eval)", ""]
        for c in artifact["numeric_checks"]:
            L.append(f"- {c.get('id')}: `{c.get('expr')}` = {_fmt(c.get('value'))} → {c['status']}")
        if artifact.get("cost"):
            L += ["", f"Cost: {artifact['cost']}"]
    elif kind == "protocol_compare":
        L += [f"Recommendation: **{artifact['recommendation']}**  margin={_fmt(artifact['score_margin'])}", "",
              "| candidate | score | coverage |", "|-|-|-|"]
        for cand in artifact["ranking"]:
            L.append(f"| {cand} | {_fmt(artifact['scores'][cand])} | {_fmt(artifact['coverage'][cand])} |")
        L += ["", "### Matrix (value / normalized)", ""]
        candids = [c.get("id") for c in artifact["candidates"]]
        L.append("| criterion | " + " | ".join(candids) + " |")
        L.append("|-" + "|-" * len(candids) + "|")
        for c in artifact["criteria"]:
            row = [next((m for m in artifact["matrix"]
                         if m.get("criterion_id") == c.get("id") and m.get("candidate_id") == cand), {})
                   for cand in candids]
            L.append(f"| {c.get('id')} ({c.get('direction')}, w={_fmt(artifact['weights_normalized'].get(c.get('id')))}) | "
                     + " | ".join(f"{_fmt(m.get('value'))}/{_fmt(m.get('normalized'))}" for m in row) + " |")
        L += ["", f"Tradeoffs: {artifact['tradeoffs']}",
              f"Weight sensitivity flips: {artifact['weight_sensitivity_flips']}"]
    elif kind == "result_anomaly":
        L += ["| metric | expected | observed(mean) | deviation | within | evidence |", "|-|-|-|-|-|-|"]
        for r in artifact["results"]:
            L.append(f"| {r.get('metric')} | {_fmt(r.get('expected'))} | {_fmt(r.get('stats', {}).get('mean'))} | {_fmt(r.get('deviation'))} | {_fmt(r.get('within_tolerance'))} | {_ev_ref(r.get('evidence'))} |")
            if r.get("outlier_flags"):
                L.append(f"  - outlier flags: {r['outlier_flags']} ({r.get('outlier_rule')})")
            if r.get("trend"):
                L.append(f"  - trend: {r['trend']['direction']} (slope={_fmt(r['trend']['slope'])}, r2={_fmt(r['trend']['r2'])})")
        L += ["", "### Anomalies — ranked candidate causes (NOT confirmed facts)", ""]
        for a in artifact["anomalies"]:
            L.append(f"- **{a.get('id')}**: {a.get('observation')}")
            for c in a["candidate_causes"]:
                L.append(f"  {c['rank']}. [{c.get('support')}/{c.get('status')}] {c.get('cause')} [{_ev_ref(c.get('evidence'))}]")
            L.append(f"  - action: {a.get('action', '—')}")
    L += ["", "## Confirmations (human_confirm)", ""]
    confs = artifact.get("confirmations") or []
    if confs:
        for c in confs:
            L.append(f"- {c.get('item')}: {c.get('reason')}")
    else:
        L.append("- none")
    L += ["", "## Uncertainty", ""]
    for u in ir.get("uncertainty") or []:
        L.append(f"- {u.get('item')}: {u.get('reason')} (handling: {u.get('handling', '—')})")
    if not ir.get("uncertainty"):
        L.append("- none declared")
    L += ["", "## Provenance", "",
          f"{prov['n_claims']} claim locators; see provenance.json. Sources:"]
    for s in prov["sources"]:
        L.append(f"- `{s.get('id')}` {s.get('path')} [{s.get('file_status')}] sha256={str(s.get('sha256'))[:12]}")
    L += ["", "_Editable artifact: modify the IR and re-run assemble.py; deterministic regeneration._", ""]
    return "\n".join(L)


# ── public build / status ───────────────────────────────────────────────────

def build(ir: dict, case: dict, out_dir) -> list:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    kind = ir.get("kind")
    builder = _KIND_BUILDERS.get(kind)
    if builder is None:
        raise ValueError(f"unknown kind '{kind}'")
    artifact, summary = builder(ir, case)

    # quote verification against actual readable material
    paras_by_src = {}
    for d in ir.get("documents", []):
        sid = d.get("source_id")
        if sid:
            paras_by_src.setdefault(sid, []).extend(_doc_paragraphs(ir, case, d))
    issues = []
    for path, ev in _walk_claims(artifact):
        iss = _quote_issues(ir, case, ev, paras_by_src)
        if iss:
            issues.append({"claim_path": path, "issue": iss})
    artifact["locator_issues"] = issues
    summary["n_locator_issues"] = len(issues)

    prov = _provenance(ir, case, artifact)
    outputs = []

    def emit(name, obj, fmt, role):
        p = out_dir / name
        w4kit.write_json(p, obj)
        outputs.append({"name": name, "path": str(p), "format": fmt, "role": role})

    emit(_ARTIFACT_NAME[kind], artifact, "json", "json")
    emit("provenance.json", prov, "json", "provenance_json")
    md = _report_md(ir, case, artifact, prov, summary)
    mp = out_dir / "report.md"
    mp.write_text(md, encoding="utf-8")
    outputs.append({"name": "report.md", "path": str(mp), "format": "md", "role": "md"})
    (out_dir / "_summary.json").write_text(
        __import__("json").dumps(summary, ensure_ascii=False), encoding="utf-8")
    return outputs


def compute_status(ir: dict, validation: dict, summary: dict) -> str:
    """Honest overall status. Finding blockers/anomalies is task completion, not a
    gap; gaps are untraceable/missing info, locator issues and human_confirm items."""
    if validation.get("errors"):
        return "partial"
    gap_keys = ("n_not_reported", "n_insufficient_evidence", "n_locator_issues",
                "n_coverage_missing", "n_range_violations", "n_checks_failed",
                "n_within_unknown", "n_confirmations")
    if any(summary.get(k) for k in gap_keys):
        return "partial"
    if ir.get("uncertainty"):
        return "partial"
    return "success"