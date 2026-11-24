"""auto_arena_write.py — deterministic "autopilot" entry point for the product-arena
WRITING track (assemble.py + arena_write_engine.py + w4kit.py architecture).

Reads the ACTUAL organizer-provided local materials under --input, auto-extracts a
complete writing IR (sources / claims+evidence / citations / numbers + kind-specific
fields: latex{documentclass,packages,sections,figures} + bib_entries for kind=latex;
segments for polish; references/in_text_citations for reference_manage; sections/
parameters for intro_related/methods_section), then runs the SAME validate+build
path as assemble.py (arena_write_engine.validate_ir -> arena_write_engine.build ->
writekit.build_claim_map -> w4kit.build_result / write_result) and writes an honest
result.json preserving every output_contract key + case_id. Stdlib only; additive —
does not modify the engine or kits.

Usage:
  PYTHONDONTWRITEBYTECODE=1 python auto_arena_write.py --input /input --out /app/output \
      [--work /app/work] [--kind KIND]

Design rules (mirrors engines/search/auto_search.py):
  * Never fabricate: every section body / claim / quote / number / bib entry is an
    EXACT excerpt of real file content with a locator (LaTeX bodies are escaped
    verbatim text; inline reference parentheticals become \\cite keys backed by
    bib_entries parsed from the SAME material).
  * Judgment-heavy fields (claim strength, template/package defaults, reference
    style) get deterministic, evidence-grounded defaults flagged human_confirm in
    uncertainty[] (=> honest status "partial").
  * Defensive extraction: a bad/missing file becomes an honest gap, never a crash.
  * The WHOLE pipeline is wrapped: on ANY exception an honest result.json is still
    written (status partial/failed) with contract keys + case_id + sources + error.
  * After this baseline runs, the agent may refine /app/work/writing_ir.json within
    budget and re-run assemble.py to improve judgment fields.
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
    import w4kit as kit
    import writekit
    import arena_write_engine as engine
except Exception:  # catastrophic import failure -> emergency writer below
    kit = None
    writekit = None
    engine = None

AUTO_NOTE = ("auto_arena_write autopilot: deterministic extraction from ACTUAL local "
             "materials + existing arena_write_engine validate/build (same path as "
             "assemble.py); no fabricated content/quotes/citations/compile status. "
             "Judgment fields use documented evidence-grounded defaults flagged "
             "human_confirm; refine work/writing_ir.json and re-run assemble.py to "
             "improve.")

ARENA_KINDS = {"polish", "reference_manage", "intro_related", "methods_section", "latex"}

KIND_KEYWORDS = [
    ("latex", ["latex", "tex", "编译", "compile", "documentclass", "bibtex"]),
    ("polish", ["润色", "polish", "语言优化", "edit language"]),
    ("reference_manage", ["参考文献", "reference manage", "引用格式", "gb/t 7714",
                          "citation style", "文献管理"]),
    ("intro_related", ["引言", "introduction", "related work", "相关工作"]),
    ("methods_section", ["方法", "methods", "methodology", "参数"]),
]

KNOWN_HEADINGS = {
    "abstract", "introduction", "background", "methods", "method", "materials",
    "materials and methods", "methodology", "results", "discussion", "conclusion",
    "conclusions", "limitations", "references", "related work", "experiments",
    "experiment", "evaluation", "appendix", "acknowledgements", "acknowledgments",
    "title", "author", "摘要", "引言", "背景", "方法", "结果", "讨论", "结论",
    "局限性", "参考文献", "致谢", "附录", "相关工作", "实验",
}

HEAD_PATTERNS = [
    re.compile(r"^(#{1,6})\s+(.+?)\s*$"),
    re.compile(r"^(.{1,60}?)\s*\((Sec\.?\s*\d+[^)]*)\)\s*[:：]\s*(.*)$"),
    re.compile(r"^(Sec\.?\s*\d+)\s*[:：]\s*(.*)$"),
    re.compile(r"^(第[一二三四五六七八九十百\d]+[章节部分])\s*[:：]?\s*(.*)$"),
    re.compile(r"^([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff /&-]{0,50})\s*[:：]\s*(.*)$"),
]


# ── small helpers ────────────────────────────────────────────────────────────

def clip(s, n=600):
    s = str(s)
    return s if len(s) <= n else s[:n] + "..."


def sentences_of(text):
    parts = re.split(r"(?<=[.!?。！？])\s+", str(text or ""))
    return [p.strip() for p in parts if p.strip()]


def nums_in(text):
    return re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(text or ""))


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-") or "sec"


# ── text / PDF / DOCX reading (stdlib, defensive) ────────────────────────────

def pdf_text(data: bytes) -> str:
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
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    except Exception:
        return data.decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml, re.S)
    out = [(t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&apos;", "'")) for t in texts]
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

def heading_match(ln):
    s = ln.strip()
    if not s:
        return None
    m = HEAD_PATTERNS[0].match(s)
    if m:
        return (m.group(2).strip(), f"L-level{len(m.group(1))}", "")
    for pat in HEAD_PATTERNS[1:4]:
        m = pat.match(s)
        if m:
            body = m.group(m.lastindex).strip() if m.lastindex and m.lastindex >= 2 else ""
            return (m.group(1).strip(), m.group(1).strip(), body)
    m = HEAD_PATTERNS[4].match(s)
    if m:
        head, body = m.group(1).strip(), m.group(2).strip()
        hl = head.lower()
        if hl in KNOWN_HEADINGS or hl in ("title", "author", "标题", "作者"):
            return (head, head, body)
    return None


def parse_document(text, name):
    lines = text.splitlines()
    title, author = None, None
    sections, cur, buf, buf_start = [], None, [], None
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
            hl = head.lower()
            if hl in ("title", "标题") and title is None:
                title = body or None
                continue
            if hl in ("author", "作者"):
                if author is None:
                    author = body or None
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
    return {"title": title, "author": author, "sections": sections}


# ── material store ───────────────────────────────────────────────────────────

class Store:
    def __init__(self, case, materials):
        self.case = case
        self.sources = []
        self.files = []
        self.docs = []
        self.tables = []
        self.provided_ir = None
        self.bib = []           # {key, authors, year, title, journal, doi, source, locator}
        self.numbers = []
        self.uncertainty = []
        self.errors = []

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
            return
        if ext in ("csv", "tsv", "tab"):
            rows = kit.read_table(f["path"])
            raw_lines = read_material_text(f["path"]).splitlines()
            self.tables.append({"sid": sid, "name": name, "rows": rows,
                                "raw_lines": raw_lines})
            self.declare_numbers(sid, name, "\n".join(raw_lines))
            return
        if ext == "json":
            try:
                data = kit.load_json(f["path"])
            except Exception as e:
                self.add_unc(name, f"JSON unreadable: {e}")
                return
            if isinstance(data, dict) and data.get("kind") and any(
                    k in data for k in ("sections", "latex", "claims", "segments",
                                        "references", "bib_entries")):
                self.provided_ir = data
                self.add_unc(name, "input ships a writing-IR fragment; its fields are "
                             "merged over the auto-extracted baseline (provided values win)",
                             "note")
            return
        if ext in ("png", "jpg", "jpeg", "gif", "bmp", "svg", "ico", "zip", "gz"):
            f["role"] = "asset"
            return
        text = read_material_text(f["path"])
        f["text"] = text
        doc = parse_document(text, name)
        for s in doc["sections"]:
            s["id"] = f"{sid}_{s['id']}"
            for p in s["paragraphs"]:
                p["id"] = f"{sid}_{p['id']}"
        doc.update({"sid": sid, "name": name, "text": text})
        self.docs.append(doc)
        self.declare_numbers(sid, name, text)
        self.extract_bib(sid, name, text)

    def declare_numbers(self, sid, name, text):
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

    def extract_bib(self, sid, name, text):
        found = []
        for m in re.finditer(r"\(?(Ref\s*\d+)\s*[:：]\s*([^)\n]+)\)?", text):
            found.append((m.group(1).replace(" ", "").lower(), m.group(2).strip(),
                          f"{name} L{text[:m.start()].count(chr(10)) + 1}"))
        ref_zone = text
        rm = re.search(r"(?:References|Reference list|参考文献)\s*\n(.*)", text, re.S | re.I)
        if rm:
            ref_zone = rm.group(1)
        for m in re.finditer(r"^\s*\[?(\d+)[\].)]\s+(.{15,})$", ref_zone, re.M):
            found.append((f"ref{m.group(1)}", m.group(2).strip(),
                          f"{name} reference [{m.group(1)}]"))
        for key, entry, locator in found:
            if any(b["key"] == key for b in self.bib):
                continue
            doi = re.search(r"10\.\d{4,9}/[^\s,;)]+", entry)
            year = re.search(r"\b(19|20)\d{2}\b", entry)
            tm = re.search(r"[\"“](.+?)[\"”]", entry)
            title = tm.group(1) if tm else None
            authors = journal = None
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
            self.bib.append({"key": key, "authors": authors,
                             "year": year.group(0) if year else None,
                             "title": title, "journal": journal,
                             "doi": doi.group(0) if doi else None,
                             "source": sid, "locator": locator,
                             "raw": clip(entry, 300)})
        if self.bib:
            self.add_unc("bib metadata",
                         "authors/year/journal/doi parsed heuristically from real "
                         "reference text in the material; titles absent from the "
                         "material are left empty (never invented); verify fields")


# ── kind detection ───────────────────────────────────────────────────────────

def skill_default_kind():
    skill = SCRIPT_DIR / "SKILL.md"
    if skill.exists():
        try:
            head = skill.read_text(encoding="utf-8", errors="replace")[:3000]
            m = re.search(r"kind=([a-z_]+)", head)
            if m and m.group(1) in ARENA_KINDS:
                return m.group(1)
        except Exception:
            pass
    return "latex"


def detect_kind(args_kind, case, store):
    default = skill_default_kind()
    if args_kind:
        k = args_kind.strip().lower().replace("-", "_")
        if k in ARENA_KINDS:
            return k
    raw_kind = (case.get("raw") or {}).get("kind")
    if isinstance(raw_kind, str) and raw_kind.lower() in ARENA_KINDS:
        return raw_kind.lower()
    if default:
        return default
    blob = ((case.get("task_md") or "") + " " +
            json.dumps(case.get("raw") or {}, ensure_ascii=False)).lower()
    best, best_score = None, 0
    for kind, kws in KIND_KEYWORDS:
        score = sum(1 for kw in kws if kw.lower() in blob)
        if score > best_score:
            best, best_score = kind, score
    return best or "latex"


# ── LaTeX helpers ────────────────────────────────────────────────────────────

def latex_escape(text):
    """Escape plain text for LaTeX body (verbatim content, no rewriting)."""
    t = str(text)
    t = t.replace("\\", "\x01BS\x01")
    for ch in ("&", "%", "$", "#", "_", "{", "}"):
        t = t.replace(ch, "\\" + ch)
    t = t.replace("~", "\\textasciitilde{}").replace("^", "\\textasciicircum{}")
    t = t.replace("\x01BS\x01", "\\textbackslash{}")
    return t


def looks_like_latex(text):
    return bool(re.search(r"\\(cite|ref|begin|section|textbf|emph|label)\b|\$[^$]+\$",
                          str(text)))


def cite_placeholders(text, bib_keys):
    """Replace real reference parentheticals / [n] markers with placeholders that
    survive escaping, then restore as \\cite{key}. Returns (text, used_keys)."""
    used = []

    def sub_ref(m):
        key = m.group(1).replace(" ", "").lower()
        if key in bib_keys:
            used.append(key)
            return f"\x01CITE{key}\x01"
        return m.group(0)

    t = re.sub(r"\(\s*(Ref\s*\d+)\s*[:：][^)]*\)", sub_ref, text)
    t = re.sub(r"\(\s*(Ref\s*\d+)\s*\)", sub_ref, t)

    def sub_num(m):
        key = f"ref{m.group(1)}"
        if key in bib_keys:
            used.append(key)
            return f"\x01CITE{key}\x01"
        return m.group(0)

    t = re.sub(r"\[(\d+)\]", sub_num, t)
    return t, used


def restore_cites(text):
    return re.sub(r"\x01CITE([a-z0-9]+)\x01", lambda m: "\\cite{" + m.group(1) + "}",
                  text)


# ── claims / sections shared by manuscript kinds ────────────────────────────

def build_claims(store, doc, start=0, max_per_para=3):
    claims = []
    for s in doc["sections"]:
        if re.match(r"^(references|reference list|参考文献)\s*$", s["heading"], re.I):
            continue
        for p in s["paragraphs"]:
            taken = 0
            for sent in sentences_of(p["text"]):
                if taken >= max_per_para:
                    break
                if len(sent) < 25 and not nums_in(sent):
                    continue
                if sent not in doc["text"]:
                    continue
                cid = f"c{start + len(claims) + 1}"
                cite_ids = []
                for m in re.finditer(r"\bRef\s*(\d+)\b|\[(\d+)\]|\\cite\{([^}]+)\}", sent):
                    key = (f"ref{m.group(1) or m.group(2)}" if (m.group(1) or m.group(2))
                           else m.group(3))
                    for k in str(key).split(","):
                        k = k.strip()
                        if any(b["key"] == k for b in store.bib) and k not in cite_ids:
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


def manuscript_pieces(store):
    all_claims, sections = [], []
    for doc in store.docs:
        cs = build_claims(store, doc, start=len(all_claims))
        all_claims.extend(cs)
        for s in doc["sections"]:
            if re.match(r"^(references|reference list|参考文献)\s*$", s["heading"], re.I):
                continue
            paras = [{"id": p["id"], "text": p["text"],
                      "claims": p.get("claim_ids", []), "source": doc["sid"],
                      "locator": p["locator"]} for p in s["paragraphs"]]
            sections.append({"id": s["id"], "level": 1, "heading": s["heading"],
                             "role": s["heading"], "paragraphs": paras,
                             "source": doc["sid"], "locator": s["locator"]})
    for t in store.tables:
        paras = [{"id": f"tp{i}", "text": ln, "claims": [], "source": t["sid"],
                  "locator": f"{t['name']} L{i}"}
                 for i, ln in enumerate(t["raw_lines"], 1) if ln.strip()]
        if paras:
            sections.append({"id": f"tbl{len(sections) + 1}", "level": 1,
                             "heading": f"Data ({t['name']})",
                             "role": f"Data ({t['name']})", "paragraphs": paras,
                             "source": t["sid"], "locator": t["name"]})
    return all_claims, sections


def base_ir(case, kind, store, title):
    return {"ir_version": "1.0", "case_id": case.get("case_id"), "kind": kind,
            "title": title or (case.get("raw") or {}).get("title") or kind,
            "audience": (case.get("raw") or {}).get("audience", "peers"),
            "genre": (case.get("raw") or {}).get("genre", kind),
            "sources": store.sources, "numbers": store.numbers,
            "claims": [], "sections": [], "citations": [],
            "uncertainty": list(store.uncertainty),
            "provenance": {"pipeline": "material -> auto_extract -> writing IR -> "
                                       "validate -> editable artifact -> result",
                           "skill_version": getattr(writekit, "SKILL_VERSION", "1.0.0"),
                           "changes": [{"step": "auto_extract",
                                        "at": kit.utc_now() if kit else "",
                                        "detail": f"deterministic extraction from "
                                                  f"{len(store.sources)} material files"}]}}


def merge_provided_ir(ir, store):
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


def strength_uncertainty(ir):
    if ir.get("claims"):
        ir["uncertainty"].append({
            "item": "claim strength/type",
            "reason": "strength='supported'/type='fact' are autopilot defaults for "
                      "verbatim source sentences; expert must confirm strength",
            "handling": "human_confirm"})


# ── per-kind finalizers ──────────────────────────────────────────────────────

def f_latex(ir, store, case):
    raw = case.get("raw") or {}
    task = case.get("task_md") or ""
    # main content document: prefer content.md / manuscript-like files
    docs = sorted(store.docs, key=lambda d: (
        0 if d["name"].lower() in ("content.md", "material.md", "manuscript.md") else
        1 if d["name"].lower().endswith((".md", ".tex")) else 2,
        -len(d["text"])))
    bib_keys = {b["key"] for b in store.bib}
    lx_sections, abstract, used_keys = [], None, []
    claims = []
    for doc in docs:
        for s in doc["sections"]:
            head = s["heading"]
            hl = head.lower()
            if hl in ("overview", "front matter"):
                continue
            if re.match(r"^(references|reference list|参考文献)\s*$", hl):
                continue
            body = "\n\n".join(p["text"] for p in s["paragraphs"])
            if not body.strip():
                continue
            if hl == "abstract":
                abstract = body
                continue
            # claims from the ORIGINAL verbatim sentences
            for p in s["paragraphs"]:
                for sent in sentences_of(p["text"]):
                    if (nums_in(sent) or re.search(r"Ref\s*\d+|\[\d+\]", sent)) \
                            and sent in doc["text"] and len(sent) >= 20:
                        cid = f"c{len(claims) + 1}"
                        cite_ids = []
                        for m in re.finditer(r"\bRef\s*(\d+)\b|\[(\d+)\]", sent):
                            key = f"ref{m.group(1) or m.group(2)}"
                            if key in bib_keys and key not in cite_ids:
                                cite_ids.append(key)
                        claims.append({
                            "id": cid, "text": sent, "type": "fact",
                            "evidence": [{"source": doc["sid"],
                                          "locator": f"{s['locator']} / {p['id']}",
                                          "quote": sent, "strength": "supported",
                                          "supports": "full"}],
                            "citation_ids": cite_ids})
            already_tex = looks_like_latex(body)
            if already_tex:
                store.add_unc(f"section '{head}'",
                              "body already contains LaTeX markup; kept verbatim "
                              "(not escaped); human must verify compilability")
                tex_body = body
            else:
                ph, used = cite_placeholders(body, bib_keys)
                used_keys.extend(used)
                tex_body = restore_cites(latex_escape(ph))
            lx_sections.append({"heading": head, "level": 1,
                                "label": f"sec:{slug(head)}", "body": tex_body,
                                "source": doc["sid"], "locator": s["locator"]})
    if not lx_sections and docs:
        # no recognizable headings: typeset the whole real text as one section
        doc = docs[0]
        body = doc["text"].strip()
        ph, used = cite_placeholders(body, bib_keys)
        used_keys.extend(used)
        lx_sections.append({"heading": "Content", "level": 1, "label": "sec:content",
                            "body": restore_cites(latex_escape(ph)),
                            "source": doc["sid"], "locator": doc["name"]})
        store.add_unc("latex sections",
                      "no section headings recognized in material; whole text typeset "
                      "as one 'Content' section (structure needs human confirmation)")
    # figures: only markdown-referenced images that ACTUALLY exist in the input
    figures = []
    input_dir = Path(case.get("input_dir") or ".")
    for doc in docs:
        for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", doc["text"]):
            cap, path = m.group(1), m.group(2)
            cand = input_dir / path
            if cand.exists():
                figures.append({"path": str(cand), "caption": cap or cand.name,
                                "label": f"fig:{slug(cand.stem)}",
                                "ref": cand.name, "source": doc["sid"],
                                "locator": doc["name"]})
            else:
                store.add_unc(f"figure '{path}'",
                              "referenced image not present in provided materials; "
                              "figure omitted (never fabricated)")
    req = []
    rm = re.search(r"required sections?\s*[:：]\s*([^\n.]+)", task, re.I)
    if rm:
        req = [x.strip() for x in re.split(r"[,，/]", rm.group(1)) if x.strip()]
    template = raw.get("template") or raw.get("documentclass") or "article"
    ir["latex"] = {"documentclass": str(template), "options": "11pt",
                   "packages": ["amsmath", "graphicx", "booktabs"],
                   "title": (docs[0]["title"] if docs else ir["title"]) or ir["title"],
                   "author": next((d["author"] for d in docs if d.get("author")),
                                  raw.get("author", "")),
                   "abstract": abstract or "",
                   "bib_style": raw.get("bib_style", "plain"),
                   "required_sections": req,
                   "sections": lx_sections, "figures": figures}
    ir["bib_entries"] = [dict(b) for b in store.bib]
    ir["citations"] = [{"id": b["key"], "authors": b.get("authors"),
                        "year": b.get("year"), "title": b.get("title"),
                        "journal": b.get("journal"), "doi": b.get("doi"),
                        "source": b["source"], "locator": b["locator"]}
                       for b in store.bib]
    ir["claims"] = claims
    ir["exports"] = [{"format": "tex"}, {"format": "bib"}]
    strength_uncertainty(ir)
    ir["uncertainty"].append({
        "item": "latex template defaults",
        "reason": f"documentclass='{template}' (case.template if provided else "
                  "'article'); packages amsmath/graphicx/booktabs and 11pt are "
                  "documented autopilot defaults; confirm against the workorder "
                  "template before runtime compile",
        "handling": "human_confirm"})
    if not lx_sections:
        ir["uncertainty"].append({"item": "latex.sections",
                                  "reason": "no readable content material; cannot "
                                            "typeset anything (never fabricated)",
                                  "handling": "human_confirm"})
    if store.bib and not used_keys:
        ir["uncertainty"].append({
            "item": "unused bib entries",
            "reason": "bib entries parsed from material but no in-text marker "
                      "located; entries kept (real), placement needs human review",
            "handling": "note"})


def f_polish(ir, store, case):
    claims, sections = manuscript_pieces(store)
    ir["claims"], ir["sections"] = claims, sections
    ir["citations"] = [{"id": b["key"], "authors": b.get("authors"),
                        "year": b.get("year"), "title": b.get("title"),
                        "journal": b.get("journal"), "doi": b.get("doi"),
                        "source": b["source"]} for b in store.bib]
    segments = []
    for s in sections:
        for p in s["paragraphs"]:
            segments.append({"id": f"seg{len(segments) + 1}",
                             "original": p["text"], "revised": p["text"],
                             "reason": "autopilot baseline: no edits applied yet; "
                                       "pending human/agent polish",
                             "meaning_preserved": True,
                             "source": p["source"], "locator": p.get("locator")})
    ir["segments"] = segments
    strength_uncertainty(ir)
    ir["uncertainty"].append({
        "item": "polish edits",
        "reason": "revised==original (no machine rewriting invented); each segment "
                  "needs a real polish pass with reason + meaning_preserved review",
        "handling": "human_confirm"})
    ir["exports"] = [{"format": "md"}, {"format": "docx"}]


def f_refs(ir, store, case):
    task = ((case.get("task_md") or "") + " " +
            json.dumps(case.get("raw") or {}, ensure_ascii=False)).lower()
    style = "gb/t 7714"
    if "apa" in task:
        style = "apa"
    elif "ieee" in task:
        style = "ieee"
    ir["target_style"] = style
    ir["references"] = [{"id": b["key"], "title": b.get("title"),
                         "authors": b.get("authors"), "year": b.get("year"),
                         "journal": b.get("journal"), "doi": b.get("doi"),
                         "source": b["source"], "locator": b["locator"]}
                        for b in store.bib]
    ir["citations"] = [{"id": b["key"], "authors": b.get("authors"),
                        "year": b.get("year"), "title": b.get("title"),
                        "journal": b.get("journal"), "doi": b.get("doi"),
                        "source": b["source"]} for b in store.bib]
    in_text = []
    keys = {b["key"] for b in store.bib}
    for doc in store.docs:
        for m in re.finditer(r"\[(\d+)\]|\bRef\s*(\d+)\b", doc["text"]):
            key = f"ref{m.group(1) or m.group(2)}"
            if key in keys:
                in_text.append({"id": f"it{len(in_text) + 1}", "ref_id": key,
                                "marker": m.group(0), "source": doc["sid"],
                                "locator": f"{doc['name']} L{doc['text'][:m.start()].count(chr(10)) + 1}"})
    ir["in_text_citations"] = in_text
    ir["uncertainty"].append({
        "item": "target_style / reference metadata",
        "reason": f"target_style='{style}' inferred from task keywords (default "
                  "GB/T 7714); metadata parsed from real reference text; human "
                  "must confirm style + fields",
        "handling": "human_confirm"})
    if not ir["references"]:
        ir["uncertainty"].append({"item": "references",
                                  "reason": "no reference list found in materials; "
                                            "cannot fabricate entries",
                                  "handling": "human_confirm"})
    ir["exports"] = [{"format": "md"}, {"format": "bib"}]


def f_manuscript(ir, store, case):
    claims, sections = manuscript_pieces(store)
    ir["claims"], ir["sections"] = claims, sections
    ir["citations"] = [{"id": b["key"], "authors": b.get("authors"),
                        "year": b.get("year"), "title": b.get("title"),
                        "journal": b.get("journal"), "doi": b.get("doi"),
                        "source": b["source"]} for b in store.bib]
    strength_uncertainty(ir)
    if ir["kind"] == "methods_section":
        params = []
        for doc in store.docs:
            for m in re.finditer(r"([A-Za-z][A-Za-z _-]{0,24}?)\s*=\s*([-+]?\d+(?:\.\d+)?)",
                                 doc["text"]):
                params.append({"name": m.group(1).strip(), "value": m.group(2),
                               "status": "reported", "source": doc["sid"],
                               "locator": f"{doc['name']} L{doc['text'][:m.start()].count(chr(10)) + 1}"})
        ir["parameters"] = params
        if not params:
            ir["uncertainty"].append({"item": "parameters",
                                      "reason": "no name=value parameters located in "
                                                "material; table left empty (honest gap)",
                                      "handling": "human_confirm"})
    if not sections:
        ir["uncertainty"].append({"item": "sections",
                                  "reason": "no readable text material found; nothing "
                                            "to write (cannot fabricate content)",
                                  "handling": "human_confirm"})
    ir["exports"] = [{"format": "md"}, {"format": "docx"}]


FINALIZERS = {"latex": f_latex, "polish": f_polish, "reference_manage": f_refs,
              "intro_related": f_manuscript, "methods_section": f_manuscript}


# ── status / result helpers ──────────────────────────────────────────────────

def compute_status(ir, validation, build_error, artifacts, engine_status):
    if validation.get("errors"):
        return "partial"
    if build_error:
        return "partial" if artifacts else "failed"
    for u in ir.get("uncertainty", []):
        if u.get("handling") == "human_confirm":
            return "partial"
    return engine_status or "success"


def emergency_result(case, out_dir, error, sources=None, kind=None):
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
    ir = base_ir(case, kind, store, title)
    FINALIZERS.get(kind, f_manuscript)(ir, store, case)
    merge_provided_ir(ir, store)
    for e in store.errors:
        ir["uncertainty"].append({"item": "extraction", "reason": e,
                                  "handling": "human_confirm"})
    if not store.sources:
        ir["uncertainty"].append({"item": "materials",
                                  "reason": "input directory empty or unreadable; "
                                            "nothing to extract", "handling": "human_confirm"})
    seen, uniq = set(), []
    for u in ir["uncertainty"]:
        key = (u.get("item"), u.get("reason"))
        if key not in seen:
            seen.add(key)
            uniq.append(u)
    ir["uncertainty"] = uniq

    kit.write_json(work_dir / "writing_ir.json", ir)

    # ── SAME validate + build path as assemble.py ──
    validation = engine.validate_ir(ir)
    kit.write_json(out_dir / "validation.json", validation)

    artifacts, extra, build_error = [], {}, None
    engine_status = None
    if validation["ok"]:
        try:
            artifacts, extra = engine.build(ir, case, out_dir)
            engine_status = extra.get("status", "success")
        except Exception as e:  # noqa: BLE001
            build_error = f"{type(e).__name__}: {e}"
            traceback.print_exc()
            ir["uncertainty"].append({"item": "build", "reason": build_error,
                                      "impact": "deliverable not fully built",
                                      "handling": "IR+validation saved; fix and re-run"})
    status = compute_status(ir, validation, build_error, artifacts, engine_status)

    kit.write_json(out_dir / "writing_ir.json", ir)
    prov = ir.setdefault("provenance", {})
    prov["claim_map"] = writekit.build_claim_map(ir)
    if extra.get("provenance"):
        prov.update(extra["provenance"])
    kit.write_json(out_dir / "provenance.json", prov)

    notes = AUTO_NOTE
    if not validation["ok"]:
        notes += " validation failed: " + "; ".join(validation["errors"])
    elif validation["warnings"]:
        notes += " warnings: " + "; ".join(validation["warnings"][:6])
    result = kit.build_result(case, ir, artifacts, status, validation,
                              extra.get("result_extra"), notes)
    result["extra_checks"] = extra.get("checks", {})
    result["autopilot"] = {"kind": kind, "n_materials": len(materials),
                           "n_claims": len(ir.get("claims", [])),
                           "work_ir": str(work_dir / "writing_ir.json")}
    if build_error:
        result["build_error"] = build_error
    kit.write_result(out_dir, result)
    print(json.dumps({"status": status, "case_id": case["case_id"], "kind": kind,
                      "validation_ok": validation["ok"], "errors": validation["errors"],
                      "n_artifacts": len(artifacts),
                      "structure_ok": extra.get("checks", {}).get("structure", {}).get("ok"),
                      "result": str(out_dir / "result.json")},
                     ensure_ascii=False, indent=2))
    return 0 if status in ("success", "partial") else 1


def main():
    ap = argparse.ArgumentParser(description="product-arena writing autopilot "
                                             "(auto-extract IR + run assemble.py path)")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--kind", default=None)
    args = ap.parse_args()

    case, sources, kind = {}, [], None
    try:
        if kit is None or writekit is None or engine is None:
            raise RuntimeError("cannot import sibling w4kit.py / writekit.py / "
                               "arena_write_engine.py")
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
                  "provenance": {"pipeline": "auto_arena_write fallback", "changes": []}}
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