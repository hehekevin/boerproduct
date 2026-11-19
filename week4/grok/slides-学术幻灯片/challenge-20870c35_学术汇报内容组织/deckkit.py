"""deckkit — source-bound academic deck core (stdlib only).

Validation + provenance for the Deck IR shared by the three slides-track skills.
Rendering is build_deck.py (python-pptx); structure checks check_deck.py; export
export_deck.py; orchestration assemble_deck.py. Case loading / result.json reuse
figkit so the output contract handling is identical across tracks.
"""
from __future__ import annotations

import re
from pathlib import Path

import figkit

IR_VERSION = "1.0"
SKILL_VERSION = "1.0.0"

VALID_ROLES = {"title", "outline", "background", "question", "method", "result",
               "discussion", "limitation", "conclusion", "qa", "backup", "section"}
# Narrative backbone that a complete academic talk should cover.
BACKBONE = ["question", "method", "result", "conclusion"]


def validate_deck(ir: dict) -> dict:
    errors, warnings = [], []
    if ir.get("ir_version") != IR_VERSION:
        errors.append(f"ir_version must be {IR_VERSION}")
    if not ir.get("case_id"):
        errors.append("case_id required (copy from case.json)")
    if ir.get("kind") not in {"academic_ppt", "content_organization", "template_adaptation"}:
        errors.append(f"unknown kind {ir.get('kind')}")
    sources = {s.get("id") for s in ir.get("sources", []) if s.get("id")}
    pages = ir.get("pages", [])
    if not pages:
        errors.append("no pages planned")
    tpl = ir.get("template", {})
    max_b = tpl.get("max_bullets", 5)
    max_w = tpl.get("max_words_per_bullet", 22)
    min_pt = tpl.get("min_pt", 14)
    if tpl.get("body_pt", 18) < min_pt:
        errors.append("body_pt below min_pt (unreadable)")

    roles = [p.get("role") for p in pages]
    for bb in BACKBONE:
        if bb not in roles and not (bb == "question" and "background" in roles):
            warnings.append(f"narrative backbone missing role '{bb}'")
    if pages and pages[0].get("role") != "title":
        warnings.append("first page should be role=title")

    target = ir.get("slide_count_target")
    if target and len(pages) > target:
        warnings.append(f"page count {len(pages)} exceeds target {target}")
    dur = ir.get("duration_min")
    if dur and len(pages) > dur * 1.5 + 2:
        warnings.append(f"page count {len(pages)} likely too many for {dur} min")

    for p in pages:
        pid = p.get("id", "?")
        if p.get("role") not in VALID_ROLES:
            errors.append(f"page {pid}: invalid role {p.get('role')}")
        if not p.get("claim"):
            errors.append(f"page {pid}: missing single claim")
        if not p.get("notes") and p.get("role") not in ("title", "outline", "section"):
            warnings.append(f"page {pid}: no speaker notes")
        bs = p.get("bullets", [])
        if len(bs) > max_b:
            warnings.append(f"page {pid}: {len(bs)} bullets > max {max_b} (overload)")
        for b in bs:
            wc = len(re.findall(r"\S+", b.get("text", "")))
            if wc > max_w:
                warnings.append(f"page {pid}: bullet {wc} words > {max_w} (compress)")
            if not b.get("source"):
                warnings.append(f"page {pid}: bullet lacks source pointer")
            elif b["source"] not in sources:
                errors.append(f"page {pid}: bullet source '{b['source']}' not registered")
        for f in p.get("figures", []):
            if not f.get("image_path") and not f.get("chart"):
                errors.append(f"page {pid}: figure {f.get('ref')} has neither image_path nor chart (no placeholder allowed)")
            if not f.get("source"):
                warnings.append(f"page {pid}: figure {f.get('ref')} lacks source")
            elif f["source"] not in sources:
                errors.append(f"page {pid}: figure source '{f['source']}' not registered")
        if not p.get("source") and p.get("role") not in ("title", "outline", "section", "qa"):
            warnings.append(f"page {pid}: no page-level source pointer")

    if not ir.get("qa") and ir.get("kind") == "content_organization":
        warnings.append("content_organization should include Q&A prep (qa[])")
    if not any(e.get("format") == "pptx" for e in ir.get("exports", [])):
        ir.setdefault("exports", []).append({"format": "pptx"})
    if not ir.get("provenance", {}).get("pipeline"):
        ir.setdefault("provenance", {})["pipeline"] = "material -> deck IR -> editable pptx -> render/export"
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def build_page_map(ir: dict) -> dict:
    pm = {}
    for p in ir.get("pages", []):
        pm[p["id"]] = {
            "role": p.get("role"), "claim": p.get("claim"),
            "source": p.get("source"), "source_locator": p.get("source_locator"),
            "bullets": [{"text": b.get("text"), "source": b.get("source"), "source_locator": b.get("source_locator")} for b in p.get("bullets", [])],
            "figures": [{"ref": f.get("ref"), "source": f.get("source"), "source_locator": f.get("source_locator")} for f in p.get("figures", [])],
            "evidence_strength": p.get("evidence_strength"),
        }
    return pm