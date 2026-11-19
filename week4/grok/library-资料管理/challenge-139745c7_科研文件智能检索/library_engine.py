"""library_engine — deterministic source-bound engine for the week4 LIBRARY track.

Covers all five library workorder kinds over an organizer-provided LOCAL document
library (real files, aliases, administrative version notes, metadata, searches,
questions, annotations, recovery/index operations):

  library_manage   index + metadata + alias resolution + version chains + ops log
  library_search   keyword/field search with hard filters, ranked hits, locators
  library_classify rule-based taxonomy classification + rationale + abstain
  library_qa       extractive QA (keyword-matched sentences) + evidence locators
  library_annotate locator-bound annotations + knowledge cards

The Agent reads the ACTUAL /input material and fills the IR; this engine
validates, computes and builds editable artifacts. Every index entry, hit,
classification, answer and annotation carries a source locator
(source_id + document_id + paragraph_id/field + quote). Nothing is fabricated:
missing metadata is flagged not_reported, weak classifications abstain, empty
searches/QA report no_hits / insufficient_evidence, and every evidence quote is
verified against the actual paragraph text when the content file is readable.

API:  validate_ir(ir) -> {ok, errors, warnings}
      build(ir, case, out_dir) -> outputs[]   (w4kit artifact descriptors)

Stdlib only; imports w4kit (shared core, copied next to this file).
"""
from __future__ import annotations

import re
from pathlib import Path

import w4kit

IR_VERSION = "1.0"
KINDS = {"library_manage", "library_search", "library_classify",
         "library_qa", "library_annotate"}
META_STATUS = {"reported", "inferred", "not_reported", "source_conflict",
               "extraction_failed"}
OP_STATUS = {"done", "skipped", "failed", "conflict", "pending"}
DEFAULT_META_FIELDS = ["title", "authors", "year", "type", "project", "doi"]
STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "is", "are", "was", "were", "and",
    "or", "to", "for", "with", "what", "which", "where", "when", "how", "does",
    "do", "did", "by", "from", "this", "that", "it", "its", "as", "be", "can",
    "的", "了", "是", "在", "和", "与", "吗", "呢", "什么", "哪些", "哪个",
    "如何", "请问", "一下", "我们", "以及", "还有", "没有", "多少",
}


# ── text helpers ────────────────────────────────────────────────────────────

def _tokens(text: str) -> set:
    """Latin/digit words + Chinese character bigrams (unigram for 1-char runs)."""
    text = (text or "").lower()
    toks = set()
    for w in re.findall(r"[a-z0-9][a-z0-9_\-\.]*", text):
        w = w.strip("-.")
        if len(w) >= 2 and w not in STOPWORDS:
            toks.add(w)
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(run) == 1:
            if run not in STOPWORDS:
                toks.add(run)
        else:
            for i in range(len(run) - 1):
                bg = run[i:i + 2]
                if bg not in STOPWORDS:
                    toks.add(bg)
    return toks


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _paragraphs(text: str) -> list:
    """Split text into paragraphs; honour 'Page N' markers (week3 client.py)."""
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


def _sentences(text: str) -> list:
    parts = re.split(r"(?<=[.!?。！？；;])\s*", text or "")
    return [p.strip() for p in parts if p.strip()]


def _resolve(ir: dict, case: dict, rel) -> Path | None:
    """Resolve a relative data path against IR dir, then input dir, then cwd."""
    if not rel:
        return None
    p = Path(rel)
    if p.is_absolute():
        return p if p.exists() else None
    bases = [ir.get("_ir_dir"), (case or {}).get("input_dir"), "."]
    for b in bases:
        if not b:
            continue
        cand = Path(b) / p
        if cand.exists():
            return cand
    return None


def _doc_source(ir: dict, doc: dict) -> dict | None:
    return next((s for s in ir.get("sources", [])
                 if s.get("id") == doc.get("source_id")), None)


def _load_doc_content(ir: dict, case: dict, doc: dict) -> dict:
    """Load actual paragraphs + sha256 from the real file. Honest on failure."""
    out = {"paragraphs": [], "content_status": "ok", "sha256": None,
           "content_path": None}
    if doc.get("paragraphs"):  # agent transcribed actual text into IR
        out["paragraphs"] = [
            {"id": p.get("id", f"p{i+1}"), "page": p.get("page", 1),
             "text": p.get("text", "")}
            for i, p in enumerate(doc["paragraphs"])]
        out["content_status"] = "ir_transcribed"
    rel = doc.get("content_path") or doc.get("path")
    if not rel:
        src = _doc_source(ir, doc)
        rel = (src or {}).get("path")
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


def _meta_value(doc: dict, field: str):
    m = (doc.get("metadata") or {}).get(field)
    if isinstance(m, dict):
        return m.get("value")
    return m


def _meta_entry(doc: dict, field: str) -> dict:
    m = (doc.get("metadata") or {}).get(field)
    if isinstance(m, dict):
        return m
    if m is not None:
        return {"value": m, "status": "reported", "evidence": None}
    return {"value": None, "status": "not_reported", "evidence": None}


def _ev_entry(source_id, document_id=None, paragraph_id=None, quote=None,
              page=None, field=None) -> dict:
    ev = w4kit.evidence(source_id, paragraph_id=paragraph_id, quote=quote,
                        page=page, field=field)
    if document_id:
        ev["document_id"] = document_id
    return ev


def _quote_ok(paragraphs: list, paragraph_id, quote) -> bool:
    if not quote:
        return False
    par = next((p for p in paragraphs if p["id"] == paragraph_id), None)
    if par is None:
        return False
    return _norm_ws(quote) in _norm_ws(par["text"])


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
    errors += w4kit.check_sources(ir)

    docs = ir.get("documents", [])
    dids = [d.get("document_id") for d in docs]
    if not docs:
        errors.append("documents[] empty: the library index needs actual documents")
    if len(dids) != len(set(dids)):
        errors.append("duplicate document_id")
    dset = set(dids)
    alias_map = {}
    for d in docs:
        did = d.get("document_id", "?")
        if not d.get("source_id"):
            errors.append(f"doc {did}: source_id required (register the actual file)")
        if not (d.get("title") or _meta_value(d, "title")):
            warnings.append(f"doc {did}: no title (flagged not_reported, not invented)")
        for a in d.get("aliases", []):
            key = _norm_ws(str(a)).lower()
            if key in alias_map and alias_map[key] != did:
                warnings.append(f"alias '{a}' claimed by {alias_map[key]} and {did}: conflict")
            alias_map[key] = did
        for f, m in (d.get("metadata") or {}).items():
            if not isinstance(m, dict):
                warnings.append(f"doc {did} metadata.{f}: use {{value,status,evidence}} form")
                continue
            st = m.get("status", "reported")
            if st not in META_STATUS:
                errors.append(f"doc {did} metadata.{f}: invalid status '{st}'")
            if st in ("reported", "inferred", "source_conflict") and not m.get("evidence"):
                errors.append(f"doc {did} metadata.{f}: status {st} requires evidence locator")
            if st == "inferred" and not m.get("uncertainty"):
                warnings.append(f"doc {did} metadata.{f}: inferred without uncertainty note")
        vids = [v.get("version_id") for v in d.get("versions", [])]
        if len(vids) != len(set(vids)):
            errors.append(f"doc {did}: duplicate version_id")
        for v in d.get("versions", []):
            sup = v.get("supersedes")
            if sup and sup not in vids:
                errors.append(f"doc {did}: version {v.get('version_id')} supersedes unknown '{sup}'")
            if v.get("note") and not v.get("evidence"):
                warnings.append(f"doc {did} version {v.get('version_id')}: note without evidence")

    for op in ir.get("operations", []):
        oid = op.get("op_id", "?")
        if op.get("status") not in OP_STATUS:
            errors.append(f"op {oid}: invalid status '{op.get('status')}'")
        if op.get("status") in ("skipped", "failed", "conflict") and not op.get("reason"):
            errors.append(f"op {oid}: {op['status']} requires a reason (no silent skips)")
        tgt = op.get("target")
        if tgt and tgt in dset:
            pass
        elif tgt and op.get("target_kind", "document") == "document" and tgt not in dset:
            warnings.append(f"op {oid}: target '{tgt}' is not a registered document_id")

    for s in ir.get("searches", []):
        if not s.get("query"):
            errors.append(f"search {s.get('search_id','?')}: query required")
        for did in s.get("scope", []):
            if did not in dset:
                errors.append(f"search {s.get('search_id')}: scope doc '{did}' unknown")
    for q in ir.get("questions", []):
        if not q.get("question"):
            errors.append(f"question {q.get('question_id','?')}: question text required")
        for did in q.get("scope", []):
            if did not in dset:
                errors.append(f"question {q.get('question_id')}: scope doc '{did}' unknown")
        if q.get("answer") and not q.get("evidence"):
            errors.append(f"question {q.get('question_id')}: agent answer requires evidence locators")

    tax = ir.get("taxonomy")
    if kind == "library_classify" and not tax:
        errors.append("kind library_classify requires taxonomy{}")
    if tax:
        cids = [c.get("id") for c in tax.get("categories", [])]
        if not cids:
            errors.append("taxonomy.categories empty")
        if len(cids) != len(set(cids)):
            errors.append("duplicate taxonomy category id")
        for c in tax.get("categories", []):
            if not c.get("rules"):
                warnings.append(f"category {c.get('id')}: no rules (will never match)")
            for r in c.get("rules", []):
                if not r.get("keywords"):
                    errors.append(f"category {c.get('id')} rule {r.get('rule_id','?')}: keywords required")

    aids = set()
    for a in ir.get("annotations", []):
        aid = a.get("annotation_id", "?")
        aids.add(aid)
        if a.get("document_id") not in dset:
            errors.append(f"annotation {aid}: unknown document_id")
        if not a.get("paragraph_id") and not a.get("field"):
            errors.append(f"annotation {aid}: needs paragraph_id or field locator")
        if not a.get("note"):
            errors.append(f"annotation {aid}: note text required")
        if a.get("kind") and a["kind"] not in ("reported", "inferred"):
            errors.append(f"annotation {aid}: kind must be reported/inferred")
    for k in ir.get("knowledge_cards", []):
        kid = k.get("card_id", "?")
        if not k.get("statement"):
            errors.append(f"card {kid}: statement required")
        if not k.get("evidence") and not k.get("from_annotations"):
            errors.append(f"card {kid}: needs evidence or from_annotations")
        for ref in k.get("from_annotations", []):
            if ref not in aids:
                errors.append(f"card {kid}: from_annotations references unknown '{ref}'")

    if kind == "library_search" and not ir.get("searches"):
        errors.append("kind library_search requires searches[]")
    if kind == "library_qa" and not ir.get("questions"):
        errors.append("kind library_qa requires questions[]")
    if kind == "library_annotate" and not ir.get("annotations"):
        errors.append("kind library_annotate requires annotations[]")
    if kind == "library_manage" and not ir.get("operations"):
        warnings.append("kind library_manage: no operations[] recorded (index-only run)")
    if not ir.get("provenance", {}).get("pipeline"):
        ir.setdefault("provenance", {})["pipeline"] = \
            "actual material -> IR -> validate -> index/compute -> artifact -> result"
    return {"ok": not errors, "errors": errors, "warnings": warnings}


# ── index computation ───────────────────────────────────────────────────────

def _build_index(ir: dict, case: dict) -> dict:
    docs_out, content = [], {}
    alias_map, alias_conflicts = {}, []
    for d in ir.get("documents", []):
        did = d["document_id"]
        c = _load_doc_content(ir, case, d)
        content[did] = c
        meta = {}
        for f in DEFAULT_META_FIELDS + [k for k in (d.get("metadata") or {})
                                        if k not in DEFAULT_META_FIELDS]:
            meta[f] = _meta_entry(d, f)
        if meta.get("title", {}).get("value") is None and d.get("title"):
            meta["title"] = {"value": d["title"], "status": "reported",
                             "evidence": _ev_entry(d.get("source_id"), did, field="title")}
        # version chain
        versions = d.get("versions", [])
        superseded = {v.get("supersedes") for v in versions if v.get("supersedes")}
        latest = None
        cand = [v for v in versions if v.get("version_id") not in superseded]
        if cand:
            latest = sorted(cand, key=lambda v: str(v.get("date") or ""))[-1]
        elif versions:
            latest = versions[-1]
        for a in d.get("aliases", []):
            key = _norm_ws(str(a)).lower()
            if key in alias_map and alias_map[key]["document_id"] != did:
                alias_conflicts.append({"alias": a, "documents":
                                        [alias_map[key]["document_id"], did],
                                        "handling": "human_confirm"})
            else:
                alias_map[key] = {"alias": a, "document_id": did,
                                  "canonical_title": meta.get("title", {}).get("value")}
        entry = {
            "document_id": did, "source_id": d.get("source_id"),
            "title": meta.get("title", {}).get("value"),
            "path": d.get("path") or (_doc_source(ir, d) or {}).get("path"),
            "aliases": d.get("aliases", []),
            "metadata": meta,
            "versions": versions,
            "latest_version_id": (latest or {}).get("version_id"),
            "sha256": c["sha256"] or d.get("sha256"),
            "content_status": c["content_status"],
            "n_paragraphs": len(c["paragraphs"]),
        }
        if c.get("hash_mismatch"):
            entry["hash_mismatch"] = c["hash_mismatch"]
        docs_out.append(entry)

    # content-hash duplicate groups (real hashes of actual files)
    by_hash = {}
    for e in docs_out:
        if e.get("sha256"):
            by_hash.setdefault(e["sha256"], []).append(e["document_id"])
    hash_dups = [{"sha256": h, "documents": ids, "basis": "content_hash"}
                 for h, ids in by_hash.items() if len(ids) > 1]
    # bibliographic dedup via shared core (DOI exact + fuzzy title/year)
    recs = [{"id": e["document_id"], "title": e.get("title") or "",
             "year": _meta_value({"metadata": e["metadata"]}, "year"),
             "doi": _meta_value({"metadata": e["metadata"]}, "doi")}
            for e in docs_out]
    bib_dedup = w4kit.dedup_records(recs)

    # metadata coverage / missing flags
    missing, filled, total = [], 0, 0
    for e in docs_out:
        for f in DEFAULT_META_FIELDS:
            total += 1
            st = e["metadata"].get(f, {}).get("status")
            if st in ("reported", "inferred"):
                filled += 1
            else:
                missing.append({"document_id": e["document_id"], "field": f,
                                "status": st or "not_reported"})
    coverage = {"fields_checked": total, "fields_filled": filled,
                "fill_rate": round(filled / total, 4) if total else None,
                "missing": missing}

    # operations log with real existence checks
    ops_out = []
    for op in ir.get("operations", []):
        o = dict(op)
        if op.get("status") == "done" and op.get("to_path"):
            f = _resolve(ir, case, op["to_path"])
            o["verified"] = f is not None
            if f is None:
                o["verification_note"] = "to_path not found under input/IR dir; human_confirm"
        if op.get("status") == "done" and op.get("type") == "recover" and op.get("target"):
            tgt = next((e for e in docs_out if e["document_id"] == op["target"]), None)
            if tgt is not None:
                o["verified"] = tgt["content_status"] in ("ok", "ir_transcribed")
                if not o["verified"]:
                    o["verification_note"] = f"recovery target content_status={tgt['content_status']}"
        ops_out.append(o)

    unreadable = [{"document_id": e["document_id"], "content_status": e["content_status"]}
                  for e in docs_out if e["content_status"] not in ("ok", "ir_transcribed")]
    return {"documents": docs_out, "alias_map": alias_map,
            "alias_conflicts": alias_conflicts,
            "duplicates": {"content_hash_groups": hash_dups,
                           "bibliographic": bib_dedup},
            "coverage": coverage, "operations": ops_out,
            "unreadable": unreadable,
            "n_documents": len(docs_out)}


# ── search ──────────────────────────────────────────────────────────────────

def _doc_passes_filters(doc: dict, filters: dict) -> tuple:
    for field, want in (filters or {}).items():
        if field == "version":
            if str(want).lower() == "latest":
                continue  # index already resolves latest per doc
            vids = [v.get("version_id") for v in doc.get("versions", [])]
            labels = [str(v.get("label", "")) for v in doc.get("versions", [])]
            if str(want) not in vids and str(want) not in labels:
                return False, f"version={want}"
            continue
        if field == "document_ids":
            if doc["document_id"] not in want:
                return False, "document_ids"
            continue
        got = _meta_value({"metadata": doc.get("metadata", {})}, field)
        if got is None or str(got).strip().lower() != str(want).strip().lower():
            return False, f"{field}={want} (actual: {got if got is not None else 'not_reported'})"
    return True, None


def _run_search(ir: dict, index: dict, content: dict, s: dict) -> dict:
    sid = s.get("search_id", "S?")
    qtok = _tokens(s.get("query", ""))
    # alias expansion: query mentioning an alias points at the canonical doc
    alias_hits = []
    ql = _norm_ws(s.get("query", "")).lower()
    for key, a in index["alias_map"].items():
        if key and key in ql:
            alias_hits.append(a)
    scope = set(s.get("scope") or [])
    hits, excluded = [], []
    for doc in index["documents"]:
        did = doc["document_id"]
        if scope and did not in scope:
            continue
        ok, why = _doc_passes_filters(doc, s.get("filters"))
        if not ok:
            excluded.append({"document_id": did, "reason": why})
            continue
        paras = content.get(did, {}).get("paragraphs", [])
        title_tok = _tokens(doc.get("title") or "")
        meta_tok = set()
        for f, m in doc.get("metadata", {}).items():
            if m.get("value") is not None:
                meta_tok |= _tokens(str(m["value"]))
        best = []
        for p in paras:
            ptok = _tokens(p["text"])
            overlap = qtok & ptok
            if not overlap:
                continue
            score = len(overlap) + 2 * len(qtok & title_tok) + len(qtok & meta_tok)
            best.append((score, p, sorted(overlap)))
        if alias_hits and any(a["document_id"] == did for a in alias_hits):
            if not best and paras:
                p = paras[0]
                best.append((1, p, ["<alias match>"]))
        for score, p, matched in sorted(best, key=lambda x: -x[0])[:3]:
            quote = p["text"][:240]
            hits.append({"score": score, "document_id": did,
                         "version_id": doc.get("latest_version_id"),
                         "source_id": doc.get("source_id"),
                         "paragraph_id": p["id"], "page": p["page"],
                         "quote": quote, "matched_tokens": matched,
                         "locator": _ev_entry(doc.get("source_id"), did,
                                              p["id"], quote, p["page"])})
    hits.sort(key=lambda h: -h["score"])
    for i, h in enumerate(hits):
        h["rank"] = i + 1
    status = "ok" if hits else "no_hits"
    return {"search_id": sid, "query": s.get("query"),
            "filters": s.get("filters", {}), "filters_applied_strictly": True,
            "alias_expansion": alias_hits, "status": status,
            "n_hits": len(hits), "hits": hits[:20],
            "excluded_by_filters": excluded,
            "note": None if hits else
            "no paragraph matched under the hard filters; filters were NOT relaxed"}


# ── classification ──────────────────────────────────────────────────────────

def _classify(ir: dict, index: dict, content: dict) -> dict:
    tax = ir.get("taxonomy") or {}
    threshold = float(tax.get("abstain_threshold", 0.25))
    multi = bool(tax.get("multi_label", True))
    items = []
    for doc in index["documents"]:
        did = doc["document_id"]
        paras = content.get(did, {}).get("paragraphs", [])
        fields_text = {}
        for f, m in doc.get("metadata", {}).items():
            if m.get("value") is not None:
                fields_text[f] = str(m["value"])
        full_text = " ".join(fields_text.values()) + " " + \
            " ".join(p["text"] for p in paras)
        scores = []
        for c in tax.get("categories", []):
            total_w = sum(float(r.get("weight", 1.0)) for r in c.get("rules", [])) or 1.0
            matched, rationale = 0.0, []
            for r in c.get("rules", []):
                kws = [str(k).lower() for k in r.get("keywords", [])]
                flds = r.get("fields") or list(fields_text.keys()) + ["text"]
                hit_kw, ev = [], None
                for kw in kws:
                    where = None
                    if "text" in flds and kw in full_text.lower():
                        where = "text"
                    for f in flds:
                        if f != "text" and kw in fields_text.get(f, "").lower():
                            where = f"metadata.{f}"
                            break
                    if where:
                        hit_kw.append(kw)
                        if ev is None:
                            if where.startswith("metadata."):
                                ev = _ev_entry(doc.get("source_id"), did,
                                               field=where.split(".", 1)[1],
                                               quote=fields_text.get(where.split(".", 1)[1], "")[:200])
                            else:
                                par = next((p for p in paras
                                            if kw in p["text"].lower()), None)
                                if par:
                                    ev = _ev_entry(doc.get("source_id"), did,
                                                   par["id"], par["text"][:200],
                                                   par["page"])
                if hit_kw:
                    w = float(r.get("weight", 1.0))
                    matched += w
                    rationale.append({"rule_id": r.get("rule_id", "?"),
                                      "matched_keywords": hit_kw,
                                      "weight": w, "evidence": ev})
            conf = round(matched / total_w, 4)
            scores.append({"category_id": c.get("id"), "category_name": c.get("name"),
                           "score": round(matched, 4), "confidence": conf,
                           "rationale": rationale})
    # (per-doc loop continues below; scores collected per doc)
        scores.sort(key=lambda x: -x["score"])
        top = scores[0] if scores else None
        if top and top["score"] > 0 and top["confidence"] >= threshold:
            labels = [top]
            if multi:
                labels += [x for x in scores[1:]
                           if x["score"] > 0 and x["confidence"] >= threshold]
            items.append({"document_id": did, "status": "classified",
                          "primary_category": top["category_id"],
                          "primary_category_name": top["category_name"],
                          "labels": [{"category_id": x["category_id"],
                                      "confidence": x["confidence"]} for x in labels],
                          "confidence": top["confidence"],
                          "rationale": top["rationale"],
                          "alternatives": [{"category_id": x["category_id"],
                                            "confidence": x["confidence"]}
                                           for x in scores[1:4]],
                          "locator": _ev_entry(doc.get("source_id"), did, field="title",
                                               quote=(doc.get("title") or "")[:200])})
        else:
            items.append({"document_id": did, "status": "abstain",
                          "primary_category": None, "labels": [],
                          "confidence": top["confidence"] if top else 0.0,
                          "reason": "no rule matched" if not top or top["score"] == 0
                          else f"confidence {top['confidence']} < threshold {threshold}",
                          "rationale": (top or {}).get("rationale", []),
                          "handling": "human_confirm",
                          "locator": _ev_entry(doc.get("source_id"), did, field="title",
                                               quote=(doc.get("title") or "")[:200])})
    n_cls = sum(1 for i in items if i["status"] == "classified")
    return {"taxonomy": {"categories": [{"id": c.get("id"), "name": c.get("name")}
                                        for c in tax.get("categories", [])],
                         "abstain_threshold": threshold, "multi_label": multi},
            "items": items, "n_classified": n_cls,
            "n_abstain": len(items) - n_cls}


# ── extractive QA ───────────────────────────────────────────────────────────

def _answer_question(ir: dict, index: dict, content: dict, q: dict) -> dict:
    qid = q.get("question_id", "Q?")
    scope = set(q.get("scope") or [])
    docs = [d for d in index["documents"] if not scope or d["document_id"] in scope]
    if q.get("answer"):  # agent-provided answer: bind + verify its evidence
        evs, verified = [], 0
        for ev in q.get("evidence", []):
            did = ev.get("document_id")
            e = dict(ev)
            if did and ev.get("paragraph_id") and ev.get("quote"):
                ok = _quote_ok(content.get(did, {}).get("paragraphs", []),
                               ev["paragraph_id"], ev["quote"])
                e["quote_verified"] = ok
                verified += 1 if ok else 0
            evs.append(e)
        status = "answered" if evs else "insufficient_evidence"
        return {"question_id": qid, "question": q.get("question"),
                "answer": q["answer"], "kind": "inferred", "status": status,
                "evidence": evs, "evidence_verified_count": verified,
                "note": "agent-provided answer bound to IR evidence; quotes checked against actual text"}
    qtok = _tokens(q.get("question", ""))
    scored = []
    for doc in docs:
        did = doc["document_id"]
        for p in content.get(did, {}).get("paragraphs", []):
            for sent in _sentences(p["text"]):
                overlap = qtok & _tokens(sent)
                if overlap:
                    scored.append((len(overlap), doc, p, sent, sorted(overlap)))
    scored.sort(key=lambda x: -x[0])
    picked, seen_par = [], set()
    for score, doc, p, sent, matched in scored:
        key = (doc["document_id"], p["id"])
        if key in seen_par:
            continue
        seen_par.add(key)
        picked.append((score, doc, p, sent, matched))
        if len(picked) >= 3:
            break
    if not picked:
        return {"question_id": qid, "question": q.get("question"),
                "answer": None, "kind": "reported",
                "status": "insufficient_evidence", "evidence": [],
                "note": "no keyword-matched sentence in scope; not fabricated"}
    evidence = [_ev_entry(doc.get("source_id"), doc["document_id"], p["id"],
                          sent, p["page"])
                for _, doc, p, sent, _ in picked]
    return {"question_id": qid, "question": q.get("question"),
            "answer": " ".join(s for _, _, _, s, _ in picked),
            "kind": "reported", "status": "answered", "evidence": evidence,
            "matched_tokens": [m for _, _, _, _, m in picked],
            "method": "extractive keyword-matched sentences (deterministic)"}


# ── annotations & knowledge cards ───────────────────────────────────────────

def _annotations(ir: dict, index: dict, content: dict) -> dict:
    dmap = {d["document_id"]: d for d in index["documents"]}
    anns = []
    for a in ir.get("annotations", []):
        aid = a.get("annotation_id", "?")
        did = a.get("document_id")
        doc = dmap.get(did, {})
        paras = content.get(did, {}).get("paragraphs", [])
        rec = dict(a)
        rec["source_id"] = doc.get("source_id")
        if a.get("paragraph_id"):
            par = next((p for p in paras if p["id"] == a["paragraph_id"]), None)
            rec["page"] = par["page"] if par else a.get("page")
            if par is None:
                rec["locator_status"] = "paragraph_not_found"
                rec["handling"] = "human_confirm"
            elif a.get("quote"):
                ok = _quote_ok(paras, a["paragraph_id"], a["quote"])
                rec["quote_verified"] = ok
                rec["locator_status"] = "bound" if ok else "quote_mismatch"
                if not ok:
                    rec["handling"] = "human_confirm"
            else:
                rec["locator_status"] = "bound_no_quote"
        else:
            rec["locator_status"] = "field_bound"
        anns.append(rec)
    cards = []
    for k in ir.get("knowledge_cards", []):
        kid = k.get("card_id", "?")
        rec = dict(k)
        evs, nver = [], 0
        for ev in k.get("evidence", []):
            e = dict(ev)
            did = ev.get("document_id")
            if did and ev.get("paragraph_id") and ev.get("quote"):
                ok = _quote_ok(content.get(did, {}).get("paragraphs", []),
                               ev["paragraph_id"], ev["quote"])
                e["quote_verified"] = ok
                nver += 1 if ok else 0
            evs.append(e)
        rec["evidence"] = evs
        rec["evidence_verified_count"] = nver
        linked = [a for a in anns if a.get("annotation_id") in k.get("from_annotations", [])]
        rec["linked_annotations"] = [a["annotation_id"] for a in linked]
        rec["documents"] = sorted({a["document_id"] for a in linked} |
                                  {e.get("document_id") for e in evs if e.get("document_id")})
        cards.append(rec)
    bad = [a["annotation_id"] for a in anns
           if a.get("locator_status") in ("paragraph_not_found", "quote_mismatch")]
    return {"annotations": anns, "knowledge_cards": cards,
            "n_annotations": len(anns), "n_cards": len(cards),
            "locator_issues": bad,
            "by_document": {did: sum(1 for a in anns if a.get("document_id") == did)
                            for did in dmap}}


# ── provenance & report ─────────────────────────────────────────────────────

def _provenance(ir: dict, index: dict, parts: dict) -> dict:
    items = []
    for d in index["documents"]:
        locs = [_ev_entry(d.get("source_id"), d["document_id"], field="file",
                          quote=d.get("title"))]
        for f, m in d.get("metadata", {}).items():
            if m.get("evidence"):
                locs.append(m["evidence"])
        items.append({"item_type": "index_entry", "item_id": d["document_id"],
                      "locators": locs})
    for op in index["operations"]:
        items.append({"item_type": "operation", "item_id": op.get("op_id"),
                      "locators": [op["evidence"]] if op.get("evidence") else []})
    for s in parts.get("search", {}).get("searches", []):
        items.append({"item_type": "search", "item_id": s["search_id"],
                      "locators": [h["locator"] for h in s["hits"]]})
    for it in parts.get("classify", {}).get("items", []):
        locs = [r["evidence"] for r in it.get("rationale", []) if r.get("evidence")]
        items.append({"item_type": "classification", "item_id": it["document_id"],
                      "locators": locs or [it["locator"]]})
    for a in parts.get("qa", {}).get("answers", []):
        items.append({"item_type": "answer", "item_id": a["question_id"],
                      "locators": a.get("evidence", [])})
    for a in parts.get("annotate", {}).get("annotations", []):
        items.append({"item_type": "annotation", "item_id": a.get("annotation_id"),
                      "locators": [_ev_entry(a.get("source_id"), a.get("document_id"),
                                             a.get("paragraph_id"), a.get("quote"),
                                             a.get("page"), a.get("field"))]})
    for k in parts.get("annotate", {}).get("knowledge_cards", []):
        items.append({"item_type": "knowledge_card", "item_id": k.get("card_id"),
                      "locators": k.get("evidence", [])})
    used = set()
    for it in items:
        for loc in it["locators"]:
            if loc.get("source_id"):
                used.add(loc["source_id"])
    for d in index["documents"]:
        if d.get("source_id"):
            used.add(d["source_id"])
    all_ids = {s.get("id") for s in ir.get("sources", [])}
    return {"pipeline": ir.get("provenance", {}).get("pipeline"),
            "items": items, "sources_used": sorted(used),
            "sources_unused": sorted(all_ids - used),
            "changes": ir.get("provenance", {}).get("changes", [])}


def _report_md(ir: dict, case: dict, index: dict, parts: dict, prov: dict) -> str:
    L = [f"# Library workorder report — {case.get('case_id')}",
         "", f"kind: `{ir.get('kind')}` | documents: {index['n_documents']} | "
         f"generated: {w4kit.utc_now()}",
         "", "All entries below are computed from the actual input files via the IR; "
         "every claim carries a source locator. Missing metadata is flagged, never invented.",
         "", "## 1. Document index", "",
         "| doc | title | aliases | latest version | sha256 (first 12) | content |",
         "|---|---|---|---|---|---|"]
    for d in index["documents"]:
        L.append(f"| {d['document_id']} | {d.get('title') or 'not_reported'} | "
                 f"{', '.join(d.get('aliases', [])) or '—'} | "
                 f"{d.get('latest_version_id') or '—'} | "
                 f"{(d.get('sha256') or '—')[:12]} | {d['content_status']} |")
    cov = index["coverage"]
    L += ["", f"Metadata fill rate: {cov['fields_filled']}/{cov['fields_checked']} "
          f"({cov['fill_rate']}). Missing fields (not_reported):"]
    for m in cov["missing"][:30]:
        L.append(f"- {m['document_id']}.{m['field']} [{m['status']}]")
    if index["alias_conflicts"]:
        L += ["", "### Alias conflicts (human_confirm)"]
        for c in index["alias_conflicts"]:
            L.append(f"- '{c['alias']}' claimed by {c['documents']}")
    dups = index["duplicates"]
    if dups["content_hash_groups"]:
        L += ["", "### Content-hash duplicate groups"]
        for g in dups["content_hash_groups"]:
            L.append(f"- {g['documents']} share sha256 {g['sha256'][:12]}…")
    bib = dups["bibliographic"]
    if bib["n_duplicates_removed"]:
        L += ["", f"### Bibliographic dedup: {bib['n_input']} records → "
              f"{bib['n_clusters']} clusters"]
        for c in bib["clusters"]:
            if c["n_members"] > 1:
                L.append(f"- {c['cluster_id']}: {c['members']} (match={c['match']}, "
                         f"conflicts={c['conflicts']})")
    if index["operations"]:
        L += ["", "## 2. Operations log (recovery / index / rename / move)", "",
              "| op | type | target | status | verified | reason |", "|---|---|---|---|---|---|"]
        for o in index["operations"]:
            L.append(f"| {o.get('op_id')} | {o.get('type')} | {o.get('target','—')} | "
                     f"{o.get('status')} | {o.get('verified','—')} | {o.get('reason','—')} |")
    if index["unreadable"]:
        L += ["", "### Unreadable / missing content (honest gaps)"]
        for u in index["unreadable"]:
            L.append(f"- {u['document_id']}: {u['content_status']}")
    sec = 3
    sr = parts.get("search")
    if sr:
        L += ["", f"## {sec}. Search results", ""]
        sec += 1
        for s in sr["searches"]:
            L.append(f"### {s['search_id']}: {s['query']} — **{s['status']}** "
                     f"({s['n_hits']} hits, filters strict)")
            for h in s["hits"][:10]:
                L.append(f"- rank {h['rank']} (score {h['score']}) {h['document_id']} "
                         f"{h['paragraph_id']} p{h['page']}: “{h['quote'][:120]}…”")
            if s["excluded_by_filters"]:
                L.append(f"- excluded by filters: {s['excluded_by_filters']}")
            if s["note"]:
                L.append(f"- note: {s['note']}")
    cl = parts.get("classify")
    if cl:
        L += ["", f"## {sec}. Classification "
              f"({cl['n_classified']} classified / {cl['n_abstain']} abstain)", ""]
        sec += 1
        for it in cl["items"]:
            if it["status"] == "classified":
                L.append(f"- {it['document_id']} → **{it['primary_category']}** "
                         f"(confidence {it['confidence']})")
                for r in it["rationale"]:
                    L.append(f"  - rule {r['rule_id']} matched {r['matched_keywords']}")
            else:
                L.append(f"- {it['document_id']} → ABSTAIN ({it['reason']}); human_confirm")
    qa = parts.get("qa")
    if qa:
        L += ["", f"## {sec}. Knowledge-base Q&A", ""]
        sec += 1
        for a in qa["answers"]:
            L.append(f"### {a['question_id']}: {a['question']} — **{a['status']}** "
                     f"[{a['kind']}]")
            L.append(f"A: {a['answer'] or '—'}")
            for e in a.get("evidence", []):
                L.append(f"- evidence {e.get('document_id','?')} "
                         f"{e.get('paragraph_id','?')} p{e.get('page','?')}: "
                         f"“{(e.get('quote') or '')[:120]}”"
                         + (f" [verified={e['quote_verified']}]"
                            if "quote_verified" in e else ""))
    an = parts.get("annotate")
    if an:
        L += ["", f"## {sec}. Annotations ({an['n_annotations']}) & knowledge cards "
              f"({an['n_cards']})", ""]
        sec += 1
        for a in an["annotations"]:
            L.append(f"- {a.get('annotation_id')} @ {a.get('document_id')} "
                     f"{a.get('paragraph_id') or a.get('field')} "
                     f"[{a.get('locator_status')}]: {a.get('note')}")
        for k in an["knowledge_cards"]:
            L.append(f"- CARD {k.get('card_id')} [{k.get('kind','inferred')}]: "
                     f"{k.get('statement')} (docs: {k.get('documents')})")
        if an["locator_issues"]:
            L.append(f"- locator issues (human_confirm): {an['locator_issues']}")
    L += ["", f"## {sec}. Provenance & honesty", "",
          f"- sources used: {prov['sources_used']}",
          f"- sources registered but unused: {prov['sources_unused']}",
          f"- uncertainty items: {len(ir.get('uncertainty', []))}"]
    for u in ir.get("uncertainty", []):
        L.append(f"  - {u.get('item','?')}: {u.get('reason','')} "
                 f"[{u.get('handling','human_confirm')}]")
    L += ["", "Editable artifacts: library_index.json"
          + (", search_results.json" if sr else "")
          + (", classification.json" if cl else "")
          + (", qa_answers.json" if qa else "")
          + (", annotations.json" if an else "")
          + ", provenance.json. Re-run: `python assemble.py --ir <ir.json> "
            "--input /input --out /app/output`."]
    return "\n".join(L) + "\n"


# ── build ───────────────────────────────────────────────────────────────────

def build(ir: dict, case: dict, out_dir) -> list:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = _build_index(ir, case)
    content = {d["document_id"]: _load_doc_content(ir, case, d)
               for d in ir.get("documents", [])}
    parts = {}
    if ir.get("searches"):
        parts["search"] = {"searches": [_run_search(ir, index, content, s)
                                        for s in ir["searches"]]}
    if ir.get("taxonomy"):
        parts["classify"] = _classify(ir, index, content)
    if ir.get("questions"):
        answers = [_answer_question(ir, index, content, q) for q in ir["questions"]]
        parts["qa"] = {"answers": answers,
                       "n_answered": sum(1 for a in answers if a["status"] == "answered"),
                       "n_insufficient": sum(1 for a in answers
                                             if a["status"] == "insufficient_evidence")}
    if ir.get("annotations") or ir.get("knowledge_cards"):
        parts["annotate"] = _annotations(ir, index, content)
    prov = _provenance(ir, index, parts)

    outputs = []

    def emit(name, obj, fmt, role):
        p = out_dir / name
        w4kit.write_json(p, obj)
        outputs.append({"name": name, "path": str(p), "format": fmt, "role": role})

    emit("library_index.json", index, "json", "json")
    if "search" in parts:
        emit("search_results.json", parts["search"], "json", "search_json")
    if "classify" in parts:
        emit("classification.json", parts["classify"], "json", "classify_json")
    if "qa" in parts:
        emit("qa_answers.json", parts["qa"], "json", "qa_json")
    if "annotate" in parts:
        emit("annotations.json", parts["annotate"], "json", "annotate_json")
    emit("provenance.json", prov, "json", "provenance_json")
    md = _report_md(ir, case, index, parts, prov)
    mp = out_dir / "report.md"
    mp.write_text(md, encoding="utf-8")
    outputs.append({"name": "report.md", "path": str(mp), "format": "md", "role": "md"})

    # summary for result.json extra + honest status signal
    summary = {"n_documents": index["n_documents"],
               "metadata_fill_rate": index["coverage"]["fill_rate"],
               "n_missing_metadata_fields": len(index["coverage"]["missing"]),
               "n_alias_conflicts": len(index["alias_conflicts"]),
               "n_hash_duplicate_groups": len(index["duplicates"]["content_hash_groups"]),
               "n_operations": len(index["operations"]),
               "n_ops_failed_or_skipped": sum(1 for o in index["operations"]
                                              if o.get("status") in ("failed", "skipped", "conflict")),
               "n_unreadable_documents": len(index["unreadable"])}
    if "search" in parts:
        summary["n_searches"] = len(parts["search"]["searches"])
        summary["n_searches_no_hits"] = sum(1 for s in parts["search"]["searches"]
                                            if s["status"] == "no_hits")
    if "classify" in parts:
        summary["n_classified"] = parts["classify"]["n_classified"]
        summary["n_abstain"] = parts["classify"]["n_abstain"]
    if "qa" in parts:
        summary["n_answered"] = parts["qa"]["n_answered"]
        summary["n_insufficient_evidence"] = parts["qa"]["n_insufficient"]
    if "annotate" in parts:
        summary["n_annotations"] = parts["annotate"]["n_annotations"]
        summary["n_knowledge_cards"] = parts["annotate"]["n_cards"]
        summary["n_locator_issues"] = len(parts["annotate"]["locator_issues"])
    (out_dir / "_summary.json").write_text(
        __import__("json").dumps(summary, ensure_ascii=False), encoding="utf-8")
    return outputs


def compute_status(ir: dict, validation: dict, summary: dict) -> str:
    """Honest overall status from validation + computed gaps."""
    if validation.get("errors"):
        return "partial"
    gap_keys = ("n_alias_conflicts", "n_ops_failed_or_skipped", "n_unreadable_documents",
                "n_searches_no_hits", "n_abstain", "n_insufficient_evidence",
                "n_locator_issues")
    if any(summary.get(k) for k in gap_keys):
        return "partial"
    if ir.get("uncertainty"):
        return "partial"
    return "success"