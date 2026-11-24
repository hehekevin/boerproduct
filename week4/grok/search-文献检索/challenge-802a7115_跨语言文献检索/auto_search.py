"""auto_search.py — deterministic "autopilot" entry point for the week4 SEARCH track.

Reads the ACTUAL organizer-provided local materials under --input, auto-extracts
a complete IR (sources / records / queries / references / edges / snapshots /
databases / criteria / documents ...), runs the EXISTING search_engine
(validate_ir + build) and writes an honest result.json preserving every
output_contract key + case_id. Stdlib only; additive — does not modify the engine.

Usage:
  PYTHONDONTWRITEBYTECODE=1 python auto_search.py --input /input --out /app/output \
      [--work /app/work] [--kind KIND]

Design rules:
  * Never fabricate: every record/quote/number comes from real file content.
  * Judgment-heavy fields (relevance labels, miss categories, reviewer decisions,
    appraisal grades) get deterministic, evidence-grounded heuristic defaults and
    are flagged human_confirm in uncertainty[] (=> honest status "partial").
  * Defensive extraction: a bad/missing file becomes an honest gap, never a crash.
  * The WHOLE pipeline is wrapped: on ANY exception an honest result.json is still
    written (status partial/failed) with contract keys + case_id + sources + error.
  * After this baseline runs, the agent may refine /app/work/search_ir.json within
    budget and re-run assemble.py to improve judgment fields.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
import zlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    import w4kit as kit
    import search_engine as engine
except Exception:  # catastrophic import failure -> emergency writer below
    kit = None
    engine = None

AUTO_NOTE = ("auto_search autopilot: deterministic extraction from ACTUAL local "
             "materials + existing search_engine computation; no live remote "
             "search, no fabricated records/citations/status. Judgment fields use "
             "documented evidence-grounded heuristics flagged human_confirm; "
             "refine work/search_ir.json and re-run assemble.py to improve.")

STOPWORDS = set("""a an the of for and or to in on at by with from as is are was
were be been being this that these those it its their his her our your my we you
they he she them us i not no nor only own same so than too very can will just
should now study studies paper article review using use used based via between
into over under after before during about against both each few more most other
some such all any do does did done has have had having if then else when where
which who whom what how why also may might must shall could would one two three
new old high low large small results result method methods approach approaches
""".split())

METHOD_HINTS = {"learning", "network", "networks", "model", "models", "deep",
                "neural", "algorithm", "simulation", "sequencing", "intervention",
                "trial", "randomized", "randomised", "rct", "benchmark", "method",
                "profiling", "screening", "assay", "microscopy", "spectroscopy"}

ANIMAL_SYNONYMS = {"animal", "animals", "mice", "mouse", "murine", "rat", "rats",
                   "bovine", "porcine", "zebrafish", "drosophila"}

KIND_KEYWORDS = [
    ("coverage_analysis", ["覆盖率", "遗漏", "coverage", "known-item", "known item",
                           "recall", "miss attribution", "denominator"]),
    ("multi_db_merge", ["多数据库", "联合检索", "multi-database", "multi database",
                        "merge", "crossref", "europepmc", "field normalization"]),
    ("citation_tracking", ["引文追踪", "引文", "citation track", "citation graph",
                           "reference graph", "citing", "forward/backward", "seed"]),
    ("incremental_tracking", ["增量", "最新文献", "incremental", "import state",
                              "snapshot", "subscription", "watermark", "retract"]),
    ("systematic_screening", ["系统性", "纳排", "prisma", "systematic",
                              "dual reviewer", "dual independent", "adjudicat",
                              "inclusion/exclusion", "screening audit"]),
    ("quality_appraisal", ["质量评价", "质量评估", "quality appraisal", "risk of bias",
                           "rob ", "appraise", "grade", "dimension"]),
    ("cross_language", ["跨语言", "cross-language", "cross language", "translation",
                        "bilingual", "语言", "term alignment"]),
    ("patent_search", ["专利", "patent", "uspto", "claim", "family", "legal status"]),
    ("question_driven", ["问题驱动", "question-driven", "question driven",
                         "subquestion", "fixed research question"]),
    ("screen_rank", ["筛选与智能排序", "筛选", "排序", "screen and rank", "screen_rank",
                     "rank", "keep/maybe/exclude", "label"]),
    ("query_planning", ["检索策略", "查询规划", "query plan", "facet", "keyword expansion",
                        "multi-round", "research question"]),
]

# raw bibliographic field aliases -> canonical
FIELD_ALIASES = {
    "title": ["title", "ti", "titletitle", "articletitle", "dc.title", "name",
              "publicationtitle", "inventiontitle"],
    "doi": ["doi", "do", "dc.identifier", "identifier_doi"],
    "year": ["year", "py", "pubyear", "publicationyear", "issued", "published-print",
             "published-online", "published", "date", "dc.date", "pubdate"],
    "authors": ["authors", "au", "authorstring", "author", "dc.creator", "creators",
                "inventors", "inventor"],
    "journal": ["journal", "jo", "journaltitle", "container-title", "sourcetitle",
                "dc.source", "source", "journalinfo", "venue", "publication"],
    "abstract": ["abstract", "abstracttext", "description", "summary"],
}


# ── small helpers ────────────────────────────────────────────────────────────

def tokens(text):
    return {t for t in re.findall(r"[a-z0-9\u4e00-\u9fff]+", str(text or "").lower())
            if len(t) >= 3 and t not in STOPWORDS}


def year_of(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        y = int(v)
        return y if 1500 <= y <= 2100 else None
    if isinstance(v, dict):  # crossref date-parts
        dp = v.get("date-parts") or []
        if dp and isinstance(dp[0], list) and dp[0]:
            return year_of(dp[0][0])
        return None
    if isinstance(v, list):
        return year_of(v[0]) if v else None
    m = re.search(r"(18|19|20)\d{2}", str(v))
    return int(m.group(0)) if m else None


def authors_of(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, list):
        names = []
        for a in v:
            if isinstance(a, dict):
                fam = a.get("family") or a.get("lastName") or ""
                giv = a.get("given") or a.get("firstName") or ""
                nm = (str(fam) + " " + str(giv)).strip() or a.get("name") or a.get("literal") or ""
                if nm:
                    names.append(str(nm).strip())
            elif a:
                names.append(str(a).strip())
        return "; ".join(n for n in names if n) or None
    if isinstance(v, dict):
        return v.get("name") or v.get("literal")
    return str(v)


def journal_of(v):
    if isinstance(v, list):
        return str(v[0]) if v else None
    if isinstance(v, dict):  # europepmc journalInfo
        j = v.get("journal") or {}
        return j.get("title") or j.get("medlineAbbreviation") or v.get("title")
    return str(v) if v else None


def first_str(v):
    if isinstance(v, list):
        return str(v[0]) if v else None
    return str(v) if v is not None else None


def sanitize_raw(obj):
    """Copy raw material data for embedding; rename any nested 'source_id' so it
    cannot collide with the IR's registered-source namespace (check_sources)."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "source_id":
                out["original_source_id"] = v
            else:
                out[k] = sanitize_raw(v)
        return out
    if isinstance(obj, list):
        return [sanitize_raw(x) for x in obj]
    return obj


def clip(s, n=600):
    s = str(s)
    return s if len(s) <= n else s[:n] + "..."


def exact_quote(text, needle, limit=300):
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


# ── text / PDF reading ───────────────────────────────────────────────────────

def pdf_text(data: bytes) -> str:
    """Best-effort stdlib PDF text salvage: inflate FlateDecode streams and pull
    text-show operators; fall back to raw utf-8 replace decoding."""
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
    """Split text into paragraphs with ids/pages. Handles [Pn] markers and
    markdown headers like '## p1-para1 (Methods, page 2)'."""
    paras = []
    lines = text.splitlines()
    cur_id, cur_page, cur_section, buf = None, None, None, []

    def flush():
        nonlocal buf, cur_id, cur_page, cur_section
        body = "\n".join(buf).strip()
        if body:
            pid = cur_id or f"P{len(paras) + 1}"
            paras.append({"id": pid, "text": body, "page": cur_page,
                          "section": cur_section})
        buf = []

    for ln in lines:
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
    return paras


# ── JSON structure probing ───────────────────────────────────────────────────

def json_item_lists(data):
    """Yield (container_label, list_of_dicts) for known response shapes."""
    if isinstance(data, list):
        if data and all(isinstance(x, dict) for x in data):
            yield ("root", data)
        return
    if not isinstance(data, dict):
        return
    msg = data.get("message")
    if isinstance(msg, dict):
        if isinstance(msg.get("items"), list):
            yield ("message.items", msg["items"])
        elif any(k in msg for k in ("DOI", "title")):
            yield ("message", [msg])
        if isinstance(msg.get("reference"), list):
            yield ("message.reference", msg["reference"])
    elif isinstance(msg, list):
        yield ("message", msg)
    for key in ("items", "results", "records", "data", "rows", "reference",
                "references", "known_items", "reference_set", "edges", "queries",
                "snapshots", "patents", "works", "views", "databases"):
        v = data.get(key)
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            yield (key, v)
    rl = data.get("resultList")
    if isinstance(rl, dict) and isinstance(rl.get("result"), list):
        yield ("resultList.result", rl["result"])
    if isinstance(data.get("result"), list):
        yield ("result", data["result"])


def item_role(item):
    """Classify a JSON dict by its ACTUAL keys."""
    ks = {str(k).lower() for k in item}
    if ("from" in ks and "to" in ks) or ("citing" in ks and "cited" in ks):
        return "edge"
    if "snapshot_id" in ks or ("window" in ks and "record_ids" in ks):
        return "snapshot"
    if "query_string" in ks or ("query_id" in ks and ("snippet" in ks or "n_hits" in ks)) \
            or ("query" in ks and "database" in ks):
        return "query"
    if "numbers" in ks and isinstance(item.get("numbers"), dict):
        return "patent"
    if "publication_number" in ks or "application_number" in ks:
        return "patent"
    if "work_id" in ks and ("language" in ks or "version" in ks):
        return "view"
    if "canonical_title" in ks:
        return "work"
    if "term" in ks and "render" in ks:
        return "term"
    if "inclusion_reason" in ks or "unusable" in ks:
        return "reference"
    if any(k in ks for k in ("title", "ti", "doi", "do", "articletitle", "raw_id")):
        return "record"
    if "key" in ks and ("doi" in ks or "unstructured" in ks or "article-title" in ks):
        return "reference"  # crossref reference-list entry
    return "unknown"


def bib_from_item(item):
    """Canonical bibliographic fields from a raw item (Crossref/EuropePMC/flat)."""
    low = {str(k).lower(): v for k, v in item.items()}
    out = {}
    for canon, aliases in FIELD_ALIASES.items():
        for a in aliases:
            if a in low and low[a] not in (None, "", []):
                v = low[a]
                if canon == "title":
                    out[canon] = first_str(v)
                elif canon == "year":
                    out[canon] = year_of(v)
                elif canon == "authors":
                    out[canon] = authors_of(v)
                elif canon == "journal":
                    out[canon] = journal_of(v)
                elif canon == "doi":
                    out[canon] = first_str(v)
                else:
                    out[canon] = v if isinstance(v, str) else first_str(v)
                break
    if not out.get("year"):
        for k in ("issued", "published-print", "published-online", "date", "pubdate"):
            if k in low:
                out["year"] = year_of(low[k])
                if out["year"]:
                    break
    return out


# ── material store ───────────────────────────────────────────────────────────

class Store:
    def __init__(self, case, materials):
        self.case = case
        self.sources = []
        self.files = []            # per-file parsed info
        self.by_name = {}
        self.records = []          # canonical record dicts (with source_id/snippet)
        self.references = []       # reference/known-item dicts
        self.queries = []
        self.edges = []
        self.snapshots = []
        self.patents = []
        self.terms = []
        self.criteria = []         # {id,type,text,source_id}
        self.documents = []        # {sid,name,text,paragraphs}
        self.works = []
        self.views = []
        self.databases = []
        self.errors = []           # extraction gaps -> uncertainty
        self.uncertainty = []
        self.id_aliases = {}       # (sid, original_id) -> final id
        self._rid = 0
        self._qid = 0
        self.raw_json = {}         # sid -> parsed json (for direct IR fragments)

    # -- source registration -------------------------------------------------
    def register_sources(self, materials):
        for i, m in enumerate(materials, 1):
            sid = f"S{i}"
            ext = (m.get("ext") or "").lstrip(".") or "file"
            self.sources.append({"id": sid, "path": m["path"], "name": m["name"],
                                 "type": ext})
            self.files.append({"sid": sid, "path": m["path"], "name": m["name"],
                               "ext": ext, "role": None})
            self.by_name[m["name"].lower()] = self.files[-1]

    def file_of(self, name):
        return self.by_name.get(str(name).lower())

    def new_rid(self, base=None):
        self._rid += 1
        return base or f"R{self._rid}"

    def add_unc(self, item, reason, handling="human_confirm"):
        self.uncertainty.append({"item": item, "reason": reason, "handling": handling})

    # -- record ingestion ----------------------------------------------------
    def add_record(self, bib, sid, raw=None, snippet=None, role="record",
                   orig_id=None, extra=None):
        if not bib.get("title") and not bib.get("doi"):
            self.add_unc(f"record from {sid}",
                         "item has neither title nor DOI; skipped (no fabricated records)",
                         "human_confirm")
            return None
        rid = orig_id
        if rid:
            key = (sid, str(rid))
            if key in self.id_aliases:
                rid = self.id_aliases[key]
            elif any(r["id"] == rid for r in self.records + self.references):
                new = f"{rid}__{sid}"
                self.id_aliases[key] = new
                rid = new
            else:
                self.id_aliases[key] = rid
        else:
            rid = self.new_rid()
        rec = {"id": rid, "source_id": sid, "status": "reported"}
        for f in ("title", "doi", "year", "authors", "journal", "abstract"):
            if bib.get(f) not in (None, ""):
                rec[f] = bib[f]
        if snippet:
            rec["snippet"] = clip(snippet, 700)
        elif raw is not None:
            rec["snippet"] = clip(json.dumps(sanitize_raw(raw), ensure_ascii=False), 700)
        if extra:
            rec.update(extra)
        if role == "reference":
            self.references.append(rec)
        else:
            self.records.append(rec)
        return rec

    def resolve_id(self, rid):
        """Map an original material id to the final unique record id."""
        if rid is None:
            return None
        for r in self.records + self.references:
            if r["id"] == rid:
                return rid
        for (sid, orig), final in self.id_aliases.items():
            if orig == rid:
                return final
        return rid  # stub kept (engine labels it not_reported_stub)

    # -- per-file parsing ----------------------------------------------------
    def parse_all(self):
        for f in self.files:
            try:
                self.parse_file(f)
            except Exception as e:
                self.errors.append(f"{f['name']}: {type(e).__name__}: {e}")
                self.add_unc(f["name"], f"extraction failed: {e}; file registered but not parsed",
                             "human_confirm")

    def parse_file(self, f):
        name, ext, sid = f["name"], f["ext"], f["sid"]
        low = name.lower()
        if low == "case.json" or low.startswith("readme"):
            f["role"] = "task"
            return
        if ext in ("csv", "tsv", "tab"):
            self.parse_table(f)
            return
        if ext == "json":
            try:
                data = kit.load_json(f["path"])
            except Exception as e:
                f["role"] = "unparsed"
                self.add_unc(name, f"JSON unreadable: {e}", "human_confirm")
                return
            self.raw_json[sid] = data
            self.parse_json(f, data)
            return
        # text-ish (md/txt/pdf/anything else): read defensively
        try:
            text = read_material_text(f["path"])
        except Exception as e:
            self.add_unc(name, f"cannot read bytes: {e}", "human_confirm")
            return
        f["text"] = text
        f["paragraphs"] = parse_paragraphs(text)
        if low in ("task.md", "case.json") or low.startswith("readme"):
            f["role"] = "task"
            return
        if "criteria" in low or re.search(r"^\s*[-*]?\s*(INC|EXC|MAY|I|E)\d+\s*[:：]",
                                          text, re.M):
            f["role"] = "criteria"
            self.parse_criteria(f, text)
            return
        if re.search(r"(Reference\s+list|References|参考文献)\s*\n", text) and \
                re.search(r"^\s*\[?\d+[\].)]\s+\S", text, re.M):
            f["role"] = "document+references"
            self.documents.append(f)
            self.parse_md_references(f, text)
            return
        f["role"] = "document"
        self.documents.append(f)

    def parse_table(self, f):
        rows = kit.read_table(f["path"])
        f["rows"] = rows
        if not rows:
            f["role"] = "empty_table"
            self.add_unc(f["name"], "table has no data rows", "note")
            return
        cols = {str(k).lower() for k in rows[0]}
        raw_lines = {}
        try:
            for ln in read_material_text(f["path"]).splitlines()[1:]:
                first = ln.split(",")[0].split("\t")[0].strip().strip('"')
                if first:
                    raw_lines.setdefault(first, ln)
        except Exception:
            pass
        if {"term", "render"} <= cols or {"term", "language", "render"} <= cols:
            f["role"] = "terms"
            for r in rows:
                rl = {str(k).lower(): v for k, v in r.items()}
                if rl.get("term") and rl.get("render"):
                    self.terms.append({"term": rl["term"],
                                       "language": rl.get("language") or "unknown",
                                       "render": rl["render"],
                                       "type": rl.get("type") or "aligned render",
                                       "source_id": f["sid"]})
            return
        is_ref = ("inclusion_reason" in cols or "unusable" in cols
                  or re.search(r"known|reference|frozen|gold", f["name"], re.I))
        f["role"] = "references" if is_ref else "records"
        for r in rows:
            rl = {str(k).lower(): v for k, v in r.items()}
            bib = bib_from_item(rl)
            orig_id = rl.get("id") or rl.get("raw_id")
            snippet = raw_lines.get(str(orig_id)) or \
                "; ".join(f"{k}={v}" for k, v in r.items() if v not in (None, ""))
            extra = {}
            for k in ("query_id", "database_id", "version_of", "label", "decision",
                      "reason_code", "graded_relevance"):
                if rl.get(k):
                    extra[k] = rl[k]
            if str(rl.get("retracted", "")).lower() in ("true", "1", "yes"):
                extra["retracted"] = True
            if rl.get("inclusion_reason"):
                extra["inclusion_reason"] = rl["inclusion_reason"]
            if rl.get("unusable"):
                extra["unusable"] = rl["unusable"]
            if rl.get("abstract"):
                extra["abstract"] = rl["abstract"]
            self.add_record(bib, f["sid"], snippet=snippet,
                            role="reference" if is_ref else "record",
                            orig_id=orig_id, extra=extra)

    def parse_json(self, f, data):
        sid, low = f["sid"], f["name"].lower()
        # direct IR-fragment shapes
        if isinstance(data, dict):
            if isinstance(data.get("snapshots"), list) and not data.get("message"):
                f["role"] = "snapshots"
                for s in data["snapshots"]:
                    self.add_snapshot(s, sid)
                return
            if isinstance(data.get("works"), list) or isinstance(data.get("views"), list):
                f["role"] = "works_views"
                for w in data.get("works", []):
                    self.works.append({**sanitize_raw(w), "source_id": sid})
                for v in data.get("views", []):
                    self.views.append({**sanitize_raw(v), "source_id": sid})
                return
            if isinstance(data.get("databases"), list) and not any(
                    isinstance(x, dict) and item_role(x) == "record"
                    for x in data.get("databases", [])):
                f["role"] = "databases"
                for d in data["databases"]:
                    if isinstance(d, dict):
                        self.databases.append({**sanitize_raw(d), "source_id": sid})
                return
        roles = []
        found = False
        work_rec = None
        for container, items in json_item_lists(data):
            for item in items:
                if not isinstance(item, dict):
                    continue
                role = item_role(item)
                if role == "unknown":
                    continue
                found = True
                roles.append(role)
                if role == "edge":
                    self.add_edge(item, sid)
                elif role == "snapshot":
                    self.add_snapshot(item, sid)
                elif role == "query":
                    self.add_query(item, sid)
                elif role == "patent":
                    self.patents.append({**sanitize_raw(item), "source_id": sid})
                elif role == "view":
                    self.views.append({**sanitize_raw(item), "source_id": sid})
                elif role == "work":
                    self.works.append({**sanitize_raw(item), "source_id": sid})
                elif role == "term":
                    self.terms.append({**sanitize_raw(item), "source_id": sid})
                elif role == "reference":
                    rec = self.add_reference_item(item, sid, container)
                    if container == "message.reference" and work_rec and rec:
                        self.edges.append({"from": work_rec["id"], "to": rec["id"],
                                           "direction": "backward", "source_id": sid,
                                           "context": "Crossref message.reference entry "
                                                      "(retained reference list)"})
                elif role == "record":
                    bib = bib_from_item(item)
                    orig = item.get("id") or item.get("raw_id") or item.get("DOI")
                    is_ref = bool(re.search(r"known|reference|frozen|gold", low)) and \
                        not re.search(r"result|export|response|candidate", low)
                    if "inclusion_reason" in item:
                        is_ref = True
                    rec = self.add_record(bib, sid, raw=item,
                                          role="reference" if is_ref else "record",
                                          orig_id=orig)
                    if container == "message" and rec is not None:
                        work_rec = rec
                    if rec is not None and container == "message.reference":
                        rec["role_hint"] = "reference"
        # single patent record object (record_p2.json style)
        if not found and isinstance(data, dict) and item_role(data) == "patent":
            self.patents.append({**sanitize_raw(data), "source_id": sid})
            found = True
        if not found and isinstance(data, dict) and item_role(data) == "snapshot":
            self.add_snapshot(data, sid)
            found = True
        if not found and isinstance(data, dict) and item_role(data) == "query":
            self.add_query(data, sid)
            found = True
        if not found:
            # maybe a single bibliographic work (crossref single-work response)
            if isinstance(data, dict):
                bib = bib_from_item(data.get("message", data) if isinstance(data.get("message"), dict) else data)
                if bib.get("title") or bib.get("doi"):
                    self.add_record(bib, sid, raw=data)
                    found = True
        f["role"] = "+".join(sorted(set(roles))) if roles else ("json" if found else "unrecognized")
        if not found:
            self.add_unc(f["name"], "JSON structure not recognized; registered as source only",
                         "human_confirm")

    def add_reference_item(self, item, sid, container):
        low = {str(k).lower(): v for k, v in item.items()}
        bib = bib_from_item(item)
        if not bib.get("title"):
            bib["title"] = first_str(low.get("article-title") or low.get("unstructured")
                                     or low.get("key"))
        if not bib.get("doi"):
            bib["doi"] = low.get("doi")
        if not bib.get("year"):
            bib["year"] = year_of(low.get("year"))
        extra = {"inclusion_reason": item.get("inclusion_reason")
                 or f"listed in provided {container} of this source file"}
        if item.get("unusable"):
            extra["unusable"] = item["unusable"]
        return self.add_record(bib, sid, raw=item, role="reference",
                               orig_id=item.get("id") or item.get("key"), extra=extra)

    def add_query(self, item, sid):
        qid = item.get("id") or item.get("query_id") or f"Q{len(self.queries) + 1}"
        if any(q.get("id") == qid for q in self.queries):
            return
        qs = item.get("query_string") or item.get("query") or item.get("string")
        q = {"id": str(qid), "source_id": sid}
        if qs:
            q["query_string"] = str(qs)
        else:
            q["query_string"] = (f"(original query string not present in provided "
                                 f"export; logged as {qid})")
            self.add_unc(f"query {qid}",
                         "query_string absent from material; honest placeholder kept",
                         "human_confirm")
        for k in ("database", "database_id", "round", "facet_id", "subquestion_id",
                  "n_hits", "snippet"):
            if item.get(k) is not None:
                q[k] = item[k]
        self.queries.append(q)

    def add_edge(self, item, sid):
        frm = item.get("from") or item.get("citing") or item.get("source")
        to = item.get("to") or item.get("cited") or item.get("target")
        direction = item.get("direction")
        if direction not in ("forward", "backward"):
            direction = "backward" if item.get("cited") or "reference" in str(
                item.get("context", "")).lower() else "forward"
            self.add_unc(f"edge {frm}->{to}",
                         "direction not explicit in material; inferred from keys/context",
                         "human_confirm")
        ed = {"from": self.resolve_id(frm), "to": self.resolve_id(to),
              "direction": direction, "source_id": sid}
        if item.get("source_id") and item["source_id"] != sid:
            ed["original_source_id"] = item["source_id"]
        ctx = item.get("context") or item.get("note")
        if ctx:
            ed["context"] = clip(ctx, 300)
        self.edges.append(ed)

    def add_snapshot(self, item, sid):
        snap_id = item.get("id") or item.get("snapshot_id") or f"SN{len(self.snapshots) + 1}"
        if any(s.get("id") == snap_id for s in self.snapshots):
            return
        win = item.get("window") or {}
        s = {"id": str(snap_id), "source_id": sid,
             "record_ids": [self.resolve_id(r) for r in item.get("record_ids", [])]}
        if win.get("start") and win.get("end"):
            s["window"] = {"start": str(win["start"]), "end": str(win["end"])}
        else:
            imp = str(item.get("imported_at") or "")[:10]
            if imp:
                s["window"] = {"start": imp, "end": imp}
                self.add_unc(f"snapshot {snap_id}",
                             "window not provided; inferred single-day window from imported_at",
                             "human_confirm")
            else:
                years = [r.get("year") for r in self.records if r.get("year")]
                if years:
                    s["window"] = {"start": f"{min(years)}-01-01", "end": f"{max(years)}-12-31"}
                else:
                    s["window"] = {"start": "unknown", "end": "unknown"}
                self.add_unc(f"snapshot {snap_id}",
                             "window absent; inferred from record years (or unknown)",
                             "human_confirm")
        if item.get("imported_at"):
            s["imported_at"] = item["imported_at"]
        self.snapshots.append(s)

    def parse_criteria(self, f, text):
        for m in re.finditer(r"^\s*[-*]?\s*([A-Z]{1,4}\d+)\s*[:：]\s*(.+)$", text, re.M):
            code, body = m.group(1), m.group(2).strip()
            if code.startswith("EXC") or code.startswith("E"):
                ctype = "exclude"
            else:
                ctype = "include"  # INC* and MAY* routing codes (example convention)
            self.criteria.append({"id": code, "type": ctype, "text": body,
                                  "source_id": f["sid"]})
        if not self.criteria:
            for i, m in enumerate(re.finditer(r"^\s*[-*]\s+(.+)$", text, re.M), 1):
                self.criteria.append({"id": f"C{i}", "type": "include",
                                      "text": m.group(1).strip(), "source_id": f["sid"]})

    def parse_md_references(self, f, text):
        m = re.search(r"(?:References|Reference\s+list|参考文献)\s*\n(.*)", text, re.S)
        if not m:
            return
        body = m.group(1)
        for im in re.finditer(r"^\s*\[?(\d+)[\].)]\s+(.+?)(?=^\s*\[?\d+[\].)]|\Z)",
                              body, re.M | re.S):
            entry = " ".join(im.group(2).split())
            if len(entry) < 15:
                continue
            doi = re.search(r"10\.\d{4,9}/[^\s,;]+", entry)
            yr = re.search(r"\((19|20)\d{2}\)|(19|20)\d{2}", entry)
            title = entry
            tm = re.search(r"[\"“](.+?)[\"”]", entry)
            if tm:
                title = tm.group(1)
            else:
                title = re.sub(r"^\d+\.\s*", "", entry)
                title = re.sub(r"\s*doi:?\s*10\.\S+", "", title, flags=re.I)
            self.add_record({"title": clip(title, 300),
                             "doi": doi.group(0) if doi else None,
                             "year": year_of(yr.group(0)) if yr else None},
                            f["sid"], snippet=clip(entry, 500), role="reference",
                            orig_id=f"REF{im.group(1)}",
                            extra={"inclusion_reason":
                                   "extracted from the provided document reference list (auto parse)"})


# ── task / question helpers ──────────────────────────────────────────────────

def research_question(case, store):
    task = case.get("task_md") or ""
    m = re.search(r"(?:Research question|Fixed research question|研究问题)\s*[:：]\s*(.+)",
                  task, re.I)
    if m:
        return m.group(1).strip()
    qq = quoted_query(task)
    if qq:
        return qq
    for ln in task.splitlines():
        s = ln.strip().lstrip("#").strip()
        if s and not s.lower().startswith(("synthetic", "task")) and len(s) > 20:
            if "?" in s or re.search(r"screen|rank|merge|measure|track|appraise|align|search",
                                     s, re.I):
                return s
    return task.strip()[:500] or "(research question not explicit in task.md)"


def quoted_query(task):
    m = re.search(r"query\s+['\"“]([^'\"”]+)['\"”]", task, re.I)
    if m:
        return m.group(1)
    m = re.search(r"for\s*[:：]?\s*['\"“]([^'\"”]+)['\"”]", task)
    return m.group(1) if m else None


def detect_language(name, text):
    low = name.lower()
    for code in ("zh", "cn", "en", "pt", "es", "fr", "de", "ja", "jp", "ko", "ru"):
        if re.search(r"[_\-.]" + code + r"[_\-.]?", low) or low.endswith("_" + code + ".md"):
            return {"cn": "zh", "jp": "ja"}.get(code, code)
    sample = text[:3000]
    cjk = len(re.findall(r"[\u4e00-\u9fff]", sample))
    kana = len(re.findall(r"[\u3040-\u30ff]", sample))
    hangul = len(re.findall(r"[\uac00-\ud7af]", sample))
    if kana > 5:
        return "ja"
    if hangul > 5:
        return "ko"
    if cjk > max(10, len(sample) * 0.05):
        return "zh"
    lowtxt = sample.lower()
    if re.search(r"[ãõç]|piroptose|\bum\b|\bem\b|estudo|células", lowtxt):
        return "pt"
    if re.search(r"ñ|\bestudio\b|\blos\b|\blas\b", lowtxt):
        return "es"
    if re.search(r"\bétude\b|\ble\b|\bles\b|\bune\b", lowtxt):
        return "fr"
    if re.search(r"[äöüß]|\bund\b|\bstudie\b", lowtxt):
        return "de"
    return "en"


def detect_kind(args_kind, case, store):
    if args_kind:
        k = args_kind.strip().replace("-", "_")
        if engine and k in engine.KINDS:
            return k
        if k in {x[0] for x in KIND_KEYWORDS}:
            return k
    skill = SCRIPT_DIR / "SKILL.md"
    if skill.exists():
        try:
            head = skill.read_text(encoding="utf-8", errors="replace")[:2000]
            m = re.search(r"^name:\s*search-([a-z0-9-]+)\s*$", head, re.M)
            if m:
                k = m.group(1).replace("-", "_")
                if not engine or k in engine.KINDS:
                    return k
        except Exception:
            pass
    blob = ((case.get("task_md") or "") + " " +
            json.dumps(case.get("raw") or {}, ensure_ascii=False)).lower()
    names = " ".join(f["name"].lower() for f in store.files)
    blob += " " + names
    best, best_score = None, 0
    for kind, kws in KIND_KEYWORDS:
        score = sum(1 for kw in kws if kw.lower() in blob)
        if score > best_score:
            best, best_score = kind, score
    return best or "coverage_analysis"


# ── judgment heuristics (documented, evidence-grounded, human_confirm) ──────

def lexical_features(rec, question, all_years):
    qtok = tokens(question)
    ttok = tokens(rec.get("title", "")) | tokens(rec.get("abstract", ""))
    inter = qtok & ttok
    qm = round(len(inter) / len(qtok), 4) if qtok else 0.0
    core = ("title", "authors", "year", "journal", "doi")
    eq = round(sum(1 for f in core if rec.get(f)) / len(core), 4)
    y = year_of(rec.get("year"))
    if y and all_years and max(all_years) > min(all_years):
        recency = round((y - min(all_years)) / (max(all_years) - min(all_years)), 4)
    else:
        recency = 0.5
    feats = {"question_match": qm, "evidence_quality": eq, "recency": recency,
             "facet_coverage": qm}
    if qtok & METHOD_HINTS:
        feats["method_match"] = round(len(inter & METHOD_HINTS) /
                                      max(1, len(qtok & METHOD_HINTS)), 4)
    return feats, sorted(inter)


def link_versions(records):
    """Detect preprint->published / same-DOI version chains from ACTUAL fields."""
    by_doi = {}
    for r in records:
        d = kit.normalize_doi(r.get("doi"))
        if d:
            by_doi.setdefault(d, []).append(r)
    links = []
    for d, group in by_doi.items():
        if len(group) < 2:
            continue
        def is_pre(r):
            return bool(re.search(r"preprint|biorxiv|medrxiv|arxiv",
                                  (str(r.get("title", "")) + " " +
                                   str(r.get("journal", ""))).lower()))
        pubs = [r for r in group if not is_pre(r)]
        pres = [r for r in group if is_pre(r)]
        if pubs and pres:
            for p in pres:
                if p["id"] != pubs[0]["id"]:
                    p["version_of"] = pubs[0]["id"]
                    links.append((p["id"], pubs[0]["id"]))
        else:
            ordered = sorted(group, key=lambda r: (year_of(r.get("year")) or 0, r["id"]))
            for later in ordered[1:]:
                later["version_of"] = ordered[0]["id"]
                links.append((later["id"], ordered[0]["id"]))
    # fuzzy title + explicit preprint marker (different DOI suffixes)
    for r in records:
        if r.get("version_of"):
            continue
        if re.search(r"\(preprint\)|preprint", str(r.get("title", "")).lower()):
            base = re.sub(r"\s*\(preprint\)\s*", "", str(r.get("title", "")), flags=re.I)
            for o in records:
                if o["id"] != r["id"] and kit.normalize_title(o.get("title")) == \
                        kit.normalize_title(base):
                    r["version_of"] = o["id"]
                    links.append((r["id"], o["id"]))
                    break
    return links


def negated(c):
    """Criteria like 'no intervention component' require absence judgment; a
    keyword-presence pass cannot decide them honestly -> skip + human_confirm."""
    return bool(re.match(r"^\s*(no|without|lack|lacks|not|non)\b", str(c.get("text", "")), re.I))


def crit_tokens(c):
    """Criterion keywords: drop parentheticals and '-> routing' notes so they do
    not dilute the overlap ratio (e.g. '(title/abstract decidable)')."""
    t = re.sub(r"\([^)]*\)", " ", str(c.get("text", "")))
    t = t.split("->")[0]
    return tokens(t)


def screen_decision(text, criteria, threshold=0.3, min_hits=2):
    """Deterministic criteria-keyword screening. Returns (decision, code, matched)."""
    rtok = tokens(text)
    best = None
    for c in criteria:
        if negated(c):
            continue
        ctok = crit_tokens(c)
        if c["type"] == "exclude":
            ctok |= (ANIMAL_SYNONYMS & rtok)
            ctok = {t for t in ctok if t not in STOPWORDS}
        if not ctok:
            continue
        hits = ctok & rtok
        ratio = len(hits) / len(ctok)
        if c["type"] == "exclude" and hits and (ratio >= 0.5 or len(hits) >= 2):
            return ("exclude", c["id"], sorted(hits))
        if c["type"] == "include" and ((ratio >= threshold and len(hits) >= min_hits)
                                       or ratio >= 0.6):
            if best is None or ratio > best[0]:
                best = (ratio, c["id"], sorted(hits))
    if best:
        return ("include", best[1], best[2])
    for c in criteria:
        if re.match(r"MAY", c["id"]) and crit_tokens(c) & rtok:
            return ("maybe", c["id"], sorted(crit_tokens(c) & rtok))
    may = next((c for c in criteria if re.match(r"MAY", c["id"])), None)
    if may:
        return ("maybe", may["id"], [])
    inc = next((c for c in criteria if c["type"] == "include" and not negated(c)), None)
    return ("maybe", inc["id"] if inc else (criteria[0]["id"] if criteria else "C1"), [])


def infer_query_links(store, ir):
    """When records carry no explicit query_id, link each to the query whose
    string shares the most title tokens (documented lexical inference)."""
    linked_any = False
    qtoks = [(q["id"], tokens(q.get("query_string", ""))) for q in ir.get("queries", [])]
    qtoks = [(qid, t) for qid, t in qtoks if t and not str(
        next(q.get("query_string", "") for q in ir["queries"] if q["id"] == qid)).startswith("(original")]
    for r in store.records:
        if r.get("query_id"):
            continue
        rtok = tokens(r.get("title", ""))
        best, best_n = None, 0
        for qid, qt in qtoks:
            n = len(rtok & qt)
            if n > best_n:
                best, best_n = qid, n
        if best:
            r["query_id"] = best
            r.setdefault("matched_queries", [])
            if best not in r["matched_queries"]:
                r["matched_queries"].append(best)
            linked_any = True
    if linked_any:
        store.add_unc("record->query links",
                      "query_id inferred by lexical overlap with query strings "
                      "(no explicit link in materials); human_confirm", "human_confirm")


def default_criteria(question, sid):
    return [
        {"id": "C1", "type": "include",
         "text": f"record lexically matches the research question: {clip(question, 200)}",
         "source_id": sid},
        {"id": "C2", "type": "exclude",
         "text": "no lexical overlap with the research question (off-topic)",
         "source_id": sid},
        {"id": "C3", "type": "include",
         "text": "insufficient metadata/abstract to judge -> maybe / human queue",
         "source_id": sid},
    ]


# ── per-kind IR finalizers ───────────────────────────────────────────────────

def task_sid(store):
    f = store.file_of("task.md")
    return f["sid"] if f else (store.sources[0]["id"] if store.sources else "S1")


def ensure_queries_from_responses(store):
    """Link records to queries via response snippets mentioning record ids."""
    rid_set = {r["id"] for r in store.records}
    for q in store.queries:
        snip = str(q.get("snippet") or "")
        mentioned = re.findall(r"\b([A-Za-z][A-Za-z0-9_-]*)\s*:", snip)
        for m in mentioned:
            rid = store.resolve_id(m)
            if rid in rid_set:
                for r in store.records:
                    if r["id"] == rid:
                        r.setdefault("query_id", q["id"])
                        r.setdefault("matched_queries", [])
                        if q["id"] not in r["matched_queries"]:
                            r["matched_queries"].append(q["id"])


def finalize_common(ir, store, case):
    ir["sources"] = store.sources
    ir["queries"] = store.queries
    ir["uncertainty"] = list(store.uncertainty)
    ir["provenance"] = {"pipeline": "material -> auto_extract -> IR -> validate -> artifact -> result",
                        "changes": [{"step": "auto_extract", "at": kit.utc_now(),
                                     "detail": f"deterministic extraction from "
                                               f"{len(store.sources)} material files"}]}
    for e in store.errors:
        ir["uncertainty"].append({"item": "extraction", "reason": e,
                                  "handling": "human_confirm"})


def f_query_planning(ir, store, case):
    q = research_question(case, store)
    tsid = task_sid(store)
    ir["research_question"] = {"text": q, "source_id": tsid}
    ensure_queries_from_responses(store)
    infer_query_links(store, ir)
    for i, qq in enumerate(ir["queries"], 1):
        qq.setdefault("round", i)
    qtok = sorted(tokens(q))
    if qtok:
        ir["facets"] = [{"id": "F1", "text": "research question terms (auto-extracted)",
                         "terms": qtok[:12], "expanded_terms": []}]
        for qq in ir["queries"]:
            qq.setdefault("facet_id", "F1")
    years = [year_of(r.get("year")) for r in store.records if year_of(r.get("year"))]
    for r in store.records:
        feats, inter = lexical_features(r, q, years)
        r["features"] = feats
        r["relevance_rationale"] = ("auto lexical heuristic: title/abstract tokens "
                                    f"shared with research question = {inter or 'none'}; "
                                    "features are computed overlaps, human_confirm")
        qm = feats["question_match"]
        r["label"] = "keep" if qm >= 0.5 else ("maybe" if qm >= 0.2 else "exclude")
        r.setdefault("matched_queries", [r["query_id"]] if r.get("query_id") else [])
    ir["records"] = store.records
    ir["ranking"] = {"k": min(10, max(3, len(store.records)))}
    ir["uncertainty"].append({"item": "relevance features/labels",
                              "reason": "auto lexical-overlap heuristics, not expert judgment",
                              "handling": "human_confirm"})
    if not ir["queries"]:
        ir["uncertainty"].append({"item": "queries", "reason": "no query log found in materials",
                                  "handling": "human_confirm"})


def f_question_driven(ir, store, case):
    q = research_question(case, store)
    tsid = task_sid(store)
    ensure_queries_from_responses(store)
    infer_query_links(store, ir)
    sq_ids = []
    for qq in ir["queries"]:
        if qq.get("subquestion_id") and qq["subquestion_id"] not in sq_ids:
            sq_ids.append(qq["subquestion_id"])
    if not sq_ids:
        sq_ids = ["SQ1"]
    subquestions = []
    for sq in sq_ids:
        linked = [qq for qq in ir["queries"] if qq.get("subquestion_id") == sq]
        if linked and linked[0].get("query_string", "").startswith("(original"):
            text = f"(subquestion text not provided in materials; id {sq} from response log)"
            store.add_unc(f"subquestion {sq}", "text absent from materials; honest placeholder",
                          "human_confirm")
        else:
            text = f"Evidence addressing: {linked[0]['query_string']}" if linked \
                else f"Sub-question {sq} of the fixed research question"
        subquestions.append({"id": sq, "text": text})
    ir["questions"] = [{"id": "RQ1", "text": q, "source_id": tsid,
                        "subquestions": subquestions}]
    q_to_sq = {qq["id"]: qq.get("subquestion_id") or sq_ids[0] for qq in ir["queries"]}
    for qq in ir["queries"]:
        qq.setdefault("subquestion_id", sq_ids[0])
    years = [year_of(r.get("year")) for r in store.records if year_of(r.get("year"))]
    for r in store.records:
        feats, inter = lexical_features(r, q, years)
        qm = feats["question_match"]
        dec = "include" if qm >= 0.2 else ("maybe" if qm >= 0.08 else "exclude")
        r["decision"] = dec
        r["reason_code"] = {"include": "auto_lexical_match", "maybe": "auto_partial_match",
                            "exclude": "auto_off_topic"}[dec]
        r["evidence"] = [{"source_id": r["source_id"], "field": "title",
                          "quote": r.get("title") or r.get("doi")}]
        r["subquestion_ids"] = [q_to_sq[r["query_id"]]] if r.get("query_id") in q_to_sq \
            else ([sq_ids[0]] if dec == "include" else [])
        r["features"] = feats
    ir["records"] = store.records
    ir["stopping"] = {"reason": "autopilot baseline: all provided candidates screened in one "
                                "pass over the finite local export; no live search; open gaps "
                                "escalated to human (refine within budget)",
                      "rounds_run": len({qq.get("round", 1) for qq in ir["queries"]}) or 1}
    ir["uncertainty"].append({"item": "screening decisions",
                              "reason": "auto lexical heuristics over title/abstract; human_confirm",
                              "handling": "human_confirm"})


def f_screen_rank(ir, store, case):
    q = research_question(case, store)
    tsid = task_sid(store)
    ir["research_question"] = {"text": q, "source_id": tsid}
    auto_crit = not store.criteria
    crit = store.criteria or default_criteria(q, tsid)
    ir["criteria"] = crit
    for c in crit:
        if negated(c):
            store.add_unc(f"criterion {c['id']}",
                          "negated criterion (absence judgment) not auto-decidable; human_confirm",
                          "human_confirm")
    years = [year_of(r.get("year")) for r in store.records if year_of(r.get("year"))]
    inc_code = next((c["id"] for c in crit if c["type"] == "include" and not negated(c)), "C1")
    exc_code = next((c["id"] for c in crit if c["type"] == "exclude" and not negated(c)), None)
    may_code = next((c["id"] for c in crit if re.match(r"(MAY|C3)", c["id"])), inc_code)
    for r in store.records:
        feats, inter = lexical_features(r, q, years)
        r["features"] = feats
        qm = feats["question_match"]
        text = (r.get("title") or "") + " " + (r.get("abstract") or "")
        if auto_crit:
            # default criteria: decide directly from documented lexical overlap
            if qm >= 0.5:
                dec, code = "include", inc_code
            elif qm < 0.2 and r.get("doi") and r.get("abstract"):
                dec, code = "exclude", (exc_code or inc_code)
            else:
                dec, code = "maybe", may_code
            hits = inter
        else:
            dec, code, hits = screen_decision(text, crit)
            if dec == "maybe" and qm >= 0.5:
                dec, code = "include", inc_code
        label = {"include": "keep", "exclude": "exclude", "maybe": "maybe"}[dec]
        if not r.get("doi") and not r.get("abstract") and qm < 0.5:
            label = "maybe"
            code = may_code
            r["status"] = "insufficient_evidence"
        r["label"] = label
        r["reason_code"] = code
        r["graded_relevance"] = 3 if qm >= 0.7 else 2 if qm >= 0.5 else 1 if qm >= 0.2 else 0
        quote = r.get("title") or r.get("doi") or ""
        r["evidence"] = [{"source_id": r["source_id"], "field": "title", "quote": quote}]
        r["relevance_rationale"] = (f"auto lexical heuristic: shared tokens {inter or hits or 'none'}; "
                                    "human_confirm")
    link_versions(store.records)
    ir["records"] = store.records
    ir["ranking"] = {"k": min(10, max(3, len(store.records)))}
    ir["uncertainty"].append({"item": "labels/features/graded_relevance",
                              "reason": "deterministic lexical heuristics, not expert judgment; "
                                        "criteria auto-derived from task question when no criteria file",
                              "handling": "human_confirm"})


def f_citation_tracking(ir, store, case):
    # promote reference-list items that are graph endpoints into records so the
    # BFS carries real metadata instead of stubs (Crossref message.reference etc.)
    endpoints = {e["from"] for e in store.edges} | {e["to"] for e in store.edges}
    promoted = [r for r in store.references if r["id"] in endpoints]
    for r in promoted:
        r.pop("role_hint", None)
        r.pop("inclusion_reason", None)
        store.records.append(r)
    store.references = [r for r in store.references if r["id"] not in endpoints]
    ir["records"] = store.records
    ir["edges"] = store.edges
    task = case.get("task_md") or ""
    rid_set = {r["id"] for r in store.records}
    seeds = []
    seed_ctx = re.search(r"seed[^.\n]*", task, re.I)
    if seed_ctx:
        for m in re.findall(r"\b([A-Za-z][A-Za-z0-9_-]*)\b", seed_ctx.group(0)):
            rid = store.resolve_id(m)
            if rid in rid_set and rid not in seeds:
                seeds.append(rid)
    if not seeds:
        froms = [e["from"] for e in store.edges if e["from"] in rid_set]
        seeds = list(dict.fromkeys(froms))[:3]
    if not seeds and store.records:
        seeds = [store.records[0]["id"]]
        store.add_unc("seeds", "no seed explicit in task/graph; first record used as seed",
                      "human_confirm")
    if not store.edges:
        store.add_unc("edges", "no retained reference graph found in materials; "
                      "BFS will be empty (honest gap)", "human_confirm")
    ir["seeds"] = seeds
    ir["max_depth"] = 2
    ir["uncertainty"].append({"item": "graph scope",
                              "reason": "traversal over organizer-retained edges only; "
                                        "no live citation coverage claimed",
                              "handling": "note"})


def f_multi_db(ir, store, case):
    # one database per export file that yielded records
    rec_sids = list(dict.fromkeys(r["source_id"] for r in store.records))
    dbs = list(store.databases)
    have = {d.get("id") for d in dbs}
    prio_map = {"crossref": 1, "europepmc": 2, "pubmed": 3, "wos": 4, "scopus": 5}
    for i, sid in enumerate(rec_sids, 1):
        f = next((x for x in store.files if x["sid"] == sid), {})
        nm = f.get("name", sid)
        dbid = f"DB{len(dbs) + 1}"
        base = re.sub(r"[^a-z]", "", nm.lower())
        prio = next((v for k, v in prio_map.items() if k in base), 10 + i)
        dbs.append({"id": dbid, "name": nm, "priority": prio, "source_id": sid})
        have.add(dbid)
        for r in store.records:
            if r["source_id"] == sid and not r.get("database_id"):
                r["database_id"] = dbid
    ir["databases"] = dbs
    # field mapping + per-field provenance from RAW keys actually observed
    fmap = {}
    for r in store.records:
        raw = r.pop("_raw", None)
        if raw is None:
            continue
        r["raw_fields"] = sanitize_raw(raw)
        fs = {}
        low = {str(k).lower(): k for k in raw}
        for canon, aliases in FIELD_ALIASES.items():
            if canon == "abstract":
                continue
            for a in aliases:
                if a in low and raw[low[a]] not in (None, "", []):
                    orig_key = low[a]
                    if orig_key.lower() != canon:
                        fmap[orig_key] = canon
                    fs[canon] = {"source_id": r["source_id"], "field": orig_key}
                    break
        if fs:
            r["field_sources"] = fs
    ir["field_mapping"] = fmap
    # queries: keep logged ones; else one per database from task quote / placeholder
    tsid = task_sid(store)
    qq = quoted_query(case.get("task_md") or "")
    if not store.queries:
        for d in dbs:
            qid = f"Q{len(ir['queries']) + 1}"
            if qq:
                qs = qq
            else:
                qs = f"(query string not recorded in provided export for {d['name']})"
                store.add_unc(f"query {qid}", "original query string absent from materials",
                              "human_confirm")
            ir["queries"].append({"id": qid, "query_string": qs,
                                  "database_id": d["id"], "source_id": d.get("source_id", tsid)})
    else:
        for q in ir["queries"]:
            if q.get("database_id") not in have:
                q.pop("database_id", None)
    for r in store.records:
        if r.get("query_id") and not any(q["id"] == r["query_id"] for q in ir["queries"]):
            r.pop("query_id", None)
        if not r.get("database_id"):
            r["database_id"] = dbs[0]["id"] if dbs else "DB1"
    ir["records"] = store.records
    ir["uncertainty"].append({"item": "merge priority",
                              "reason": "priorities auto-assigned (Crossref=1, EuropePMC=2, "
                                        "others by file order); confirm against workorder",
                              "handling": "human_confirm"})


def f_incremental(ir, store, case):
    link_versions(store.records)
    for r in store.records:
        if r.get("version_of") and not any(x["id"] == r["version_of"] for x in store.records):
            r.pop("version_of")
    ir["records"] = store.records
    snaps = sorted(store.snapshots, key=lambda s: str(s.get("window", {}).get("start", "")))
    if not snaps:
        years = [year_of(r.get("year")) for r in store.records if year_of(r.get("year"))]
        win = {"start": f"{min(years)}-01-01", "end": f"{max(years)}-12-31"} if years \
            else {"start": "unknown", "end": "unknown"}
        snaps = [{"id": "SN_AUTO1", "window": win, "source_id": task_sid(store),
                  "record_ids": [r["id"] for r in store.records]}]
        store.add_unc("snapshots", "no import-state files found; single inferred snapshot "
                      "from record years (no live/latest claim)", "human_confirm")
    ir["snapshots"] = snaps
    task = case.get("task_md") or ""
    tm = re.search(r"topic\s+['\"“]([^'\"”]+)['\"”]", task, re.I)
    ir["subscription"] = {"topic": tm.group(1) if tm else research_question(case, store),
                          "source_id": task_sid(store),
                          "dedup_key": "normalized DOI, else normalized title+year",
                          "scope": "organizer-local import states only; NO live/latest claim"}
    ir["uncertainty"].append({"item": "version links",
                              "reason": "preprint->published links inferred from same normalized "
                                        "DOI / title markers; human_confirm",
                              "handling": "human_confirm"})


def f_coverage(ir, store, case):
    refs = store.references
    if not refs:
        # fall back: reference-role hints inside record files
        hinted = [r for r in store.records if r.pop("role_hint", None) == "reference"]
        refs = hinted
        store.records = [r for r in store.records if r not in hinted]
    if not refs:
        store.add_unc("reference_set", "no independent known-item/reference list found in "
                      "materials; denominator missing (cannot fabricate)", "human_confirm")
    for x in refs:
        x.setdefault("inclusion_reason", "listed in the provided frozen known-item source")
        x.pop("role_hint", None)
    ir["reference_set"] = refs
    ir["records"] = store.records
    ensure_queries_from_responses(store)
    infer_query_links(store, ir)
    had_rounds = any("round" in q for q in ir["queries"])
    for i, q in enumerate(ir["queries"], 1):
        q.setdefault("round", i)
    if ir["queries"] and not had_rounds:
        store.add_unc("query rounds", "round numbers inferred from query-log order", "note")
    # compute hits with the ENGINE's own matcher; attribute misses heuristically
    norm = [engine.norm_record(r) for r in store.records]
    qtok_all = set()
    for q in ir["queries"]:
        qtok_all |= tokens(q.get("query_string", ""))
    miss_attr = []
    for x in refs:
        if x.get("unusable"):
            continue
        hits, method = engine._match(x, norm)
        if hits:
            continue
        rtok = tokens(x.get("title", ""))
        uncovered = sorted(rtok - qtok_all)
        qstrs = "; ".join(f"{q['id']}={clip(q.get('query_string', ''), 80)}"
                          for q in ir["queries"]) or "(no queries registered)"
        ref_doi = kit.normalize_doi(x.get("doi"))
        near = [r for r in norm if kit._title_sim(x.get("title", ""), r.get("title", "")) >= 0.5]
        if ref_doi and near:
            cat = "identifier_anomaly"
            expl = (f"title-similar record(s) {','.join(r['id'] for r in near[:3])} exist but "
                    f"DOI {ref_doi} does not match any retrieved DOI; check identifier variants "
                    f"against queries {qstrs}")
        elif rtok and len(uncovered) / max(1, len(rtok)) >= 0.5:
            cat = "term_not_covered"
            expl = (f"reference title tokens {uncovered[:8]} are not covered by any registered "
                    f"query string ({qstrs}); add synonyms/fields for these terms")
        elif not ref_doi:
            cat = "identifier_anomaly"
            expl = (f"reference has no DOI and fuzzy title match failed against queries "
                    f"{qstrs}; identifier/title-variant gap")
        else:
            cat = "other"
            expl = (f"no lexical/identifier path from registered queries ({qstrs}) to this "
                    f"item in source {x.get('source_id')}; suspected source-indexing gap; "
                    f"human_confirm required")
        miss_attr.append({"reference_id": x["id"], "category": cat, "explanation": expl})
        store.add_unc(f"miss {x['id']}", f"auto attribution '{cat}' is a lexical/identifier "
                      "heuristic; verify against actual search logs", "human_confirm")
    ir["miss_attributions"] = miss_attr
    # supplementary rounds from round-tagged queries that recover base-round misses
    rounds = []
    if ir["queries"]:
        max_round = max(q.get("round", 1) for q in ir["queries"])
        base_records = [engine.norm_record(r) for r in store.records
                        if (next((q.get("round", 1) for q in ir["queries"]
                                  if q["id"] == r.get("query_id")), 1)) <= 1]
        base_hits = set()
        for x in refs:
            if x.get("unusable"):
                continue
            hs, _ = engine._match(x, base_records)
            if hs:
                base_hits.add(x["id"])
        for rnd in range(2, max_round + 1):
            qids = [q["id"] for q in ir["queries"] if q.get("round", 1) == rnd]
            rids = [r["id"] for r in store.records if r.get("query_id") in qids]
            new_hits = []
            for x in refs:
                if x.get("unusable") or x["id"] in base_hits:
                    continue
                for r in store.records:
                    if r["id"] in rids:
                        hs, _ = engine._match(x, [engine.norm_record(r)])
                        if hs:
                            new_hits.append(x["id"])
                            base_hits.add(x["id"])
                            break
            if qids:
                rounds.append({"id": f"SR{rnd - 1}", "query_ids": qids,
                               "new_record_ids": rids,
                               "basis": "round inferred from query-log order; new hits computed "
                                        "by engine matcher (auto)"})
    ir["supplementary_rounds"] = rounds
    ir["uncertainty"].append({"item": "denominator independence",
                              "reason": "reference set taken from provided known-item/reference "
                                        "files, never from retrieved results",
                              "handling": "note"})


def f_systematic(ir, store, case):
    tsid = task_sid(store)
    q = research_question(case, store)
    crit = store.criteria or default_criteria(q, tsid)
    if not any(re.match(r"MAY", c["id"]) for c in crit):
        crit.append({"id": "MAY_AUTO", "type": "include",
                     "text": "insufficient information / abstract-only -> human decision",
                     "source_id": tsid})
    ir["criteria"] = crit
    for c in crit:
        if negated(c):
            store.add_unc(f"criterion {c['id']}",
                          "negated criterion (absence judgment) not auto-decidable; human_confirm",
                          "human_confirm")
    db_names = [f["name"] for f in store.files if f.get("role") in ("records", "references")]
    ir["protocol"] = {"databases": db_names or ["provided local export"],
                      "search_date": "(not recorded in provided materials)",
                      "criteria_version": "as provided in criteria file (auto-extracted)",
                      "query_strings": [qq.get("query_string") for qq in store.queries] or
                                       [quoted_query(case.get("task_md") or "") or q],
                      "source_id": tsid,
                      "note": "autopilot baseline protocol; refine within budget"}
    for r in store.records:
        title = r.get("title") or ""
        full = title + " " + (r.get("abstract") or "") + " " + (r.get("snippet") or "")
        revs = []
        for reviewer, text in (("auto_A_title", title), ("auto_B_title_abstract", full)):
            dec, code, hits = screen_decision(text, crit)
            ev_quote = title if reviewer == "auto_A_title" else (r.get("abstract") or title)
            ev = [{"source_id": r["source_id"],
                   "field": "title" if reviewer == "auto_A_title" else "abstract_or_title",
                   "quote": ev_quote or r.get("doi") or ""}]
            revs.append({"reviewer": reviewer, "decision": dec, "reason_code": code,
                         "evidence": ev,
                         "note": "deterministic criteria-keyword pass (not a human reviewer)"})
        r["reviewers"] = revs
        ds = {rv["decision"] for rv in revs}
        if len(ds) > 1:
            may = next((c["id"] for c in crit if re.match(r"MAY", c["id"])), crit[0]["id"])
            r["adjudication"] = {"decision": "maybe", "reason_code": may,
                                 "rationale": "automated rule passes disagreed "
                                              f"({', '.join(sorted(ds))}); escalate to human "
                                              "adjudication per criteria (auto baseline)",
                                 "adjudicator": "auto_pending_human", "source_id": tsid}
    ir["records"] = store.records
    ir["uncertainty"].append({"item": "dual screening",
                              "reason": "reviewers auto_A_title / auto_B_title_abstract are "
                                        "deterministic rule passes, NOT independent human "
                                        "reviewers; all decisions require human_confirm",
                              "handling": "human_confirm"})


APPRAISAL_DIMS = [
    {"id": "D1", "name": "design & allocation",
     "pos": ["randomiz", "randomised", "randomized", "allocation concealment",
             "randomly assigned", "computer-generated sequence"],
     "neg": ["single clinic", "convenience", "volunteers recruited", "observational"],
     "pos_grade": "low", "neg_grade": "some_concerns"},
    {"id": "D2", "name": "sampling & power",
     "pos": ["sample size was calculated", "power", "a priori", "required and"],
     "neg": ["volunteers", "single clinic", "convenience sample"],
     "pos_grade": "low", "neg_grade": "some_concerns"},
    {"id": "D3", "name": "statistics & reporting",
     "pos": ["intention-to-treat", "mixed model", "adjusted", "adjustment",
             "95% ci", "confidence interval", "multivariable"],
     "neg": ["not described", "not reported", "not stated", "unclear"],
     "pos_grade": "low", "neg_grade": "some_concerns"},
]


def f_appraisal(ir, store, case):
    docs = [d for d in store.documents if d.get("role") == "document"]
    tool = {"name": "auto default RoB-style scale (design/sampling/statistics)",
            "aggregation": "worst_domain", "critical_dimensions": ["D1"],
            "dimensions": [{"id": d["id"], "name": d["name"], "applies_to": []}
                           for d in APPRAISAL_DIMS]}
    # use a provided scale if materials ship one
    for sid, data in store.raw_json.items():
        if isinstance(data, dict) and isinstance(data.get("dimensions"), list):
            tool = {"name": data.get("name", "provided scale"),
                    "aggregation": data.get("aggregation", "worst_domain"),
                    "critical_dimensions": data.get("critical_dimensions", []),
                    "dimensions": data["dimensions"], "source_id": sid}
            break
    ir["appraisal_tool"] = tool
    papers = []
    for d in docs:
        text = d.get("text", "")
        paras = d.get("paragraphs", [])
        head = text.strip().splitlines()[0] if text.strip() else d["name"]
        pid_m = re.search(r"\b(P\d+)\b", head) or re.search(r"paper_?(p\d+)", d["name"], re.I)
        pid = pid_m.group(1).upper() if pid_m else f"DOC{len(papers) + 1}"
        title = re.sub(r"^#+\s*", "", head)
        title = re.sub(r"^SYNTHETIC\s+paper\s+P\d+\s*[—-]\s*", "", title, flags=re.I).strip()
        study = "rct" if re.search(r"randomiz|randomised|\bRCT\b", text, re.I) else \
                ("cohort" if re.search(r"cohort|followed|observational", text, re.I)
                 else "not_reported")
        dims = []
        for spec in APPRAISAL_DIMS:
            if any(dd["id"] == spec["id"] for dd in tool["dimensions"]) is False:
                continue
            judgment, grade, rationale, evidence = "insufficient_evidence", None, \
                "no dimension-relevant statement located in the provided text; abstain", []
            for p in paras:
                ptext = p["text"]
                pos_hit = next((k for k in spec["pos"] if k in ptext.lower()), None)
                neg_hit = next((k for k in spec["neg"] if k in ptext.lower()), None)
                if spec["id"] == "D3" and neg_hit:
                    break  # explicit 'not described/reported' -> abstain, never guess
                hit = pos_hit or neg_hit
                if not hit:
                    continue
                quote = exact_quote(ptext, hit)
                if not quote:
                    continue
                ev = {"source_id": d["sid"], "paragraph_id": p["id"], "quote": quote}
                if p.get("page") is not None:
                    ev["page"] = p["page"]
                evidence = [ev]
                if pos_hit and not neg_hit:
                    judgment, grade = "yes", spec["pos_grade"]
                    rationale = f"auto keyword evidence '{pos_hit}' located in text (heuristic)"
                elif neg_hit:
                    judgment, grade = "partial", spec["neg_grade"]
                    rationale = f"auto keyword concern '{neg_hit}' located in text (heuristic)"
                break
            entry = {"dimension_id": spec["id"], "judgment": judgment,
                     "rationale": rationale}
            if judgment != "insufficient_evidence":
                entry["grade"] = grade
                entry["evidence"] = evidence
            dims.append(entry)
        papers.append({"id": pid, "title": title or d["name"], "study_type": study,
                       "source_id": d["sid"], "dimensions": dims})
    if not papers:
        for r in store.records:
            papers.append({"id": r["id"], "title": r.get("title"),
                           "study_type": "not_reported", "source_id": r["source_id"],
                           "dimensions": [{"dimension_id": dd["id"],
                                           "judgment": "insufficient_evidence",
                                           "rationale": "no full text provided; abstain"}
                                          for dd in tool["dimensions"]]})
    ir["records"] = papers
    ir["uncertainty"].append({"item": "appraisal judgments/grades",
                              "reason": "auto keyword-located heuristic judgments with exact "
                                        "quotes; default scale used when none provided; "
                                        "human_confirm all grades",
                              "handling": "human_confirm"})


def f_cross_language(ir, store, case):
    docs = [d for d in store.documents if d.get("role") == "document"]
    views = list(store.views)
    works = list(store.works)
    # build views from document files
    for d in docs:
        text = d.get("text", "")
        name = d["name"]
        head = text.strip().splitlines()[0] if text.strip() else name
        lang = detect_language(name, text)
        low = (name + " " + head + " " + text[:400]).lower()
        if "abstract" in low and ("only" in low or "abstract_" in name.lower()
                                  or "abstract-only" in low):
            version = "abstract_only"
        elif "translat" in low:
            version = "publisher_translation"
        elif "bilingual" in low:
            version = "bilingual"
        else:
            version = "original"
        wm = re.search(r"\b(W\d+)\b", head)
        vm = re.search(r"\b(V\d+)\b", head)
        doi_m = re.search(r"10\.\d{4,9}/[^\s,;\"']+", text)
        title = re.sub(r"^#+\s*", "", head)
        title = re.sub(r"^SYNTHETIC[^—-]*[—-]\s*", "", title, flags=re.I)
        title = re.sub(r"\s*W\d+/V\d+\s*$", "", title).strip()
        # prefer the first real body sentence as the view title (genuine content)
        body_lines = [ln.strip() for ln in text.splitlines()
                      if ln.strip() and not ln.strip().startswith("#")]
        body_title = title
        if body_lines:
            first = re.split(r"(?<=[.!?])\s+", body_lines[0])[0].strip()
            if len(first) >= 8:
                body_title = first
        if not body_title or len(body_title) < 8:
            body_title = (body_lines[0] if body_lines else text.strip())[:120]
        views.append({"id": vm.group(1) if vm else f"V{len(views) + 1}",
                      "work_id": wm.group(1) if wm else None,
                      "language": lang, "body_language": lang,
                      "version": version, "title": body_title,
                      "doi": doi_m.group(0) if doi_m else None,
                      "source_id": d["sid"],
                      "snippet": clip(text.strip()[:300], 300),
                      "_marker_work": wm.group(1) if wm else None})
    # group views into works
    def sim(a, b):
        ta, tb = tokens(a), tokens(b)
        return len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    groups = {}
    for v in views:
        key = v.get("_marker_work") or v.get("work_id")
        if not key and v.get("doi"):
            key = "doi:" + kit.normalize_doi(v["doi"])
        if not key:
            for gk, gv in groups.items():
                if sim(v.get("title", ""), gv[0].get("title", "")) >= 0.6:
                    key = gk
                    break
        if not key:
            key = f"W{len(groups) + 1}"
        groups.setdefault(key, []).append(v)
    final_works, final_views = [], []
    seen_ids = set()
    for i, (gk, vs) in enumerate(groups.items(), 1):
        wid = gk if re.match(r"^W\d+$", str(gk)) else f"W{i}"
        en = [v for v in vs if v.get("language") == "en"]
        canon = (en or vs)[0].get("title")
        doi = next((v.get("doi") for v in vs if v.get("doi")), None)
        final_works.append({"id": wid, "canonical_title": canon, "doi": doi,
                            "source_id": vs[0]["source_id"]})
        orig_lang = next((v["language"] for v in vs if v.get("version") == "original"),
                         vs[0].get("language"))
        content_seen = {}
        for v in vs:
            vid = v.get("id") or f"V{len(final_views) + 1}"
            while vid in seen_ids:
                vid = vid + "x"
            seen_ids.add(vid)
            body_lang = orig_lang if v.get("version") == "abstract_only" else v.get("language")
            norm_content = re.sub(r"\s+", " ", (v.get("snippet") or "")).strip().lower()
            version = v.get("version") or "original"
            if norm_content and norm_content in content_seen:
                version = "exact_duplicate"
            content_seen.setdefault(norm_content, vid)
            fv = {"id": vid, "work_id": wid, "language": v.get("language") or "unknown",
                  "body_language": body_lang, "version": version,
                  "title": v.get("title"), "doi": v.get("doi"),
                  "source_id": v["source_id"], "snippet": v.get("snippet")}
            final_views.append(fv)
    if not final_works:
        store.add_unc("works/views", "no cross-language documents found in materials",
                      "human_confirm")
    ir["works"] = final_works
    ir["views"] = final_views
    ir["term_alignments"] = store.terms
    ir["uncertainty"].append({"item": "work/view identity & language/version",
                              "reason": "grouping uses header W-markers > DOI > title overlap; "
                                        "language/version detected from filename+content "
                                        "heuristics; human_confirm",
                              "handling": "human_confirm"})


PAT_NUM_RE = re.compile(r"\b([A-Z]{2}\s?\d{4}/\d{6,}\s?[A-Z]\d?)\b")
PAT_GRANT_RE = re.compile(r"\b([A-Z]{2}\s?\d{7,}\s?[AB]\d?)\b")


def f_patent(ir, store, case):
    pats = list(store.patents)
    for p in pats:
        p.setdefault("authorization", "green")
        if not p.get("id"):
            p["id"] = f"PAT{len(pats) + 1}"
        nums = p.get("numbers") or {}
        if not nums:
            nums = {}
            for k, aliases in (("publication", ["publication_number", "publication"]),
                               ("application", ["application_number", "application"]),
                               ("grant", ["grant_number", "grant"])):
                for a in aliases:
                    if p.get(a):
                        nums[k] = p.pop(a)
                        break
            p["numbers"] = nums
    # parse facsimile documents
    for d in store.documents:
        text = d.get("text", "")
        if not re.search(r"patent|USPTO|专利|Application Number|Publication", text, re.I):
            continue
        if d.get("role") != "document":
            continue
        pub = PAT_NUM_RE.search(text)
        grant = PAT_GRANT_RE.search(text)
        app = re.search(r"Application\s+Number\s*[:：]?\s*([\d/,]+)", text, re.I)
        if not (pub or app or grant):
            continue
        pid_m = re.search(r"\b(P\d+)\b", text[:200]) or re.search(r"_(p\d+)", d["name"], re.I)
        pid = pid_m.group(1).upper() if pid_m else f"PAT{len(pats) + 1}"
        if any(p.get("id") == pid for p in pats):
            pid = pid + "_F"
        nums = {}
        if pub:
            nums["publication"] = pub.group(1)
        if app:
            nums["application"] = app.group(1).strip()
        if grant:
            nums["grant"] = grant.group(1)
        title_m = re.search(r"Title\s*[:：]\s*([^\n]+)", text)
        assignee_m = re.search(r"Assignee\s*[:：]\s*([^\n;]+?)(?=\s+Title\s*[:：]|$)", text)
        filing_m = re.search(r"Filing\s+Date\s*[:：]?\s*([\d-]+)", text, re.I)
        pubdate_m = re.search(r"Publication\s+Date\s*[:：]?\s*([\d-]+)", text, re.I)
        claims = []
        for p in d.get("paragraphs", []):
            if re.search(r"claim", (p.get("section") or "") + " " + p["text"][:60], re.I):
                for cm in re.finditer(r"^\s*(\d+)\.\s+(.+)$", p["text"], re.M):
                    loc = {"source_id": d["sid"], "paragraph_id": p["id"],
                           "quote": cm.group(0).strip()}
                    if p.get("page") is not None:
                        loc["page"] = p["page"]
                    claims.append({"version": "as_published", "locator": loc,
                                   "text_snippet": cm.group(0).strip()})
        ocr = next((p["text"] for p in d.get("paragraphs", [])
                    if re.search(r"OCR|unreadable|cut", p["text"], re.I)), None)
        entry = {"id": pid, "title": title_m.group(1).strip() if title_m else d["name"],
                 "numbers": nums, "source_id": d["sid"], "authorization": "green",
                 "claims": claims}
        if assignee_m:
            entry["assignee"] = assignee_m.group(1).strip()
        if filing_m:
            entry["filing_date"] = filing_m.group(1)
        if pubdate_m:
            entry["publication_date"] = pubdate_m.group(1)
        if ocr:
            entry["ocr_boundary"] = clip(ocr, 300)
        entry["risk_flags"] = ["legal_status UNKNOWN (no official register in provided sources)"]
        pats.append(entry)
    # tech literature: non-facsimile documents with a DOI / paper-like content
    for d in store.documents:
        if d.get("role") != "document":
            continue
        text = d.get("text", "")
        if PAT_NUM_RE.search(text) or re.search(r"Application\s+Number", text, re.I):
            continue  # facsimile handled above
        doi_m = re.search(r"10\.\d{4,9}/[^\s,;\"']+", text)
        body = [ln.strip() for ln in text.splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
        if not doi_m and not body:
            continue
        title = re.split(r"(?<=[.!?])\s+", body[0])[0].strip() if body else d["name"]
        tm = re.search(r"\b(T\d+)\b", text[:200])
        rid = tm.group(1) if tm else None
        store.add_record({"title": clip(title, 300),
                          "doi": doi_m.group(0) if doi_m else None,
                          "year": year_of(text)},
                         d["sid"], snippet=clip(text.strip(), 500), orig_id=rid)
    # observed family links via priority mentions of another patent's application no.
    def norm_num(s):
        return re.sub(r"[\s\-/,]", "", str(s or "")).upper()
    app_index = {}
    for p in pats:
        a = (p.get("numbers") or {}).get("application")
        if a:
            app_index[norm_num(a)] = p["id"]
    for p in pats:
        blob = json.dumps(p, ensure_ascii=False)
        links = p.get("family_links") or []
        for m in re.finditer(r"priority[^.\n]*?([\d]{2}/[\d,]{6,})", blob, re.I):
            target = app_index.get(norm_num(m.group(1)))
            if target and target != p["id"] and not any(l.get("to") == target for l in links):
                links.append({"to": target,
                              "basis": f"observed priority mention of {m.group(1)} in this record",
                              "source_id": p["source_id"]})
        if links:
            p["family_links"] = links
    # tech literature records: keep bibliographic records that are NOT patents
    ir["patents"] = pats
    ir["records"] = store.records
    if not pats:
        store.add_unc("patents", "no patent records/facsimiles recognized in materials",
                      "human_confirm")
    ir["uncertainty"].append({"item": "legal status / families",
                              "reason": "legal status UNKNOWN (no register provided); families "
                                        "from observed priority links only, not exhaustive",
                              "handling": "human_confirm"})


FINALIZERS = {
    "query_planning": f_query_planning,
    "question_driven": f_question_driven,
    "screen_rank": f_screen_rank,
    "citation_tracking": f_citation_tracking,
    "multi_db_merge": f_multi_db,
    "incremental_tracking": f_incremental,
    "coverage_analysis": f_coverage,
    "systematic_screening": f_systematic,
    "quality_appraisal": f_appraisal,
    "cross_language": f_cross_language,
    "patent_search": f_patent,
}


# ── raw-item attachment for multi_db (kept out of records until needed) ─────

def attach_raw_items(store):
    """Re-associate raw JSON items / CSV rows with their records for raw_fields."""
    for f in store.files:
        # CSV/TSV rows
        for row in f.get("rows", []) or []:
            rl = {str(k).lower(): v for k, v in row.items()}
            orig = rl.get("id") or rl.get("raw_id")
            rid = store.id_aliases.get((f["sid"], str(orig))) if orig else None
            if rid:
                for r in store.records:
                    if r["id"] == rid and not r.get("_raw"):
                        r["_raw"] = row
                        break
        data = store.raw_json.get(f["sid"])
        if data is None:
            continue
        try:
            for container, items in json_item_lists(data):
                for item in items:
                    if not isinstance(item, dict) or item_role(item) != "record":
                        continue
                    orig = item.get("id") or item.get("raw_id") or item.get("DOI")
                    rid = store.id_aliases.get((f["sid"], str(orig))) if orig else None
                    if rid is None and orig is None:
                        bib = bib_from_item(item)
                        for r in store.records:
                            if r["source_id"] == f["sid"] and \
                                    r.get("title") == bib.get("title") and not r.get("_raw"):
                                rid = r["id"]
                                break
                    if rid:
                        for r in store.records:
                            if r["id"] == rid:
                                r["_raw"] = item
                                break
        except Exception:
            continue


# ── status / result helpers (mirror assemble.py policy) ─────────────────────

def compute_status(ir, validation):
    if validation.get("errors"):
        return "partial"
    for u in ir.get("uncertainty", []):
        if u.get("handling") == "human_confirm":
            return "partial"
    return "success"


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
    store = Store(case, materials)
    store.register_sources(materials)
    kind = detect_kind(args.kind, case, store)
    ir = kit.base_ir(case, kind)
    ir["sources"] = store.sources

    store.parse_all()
    attach_raw_items(store)
    finalize_common(ir, store, case)
    FINALIZERS[kind](ir, store, case)
    ir["uncertainty"] = list(store.uncertainty) + [
        u for u in ir.get("uncertainty", []) if u not in store.uncertainty]
    # de-duplicate uncertainty entries
    seen, uniq = set(), []
    for u in ir["uncertainty"]:
        key = (u.get("item"), u.get("reason"))
        if key not in seen:
            seen.add(key)
            uniq.append(u)
    ir["uncertainty"] = uniq
    if not store.sources:
        ir["uncertainty"].append({"item": "materials",
                                  "reason": "input directory empty or unreadable; nothing to extract",
                                  "handling": "human_confirm"})

    kit.write_json(work_dir / "search_ir.json", ir)

    validation = engine.validate_ir(ir)
    kit.write_json(out_dir / "validation.json", validation)

    outputs, build_error = [], None
    try:
        outputs = engine.build(ir, case, out_dir)
    except Exception as e:
        build_error = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    if build_error:
        status = "partial" if outputs else "failed"
        ir["uncertainty"].append({"item": "build", "reason": build_error,
                                  "handling": "human_confirm"})
    else:
        status = compute_status(ir, validation)

    notes = AUTO_NOTE
    if validation["errors"]:
        notes += " IR validation errors present; see validation.json."
    result = kit.build_result(case, ir, outputs, status, validation=validation,
                              extra={"summary": ir.get("_summary", {}),
                                     "autopilot": {"kind": kind,
                                                   "n_materials": len(materials),
                                                   "n_records": len(ir.get("records", [])),
                                                   "work_ir": str(work_dir / "search_ir.json")}},
                              notes=notes)
    if build_error:
        result["build_error"] = build_error
    kit.write_result(out_dir, result)
    print(json.dumps({"status": status, "case_id": case["case_id"], "kind": kind,
                      "n_outputs": len(outputs),
                      "n_records": len(ir.get("records", [])),
                      "summary": ir.get("_summary", {}),
                      "errors": validation["errors"],
                      "warnings": validation["warnings"][:10]},
                     ensure_ascii=False, indent=2))
    return 0 if status in ("success", "partial") else 1


def main():
    ap = argparse.ArgumentParser(description="search track autopilot (auto-extract IR + run engine)")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--kind", default=None)
    args = ap.parse_args()

    case, sources, kind = {}, [], None
    try:
        if kit is None or engine is None:
            raise RuntimeError("cannot import sibling w4kit.py / search_engine.py")
        return run(args)
    except Exception as e:
        traceback.print_exc()
        # honest fallback: NEVER exit without result.json
        try:
            case = kit.load_case(args.input) if kit else {}
            kind = kind or (args.kind or "coverage_analysis")
            try:
                mats = kit.list_materials(args.input) if kit else []
                sources = [{"id": f"S{i}", "path": m["path"], "name": m["name"],
                            "type": (m.get("ext") or "").lstrip(".")}
                           for i, m in enumerate(mats, 1)]
            except Exception:
                mats, sources = [], []
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
        print(json.dumps({"status": "failed", "error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())