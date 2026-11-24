"""auto_read.py — deterministic "autopilot" entry point for the week4 READING track
(carryover architecture: assemble_read.py + readkit.py + figkit.py).

Reads the ACTUAL organizer-provided local materials under --input, auto-extracts
a complete reading IR (sources / items / claims / matrix / figures / cleaning /
formulas / coverage / unanswered_parts), writes it to --work, then runs the
PACKAGE'S OWN assemble_read.py (readkit.validate_reading + apply_coverage +
domain helper + figkit.build_result) so the validate+build path is identical to
the manual workflow. Stdlib only; additive — does not modify any sibling module.

Usage:
  PYTHONDONTWRITEBYTECODE=1 python auto_read.py --input /input --out /app/output \
      [--work /app/work] [--kind KIND]

Design rules (mirrors engines/search/auto_search.py):
  * Never fabricate: every value/quote comes from real file content; missing ->
    insufficient_evidence / not_reported + human_confirm, never invented.
  * Judgment-heavy fields (answer selection, claim support, figure typing) use
    deterministic evidence-grounded heuristics flagged human_confirm => the
    overall run status is forced to "partial" (honest).
  * Defensive extraction: a bad/missing file becomes an honest gap, never a crash.
  * The WHOLE pipeline is wrapped: on ANY exception an honest result.json is
    still written (status partial/failed) preserving output_contract + case_id.
  * After this baseline runs, the agent may refine work/reading_ir.json within
    budget and re-run assemble_read.py to improve judgment fields.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import traceback
import zlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    import figkit
    import readkit
except Exception:  # catastrophic import failure -> emergency writer below
    figkit = None
    readkit = None

AUTO_NOTE = ("auto_read autopilot: deterministic extraction from ACTUAL local "
             "materials + the package's own assemble_read.py (readkit validate + "
             "domain helper + result writer). No online retrieval, no fabricated "
             "values/quotes. Judgment fields use documented evidence-grounded "
             "heuristics flagged human_confirm; refine work/reading_ir.json and "
             "re-run assemble_read.py to improve.")

STOPWORDS = set("""a an the of for and or to in on at by with from as is are was
were be been being this that these those it its their his her our your my we you
they he she them us i not no nor only own same so than too very can will just
should now study studies paper article review using use used based via between
into over under after before during about against both each few more most other
some such all any do does did done has have had having if then else when where
which who whom what how why also may might must shall could would one two three
new old high low large small results result method methods approach approaches
show shows shown found report reported reports according given figure fig table
""".split())

SKILL_KIND = {
    "literature-intelligent-qa": "literature_qa",
    "scientific-figure-parsing": "figure_parse",
    "multi-document-comparison": "multi_doc_compare",
    "literature-conclusion-data-extraction": "conclusion_extraction",
    "literature-evidence-verification": "evidence_verification",
    "formula-parsing-math-reasoning": "formula_reasoning",
    "paper-reproduction-method-verification": "reproduction",
    "literature-reading-benchmark-eval": "reading_benchmark",
    "literature-data-cleaning-standardization": "data_cleaning",
}

WORKORDER_HINTS = [
    ("evidence_verification", ["claims-to-verify", "claim"]),
    ("multi_doc_compare", ["comparison-workorder", "comparison", "compare"]),
    ("data_cleaning", ["cleaning-workorder", "clean"]),
    ("formula_reasoning", ["formula"]),
    ("reading_benchmark", ["benchmark-workorder", "benchmark"]),
    ("reproduction", ["reproduction-workorder", "reproduction", "replication", "repro"]),
    ("literature_qa", ["questions.json", "question"]),
    ("conclusion_extraction", ["target-fields", "fields.json"]),
]


# ── small helpers ────────────────────────────────────────────────────────────

def tokens(text):
    return {t for t in re.findall(r"[a-z0-9\u4e00-\u9fff]+", str(text or "").lower())
            if len(t) >= 3 and t not in STOPWORDS}


def clip(s, n=500):
    s = str(s)
    return s if len(s) <= n else s[:n]


def sentences(text):
    parts = re.split(r"(?<=[.!?;])\s+|\n", str(text or ""))
    return [p.strip() for p in parts if p.strip()]


def exact_quote(text, needle, limit=400):
    """Return an EXACT substring of text around needle (sentence if possible)."""
    if not text or not needle:
        return None
    idx = text.lower().find(str(needle).lower())
    if idx < 0:
        return None
    start = max(text.rfind(". ", 0, idx), text.rfind("\n", 0, idx)) + 1
    end = text.find(". ", idx)
    if end < 0:
        end = min(len(text), idx + limit)
    else:
        end += 1
    q = text[start:min(end, start + limit)].strip()
    return q if q and q in text else text[idx:idx + limit]


def pdf_text(data: bytes) -> str:
    """Best-effort stdlib PDF text salvage (inflate FlateDecode + text operators)."""
    chunks = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        raw = m.group(1)
        try:
            raw = zlib.decompress(raw)
        except Exception:
            pass
        try:
            s = raw.decode("utf-8", errors="replace")
        except Exception:
            continue
        if "Tj" in s or "TJ" in s:
            parts = re.findall(r"\((?:\\.|[^\\()])*\)", s)
            txt = " ".join(p[1:-1] for p in parts)
            txt = txt.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
            if txt.strip():
                chunks.append(txt)
    if chunks:
        return "\n\n".join(chunks)
    return data.decode("utf-8", errors="replace")


def read_material_text(path):
    data = Path(path).read_bytes()
    if str(path).lower().endswith(".pdf") or data[:5] == b"%PDF-":
        return pdf_text(data)
    return data.decode("utf-8", errors="replace")


def parse_paragraphs(text):
    """Split text into paragraphs with ids/pages/sections. Handles [Pn] markers
    and markdown headers like '## p1-para1 (Methods, page 2)'."""
    paras = []
    cur_id, cur_page, cur_section, buf = None, None, None, []

    def flush():
        nonlocal buf, cur_id, cur_page, cur_section
        body = "\n".join(buf).strip()
        if body:
            pid = cur_id or f"P{len(paras) + 1}"
            paras.append({"id": pid, "text": body, "page": cur_page,
                          "section": cur_section})
        buf = []

    for ln in text.splitlines():
        hm = re.match(r"^#{1,6}\s+(.+?)\s*(?:\(([^)]*)\))?\s*$", ln)
        pm = re.match(r"^\s*\[(P\d+)\]\s*(.*)$", ln)
        if hm:
            flush()
            cur_id = hm.group(1).strip()
            cur_page, cur_section = None, None
            meta = hm.group(2) or ""
            pg = re.search(r"page\s*(\d+)", cur_id + " " + meta, re.I)
            if pg:
                cur_page = int(pg.group(1))
            sec = re.split(r",", meta)[0].strip()
            cur_section = sec or None
            continue
        if pm:
            flush()
            cur_id, cur_page, cur_section = pm.group(1), None, None
            if pm.group(2):
                buf.append(pm.group(2))
            continue
        if not ln.strip():
            flush()
            cur_id, cur_page, cur_section = None, None, None
            continue
        buf.append(ln)
    flush()
    if not paras and text.strip():
        paras.append({"id": "P1", "text": text.strip(), "page": None, "section": None})
    # enrich section from inline "(Sec N)" / "Section N" / "Methods:" markers
    for p in paras:
        if not p["section"]:
            m = re.search(r"\((Sec(?:tion)?\.?\s*\d+[^)]*)\)", p["text"], re.I) or \
                re.match(r"^\s*(Abstract|Background|Introduction|Methods?|Materials?|"
                         r"Results?|Discussion|Conclusion|Limitations|References|"
                         r"Sec\s*\d+)\b", p["text"], re.I)
            if m:
                p["section"] = m.group(1).strip()
    return paras


# ── material store ───────────────────────────────────────────────────────────

class Store:
    def __init__(self, case, materials):
        self.case = case
        self.sources = []
        self.files = []
        self.documents = []      # parsed text materials
        self.tables = []         # parsed csv/tsv materials
        self.workorder_raw = {}
        self.errors = []
        self.uncertainty = []

    def register(self, materials):
        for i, m in enumerate(materials, 1):
            sid = f"S{i}"
            ext = (m.get("ext") or "").lstrip(".") or "file"
            self.sources.append({"id": sid, "path": m["path"], "name": m["name"],
                                 "document_id": sid, "kind": ext,
                                 "locator": m["name"], "version": "as-provided"})
            self.files.append({"sid": sid, "path": m["path"], "name": m["name"],
                               "ext": ext, "role": None})

    def add_unc(self, item, reason, handling="human_confirm"):
        self.uncertainty.append({"item": item, "reason": reason, "handling": handling})

    def parse_all(self, input_dir):
        if readkit is not None:
            try:
                wo = readkit.load_workorders(input_dir)
                self.workorder_raw = wo.get("raw", {})
            except Exception as e:
                self.errors.append(f"workorders: {e}")
        for f in self.files:
            try:
                self.parse_file(f)
            except Exception as e:
                self.errors.append(f"{f['name']}: {type(e).__name__}: {e}")
                self.add_unc(f["name"], f"extraction failed: {e}; registered but not parsed")

    def parse_file(self, f):
        low = f["name"].lower()
        if low in ("case.json", "task.md") or low.startswith("readme"):
            f["role"] = "task"
            return
        if f["ext"] == "json":
            try:
                data = figkit.load_json(f["path"])
            except Exception as e:
                f["role"] = "unparsed"
                self.add_unc(f["name"], f"JSON unreadable: {e}")
                return
            f["role"] = "workorder"
            self.workorder_raw.setdefault(f["name"], data)
            return
        if f["ext"] in ("csv", "tsv", "tab"):
            try:
                rows = figkit.read_table(f["path"])
            except Exception as e:
                self.add_unc(f["name"], f"table unreadable: {e}")
                return
            f["role"] = "table"
            f["rows"] = rows
            self.tables.append(f)
            return
        text = read_material_text(f["path"])
        f["text"] = text
        f["paragraphs"] = parse_paragraphs(text)
        f["role"] = "document"
        self.documents.append(f)

    def all_paragraphs(self):
        for d in self.documents:
            for p in d.get("paragraphs", []):
                yield d, p

    def ev(self, d, p, quote):
        e = {"source": d["sid"], "source_id": d["sid"], "document_id": d["sid"],
             "paragraph_id": p["id"], "quote": clip(quote, 400)}
        if p.get("page") is not None:
            e["page"] = p["page"]
        if p.get("section"):
            e["section"] = p["section"]
        return e


# ── workorder request collection (ids + actual texts) ───────────────────────

def collect_requests(store):
    """Return {"fields":[{id,text}], "claims":[{id,text}], "questions":[{id,text}]}
    from the ACTUAL workorder JSON files (defensive about schema)."""
    req = {"fields": [], "claims": [], "questions": []}
    seen = {"fields": set(), "claims": set(), "questions": set()}

    def add(bucket, rid, text=None):
        if not rid or rid in seen[bucket]:
            return
        seen[bucket].add(rid)
        req[bucket].append({"id": str(rid), "text": str(text) if text else None})

    def walk(obj, hint=None):
        if isinstance(obj, dict):
            bucket = hint
            for k in obj:
                kl = str(k).lower()
                if "claim" in kl:
                    bucket = "claims"
                elif "question" in kl:
                    bucket = "questions"
                elif "field" in kl or "target" in kl:
                    bucket = "fields"
            rid = obj.get("field_id") or obj.get("target_field_id") or \
                obj.get("claim_id") or obj.get("question_id") or obj.get("id")
            text = obj.get("text") or obj.get("question") or obj.get("claim") or \
                obj.get("description") or obj.get("label") or obj.get("name") or \
                obj.get("prompt")
            if rid and bucket:
                add(bucket, rid, text)
            elif rid and isinstance(text, str) and text:
                # bare {id,text}: route by workorder hint already set
                if hint:
                    add(hint, rid, text)
            for k, v in obj.items():
                kl = str(k).lower()
                nh = hint
                if "claim" in kl:
                    nh = "claims"
                elif "question" in kl:
                    nh = "questions"
                elif "field" in kl or "target" in kl:
                    nh = "fields"
                walk(v, nh)
        elif isinstance(obj, list):
            for it in obj:
                if isinstance(it, str):
                    if hint:
                        add(hint, it, it)
                elif isinstance(it, dict):
                    walk(it, hint)

    for name, data in store.workorder_raw.items():
        if isinstance(data, dict) and data.get("_parse_error"):
            store.add_unc(name, "workorder JSON unreadable; requests unknown")
            continue
        low = name.lower()
        hint = None
        if "claim" in low:
            hint = "claims"
        elif "question" in low:
            hint = "questions"
        elif "field" in low or "target" in low:
            hint = "fields"
        walk(data, hint)
    return req


# ── kind detection ───────────────────────────────────────────────────────────

def detect_kind(args_kind, case, store):
    valid = (readkit.KINDS if readkit else
             {"literature_qa", "figure_parse", "conclusion_extraction",
              "evidence_verification", "multi_doc_compare", "data_cleaning",
              "formula_reasoning", "reading_client", "reproduction",
              "reading_benchmark"})
    if args_kind:
        k = args_kind.strip().replace("-", "_")
        if k in valid:
            return k
    skill = SCRIPT_DIR / "SKILL.md"
    pkg_kind = None
    if skill.exists():
        try:
            head = skill.read_text(encoding="utf-8", errors="replace")[:2000]
            m = re.search(r"^name:\s*([a-z0-9-]+)\s*$", head, re.M)
            if m and m.group(1) in SKILL_KIND:
                pkg_kind = SKILL_KIND[m.group(1)]
        except Exception:
            pass
    names = " ".join(f["name"].lower() for f in store.files)
    blob = ((case.get("task_md") or "") + " " + names + " " +
            json.dumps(case.get("raw") or {}, ensure_ascii=False)).lower()
    best, best_score = None, 0
    for kind, kws in WORKORDER_HINTS:
        score = sum(1 for kw in kws if kw in blob)
        if score > best_score:
            best, best_score = kind, score
    if best and best_score >= 1 and (pkg_kind is None or best_score >= 2):
        return best
    return pkg_kind or best or "literature_qa"


# ── evidence-grounded extraction primitives ─────────────────────────────────

def best_sentence(store, query_text, min_hits=1):
    """Locate the paragraph+sentence with the highest lexical overlap with the
    query. Returns (doc, para, sentence, hits, ratio) or None. Deterministic."""
    qtok = tokens(query_text)
    if not qtok:
        return None
    best = None
    for d, p in store.all_paragraphs():
        for s in sentences(p["text"]):
            st = tokens(s)
            hits = qtok & st
            if len(hits) < min_hits:
                continue
            ratio = len(hits) / len(qtok)
            key = (ratio, len(hits))
            if best is None or key > best[0]:
                best = (key, d, p, s, sorted(hits), ratio)
    if best is None:
        return None
    _, d, p, s, hits, ratio = best
    return d, p, s, hits, ratio


def extract_field(store, fid, ftext, docs=None):
    """One honest item per requested field: label match > numeric match >
    lexical sentence match > insufficient_evidence. `docs` optionally restricts
    the search to a subset of documents (per-document comparison cells)."""
    label = re.sub(r"[_\-]+", " ", str(ftext or fid)).strip()
    item = {"id": fid, "field_id": fid, "value": None, "units": None,
            "kind": "reported", "status": "insufficient_evidence", "evidence": []}
    scoped = [(d, p) for d in (docs if docs is not None else store.documents)
              for p in d.get("paragraphs", [])]

    def paragraphs():
        return iter(scoped)
    # 1) explicit "label: value" / "label = value" in a paragraph
    pat = re.compile(r"(?:^|\n|(?<=[.!?])\s*)(" + re.escape(label) +
                     r")\s*[:：=]\s*([^\n]+)", re.I)
    for d, p in paragraphs():
        m = pat.search(p["text"])
        if m:
            val = m.group(2).strip()
            quote = m.group(0).strip()
            item.update({"value": val, "status": "answered",
                         "evidence": [store.ev(d, p, quote)]})
            num = re.match(r"^([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*(\S.*)?$", val)
            if num:
                item["value"] = float(num.group(1))
                if num.group(2):
                    item["units"] = num.group(2).strip()
            return item
    # 2) sentence containing ALL field tokens AND a number -> numeric value.
    #    Numbers attached to labels (Day3/Sec 2/Table 1) are excluded; for
    #    count-like fields an explicit "n=..." wins; otherwise the LAST standalone
    #    number in the matched sentence is taken (documented heuristic).
    qtok = tokens(label)
    if qtok:
        count_like = bool(re.search(r"\bn\b|sample|count|number|size", str(fid).lower() + " " + label.lower()))
        for d, p in paragraphs():
            for s in sentences(p["text"]):
                st = tokens(s)
                hits = qtok & st
                if len(hits) < len(qtok) or not hits:
                    continue
                nums = [m for m in re.finditer(r"(?<![A-Za-z0-9.])(\d+(?:\.\d+)?)", s)
                        if not re.search(r"(?:Sec|Section|Table|Fig|Figure|Eq|Panel|Day|p\.)\s*$",
                                         s[:m.start()], re.I)]
                nm = None
                if count_like:
                    cm = re.search(r"\bn\s*=\s*(\d+)", s, re.I)
                    if cm:
                        nm = cm
                if nm is None and nums:
                    nm = nums[-1]
                if nm is not None:
                    val = nm.group(1)
                    um = re.search(re.escape(val) + r"\s*([%a-zA-Zμ°/][\w/%.°μ-]*)", s)
                    item.update({"value": float(val),
                                 "units": um.group(1) if um else None,
                                 "status": "answered",
                                 "condition": clip(s, 200),
                                 "human_confirm": True,
                                 "note": "numeric value selected by deterministic heuristic "
                                         "(n= pattern / last standalone number in matched "
                                         "sentence); human_confirm",
                                 "evidence": [store.ev(d, p, s)]})
                    return item
        # 3) lexical sentence match (text-valued field), within the scoped docs
        found = None
        for d, p in paragraphs():
            for s in sentences(p["text"]):
                hits = qtok & tokens(s)
                if len(hits) < max(1, min(2, len(qtok))):
                    continue
                ratio = len(hits) / len(qtok)
                key = (ratio, len(hits))
                if found is None or key > found[0]:
                    found = (key, d, p, s, ratio)
        if found:
            _, d, p, s, ratio = found
            if ratio >= 0.5:
                item.update({"value": clip(s, 400), "status": "answered",
                             "evidence": [store.ev(d, p, s)]})
                return item
    item["note"] = "requested field not located in provided material; needs human_confirm"
    item["human_confirm"] = True
    return item


def answer_question(store, qid, qtext):
    item = {"id": qid, "question_id": qid, "answer": None, "conditions": None,
            "kind": "reported", "status": "insufficient_evidence", "evidence": []}
    if not qtext:
        item["note"] = "question text not present in workorder; cannot answer honestly"
        item["human_confirm"] = True
        return item
    found = best_sentence(store, qtext, min_hits=1)
    if not found:
        item["note"] = "no material sentence overlaps the question; needs human_confirm"
        item["human_confirm"] = True
        return item
    d, p, s, hits, ratio = found
    # gather up to 2 adjacent supporting sentences from the same paragraph
    sents = sentences(p["text"])
    idx = next((i for i, x in enumerate(sents) if x == s), 0)
    answer_parts = [s]
    if idx + 1 < len(sents) and ratio < 0.6:
        nxt = sents[idx + 1]
        if tokens(qtext) & tokens(nxt):
            answer_parts.append(nxt)
    answer = " ".join(answer_parts)
    cond = re.findall(r"\b(?:under|at|with|for|in)\s+[^,.;]{3,60}|"
                      r"\bn\s*=\s*\d+|\bDay\s*\d+|\b\d+\s*(?:days?|weeks?|h|min|°C|C)\b",
                      answer, re.I)
    item.update({"answer": clip(answer, 600),
                 "conditions": "; ".join(dict.fromkeys(cond)) or None,
                 "status": "answered" if ratio >= 0.35 and len(hits) >= 2 else "partial",
                 "evidence": [store.ev(d, p, answer)]})
    if item["status"] == "partial":
        item["human_confirm"] = True
        item["note"] = "weak lexical match; answer is a verbatim candidate passage, human_confirm"
    return item


def verify_claim(store, cid, ctext):
    claim = {"id": cid, "claim": ctext, "verdict": "insufficient_evidence",
             "subclaims": [], "human_confirm": True}
    if not ctext:
        claim["note"] = "claim text not present in workorder; cannot verify honestly"
        return claim
    found = best_sentence(store, ctext, min_hits=2)
    if not found:
        claim["note"] = "no material passage overlaps the claim; needs human_confirm"
        return claim
    d, p, s, hits, ratio = found
    neg_claim = bool(re.search(r"\b(not|no|never|without|fails?|cannot)\b", ctext, re.I))
    neg_sent = bool(re.search(r"\b(not|no|never|without|fails?|cannot)\b", s, re.I))
    if ratio >= 0.5 and neg_claim == neg_sent:
        support = "supports"
    elif ratio >= 0.25:
        support = "partial"
    else:
        support = "insufficient"
    claim["verdict"] = support
    claim["subclaims"] = [{"text": ctext, "support": support,
                           "evidence": [store.ev(d, p, s)] if support != "insufficient" else []}]
    claim["note"] = ("deterministic lexical-overlap heuristic (not expert verification); "
                     "human_confirm")
    return claim


# ── per-kind builders ────────────────────────────────────────────────────────

def build_qa(ir, store, req):
    for f in req["fields"]:
        ir["items"].append(extract_field(store, f["id"], f["text"]))
    for q in req["questions"]:
        ir["items"].append(answer_question(store, q["id"], q["text"]))
    for c in req["claims"]:
        ir["claims"].append(verify_claim(store, c["id"], c["text"]))
    if not req["fields"] and not req["questions"] and not req["claims"]:
        # no workorder: answer the task's own question(s) if any
        task = store.case.get("task_md") or ""
        qs = [ln.strip() for ln in task.splitlines() if "?" in ln]
        for i, q in enumerate(qs[:8], 1):
            ir["items"].append(answer_question(store, f"Q{i}", q))
        if not ir["items"]:
            store.add_unc("requests", "no workorder questions/fields found and no question "
                          "in task.md; nothing requested to extract")


def build_figure(ir, store, req):
    fig_paras = []
    for d, p in store.all_paragraphs():
        if re.search(r"\bfig(?:ure)?s?\.?\s*\d+|\bpanel\s+[A-Z]\b|axis|axes|plot|"
                     r"scale\s*bar|error\s*bar", p["text"], re.I):
            fig_paras.append((d, p))
    figures = []
    for i, (d, p) in enumerate(fig_paras, 1):
        fm = re.search(r"\bfig(?:ure)?s?\.?\s*(\d+)", p["text"], re.I)
        fid = f"FIG{fm.group(1)}" if fm else f"FIG{i}"
        if any(f["id"] == fid for f in figures):
            fid = f"{fid}_{i}"
        panels = re.findall(r"\bpanel\s+([A-Z])\b|\(([A-Z])\)\s", p["text"])
        figures.append({"id": fid, "source": d["sid"], "paragraph_id": p["id"],
                        "caption": clip(p["text"], 400),
                        "panels": sorted({a or b for a, b in panels}),
                        "elements": [], "status": "reported",
                        "evidence": [store.ev(d, p, p["text"])]})
    ir["figures"] = figures
    # requested figure fields (workorder) or default axis/unit/scale checklist
    field_ids = [f["id"] for f in req["fields"]] or \
        ["axis_type", "x_axis_label", "y_axis_label", "x_unit", "y_unit",
         "scale_start", "scale_interval", "data_points", "error_bars",
         "significance_markers", "scale_bar", "subplots"]
    texts = {f["id"]: f["text"] for f in req["fields"]}
    for fid in field_ids:
        label = re.sub(r"[_\-]+", " ", texts.get(fid) or fid)
        item = {"id": fid, "field_id": fid, "value": None, "units": None,
                "kind": "reported", "status": "insufficient_evidence", "evidence": [],
                "human_confirm": True,
                "note": "figure attribute not readable from provided text material; "
                        "no pixel access; needs human_confirm"}
        low = fid.lower()
        for d, p in fig_paras:
            t = p["text"]
            quote = None
            val = None
            if "axis_type" in low or low in ("axis", "scale_type"):
                if re.search(r"\blog(?:arithmic)?\b|semi-log|log-log", t, re.I):
                    val = "log"
                    quote = exact_quote(t, re.search(r"\blog\w*\b", t, re.I).group(0))
                elif re.search(r"\blinear\b", t, re.I):
                    val = "linear"
                    quote = exact_quote(t, "linear")
            elif "unit" in low:
                um = re.search(r"(?:y|x)[\s-]*axis[^(\n]*\(([^)]+)\)|"
                               r"\b(?:in|units?)\s+([%a-zA-Zμ°/][\w/%.°μ-]*)", t)
                if um:
                    val = (um.group(1) or um.group(2)).strip()
                    quote = exact_quote(t, val)
            elif "label" in low:
                lm = re.search(r"((?:y|x)[\s-]*axis\s*(?:label)?\s*[:：=]\s*[^\n,.;]+)", t, re.I)
                if lm:
                    val = lm.group(1).strip()
                    quote = lm.group(1)
            elif "scale" in low or "interval" in low or "start" in low:
                sm = re.search(r"(?:scale|axis)[^.\n]*?(\d+(?:\.\d+)?)\s*(?:to|-|–)\s*"
                               r"(\d+(?:\.\d+)?)", t, re.I)
                if sm:
                    val = {"start": float(sm.group(1)), "end": float(sm.group(2))}
                    quote = exact_quote(t, sm.group(0))
            elif "data" in low or "point" in low or "curve" in low:
                pts = re.findall(r"\(?\s*(\d+(?:\.\d+)?)\s*[,;]\s*(\d+(?:\.\d+)?)\s*\)?", t)
                if pts:
                    val = [{"x": float(a), "y": float(b)} for a, b in pts]
                    quote = clip(t, 400)
            elif re.search(r"error|significan|scale\s*bar|subplot|panel", low):
                kw = {"error": "error bar", "significan": "significan",
                      "scale": "scale bar", "subplot": "panel", "panel": "panel"}
                for k, needle in kw.items():
                    if k in low:
                        m = re.search(needle, t, re.I)
                        if m:
                            val = clip(exact_quote(t, m.group(0)) or "", 300)
                            quote = val
                        break
            if val is not None and quote:
                item.update({"value": val, "status": "answered",
                             "evidence": [store.ev(d, p, quote)]})
                break
        if item["status"] == "answered":
            item["note"] = "auto keyword/regex extraction from figure text; human_confirm"
        ir["items"].append(item)
    # tabular data materials -> data_points item if present
    for t in store.tables:
        rows = t.get("rows") or []
        if rows:
            ir["items"].append({"id": f"data_{t['sid']}", "field_id": f"data_{t['name']}",
                                "value": rows, "kind": "reported", "status": "answered",
                                "evidence": [{"source": t["sid"], "source_id": t["sid"],
                                              "document_id": t["sid"],
                                              "locator": t["name"],
                                              "quote": clip(json.dumps(rows[0], ensure_ascii=False), 300)}],
                                "note": "verbatim rows from provided data table"})
    if not figures:
        store.add_unc("figures", "no figure description located in provided text material; "
                      "pixel-level parsing impossible (text-only track)")


def build_compare(ir, store, req):
    """Common-field matrix, ONE ROW PER DOCUMENT; every cell is extracted from
    THAT document only (scoped extract_field) so source_document_id, paragraph_id
    and quote always agree. Missing cells stay honest insufficient_evidence."""
    fields = [f["id"] for f in req["fields"]] or ["main_result", "n", "condition"]
    texts = {f["id"]: f["text"] for f in req["fields"]}
    rows = []
    for d in store.documents:
        cells = []
        for fid in fields:
            it = extract_field(store, fid, texts.get(fid), docs=[d])
            ev = (it.get("evidence") or [{}])[0]
            cells.append({"field": fid, "value": it.get("value"),
                          "units": it.get("units"),
                          "status": it.get("status"),
                          "source_document_id": d["sid"],
                          "paragraph_id": ev.get("paragraph_id"),
                          "quote": ev.get("quote"),
                          "metric": texts.get(fid) or fid,
                          "condition": it.get("condition")})
        rows.append({"document_id": d["sid"], "task": store.case.get("case_id"),
                     "metric": ", ".join(fields), "condition": d["name"],
                     "cells": cells})
    # conflict explanation: attribute differing values to document/condition,
    # never silently merge; only fields with >=2 reported differing values.
    conflicts = {}
    for fid in fields:
        vals = [(r["document_id"], c) for r in rows for c in r["cells"]
                if c["field"] == fid and c.get("value") is not None]
        if len(vals) >= 2 and len({str(c["value"]) for _, c in vals}) > 1:
            conflicts[fid] = ("values differ across documents (" +
                              ", ".join(f"{doc}={c['value']}" for doc, c in vals) +
                              "); attributed to sample/method/condition/metric "
                              "differences between the source documents; see "
                              "per-cell source_document_id + paragraph_id + quote")
    ir["matrix"] = {"fields": fields, "rows": rows, "conflict_explanation": conflicts}
    if conflicts:
        store.add_unc("comparison conflicts",
                      "differing values across documents for: " + ", ".join(conflicts) +
                      "; comparability limited to same task/metric/condition")
    if len(store.documents) < 2:
        store.add_unc("comparison", "fewer than 2 document materials provided; "
                      "cross-document comparison not possible")


def build_cleaning(ir, store, req):
    records = []
    for t in store.tables:
        for i, r in enumerate(t.get("rows") or [], 1):
            for k, v in r.items():
                if v in (None, ""):
                    continue
                records.append({"id": f"{t['sid']}_r{i}_{k}", "field": k,
                                "original": v, "value": v, "unit": None,
                                "source": t["sid"],
                                "condition": f"row {i}"})
    # organizer cleaning-workorder may declare mapping/allowed values/target unit
    mapping, allowed, target_unit, dedup = {}, {}, None, ["source", "field", "condition"]
    for name, data in store.workorder_raw.items():
        if not isinstance(data, dict):
            continue
        if isinstance(data.get("field_mapping"), dict):
            mapping.update(data["field_mapping"])
        if isinstance(data.get("allowed_values"), dict):
            allowed.update(data["allowed_values"])
        if data.get("target_unit"):
            target_unit = data["target_unit"]
        if isinstance(data.get("dedup_keys"), list) and data["dedup_keys"]:
            dedup = data["dedup_keys"]
    ir["cleaning"] = {"field_mapping": mapping, "allowed_values": allowed,
                      "target_unit": target_unit,
                      "dedup_keys": dedup,
                      "records": records}
    if not records:
        store.add_unc("cleaning", "no tabular data material found; nothing to clean")


def build_formulas(ir, store, req):
    formulas = []
    for d, p in store.all_paragraphs():
        for m in re.finditer(r"\$\$?(.+?)\$\$?|\\\[(.+?)\\\]|"
                             r"(?:^|\n)\s*(?:Eq(?:uation)?\.?\s*\d*\s*[:：]?)\s*"
                             r"([^\n]*=[^\n]+)", p["text"]):
            expr = next(g for g in m.groups() if g)
            symbols = sorted(set(re.findall(r"\b([a-zA-Z](?:_[a-zA-Z0-9]+)?)\b", expr)))
            formulas.append({"id": f"F{len(formulas) + 1}", "latex": expr.strip(),
                             "source": d["sid"],
                             "variables": [{"symbol": s, "definition": None}
                                           for s in symbols
                                           if s.lower() not in ("eq", "equation")],
                             "evidence": [store.ev(d, p, m.group(0))]})
    ir["formulas"] = formulas
    if not formulas:
        store.add_unc("formulas", "no formula located in provided material")


def build_reproduction(ir, store, req):
    """Reproduction workflow IR from ACTUAL material (text-only, honest):
    locate code/data/params/deps/license mentions with locators (missing ones
    registered not_reported); record paper-side params/env/results with evidence.
    The autopilot NEVER executes code: repro values stay null, within-tolerance
    is not computed, and the run is flagged human_confirm (partial)."""
    asset_kw = {"code": r"\b(?:code|repository|repo|github|gitlab|source\s+code)\b",
                "data": r"\b(?:data(?:set)?s?|csv|database|archive)\b",
                "params": r"\b(?:param(?:eter)?s?|hyperparam(?:eter)?s?|settings?|config(?:uration)?)\b",
                "deps": r"\b(?:dependenc(?:y|ies)|requirements?|package|library|version|python|pytorch|tensorflow)\b",
                "license": r"\blicen[cs]e\b"}
    assets = []
    for name, pat in asset_kw.items():
        found = None
        for d, p in store.all_paragraphs():
            m = re.search(pat, p["text"], re.I)
            if m:
                found = {"asset": name, "status": "reported",
                         "locator": exact_quote(p["text"], m.group(0)) or clip(p["text"], 200),
                         "version": None,
                         "evidence": [store.ev(d, p, p["text"])]}
                vm = re.search(r"\bv(?:ersion)?\.?\s*(\d+(?:\.\d+)+)", p["text"], re.I)
                if vm:
                    found["version"] = vm.group(1)
                break
        if found is None:
            found = {"asset": name, "status": "not_reported", "version": None,
                     "human_confirm": True,
                     "note": f"{name} not located in provided material; registered missing"}
        assets.append(found)
    # params: explicit "name = value" / "name: value" patterns in the material
    params = []
    seen = set()
    for d, p in store.all_paragraphs():
        for m in re.finditer(r"(?:^|\n|(?<=[.!?])\s*)([A-Za-z][\w \-]{1,40}?)\s*[:：=]\s*"
                             r"([-+]?\d+(?:\.\d+)?(?:\s*[a-zA-Zμ°%][\w/%.°μ-]*)?)\s*(?=[,.;\n]|$)",
                             p["text"]):
            name = m.group(1).strip()
            if name.lower() in seen or len(name) < 2:
                continue
            seen.add(name.lower())
            params.append({"name": name, "paper_value": m.group(2).strip(),
                           "repo_value": None, "used": None,
                           "source": d["sid"],
                           "evidence": [store.ev(d, p, m.group(0))]})
    # env mentions
    env = []
    for d, p in store.all_paragraphs():
        if re.search(r"\b(?:environment|runtime|OS|ubuntu|windows|cuda|gpu|cpu|"
                     r"python\s*\d|pytorch|tensorflow)\b", p["text"], re.I):
            env.append({"source": d["sid"], "paragraph_id": p["id"],
                        "description": clip(p["text"], 300),
                        "evidence": [store.ev(d, p, p["text"])]})
    # results: paper-side numeric findings; repro side never fabricated
    results = []
    metric_reqs = req["fields"] or []
    if metric_reqs:
        for f in metric_reqs:
            it = extract_field(store, f["id"], f["text"])
            ev = (it.get("evidence") or [{}])[0]
            results.append({"metric": f["id"], "paper": it.get("value"),
                            "repro": None, "tolerance": None, "within": None,
                            "units": it.get("units"),
                            "paragraph_id": ev.get("paragraph_id"),
                            "evidence": it.get("evidence", []),
                            "status": it.get("status"),
                            "note": "paper value extracted from material; reproduction NOT "
                                    "executed by autopilot (text-only); tolerance not "
                                    "declared in material; human_confirm"})
    else:
        for d, p in store.all_paragraphs():
            if not re.search(r"\bResults?\b", p.get("section") or "", re.I) and \
                    not re.match(r"^\s*Results?\b", p["text"], re.I):
                continue
            for s in sentences(p["text"]):
                nm = re.search(r"(?<![A-Za-z0-9.])(\d+(?:\.\d+)?)", s)
                if nm and len(tokens(s)) >= 3:
                    results.append({"metric": clip(s, 80), "paper": float(nm.group(1)),
                                    "repro": None, "tolerance": None, "within": None,
                                    "evidence": [store.ev(d, p, s)],
                                    "note": "first number in verbatim results sentence "
                                            "(heuristic); repro not executed; human_confirm"})
    ir["reproduction"] = {"assets": assets, "params": params[:20], "env": env[:10],
                          "results": results[:12], "attribution": [],
                          "steps": [{"step": "locate assets/params/env in material",
                                     "status": "done"},
                                    {"step": "restore env + run with paper params",
                                     "status": "not_executed",
                                     "reason": "text-only autopilot; no code execution"},
                                    {"step": "compare within declared tolerance + attribute",
                                     "status": "pending_human"}]}
    for f in req["fields"]:
        ir["items"].append(extract_field(store, f["id"], f["text"]))
    store.add_unc("reproduction", "reproduction not executed (text-only autopilot); "
                  "repro values null, tolerance/within-tolerance and difference "
                  "attribution pending a human run; never fabricated")
    if not params:
        store.add_unc("reproduction params", "no explicit parameter assignments located "
                      "in provided material")


def build_benchmark(ir, store, req):
    """Reading-benchmark task cards derived from the ACTUAL material: every
    instruction/reference answer/required point is grounded in verbatim material
    sentences (never invented). Scoring anchors are observable substring checks
    (benchkit eval.py). Repeat-run stability is NOT measured here -> flagged."""
    tasks = []
    # organizer-provided task cards win if present and decidable
    for name, data in store.workorder_raw.items():
        cand = data.get("tasks") if isinstance(data, dict) else None
        if isinstance(cand, list):
            for t in cand:
                if isinstance(t, dict) and t.get("instruction") and t.get("required_points"):
                    t.setdefault("id", f"T{len(tasks) + 1}")
                    t.setdefault("input_material", ", ".join(
                        f["name"] for f in store.files if f["role"] == "document") or name)
                    tasks.append(t)
    if not tasks:
        body = [(d, p) for d, p in store.all_paragraphs()
                if not re.match(r"^\s*(?:SYNTHETIC|EXAMPLE SOURCE)", p["text"], re.I)]
        candidates = []
        for d, p in body:
            for s in sentences(p["text"]):
                if "?" in s:
                    candidates.append(("question", d, p, s))
        for d, p in body:
            sec = (p.get("section") or "") + " " + p["text"][:40]
            if re.search(r"\b(?:Results?|Conclusion)\b", sec, re.I):
                for s in sentences(p["text"]):
                    if re.search(r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?", s) and len(tokens(s)) >= 4:
                        candidates.append(("finding", d, p, s))
        seen_ans = set()
        for ctype, d, p, s in candidates:
            if ctype == "question":
                found = best_sentence(store, s, min_hits=2)
                if not found:
                    continue
                d2, p2, ans, hits, ratio = found
                if "?" in ans:
                    continue
                instruction = s
            else:
                d2, p2, ans = d, p, s
                topic = ", ".join(sorted(tokens(s))[:4])
                instruction = (f"According to {d['name']} ({p['id']}), what does the "
                               f"material report regarding {topic}?")
            if ans in seen_ans:
                continue
            seen_ans.add(ans)
            nums = re.findall(r"\d+(?:\.\d+)?%?", ans)
            words = [t for t in sorted(tokens(ans)) if len(t) >= 5][:3]
            points = list(dict.fromkeys(nums + words))[:5]
            if not points:
                continue
            variants = [x for x in sentences(p2["text"])
                        if x != ans and len(tokens(x) & tokens(ans)) >= 3][:2]
            tasks.append({"id": f"T{len(tasks) + 1}",
                          "instruction": clip(instruction, 400),
                          "input_material": f"{d2['name']} ({p2['id']})",
                          "required_points": points,
                          "forbidden": [],
                          "anchors": [{"criterion": "each required point present verbatim",
                                       "observable": True, "check": "substring"},
                                      {"criterion": "no forbidden content",
                                       "observable": True, "check": "substring"}],
                          "acceptable_variants": variants,
                          "reference_answer": clip(ans, 500),
                          "reference_locator": {"source": d2["sid"],
                                                "paragraph_id": p2["id"],
                                                "quote": clip(ans, 400)},
                          "difficulty": "derived", "license": "as-provided material"})
            if len(tasks) >= 8:
                break
    ir["tasks"] = tasks
    ir["benchmark_meta"] = {"runner": {"tools": "stdlib eval.py (benchkit)",
                                       "budget": "fixed per task", "output_format": "markdown"},
                            "scoring": "0/1/2 rule anchors + human review",
                            "stability": "repeat-run stability NOT measured by autopilot"}
    store.add_unc("benchmark stability", "repeat-run stability not measured; task cards "
                  "derived by deterministic heuristics from verbatim material; human_confirm")
    if not tasks:
        store.add_unc("benchmark tasks", "no decidable task could be derived from the "
                      "provided material (no questions/numeric findings)")


BUILDERS = {
    "literature_qa": build_qa,
    "reading_client": build_qa,
    "conclusion_extraction": build_qa,
    "evidence_verification": build_qa,
    "figure_parse": build_figure,
    "multi_doc_compare": build_compare,
    "data_cleaning": build_cleaning,
    "formula_reasoning": build_formulas,
    "reproduction": build_reproduction,
    "reading_benchmark": build_benchmark,
}


# ── status / fallback helpers ────────────────────────────────────────────────

GAP_STATUSES = {"insufficient_evidence", "input_error", "not_reported",
                "extraction_failed", "source_conflict", "partial"}


def has_gaps(ir):
    for it in ir.get("items", []):
        if it.get("status") in GAP_STATUSES or it.get("human_confirm"):
            return True
    for c in ir.get("claims", []):
        if c.get("verdict") in ("insufficient_evidence", "insufficient", "partial"):
            return True
    if ir.get("unanswered_parts"):
        return True
    for u in ir.get("uncertainty", []):
        if u.get("handling") == "human_confirm":
            return True
    return False


def emergency_result(case, out_dir, error, sources=None, kind=None):
    """Last-resort honest result.json using ONLY json/os (figkit may be unavailable)."""
    contract = (case or {}).get("output_contract") or {}
    result = {}
    if isinstance(contract, dict):
        for key, spec in contract.items():
            kl = key.lower()
            if "json" in kl or "result" in kl or "meta" in kl:
                result[key] = "result.json"
            elif isinstance(spec, dict) and "default" in spec:
                result[key] = spec["default"]
            else:
                result[key] = {"_contract_spec": spec, "_status": "see notes/error"}
    elif isinstance(contract, list):
        result["output_contract"] = contract
    result.update({"case_id": (case or {}).get("case_id", "unknown-case"),
                   "status": "failed", "kind": kind,
                   "sources": sources or [],
                   "uncertainty": [{"item": "pipeline", "reason": str(error),
                                    "handling": "human_confirm"}],
                   "notes": AUTO_NOTE, "error": str(error)})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "result.json", "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return result


def fallback_result(case, ir, out_dir, error, status="failed"):
    """Honest result via figkit when assemble_read.py could not produce one."""
    ir.setdefault("uncertainty", []).append(
        {"item": "pipeline", "reason": f"{type(error).__name__}: {error}",
         "handling": "human_confirm"})
    validation = None
    if readkit is not None:
        try:
            validation = readkit.validate_reading(ir)
        except Exception:
            validation = None
    result = figkit.build_result(case, ir, [], status, validation, None,
                                 AUTO_NOTE + f" FATAL: {error}")
    result["error"] = f"{type(error).__name__}: {error}"
    figkit.write_result(out_dir, result)
    return result


# ── main pipeline ────────────────────────────────────────────────────────────

def run(args):
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(args.work)
    work_dir.mkdir(parents=True, exist_ok=True)

    case = figkit.load_case(args.input)
    materials = figkit.list_materials(args.input)
    store = Store(case, materials)
    store.register(materials)
    store.parse_all(args.input)
    kind = detect_kind(args.kind, case, store)
    req = collect_requests(store)

    ir = {"ir_version": "1.0", "case_id": case.get("case_id"), "kind": kind,
          "sources": store.sources, "items": [], "claims": [],
          "coverage": {"read": [], "unread": []},
          "unanswered_parts": [], "uncertainty": [],
          "provenance": {"pipeline": "material -> auto_extract -> reading IR -> "
                                     "assemble_read (validate+build) -> result",
                         "changes": [{"step": "auto_extract",
                                      "detail": f"deterministic extraction from "
                                                f"{len(materials)} material files"}]}}
    BUILDERS.get(kind, build_qa)(ir, store, req)

    # coverage: every parsed paragraph is read; unparsed files are honest unread
    for d in store.documents:
        ir["coverage"]["read"].extend(f"{d['sid']}:{p['id']}"
                                      for p in d.get("paragraphs", []))
    for f in store.files:
        if f["role"] in (None, "unparsed"):
            ir["coverage"]["unread"].append({"source": f["sid"], "name": f["name"],
                                             "reason": "not parsed (unsupported/unreadable)"})
    for e in store.errors:
        ir["uncertainty"].append({"item": "extraction", "reason": e,
                                  "handling": "human_confirm"})
    ir["uncertainty"].extend(store.uncertainty)
    if not materials:
        ir["uncertainty"].append({"item": "materials",
                                  "reason": "input directory empty or unreadable; nothing to extract",
                                  "handling": "human_confirm"})
    if kind in ("literature_qa", "reading_client", "conclusion_extraction",
                "evidence_verification", "figure_parse", "multi_doc_compare",
                "reproduction", "reading_benchmark"):
        ir["uncertainty"].append({"item": "judgment fields",
                                  "reason": "answer/claim/figure/cell/task selection uses "
                                            "deterministic lexical heuristics over verbatim "
                                            "quotes, not expert judgment; human_confirm",
                                  "handling": "human_confirm"})
    # de-duplicate uncertainty
    seen, uniq = set(), []
    for u in ir["uncertainty"]:
        key = (u.get("item"), u.get("reason"))
        if key not in seen:
            seen.add(key)
            uniq.append(u)
    ir["uncertainty"] = uniq

    work_ir = work_dir / "reading_ir.json"
    figkit.write_json(work_ir, ir)

    # run the PACKAGE'S OWN assemble_read.py (same validate+build+result path)
    cmd = [sys.executable, str(SCRIPT_DIR / "assemble_read.py"),
           "--ir", str(work_ir), "--input", str(args.input), "--out", str(out_dir)]
    if has_gaps(ir):
        cmd += ["--status", "partial"]
    # AUTOPILOT_DELEGATED guards the hardened assemble against re-delegation loops
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", AUTOPILOT_DELEGATED="1")
    proc = subprocess.run(cmd, cwd=str(SCRIPT_DIR), env=env, capture_output=True,
                          text=True, timeout=300)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)
    if not (out_dir / "result.json").exists():
        raise RuntimeError(f"assemble_read.py exited {proc.returncode} without result.json: "
                           f"{(proc.stderr or proc.stdout or '')[-500:]}")
    result = figkit.load_json(out_dir / "result.json")
    print(json.dumps({"autopilot": "auto_read", "kind": kind,
                      "status": result.get("status"),
                      "case_id": result.get("case_id"),
                      "n_items": len(ir.get("items", [])),
                      "n_claims": len(ir.get("claims", [])),
                      "n_materials": len(materials),
                      "work_ir": str(work_ir)}, ensure_ascii=False))
    return 0 if result.get("status") in ("success", "partial") else 1


def main():
    ap = argparse.ArgumentParser(description="reading track autopilot (carryover architecture)")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--kind", default=None)
    args = ap.parse_args()

    case, sources, kind = {}, [], None
    try:
        if figkit is None or readkit is None:
            raise RuntimeError("cannot import sibling figkit.py / readkit.py")
        return run(args)
    except Exception as e:
        traceback.print_exc()
        # honest fallback: NEVER exit without result.json
        try:
            case = figkit.load_case(args.input) if figkit else {}
            kind = args.kind or "literature_qa"
            try:
                mats = figkit.list_materials(args.input) if figkit else []
                sources = [{"id": f"S{i}", "path": m["path"], "name": m["name"],
                            "document_id": f"S{i}", "kind": (m.get("ext") or "").lstrip(".")}
                           for i, m in enumerate(mats, 1)]
            except Exception:
                sources = []
            ir = {"ir_version": "1.0", "case_id": case.get("case_id"), "kind": kind,
                  "sources": sources, "items": [], "claims": [],
                  "uncertainty": [{"item": "pipeline",
                                   "reason": f"{type(e).__name__}: {e}",
                                   "handling": "human_confirm"}]}
            if figkit is not None:
                fallback_result(case, ir, args.out, e)
            else:
                emergency_result(case, args.out, e, sources=sources, kind=kind)
        except Exception as e2:
            emergency_result(case, args.out, f"{e}; fallback also failed: {e2}",
                             sources=sources, kind=kind)
        print(json.dumps({"status": "failed", "error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())