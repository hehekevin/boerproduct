"""arena_read_engine — deterministic engine for the 5 product-arena READING kinds.

Kinds: document_parse / translation / summary_notes / nanopublication / knowledge_graph.
The Agent reads the ACTUAL organizer material under /input and fills the reading IR;
this module validates it (source-bound locators + honest status vocabulary), computes
kind-specific checks (term/number/citation preservation, coverage, graph consistency),
builds editable artifacts (JSON/MD/SVG/TriG) and provenance. Stdlib only (+ optional
svgkit for the knowledge-graph SVG). Reuses figkit (case/result.json) and readkit
(shared reading validation vocabulary).

Status vocabulary per record: reported | not_reported | source_conflict |
extraction_failed | insufficient_evidence.  kind tag: reported | inferred.
Never fabricate: gap statuses must carry no value and flag human_confirm.
"""
from __future__ import annotations

import re
from pathlib import Path

import figkit
import readkit

IR_VERSION = "1.0"
KINDS = {"document_parse", "translation", "summary_notes", "nanopublication", "knowledge_graph"}
STATUS = {"reported", "not_reported", "source_conflict", "extraction_failed", "insufficient_evidence"}
GAP_STATUS = STATUS - {"reported"}
KIND_TAG = {"reported", "inferred"}

DEFAULT_FIELDS = {
    "document_parse": ["title", "authors", "abstract", "methods", "results", "conclusion"],
    "summary_notes": ["research_question", "data", "methods", "results", "conclusion", "limitations"],
}
WORKORDER_NAMES = ["target-fields.json", "target_fields.json", "workorder.json", "note-fields.json"]

NP_PREDICATES = {"increases", "decreases", "causes", "inhibits", "activates", "binds",
                 "measures", "uses", "compares", "outperforms", "supports", "contradicts",
                 "part_of", "associated_with", "reports", "contains", "produces", "improves"}
NODE_TYPES = {"researcher", "material", "method", "task", "metric", "conclusion",
              "concept", "dataset", "instrument", "organization", "other"}
EDGE_TYPES = {"uses", "compares", "outperforms", "supports", "contradicts", "causes",
              "increases", "decreases", "inhibits", "activates", "binds", "part_of",
              "measures", "associated_with", "applied_to", "produces", "contains",
              "upstream_of", "reports"}

NUM_RE = re.compile(r"\d+(?:\.\d+)?")
CITE_RE = re.compile(r"\[\d+(?:[,\u2013\-]\s*\d+)*\]")


# ── helpers ─────────────────────────────────────────────────────────────────

def records_of(ir: dict) -> list:
    k = ir.get("kind")
    if k in ("document_parse", "summary_notes"):
        return ir.get("items", [])
    if k == "translation":
        return ir.get("segments", [])
    if k == "nanopublication":
        return ir.get("nanopubs", [])
    if k == "knowledge_graph":
        return ir.get("nodes", []) + ir.get("edges", [])
    return []


def record_id(rec: dict) -> str:
    return rec.get("id") or rec.get("field_id") or rec.get("segment_id") or "?"


def resolve_source_path(src: dict, input_dir) -> Path | None:
    p = src.get("path")
    if not p:
        return None
    cand = Path(p)
    if cand.is_absolute():
        return cand if cand.exists() else None
    for base in (Path(input_dir), Path.cwd()):
        q = base / p
        if q.exists():
            return q
    return None


def load_requested_fields(input_dir) -> list | None:
    """Read the ACTUAL organizer workorder file if present; return requested field ids."""
    for name in WORKORDER_NAMES:
        p = Path(input_dir) / name
        if p.exists():
            try:
                data = figkit.load_json(p)
            except Exception:
                continue
            if isinstance(data, list):
                return [f if isinstance(f, str) else (f.get("field_id") or f.get("id")) for f in data]
            if isinstance(data, dict):
                for key in ("fields", "target_fields", "requested_fields", "note_fields"):
                    if isinstance(data.get(key), list):
                        return [f if isinstance(f, str) else (f.get("field_id") or f.get("id")) for f in data[key]]
    return None


def check_record(rec, rid, sources, errors, warnings, value_key="value"):
    st = rec.get("status")
    if st not in STATUS:
        errors.append(f"{rid}: status must be one of {sorted(STATUS)} (got {st!r})")
    kd = rec.get("kind")
    if kd and kd not in KIND_TAG:
        errors.append(f"{rid}: kind must be reported/inferred")
    evs = rec.get("evidence") or []
    for ev in evs:
        if ev.get("source") not in sources:
            errors.append(f"{rid}: evidence source {ev.get('source')!r} not registered in sources[]")
        if not (ev.get("paragraph_id") or ev.get("quote") or ev.get("page") or ev.get("locator")):
            warnings.append(f"{rid}: evidence lacks paragraph_id/quote locator")
    if st == "reported":
        if not evs:
            errors.append(f"{rid}: status=reported requires >=1 evidence locator")
        elif not any(ev.get("quote") for ev in evs):
            warnings.append(f"{rid}: reported evidence lacks an exact quote")
        if value_key and rec.get(value_key) in (None, "", []):
            errors.append(f"{rid}: status=reported with empty {value_key}")
    if st in ("not_reported", "insufficient_evidence"):
        if value_key and rec.get(value_key) not in (None, "", []):
            errors.append(f"{rid}: {st} must not carry a value (absent != zero, never fabricate)")
        if not rec.get("human_confirm"):
            warnings.append(f"{rid}: {st} should set human_confirm=true")
    if st == "source_conflict" and len(evs) < 2 and not rec.get("conflict"):
        warnings.append(f"{rid}: source_conflict should carry >=2 evidence locators or a conflict note")
    if st == "extraction_failed" and not rec.get("reason"):
        warnings.append(f"{rid}: extraction_failed should carry a reason")
    if kd == "inferred" and not (rec.get("uncertainty") or rec.get("note")):
        warnings.append(f"{rid}: inferred without uncertainty note")


def translation_issues(ir: dict) -> list:
    """Deterministic faithfulness checks: glossary enforcement, number + citation preservation."""
    issues = []
    glossary = ir.get("glossary", [])
    for seg in ir.get("segments", []):
        if seg.get("status") != "reported":
            continue
        sid = record_id(seg)
        src = seg.get("source_text") or ""
        tgt = seg.get("target_text") or ""
        for g in glossary:
            st, tt = g.get("source_term", ""), g.get("target_term", "")
            if st and tt and st.lower() in src.lower() and tt not in tgt:
                issues.append({"segment_id": sid, "type": "term_inconsistent",
                               "detail": f"'{st}' expected as '{tt}' in target", "severity": "must_fix"})
        for n in dict.fromkeys(NUM_RE.findall(src)):
            if n not in set(NUM_RE.findall(tgt)):
                issues.append({"segment_id": sid, "type": "number_missing",
                               "detail": f"number {n} in source not found in target", "severity": "must_fix"})
        for c in dict.fromkeys(CITE_RE.findall(src)):
            if c not in tgt:
                issues.append({"segment_id": sid, "type": "citation_missing",
                               "detail": f"citation marker {c} not preserved", "severity": "must_fix"})
    return issues


# ── validation ──────────────────────────────────────────────────────────────

def validate_ir(ir: dict, input_dir=None) -> dict:
    errors, warnings = [], []
    if ir.get("ir_version") != IR_VERSION:
        errors.append(f"ir_version must be {IR_VERSION}")
    if not ir.get("case_id"):
        errors.append("case_id required (copy from /input/case.json)")
    kind = ir.get("kind")
    if kind not in KINDS:
        errors.append(f"unknown kind {kind!r}; expected one of {sorted(KINDS)}")
    srcs = ir.get("sources", [])
    if not srcs:
        errors.append("sources[] empty: register the ACTUAL /input material files first")
    sources = set()
    for s in srcs:
        sid = s.get("id")
        if not sid:
            errors.append("source without id")
            continue
        if sid in sources:
            errors.append(f"duplicate source id {sid}")
        sources.add(sid)
        if not s.get("path"):
            warnings.append(f"source {sid}: no path (register the real file path under /input)")
        elif input_dir is not None and resolve_source_path(s, input_dir) is None:
            warnings.append(f"source {sid}: file {s.get('path')!r} not found under input dir")

    # shared reading-core checks (items/claims/matrix vocabulary + locators)
    base = readkit.validate_reading(ir)
    errors += base["errors"]
    warnings += base["warnings"]

    recs = records_of(ir)
    if kind in KINDS and not recs:
        errors.append(f"kind {kind}: no records extracted (items/segments/nanopubs/nodes+edges)")
    seen = set()
    for rec in recs:
        rid = record_id(rec)
        if rid in seen:
            errors.append(f"duplicate record id {rid}")
        seen.add(rid)
        vk = {"translation": "target_text", "knowledge_graph": "label"}.get(kind, "value")
        if kind == "knowledge_graph" and "from" in rec:
            vk = "type"
        if kind == "nanopublication":
            vk = None
        check_record(rec, f"{kind}:{rid}", sources, errors, warnings, value_key=vk)

    if kind in ("document_parse", "summary_notes"):
        for it in ir.get("items", []):
            if not it.get("field_id"):
                errors.append(f"item {it.get('id', '?')}: field_id required (one result per requested field)")
        for sec in ir.get("sections", []):
            if sec.get("parent_id") and sec["parent_id"] not in {s.get("id") for s in ir.get("sections", [])}:
                errors.append(f"section {sec.get('id')}: parent_id {sec['parent_id']} not a known section")
            if not sec.get("paragraph_ids"):
                warnings.append(f"section {sec.get('id')}: no paragraph_ids locator")
        requested = (load_requested_fields(input_dir) if input_dir else None) or DEFAULT_FIELDS[kind]
        have = {it.get("field_id") for it in ir.get("items", [])}
        unans = ir.setdefault("unanswered_parts", [])
        for fid in requested:
            if fid and fid not in have and not any(u.get("part") == fid for u in unans):
                unans.append({"part": fid, "status": "not_reported",
                              "reason": "requested field not present in IR", "human_confirm": True})
                warnings.append(f"requested field {fid!r} not covered; added to unanswered_parts (human_confirm)")

    elif kind == "translation":
        for seg in ir.get("segments", []):
            if seg.get("status") == "reported" and not (seg.get("source_text") or "").strip():
                errors.append(f"segment {record_id(seg)}: reported without source_text")
        for g in ir.get("glossary", []):
            if not (g.get("source_term") and g.get("target_term")):
                errors.append("glossary entry needs source_term and target_term")
        for iss in translation_issues(ir)[:12]:
            warnings.append(f"translation {iss['segment_id']}: {iss['type']} — {iss['detail']}")

    elif kind == "nanopublication":
        triples = set()
        for np_ in ir.get("nanopubs", []):
            nid = record_id(np_)
            a = np_.get("assertion") or {}
            if isinstance(a, dict) and a.get("subject") and a.get("predicate") and a.get("object"):
                if a["predicate"] not in NP_PREDICATES:
                    warnings.append(f"nanopub {nid}: predicate {a['predicate']!r} outside controlled vocabulary")
                key = (str(a["subject"]).lower(), a["predicate"], str(a["object"]).lower())
                if key in triples:
                    warnings.append(f"nanopub {nid}: duplicate assertion triple (dedup/merge needed)")
                triples.add(key)
            elif not np_.get("assertion_text"):
                errors.append(f"nanopub {nid}: needs structured assertion {{subject,predicate,object}} or assertion_text")
            else:
                warnings.append(f"nanopub {nid}: only assertion_text; structured triple preferred")
            prov = np_.get("provenance") or {}
            if prov.get("source_id") and prov["source_id"] not in sources:
                errors.append(f"nanopub {nid}: provenance.source_id {prov['source_id']!r} not registered")
            if not (prov.get("authors") or prov.get("year") or prov.get("doi")):
                warnings.append(f"nanopub {nid}: provenance metadata thin (authors/year/doi); mark gaps not_reported, do not invent")

    elif kind == "knowledge_graph":
        nodes = ir.get("nodes", [])
        edges = ir.get("edges", [])
        nids = {n.get("id") for n in nodes}
        labels = {}
        for n in nodes:
            if n.get("type") not in NODE_TYPES:
                errors.append(f"node {n.get('id')}: type {n.get('type')!r} not in {sorted(NODE_TYPES)}")
            lab = (n.get("label") or "").strip().lower()
            if lab in labels:
                warnings.append(f"node {n.get('id')}: label duplicates node {labels[lab]} — alias merge_basis or distinct evidence needed")
            labels[lab] = n.get("id")
        for e in edges:
            eid = e.get("id", "?")
            if e.get("type") not in EDGE_TYPES:
                errors.append(f"edge {eid}: type {e.get('type')!r} not in controlled vocabulary {sorted(EDGE_TYPES)}")
            for end in ("from", "to"):
                if e.get(end) not in nids:
                    errors.append(f"edge {eid}: {end}={e.get(end)!r} is not a known node")
        for q in ir.get("queries", []):
            for nid in q.get("node_ids", []):
                if nid not in nids:
                    errors.append(f"query {q.get('id')}: answer node {nid!r} not in graph")
        if len(ir.get("queries", [])) < 3:
            warnings.append("knowledge_graph: provide >=3 real queries with answer node_ids + evidence")

    ir.setdefault("provenance", {})["pipeline"] = \
        "actual /input material -> reading IR (agent) -> validate -> deterministic build -> result.json"
    return {"ok": not errors, "errors": list(dict.fromkeys(errors)), "warnings": list(dict.fromkeys(warnings))}


# ── build ───────────────────────────────────────────────────────────────────

def build_record_map(ir: dict) -> dict:
    m = {}
    for rec in records_of(ir):
        m[record_id(rec)] = {"status": rec.get("status"), "kind": rec.get("kind"),
                             "evidence": rec.get("evidence", []),
                             "human_confirm": rec.get("human_confirm", False)}
    return m


def _md_evidence(rec) -> str:
    parts = []
    for ev in rec.get("evidence", []):
        loc = ev.get("paragraph_id") or ev.get("page") or ev.get("locator") or "?"
        q = (ev.get("quote") or "")[:120]
        parts.append(f"{ev.get('source')}:{loc} \"{q}\"")
    return "; ".join(parts) or "no locator"


def _kg_scene(ir: dict) -> dict:
    """Deterministic layered SVG: one column per node type, arrows for edges."""
    import svgkit
    nodes, edges = ir.get("nodes", []), ir.get("edges", [])
    types = list(dict.fromkeys(n.get("type", "other") for n in nodes))
    pos, rows = {}, {}
    for n in nodes:
        t = n.get("type", "other")
        col = types.index(t)
        row = rows.get(t, 0)
        rows[t] = row + 1
        pos[n["id"]] = (28 + col * 58, 30 + row * 22)
    w = max(180, 40 + len(types) * 58)
    h = max(100, 40 + max(rows.values(), default=1) * 22)
    node_els, edge_els = [], []
    for n in nodes:
        x, y = pos[n["id"]]
        ev = (n.get("evidence") or [{}])[0]
        src_attrs = {"source": ev.get("source"), "source_locator": ev.get("paragraph_id"), "category": n.get("type")}
        node_els.append({"type": "rect", "id": f"node-{n['id']}", "x": x - 24, "y": y - 6, "w": 48, "h": 12,
                         "rx": 2, "fill": "#eef4fb", "stroke": "#2b5d8a", **src_attrs})
        node_els.append({"type": "text", "x": x, "y": y, "font_pt": 6.5, "text": (n.get("label") or "")[:30], **src_attrs})
    for e in edges:
        if e.get("from") not in pos or e.get("to") not in pos:
            continue
        x1, y1 = pos[e["from"]]
        x2, y2 = pos[e["to"]]
        ev = (e.get("evidence") or [{}])[0]
        edge_els.append({"type": "line", "id": f"edge-{e.get('id')}", "x1": x1, "y1": y1 + 6, "x2": x2, "y2": y2 - 6,
                         "stroke": "#a33" if e.get("type") in ("contradicts", "inhibits", "decreases") else "#444",
                         "dash": "2,1" if e.get("type") in ("compares", "associated_with") else None,
                         "marker_end": "arr-activate",
                         "source": ev.get("source"), "source_locator": ev.get("paragraph_id"),
                         "category": e.get("type"), "value": e.get("type")})
    scene = {"title": f"Knowledge graph — {ir.get('case_id')}",
             "desc": "Source-bound literature knowledge graph; every node/edge carries data-source locator. Editable layers.",
             "canvas": {"width_mm": w, "height_mm": h},
             "layers": [{"id": "edges", "label": "relations", "elements": edge_els},
                        {"id": "nodes", "label": "entities", "elements": node_els}]}
    return scene


def _trig_escape(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _slug(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]+", "_", str(s)).strip("_") or "x"


def _trig(ir: dict) -> str:
    lines = ["@prefix np: <http://www.nanopub.org/nschema#> .",
             "@prefix ex: <http://example.org/bohrium/> .",
             "@prefix dct: <http://purl.org/dc/terms/> .", ""]
    for n in ir.get("nanopubs", []):
        nid = _slug(record_id(n))
        a = n.get("assertion") or {}
        prov = n.get("provenance") or {}
        lines.append(f"ex:{nid} {{ ex:{nid} a np:Nanopublication ; np:hasAssertion ex:{nid}_assertion ; "
                     f"np:hasProvenance ex:{nid}_provenance ; np:hasPublicationInfo ex:{nid}_pubinfo . }}")
        if a.get("subject") and a.get("predicate") and a.get("object"):
            lines.append(f"ex:{nid}_assertion {{ ex:{_slug(a['subject'])} ex:{_slug(a['predicate'])} "
                         f"\"{_trig_escape(a['object'])}\" . }}")
        else:
            lines.append(f"ex:{nid}_assertion {{ ex:{nid} ex:assertionText \"{_trig_escape(n.get('assertion_text', ''))}\" . }}")
        pl = []
        if prov.get("doi"):
            pl.append(f'dct:identifier "{_trig_escape(prov["doi"])}"')
        if prov.get("year"):
            pl.append(f'dct:issued "{_trig_escape(prov["year"])}"')
        for au in prov.get("authors", []) or []:
            pl.append(f'dct:creator "{_trig_escape(au)}"')
        if prov.get("source_id"):
            pl.append(f'dct:source ex:{_slug(prov["source_id"])}')
        lines.append(f"ex:{nid}_provenance {{ ex:{nid}_assertion " + (" ; ".join(pl) if pl else 'dct:source "not_reported"') + " . }")
        lines.append(f"ex:{nid}_pubinfo {{ ex:{nid} dct:created \"{figkit.utc_now()}\" ; "
                     f'dct:creator "arena-nanopublication skill" . }}')
        lines.append("")
    return "\n".join(lines)


def build(ir: dict, case: dict, out_dir, input_dir="/input"):
    """Deterministically build editable artifacts from the validated IR. Returns (artifacts, extra)."""
    out_dir = Path(out_dir)
    kind = ir["kind"]
    artifacts = []

    def add(name, fmt, role):
        artifacts.append({"name": name, "path": str(out_dir / name), "format": fmt, "role": role})

    # real source-file provenance (sha256 of the ACTUAL files)
    src_files = []
    for s in ir.get("sources", []):
        p = resolve_source_path(s, input_dir)
        if p is not None:
            src_files.append({"id": s.get("id"), "path": str(p), "bytes": p.stat().st_size,
                              "sha256": figkit.sha256_file(p)})
        else:
            src_files.append({"id": s.get("id"), "path": s.get("path"), "sha256": None,
                              "note": "file not found at build time; human_confirm"})
    ir.setdefault("provenance", {})["source_files"] = src_files

    recs = records_of(ir)
    gaps = [r for r in recs if r.get("status") in GAP_STATUS]
    unans = ir.get("unanswered_parts", [])
    extra = {"kind": kind, "n_records": len(recs),
             "n_reported": sum(1 for r in recs if r.get("status") == "reported"),
             "n_gaps": len(gaps), "n_unanswered": len(unans)}

    md = [f"# {kind} — {ir.get('case_id')}", "",
          f"Records: {extra['n_records']} (reported {extra['n_reported']}, gaps {extra['n_gaps']}). "
          "Every record below carries its source locator; gaps are flagged, never fabricated.", ""]

    if kind in ("document_parse", "summary_notes"):
        fields = {it.get("field_id"): it for it in ir.get("items", [])}
        figkit.write_json(out_dir / ("fields.json" if kind == "document_parse" else "notes.json"),
                          {"case_id": ir.get("case_id"), "kind": kind, "fields": fields,
                           "sections": ir.get("sections", []), "claims": ir.get("claims", []),
                           "unanswered_parts": unans})
        add("fields.json" if kind == "document_parse" else "notes.json", "json", "json")
        for fid, it in fields.items():
            md.append(f"## {fid} [{it.get('kind', 'reported')}/{it.get('status')}]")
            md.append(f"{it.get('value') if it.get('value') is not None else '(not reported — human_confirm)'}")
            md.append(f"- evidence: {_md_evidence(it)}")
            if it.get("units"):
                md.append(f"- units: {it['units']}")
            md.append("")
        if ir.get("sections"):
            md.append("## Section structure")
            for s in ir.get("sections", []):
                md.append(f"{'  ' * (int(s.get('level', 1)) - 1)}- {s.get('id')} {s.get('title')} "
                          f"(paragraphs: {', '.join(s.get('paragraph_ids', []))})")
        for c in ir.get("claims", []):
            md.append(f"- claim {c.get('id')}: {c.get('text', '')}")
            for sc in c.get("subclaims", []):
                md.append(f"  - {sc.get('text', '')} [{sc.get('support')}] {_md_evidence(sc)}")

    elif kind == "translation":
        issues = translation_issues(ir)
        figkit.write_json(out_dir / "bilingual.json",
                          {"case_id": ir.get("case_id"), "segments": ir.get("segments", []),
                           "glossary": ir.get("glossary", []), "unanswered_parts": unans})
        add("bilingual.json", "json", "json")
        figkit.write_json(out_dir / "translation_check.json",
                          {"n_segments": len(ir.get("segments", [])), "n_issues": len(issues),
                           "issues": issues, "human_confirm": [i["segment_id"] for i in issues]})
        add("translation_check.json", "json", "json")
        extra["n_segments"] = len(ir.get("segments", []))
        extra["n_translation_issues"] = len(issues)
        md.append("| seg | source | target | status | locator |")
        md.append("|---|---|---|---|---|")
        for seg in ir.get("segments", []):
            ev = (seg.get("evidence") or [{}])[0]
            md.append(f"| {record_id(seg)} | {(seg.get('source_text') or '')[:160]} | "
                      f"{(seg.get('target_text') or '(untranslated — human_confirm)')[:160]} | "
                      f"{seg.get('status')} | {ev.get('source')}:{ev.get('paragraph_id', '?')} |")
        md.append("")
        md.append("## Glossary")
        for g in ir.get("glossary", []):
            md.append(f"- {g.get('source_term')} -> {g.get('target_term')}")
        if issues:
            md.append("## Faithfulness issues (human_confirm)")
            for i in issues:
                md.append(f"- {i['segment_id']}: {i['type']} — {i['detail']}")

    elif kind == "nanopublication":
        pubs = []
        for n in ir.get("nanopubs", []):
            pubs.append({"id": record_id(n), "assertion": n.get("assertion") or {"text": n.get("assertion_text")},
                         "conditions": (n.get("assertion") or {}).get("conditions") or n.get("conditions"),
                         "evidence": n.get("evidence", []), "provenance": n.get("provenance", {}),
                         "publication_info": {"generated_at": figkit.utc_now(), "derived_from": n.get("provenance", {}).get("source_id"),
                                              "status": n.get("status"), "kind": n.get("kind", "reported")},
                         "status": n.get("status"), "human_confirm": n.get("human_confirm", False)})
        figkit.write_json(out_dir / "nanopubs.json", {"case_id": ir.get("case_id"), "nanopubs": pubs, "unanswered_parts": unans})
        add("nanopubs.json", "json", "json")
        (out_dir / "nanopubs.trig").write_text(_trig(ir), encoding="utf-8")
        add("nanopubs.trig", "trig", "text")
        extra["n_nanopubs"] = len(pubs)
        for n in ir.get("nanopubs", []):
            a = n.get("assertion") or {}
            md.append(f"## {record_id(n)} [{n.get('kind', 'reported')}/{n.get('status')}]")
            md.append(f"{a.get('subject', '?')} —{a.get('predicate', '?')}→ {a.get('object', n.get('assertion_text', ''))}")
            if a.get("conditions") or n.get("conditions"):
                md.append(f"- conditions: {a.get('conditions') or n.get('conditions')}")
            md.append(f"- evidence: {_md_evidence(n)}")
            md.append(f"- provenance: {n.get('provenance', {})}")
            md.append("")

    elif kind == "knowledge_graph":
        nodes, edges, queries = ir.get("nodes", []), ir.get("edges", []), ir.get("queries", [])
        # deterministic graph computation: components + degrees
        parent = {n["id"]: n["id"] for n in nodes}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        deg = {n["id"]: 0 for n in nodes}
        for e in edges:
            if e.get("from") in parent and e.get("to") in parent:
                parent[find(e["from"])] = find(e["to"])
                deg[e["from"]] += 1
                deg[e["to"]] += 1
        comps = {}
        for nid in parent:
            comps.setdefault(find(nid), []).append(nid)
        nmap = {n["id"]: n for n in nodes}
        qresults = [{"id": q.get("id"), "question": q.get("question"), "answer": q.get("answer"),
                     "node_ids": q.get("node_ids", []),
                     "evidence": [ev for nid in q.get("node_ids", []) if nid in nmap
                                  for ev in nmap[nid].get("evidence", [])]} for q in queries]
        figkit.write_json(out_dir / "graph.json", {"case_id": ir.get("case_id"), "nodes": nodes, "edges": edges,
                                                   "queries": qresults, "unanswered_parts": unans})
        add("graph.json", "json", "json")
        figkit.write_json(out_dir / "graph_check.json",
                          {"n_nodes": len(nodes), "n_edges": len(edges), "n_queries": len(queries),
                           "n_components": len(comps), "components": list(comps.values()),
                           "orphan_nodes": [k for k, v in deg.items() if v == 0], "degree": deg})
        add("graph_check.json", "json", "json")
        try:
            import svgkit
            svgkit.write_svg(out_dir / "graph.svg", _kg_scene(ir))
            add("graph.svg", "svg", "svg")
        except Exception as e:  # noqa: BLE001
            ir.setdefault("uncertainty", []).append({"item": "graph.svg", "reason": str(e),
                                                     "impact": "SVG preview not built", "handling": "graph.json remains editable"})
        extra.update({"n_nodes": len(nodes), "n_edges": len(edges), "n_queries": len(queries),
                      "n_components": len(comps)})
        md.append("## Nodes")
        for n in nodes:
            md.append(f"- {n['id']} ({n.get('type')}) {n.get('label')} [{n.get('status')}] — {_md_evidence(n)}")
        md.append("## Edges")
        for e in edges:
            md.append(f"- {e.get('from')} —{e.get('type')}→ {e.get('to')} [{e.get('status')}] — {_md_evidence(e)}")
        md.append("## Queries")
        for q in qresults:
            md.append(f"- {q['id']}: {q['question']} → {q['answer']} (nodes: {', '.join(q['node_ids'])})")

    # honest uncertainty for every gap (never fabricate)
    unc = ir.setdefault("uncertainty", [])
    for r in gaps:
        rid = record_id(r)
        if not any(u.get("item") == rid for u in unc):
            unc.append({"item": rid, "reason": r.get("reason") or r.get("status"),
                        "impact": "field/record not fully reported", "handling": "human_confirm"})
    for u in unans:
        if not any(x.get("item") == u.get("part") for x in unc):
            unc.append({"item": u.get("part"), "reason": u.get("reason"), "impact": "requested part unanswered",
                        "handling": "human_confirm"})

    if unans:
        md.append("## Unanswered parts (human_confirm)")
        for u in unans:
            md.append(f"- {u.get('part')}: {u.get('reason')} [{u.get('status')}]")
    (out_dir / f"{kind}_result.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    add(f"{kind}_result.md", "md", "md")

    n_issues = extra.get("n_translation_issues", 0)
    status = "success" if not (gaps or unans or n_issues) else "partial"
    extra["_status"] = status
    return artifacts, extra