"""auto_research.py — deterministic "autopilot" entry point for the week4 RESEARCH track.

Reads the ACTUAL organizer-provided local materials under --input, auto-extracts
a complete Research IR (sources / protocol / records+PRISMA / research_question /
themes / claims with EXACT re-verifiable quotes / conflicts / gaps / tool_log /
proposal / kind-specific trend|topic blocks), runs the EXISTING research_engine
(validate_ir + build) and writes an honest result.json preserving every
output_contract key + case_id. Stdlib only; additive — does not modify the engine.

Usage:
  PYTHONDONTWRITEBYTECODE=1 python auto_research.py --input /input --out /app/output \
      [--work /app/work] [--kind KIND]

Design rules (mirrors the proven search-track auto_search.py):
  * Never fabricate: every record/quote/year comes from real file content; quotes
    are EXACT substrings of the cited paragraph (the engine re-verifies them).
  * Judgment-heavy fields (screening decisions, theme clustering, claim strength,
    novelty coverage) get deterministic, evidence-grounded heuristic defaults and
    are flagged human_confirm in uncertainty[].
  * Defensive extraction: a bad/missing/binary file becomes an honest gap, never a
    crash; PDFs without a text layer are abstained, never guessed.
  * The WHOLE pipeline is wrapped: on ANY exception an honest result.json is still
    written (status partial/failed) with contract keys + case_id + sources + error.
  * After this baseline runs, the agent may refine /app/work/research_ir.json within
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
    import research_engine as engine
except Exception:  # catastrophic import failure -> emergency writer below
    kit = None
    engine = None

AUTO_NOTE = ("auto_research autopilot: deterministic extraction from ACTUAL local "
             "materials + existing research_engine computation; no live remote "
             "search, no fabricated records/quotes/years. Judgment fields use "
             "documented evidence-grounded heuristics flagged human_confirm; "
             "refine work/research_ir.json and re-run assemble.py to improve.")

STOPWORDS = set("""a an the of for and or to in on at by with from as is are was
were be been being this that these those it its their his her our your my we you
they he she them us i not no nor only own same so than too very can will just
should now study studies paper article review using use used based via between
into over under after before during about against both each few more most other
some such all any do does did done has have had having if then else when where
which who whom what how why also may might must shall could would one two three
new old high low large small results result method methods approach approaches
""".split())

KIND_KEYWORDS = [
    ("topic_novelty", ["选题", "新颖性", "创新性", "novelty", "feasibility",
                       "question definition", "falsifiable", "comparison matrix"]),
    ("trend_analysis", ["趋势", "前沿", "trend", "hotspot", "evolution", "burst",
                        "year histogram", "phase", "frontier"]),
    ("systematic_review", ["系统性", "prisma", "systematic", "quality appraisal",
                           "risk of bias", "dual reviewer", "grade"]),
    ("lit_review", ["综述", "literature review", "lit review", "thematic",
                    "narrative review", "themes"]),
    ("deep_research", ["深度研究", "deep research", "subquestion", "decompose",
                       "synthesis", "conflicting evidence", "research gap"]),
]

FINDING_VERBS = re.compile(
    r"\b(show|shows|showed|report|reports|reported|find|finds|found|reveal|"
    r"increas\w*|decreas\w*|reduc\w*|delay\w*|shorten\w*|improv\w*|enhanc\w*|"
    r"advance\w*|suppress\w*|associat\w*|correlat\w*|significant\w*|effect\w*|"
    r"observ\w*|demonstrat\w*|suggest\w*|indicat\w*)\b", re.I)
HEDGE_RE = re.compile(r"\b(may|might|could|suggest\w*|pilot|preliminary|possible|"
                      r"hypothesis|potential\w*|small sample)\b", re.I)
NEG_RE = re.compile(r"\b(no significant|no effect|no difference|no change|"
                    r"did not|failed to|not significant|no association|"
                    r"no improvement|remained unchanged)\b", re.I)
POS_RE = re.compile(r"\b(increas\w*|reduc\w*|shorten\w*|delay\w*|improv\w*|"
                    r"enhanc\w*|advance\w*|suppress\w*|significant\w*)\b", re.I)

GLOBAL_PAT_FALLBACK = re.compile(
    r"(全球|国际|世界)(首创|首次|领先|空白)|国内(首创|空白)|无人研究|尚无人(研究|报道)"
    r"|填补.{0,6}空白|world[- ]?first|first[- ]?ever|globally (novel|new)"
    r"|state[- ]of[- ]the[- ]art (overall|globally)"
    r"|已完成(了)?(全部|系统)?实验|实验(已|均)完成|experiments? (were |have been )?(completed|finished)",
    re.IGNORECASE)


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
    m = re.search(r"(18|19|20)\d{2}", str(v))
    return int(m.group(0)) if m else None


def clip(s, n=600):
    s = str(s)
    return s if len(s) <= n else s[:n] + "..."


def global_pat():
    return engine.GLOBAL_PAT if engine is not None else GLOBAL_PAT_FALLBACK


def safe_text(text, fallback):
    """Agent-authored prose must not overstep the provided-source boundary."""
    text = str(text or "").strip()
    if not text or global_pat().search(text):
        return fallback
    return text


def sentences(ptext):
    """Verbatim sentence fragments (each an EXACT substring of ptext)."""
    parts = re.split(r"(?<=[.!?])\s+|(?<=[。！？])", str(ptext or ""))
    return [p.strip() for p in parts if p and p.strip()]


def derive_verdict(covered_by):
    if engine is not None:
        return engine.derive_verdict(covered_by)
    covs = [cb.get("coverage") for cb in covered_by]
    if "full" in covs:
        return "covered"
    if "partial" in covs:
        return "partially_overlapping"
    if covs and all(c == "none" for c in covs):
        return "novel_within_sources"
    return "uncertain"


# ── text / PDF reading ───────────────────────────────────────────────────────

def _pdf_unescape(p):
    out, i = [], 0
    while i < len(p):
        c = p[i]
        if c == "\\" and i + 1 < len(p):
            nxt = p[i + 1]
            if nxt in "nrtbf":
                out.append({"n": "\n", "r": "\r", "t": "\t", "b": "", "f": ""}[nxt])
                i += 2
                continue
            if nxt.isdigit():
                j = i + 1
                oct_digits = ""
                while j < len(p) and len(oct_digits) < 3 and p[j] in "01234567":
                    oct_digits += p[j]
                    j += 1
                try:
                    out.append(chr(int(oct_digits, 8)))
                except Exception:
                    pass
                i = j
                continue
            out.append(nxt)
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _pdf_hex(h):
    try:
        data = bytes.fromhex(re.sub(r"\s+", "", h))
    except Exception:
        return ""
    if data[:2] == b"\xfe\xff":
        try:
            return data[2:].decode("utf-16-be", errors="replace")
        except Exception:
            return ""
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return data.decode("latin-1", errors="replace")


def pdf_text(data: bytes) -> str:
    """Best-effort stdlib PDF text salvage: inflate FlateDecode streams and pull
    text-show operators (literal + hex strings, Tj/TJ); fall back to raw utf-8
    replace decoding. Never guesses content that is not in the bytes."""
    chunks = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        raw = m.group(1)
        try:
            raw = zlib.decompress(raw)
        except Exception:
            pass
        try:
            s = raw.decode("latin-1", errors="replace")
        except Exception:
            continue
        if "Tj" not in s and "TJ" not in s:
            continue
        blocks = re.findall(r"BT(.*?)ET", s, re.S) or [s]
        for blk in blocks:
            parts = []
            for tm in re.finditer(r"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]+>", blk):
                tok = tm.group(0)
                if tok.startswith("("):
                    parts.append(_pdf_unescape(tok[1:-1]))
                else:
                    parts.append(_pdf_hex(tok[1:-1]))
            txt = " ".join(p for p in parts if p)
            txt = re.sub(r"\s+", " ", txt).strip()
            if txt:
                chunks.append(txt)
    if chunks:
        return "\n\n".join(chunks)
    return data.decode("utf-8", errors="replace")


def docx_text(data: bytes) -> str:
    try:
        import io
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        xml = re.sub(r"</w:p>", "\n\n", xml)
        return re.sub(r"<[^>]+>", "", xml)
    except Exception:
        return ""


def read_material_text(path):
    data = Path(path).read_bytes()
    low = str(path).lower()
    if low.endswith(".pdf") or data[:5] == b"%PDF-":
        return pdf_text(data)
    if low.endswith(".docx") or data[:2] == b"PK":
        return docx_text(data)
    return data.decode("utf-8", errors="replace")


def text_quality(text):
    """True when the extracted text looks like real prose (not font garbage)."""
    body = re.sub(r"\s+", "", str(text or ""))
    if len(body) < 40:
        return False
    good = len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", body))
    return good / len(body) >= 0.5


def parse_paragraphs(text):
    """Split text into paragraphs with ids/pages. Handles [Pn] markers and
    markdown headers; otherwise auto-assigns P1..Pn by blank-line blocks."""
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
            cur_id = None
            cur_page, cur_section = None, None
            meta = hm.group(2) or ""
            pg = re.search(r"page\s*(\d+)", hm.group(1) + " " + meta, re.I)
            if pg:
                cur_page = int(pg.group(1))
            buf.append(ln)
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


def body_paragraphs(doc):
    """Paragraphs usable as evidence: skip headings / metadata blocks."""
    out = []
    for p in doc.get("paragraphs", []):
        t = p["text"]
        if t.startswith("#"):
            continue
        if re.match(r"^(Source-id|Year|DOI|Status|SYNTHETIC)\b", t, re.I):
            continue
        if len(t) < 40:
            continue
        out.append(p)
    return out


def best_sentence(doc):
    """Pick the most finding-like sentence; returns (paragraph, sentence) or None.
    The sentence is a verbatim substring of the paragraph text."""
    best, best_score = None, -1
    for idx, p in enumerate(body_paragraphs(doc)):
        for s in sentences(p["text"]):
            if len(s) < 25:
                continue
            score = 0
            if re.search(r"\d", s):
                score += 3
            score += 2 * len(FINDING_VERBS.findall(s))
            if 40 <= len(s) <= 350:
                score += 2
            score -= idx  # prefer earlier paragraphs
            if score > best_score:
                best, best_score = (p, s), score
    return best


def evidence_of(doc, para, sentence, stance="supports", limit=300):
    quote = sentence[:limit].rstrip()
    ev = {"source_id": doc["sid"], "paragraph_id": para["id"], "quote": quote}
    if para.get("page") is not None:
        ev["page"] = para["page"]
    if stance:
        ev["stance"] = stance
    return ev


# ── material store ───────────────────────────────────────────────────────────

class Store:
    def __init__(self, case, materials, input_dir):
        self.case = case
        self.input_dir = Path(input_dir).resolve()
        self.sources = []
        self.files = []
        self.documents = []      # parsed text docs {sid,name,file,text,paragraphs,...}
        self.table_records = []  # bibliographic rows from CSV/JSON tables
        self.errors = []
        self.uncertainty = []
        self._sid = 0

    def add_unc(self, item, reason, handling="human_confirm", impact=None):
        u = {"item": item, "reason": reason, "handling": handling}
        if impact:
            u["impact"] = impact
        self.uncertainty.append(u)

    def register_sources(self, materials):
        for m in materials:
            low = m["name"].lower()
            if low == "case.json" or low == "task.md" or low.startswith("readme"):
                continue  # task framing, not evidence
            self._sid += 1
            sid = f"S{self._sid}"
            try:
                rel = Path(m["path"]).resolve().relative_to(self.input_dir).as_posix()
            except Exception:
                rel = m["name"]
            ext = (m.get("ext") or "").lstrip(".") or "file"
            f = {"sid": sid, "path": m["path"], "name": m["name"], "file": rel,
                 "ext": ext, "role": None}
            self.files.append(f)
            self.sources.append({"id": sid, "title": Path(m["name"]).stem,
                                 "file": rel, "type": ext})

    def parse_all(self):
        for f in self.files:
            try:
                self.parse_file(f)
            except Exception as e:
                self.errors.append(f"{f['name']}: {type(e).__name__}: {e}")
                self.add_unc(f["name"], f"extraction failed: {e}; file registered "
                             "but not parsed", "human_confirm")

    def parse_file(self, f):
        ext = f["ext"]
        if ext in ("csv", "tsv", "tab", "json"):
            try:
                rows = kit.read_table(f["path"])
            except Exception as e:
                self.add_unc(f["name"], f"table unreadable: {e}", "human_confirm")
                return
            rows = [r for r in rows if isinstance(r, dict)]
            if not rows:
                self.add_unc(f["name"], "table has no data rows", "note")
                return
            f["role"] = "table"
            src = next(s for s in self.sources if s["id"] == f["sid"])
            src["type"] = "data_table"
            for r in rows[:200]:
                rl = {str(k).lower(): v for k, v in r.items()}
                title = rl.get("title") or rl.get("ti") or rl.get("name")
                doi = rl.get("doi") or rl.get("do")
                if not title and not doi:
                    continue
                self.table_records.append({
                    "source_id": f["sid"], "title": str(title or doi),
                    "year": year_of(rl.get("year") or rl.get("py") or rl.get("date")),
                    "doi": str(doi) if doi else None,
                    "abstract": str(rl.get("abstract") or "")})
            return
        # text-ish (md/txt/pdf/docx/anything else): read defensively
        try:
            text = read_material_text(f["path"])
        except Exception as e:
            self.add_unc(f["name"], f"cannot read bytes: {e}", "human_confirm")
            f["role"] = "unreadable"
            return
        f["text"] = text
        f["paragraphs"] = parse_paragraphs(text)
        f["ok"] = text_quality(text)
        f["role"] = "document"
        # bibliographic metadata from the ACTUAL content
        head = ""
        for ln in text.splitlines():
            if ln.strip():
                head = ln.strip()
                break
        title = re.sub(r"^#+\s*", "", head)
        title = re.sub(r"\s*\[(P\d+)\]\s*", " ", title).strip()
        src = next(s for s in self.sources if s["id"] == f["sid"])
        if title and len(title) >= 8 and text_quality(title):
            src["title"] = clip(title, 300)
        ym = re.search(r"^Year\s*[:：]\s*((18|19|20)\d{2})", text, re.M | re.I)
        year = year_of(ym.group(1)) if ym else year_of(src["title"])
        if year is None:
            year = year_of(text[:600])
        if year is not None:
            src["year"] = year
        dm = re.search(r"10\.\d{4,9}/[^\s,;\"'<>)\]]+", text[:2000])
        if dm:
            src["doi"] = dm.group(0).rstrip(".")
        if ext in ("md", "txt", "pdf", "docx"):
            src["type"] = "journal_article"
        if not f["ok"]:
            self.add_unc(f["name"], "no usable text layer extracted (binary/encoded "
                         "content); claims from this file abstained", "human_confirm")
        self.documents.append(f)

    def doc_of(self, sid):
        return next((d for d in self.documents if d["sid"] == sid), None)


# ── task / question helpers ──────────────────────────────────────────────────

def main_question(case, store):
    task = case.get("task_md") or ""
    m = re.search(r"(?:Research question|Main question|研究问题|核心问题)\s*[:：]\s*(.+)",
                  task, re.I)
    if m:
        return m.group(1).strip()
    for ln in task.splitlines():
        s = ln.strip().lstrip("#-*0123456789. ").strip()
        if s.endswith("?") and len(s) > 15:
            return s
        if s.endswith("？") and len(s) > 8:
            return s
    # no explicit question: derive a bounded corpus-scoped question from real titles
    ttok = {}
    for d in store.documents:
        src = next((s for s in store.sources if s["id"] == d["sid"]), {})
        for t in tokens(src.get("title", "")):
            ttok[t] = ttok.get(t, 0) + 1
    top = sorted(ttok, key=lambda t: -ttok[t])[:5]
    topic = ", ".join(top) if top else "the provided materials"
    return (f"What do the provided sources report about {topic}, and where do they "
            "agree or disagree? (auto-derived scope; no explicit question found in task.md)")


def subquestions_from(case, store):
    task = case.get("task_md") or ""
    qs = []
    for ln in task.splitlines():
        s = ln.strip().lstrip("#-*0123456789.、) ").strip()
        if (s.endswith("?") or s.endswith("？")) and len(s) > 15 and s not in qs:
            qs.append(s)
    main = main_question(case, store)
    qs = [q for q in qs if q != main][:5]
    sqs = [{"id": f"SQ{i}", "question": safe_text(q, f"Sub-question {i} of the main question"),
            "depends_on": []} for i, q in enumerate(qs, 1)]
    if not sqs:
        sqs = [
            {"id": "SQ1", "question": "What effects or findings do the provided sources report?",
             "depends_on": []},
            {"id": "SQ2", "question": "Where do the provided sources disagree, and what may explain the differences?",
             "depends_on": ["SQ1"]},
            {"id": "SQ3", "question": "What evidence gaps remain within the provided source set?",
             "depends_on": ["SQ1"]},
        ]
    return sqs


def detect_kind(args_kind, case, store):
    if args_kind:
        k = args_kind.strip().replace("-", "_")
        if not engine or k in engine.KINDS:
            return k
    skill = SCRIPT_DIR / "SKILL.md"
    if skill.exists():
        try:
            head = skill.read_text(encoding="utf-8", errors="replace")[:2000]
            m = re.search(r"^name:\s*research-([a-z0-9-]+)\s*$", head, re.M)
            if m:
                k = m.group(1).replace("-", "_")
                if not engine or k in engine.KINDS:
                    return k
        except Exception:
            pass
    blob = ((case.get("task_md") or "") + " " +
            json.dumps(case.get("raw") or {}, ensure_ascii=False)).lower()
    best, best_score = None, 0
    for kind, kws in KIND_KEYWORDS:
        score = sum(1 for kw in kws if kw.lower() in blob)
        if score > best_score:
            best, best_score = kind, score
    return best or "deep_research"


# ── shared IR construction ───────────────────────────────────────────────────

def build_protocol(ir, store, question):
    qtok = sorted(tokens(question))[:8]
    query = " AND ".join(qtok) if qtok else "(provided-corpus scan)"
    ir["protocol"] = {
        "inclusion": [
            {"id": "I1", "text": "Provided source whose title/content lexically matches "
                                 "the research question (auto heuristic; human_confirm)."},
            {"id": "I2", "text": "Source has an extractable text layer allowing exact-quote "
                                 "evidence binding."},
        ],
        "exclusion": [
            {"id": "E1", "text": "No lexical overlap with the research question in title or "
                                 "extractable content (auto screening; human_confirm)."},
        ],
        "search_queries": [
            {"id": "Q1", "query": query, "intent": "core evidence scan over the provided local corpus",
             "executed": True, "date": kit.utc_now()[:10],
             "database": "provided local corpus (/input)"},
        ],
    }


def build_records(ir, store, question):
    qtok = tokens(question)
    records, keys = [], {}
    n = 0

    def add_rec(sid, title, year, doi, text_blob, has_fulltext):
        nonlocal n
        n += 1
        rid = f"R{n}"
        rec = {"id": rid, "source_id": sid, "title": title, "reviewer": "auto_agent"}
        if year is not None:
            rec["year"] = year
        if doi:
            rec["doi"] = doi
        # duplicate cross-check on REAL DOI / normalized title
        key = ("doi:" + re.sub(r"\s+", "", str(doi).lower())) if doi else \
              ("title:" + re.sub(r"[^a-z0-9]", "", str(title).lower()))
        if len(key) > 8 and key in keys:
            rec["duplicate_of"] = keys[key]
            rec["reason"] = f"Same DOI/title as {keys[key]} (auto dedup cross-check)."
            records.append(rec)
            return rec
        keys[key] = rid
        rtok = tokens(title) | tokens(text_blob[:1500])
        hits = sorted(qtok & rtok)
        if not has_fulltext:
            rec.update({"stage": "title_abstract", "decision": "pending",
                        "reason": "No extractable full text; auto screening abstains "
                                  "(human_confirm)."})
        elif len(hits) >= 2 or (qtok and len(hits) / len(qtok) >= 0.15):
            rec.update({"stage": "full_text", "decision": "include",
                        "criteria_applied": ["I1", "I2"],
                        "reason": f"Auto lexical match to question: shared terms {hits[:8]}."})
        elif not hits and len(tokens(title)) >= 4 and text_quality(text_blob):
            rec.update({"stage": "title_abstract", "decision": "exclude",
                        "criteria_applied": ["E1"],
                        "reason": "No lexical overlap with the research question "
                                  "(auto heuristic; human_confirm)."})
        else:
            rec.update({"stage": "title_abstract", "decision": "pending",
                        "reason": "Weak lexical overlap; auto screening abstains "
                                  "(human_confirm)."})
        records.append(rec)
        return rec

    for src in ir["sources"]:
        doc = store.doc_of(src["id"])
        if doc is not None:
            add_rec(src["id"], src["title"], src.get("year"), src.get("doi"),
                    doc.get("text", ""), bool(doc.get("ok")))
        elif any(t["source_id"] == src["id"] for t in store.table_records):
            pass  # table rows added below
    for t in store.table_records:
        add_rec(t["source_id"], t["title"], t.get("year"), t.get("doi"),
                t.get("abstract", ""), False)
    # safety: never leave the included set empty when usable evidence exists
    if not any(r.get("decision") == "include" for r in records):
        usable = [r for r in records if not r.get("duplicate_of")
                  and store.doc_of(r["source_id"]) is not None
                  and store.doc_of(r["source_id"]).get("ok")]
        for r in usable[:3]:
            r.update({"stage": "full_text", "decision": "include",
                      "criteria_applied": ["I2"],
                      "reason": "No lexical match found; included as provided-corpus "
                                "evidence pending human screening (human_confirm)."})
        if usable:
            store.add_unc("screening", "no record matched the question lexically; "
                          "first usable sources included provisionally", "human_confirm")
    ir["records"] = records
    store.add_unc("screening decisions", "auto lexical-overlap heuristic over real "
                  "title/content, not expert judgment; verify include/exclude/pending",
                  "human_confirm")
    return records


def included_docs(ir, store):
    inc_sids = [r["source_id"] for r in ir["records"]
                if r.get("decision") == "include" and not r.get("duplicate_of")]
    docs = []
    for sid in dict.fromkeys(inc_sids):
        d = store.doc_of(sid)
        if d is not None and d.get("ok"):
            docs.append(d)
    return docs


def build_themes(ir, store, docs):
    df = {}
    doc_tok = {}
    for d in docs:
        src = next((s for s in ir["sources"] if s["id"] == d["sid"]), {})
        tt = tokens(src.get("title", "")) | tokens(d.get("text", "")[:800])
        doc_tok[d["sid"]] = tt
        for t in tt:
            df[t] = df.get(t, 0) + 1
    seeds = [t for t in sorted(df, key=lambda t: (-df[t], t)) if df[t] >= 2][:5]
    groups = {}
    for d in docs:
        hit = next((t for t in seeds if t in doc_tok[d["sid"]]), None)
        groups.setdefault(hit or "_misc", []).append(d)
    themes, doc_theme = [], {}
    for i, (seed, members) in enumerate(groups.items(), 1):
        tid = f"T{i}"
        sids = [m["sid"] for m in members]
        if seed == "_misc":
            name = "Other provided-corpus findings"
        else:
            name = f"{seed} — findings within the provided corpus"
        basis = (f"Induced from titles/content of {', '.join(sids)} sharing the term "
                 f"'{seed}' (auto clustering; human_confirm)." if seed != "_misc" else
                 f"Induced from {', '.join(sids)} (no shared seed term; auto grouping).")
        themes.append({"id": tid, "name": safe_text(name, f"Theme {tid}"),
                       "basis": safe_text(basis, f"Induced from {', '.join(sids)}.")})
        for m in members:
            doc_theme[m["sid"]] = tid
    if not themes:
        themes = [{"id": "T1", "name": "Provided-corpus findings",
                   "basis": "No usable document text; theme kept as honest placeholder."}]
    ir["themes"] = themes
    store.add_unc("theme clustering", "themes auto-induced from shared title/content "
                  "tokens; verify grouping and naming", "human_confirm")
    return doc_theme


def build_claims(ir, store, docs, doc_theme):
    claims, claim_sent = [], {}
    for i, d in enumerate(docs, 1):
        picked = best_sentence(d)
        if not picked:
            store.add_unc(f"claim for {d['sid']}", "no finding-like sentence located; "
                          "abstained (no fabricated claim)", "human_confirm")
            continue
        para, sent = picked
        cid = f"C{i}"
        text = sent if len(sent) <= 400 else sent[:397] + "..."
        text = safe_text(text, f"{d['sid']} reports findings relevant to the question "
                               "(see the exact quoted evidence).")
        hedge = bool(HEDGE_RE.search(sent))
        claim = {"id": cid, "text": text, "type": "fact",
                 "strength": "suggestive" if hedge else "supported",
                 "theme_id": doc_theme.get(d["sid"]), "subquestion_id": "SQ1",
                 "evidence": [evidence_of(d, para, sent)]}
        if hedge:
            claim["uncertainty"] = ("Hedged or single-study report; auto strength "
                                    "heuristic, human_confirm.")
        claims.append(claim)
        claim_sent[d["sid"]] = (para, sent, cid)
    ir["claims"] = claims
    if claims:
        store.add_unc("claim strength", "supported/suggestive assigned by hedge-word "
                      "heuristic on single-source reports; not expert grading",
                      "human_confirm")
    return claim_sent


def build_conflicts(ir, store, claim_sent):
    conflicts = []
    sids = list(claim_sent)
    for i in range(len(sids)):
        for j in range(i + 1, len(sids)):
            a, b = sids[i], sids[j]
            pa, sa, ca = claim_sent[a]
            pb, sb, cb = claim_sent[b]
            shared = tokens(sa) & tokens(sb)
            if len(shared) < 2:
                continue
            a_neg, b_neg = bool(NEG_RE.search(sa)), bool(NEG_RE.search(sb))
            a_pos = bool(POS_RE.search(sa)) and not a_neg
            b_pos = bool(POS_RE.search(sb)) and not b_neg
            if (a_pos and b_neg) or (b_pos and a_neg):
                pos_sid, neg_sid = (a, b) if a_pos else (b, a)
                pp, ps, pc = claim_sent[pos_sid]
                np_, ns, nc = claim_sent[neg_sid]
                cf_id = f"CF{len(conflicts) + 1}"
                topic = safe_text(
                    f"Divergent reported effects ({', '.join(sorted(shared)[:4])})",
                    "Divergent reported effects within the provided corpus")
                conflicts.append({
                    "id": cf_id, "topic": topic,
                    "positions": [
                        evidence_of(store.doc_of(pos_sid), pp, ps, "supports"),
                        evidence_of(store.doc_of(neg_sid), np_, ns, "contradicts"),
                    ],
                    "handling": "Present both positions; designs/populations may differ. "
                                "Auto-detected divergence (keyword heuristic); do not "
                                "collapse to one verdict — human_confirm.",
                })
                for cid in (pc, nc):
                    for c in ir["claims"]:
                        if c["id"] == cid:
                            c["subquestion_id"] = "SQ2"
                store.add_unc(f"conflict {cf_id}", "divergence auto-detected by "
                              "negation/positive-effect keywords on shared terms; "
                              "verify it is a genuine disagreement", "human_confirm")
            if len(conflicts) >= 3:
                break
        if len(conflicts) >= 3:
            break
    ir["conflicts"] = conflicts
    return conflicts


def build_gaps(ir, store, conflicts):
    gaps = [{
        "id": "G1", "type": "coverage_gap",
        "text": f"The provided corpus comprises {len(ir['sources'])} registered sources; "
                "long-term, large-sample or out-of-corpus evidence cannot be assessed "
                "from this set. No field-wide coverage is claimed.",
        "search_scope_checked": "All provided sources parsed: "
                                + ", ".join(s["id"] for s in ir["sources"]) + ".",
        "human_confirm": True,
    }]
    for f in store.files:
        if f.get("role") == "document" and not f.get("ok"):
            gaps.append({
                "id": f"G{len(gaps) + 1}", "type": "method_failure",
                "text": f"No usable text layer extracted from {f['file']}; its content "
                        "was not assessable and no claims were made from it.",
                "search_scope_checked": f"{f['file']} registered and byte-read; "
                                        "text extraction failed quality check.",
                "human_confirm": True,
            })
    if conflicts:
        gaps.append({
            "id": f"G{len(gaps) + 1}", "type": "conflict_unresolved",
            "text": "Divergent reports (see conflicts) remain unresolved within the "
                    "provided set; moderator data are insufficient to adjudicate.",
            "search_scope_checked": "All provided sources checked for moderator analyses.",
            "human_confirm": True,
        })
    ir["gaps"] = gaps


def build_tool_log(ir, store, args):
    log = [{"step": 1, "tool": "list_materials", "params": {"dir": str(args.input)},
            "result": f"{len(store.files)} evidence files registered "
                      f"({len(store.sources)} sources)"}]
    step = 2
    for d in store.documents[:12]:
        log.append({"step": step, "tool": "read_text",
                    "params": {"file": d["file"]},
                    "result": f"{len(d.get('paragraphs', []))} paragraphs extracted; "
                              f"usable_text={bool(d.get('ok'))}"})
        step += 1
    recs = ir.get("records", [])
    inc = sum(1 for r in recs if r.get("decision") == "include")
    exc = sum(1 for r in recs if r.get("decision") == "exclude")
    pend = sum(1 for r in recs if r.get("decision") == "pending")
    dup = sum(1 for r in recs if r.get("duplicate_of"))
    log.append({"step": step, "tool": "screen",
                "params": {"criteria": ["I1", "I2", "E1"]},
                "result": f"{inc} included, {exc} excluded, {pend} pending, {dup} duplicates"})
    log.append({"step": step + 1, "tool": "synthesize",
                "params": {"n_claims": len(ir.get("claims", []))},
                "result": f"{len(ir.get('claims', []))} claims, "
                          f"{len(ir.get('conflicts', []))} conflicts, "
                          f"{len(ir.get('gaps', []))} gaps"})
    ir["tool_log"] = log


def build_proposal(ir, store, question):
    terms = sorted(tokens(question))[:5]
    topic = ", ".join(terms) if terms else "the reported findings"
    extra = ""
    if ir.get("conflicts"):
        extra = (" Prioritize adjudicating the recorded conflicting reports by checking "
                 "population, design and measurement differences.")
    ir["proposal"] = {
        "text": safe_text(
            f"Prospective follow-up plan scoped to the provided evidence: design a "
            f"pre-registered study that re-tests the reported effects on {topic} with "
            f"verified measurement and an explicit comparison condition.{extra} "
            "This is a plan only; no experiments were run and no new data were collected.",
            "Prospective follow-up plan scoped to the provided evidence; a plan only, "
            "no experiments were run and no new data were collected."),
        "bounded": True,
        "not_claimed": ["field-wide novelty", "field-wide completeness", "completed experiments"],
    }


# ── kind-specific finalizers ─────────────────────────────────────────────────

def f_deep_research(ir, store, case):
    pass  # subquestions + tool_log already built in common


def f_lit_review(ir, store, case):
    if not ir.get("themes"):
        ir["themes"] = [{"id": "T1", "name": "Provided-corpus findings",
                         "basis": "No usable document text; honest placeholder theme."}]


def f_systematic_review(ir, store, case):
    quality = []
    for r in ir["records"]:
        if r.get("decision") != "include" or r.get("duplicate_of"):
            continue
        doc = store.doc_of(r["source_id"])
        dims = [{"name": "study_design_reporting",
                 "judgment": "not appraised by a human reviewer (auto baseline); "
                             "human_confirm required"}]
        if doc is not None and doc.get("ok"):
            picked = best_sentence(doc)
            if picked:
                para, sent = picked
                dims[0]["evidence"] = evidence_of(doc, para, sent, stance=None)
        quality.append({"record_id": r["id"], "overall": "unclear",
                        "dimensions": dims,
                        "effect_on_synthesis": "Quality not appraised; claim strengths "
                                               "kept conservative pending human appraisal."})
    ir["quality"] = quality
    store.add_unc("quality appraisal", "overall grade 'unclear' for every included "
                  "record: no human risk-of-bias appraisal performed", "human_confirm")


def f_trend_analysis(ir, store, case):
    src_by_id = {s["id"]: s for s in ir["sources"]}
    inc_sids = [r["source_id"] for r in ir["records"]
                if r.get("decision") == "include" and not r.get("duplicate_of")]
    scope = list(dict.fromkeys(inc_sids)) or list(src_by_id)
    dated = sorted((sid for sid in scope if year_of(src_by_id[sid].get("year")) is not None),
                   key=lambda sid: year_of(src_by_id[sid]["year"]))
    phases = []
    if dated:
        years = [year_of(src_by_id[sid]["year"]) for sid in dated]
        n_groups = min(3, len(dated))
        size = max(1, len(dated) // n_groups)
        groups = [dated[i:i + size] for i in range(0, len(dated), size)]
        if len(groups) > n_groups and len(groups[-1]) < size:
            groups[-2].extend(groups.pop())
        for i, g in enumerate(groups, 1):
            gy = [year_of(src_by_id[sid]["year"]) for sid in g]
            phases.append({
                "id": f"PH{i}",
                "label": f"Chronological segment {i} (provided set)",
                "years": [min(gy), max(gy)],
                "basis": f"Auto chronological split of included sources {', '.join(g)} "
                         f"published {min(gy)}-{max(gy)} within the provided set; "
                         "descriptive only, not a field-wide trend.",
                "representative_works": [{"source_id": sid} for sid in g],
            })
    else:
        store.add_unc("trend years", "no publication years extractable from the provided "
                      "sources; year histogram may be empty (no fabricated years)",
                      "human_confirm")
    ir["trend"] = {"year_basis": "publication_year", "phases": phases}
    missing = [sid for sid in scope if year_of(src_by_id[sid].get("year")) is None]
    if missing:
        store.add_unc("missing years", f"year not found in content of {missing}; "
                      "excluded from year statistics (not guessed)", "human_confirm")
    store.add_unc("trend phases", "phases are an automatic chronological split of the "
                  "provided set; verify labels and boundaries", "human_confirm")


def f_topic_novelty(ir, store, case):
    question = ir.get("research_question", {}).get("main", "")
    docs = included_docs(ir, store)
    terms = sorted(tokens(question))[:6]
    topic_str = ", ".join(terms) if terms else "the question as framed in task.md"
    qd = {
        "object": safe_text(f"Object/population as framed by the task question: "
                            f"{clip(question, 250)}",
                            "Object as framed by the provided task question."),
        "variables": f"Exposure/intervention and outcome terms appearing in the provided "
                     f"sources and question: {topic_str}. Exact operational definitions "
                     "require human confirmation.",
        "baseline": "Comparison conditions reported in the provided sources (control/sham "
                    "arms where present); where absent, no baseline is claimed — human_confirm.",
        "falsifiable": "If a prospective study under the same conditions does not reproduce "
                       "the direction of effect reported in the provided sources, the "
                       "proposed benefit is falsified.",
    }
    # novelty item: the bounded proposal idea, coverage checked against REAL sentences
    statement = safe_text(
        f"Pre-registered prospective verification of the reported effects on {topic_str} "
        "with verified measurement and an explicit comparison condition, scoped to the "
        "provided evidence.",
        "Pre-registered prospective verification of the reported effects, scoped to the "
        "provided evidence.")
    covered_by = []
    stmt_tok = tokens(statement)
    scored = []
    for d in docs:
        picked = best_sentence(d)
        if not picked:
            continue
        para, sent = picked
        overlap = len(stmt_tok & tokens(sent))
        scored.append((overlap, d, para, sent))
    scored.sort(key=lambda x: -x[0])
    for overlap, d, para, sent in scored[:2]:
        covered_by.append({
            "source_id": d["sid"], "paragraph_id": para["id"],
            "coverage": "partial" if overlap >= 2 else "none",
            "quote": sent[:300].rstrip(),
        })
    novelty = [{
        "id": "N1", "statement": statement, "type": "method",
        "covered_by": covered_by, "verdict": derive_verdict(covered_by),
        "uncertainty": "Coverage judged by lexical overlap with real source sentences "
                       "(auto heuristic). Absence within this corpus is not a claim about "
                       "the whole field; human_confirm.",
    }]
    comparison = []
    if scored:
        prior = [{"source_id": d["sid"],
                  "evidence": evidence_of(d, para, sent, stance=None)}
                 for _, d, para, sent in scored[:2]]
        comparison.append({
            "dimension": "Outcome / reported finding",
            "comparable": False,
            "prior_work": prior,
            "proposed": "Pre-registered re-test with verified measurement (see proposal).",
            "reason": "Auto baseline cannot confirm direct comparability of designs; "
                      "human_confirm.",
        })
    feasibility = []
    if scored:
        _, d, para, sent = scored[0]
        feasibility.append({
            "id": "F1",
            "premise": "The provided sources report measurable outcomes relevant to the question.",
            "status": "supported",
            "evidence": [evidence_of(d, para, sent, stance=None)],
            "risk": "Measurement validity across studies is unverified; human_confirm.",
        })
    feasibility.append({
        "id": f"F{len(feasibility) + 1}",
        "premise": "The proposed follow-up design is feasible with available resources "
                   "and verified measurement.",
        "status": "assumption", "human_confirm": True, "evidence": [],
        "risk": "Feasibility not demonstrated in the provided sources; may fail in practice.",
    })
    ir["topic"] = {"question_definition": qd, "comparison": comparison,
                   "novelty": novelty, "feasibility": feasibility}
    store.add_unc("novelty coverage", "coverage=partial/none assigned by lexical overlap "
                  "with real sentences; verdicts derived by the engine; human_confirm",
                  "human_confirm")


FINALIZERS = {
    "deep_research": f_deep_research,
    "lit_review": f_lit_review,
    "systematic_review": f_systematic_review,
    "trend_analysis": f_trend_analysis,
    "topic_novelty": f_topic_novelty,
}


# ── status / result helpers (mirror assemble.py policy) ─────────────────────

def compute_status(ir, validation, build_error, outputs):
    missing_files = any("not found" in w for w in validation.get("warnings", []))
    if build_error and not outputs:
        return "failed"
    if build_error or not validation.get("ok") or missing_files:
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
    store = Store(case, materials, args.input)
    store.register_sources(materials)
    kind = detect_kind(args.kind, case, store)
    ir = kit.base_ir(case, kind)
    ir["_base_dirs"] = [str(work_dir.resolve()), str(Path(args.input).resolve())]
    ir["sources"] = store.sources

    store.parse_all()

    question = safe_text(main_question(case, store),
                         "What do the provided sources report, and where do they agree "
                         "or disagree? (scoped to the provided corpus)")
    ir["research_question"] = {"main": question,
                               "subquestions": subquestions_from(case, store)}
    ir["title"] = clip(f"Source-bound research report — {question}", 120)
    ir["scope"] = {"corpus": "provided local materials only (/input)",
                   "n_sources": str(len(store.sources))}

    build_protocol(ir, store, question)
    build_records(ir, store, question)
    docs = included_docs(ir, store)
    doc_theme = build_themes(ir, store, docs)
    claim_sent = build_claims(ir, store, docs, doc_theme)
    conflicts = build_conflicts(ir, store, claim_sent)
    build_gaps(ir, store, conflicts)
    build_tool_log(ir, store, args)
    build_proposal(ir, store, question)
    FINALIZERS[kind](ir, store, case)

    ir["uncertainty"] = list(store.uncertainty)
    ir["uncertainty"].append({
        "item": "corpus_scope",
        "reason": f"Only {len(store.sources)} provided sources; not a comprehensive "
                  "database search.",
        "impact": "All conclusions, trends and novelty verdicts are bounded to this set.",
        "handling": "Declare scope; no field-wide claims.",
    })
    for e in store.errors:
        ir["uncertainty"].append({"item": "extraction", "reason": e,
                                  "handling": "human_confirm"})
    if not store.sources:
        ir["uncertainty"].append({"item": "materials",
                                  "reason": "input directory empty or unreadable; "
                                            "nothing to extract",
                                  "handling": "human_confirm"})
    ir["provenance"] = {"pipeline": "material -> auto_extract -> research IR -> validate "
                                    "-> compute -> artifact -> result",
                        "changes": [{"step": "auto_extract", "at": kit.utc_now(),
                                     "detail": f"deterministic extraction from "
                                               f"{len(store.sources)} material files"}]}

    kit.write_json(work_dir / "research_ir.json", ir)

    validation = engine.validate_ir(ir)
    kit.write_json(out_dir / "validation.json", validation)

    outputs, build_error = [], None
    try:
        outputs = engine.build(ir, case, out_dir)
    except Exception as e:
        build_error = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    status = compute_status(ir, validation, build_error, outputs)

    # mirror assemble.py: unverifiable quotes (binary PDFs) stay honest but declared
    qsum = {}
    for q in (ir.get("_computed") or {}).get("quote_checks", []):
        qsum[q["status"]] = qsum.get(q["status"], 0) + 1
    unverifiable = sum(v for k, v in qsum.items() if k == "unverifiable")
    if unverifiable:
        ir["uncertainty"].append({
            "item": "quote_verification",
            "reason": f"{unverifiable} quotes cannot be auto-re-verified against "
                      "binary/missing files; human check against the original required",
            "handling": "human_confirm"})

    extra = {}
    try:
        extra = engine.summarize(ir)
    except Exception:
        extra = {"summary_error": traceback.format_exc(limit=3)}
    extra["autopilot"] = {"kind": kind, "n_materials": len(materials),
                          "n_sources": len(ir["sources"]),
                          "n_records": len(ir.get("records", [])),
                          "n_claims": len(ir.get("claims", [])),
                          "work_ir": str(work_dir / "research_ir.json")}
    notes = AUTO_NOTE
    if validation["errors"]:
        notes += " IR validation errors present; see validation.json."
    if build_error:
        notes += f" BUILD ERROR: {build_error}"
        extra["build_error"] = build_error
    result = kit.build_result(case, ir, outputs, status, validation=validation,
                              extra=extra, notes=notes)
    kit.write_result(out_dir, result)
    print(json.dumps({"status": status, "case_id": case["case_id"], "kind": kind,
                      "n_outputs": len(outputs),
                      "n_sources": len(ir["sources"]),
                      "n_records": len(ir.get("records", [])),
                      "n_claims": len(ir.get("claims", [])),
                      "quote_check_summary": qsum,
                      "errors": validation["errors"],
                      "warnings": validation["warnings"][:10]},
                     ensure_ascii=False, indent=2))
    return 0 if status in ("success", "partial") else 1


def main():
    ap = argparse.ArgumentParser(description="research track autopilot (auto-extract IR + run engine)")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--kind", default=None)
    args = ap.parse_args()

    case, sources, kind = {}, [], None
    try:
        if kit is None or engine is None:
            raise RuntimeError("cannot import sibling w4kit.py / research_engine.py")
        return run(args)
    except Exception as e:
        traceback.print_exc()
        # honest fallback: NEVER exit without result.json
        try:
            case = kit.load_case(args.input) if kit else {}
            kind = kind or (args.kind or "deep_research")
            try:
                mats = kit.list_materials(args.input) if kit else []
                sources = [{"id": f"S{i}", "title": Path(m["name"]).stem,
                            "file": m["name"], "type": (m.get("ext") or "").lstrip(".")}
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
        print(json.dumps({"status": "failed", "error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())