"""auto_write.py — deterministic "autopilot" entry point for the week4 WRITING track
(writekit / assemble_write.py architecture).

Reads the ACTUAL organizer-provided local materials under --input, auto-extracts
a complete writing IR (sources / sections / claims+evidence / citations / numbers /
glossary / revisions + kind-specific domain fields: chapter_plan for thesis_longdoc,
aligned pairs for translation, nodes/relations for mind_map, tasks for
writing_benchmark), then runs the SAME validate+build path as assemble_write.py
(writekit.validate_writing / benchkit.validate_benchmark / mindmap node check ->
docxkit.write_manuscript / mindmap.render / benchkit.build_benchmark ->
figkit.build_result / write_result) and writes an honest result.json preserving
every output_contract key + case_id. Stdlib only; additive — does not modify the
engine or kits.

Usage:
  PYTHONDONTWRITEBYTECODE=1 python auto_write.py --input /input --out /app/output \
      [--work /app/work] [--kind KIND]

Design rules (mirrors engines/search/auto_search.py):
  * Never fabricate: every section paragraph / claim / quote / number / citation is
    an EXACT excerpt of real file content with a locator.
  * Judgment-heavy fields (claim strength, chapter word budgets, mind-map relation
    types, benchmark task design, translation renderings) get deterministic,
    evidence-grounded heuristic defaults and are flagged human_confirm in
    uncertainty[] (=> honest status "partial"). Translation targets are NEVER
    machine-invented: missing target -> pending_human + human_confirm.
  * Defensive extraction: a bad/missing file becomes an honest gap, never a crash.
  * The WHOLE pipeline is wrapped: on ANY exception an honest result.json is still
    written (status partial/failed) with contract keys + case_id + sources + error.
  * After this baseline runs, the agent may refine /app/work/writing_ir.json within
    budget and re-run assemble_write.py to improve judgment fields.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
import zipfile
import zlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    import figkit as kit
    import writekit
except Exception:  # catastrophic import failure -> emergency writer below
    kit = None
    writekit = None

AUTO_NOTE = ("auto_write autopilot: deterministic extraction from ACTUAL local "
             "materials + existing writekit/docxkit/mindmap/benchkit build path "
             "(same as assemble_write.py); no fabricated content/quotes/citations. "
             "Judgment fields use documented evidence-grounded heuristics flagged "
             "human_confirm; refine work/writing_ir.json and re-run "
             "assemble_write.py to improve.")

KIND_ALIASES = {"writing": None, "mindmap": "mind_map", "mind_map": "mind_map",
                "bench": "writing_benchmark", "benchmark": "writing_benchmark",
                "thesis": "thesis_longdoc", "thesis_longdoc": "thesis_longdoc",
                "translate": "translation", "translation": "translation",
                "sci_translation": "sci_translation"}

KIND_KEYWORDS = [
    ("mind_map", ["思维导图", "mind map", "mindmap", "mind-map"]),
    ("translation", ["翻译", "双语", "translation", "bilingual", "translate"]),
    ("thesis_longdoc", ["学位论文", "长文档", "thesis", "long document", "longdoc",
                        "chapter", "章节"]),
    ("writing_benchmark", ["benchmark", "评测", "评分", "rubric", "eval tool",
                           "测评"]),
    ("reviewer_response", ["审稿", "reviewer", "response letter", "rebuttal"]),
    ("grant_proposal", ["基金", "grant", "proposal", "申请书"]),
    ("research_plan", ["研究计划", "research plan", "开题"]),
    ("results_discussion", ["results", "discussion", "结果与讨论"]),
    ("paper_writing", ["论文", "paper", "manuscript", "写作"]),
]

KNOWN_HEADINGS = {
    "abstract", "introduction", "background", "methods", "method", "materials",
    "materials and methods", "methodology", "results", "discussion", "conclusion",
    "conclusions", "limitations", "references", "related work", "experiments",
    "experiment", "evaluation", "appendix", "acknowledgements", "acknowledgments",
    "title", "author", "摘要", "引言", "背景", "方法", "结果", "讨论", "结论",
    "局限性", "参考文献", "致谢", "附录", "相关工作", "实验",
}

REF_SECTION_RE = re.compile(r"^(references|reference list|参考文献)\s*$", re.I)


# ── small helpers ────────────────────────────────────────────────────────────

def clip(s, n=600):
    s = str(s)
    return s if len(s) <= n else s[:n] + "..."


def sentences_of(text):
    parts = re.split(r"(?<=[.!?。！？])\s+", str(text or ""))
    return [p.strip() for p in parts if p.strip()]


def nums_in(text):
    return re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(text or ""))


# ── text / PDF / DOCX reading (stdlib, defensive) ────────────────────────────

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


def docx_text(data: bytes) -> str:
    """Stdlib DOCX salvage: word/document.xml <w:t> runs, paragraph breaks."""
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    except Exception:
        return data.decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml, re.S)
    out = []
    for t in texts:
        t = (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'"))
        out.append(t)
    joined = "".join(out)
    return joined if joined.strip() else data.decode("utf-8", errors="replace")


def read_material_text(path):
    data = Path(path).read_bytes()
    low = str(path).lower()
    if low.endswith(".pdf") or data[:5] == b"%PDF-":
        return pdf_text(data)
    if low.endswith(".docx") or data[:2] == b"PK":
        return docx_text(data)
    return data.decode("utf-8", errors="replace")


# ── document structure parsing ───────────────────────────────────────────────

HEAD_PATTERNS = [
    re.compile(r"^(#{1,6})\s+(.+?)\s*$"),
    re.compile(r"^(.{1,60}?)\s*\((Sec\.?\s*\d+[^)]*)\)\s*[:：]\s*(.*)$"),
    re.compile(r"^(Sec\.?\s*\d+)\s*[:：]\s*(.*)$"),
    re.compile(r"^(第[一二三四五六七八九十百\d]+[章节部分])\s*[:：]?\s*(.*)$"),
    re.compile(r"^([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff /&-]{0,50})\s*[:：]\s*(.*)$"),
]


def heading_match(ln):
    """Return (heading, locator_tag, inline_body) if line looks like a heading."""
    s = ln.strip()
    if not s:
        return None
    m = HEAD_PATTERNS[0].match(s)
    if m:
        return (m.group(2).strip(), f"L-level{len(m.group(1))}", "")
    for pat in HEAD_PATTERNS[1:4]:
        m = pat.match(s)
        if m:
            return (m.group(1).strip(), m.group(1).strip(), m.group(m.lastindex).strip()
                    if m.lastindex and m.lastindex >= 2 else "")
    m = HEAD_PATTERNS[4].match(s)
    if m:
        head = m.group(1).strip()
        body = m.group(2).strip()
        hl = head.lower()
        if hl in KNOWN_HEADINGS or (len(head) <= 40 and body and
                                    (hl.split(" /")[0] in KNOWN_HEADINGS or
                                     re.match(r"^(title|author|标题|作者)$", hl))):
            return (head, head, body)
        if hl in ("title", "author", "标题", "作者"):
            return (head, head, body)
    return None


def parse_document(text, name):
    """Split real material text into title + sections + paragraphs with EXACT
    line locators. Paragraph text is always a verbatim excerpt of the file."""
    lines = text.splitlines()
    title = None
    sections = []
    cur = None
    buf = []
    buf_start = None
    pid = [0]

    def flush():
        nonlocal buf, buf_start
        body = "\n".join(buf).strip()
        if body and cur is not None:
            pid[0] += 1
            cur["paragraphs"].append({
                "id": f"p{pid[0]}", "text": body,
                "locator": f"{name} L{buf_start}-L{buf_start + len(buf) - 1}"})
        buf, buf_start = [], None

    def new_section(heading, tag, lineno):
        nonlocal cur
        flush()
        cur = {"id": f"s{len(sections) + 1}", "heading": heading,
               "locator": f"{name} {tag} (L{lineno})", "paragraphs": []}
        sections.append(cur)

    for i, ln in enumerate(lines, 1):
        hm = heading_match(ln)
        if hm:
            head, tag, body = hm
            if head.lower() in ("title", "标题") and title is None:
                title = body or None
                continue
            if head.lower() in ("author", "作者"):
                if cur is None:
                    new_section("Front matter", "front", i)
                if body:
                    buf.append(ln)
                    if buf_start is None:
                        buf_start = i
                continue
            new_section(head, tag, i)
            if body:
                buf.append(body)
                buf_start = i
            continue
        if not ln.strip():
            flush()
            continue
        if cur is None:
            new_section("Overview", "overview", i)
        if buf_start is None:
            buf_start = i
        buf.append(ln)
    flush()
    if title is None:
        for s in sections:
            if s["heading"].lower() not in ("overview", "front matter"):
                title = s["heading"]
                break
    if title is None and lines:
        first = next((l.strip() for l in lines if l.strip()), name)
        title = clip(re.sub(r"^#+\s*", "", first), 120)
    return {"title": title, "sections": sections}


# ── material store ───────────────────────────────────────────────────────────

class Store:
    def __init__(self, case, materials):
        self.case = case
        self.sources = []
        self.files = []
        self.docs = []          # parsed text documents {sid,name,text,title,sections}
        self.tables = []        # {sid,name,rows,raw_lines}
        self.json_data = {}     # sid -> parsed json
        self.provided_ir = None
        self.citations = []
        self.numbers = []
        self.glossary = []
        self.uncertainty = []
        self.errors = []
        self._cid = 0

    def add_unc(self, item, reason, handling="human_confirm"):
        self.uncertainty.append({"item": item, "reason": reason, "handling": handling})

    def register_sources(self, materials):
        for i, m in enumerate(materials, 1):
            sid = f"S{i}"
            ext = (m.get("ext") or "").lstrip(".").lower() or "file"
            try:
                ver = kit.sha256_file(m["path"])[:12]
            except Exception:
                ver = "unknown"
            self.sources.append({"id": sid, "locator": m["name"], "path": m["path"],
                                 "kind": "table" if ext in ("csv", "tsv") else
                                         ("text" if ext in ("md", "txt", "tex") else ext),
                                 "version": ver, "values": []})
            self.files.append({"sid": sid, "path": m["path"], "name": m["name"],
                               "ext": ext})

    def parse_all(self):
        for f in self.files:
            try:
                self.parse_file(f)
            except Exception as e:
                self.errors.append(f"{f['name']}: {type(e).__name__}: {e}")
                self.add_unc(f["name"], f"extraction failed: {e}; file registered but not parsed")

    def parse_file(self, f):
        name, ext, sid = f["name"], f["ext"], f["sid"]
        low = name.lower()
        if low in ("case.json", "task.md") or low.startswith("readme"):
            f["role"] = "task"
            if ext == "json":
                try:
                    self.json_data[sid] = kit.load_json(f["path"])
                except Exception:
                    pass
            return
        if ext in ("csv", "tsv", "tab"):
            rows = kit.read_table(f["path"])
            raw_lines = read_material_text(f["path"]).splitlines()
            self.tables.append({"sid": sid, "name": name, "rows": rows,
                                "raw_lines": raw_lines})
            self.declare_table_numbers(sid, name, rows, raw_lines)
            self.extract_glossary_table(sid, rows)
            return
        if ext == "json":
            try:
                data = kit.load_json(f["path"])
            except Exception as e:
                self.add_unc(name, f"JSON unreadable: {e}")
                return
            self.json_data[sid] = data
            if isinstance(data, dict) and data.get("kind") and any(
                    k in data for k in ("sections", "nodes", "tasks", "latex",
                                        "claims", "segments", "references")):
                self.provided_ir = data
                self.add_unc(name, "input ships a writing-IR fragment; its fields are "
                             "merged over the auto-extracted baseline (provided values win)",
                             "note")
            elif isinstance(data, dict):
                self.extract_glossary_json(sid, data)
            return
        text = read_material_text(f["path"])
        f["text"] = text
        doc = parse_document(text, name)
        # namespace section/paragraph ids per source so multi-file IRs stay unique
        for s in doc["sections"]:
            s["id"] = f"{sid}_{s['id']}"
            for p in s["paragraphs"]:
                p["id"] = f"{sid}_{p['id']}"
        doc.update({"sid": sid, "name": name, "text": text})
        self.docs.append(doc)
        self.declare_text_numbers(sid, name, text)
        self.extract_citations(sid, name, text)
        self.extract_glossary_text(sid, text)

    # -- numbers (declare EVERY numeric token actually present, with locator) --
    def declare_text_numbers(self, sid, name, text):
        seen = set()
        for i, ln in enumerate(text.splitlines(), 1):
            for tok in nums_in(ln):
                if tok in seen:
                    continue
                seen.add(tok)
                self.numbers.append({"value": tok, "source": sid,
                                     "locator": f"{name} L{i}"})
        src = next(s for s in self.sources if s["id"] == sid)
        src["values"] = sorted({float(t) for t in seen
                                if re.match(r"^[-+]?\d+(\.\d+)?$", t)})

    def declare_table_numbers(self, sid, name, rows, raw_lines):
        seen = set()
        for ri, r in enumerate(rows, 2):
            for k, v in r.items():
                for tok in nums_in(v):
                    if tok in seen:
                        continue
                    seen.add(tok)
                    self.numbers.append({"value": tok, "source": sid,
                                         "locator": f"{name} row{ri} col '{k}'"})
        src = next(s for s in self.sources if s["id"] == sid)
        src["values"] = sorted({float(t) for t in seen
                                if re.match(r"^[-+]?\d+(\.\d+)?$", t)})

    # -- citations (only from REAL reference text; never invented) -------------
    def add_citation(self, fields, sid, locator, raw):
        self._cid += 1
        cid = fields.get("key") or f"ref{self._cid}"
        if any(c["id"] == cid for c in self.citations):
            return None
        c = {"id": cid, "source": sid, "locator": locator}
        for k in ("authors", "year", "title", "journal", "doi"):
            if fields.get(k):
                c[k] = fields[k]
        c["raw"] = clip(raw, 300)
        self.citations.append(c)
        return c

    def extract_citations(self, sid, name, text):
        found = []
        # inline "(Ref1: Authors, year, Journal, doi ...)" style
        for m in re.finditer(r"\(?(Ref\s*\d+)\s*[:：]\s*([^)\n]+)\)?", text):
            found.append((m.group(1).replace(" ", "").lower(), m.group(2).strip(),
                          f"{name} L{text[:m.start()].count(chr(10)) + 1}"))
        # numbered reference-list entries
        ref_zone = text
        rm = re.search(r"(?:References|Reference list|参考文献)\s*\n(.*)", text, re.S | re.I)
        if rm:
            ref_zone = rm.group(1)
        for m in re.finditer(r"^\s*\[?(\d+)[\].)]\s+(.{15,})$", ref_zone, re.M):
            found.append((f"ref{m.group(1)}", m.group(2).strip(),
                          f"{name} reference [{m.group(1)}]"))
        for key, entry, locator in found:
            doi = re.search(r"10\.\d{4,9}/[^\s,;)]+", entry)
            year = re.search(r"\b(19|20)\d{2}\b", entry)
            tm = re.search(r"[\"“](.+?)[\"”]", entry)
            title = tm.group(1) if tm else None
            authors = None
            journal = None
            parts = [p.strip() for p in entry.split(",")]
            if year:
                yi = next((i for i, p in enumerate(parts)
                           if re.search(r"\b(19|20)\d{2}\b", p)), None)
                if yi is not None:
                    authors = ", ".join(parts[:yi]) or None
                    rest = parts[yi + 1:]
                    if rest:
                        journal = re.sub(r"\s*doi:?\s*10\.\S+", "", rest[0],
                                         flags=re.I).strip() or None
                    if title is None and len(rest) > 1:
                        title = rest[-1] if doi else None
            if title is None:
                title = clip(re.sub(r"\s*doi:?\s*10\.\S+", "", entry, flags=re.I), 200)
            self.add_citation({"key": key, "authors": authors,
                               "year": year.group(0) if year else None,
                               "title": title, "journal": journal,
                               "doi": doi.group(0) if doi else None},
                              sid, locator, entry)
        if self.citations:
            self.add_unc("citation metadata",
                         "authors/year/title/journal parsed heuristically from real "
                         "reference text; verify each field against the source")

    # -- glossary (only bilingual evidence actually present in materials) ------
    def extract_glossary_table(self, sid, rows):
        for r in rows:
            rl = {str(k).lower(): v for k, v in r.items()}
            term = rl.get("term") or rl.get("en") or rl.get("source_term")
            render = rl.get("render") or rl.get("translation") or rl.get("zh") or rl.get("target")
            if term and render:
                self._add_gloss(term, render, sid, "glossary table row")

    def extract_glossary_json(self, sid, data):
        items = data.get("glossary") or data.get("terms") or []
        if isinstance(items, list):
            for g in items:
                if isinstance(g, dict) and g.get("term") and (g.get("render") or g.get("translation")):
                    self._add_gloss(g["term"], g.get("render") or g.get("translation"),
                                    sid, "glossary JSON entry")

    def extract_glossary_text(self, sid, text):
        for m in re.finditer(r"([A-Za-z][A-Za-z -]{2,30})\s*[（(]([\u4e00-\u9fff]{2,20})[)）]", text):
            self._add_gloss(m.group(1).strip(), m.group(2), sid,
                            f"inline bilingual parenthetical L{text[:m.start()].count(chr(10)) + 1}")

    def _add_gloss(self, term, render, sid, locator):
        for g in self.glossary:
            if g["term"] == term:
                if g["render"] != render:
                    self.add_unc(f"term '{term}'",
                                 f"conflicting renders in materials ('{g['render']}' vs "
                                 f"'{render}'); first kept, human must lock one")
                return
        self.glossary.append({"term": term, "render": render, "source": sid,
                              "locator": locator})


# ── kind detection ───────────────────────────────────────────────────────────

def skill_default_kind():
    skill = SCRIPT_DIR / "SKILL.md"
    if skill.exists():
        try:
            head = skill.read_text(encoding="utf-8", errors="replace")[:3000]
            m = re.search(r"kind=([a-z_]+)", head)
            if m and (writekit is None or m.group(1) in writekit.KINDS):
                return m.group(1)
        except Exception:
            pass
    return "paper_writing"


def detect_kind(args_kind, case, store):
    default = skill_default_kind()
    if args_kind:
        k = args_kind.strip().lower().replace("-", "_")
        k = KIND_ALIASES.get(k, k)
        if k and (writekit is None or k in writekit.KINDS):
            return k
    raw_kind = (case.get("raw") or {}).get("kind")
    if isinstance(raw_kind, str):
        k = KIND_ALIASES.get(raw_kind.lower().replace("-", "_"), raw_kind.lower())
        if k and (writekit is None or k in writekit.KINDS):
            return k
    # the package's own skill kind (SKILL.md frontmatter) outranks keyword guesses
    if default != "paper_writing":
        return default
    blob = ((case.get("task_md") or "") + " " +
            json.dumps(case.get("raw") or {}, ensure_ascii=False) + " " +
            " ".join(f["name"] for f in store.files)).lower()
    best, best_score = None, 0
    for kind, kws in KIND_KEYWORDS:
        score = sum(1 for kw in kws if kw.lower() in blob)
        if score > best_score:
            best, best_score = kind, score
    if best and best_score >= 2:
        return best
    return default


# ── shared IR pieces ─────────────────────────────────────────────────────────

def build_claims(store, doc, start=0, max_per_para=3):
    """Claims are EXACT sentences of the material, bound to source+locator."""
    claims = []
    for s in doc["sections"]:
        if REF_SECTION_RE.match(s["heading"]):
            continue
        for p in s["paragraphs"]:
            taken = 0
            for sent in sentences_of(p["text"]):
                if taken >= max_per_para:
                    break
                if len(sent) < 25 and not nums_in(sent):
                    continue
                if sent not in doc["text"]:
                    continue  # never emit a non-verbatim quote
                cid = f"c{start + len(claims) + 1}"
                cite_ids = []
                for m in re.finditer(r"\[(\d+)\]|\bRef\s*(\d+)\b|\\cite\{([^}]+)\}", sent):
                    key = (f"ref{m.group(1) or m.group(2)}" if (m.group(1) or m.group(2))
                           else m.group(3))
                    for k in str(key).split(","):
                        k = k.strip()
                        if any(c["id"] == k for c in store.citations) and k not in cite_ids:
                            cite_ids.append(k)
                claims.append({
                    "id": cid, "text": sent, "type": "fact",
                    "evidence": [{"source": doc["sid"],
                                  "locator": f"{s['locator']} / {p['id']}",
                                  "quote": sent, "strength": "supported",
                                  "supports": "full"}],
                    "citation_ids": cite_ids})
                p.setdefault("claim_ids", []).append(cid)
                taken += 1
    return claims


def ir_sections(store, doc, claims_by_para):
    out = []
    for s in doc["sections"]:
        if REF_SECTION_RE.match(s["heading"]):
            continue
        paras = []
        for p in s["paragraphs"]:
            paras.append({"id": p["id"], "text": p["text"],
                          "claims": claims_by_para.get(p["id"], []),
                          "source": doc["sid"], "locator": p["locator"]})
        out.append({"id": s["id"], "level": 1, "heading": s["heading"],
                    "role": s["heading"], "paragraphs": paras,
                    "source": doc["sid"], "locator": s["locator"]})
    return out


def table_sections(store):
    """Verbatim table content as an editable section (no invented prose)."""
    out = []
    for t in store.tables:
        if not t["raw_lines"]:
            continue
        paras = [{"id": f"tp{i}", "text": ln, "claims": [], "source": t["sid"],
                  "locator": f"{t['name']} L{i}"}
                 for i, ln in enumerate(t["raw_lines"], 1) if ln.strip()]
        out.append({"id": f"tbl{len(out) + 1}", "level": 1,
                    "heading": f"Data ({t['name']})", "role": f"Data ({t['name']})",
                    "paragraphs": paras, "source": t["sid"],
                    "locator": t["name"]})
    return out


def base_write_ir(case, kind, store, title):
    ir = {"ir_version": "1.0", "case_id": case.get("case_id"), "kind": kind,
          "title": title or case.get("raw", {}).get("title") or kind,
          "audience": (case.get("raw") or {}).get("audience", "peers"),
          "genre": (case.get("raw") or {}).get("genre", kind),
          "sources": store.sources, "citations": store.citations,
          "numbers": store.numbers, "glossary": store.glossary,
          "claims": [], "sections": [], "revisions": [],
          "required_sections": (case.get("raw") or {}).get("required_sections", []),
          "declarations": [], "uncertainty": list(store.uncertainty),
          "provenance": {"pipeline": "material -> auto_extract -> writing IR -> "
                                     "validate -> editable doc -> check/export",
                         "skill_version": getattr(writekit, "SKILL_VERSION", "1.0.0"),
                         "changes": [{"step": "auto_extract",
                                      "at": kit.utc_now() if kit else "",
                                      "detail": f"deterministic extraction from "
                                                f"{len(store.sources)} material files"}]}}
    return ir


def merge_provided_ir(ir, store):
    """If the input ships an IR fragment, its real fields win over the baseline."""
    prov = store.provided_ir
    if not isinstance(prov, dict):
        return
    for k, v in prov.items():
        if k in ("sources", "case_id", "ir_version"):
            continue
        ir[k] = v
    have = {s["id"] for s in ir["sources"]}
    for s in prov.get("sources", []):
        if isinstance(s, dict) and s.get("id") and s["id"] not in have:
            ir["sources"].append(s)
            have.add(s["id"])


# ── per-kind finalizers ──────────────────────────────────────────────────────

def f_generic(ir, store, case):
    all_claims, by_para = [], {}
    for doc in store.docs:
        cs = build_claims(store, doc, start=len(all_claims))
        all_claims.extend(cs)
        for s in doc["sections"]:
            for p in s["paragraphs"]:
                by_para[p["id"]] = p.get("claim_ids", [])
        ir["sections"].extend(ir_sections(store, doc, by_para))
    ir["sections"].extend(table_sections(store))
    ir["claims"] = all_claims
    if all_claims:
        ir["uncertainty"].append({
            "item": "claim strength/type",
            "reason": "strength='supported'/type='fact' are autopilot defaults for "
                      "verbatim source sentences; expert must confirm strength "
                      "(established/supported/hypothesized/uncertain/correlational)",
            "handling": "human_confirm"})
    if not ir["sections"]:
        ir["uncertainty"].append({"item": "sections",
                                  "reason": "no readable text material found; nothing "
                                            "to write (cannot fabricate content)",
                                  "handling": "human_confirm"})
    ir["exports"] = [{"format": "md"}, {"format": "docx"}]


def f_thesis(ir, store, case):
    f_generic(ir, store, case)
    plan = []
    for s in ir["sections"]:
        words = sum(len(p["text"].split()) + len(re.findall(r"[\u4e00-\u9fff]", p["text"]))
                    for p in s["paragraphs"])
        question = None
        for p in s["paragraphs"]:
            q = next((x for x in sentences_of(p["text"]) if "?" in x or "？" in x), None)
            if q:
                question = q
                break
        plan.append({"id": s["id"], "heading": s["heading"],
                     "question": question or "(chapter question not explicit in material; "
                                             "human must set)",
                     "required_evidence": [c for p in s["paragraphs"] for c in p["claims"]],
                     "word_budget": words,
                     "source": s.get("source"), "locator": s.get("locator")})
    ir["chapter_plan"] = plan
    ir["uncertainty"].append({
        "item": "chapter_plan word_budget/question",
        "reason": "word_budget = observed source word/char counts (not a negotiated "
                  "budget); questions taken from material interrogatives where present; "
                  "outline/argument alignment requires human confirmation",
        "handling": "human_confirm"})
    concl = [s for s in ir["sections"]
             if re.search(r"conclusion|结论|discussion|讨论", s["heading"], re.I)]
    ir["conclusion_registry"] = [{"section": s["id"],
                                  "claim_ids": [c for p in s["paragraphs"] for c in p["claims"]]}
                                 for s in concl]


def f_translation(ir, store, case):
    f_generic(ir, store, case)
    pairs = []
    for s in ir["sections"]:
        for p in s["paragraphs"]:
            for sent in sentences_of(p["text"]):
                if sent not in " ".join(d["text"] for d in store.docs):
                    continue
                pairs.append({"id": f"pair{len(pairs) + 1}",
                              "source_text": sent, "target_text": None,
                              "status": "pending_human_translation",
                              "source": p["source"],
                              "locator": p.get("locator")})
    ir["pairs"] = pairs
    ir["uncertainty"].append({
        "item": "translation targets",
        "reason": "autopilot NEVER machine-invents translations: target_text=null "
                  "until a human/agent translator fills it; source sentences are "
                  "verbatim and aligned at sentence level; glossary holds only "
                  "renderings actually evidenced in the materials",
        "handling": "human_confirm"})
    if not store.glossary:
        ir["uncertainty"].append({
            "item": "glossary",
            "reason": "no bilingual term evidence found in materials; terminology "
                      "must be locked by a human translator before delivery",
            "handling": "human_confirm"})
    # bilingual editable deliverable: source paragraph + explicit pending marker
    for s in ir["sections"]:
        for p in s["paragraphs"]:
            p["text"] = p["text"] + "\n[译文待人工确认 / target pending human translation]"


def f_mindmap(ir, store, case):
    nodes, relations = [], []
    docs = store.docs
    title = ir.get("title") or (docs[0]["title"] if docs else "mind map")
    root_sid = docs[0]["sid"] if docs else (store.sources[0]["id"] if store.sources else None)
    if root_sid is None:
        ir["uncertainty"].append({"item": "nodes",
                                  "reason": "no readable material; cannot extract nodes "
                                            "(never invented)", "handling": "human_confirm"})
        ir["nodes"], ir["relations"] = [], []
        ir["exports"] = [{"format": "svg"}, {"format": "png"}, {"format": "pdf"}]
        return
    nodes.append({"id": "root", "label": clip(title, 60), "source": root_sid,
                  "source_locator": docs[0]["name"] + " Title" if docs else "case"})
    sec_nodes = {}
    for doc in docs:
        for s in doc["sections"]:
            if REF_SECTION_RE.match(s["heading"]):
                continue
            nid = f"{doc['sid']}_{s['id']}"
            sec_nodes[nid] = s
            nodes.append({"id": nid, "parent": "root", "label": clip(s["heading"], 48),
                          "source": doc["sid"], "source_locator": s["locator"],
                          "evidence": s["locator"]})
            for p in s["paragraphs"][:4]:
                sent = sentences_of(p["text"])[0] if sentences_of(p["text"]) else p["text"]
                label = sent[:48]
                if label not in doc["text"]:
                    label = p["text"][:48]
                pid = f"{nid}_{p['id']}"
                nodes.append({"id": pid, "parent": nid, "label": label,
                              "source": doc["sid"], "source_locator": p["locator"],
                              "evidence": p["id"]})
    # evidence-grounded relation heuristic: sections sharing numeric tokens
    def numset(s):
        return {t for p in s["paragraphs"] for t in nums_in(p["text"])
                if not re.match(r"^(19|20)\d{2}$", t)}
    items = list(sec_nodes.items())
    for i, (nid_a, sa) in enumerate(items):
        for nid_b, sb in items[i + 1:]:
            shared = numset(sa) & numset(sb)
            if len(shared) >= 2:
                relations.append({"id": f"e{len(relations) + 1}", "from": nid_a,
                                  "to": nid_b, "type": "support",
                                  "source": sa.get("source") or root_sid,
                                  "source_locator": f"{sa['locator']} + {sb['locator']} "
                                                    f"(shared values {sorted(shared)[:5]})"})
    ir["nodes"], ir["relations"] = nodes, relations
    ir["exports"] = [{"format": "svg"}, {"format": "png"}, {"format": "pdf"}]
    ir["uncertainty"].append({
        "item": "node labels / relation types",
        "reason": "labels are verbatim excerpts; 'support' relations inferred from "
                  ">=2 shared numeric tokens between sections (lexical heuristic, "
                  "not a sourced causal claim); human_confirm all relations",
        "handling": "human_confirm"})


def f_benchmark(ir, store, case):
    f_generic(ir, store, case)
    tasks = []
    for s in ir["sections"]:
        toks = sorted({t for p in s["paragraphs"] for t in nums_in(p["text"])})
        body = "\n".join(p["text"] for p in s["paragraphs"])
        if not body.strip():
            continue
        tasks.append({
            "id": f"t{len(tasks) + 1}",
            "instruction": f"Write a paragraph reproducing the key points of section "
                           f"'{s['heading']}' from the provided material, keeping all "
                           f"reported values exact.",
            "input_material": s.get("locator") or s["heading"],
            "required_points": toks or [clip(sentences_of(body)[0], 60)],
            "forbidden": ["causes", "proves mechanism"],
            "acceptable_variants": ["sentence structure", "order of mention"],
            "reference_answer": body,
            "anchors": [{"criterion": f"reported value '{t}' present",
                         "observable": f"string '{t}' in text"} for t in toks[:8]] or
                       [{"criterion": "key sentence reproduced",
                         "observable": f"string '{clip(sentences_of(body)[0], 40)}' in text"}],
            "source": s.get("source"), "locator": s.get("locator")})
    ir["tasks"] = tasks
    ir["uncertainty"].append({
        "item": "benchmark task design",
        "reason": "tasks/required_points/anchors auto-derived from real section text "
                  "(reference_answer is the verbatim source); difficulty, forbidden "
                  "errors and rubric weighting need human confirmation",
        "handling": "human_confirm"})
    if not tasks:
        ir["uncertainty"].append({"item": "tasks",
                                  "reason": "no material sections to derive decidable tasks from",
                                  "handling": "human_confirm"})


FINALIZERS = {"thesis_longdoc": f_thesis, "translation": f_translation,
              "sci_translation": f_translation, "mind_map": f_mindmap,
              "writing_benchmark": f_benchmark}


# ── status / result helpers (mirror assemble_write.py policy + honesty) ─────

def compute_status(ir, validation, build_error, artifacts):
    if validation.get("errors"):
        return "partial"
    if build_error:
        return "partial" if artifacts else "failed"
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
    store.parse_all()

    title = next((d["title"] for d in store.docs if d.get("title")), None)
    ir = base_write_ir(case, kind, store, title)
    FINALIZERS.get(kind, f_generic)(ir, store, case)
    merge_provided_ir(ir, store)
    for e in store.errors:
        ir["uncertainty"].append({"item": "extraction", "reason": e,
                                  "handling": "human_confirm"})
    if not store.sources:
        ir["uncertainty"].append({"item": "materials",
                                  "reason": "input directory empty or unreadable; "
                                            "nothing to extract", "handling": "human_confirm"})
    # de-duplicate uncertainty entries
    seen, uniq = set(), []
    for u in ir["uncertainty"]:
        key = (u.get("item"), u.get("reason"))
        if key not in seen:
            seen.add(key)
            uniq.append(u)
    ir["uncertainty"] = uniq

    kit.write_json(work_dir / "writing_ir.json", ir)

    # ── SAME validate + build path as assemble_write.py ──
    if kind == "writing_benchmark":
        import benchkit
        validation = writekit.validate_writing(ir) if ir.get("claims") else \
            {"ok": True, "errors": [], "warnings": []}
        bv = benchkit.validate_benchmark(ir)
        validation = {"ok": validation["ok"] and bv["ok"],
                      "errors": validation["errors"] + bv["errors"],
                      "warnings": validation["warnings"] + bv["warnings"]}
    elif kind == "mind_map":
        validation = {"ok": bool(ir.get("nodes")),
                      "errors": [] if ir.get("nodes") else ["mind_map requires nodes"],
                      "warnings": []}
        for n in ir.get("nodes", []):
            if not n.get("source"):
                validation["warnings"].append(f"node {n.get('id')} lacks source")
    else:
        validation = writekit.validate_writing(ir)
    kit.write_json(out_dir / "validation.json", validation)

    artifacts, extra, build_error = [], {}, None
    if validation["ok"]:
        try:
            if kind == "writing_benchmark":
                import benchkit
                extra = benchkit.build_benchmark(ir, out_dir)
                artifacts = extra["artifacts"]
            elif kind == "mind_map":
                import mindmap
                extra = mindmap.render(ir, out_dir)
                artifacts = extra["artifacts"]
            else:
                import docxkit
                paths = docxkit.write_manuscript(ir, out_dir)
                artifacts = [{"name": "manuscript.md", "path": paths["md"],
                              "format": "md", "role": "md"},
                             {"name": "manuscript.docx", "path": paths["docx"],
                              "format": "docx", "role": "docx"}]
                extra["number_issues"] = writekit.check_number_consistency(ir)
                try:
                    import export_deck
                    ex = export_deck.export(ir, out_dir)
                    artifacts += [a for a in ex["artifacts"]
                                  if a["format"] in ("pdf", "png")]
                except Exception:
                    pass
        except Exception as e:  # noqa: BLE001
            build_error = f"{type(e).__name__}: {e}"
            traceback.print_exc()
            ir["uncertainty"].append({"item": "build", "reason": build_error,
                                      "impact": "deliverable not fully built",
                                      "handling": "IR+validation saved; fix and re-run"})
    status = compute_status(ir, validation, build_error, artifacts)

    kit.write_json(out_dir / "writing_ir.json", ir)
    ir.setdefault("provenance", {})["claim_map"] = writekit.build_claim_map(ir)
    kit.write_json(out_dir / "provenance.json", ir["provenance"])

    notes = AUTO_NOTE
    if not validation["ok"]:
        notes += " validation failed: " + "; ".join(validation["errors"])
    elif validation["warnings"]:
        notes += " warnings: " + "; ".join(validation["warnings"][:6])
    result = kit.build_result(case, ir, artifacts, status, validation, None, notes)
    result["extra_checks"] = extra
    result["autopilot"] = {"kind": kind, "n_materials": len(materials),
                           "n_claims": len(ir.get("claims", [])),
                           "n_sections": len(ir.get("sections", [])),
                           "work_ir": str(work_dir / "writing_ir.json")}
    if build_error:
        result["build_error"] = build_error
    kit.write_result(out_dir, result)
    print(json.dumps({"status": status, "case_id": case["case_id"], "kind": kind,
                      "validation_ok": validation["ok"], "errors": validation["errors"],
                      "n_artifacts": len(artifacts),
                      "n_claims": len(ir.get("claims", [])),
                      "result": str(out_dir / "result.json")},
                     ensure_ascii=False, indent=2))
    return 0 if status in ("success", "partial") else 1


def main():
    ap = argparse.ArgumentParser(description="writing track autopilot "
                                             "(auto-extract IR + run assemble_write path)")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--kind", default=None)
    args = ap.parse_args()

    case, sources, kind = {}, [], None
    try:
        if kit is None or writekit is None:
            raise RuntimeError("cannot import sibling figkit.py / writekit.py")
        return run(args)
    except Exception as e:
        traceback.print_exc()
        # honest fallback: NEVER exit without result.json
        try:
            case = kit.load_case(args.input) if kit else {}
            kind = args.kind or skill_default_kind()
            try:
                mats = kit.list_materials(args.input) if kit else []
                sources = [{"id": f"S{i}", "locator": m["name"], "path": m["path"],
                            "kind": (m.get("ext") or "").lstrip(".")}
                           for i, m in enumerate(mats, 1)]
            except Exception:
                sources = []
            ir = {"ir_version": "1.0", "case_id": case.get("case_id"), "kind": kind,
                  "sources": sources,
                  "uncertainty": [{"item": "pipeline",
                                   "reason": f"{type(e).__name__}: {e}",
                                   "handling": "human_confirm"}],
                  "provenance": {"pipeline": "auto_write fallback", "changes": []}}
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