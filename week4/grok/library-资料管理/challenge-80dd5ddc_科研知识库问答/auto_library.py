"""auto_library.py — deterministic "autopilot" entry point for the week4 LIBRARY track.

Reads the ACTUAL organizer-provided local materials under --input, auto-extracts
a complete IR (sources / documents / metadata / aliases / versions / operations /
taxonomy / annotations / searches / questions ...), runs the EXISTING
library_engine (validate_ir + build) and writes an honest result.json preserving
every output_contract key + case_id. Stdlib only; additive — does not modify the
engine.

Usage:
  PYTHONDONTWRITEBYTECODE=1 python auto_library.py --input /input --out /app/output \
      [--work /app/work] [--kind KIND]

Design rules:
  * Never fabricate: every title/metadata value/quote/version note comes from a
    real input file; evidence locators point at registered sources.
  * Judgment-heavy fields (metadata-row -> file mapping, inferred year/type,
    taxonomy design, annotation selection) get deterministic evidence-grounded
    heuristic defaults and are flagged human_confirm in uncertainty[]
    (=> honest status "partial"). Missing fields stay not_reported, never invented.
  * Defensive extraction: a bad/missing file becomes an honest gap, never a crash.
  * The WHOLE pipeline is wrapped: on ANY exception an honest result.json is still
    written (status partial/failed) with contract keys + case_id + sources + error.
  * After this baseline runs, the agent may refine /app/work/library_ir.json within
    budget and re-run assemble.py to improve judgment fields.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
import zipfile
import zlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    import w4kit as kit
    import library_engine as engine
except Exception:  # catastrophic import failure -> emergency writer below
    kit = None
    engine = None

AUTO_NOTE = ("auto_library autopilot: deterministic extraction from ACTUAL local "
             "library materials + existing library_engine computation (index, "
             "content-hash dedup, metadata coverage, classification, extractive "
             "QA, locator-bound annotations). No fabricated metadata/quotes; "
             "judgment fields use documented evidence-grounded heuristics flagged "
             "human_confirm; refine work/library_ir.json and re-run assemble.py "
             "to improve.")

META_FIELDS = ["title", "authors", "year", "type", "project", "doi"]

# conservative heading/filename keyword -> document type inference (inferred only)
TYPE_HINTS = [
    ("protocol", ["protocol", "procedure", "sop", "方案", "规程"]),
    ("thesis", ["thesis", "dissertation", "学位论文", "论文"]),
    ("preprint", ["preprint", "预印本"]),
    ("report", ["report", "annual", "报告", "年报"]),
    ("dataset", ["dataset", "data", "数据"]),
    ("notes", ["notes", "meeting", "minutes", "纪要", "笔记", "记录"]),
    ("record", ["record", "calibration", "log", "记录", "校准"]),
]

TYPE_SYNONYMS = {
    "journal_article": ["article", "paper", "journal", "期刊论文"],
    "protocol": ["protocol", "procedure", "recipe", "方案"],
    "dataset": ["dataset", "data", "csv", "数据"],
    "thesis": ["thesis", "dissertation", "学位论文"],
    "report": ["report", "annual", "报告"],
    "notes": ["notes", "meeting", "minutes", "纪要"],
    "record": ["record", "calibration", "log", "记录"],
    "preprint": ["preprint", "预印本"],
    "duplicate_copy": ["duplicate", "copy", "backup", "副本"],
}

RESULT_HINTS = re.compile(
    r"\d+(?:\.\d+)?\s*(?:mm|nm|cm|ml|mg|kg|um|µm|nm|k\b|c\b|l\b|u/mg|percent|%|"
    r"mol|nmol|µl|ul)|optimal|result|conclusion|we found|showed|shows|increased|"
    r"raised|关键|结果|表明|最优|提高", re.I)

KIND_KEYWORDS = [
    ("library_classify", ["classif", "taxonomy", "categor", "分类", "归类", "标签体系"]),
    ("library_annotate", ["annotat", "knowledge card", "批注", "标注", "知识卡片"]),
    ("library_search", ["search", "find documents", "检索", "查找", "lookup"]),
    ("library_qa", ["question", "answer", "qa", "问答", "回答"]),
    ("library_manage", ["manage", "dedup", "inventory", "organize", "整理", "去重",
                        "资料库", "归档", "版本"]),
]


# ── small helpers ────────────────────────────────────────────────────────────

def clip(s, n=400):
    s = str(s)
    return s if len(s) <= n else s[:n] + "..."


def norm_title(t):
    if kit:
        try:
            return kit.normalize_title(t)
        except Exception:
            pass
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", str(t or "").lower()).strip()


def rel_path(path, input_dir):
    try:
        return Path(os.path.relpath(str(path), str(input_dir))).as_posix()
    except Exception:
        return Path(path).as_posix()


def pdf_text(data: bytes) -> str:
    """Best-effort stdlib PDF text salvage (inflate FlateDecode streams)."""
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


def docx_text(data: bytes) -> str:
    """Best-effort stdlib DOCX salvage: word/document.xml paragraph text."""
    try:
        import io
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        xml = re.sub(r"</w:p>", "\n\n", xml)
        txt = re.sub(r"<[^>]+>", "", xml)
        return txt.strip()
    except Exception:
        return ""


def read_material_text(path):
    p = Path(path)
    data = p.read_bytes()
    low = str(path).lower()
    if low.endswith(".pdf") or data[:5] == b"%PDF-":
        return pdf_text(data)
    if low.endswith(".docx") or data[:2] == b"PK":
        t = docx_text(data)
        if t:
            return t
    return data.decode("utf-8", errors="replace")


def paragraphs_of(text):
    """Paragraph ids/pages EXACTLY as library_engine._paragraphs computes them."""
    if engine:
        return engine._paragraphs(text)
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


def sentences_of(text):
    if engine:
        return engine._sentences(text)
    return [p.strip() for p in re.split(r"(?<=[.!?。！？；;])\s*", text or "") if p.strip()]


def first_heading(text, name):
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s or re.match(r"^page\s+\d+\s*$", s, re.I):
            continue
        return re.sub(r"^#{1,6}\s*", "", s).strip()
    return Path(str(name)).stem.replace("_", " ").strip() or None


def sentence_with(par_text, needle):
    """Exact sentence substring of par_text containing needle (or first sentence)."""
    for s in sentences_of(par_text):
        if needle and needle.lower() in s.lower():
            return s
    ss = sentences_of(par_text)
    return ss[0] if ss else par_text.strip()


def find_quote_paragraph(paras, pattern):
    """First paragraph matching regex -> (paragraph, exact sentence quote, hit)."""
    for p in paras:
        m = pattern.search(p["text"])
        if m:
            return p, sentence_with(p["text"], m.group(0)), m.group(0)
    return None, None, None


# ── material store ───────────────────────────────────────────────────────────

class Store:
    def __init__(self, case, materials, input_dir):
        self.case = case
        self.input_dir = Path(input_dir)
        self.sources = []
        self.files = []
        self.by_name = {}
        self.meta_rows = []        # {row, raw, sid}
        self.meta_sid = None
        self.aliases = []          # {alias, document, sid, raw}
        self.alias_sid = None
        self.version_lines = []    # {text, sid}
        self.version_sid = None
        self.taxonomy = None
        self.taxonomy_sid = None
        self.uncertainty = []
        self.errors = []

    def add_unc(self, item, reason, handling="human_confirm"):
        self.uncertainty.append({"item": item, "reason": reason, "handling": handling})

    def register_sources(self, materials):
        for i, m in enumerate(materials, 1):
            sid = f"S{i:02d}"
            ext = (m.get("ext") or "").lstrip(".") or "file"
            rel = rel_path(m["path"], self.input_dir)
            self.sources.append({"id": sid, "path": rel, "name": m["name"],
                                 "type": ext, "role": "document"})
            self.files.append({"sid": sid, "path": m["path"], "rel": rel,
                               "name": m["name"], "ext": ext, "role": None})
            self.by_name[m["name"].lower()] = self.files[-1]

    def file_of(self, name):
        return self.by_name.get(str(name).lower())

    def task_sid(self):
        f = self.file_of("task.md")
        if f:
            return f["sid"]
        f = self.file_of("case.json")
        return f["sid"] if f else (self.sources[0]["id"] if self.sources else "S01")

    def parse_all(self):
        for f in self.files:
            try:
                self.parse_file(f)
            except Exception as e:
                self.errors.append(f"{f['name']}: {type(e).__name__}: {e}")
                self.add_unc(f["name"], f"extraction failed: {e}; file registered but not parsed")
        for s in self.sources:
            f = next((x for x in self.files if x["sid"] == s["id"]), None)
            if f and f.get("role"):
                s["role"] = f["role"]

    def parse_file(self, f):
        name, ext, sid = f["name"], f["ext"], f["sid"]
        low = name.lower()
        if low == "case.json":
            f["role"] = "case"
            return
        if low == "task.md" or low.startswith("readme"):
            f["role"] = "workorder" if low == "task.md" else "readme"
            try:
                f["text"] = read_material_text(f["path"])
            except Exception:
                f["text"] = ""
            return
        if ext == "json":
            try:
                data = kit.load_json(f["path"])
            except Exception as e:
                self.add_unc(name, f"JSON unreadable: {e}; registered as source only")
                f["role"] = "unparsed"
                return
            if isinstance(data, dict) and isinstance(data.get("aliases"), list):
                f["role"] = "alias_table"
                self.alias_sid = sid
                for a in data["aliases"]:
                    if isinstance(a, dict) and a.get("alias"):
                        self.aliases.append({"alias": a["alias"],
                                             "document": a.get("document") or a.get("document_id"),
                                             "sid": sid,
                                             "raw": json.dumps(a, ensure_ascii=False)})
                return
            if isinstance(data, list) and data and all(
                    isinstance(a, dict) and a.get("alias") for a in data):
                f["role"] = "alias_table"
                self.alias_sid = sid
                for a in data:
                    self.aliases.append({"alias": a["alias"],
                                         "document": a.get("document") or a.get("document_id"),
                                         "sid": sid,
                                         "raw": json.dumps(a, ensure_ascii=False)})
                return
            if isinstance(data, dict) and isinstance(data.get("categories"), list):
                f["role"] = "taxonomy"
                self.taxonomy, self.taxonomy_sid = data, sid
                return
            # otherwise fall through: treat as a document file
        if ext in ("csv", "tsv", "tab"):
            try:
                rows = kit.read_table(f["path"])
            except Exception as e:
                self.add_unc(name, f"table unreadable: {e}")
                f["role"] = "unparsed"
                return
            cols = {str(k).lower() for k in (rows[0] if rows else {})}
            if rows and "title" in cols and ("document_id" in cols or "id" in cols):
                f["role"] = "metadata_table"
                self.meta_sid = sid
                raw_lines = {}
                try:
                    for ln in read_material_text(f["path"]).splitlines()[1:]:
                        first = ln.split(",")[0].split("\t")[0].strip().strip('"')
                        if first:
                            raw_lines.setdefault(first, ln.strip())
                except Exception:
                    pass
                for r in rows:
                    rl = {str(k).lower(): v for k, v in r.items()}
                    rid = rl.get("document_id") or rl.get("id")
                    self.meta_rows.append({"row": rl, "id": str(rid) if rid else None,
                                           "raw": raw_lines.get(str(rid)) or
                                           ",".join(str(v) for v in r.values()),
                                           "sid": sid})
                return
            # data table (e.g. measurements) -> document, fall through
        if ext in ("md", "txt", "text") and "version" in low:
            f["role"] = "version_notes"
            self.version_sid = sid
            try:
                text = read_material_text(f["path"])
            except Exception as e:
                self.add_unc(name, f"version notes unreadable: {e}")
                return
            for ln in text.splitlines():
                s = ln.strip()
                if s and not re.match(r"^page\s+\d+\s*$", s, re.I):
                    self.version_lines.append({"text": s, "sid": sid})
            return
        # document file: read defensively
        try:
            text = read_material_text(f["path"])
        except Exception as e:
            self.add_unc(name, f"cannot read bytes: {e}")
            f["role"] = "unreadable"
            return
        f["role"] = "document"
        f["text"] = text
        f["paragraphs"] = paragraphs_of(text)
        f["title"] = first_heading(text, name)
        try:
            f["sha256"] = kit.sha256_file(f["path"])
        except Exception:
            f["sha256"] = None


# ── kind detection ───────────────────────────────────────────────────────────

def norm_kind(k):
    k = str(k or "").strip().lower().replace("-", "_").replace(" ", "_")
    if k and not k.startswith("library_"):
        k = "library_" + k
    return k


def detect_kind(args_kind, case, store):
    kinds = engine.KINDS if engine else {"library_manage", "library_search",
                                         "library_classify", "library_qa",
                                         "library_annotate"}
    if args_kind:
        k = norm_kind(args_kind)
        if k in kinds:
            return k
    skill = SCRIPT_DIR / "SKILL.md"
    if skill.exists():
        try:
            head = skill.read_text(encoding="utf-8", errors="replace")[:2000]
            m = re.search(r"^name:\s*library-([a-z0-9-]+)\s*$", head, re.M)
            if m:
                k = norm_kind(m.group(1))
                if k in kinds:
                    return k
        except Exception:
            pass
    task = case.get("task_md") or ""
    m = re.search(r"workorder kind\s*[:：]\s*([A-Za-z_]+)", task, re.I) or \
        re.search(r"\bkind\s*[:：]\s*([A-Za-z_]+)", task, re.I)
    if m:
        k = norm_kind(m.group(1))
        if k in kinds:
            return k
    raw_kind = (case.get("raw") or {}).get("kind")
    if raw_kind:
        k = norm_kind(raw_kind)
        if k in kinds:
            return k
    blob = (task + " " + json.dumps(case.get("raw") or {}, ensure_ascii=False) +
            " " + " ".join(f["name"] for f in store.files)).lower()
    best, best_score = None, 0
    for kind, kws in KIND_KEYWORDS:
        score = sum(1 for kw in kws if kw in blob)
        if score > best_score:
            best, best_score = kind, score
    return best or "library_manage"


# ── shared document builder ──────────────────────────────────────────────────

def match_metadata_rows(store, doc_files):
    """Map metadata-table rows to actual files: explicit file column > normalized
    title match (filename heuristic breaks ties: copies/preprints penalized)."""
    for mr in store.meta_rows:
        row = mr["row"]
        cand = None
        file_hint = row.get("file") or row.get("filename") or row.get("path")
        if file_hint:
            hint = Path(str(file_hint)).name.lower()
            cand = next((f for f in doc_files if f["name"].lower() == hint), None)
        if cand is None and row.get("title"):
            nt = norm_title(row["title"])
            matches = [f for f in doc_files if f.get("title") and
                       norm_title(f["title"]) == nt and not f.get("meta_row")]
            if matches:
                def score(f):
                    stem = Path(f["name"]).stem.lower()
                    pen = 2 if re.search(r"copy|dup|backup|preprint|_old|_v\d", stem) else 0
                    return (-pen, -len(f.get("text") or ""))
                matches.sort(key=score, reverse=True)
                cand = matches[0]
                if len(matches) > 1:
                    store.add_unc(f"metadata row {mr['id']}",
                                  f"title matches {len(matches)} files; mapped to "
                                  f"{cand['name']} by filename/content heuristic")
        if cand is None and row.get("title"):
            # fallback: shared tokens between row title and filename stem
            ttok = {t for t in norm_title(row["title"]).split() if len(t) >= 3}
            best, best_n = None, 0
            for f in doc_files:
                if f.get("meta_row"):
                    continue
                stok = set(re.split(r"[^a-z0-9\u4e00-\u9fff]+",
                                    Path(f["name"]).stem.lower()))
                n = len(ttok & stok)
                if n > best_n:
                    best, best_n = f, n
            if best is not None:
                cand = best
                store.add_unc(f"metadata row {mr['id']}",
                              f"no exact title match; mapped to {cand['name']} by "
                              "filename-token overlap heuristic")
        if cand is not None:
            cand["meta_row"] = mr
        else:
            store.add_unc(f"metadata row {mr['id']}",
                          "no document file matches this row (title/file); row kept unattached")


def assign_document_ids(store, doc_files):
    used = {f["meta_row"]["id"] for f in doc_files if f.get("meta_row") and f["meta_row"]["id"]}
    prefixes = [re.match(r"^([A-Za-z]*)(\d+)$", i) for i in used]
    prefix = "D"
    nums = [int(m.group(2)) for m in prefixes if m]
    if nums:
        pref_counts = {}
        for m in prefixes:
            if m:
                pref_counts[m.group(1) or "D"] = pref_counts.get(m.group(1) or "D", 0) + 1
        prefix = max(pref_counts, key=pref_counts.get)
    n = 0
    for f in doc_files:
        if f.get("meta_row") and f["meta_row"]["id"]:
            f["did"] = f["meta_row"]["id"]
            continue
        while True:
            n += 1
            did = f"{prefix}{n:02d}"
            if did not in used:
                break
        used.add(did)
        f["did"] = did


def infer_type(f):
    blob = ((f.get("title") or "") + " " + Path(f["name"]).stem).lower()
    for typ, kws in TYPE_HINTS:
        if any(k in blob for k in kws):
            return typ
    if f["ext"] in ("csv", "tsv", "tab"):
        return "dataset"
    return None


def build_documents(ir, store, case):
    doc_files = [f for f in store.files if f.get("role") == "document"]
    match_metadata_rows(store, doc_files)
    assign_document_ids(store, doc_files)
    by_hash = {}
    for f in doc_files:
        if f.get("sha256"):
            by_hash.setdefault(f["sha256"], []).append(f)
    # hash-duplicate inheritance source: first file (with a metadata row) per group
    dup_of = {}
    for h, group in by_hash.items():
        if len(group) < 2:
            continue
        canon = next((g for g in group if g.get("meta_row")), group[0])
        for g in group:
            if g is not canon:
                dup_of[g["did"]] = canon
                g["dup_canon"] = canon

    attach_version_notes(store, doc_files)

    docs = []
    for f in doc_files:
        did, sid = f["did"], f["sid"]
        paras = f.get("paragraphs") or []
        text = f.get("text") or ""
        mr = f.get("meta_row")
        canon = f.get("dup_canon")
        meta = {}
        filled, missing = [], []
        for field in META_FIELDS:
            entry = None
            if mr and mr["row"].get(field) not in (None, ""):
                entry = {"value": str(mr["row"][field]), "status": "reported",
                         "evidence": {"source_id": mr["sid"], "field": field,
                                      "quote": clip(mr["raw"], 400)}}
            elif canon is not None and canon.get("meta_row") and \
                    canon["meta_row"]["row"].get(field) not in (None, ""):
                cmr = canon["meta_row"]
                entry = {"value": str(cmr["row"][field]), "status": "inferred",
                         "uncertainty": f"content-hash duplicate of {canon['did']}; "
                                        "field taken from its metadata row",
                         "evidence": {"source_id": cmr["sid"], "field": field,
                                      "quote": clip(cmr["raw"], 400)}}
            if entry is None:
                entry = extract_field(field, f, paras, text)
            if entry is None:
                entry = {"value": None, "status": "not_reported"}
                missing.append(field)
            else:
                filled.append(field)
            meta[field] = entry
        f["filled"], f["missing"] = filled, missing
        title = meta["title"].get("value") or f.get("title")
        aliases = []
        for a in store.aliases:
            doc_ref = str(a.get("document") or "")
            if doc_ref and (doc_ref.lower() == f["name"].lower() or
                            doc_ref == did or
                            Path(doc_ref).name.lower() == f["name"].lower()):
                if a["alias"] not in aliases:
                    aliases.append(a["alias"])
                f.setdefault("alias_entries", []).append(a)
        doc = {"document_id": did, "source_id": sid, "title": title,
               "path": f["rel"], "aliases": aliases, "metadata": meta,
               "versions": f.get("versions", [])}
        if f["ext"] not in ("txt", "md", "text", "csv", "tsv", "json", "log") and paras:
            doc["paragraphs"] = paras  # transcribe non-plain text (pdf/docx salvage)
        docs.append(doc)
        if missing and not mr:
            store.add_unc(f"{did}.metadata",
                          f"fields {missing} absent from the file and all provided "
                          "tables/notes; left not_reported (not invented)")
    ir["documents"] = docs
    return doc_files


def extract_field(field, f, paras, text):
    """Evidence-grounded single-field extraction from the ACTUAL file text."""
    sid = f["sid"]
    if field == "title":
        head = f.get("title")
        if head and paras:
            return {"value": head, "status": "reported",
                    "evidence": {"source_id": sid, "paragraph_id": paras[0]["id"],
                                 "quote": clip(head, 300)}}
        if head:
            return {"value": head, "status": "reported",
                    "evidence": {"source_id": sid, "field": "filename",
                                 "quote": f["name"]}}
        return None
    if field == "doi":
        p, quote, hit = find_quote_paragraph(paras, re.compile(r"10\.\d{4,9}/[^\s,;\"'<>]+"))
        if p:
            return {"value": hit.rstrip(".,;)"), "status": "reported",
                    "evidence": {"source_id": sid, "paragraph_id": p["id"],
                                 "quote": clip(quote, 300)}}
        return None
    if field == "year":
        p, quote, hit = find_quote_paragraph(
            paras, re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b|\b(?:19|20)\d{2}\b"))
        if p:
            return {"value": hit[:4], "status": "inferred",
                    "uncertainty": "year inferred from a date/year mention in the text; "
                                   "may be a grant/measurement date, not publication year",
                    "evidence": {"source_id": sid, "paragraph_id": p["id"],
                                 "quote": clip(quote, 300)}}
        return None
    if field == "authors":
        m = re.search(r"^authors?\s*[:：]\s*(.+)$", text, re.M | re.I)
        if m:
            p = next((p for p in paras if m.group(0) in p["text"]), None)
            ev = {"source_id": sid, "quote": clip(m.group(0), 300)}
            if p:
                ev["paragraph_id"] = p["id"]
            return {"value": m.group(1).strip(), "status": "reported", "evidence": ev}
        return None
    if field == "type":
        typ = infer_type(f)
        if typ and paras:
            return {"value": typ, "status": "inferred",
                    "uncertainty": "type inferred from heading/filename keywords",
                    "evidence": {"source_id": sid, "paragraph_id": paras[0]["id"],
                                 "quote": clip(f.get("title") or f["name"], 300)}}
        return None
    if field == "project":
        p, quote, hit = find_quote_paragraph(
            paras, re.compile(r"\bP-[A-Z0-9]+\b|\bProject\s+[A-Z][A-Z0-9-]+"))
        if p:
            val = hit if hit.startswith("P-") else hit.split(None, 1)[-1]
            return {"value": val, "status": "inferred",
                    "uncertainty": "project code inferred from a text mention",
                    "evidence": {"source_id": sid, "paragraph_id": p["id"],
                                 "quote": clip(quote, 300)}}
        return None
    return None


def attach_version_notes(store, doc_files):
    """Bind administrative version-note lines to documents by the document ids
    they actually mention; build version chains / dup / recover hints."""
    dids = {f["did"]: f for f in doc_files}
    for vl in store.version_lines:
        line, sid = vl["text"], vl["sid"]
        tokens = set(re.findall(r"\b[A-Za-z]+-?\d+\b", line))
        mentioned = sorted((t for t in tokens if t in dids), key=line.find)
        if not mentioned:
            if any(re.match(r"^[A-Z]+\d+$", t) for t in tokens):
                store.add_unc("version_notes",
                              f"note mentions unregistered id(s) {sorted(tokens)}; "
                              f"not attached: {clip(line, 160)}")
            continue
        ev = {"source_id": sid, "quote": clip(line, 400)}
        low = line.lower()
        subject = mentioned[0]  # the note's subject is the first id it mentions
        for did in mentioned:
            f = dids[did]
            versions = f.setdefault("versions", [])
            chain = re.findall(
                r"(\S+)\s+v(\d+)\s+([A-Za-z_]+)\s+(\d{4}-\d{2}-\d{2})", line)
            if chain and "superseded" in low:
                prev = None
                for tok, vn, label, date in chain:
                    if tok != did:
                        continue
                    v = {"version_id": f"{did}V{vn}", "label": label, "date": date,
                         "note": clip(line, 300), "evidence": ev}
                    if prev:
                        v["supersedes"] = prev
                    prev = v["version_id"]
                    if not any(x.get("version_id") == v["version_id"] for x in versions):
                        versions.append(v)
            elif did != subject:
                continue  # non-subject ids in the line are context, not the target
            elif "duplicate" in low or "identical" in low:
                f["dup_note"] = line
            elif "recover" in low or "lost" in low:
                f["recover_note"] = line
                date = re.search(r"\d{4}-\d{2}-\d{2}", line)
                versions.append({"version_id": f"{did}V{len(versions) + 1}",
                                 "label": "recovered",
                                 "date": date.group(0) if date else None,
                                 "note": clip(line, 300), "evidence": ev})
            elif "preprint" in low:
                date = re.search(r"\d{4}-\d{2}-\d{2}", line)
                versions.append({"version_id": f"{did}V{len(versions) + 1}",
                                 "label": "preprint",
                                 "date": date.group(0) if date else None,
                                 "note": clip(line, 300), "evidence": ev})
            else:
                store.add_unc(f"{did}.version_note",
                              f"administrative note not auto-interpretable: {clip(line, 200)}")


# ── per-kind finalizers ──────────────────────────────────────────────────────

def finalize_common(ir, store, case):
    ir["sources"] = store.sources
    ir.setdefault("operations", [])
    ir.setdefault("searches", [])
    ir.setdefault("questions", [])
    ir.setdefault("annotations", [])
    ir.setdefault("knowledge_cards", [])
    ir["provenance"] = {"pipeline": "actual material -> auto_extract -> IR -> validate "
                                    "-> index/compute -> artifact -> result",
                        "changes": [{"at": kit.utc_now(), "change":
                                     f"auto_library: deterministic extraction from "
                                     f"{len(store.sources)} material files"}]}
    for e in store.errors:
        store.add_unc("extraction", e)


def f_manage(ir, store, case):
    doc_files = build_documents(ir, store, case)
    ops = ir["operations"]
    tsid = store.task_sid()
    task = case.get("task_md") or ""
    wq = next((ln.strip() for ln in task.splitlines()
               if re.search(r"kind", ln, re.I)), None) or \
        next((ln.strip() for ln in task.splitlines() if ln.strip()), None) or \
        f"case_id {case.get('case_id')}"
    ops.append({"op_id": f"O{len(ops) + 1}", "type": "index", "target": "LIBRARY",
                "target_kind": "library", "status": "done",
                "note": f"auto index over {len(doc_files)} documents "
                        "(engine computes hashes/aliases/coverage)",
                "evidence": {"source_id": tsid, "quote": clip(wq, 300)}})
    for f in doc_files:
        for a in f.get("alias_entries", []):
            ops.append({"op_id": f"O{len(ops) + 1}", "type": "alias_fix",
                        "target": f["did"], "status": "done",
                        "note": f"alias '{a['alias']}' resolved to {f['did']} ({f['name']})",
                        "evidence": {"source_id": a["sid"], "quote": clip(a["raw"], 300)}})
    # content-hash dedup (real hashes computed by kit over actual files)
    for f in doc_files:
        canon = f.get("dup_canon")
        if canon is not None:
            ev = ({"source_id": store.version_sid, "quote": clip(f["dup_note"], 400)}
                  if f.get("dup_note") and store.version_sid else
                  {"source_id": f["sid"], "field": "sha256", "quote": f["sha256"]})
            ops.append({"op_id": f"O{len(ops) + 1}", "type": "dedup",
                        "target": f["did"], "status": "done",
                        "note": f"content-hash duplicate of {canon['did']}; kept, not deleted",
                        "evidence": ev})
        elif f.get("dup_note"):
            ops.append({"op_id": f"O{len(ops) + 1}", "type": "dedup",
                        "target": f["did"], "status": "conflict",
                        "reason": "administrative note claims a duplicate but content "
                                  "hashes differ; human_confirm",
                        "evidence": {"source_id": store.version_sid,
                                     "quote": clip(f["dup_note"], 400)}})
            store.add_unc(f"{f['did']}.dedup",
                          "note claims duplicate but sha256 differs from every other file")
    # recovery (files under recovered/ or explicit loss/recovery notes)
    for f in doc_files:
        if f.get("recover_note") or f["rel"].lower().startswith("recovered/"):
            ev = ({"source_id": store.version_sid, "quote": clip(f["recover_note"], 400)}
                  if f.get("recover_note") and store.version_sid else
                  {"source_id": f["sid"], "quote": clip(f.get("title") or f["name"], 300)})
            ops.append({"op_id": f"O{len(ops) + 1}", "type": "recover",
                        "target": f["did"], "status": "done", "to_path": f["rel"],
                        "note": "recovered copy verified present under input; indexed",
                        "evidence": ev})
    # metadata fill / honest skips
    for f in doc_files:
        if f.get("meta_row") or f.get("dup_canon") is not None:
            src = "metadata.csv row" if f.get("meta_row") else \
                f"duplicate inheritance from {f['dup_canon']['did']}"
            ops.append({"op_id": f"O{len(ops) + 1}", "type": "metadata_fill",
                        "target": f["did"], "status": "done",
                        "note": f"filled {f['filled']} from {src}",
                        "evidence": ({"source_id": f["meta_row"]["sid"],
                                      "quote": clip(f["meta_row"]["raw"], 400)}
                                     if f.get("meta_row") else
                                     {"source_id": f["sid"], "field": "sha256",
                                      "quote": f["sha256"]})})
        if f["missing"]:
            ops.append({"op_id": f"O{len(ops) + 1}", "type": "metadata_fill",
                        "target": f["did"], "status": "skipped",
                        "reason": f"{f['missing']} absent from the file, metadata table "
                                  "and notes; not invented"})
    if any(f.get("meta_row") for f in doc_files):
        store.add_unc("metadata row->file mapping",
                      "rows mapped by normalized title (+filename heuristic for "
                      "copies/preprints); verify against the workorder")


def f_classify(ir, store, case):
    build_documents(ir, store, case)
    tax = store.taxonomy
    if isinstance(tax, dict) and tax.get("categories"):
        tax = dict(tax)
        tax.setdefault("abstain_threshold", 0.25)
        tax.setdefault("multi_label", True)
        ir["taxonomy"] = tax
        store.add_unc("taxonomy", "provided taxonomy file used as-is; verify category rules",
                      "note")
        return
    # derive categories from the document types ACTUALLY observed in the library
    types = []
    for d in ir["documents"]:
        t = (d.get("metadata") or {}).get("type", {}).get("value")
        if t and t not in types:
            types.append(t)
    cats = []
    for i, t in enumerate(types, 1):
        kws = [t] + [k for k in TYPE_SYNONYMS.get(t, []) if k != t]
        cats.append({"id": f"C{i}", "name": t,
                     "rules": [{"rule_id": f"C{i}R1", "keywords": kws,
                                "fields": ["title", "type", "text"], "weight": 1.0}]})
    if not cats:
        # no type metadata anywhere: keyword categories from real headings
        found = []
        for typ, kws in TYPE_HINTS:
            if any(any(k in (d.get("title") or "").lower() for k in kws)
                   for d in ir["documents"]):
                found.append((typ, kws))
        for i, (typ, kws) in enumerate(found, 1):
            cats.append({"id": f"C{i}", "name": typ,
                         "rules": [{"rule_id": f"C{i}R1", "keywords": kws,
                                    "fields": ["title", "text"], "weight": 1.0}]})
    if not cats:
        title_tokens = []
        for d in ir["documents"]:
            for t in re.findall(r"[A-Za-z]{3,}|[\u4e00-\u9fff]{2,}", d.get("title") or ""):
                if t.lower() not in title_tokens:
                    title_tokens.append(t.lower())
        cats = [{"id": "C1", "name": "general (auto fallback)",
                 "rules": [{"rule_id": "C1R1", "keywords": title_tokens[:8] or ["library"],
                            "fields": ["title", "text"], "weight": 1.0}]}]
        store.add_unc("taxonomy", "no type metadata or heading keywords found; "
                      "fallback category uses real title tokens")
    ir["taxonomy"] = {"abstain_threshold": 0.25, "multi_label": True, "categories": cats}
    store.add_unc("taxonomy categories/rules",
                  "auto-derived from observed document types/heading keywords "
                  "(keyword rules, not expert taxonomy); engine abstains below "
                  "threshold -> human_confirm")


def f_annotate(ir, store, case):
    doc_files = build_documents(ir, store, case)
    anns = ir["annotations"]
    for f in doc_files:
        paras = f.get("paragraphs") or []
        body = [p for p in paras if p is not (paras[0] if paras else None)]
        picked = []
        for p in body or paras:
            m = RESULT_HINTS.search(p["text"])
            if m:
                picked.append((p, m.group(0)))
            if len(picked) >= 2:
                break
        if not picked and paras:
            p = (body or paras)[0]
            picked.append((p, None))
        for p, hit in picked:
            quote = sentence_with(p["text"], hit) if hit else sentences_of(p["text"])[0] \
                if sentences_of(p["text"]) else p["text"].strip()
            if not quote:
                continue
            anns.append({"annotation_id": f"A{len(anns) + 1}",
                         "document_id": f["did"], "paragraph_id": p["id"],
                         "page": p.get("page", 1), "quote": clip(quote, 400),
                         "kind": "reported",
                         "tags": ["auto-extract"] + ([hit.lower()] if hit and
                                                     len(hit) <= 20 else []),
                         "note": f"Key statement auto-located in {f['name']} "
                                 f"({p['id']}); verbatim quote, selection is a "
                                 "heuristic — verify interpretation."})
        if not picked:
            anns.append({"annotation_id": f"A{len(anns) + 1}",
                         "document_id": f["did"], "field": "title",
                         "kind": "reported",
                         "note": "document registered but no readable body paragraph "
                                 "to annotate; title-level marker only"})
    if anns:
        store.add_unc("annotation selection/notes",
                      "annotations auto-bound to real paragraph locators with verbatim "
                      "quotes; which statements deserve annotation is a heuristic "
                      "choice -> human_confirm")
    else:
        store.add_unc("annotations", "no readable documents found; cannot annotate "
                      "(nothing fabricated)")


def task_queries(task):
    qs = re.findall(r"['\"“]([^'\"”]{3,})['\"”]", task)
    qs += [m.group(1).strip() for m in
           re.finditer(r"(?:query|search|检索(?:式|词)?)\s*[:：]\s*(.+)", task, re.I)]
    return list(dict.fromkeys(q for q in qs if q.strip()))


def f_search(ir, store, case):
    build_documents(ir, store, case)
    task = case.get("task_md") or ""
    qs = task_queries(task)
    if not qs:
        head = next((ln.strip().lstrip("#").strip() for ln in task.splitlines()
                     if ln.strip() and not ln.strip().startswith("# SYNTHETIC")), None)
        if head:
            qs = [head]
            store.add_unc("search query", "no explicit query in task.md; first task "
                          "line used as query -> human_confirm")
    for i, q in enumerate(qs[:5], 1):
        ir["searches"].append({"search_id": f"SR{i}", "query": clip(q, 300),
                               "scope": [], "filters": {}})
    if not ir["searches"]:
        store.add_unc("searches", "no query found in materials; none invented")


def f_qa(ir, store, case):
    build_documents(ir, store, case)
    task = case.get("task_md") or ""
    qs = [ln.strip() for ln in task.splitlines()
          if ln.strip().endswith(("?", "？"))]
    qs += [m.group(1).strip() for m in
           re.finditer(r"(?:question|问题)\s*[:：]\s*(.+)", task, re.I)]
    qs = list(dict.fromkeys(qs))
    if not qs:
        head = next((ln.strip().lstrip("#").strip() for ln in task.splitlines()
                     if ln.strip()), None)
        if head:
            qs = [head]
            store.add_unc("questions", "no explicit question in task.md; first task "
                          "line used -> human_confirm")
    for i, q in enumerate(qs[:5], 1):
        ir["questions"].append({"question_id": f"Q{i}", "question": clip(q, 400),
                                "scope": []})  # engine computes extractive answers
    if not ir["questions"]:
        store.add_unc("questions", "no question found in materials; none invented")


FINALIZERS = {
    "library_manage": f_manage,
    "library_classify": f_classify,
    "library_annotate": f_annotate,
    "library_search": f_search,
    "library_qa": f_qa,
}


# ── status / result helpers (mirror assemble.py policy) ─────────────────────

def emergency_result(case, out_dir, error, sources=None, kind=None):
    """Last-resort honest result.json using ONLY json/os (kit may be unavailable)."""
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


# ── main pipeline ────────────────────────────────────────────────────────────

def run(args):
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(args.work)
    work_dir.mkdir(parents=True, exist_ok=True)

    case = kit.load_case(args.input)
    materials = kit.list_materials(args.input)
    store = Store(case, materials, args.input)
    store.register_sources(materials)
    kind = detect_kind(args.kind, case, store)
    ir = kit.base_ir(case, kind)
    ir["sources"] = store.sources

    store.parse_all()
    finalize_common(ir, store, case)
    FINALIZERS[kind](ir, store, case)

    # de-duplicate uncertainty entries
    seen, uniq = set(), []
    for u in store.uncertainty + ir.get("uncertainty", []):
        key = (u.get("item"), u.get("reason"))
        if key not in seen:
            seen.add(key)
            uniq.append(u)
    ir["uncertainty"] = uniq
    if not store.sources:
        ir["uncertainty"].append({"item": "materials",
                                  "reason": "input directory empty or unreadable; "
                                            "nothing to extract",
                                  "handling": "human_confirm"})

    kit.write_json(work_dir / "library_ir.json", ir)

    validation = engine.validate_ir(ir)
    kit.write_json(out_dir / "validation.json", validation)

    outputs, summary, build_error = [], {}, None
    try:
        outputs = engine.build(ir, case, out_dir)
        sp = out_dir / "_summary.json"
        if sp.exists():
            summary = kit.load_json(sp)
            sp.unlink()
    except Exception as e:
        build_error = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    if build_error:
        status = "partial" if outputs else "failed"
        ir["uncertainty"].append({"item": "build", "reason": build_error,
                                  "handling": "human_confirm"})
    elif validation["errors"]:
        status = "partial"
    else:
        status = engine.compute_status(ir, validation, summary)

    notes = AUTO_NOTE
    if validation["errors"]:
        notes += " IR validation errors present; see validation.json."
    result = kit.build_result(case, ir, outputs, status, validation=validation,
                              extra={"summary": summary,
                                     "autopilot": {"kind": kind,
                                                   "n_materials": len(materials),
                                                   "n_documents": len(ir.get("documents", [])),
                                                   "work_ir": str(work_dir / "library_ir.json")}},
                              notes=notes)
    if build_error:
        result["build_error"] = build_error
    kit.write_result(out_dir, result)
    print(json.dumps({"status": status, "case_id": case["case_id"], "kind": kind,
                      "n_outputs": len(outputs),
                      "n_documents": len(ir.get("documents", [])),
                      "summary": summary,
                      "errors": validation["errors"],
                      "warnings": validation["warnings"][:10]},
                     ensure_ascii=True, indent=2))
    return 0 if status in ("success", "partial") else 1


def main():
    ap = argparse.ArgumentParser(description="library track autopilot (auto-extract IR + run engine)")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--kind", default=None)
    args = ap.parse_args()

    case, sources, kind = {}, [], None
    try:
        if kit is None or engine is None:
            raise RuntimeError("cannot import sibling w4kit.py / library_engine.py")
        return run(args)
    except Exception as e:
        traceback.print_exc()
        # honest fallback: NEVER exit without result.json
        try:
            case = kit.load_case(args.input) if kit else {}
            kind = norm_kind(args.kind) if args_kind_ok(args.kind) else "library_manage"
            try:
                mats = kit.list_materials(args.input) if kit else []
                sources = [{"id": f"S{i:02d}", "path": m["path"], "name": m["name"],
                            "type": (m.get("ext") or "").lstrip(".")}
                           for i, m in enumerate(mats, 1)]
            except Exception:
                sources = []
            ir = kit.base_ir(case, kind) if kit else {"kind": kind}
            ir["sources"] = sources
            ir["uncertainty"] = [{"item": "pipeline",
                                  "reason": f"{type(e).__name__}: {e}",
                                  "handling": "human_confirm"}]
            result = kit.build_result(case, ir, [], "failed",
                                      notes=AUTO_NOTE + f" FATAL: {e}")
            result["error"] = f"{type(e).__name__}: {e}"
            kit.write_result(args.out, result)
        except Exception as e2:
            emergency_result(case, args.out, f"{e}; fallback also failed: {e2}",
                             sources=sources, kind=kind)
        print(json.dumps({"status": "failed", "error": str(e)}, ensure_ascii=True))
        return 1


def args_kind_ok(k):
    return bool(k) and norm_kind(k) in (engine.KINDS if engine else
                                        {"library_manage", "library_search",
                                         "library_classify", "library_qa",
                                         "library_annotate"})


if __name__ == "__main__":
    sys.exit(main())