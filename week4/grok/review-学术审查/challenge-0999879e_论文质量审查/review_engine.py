"""review_engine — deterministic source-bound engine for the week4 REVIEW track.

Covers all five review workorder kinds over organizer-provided LOCAL material
(the actual manuscript + provided references / data / guidelines):

  quality_review        overall manuscript quality audit (dimension scores +
                        six-category checklist + itemized findings + recommendation)
  citation_fact_check   claim/citation verification against provided sources
                        (supports/partial/insufficient/unrelated/contradicts,
                        DOI/title normalization, mis-citation flags)
  methods_stats_review  methods + statistics audit with REAL recomputation
                        (w4kit.describe/correlation/linreg/safe_eval over provided data)
  logic_argument_review premise->conclusion validity, fallacies, gaps,
                        cross-section consistency
  compliance_check      ethics/COI/data availability/authorship/plagiarism-risk/
                        reporting-guideline checklist with evidence + missing items

The Agent reads the ACTUAL /input material and fills the IR; this engine
validates, recomputes and builds editable artifacts. Every finding / verdict /
score / compliance judgment carries an evidence locator (source_id +
document_id + paragraph_id/field + quote); quotes are verified against the
actual paragraph text when the file is readable. Nothing is fabricated:
unsupported judgments become insufficient_evidence + human_confirm, missing
material becomes not_reported / not_provided, and status is honest
(success / partial / failed).

API:  validate_ir(ir) -> {ok, errors, warnings}
      build(ir, case, out_dir) -> outputs[]   (w4kit artifact descriptors)
      compute_status(ir, validation, summary) -> str

Stdlib only; imports w4kit (shared core, copied next to this file).
"""
from __future__ import annotations

import csv
import math
import re
from pathlib import Path

import w4kit

IR_VERSION = "1.0"
KINDS = {"quality_review", "citation_fact_check", "methods_stats_review",
         "logic_argument_review", "compliance_check"}
DOC_ROLES = {"manuscript", "reference", "data", "guideline", "other"}
SEVERITIES = {"major", "minor", "suggestion"}
FINDING_STATUS = {"confirmed", "suspected", "insufficient_evidence", "not_applicable"}
SUPPORT = {"supports", "partial", "insufficient", "unrelated", "contradicts"}
SUPPORT_WORST = ["contradicts", "unrelated", "insufficient", "partial", "supports"]
VALIDITY = {"valid", "gap", "fallacy", "insufficient_evidence"}
INFERENCE = {"deductive", "inductive", "causal", "correlational", "analogical", "other"}
COMPLIANCE_STATUS = {"compliant", "non_compliant", "partial", "not_applicable",
                     "insufficient_evidence"}
COMPLIANCE_CATS = {"ethics", "coi", "data_availability", "authorship",
                   "plagiarism_risk", "reporting_guideline", "copyright",
                   "privacy", "submission_requirements", "other"}
CATEGORIES = ["fact_check", "citation_support", "methods_design",
              "stats_reporting", "argument_chain", "academic_norms"]
CHECKLIST_STATUS = {"checked", "not_applicable", "uncheckable"}
DECISIONS = {"accept", "minor_revision", "major_revision", "reject", "undetermined"}
STATS_TYPES = {"describe", "correlation", "linreg", "expr"}


# ── text / path helpers (same conventions as library_engine) ────────────────

def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _paragraphs(text: str) -> list:
    paras, page = [], 1
    for i, block in enumerate(re.split(r"\n\s*\n", text or "")):
        block = block.strip()
        if not block:
            continue
        m = re.match(r"page\s+(\d+)\s*$", block, re.I)
        if m:
            page = int(m.group(1))
            continue
        paras.append({"id": f"p{i + 1}", "page": page, "text": block})
    return paras


def _resolve(ir: dict, case: dict, rel) -> Path | None:
    if not rel:
        return None
    p = Path(rel)
    if p.is_absolute():
        return p if p.exists() else None
    for b in (ir.get("_ir_dir"), (case or {}).get("input_dir"), "."):
        if not b:
            continue
        cand = Path(b) / p
        if cand.exists():
            return cand
    return None


def _source(ir: dict, sid):
    return next((s for s in ir.get("sources", []) if s.get("id") == sid), None)


def _load_doc_content(ir: dict, case: dict, doc: dict) -> dict:
    """Load actual paragraphs + sha256 from the real file. Honest on failure."""
    out = {"paragraphs": [], "content_status": "ok", "sha256": None,
           "content_path": None}
    if doc.get("paragraphs"):
        out["paragraphs"] = [
            {"id": p.get("id", f"p{i+1}"), "page": p.get("page", 1),
             "text": p.get("text", "")}
            for i, p in enumerate(doc["paragraphs"])]
        out["content_status"] = "ir_transcribed"
    rel = doc.get("content_path") or doc.get("path")
    if not rel:
        rel = (_source(ir, doc.get("source_id")) or {}).get("path")
    f = _resolve(ir, case, rel)
    if f is not None and f.is_file():
        out["content_path"] = str(f)
        try:
            out["sha256"] = w4kit.sha256_file(f)
            if not out["paragraphs"] and f.suffix.lower() in (
                    ".txt", ".md", ".text", ".csv", ".tsv", ".json", ".log"):
                out["paragraphs"] = _paragraphs(w4kit.read_text(f))
                out["content_status"] = "ok"
            elif not out["paragraphs"]:
                out["content_status"] = "binary_not_parsed"
        except OSError as e:
            out["content_status"] = f"read_failed: {e}"
    elif not out["paragraphs"]:
        out["content_status"] = "file_not_found"
    claimed = doc.get("sha256")
    if claimed and out["sha256"] and claimed.lower() != out["sha256"]:
        out["hash_mismatch"] = {"claimed": claimed, "actual": out["sha256"]}
    return out


def _quote_ok(paragraphs: list, paragraph_id, quote) -> bool:
    if not quote:
        return False
    par = next((p for p in paragraphs if p["id"] == paragraph_id), None)
    if par is None:
        return False
    return _norm_ws(quote) in _norm_ws(par["text"])


def _bind_evidence(ir: dict, content: dict, evs: list) -> tuple:
    """Bind + verify a list of evidence locators against actual content.
    Returns (bound_list, n_issues). Never drops an locator; flags problems."""
    src2doc = {}
    for d in ir.get("documents", []):
        src2doc.setdefault(d.get("source_id"), d.get("document_id"))
    bound, issues = [], 0
    for ev in evs or []:
        e = dict(ev)
        did = e.get("document_id") or src2doc.get(e.get("source_id"))
        if did:
            e["document_id"] = did
        c = content.get(did) if did else None
        if e.get("paragraph_id") and c and c["paragraphs"]:
            par = next((p for p in c["paragraphs"]
                        if p["id"] == e["paragraph_id"]), None)
            if par is None:
                e["locator_status"] = "paragraph_not_found"
                e["handling"] = "human_confirm"
                issues += 1
            elif e.get("quote"):
                ok = _quote_ok(c["paragraphs"], e["paragraph_id"], e["quote"])
                e["quote_verified"] = ok
                e["locator_status"] = "bound" if ok else "quote_mismatch"
                if not ok:
                    e["handling"] = "human_confirm"
                    issues += 1
                e.setdefault("page", par["page"])
            else:
                e["locator_status"] = "bound_no_quote"
        elif e.get("paragraph_id"):
            e["locator_status"] = "content_unreadable"
            e["handling"] = "human_confirm"
            issues += 1
        else:
            e["locator_status"] = "field_or_doc_bound"
        bound.append(e)
    return bound, issues


def _ev_groups(ir: dict):
    """Yield (label, container, key) for every evidence array in the IR."""
    for f in ir.get("findings", []):
        yield f"finding {f.get('id')}", f, "evidence"
    for s in ir.get("dimension_scores", []):
        yield f"score {s.get('dimension')}", s, "evidence"
    for c in ir.get("checklist", []):
        yield f"checklist {c.get('category')}", c, "evidence"
    rec = ir.get("overall_recommendation")
    if isinstance(rec, dict):
        yield "overall_recommendation", rec, "evidence"
    for c in ir.get("claims", []):
        yield f"claim {c.get('id')}", c, "evidence"
        for sc in c.get("subclaims", []):
            yield f"subclaim {sc.get('id')}", sc, "evidence"
    for r in ir.get("references", []):
        yield f"reference {r.get('ref_id')}", r, "evidence"
    for s in ir.get("stats_checks", []):
        yield f"stats_check {s.get('id')}", s, "evidence"
    for a in ir.get("arguments", []):
        if isinstance(a.get("conclusion"), dict):
            yield f"argument {a.get('id')} conclusion", a["conclusion"], "evidence"
        for p in a.get("premises", []):
            yield f"premise {p.get('id')}", p, "evidence"
    for c in ir.get("consistency_checks", []):
        for side in ("a", "b"):
            if isinstance(c.get(side), dict):
                yield f"consistency {c.get('id')}.{side}", c[side], "evidence"
    for it in ir.get("compliance_items", []):
        yield f"compliance {it.get('id')}", it, "evidence"


# ── validation ──────────────────────────────────────────────────────────────

def _check_ev_array(errors, where, evs, required=True):
    if required and not evs:
        errors.append(f"{where}: evidence[] required (locator-bound judgment)")
        return
    for ev in evs or []:
        if not ev.get("source_id"):
            errors.append(f"{where}: evidence without source_id")
        if not (ev.get("paragraph_id") or ev.get("field") or ev.get("table")
                or ev.get("quote")):
            errors.append(f"{where}: evidence needs paragraph_id/field/table/quote locator")


def _validate_findings(ir, errors, warnings):
    fids = [f.get("id") for f in ir.get("findings", [])]
    if len(fids) != len(set(fids)):
        errors.append("duplicate finding id")
    for f in ir.get("findings", []):
        fid = f.get("id", "?")
        if not f.get("dimension"):
            errors.append(f"finding {fid}: dimension required")
        if f.get("severity") not in SEVERITIES:
            errors.append(f"finding {fid}: severity must be one of {sorted(SEVERITIES)}")
        st = f.get("status")
        if st not in FINDING_STATUS:
            errors.append(f"finding {fid}: invalid status '{st}'")
        if not f.get("verdict"):
            errors.append(f"finding {fid}: verdict text required")
        if st in ("confirmed", "suspected"):
            _check_ev_array(errors, f"finding {fid}", f.get("evidence"))
            if not f.get("recommendation"):
                warnings.append(f"finding {fid}: no recommendation (actionable fix expected)")
        if st == "insufficient_evidence":
            f.setdefault("handling", "human_confirm")
            if not f.get("reason") and not f.get("verdict"):
                errors.append(f"finding {fid}: insufficient_evidence needs a reason")
        if st == "not_applicable" and not f.get("reason"):
            errors.append(f"finding {fid}: not_applicable needs a reason")
        if f.get("polarity") and f["polarity"] not in ("issue", "strength"):
            errors.append(f"finding {fid}: polarity must be issue/strength")


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
            errors.append(f"source {s.get('id')}: path required (real file)")
    errors += w4kit.check_sources(ir)

    docs = ir.get("documents", [])
    dids = [d.get("document_id") for d in docs]
    if not docs:
        errors.append("documents[] empty: register the manuscript and provided material")
    if len(dids) != len(set(dids)):
        errors.append("duplicate document_id")
    dset = set(dids)
    sset = set(sids)
    for d in docs:
        did = d.get("document_id", "?")
        if d.get("source_id") not in sset:
            errors.append(f"doc {did}: source_id not registered")
        if d.get("role") and d["role"] not in DOC_ROLES:
            errors.append(f"doc {did}: invalid role '{d['role']}'")
        if not d.get("title"):
            warnings.append(f"doc {did}: no title (flagged, not invented)")
    mid = ir.get("manuscript_id")
    if not mid:
        errors.append("manuscript_id required (the document under review)")
    elif mid not in dset:
        errors.append(f"manuscript_id '{mid}' is not a registered document_id")

    _validate_findings(ir, errors, warnings)

    if kind == "quality_review":
        scores = ir.get("dimension_scores", [])
        if not scores:
            errors.append("quality_review requires dimension_scores[] (novelty/rigor/clarity/significance)")
        for s in scores:
            dim = s.get("dimension", "?")
            if not isinstance(s.get("score"), (int, float)):
                errors.append(f"score {dim}: numeric score required")
            scale = s.get("scale", 5)
            if not isinstance(scale, (int, float)) or scale <= 0:
                errors.append(f"score {dim}: scale must be a positive number")
            elif isinstance(s.get("score"), (int, float)) and not (0 <= s["score"] <= scale):
                errors.append(f"score {dim}: score {s['score']} outside [0,{scale}]")
            if not s.get("basis"):
                errors.append(f"score {dim}: basis (scoring rationale) required")
            _check_ev_array(errors, f"score {dim}", s.get("evidence"))
        cl = ir.get("checklist", [])
        cats = [c.get("category") for c in cl]
        for cat in CATEGORIES:
            if cat not in cats:
                errors.append(f"checklist missing category '{cat}' (six-category coverage required)")
        if len(cats) != len(set(cats)):
            errors.append("duplicate checklist category")
        for c in cl:
            st = c.get("status")
            if st not in CHECKLIST_STATUS:
                errors.append(f"checklist {c.get('category')}: invalid status '{st}'")
            if st in ("not_applicable", "uncheckable") and not c.get("reason"):
                errors.append(f"checklist {c.get('category')}: {st} requires a reason")
        rec = ir.get("overall_recommendation") or {}
        if rec.get("decision") not in DECISIONS:
            errors.append(f"overall_recommendation.decision must be one of {sorted(DECISIONS)}")
        if not rec.get("rationale"):
            errors.append("overall_recommendation.rationale required")
        if rec.get("decision") == "undetermined" and not rec.get("reason"):
            errors.append("undetermined decision requires a reason (human_confirm)")

    if kind == "citation_fact_check":
        claims = ir.get("claims", [])
        if not claims:
            errors.append("citation_fact_check requires claims[]")
        cids = [c.get("id") for c in claims]
        if len(cids) != len(set(cids)):
            errors.append("duplicate claim id")
        for c in claims:
            cid = c.get("id", "?")
            if not c.get("text"):
                errors.append(f"claim {cid}: text required (verbatim or faithful paraphrase)")
            _check_ev_array(errors, f"claim {cid} location", c.get("evidence"))
            subs = c.get("subclaims", [])
            scids = [s.get("id") for s in subs]
            if len(scids) != len(set(scids)):
                errors.append(f"claim {cid}: duplicate subclaim id")
            for sc in subs:
                sid = sc.get("id", "?")
                if sc.get("support") not in SUPPORT:
                    errors.append(f"subclaim {sid}: support must be one of {sorted(SUPPORT)}")
                if not sc.get("text"):
                    errors.append(f"subclaim {sid}: text required")
                if sc.get("support") != "insufficient":
                    _check_ev_array(errors, f"subclaim {sid}", sc.get("evidence"))
                elif not sc.get("rationale"):
                    errors.append(f"subclaim {sid}: insufficient support needs a rationale")
            if not subs and c.get("support") not in SUPPORT:
                errors.append(f"claim {cid}: support required when no subclaims")
            if not subs and c.get("support") != "insufficient":
                pass  # claim-level evidence already checked above
        refids = [r.get("ref_id") for r in ir.get("references", [])]
        if len(refids) != len(set(refids)):
            errors.append("duplicate ref_id")
        for r in ir.get("references", []):
            rid = r.get("ref_id", "?")
            if r.get("document_id") and r["document_id"] not in dset:
                errors.append(f"reference {rid}: document_id not registered")
            if not (r.get("cited") or {}).get("title") and not (r.get("cited") or {}).get("doi"):
                warnings.append(f"reference {rid}: no cited title/doi to normalize")
            for cid in r.get("claim_ids", []):
                if cid not in cids:
                    errors.append(f"reference {rid}: claim_ids references unknown '{cid}'")

    if kind == "methods_stats_review":
        if not ir.get("findings") and not ir.get("stats_checks"):
            errors.append("methods_stats_review requires findings[] and/or stats_checks[]")
        stids = [s.get("id") for s in ir.get("stats_checks", [])]
        if len(stids) != len(set(stids)):
            errors.append("duplicate stats_check id")
        for s in ir.get("stats_checks", []):
            sid = s.get("id", "?")
            ct = s.get("check_type")
            if ct not in STATS_TYPES:
                errors.append(f"stats_check {sid}: check_type must be one of {sorted(STATS_TYPES)}")
            if not s.get("description"):
                errors.append(f"stats_check {sid}: description required")
            if ct == "expr":
                if not s.get("expr"):
                    errors.append(f"stats_check {sid}: expr required")
            else:
                data = s.get("data") or {}
                has_inline = s.get("values") or (s.get("xs") and s.get("ys"))
                if not has_inline and not data.get("source_id"):
                    errors.append(f"stats_check {sid}: data.source_id or inline values/xs+ys required")
                if data.get("source_id") and data["source_id"] not in sset:
                    errors.append(f"stats_check {sid}: data.source_id not registered")
                if ct in ("correlation", "linreg") and not has_inline:
                    if not (data.get("x_field") and data.get("y_field")):
                        errors.append(f"stats_check {sid}: x_field and y_field required")
                if ct == "describe" and not has_inline and not data.get("field"):
                    errors.append(f"stats_check {sid}: data.field required for describe")
            if s.get("reported"):
                _check_ev_array(errors, f"stats_check {sid} reported values", s.get("evidence"))
            else:
                warnings.append(f"stats_check {sid}: no reported values to compare (recompute-only)")

    if kind == "logic_argument_review":
        args = ir.get("arguments", [])
        if not args:
            errors.append("logic_argument_review requires arguments[]")
        aids = [a.get("id") for a in args]
        if len(aids) != len(set(aids)):
            errors.append("duplicate argument id")
        for a in args:
            aid = a.get("id", "?")
            con = a.get("conclusion") or {}
            if not con.get("text"):
                errors.append(f"argument {aid}: conclusion.text required")
            _check_ev_array(errors, f"argument {aid} conclusion", con.get("evidence"))
            prem = a.get("premises", [])
            if not prem:
                errors.append(f"argument {aid}: premises[] required (>=1; mark not_reported if absent)")
            pids = [p.get("id") for p in prem]
            if len(pids) != len(set(pids)):
                errors.append(f"argument {aid}: duplicate premise id")
            for p in prem:
                pid = p.get("id", "?")
                if not p.get("text"):
                    errors.append(f"premise {pid}: text required")
                if p.get("status", "reported") == "reported":
                    _check_ev_array(errors, f"premise {pid}", p.get("evidence"))
                elif p.get("status") not in ("reported", "inferred", "not_reported"):
                    errors.append(f"premise {pid}: status must be reported/inferred/not_reported")
            v = a.get("validity")
            if v not in VALIDITY:
                errors.append(f"argument {aid}: validity must be one of {sorted(VALIDITY)}")
            if v == "fallacy" and not a.get("fallacy_type"):
                errors.append(f"argument {aid}: fallacy requires fallacy_type")
            if v == "gap" and not (a.get("gaps") or a.get("note")):
                errors.append(f"argument {aid}: gap requires gaps[] or note")
            if v == "insufficient_evidence":
                a.setdefault("handling", "human_confirm")
            if a.get("inference_type") and a["inference_type"] not in INFERENCE:
                errors.append(f"argument {aid}: invalid inference_type")
        for c in ir.get("consistency_checks", []):
            cid = c.get("id", "?")
            for side in ("a", "b"):
                obj = c.get(side) or {}
                if not obj.get("text"):
                    errors.append(f"consistency {cid}.{side}: text required")
                _check_ev_array(errors, f"consistency {cid}.{side}", obj.get("evidence"))
            if c.get("verdict") not in ("consistent", "inconsistent", "unclear"):
                errors.append(f"consistency {cid}: verdict must be consistent/inconsistent/unclear")

    if kind == "compliance_check":
        items = ir.get("compliance_items", [])
        if not items:
            errors.append("compliance_check requires compliance_items[]")
        iids = [i.get("id") for i in items]
        if len(iids) != len(set(iids)):
            errors.append("duplicate compliance item id")
        for it in items:
            iid = it.get("id", "?")
            if it.get("category") not in COMPLIANCE_CATS:
                errors.append(f"compliance {iid}: category must be one of {sorted(COMPLIANCE_CATS)}")
            if not it.get("item"):
                errors.append(f"compliance {iid}: item (checklist text) required")
            if not it.get("guideline"):
                errors.append(f"compliance {iid}: guideline required (CONSORT/PRISMA/ARRIVE/journal guide/...)")
            st = it.get("status")
            if st not in COMPLIANCE_STATUS:
                errors.append(f"compliance {iid}: invalid status '{st}'")
            if st in ("compliant", "non_compliant", "partial"):
                _check_ev_array(errors, f"compliance {iid}", it.get("evidence"))
            if st == "not_applicable" and not it.get("reason"):
                errors.append(f"compliance {iid}: not_applicable requires a reason")
            if st == "insufficient_evidence":
                it.setdefault("handling", "human_confirm")
            if st in ("non_compliant", "partial") and not it.get("recommendation"):
                warnings.append(f"compliance {iid}: {st} without recommendation")
            if it.get("severity") and it["severity"] not in SEVERITIES:
                errors.append(f"compliance {iid}: invalid severity")
        for g in ir.get("guidelines", []):
            if g.get("source_id") and g["source_id"] not in sset:
                errors.append(f"guideline {g.get('id')}: source_id not registered")

    if not ir.get("provenance", {}).get("pipeline"):
        ir.setdefault("provenance", {})["pipeline"] = \
            "actual material -> IR -> validate -> recompute/verify -> artifact -> result"
    return {"ok": not errors, "errors": errors, "warnings": warnings}


# ── statistics recomputation (REAL computation over provided data) ──────────

def _series_from_data(ir, case, s):
    """Return (xs, ys, note) for a stats check; honest note when unavailable."""
    if s.get("values") is not None:
        return s["values"], None, "inline values from IR (agent transcribed from material)"
    if s.get("xs") is not None and s.get("ys") is not None:
        return s["xs"], s["ys"], "inline xs/ys from IR"
    data = s.get("data") or {}
    src = _source(ir, data.get("source_id"))
    f = _resolve(ir, case, (src or {}).get("path"))
    if f is None:
        return None, None, f"data file not found for source {data.get('source_id')}"
    try:
        rows = w4kit.read_table(f)
    except Exception as e:
        return None, None, f"data read failed: {e}"
    if not rows:
        return None, None, "data file has no rows"
    xf, yf = data.get("x_field") or data.get("field"), data.get("y_field")
    if xf and xf not in rows[0]:
        return None, None, f"field '{xf}' not in data columns {list(rows[0])}"
    xs = [r.get(xf) for r in rows]
    ys = [r.get(yf) for r in rows] if yf else None
    if yf and yf not in rows[0]:
        return None, None, f"field '{yf}' not in data columns {list(rows[0])}"
    return xs, ys, f"read {len(rows)} rows from {f.name}"


def _compare(reported, computed, tol):
    rel = float((tol or {}).get("rel", 0.05))
    abst = float((tol or {}).get("abs", 1e-9))
    comps = []
    for k, rv in (reported or {}).items():
        rvf = w4kit.to_float(rv)
        av = computed.get(k)
        if rvf is None or av is None:
            comps.append({"key": k, "reported": rv, "computed": av,
                          "verdict": "not_comparable"})
            continue
        diff = abs(rvf - av)
        ok = diff <= max(abst, rel * abs(av))
        comps.append({"key": k, "reported": rvf, "computed": round(av, 6),
                      "abs_diff": round(diff, 6),
                      "rel_diff": round(diff / abs(av), 6) if av else None,
                      "verdict": "match" if ok else "mismatch"})
    return comps


def _run_stats_check(ir, case, s, content):
    sid = s.get("id", "?")
    ct = s.get("check_type")
    out = {"id": sid, "description": s.get("description"), "check_type": ct,
           "reported": s.get("reported") or {}, "computed": None,
           "comparisons": [], "verdict": "not_recomputable", "note": None}
    evs, issues = _bind_evidence(ir, content, s.get("evidence", []))
    out["evidence"] = evs
    out["locator_issues"] = issues
    computed = {}
    try:
        if ct == "expr":
            env = {k: float(v) for k, v in (s.get("env") or {}).items()}
            computed = {"value": w4kit.safe_eval(s["expr"], env)}
            out["expr"] = s["expr"]
            out["env"] = env
        else:
            xs, ys, note = _series_from_data(ir, case, s)
            out["data_note"] = note
            if xs is None:
                out["note"] = note
                return out
            if ct == "describe":
                computed = w4kit.describe(xs)
                if computed.get("n", 0) == 0:
                    out["note"] = "no numeric values in series"
                    return out
            elif ct == "correlation":
                r = w4kit.correlation(xs, ys or [])
                if r is None:
                    out["note"] = "correlation not computable (n<2 or zero variance)"
                    return out
                pairs = [(w4kit.to_float(a), w4kit.to_float(b))
                         for a, b in zip(xs, ys or [])]
                computed = {"r": r, "n": sum(1 for a, b in pairs
                                             if a is not None and b is not None)}
            elif ct == "linreg":
                reg = w4kit.linreg(xs, ys or [])
                if reg is None:
                    out["note"] = "regression not computable (n<2 or zero x variance)"
                    return out
                computed = reg
    except (ValueError, ZeroDivisionError, OverflowError, TypeError) as e:
        out["note"] = f"recompute failed: {e}"
        return out
    out["computed"] = {k: (round(v, 6) if isinstance(v, float) else v)
                       for k, v in computed.items()}
    comps = _compare(s.get("reported"), computed, s.get("tolerance"))
    out["comparisons"] = comps
    verdicts = [c["verdict"] for c in comps]
    if not comps:
        out["verdict"] = "recomputed_only"
    elif "mismatch" in verdicts:
        out["verdict"] = "mismatch"
    elif all(v == "match" for v in verdicts):
        out["verdict"] = "match"
    else:
        out["verdict"] = "partial_compare"
    return out


# ── citation / fact check ───────────────────────────────────────────────────

def _check_references(ir, content):
    refs = []
    dmap = {d.get("document_id"): d for d in ir.get("documents", [])}
    for r in ir.get("references", []):
        rid = r.get("ref_id", "?")
        cited = r.get("cited") or {}
        out = {"ref_id": rid, "cited": cited,
               "cited_doi_normalized": w4kit.normalize_doi(cited.get("doi")),
               "cited_title_normalized": w4kit.normalize_title(cited.get("title")),
               "claim_ids": r.get("claim_ids", []),
               "match_status": "not_provided", "mismatches": [],
               "handling": "human_confirm"}
        evs, issues = _bind_evidence(ir, content, r.get("evidence", []))
        out["evidence"] = evs
        out["locator_issues"] = issues
        did = r.get("document_id")
        doc = dmap.get(did)
        if doc is None:
            out["note"] = ("reference full text not provided under /input; existence and "
                           "content cannot be verified locally — never assumed")
            refs.append(out)
            continue
        meta = doc.get("metadata") or {}
        actual = {"title": meta.get("title") or doc.get("title"),
                  "doi": meta.get("doi"), "year": meta.get("year"),
                  "authors": meta.get("authors")}
        out["document_id"] = did
        out["actual"] = actual
        out["actual_doi_normalized"] = w4kit.normalize_doi(actual.get("doi"))
        out["actual_title_normalized"] = w4kit.normalize_title(actual.get("title"))
        mism = []
        cd, ad = out["cited_doi_normalized"], out["actual_doi_normalized"]
        if cd and ad and cd != ad:
            mism.append({"field": "doi", "cited": cd, "actual": ad})
        ct, at = cited.get("title"), actual.get("title")
        if ct and at:
            sim = w4kit._title_sim(ct, at)
            out["title_similarity"] = round(sim, 4)
            if sim < 0.85:
                mism.append({"field": "title", "cited": ct, "actual": at,
                             "similarity": round(sim, 4)})
        cy, ay = cited.get("year"), actual.get("year")
        if cy and ay and str(cy) != str(ay):
            mism.append({"field": "year", "cited": cy, "actual": ay})
        out["mismatches"] = mism
        if not cd and not ct:
            out["match_status"] = "no_cited_metadata"
        elif mism:
            out["match_status"] = "metadata_mismatch"
        else:
            out["match_status"] = "matched"
            out.pop("handling", None)
        refs.append(out)
    return refs


def _check_claims(ir, content):
    claims, issues_total = [], 0
    for c in ir.get("claims", []):
        cid = c.get("id", "?")
        out = {"id": cid, "text": c.get("text"),
               "citation_ref_ids": c.get("citation_ref_ids", [])}
        evs, i1 = _bind_evidence(ir, content, c.get("evidence", []))
        out["location_evidence"] = evs
        subs = []
        for sc in c.get("subclaims", []):
            s = dict(sc)
            evs2, i2 = _bind_evidence(ir, content, sc.get("evidence", []))
            s["evidence"] = evs2
            if sc.get("support") == "insufficient":
                s.setdefault("handling", "human_confirm")
            subs.append(s)
            issues_total += i2
        issues_total += i1
        out["subclaims"] = subs
        if subs:
            worst = min((s["support"] for s in subs), key=SUPPORT_WORST.index)
            out["support"] = worst
            out["support_basis"] = "engine rollup: worst subclaim support"
            if c.get("support") and c["support"] != worst:
                out["support_override"] = {"agent_declared": c["support"],
                                           "engine_rollup": worst}
        else:
            out["support"] = c.get("support")
            out["support_basis"] = "agent judgment bound to claim-level evidence"
            if out["support"] == "insufficient":
                out.setdefault("handling", "human_confirm")
        out["rationale"] = c.get("rationale")
        out["recommendation"] = c.get("recommendation")
        claims.append(out)
    unsupported = [c["id"] for c in claims
                   if c["support"] in ("insufficient", "unrelated", "contradicts")]
    miscited = [c["id"] for c in claims
                if c["support"] in ("unrelated", "contradicts")]
    partial = [c["id"] for c in claims if c["support"] == "partial"]
    return {"claims": claims, "n_claims": len(claims),
            "unsupported_claims": unsupported, "mis_cited_claims": miscited,
            "overgeneralization_candidates": partial,
            "locator_issues": issues_total}


# ── kind payloads ───────────────────────────────────────────────────────────

def _quality_payload(ir, content):
    issues = 0
    scores = []
    for s in ir.get("dimension_scores", []):
        e = dict(s)
        evs, i = _bind_evidence(ir, content, s.get("evidence", []))
        e["evidence"] = evs
        issues += i
        e["normalized"] = round(s["score"] / s.get("scale", 5), 4)
        scores.append(e)
    findings = []
    for f in ir.get("findings", []):
        e = dict(f)
        evs, i = _bind_evidence(ir, content, f.get("evidence", []))
        e["evidence"] = evs
        issues += i
        findings.append(e)
    checklist = []
    for c in ir.get("checklist", []):
        e = dict(c)
        evs, i = _bind_evidence(ir, content, c.get("evidence", []))
        e["evidence"] = evs
        issues += i
        e["n_findings"] = sum(1 for f in findings if f.get("dimension") == c.get("category"))
        checklist.append(e)
    rec = dict(ir.get("overall_recommendation") or {})
    evs, i = _bind_evidence(ir, content, rec.get("evidence", []))
    rec["evidence"] = evs
    issues += i
    overall = (round(sum(s["normalized"] for s in scores) / len(scores), 4)
               if scores else None)
    strengths = [f for f in findings if f.get("polarity") == "strength"]
    weaknesses = [f for f in findings if f.get("polarity", "issue") == "issue"
                  and f.get("severity") in ("major", "minor")]
    return {"dimension_scores": scores, "overall_quality_normalized": overall,
            "checklist_coverage": checklist,
            "n_uncheckable_categories": sum(1 for c in checklist
                                            if c.get("status") == "uncheckable"),
            "findings": findings, "strengths": strengths, "weaknesses": weaknesses,
            "overall_recommendation": rec, "locator_issues": issues}


def _methods_payload(ir, case, content):
    issues = 0
    findings = []
    for f in ir.get("findings", []):
        e = dict(f)
        evs, i = _bind_evidence(ir, content, f.get("evidence", []))
        e["evidence"] = evs
        issues += i
        findings.append(e)
    checks = [_run_stats_check(ir, case, s, content) for s in ir.get("stats_checks", [])]
    issues += sum(c.get("locator_issues", 0) for c in checks)
    return {"findings": findings, "stats_checks": checks,
            "n_stats_checks": len(checks),
            "n_stats_match": sum(1 for c in checks if c["verdict"] == "match"),
            "n_stats_mismatch": sum(1 for c in checks if c["verdict"] == "mismatch"),
            "n_stats_not_recomputable": sum(1 for c in checks
                                            if c["verdict"] == "not_recomputable"),
            "locator_issues": issues}


def _logic_payload(ir, content):
    issues = 0
    args = []
    for a in ir.get("arguments", []):
        e = dict(a)
        con = dict(a.get("conclusion") or {})
        evs, i = _bind_evidence(ir, content, con.get("evidence", []))
        con["evidence"] = evs
        issues += i
        e["conclusion"] = con
        prem = []
        for p in a.get("premises", []):
            q = dict(p)
            evs2, i2 = _bind_evidence(ir, content, p.get("evidence", []))
            q["evidence"] = evs2
            issues += i2
            if p.get("status") == "not_reported":
                q.setdefault("handling", "human_confirm")
            prem.append(q)
        e["premises"] = prem
        e["n_premises_not_reported"] = sum(1 for p in prem
                                           if p.get("status") == "not_reported")
        args.append(e)
    cons = []
    for c in ir.get("consistency_checks", []):
        e = dict(c)
        for side in ("a", "b"):
            obj = dict(c.get(side) or {})
            evs, i = _bind_evidence(ir, content, obj.get("evidence", []))
            obj["evidence"] = evs
            issues += i
            e[side] = obj
        if c.get("verdict") == "unclear":
            e.setdefault("handling", "human_confirm")
        cons.append(e)
    findings = []
    for f in ir.get("findings", []):
        e = dict(f)
        evs, i = _bind_evidence(ir, content, f.get("evidence", []))
        e["evidence"] = evs
        issues += i
        findings.append(e)
    return {"arguments": args, "consistency_checks": cons, "findings": findings,
            "n_arguments": len(args),
            "n_valid": sum(1 for a in args if a.get("validity") == "valid"),
            "n_gap": sum(1 for a in args if a.get("validity") == "gap"),
            "n_fallacy": sum(1 for a in args if a.get("validity") == "fallacy"),
            "n_argument_insufficient": sum(1 for a in args
                                           if a.get("validity") == "insufficient_evidence"),
            "n_inconsistent": sum(1 for c in cons if c.get("verdict") == "inconsistent"),
            "locator_issues": issues}


def _compliance_payload(ir, content):
    issues = 0
    items = []
    for it in ir.get("compliance_items", []):
        e = dict(it)
        evs, i = _bind_evidence(ir, content, it.get("evidence", []))
        e["evidence"] = evs
        issues += i
        e.setdefault("severity", "minor")
        items.append(e)
    by_cat = {}
    for it in items:
        c = by_cat.setdefault(it["category"], {
            "n_items": 0, "compliant": 0, "non_compliant": 0, "partial": 0,
            "not_applicable": 0, "insufficient_evidence": 0})
        c["n_items"] += 1
        c[it["status"]] = c.get(it["status"], 0) + 1
    assessed = sum(1 for i in items
                   if i["status"] in ("compliant", "non_compliant", "partial"))
    n_ok = sum(1 for i in items if i["status"] == "compliant")
    missing = [{"item_id": i["id"], "category": i["category"],
                "guideline": i["guideline"], "item": i["item"],
                "missing": i.get("missing", []), "status": i["status"],
                "recommendation": i.get("recommendation")}
               for i in items if i["status"] in ("non_compliant", "partial")]
    return {"compliance_items": items, "by_category": by_cat,
            "guidelines": ir.get("guidelines", []),
            "n_items": len(items), "assessed": assessed,
            "compliance_rate": round(n_ok / assessed, 4) if assessed else None,
            "missing_items": missing,
            "n_insufficient": sum(1 for i in items
                                  if i["status"] == "insufficient_evidence"),
            "locator_issues": issues}


# ── provenance / report / csv ───────────────────────────────────────────────

def _provenance(ir, payload, docs_out):
    items = []
    for label, container, key in _ev_groups(ir):
        items.append({"item_type": label.split(" ")[0], "item_id": label,
                      "locators": container.get(key, [])})
    used = set()
    for it in items:
        for loc in it["locators"]:
            if loc.get("source_id"):
                used.add(loc["source_id"])
    for d in docs_out:
        if d.get("source_id"):
            used.add(d["source_id"])
    all_ids = {s.get("id") for s in ir.get("sources", [])}
    return {"pipeline": ir.get("provenance", {}).get("pipeline"),
            "items": items, "sources_used": sorted(used),
            "sources_unused": sorted(all_ids - used),
            "changes": ir.get("provenance", {}).get("changes", [])}


def _loc_str(evs):
    parts = []
    for e in evs or []:
        s = e.get("source_id", "?")
        if e.get("document_id"):
            s += ":" + e["document_id"]
        if e.get("paragraph_id"):
            s += ":" + e["paragraph_id"]
        elif e.get("field"):
            s += ":" + e["field"]
        parts.append(s)
    return "; ".join(parts) or "—"


def _report_md(ir, case, docs_out, payload, prov, status):
    kind = ir.get("kind")
    L = [f"# Review report — {case.get('case_id')}", "",
         f"kind: `{kind}` | status: **{status}** | generated: {w4kit.utc_now()}", "",
         "All judgments below are bound to the ACTUAL input material via the IR; "
         "every locator was checked against the real file text where readable. "
         "Unsupported judgments are marked insufficient_evidence + human_confirm, "
         "never fabricated.", "",
         "## 0. Material under review", "",
         "| doc | role | title | sha256 (12) | content |", "|---|---|---|---|---|"]
    for d in docs_out:
        L.append(f"| {d['document_id']} | {d.get('role','other')} | "
                 f"{d.get('title') or 'not_reported'} | {(d.get('sha256') or '—')[:12]} | "
                 f"{d['content_status']} |")
    sec = 1
    if kind == "quality_review":
        L += ["", f"## {sec}. Dimension scores", "",
              "| dimension | score | scale | basis |", "|---|---|---|---|"]
        for s in payload["dimension_scores"]:
            L.append(f"| {s['dimension']} | {s['score']} | {s.get('scale',5)} | {s.get('basis','')} |")
        L.append(f"\nOverall (normalized mean): **{payload['overall_quality_normalized']}**")
        sec += 1
        L += ["", f"## {sec}. Six-category checklist coverage", "",
              "| category | status | findings | reason |", "|---|---|---|---|"]
        for c in payload["checklist_coverage"]:
            L.append(f"| {c['category']} | {c['status']} | {c['n_findings']} | "
                     f"{c.get('reason','—')} |")
        sec += 1
        L += ["", f"## {sec}. Findings ({len(payload['findings'])})", ""]
        for f in payload["findings"]:
            L.append(f"### {f['id']} [{f.get('severity')}/{f.get('status')}] "
                     f"{f.get('dimension')} ({f.get('polarity','issue')})")
            L.append(f"- verdict: {f.get('verdict')}")
            L.append(f"- locator: {_loc_str(f.get('evidence'))}")
            for e in f.get("evidence", []):
                if e.get("quote"):
                    L.append(f"  - “{e['quote'][:160]}” [verified={e.get('quote_verified','n/a')}]")
            if f.get("recommendation"):
                L.append(f"- recommendation: {f['recommendation']}")
        rec = payload["overall_recommendation"]
        L += ["", f"## {sec}. Overall recommendation: **{rec.get('decision')}**",
              f"{rec.get('rationale','')}"]
    elif kind == "citation_fact_check":
        L += ["", f"## {sec}. Claim verification ({payload['n_claims']} claims)", ""]
        for c in payload["claims"]:
            L.append(f"### {c['id']} — support: **{c['support']}**")
            L.append(f"- claim: {c.get('text')}")
            L.append(f"- location: {_loc_str(c.get('location_evidence'))}")
            for sc in c.get("subclaims", []):
                L.append(f"  - subclaim {sc['id']} [{sc['support']}]: {sc.get('text')}")
                L.append(f"    - evidence: {_loc_str(sc.get('evidence'))}"
                         + (f" — {sc.get('rationale')}" if sc.get("rationale") else ""))
            if c.get("recommendation"):
                L.append(f"- recommendation: {c['recommendation']}")
        sec += 1
        L += ["", f"## {sec}. Reference metadata check (normalized DOI/title)", "",
              "| ref | match | mismatches |", "|---|---|---|"]
        for r in payload["references"]:
            mm = "; ".join(f"{m['field']}: {m.get('cited')} ≠ {m.get('actual')}"
                           for m in r["mismatches"]) or "—"
            L.append(f"| {r['ref_id']} | {r['match_status']} | {mm} |")
        L += ["", f"- unsupported claims: {payload['unsupported_claims']}",
              f"- mis-cited claims: {payload['mis_cited_claims']}",
              f"- overgeneralization candidates (partial): {payload['overgeneralization_candidates']}"]
    elif kind == "methods_stats_review":
        L += ["", f"## {sec}. Methods findings ({len(payload['findings'])})", ""]
        for f in payload["findings"]:
            L.append(f"- {f['id']} [{f.get('severity')}/{f.get('status')}] "
                     f"{f.get('dimension')}: {f.get('verdict')} "
                     f"(locator {_loc_str(f.get('evidence'))})")
            if f.get("recommendation"):
                L.append(f"  - fix: {f['recommendation']}")
        sec += 1
        L += ["", f"## {sec}. Statistics recomputation ({payload['n_stats_checks']} checks)", "",
              "| check | type | verdict | detail |", "|---|---|---|---|"]
        for c in payload["stats_checks"]:
            detail = "; ".join(f"{x['key']}: reported {x['reported']} vs computed "
                               f"{x['computed']} → {x['verdict']}"
                               for x in c["comparisons"]) or c.get("note") or "—"
            L.append(f"| {c['id']} | {c['check_type']} | **{c['verdict']}** | {detail} |")
        L += ["", "Recomputation uses w4kit.describe/correlation/linreg/safe_eval over "
              "the ACTUAL provided data files (or IR-transcribed values with locators)."]
    elif kind == "logic_argument_review":
        L += ["", f"## {sec}. Argument audit ({payload['n_arguments']} arguments)", ""]
        for a in payload["arguments"]:
            L.append(f"### {a['id']} — validity: **{a.get('validity')}** "
                     f"({a.get('inference_type','other')}"
                     + (f", fallacy: {a.get('fallacy_type')}" if a.get("fallacy_type") else "") + ")")
            L.append(f"- conclusion: {a['conclusion'].get('text')} "
                     f"({_loc_str(a['conclusion'].get('evidence'))})")
            for p in a.get("premises", []):
                L.append(f"  - premise {p['id']} [{p.get('status','reported')}]: "
                         f"{p.get('text')} ({_loc_str(p.get('evidence'))})")
            for g in a.get("gaps", []):
                L.append(f"  - GAP: {g}")
            if a.get("recommendation"):
                L.append(f"- recommendation: {a['recommendation']}")
        sec += 1
        if payload["consistency_checks"]:
            L += ["", f"## {sec}. Cross-section consistency", ""]
            for c in payload["consistency_checks"]:
                L.append(f"- {c['id']} [{c['verdict']}]: {c['a'].get('text')} ↔ "
                         f"{c['b'].get('text')}" + (f" — {c.get('note')}" if c.get("note") else ""))
            sec += 1
        if payload["findings"]:
            L += ["", f"## {sec}. Additional findings", ""]
            for f in payload["findings"]:
                L.append(f"- {f['id']} [{f.get('severity')}/{f.get('status')}]: "
                         f"{f.get('verdict')} ({_loc_str(f.get('evidence'))})")
    elif kind == "compliance_check":
        L += ["", f"## {sec}. Compliance checklist ({payload['n_items']} items, "
              f"rate {payload['compliance_rate']})", "",
              "| id | category | guideline | status | severity | item |",
              "|---|---|---|---|---|---|"]
        for it in payload["compliance_items"]:
            L.append(f"| {it['id']} | {it['category']} | {it['guideline']} | "
                     f"**{it['status']}** | {it.get('severity')} | {it['item']} |")
        sec += 1
        L += ["", f"## {sec}. Missing / non-compliant items (actionable)", ""]
        for m in payload["missing_items"]:
            L.append(f"- {m['item_id']} ({m['category']}/{m['guideline']}, {m['status']}): "
                     f"{m['item']}")
            if m.get("missing"):
                L.append(f"  - missing: {m['missing']}")
            if m.get("recommendation"):
                L.append(f"  - fix: {m['recommendation']}")
        sec += 1
        L += ["", f"## {sec}. Coverage by category", ""]
        for cat, c in payload["by_category"].items():
            L.append(f"- {cat}: {c}")
    L += ["", f"## {sec}. Provenance & honesty", "",
          f"- sources used: {prov['sources_used']}",
          f"- sources registered but unused: {prov['sources_unused']}",
          f"- locator issues (human_confirm): {payload.get('locator_issues', 0)}",
          f"- uncertainty items: {len(ir.get('uncertainty', []))}"]
    for u in ir.get("uncertainty", []):
        L.append(f"  - {u.get('item','?')}: {u.get('reason','')} "
                 f"[{u.get('handling','human_confirm')}]")
    L += ["", "Editable artifacts: review.json, checklist.csv, provenance.json, "
          "report.md. Re-run: `python assemble.py --ir <ir.json> --input /input "
          "--out /app/output`."]
    return "\n".join(L) + "\n"


def _checklist_csv(ir, payload, path):
    kind = ir.get("kind")
    rows = []
    if kind == "citation_fact_check":
        for c in payload["claims"]:
            rows.append([c["id"], "claim", "", c["support"], c.get("text", ""),
                         _loc_str(c.get("location_evidence")),
                         c.get("recommendation", "")])
            for sc in c.get("subclaims", []):
                rows.append([sc["id"], "subclaim", "", sc["support"],
                             sc.get("text", ""), _loc_str(sc.get("evidence")),
                             sc.get("rationale", "")])
        for r in payload["references"]:
            rows.append([r["ref_id"], "reference", "", r["match_status"],
                         str(r.get("cited", {}).get("title", "")),
                         _loc_str(r.get("evidence")),
                         "; ".join(m["field"] for m in r["mismatches"])])
    elif kind == "compliance_check":
        for it in payload["compliance_items"]:
            rows.append([it["id"], it["category"], it.get("severity", ""),
                         it["status"], it["item"], _loc_str(it.get("evidence")),
                         it.get("recommendation", "")])
    elif kind == "logic_argument_review":
        for a in payload["arguments"]:
            rows.append([a["id"], "argument", "", a.get("validity", ""),
                         a["conclusion"].get("text", ""),
                         _loc_str(a["conclusion"].get("evidence")),
                         a.get("recommendation", "")])
        for c in payload["consistency_checks"]:
            rows.append([c["id"], "consistency", "", c["verdict"],
                         c["a"].get("text", "") + " <-> " + c["b"].get("text", ""),
                         _loc_str(c["a"].get("evidence")), c.get("note", "")])
        for f in payload.get("findings", []):
            rows.append([f["id"], f.get("dimension", ""), f.get("severity", ""),
                         f.get("status", ""), f.get("verdict", ""),
                         _loc_str(f.get("evidence")), f.get("recommendation", "")])
    elif kind == "methods_stats_review":
        for f in payload["findings"]:
            rows.append([f["id"], f.get("dimension", ""), f.get("severity", ""),
                         f.get("status", ""), f.get("verdict", ""),
                         _loc_str(f.get("evidence")), f.get("recommendation", "")])
        for c in payload["stats_checks"]:
            rows.append([c["id"], "stats_check", "", c["verdict"],
                         c.get("description", ""), _loc_str(c.get("evidence")),
                         "; ".join(f"{x['key']}:{x['verdict']}" for x in c["comparisons"])])
    else:  # quality_review
        for f in payload["findings"]:
            rows.append([f["id"], f.get("dimension", ""), f.get("severity", ""),
                         f.get("status", ""), f.get("verdict", ""),
                         _loc_str(f.get("evidence")), f.get("recommendation", "")])
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "dimension", "severity", "status", "verdict",
                    "locator", "recommendation"])
        w.writerows(rows)
    return len(rows)


# ── build ───────────────────────────────────────────────────────────────────

def build(ir: dict, case: dict, out_dir) -> list:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    kind = ir.get("kind")
    content, docs_out = {}, []
    for d in ir.get("documents", []):
        c = _load_doc_content(ir, case, d)
        content[d["document_id"]] = c
        entry = {"document_id": d["document_id"], "source_id": d.get("source_id"),
                 "role": d.get("role", "other"), "title": d.get("title"),
                 "sha256": c["sha256"] or d.get("sha256"),
                 "content_status": c["content_status"],
                 "n_paragraphs": len(c["paragraphs"])}
        if c.get("hash_mismatch"):
            entry["hash_mismatch"] = c["hash_mismatch"]
        docs_out.append(entry)

    if kind == "quality_review":
        payload = _quality_payload(ir, content)
    elif kind == "citation_fact_check":
        payload = _check_claims(ir, content)
        payload["references"] = _check_references(ir, content)
        payload["locator_issues"] += sum(r.get("locator_issues", 0)
                                         for r in payload["references"])
        payload["n_ref_mismatch"] = sum(1 for r in payload["references"]
                                        if r["match_status"] == "metadata_mismatch")
        payload["n_ref_unverified"] = sum(1 for r in payload["references"]
                                          if r["match_status"] in ("not_provided",
                                                                   "no_cited_metadata"))
    elif kind == "methods_stats_review":
        payload = _methods_payload(ir, case, content)
    elif kind == "logic_argument_review":
        payload = _logic_payload(ir, content)
    elif kind == "compliance_check":
        payload = _compliance_payload(ir, content)
    else:
        raise ValueError(f"unknown kind {kind}")
    payload["manuscript_id"] = ir.get("manuscript_id")
    payload["documents"] = docs_out
    prov = _provenance(ir, payload, docs_out)

    outputs = []

    def emit(name, obj, fmt, role):
        p = out_dir / name
        w4kit.write_json(p, obj)
        outputs.append({"name": name, "path": str(p), "format": fmt, "role": role})

    emit("review.json", payload, "json", "json")
    emit("provenance.json", prov, "json", "provenance_json")
    cp = out_dir / "checklist.csv"
    n_rows = _checklist_csv(ir, payload, cp)
    outputs.append({"name": "checklist.csv", "path": str(cp), "format": "csv", "role": "csv"})
    summary = _summary(ir, payload, docs_out, n_rows)
    status = compute_status(ir, {"errors": []}, summary)
    md = _report_md(ir, case, docs_out, payload, prov, status)
    mp = out_dir / "report.md"
    mp.write_text(md, encoding="utf-8")
    outputs.append({"name": "report.md", "path": str(mp), "format": "md", "role": "md"})
    (out_dir / "_summary.json").write_text(
        __import__("json").dumps(summary, ensure_ascii=False), encoding="utf-8")
    return outputs


def _summary(ir, payload, docs_out, n_rows):
    kind = ir.get("kind")
    s = {"kind": kind, "n_documents": len(docs_out),
         "n_unreadable_documents": sum(1 for d in docs_out
                                       if d["content_status"] not in ("ok", "ir_transcribed")),
         "n_locator_issues": payload.get("locator_issues", 0),
         "n_checklist_rows": n_rows,
         "n_insufficient_evidence": sum(1 for f in ir.get("findings", [])
                                        if f.get("status") == "insufficient_evidence")}
    if kind == "quality_review":
        s["n_findings"] = len(payload["findings"])
        s["n_major"] = sum(1 for f in payload["findings"]
                           if f.get("severity") == "major" and f.get("polarity", "issue") == "issue")
        s["n_uncheckable_categories"] = payload["n_uncheckable_categories"]
        s["overall_quality_normalized"] = payload["overall_quality_normalized"]
        s["decision"] = payload["overall_recommendation"].get("decision")
        if payload["overall_recommendation"].get("decision") == "undetermined":
            s["n_undetermined"] = 1
    elif kind == "citation_fact_check":
        s["n_claims"] = payload["n_claims"]
        s["n_claims_unsupported"] = len(payload["unsupported_claims"])
        s["n_claims_insufficient"] = sum(1 for c in payload["claims"]
                                         if c["support"] == "insufficient")
        s["n_ref_mismatch"] = payload["n_ref_mismatch"]
        s["n_ref_unverified"] = payload["n_ref_unverified"]
        s["n_insufficient_evidence"] += s["n_claims_insufficient"]
    elif kind == "methods_stats_review":
        s["n_findings"] = len(payload["findings"])
        s["n_stats_checks"] = payload["n_stats_checks"]
        s["n_stats_match"] = payload["n_stats_match"]
        s["n_stats_mismatch"] = payload["n_stats_mismatch"]
        s["n_stats_not_recomputable"] = payload["n_stats_not_recomputable"]
    elif kind == "logic_argument_review":
        s["n_arguments"] = payload["n_arguments"]
        s["n_gap"] = payload["n_gap"]
        s["n_fallacy"] = payload["n_fallacy"]
        s["n_argument_insufficient"] = payload["n_argument_insufficient"]
        s["n_inconsistent"] = payload["n_inconsistent"]
        s["n_insufficient_evidence"] += payload["n_argument_insufficient"]
        s["n_premises_not_reported"] = sum(a["n_premises_not_reported"]
                                           for a in payload["arguments"])
    elif kind == "compliance_check":
        s["n_compliance_items"] = payload["n_items"]
        s["n_non_compliant"] = sum(1 for i in payload["compliance_items"]
                                   if i["status"] == "non_compliant")
        s["n_compliance_insufficient"] = payload["n_insufficient"]
        s["compliance_rate"] = payload["compliance_rate"]
        s["n_insufficient_evidence"] += payload["n_insufficient"]
    return s


def compute_status(ir: dict, validation: dict, summary: dict) -> str:
    """Honest overall status. Confirmed findings (even major) mean the review
    SUCCEEDED; only coverage/verification gaps downgrade to partial."""
    if validation.get("errors"):
        return "partial"
    gap_keys = ("n_unreadable_documents", "n_locator_issues", "n_insufficient_evidence",
                "n_uncheckable_categories", "n_undetermined", "n_claims_insufficient",
                "n_ref_mismatch", "n_ref_unverified", "n_stats_not_recomputable",
                "n_argument_insufficient", "n_premises_not_reported",
                "n_compliance_insufficient")
    if any(summary.get(k) for k in gap_keys):
        return "partial"
    if ir.get("uncertainty"):
        return "partial"
    return "success"