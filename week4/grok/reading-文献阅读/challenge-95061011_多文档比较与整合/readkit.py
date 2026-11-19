"""readkit — source-bound literature-reading core (stdlib only).

Cross-cutting validation for the 10 reading-track skills. Enforces the output
triad: 解析结果 (cover task, traceable), 证据与边界 (locators + unreported/uncertain,
can't-judge not written as fact), 运行状态 (success/partial/cannot-judge/refuse +
reason). Domain rule packs add task specifics; this module provides shared checks.

Case loading / result.json reuse figkit. Helpers: clean.py (unit conversion/dedup),
formula.py (symbolic/numeric check), compare.py (matrix/comparability), benchkit.py.
"""
from __future__ import annotations

import re
from pathlib import Path
import figkit

IR_VERSION = "1.0"
SKILL_VERSION = "1.0.0"
KINDS = {"figure_parse", "literature_qa", "multi_doc_compare", "reading_client",
         "conclusion_extraction", "evidence_verification", "formula_reasoning",
         "reproduction", "reading_benchmark", "data_cleaning"}
QA_STATUS = {"answered", "partial", "insufficient_evidence", "input_error"}
# week4 v2 record-status vocabulary (organizer revision) accepted alongside QA_STATUS
RECORD_STATUS = {"reported", "not_reported", "source_conflict", "extraction_failed",
                 "insufficient_evidence"}
SUPPORT = {"supports", "partial", "insufficient", "unrelated", "contradicts"}
ITEM_KIND = {"reported", "inferred"}

WORKORDER_NAMES = ("target-fields.json", "comparison-workorder.json",
                   "claims-to-verify.json", "questions.json", "workorder.json",
                   "benchmark-workorder.json", "fields.json", "tasks.json")


def load_workorders(input_dir="/input") -> dict:
    """Discover organizer workorder files in /input and extract the requested
    field/claim/question ids. Defensive about schema (hidden cases vary): collect
    any field_id/claim_id/question_id keys, plus ids under fields/claims/questions
    lists. The agent still reads the actual material; this guarantees coverage."""
    input_dir = Path(input_dir)
    raw = {}
    if input_dir.exists():
        for p in sorted(input_dir.glob("*.json")):
            if p.name == "case.json":
                continue
            low = p.name.lower()
            if p.name in WORKORDER_NAMES or any(
                    t in low for t in ("workorder", "target", "claim", "question", "field", "task")):
                try:
                    raw[p.name] = figkit.load_json(p)
                except Exception:  # noqa: BLE001
                    raw[p.name] = {"_parse_error": True}
    req = {"fields": [], "claims": [], "questions": []}
    for data in raw.values():
        _collect_requests(data, req)
    return {"files": list(raw), "raw": raw, "requests": req}


def _collect_requests(obj, req, hint=None):
    if isinstance(obj, dict):
        for idkey, bucket in (("field_id", "fields"), ("target_field_id", "fields"),
                              ("claim_id", "claims"), ("question_id", "questions")):
            v = obj.get(idkey)
            if isinstance(v, str) and v not in req[bucket]:
                req[bucket].append(v)
        for k, v in obj.items():
            kl = k.lower()
            nh = hint
            if "field" in kl or "target" in kl:
                nh = "fields"
            elif "claim" in kl:
                nh = "claims"
            elif "question" in kl:
                nh = "questions"
            _collect_requests(v, req, nh)
    elif isinstance(obj, list):
        for it in obj:
            if isinstance(it, str):
                if hint and it not in req[hint]:
                    req[hint].append(it)
            elif isinstance(it, dict):
                if hint and isinstance(it.get("id"), str) and it["id"] not in req[hint]:
                    req[hint].append(it["id"])
                _collect_requests(it, req, hint)


def apply_coverage(ir: dict, workorders: dict) -> dict:
    """Ensure ONE result per requested field/claim/question. Any requested id the
    agent did not extract is added as an honest insufficient_evidence placeholder
    (value null, no fabricated evidence) and recorded in unanswered_parts. This
    directly satisfies the week4 'one result per requested field_id' requirement
    even when extraction misses a field — a gap is reported, never invented."""
    req = workorders.get("requests", {})
    added = {"fields": [], "claims": [], "questions": []}
    items = ir.setdefault("items", [])
    have = set()
    for it in items:
        for k in ("field_id", "id", "question_id"):
            if it.get(k):
                have.add(it[k])
    for fid in req.get("fields", []):
        if fid not in have:
            items.append({"id": fid, "field_id": fid, "value": None, "units": None,
                          "kind": "reported", "status": "insufficient_evidence",
                          "evidence": [],
                          "note": "requested field not extracted from material; needs human_confirm"})
            ir.setdefault("unanswered_parts", []).append(
                {"field_id": fid, "reason": "not extracted from material", "handling": "human_confirm"})
            added["fields"].append(fid)
            have.add(fid)
    for qid in req.get("questions", []):
        if qid not in have:
            items.append({"id": qid, "question_id": qid, "answer": None,
                          "kind": "reported", "status": "insufficient_evidence",
                          "evidence": [],
                          "note": "requested question not answered from material; needs human_confirm"})
            ir.setdefault("unanswered_parts", []).append(
                {"question_id": qid, "reason": "not answered from material", "handling": "human_confirm"})
            added["questions"].append(qid)
            have.add(qid)
    claims = ir.setdefault("claims", [])
    havec = {c.get("id") for c in claims}
    for cid in req.get("claims", []):
        if cid not in havec:
            claims.append({"id": cid, "claim": None, "verdict": "insufficient_evidence",
                           "subclaims": [],
                           "note": "requested claim not verified against material; needs human_confirm"})
            added["claims"].append(cid)
            havec.add(cid)
    return added


def validate_reading(ir: dict) -> dict:
    errors, warnings = [], []
    if ir.get("ir_version") != IR_VERSION:
        errors.append(f"ir_version must be {IR_VERSION}")
    if not ir.get("case_id"):
        errors.append("case_id required")
    if ir.get("kind") not in KINDS:
        errors.append(f"unknown kind {ir.get('kind')}")
    sources = {s.get("id") for s in ir.get("sources", []) if s.get("id")}

    def loc_ok(ev):
        return ev.get("source") in sources or ev.get("document_id")

    # items (extraction / qa / figure fields)
    for it in ir.get("items", []):
        iid = it.get("id", it.get("field_id", it.get("question_id", "?")))
        if it.get("kind") and it["kind"] not in ITEM_KIND:
            errors.append(f"item {iid}: kind must be reported/inferred")
        if it.get("status") and it["status"] not in (QA_STATUS | RECORD_STATUS):
            warnings.append(f"item {iid}: non-standard status {it['status']}")
        evs = it.get("evidence", [])
        if not evs and it.get("status") not in ("insufficient_evidence", "input_error"):
            warnings.append(f"item {iid}: no evidence locator")
        for ev in evs:
            if not loc_ok(ev):
                errors.append(f"item {iid}: evidence source not registered")
            if not (ev.get("paragraph_id") or ev.get("quote") or ev.get("locator")):
                warnings.append(f"item {iid}: evidence lacks paragraph/quote locator")
        # inferred must be flagged, not presented as reported fact
        if it.get("kind") == "inferred" and not it.get("uncertainty"):
            warnings.append(f"item {iid}: inferred without uncertainty note")

    # verification claims: support degree valid; unrelated != supports
    for c in ir.get("claims", []):
        for sc in c.get("subclaims", []):
            if sc.get("support") and sc["support"] not in SUPPORT:
                errors.append(f"claim {c.get('id')}: invalid support {sc['support']}")
            if sc.get("support") == "supports" and not sc.get("evidence"):
                errors.append(f"claim {c.get('id')}: 'supports' without evidence")

    # comparison matrix: cells carry source_document_id + paragraph_id
    for row in ir.get("matrix", {}).get("rows", []):
        for cell in row.get("cells", []):
            if not cell.get("source_document_id"):
                errors.append(f"matrix row {row.get('document_id')}: cell {cell.get('field')} lacks source_document_id")
            if not cell.get("paragraph_id"):
                warnings.append(f"matrix cell {cell.get('field')}: lacks paragraph_id")

    # cleaning: keep original + conversion formula + precision; dedup key
    for r in ir.get("cleaning", {}).get("records", []):
        if r.get("original") is None:
            warnings.append(f"clean record {r.get('id')}: original not preserved")
        uc = r.get("unit_conversion")
        if uc and not (uc.get("formula") and uc.get("from") and uc.get("to")):
            warnings.append(f"clean record {r.get('id')}: conversion lacks formula/from/to")
        if not r.get("source"):
            warnings.append(f"clean record {r.get('id')}: no source")

    # reproduction: results have tolerance + within; params sourced
    for res in ir.get("reproduction", {}).get("results", []):
        if res.get("tolerance") is None:
            warnings.append(f"repro result {res.get('metric')}: no declared tolerance")
        if "within" not in res:
            warnings.append(f"repro result {res.get('metric')}: within-tolerance not computed")
    for p in ir.get("reproduction", {}).get("params", []):
        if not p.get("source"):
            warnings.append(f"repro param {p.get('name')}: no source (paper vs repo)")

    # formulas: variables defined; numeric check present if claimed
    for f in ir.get("formulas", []):
        for v in f.get("variables", []):
            if not v.get("definition"):
                warnings.append(f"formula {f.get('id')}: variable {v.get('symbol')} undefined")
    if not ir.get("provenance", {}).get("pipeline"):
        ir.setdefault("provenance", {})["pipeline"] = "material -> reading IR -> structured result -> check"
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def build_item_map(ir: dict) -> dict:
    m = {}
    for it in ir.get("items", []):
        key = it.get("id") or it.get("field_id") or it.get("question_id")
        m[key] = {"value": it.get("value", it.get("answer")), "units": it.get("units"),
                  "kind": it.get("kind"), "status": it.get("status"),
                  "evidence": it.get("evidence", []), "condition": it.get("condition")}
    return m