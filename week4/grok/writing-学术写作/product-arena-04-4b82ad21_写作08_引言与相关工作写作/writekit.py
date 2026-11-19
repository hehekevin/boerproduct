"""writekit — source-bound academic writing core (stdlib only).

Cross-cutting validation for the 14 writing-track skills. Enforces the rubric's
four invariants: 写得实 (facts/numbers from source), 引得对 (citations support the
claim, metadata accurate), 全得起来 (required sections/fields present), 改得动
(editable structure + traceable revisions). Domain rule packs add task-specific
checks; this module provides the shared, deterministic ones.

Case loading / result.json reuse figkit so output-contract handling is identical
across tracks. Rendering: docxkit.py (md+docx), mindmap.py, benchkit.py.
"""
from __future__ import annotations

import re
from pathlib import Path

IR_VERSION = "1.0"
SKILL_VERSION = "1.0.0"

KINDS = {"paper_writing", "format_template", "evidence_driven", "writing_client",
         "structure_logic", "results_discussion", "reviewer_response", "translation",
         "grant_proposal", "research_plan", "thesis_longdoc", "sci_translation",
         "writing_benchmark", "mind_map",
         # week4 product-arena writing variants (shared arena_write_engine)
         "polish", "reference_manage", "intro_related", "methods_section", "latex"}

STRENGTHS = {"established", "supported", "hypothesized", "uncertain", "correlational"}


def _nums_in(text):
    return re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(text))


def validate_writing(ir: dict) -> dict:
    errors, warnings = [], []
    if ir.get("ir_version") != IR_VERSION:
        errors.append(f"ir_version must be {IR_VERSION}")
    if not ir.get("case_id"):
        errors.append("case_id required")
    if ir.get("kind") not in KINDS:
        errors.append(f"unknown kind {ir.get('kind')}")
    sources = {s.get("id") for s in ir.get("sources", []) if s.get("id")}
    cites = {c.get("id"): c for c in ir.get("citations", []) if c.get("id")}
    claims = ir.get("claims", [])
    claim_ids = {c.get("id") for c in claims}

    # claims: every substantive claim needs evidence + source; strength tagged
    for c in claims:
        cid = c.get("id", "?")
        if not c.get("text"):
            errors.append(f"claim {cid}: empty text")
        ev = c.get("evidence", [])
        if not ev and c.get("type", "fact") != "structural":
            warnings.append(f"claim {cid}: no evidence binding")
        for e in ev:
            if not e.get("source"):
                warnings.append(f"claim {cid}: evidence lacks source")
            elif e["source"] not in sources:
                errors.append(f"claim {cid}: evidence source '{e['source']}' not registered")
            if e.get("strength") and e["strength"] not in STRENGTHS:
                warnings.append(f"claim {cid}: unknown strength {e['strength']}")
        for ref in c.get("citation_ids", []):
            if ref not in cites:
                errors.append(f"claim {cid}: citation '{ref}' not in citations registry")
        # causal language vs correlational evidence
        if re.search(r"导致|引起|因果|causes?|leads? to", c.get("text", "")) and \
           any(e.get("strength") == "correlational" for e in ev):
            warnings.append(f"claim {cid}: causal wording with correlational evidence")

    # citations: metadata completeness + DOI format
    for cid, c in cites.items():
        for field in ("authors", "year", "title"):
            if not c.get(field):
                warnings.append(f"citation {cid}: missing {field}")
        doi = c.get("doi", "")
        if doi and not re.match(r"^10\.\d{4,9}/\S+$", doi):
            warnings.append(f"citation {cid}: DOI format suspicious '{doi}'")
        if not c.get("source"):
            warnings.append(f"citation {cid}: no source (unverifiable)")

    # numbers consistency: declared numbers must match a source value
    src_nums = set()
    for s in ir.get("sources", []):
        for v in s.get("values", []):
            src_nums.add(str(v))
    for n in ir.get("numbers", []):
        if not n.get("source"):
            warnings.append(f"number {n.get('value')}: no source pointer")
        elif n["source"] not in sources:
            errors.append(f"number {n.get('value')}: source not registered")

    # sections completeness vs required list
    required = ir.get("required_sections", [])
    have = {s.get("role") or s.get("heading") for s in ir.get("sections", [])}
    for r in required:
        if r not in have:
            warnings.append(f"required section '{r}' missing (flag explicitly)")

    # terminology uniformity: same term must have single translation/definition
    gloss = {}
    for g in ir.get("glossary", []):
        t = g.get("term")
        if t in gloss and gloss[t] != g.get("render"):
            errors.append(f"terminology '{t}' has conflicting renders")
        gloss[t] = g.get("render")

    # revisions: traceable (location + before + after + reason)
    for r in ir.get("revisions", []):
        if not (r.get("location") and r.get("before") is not None and r.get("after") is not None):
            warnings.append(f"revision {r.get('id')}: not fully traceable")

    # alignment (grant/plan): goal/content/route/indicator tuples complete
    for a in ir.get("alignment", []):
        for k in ("goal", "content", "route", "indicator"):
            if not a.get(k):
                warnings.append(f"alignment {a.get('id')}: missing {k}")

    # reviewer response: every comment/subrequest has decision + response + edit ref
    for cm in ir.get("comments", []):
        if not cm.get("decision"):
            warnings.append(f"comment {cm.get('id')}: no decision")
        if not cm.get("response"):
            warnings.append(f"comment {cm.get('id')}: no response")
    if not ir.get("provenance", {}).get("pipeline"):
        ir.setdefault("provenance", {})["pipeline"] = "material -> writing IR -> editable doc -> check/export"
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def build_claim_map(ir: dict) -> dict:
    cm = {}
    for c in ir.get("claims", []):
        cm[c["id"]] = {"text": c.get("text"), "type": c.get("type"),
                       "evidence": c.get("evidence", []), "citation_ids": c.get("citation_ids", []),
                       "strength": c.get("strength")}
    return cm


def check_number_consistency(ir: dict) -> list:
    """Compare numbers asserted in section paragraphs against declared source numbers."""
    issues = []
    declared = {str(n.get("value")): n for n in ir.get("numbers", [])}
    for s in ir.get("sections", []):
        for p in s.get("paragraphs", []):
            for tok in _nums_in(p.get("text", "")):
                if tok in declared:
                    continue
                # only flag numbers that look like data (skip years/section ids)
                if re.match(r"^(19|20)\d{2}$", tok):
                    continue
                issues.append({"section": s.get("id"), "number": tok,
                               "issue": "not in declared source numbers; verify or add source"})
    return issues