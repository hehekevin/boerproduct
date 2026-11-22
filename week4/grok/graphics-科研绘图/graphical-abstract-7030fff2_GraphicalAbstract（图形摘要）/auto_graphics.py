"""auto_graphics.py — deterministic "autopilot" entry point for the week4 GRAPHICS track.

Reads the ACTUAL organizer-provided local materials under --input, auto-extracts
a complete Figure IR (sources / entities / relations / groups / chart spec bound
to real table columns), then runs the SAME validate + render + export_check +
result path as assemble.py (figkit.validate_ir -> render_chart/render_diagram ->
export_check.check -> figkit.build_result) and writes an honest result.json
preserving every output_contract key + case_id. Stdlib only; matplotlib is
optional/lazy exactly like the engine — when the renderer is unavailable a
stdlib svgkit fallback still produces an editable, source-bound figure.svg.
Additive: does not modify figkit/render_chart/render_diagram/assemble.

Usage:
  PYTHONDONTWRITEBYTECODE=1 python auto_graphics.py --input /input --out /app/output \
      [--work /app/work] [--kind KIND]

Design rules (mirrors engines/search/auto_search.py):
  * Never fabricate: every entity label, relation and plotted number comes from
    real file content; each carries a source id + locator.
  * Judgment-heavy fields (relation semantics, categories, compartments) use
    documented evidence-grounded heuristics flagged human_confirm in
    uncertainty[] (=> honest status "partial").
  * Defensive extraction: a bad/missing file becomes an honest gap, never a crash.
  * The WHOLE pipeline is wrapped: on ANY exception an honest result.json is
    still written (status partial/failed) with contract keys + case_id + error.
  * After this baseline runs, the agent may refine work/figure_ir.json within
    budget and re-run assemble.py to improve judgment fields.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import traceback
import zlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    import figkit
except Exception:  # catastrophic import failure -> emergency writer below
    figkit = None

KINDS = {"relationship_schematic", "source_value_chart", "mechanism_pathway",
         "apparatus_route", "graphical_abstract"}

SKILL_KIND = {
    "bio-mechanism-pathway-figure": "mechanism_pathway",
    "apparatus-and-technical-route": "apparatus_route",
    "graphical-abstract-figure": "graphical_abstract",
    "editable-relationship-schematic": "relationship_schematic",
    "source-bound-data-chart": "source_value_chart",
}

KIND_KEYWORDS = [
    ("apparatus_route", ["apparatus", "setup", "technical route", "roadmap", "workflow",
                         "flowchart", "process flow", "material flow", "装置", "流程",
                         "技术路线", "步骤", "parts list", "procedure"]),
    ("mechanism_pathway", ["mechanism", "pathway", "signaling", "signalling", "cascade",
                           "activates", "inhibits", "phosphorylat", "机制", "通路",
                           "信号", "调控网络", "feedback loop"]),
    ("graphical_abstract", ["graphical abstract", "visual summary", "图文摘要",
                            "摘要图", "single-page summary"]),
    ("source_value_chart", ["chart", "plot", "bar chart", "line chart", "scatter",
                            "heatmap", "error bars", "图表", "柱状图", "折线图",
                            "散点", "数据图", "data.csv"]),
    ("relationship_schematic", ["schematic", "relationship", "conceptual", "structure",
                                "hierarchy", "示意图", "关系图", "结构图", "概念图"]),
]

AUTO_NOTE = ("auto_graphics autopilot: deterministic extraction from ACTUAL local "
             "materials + existing figkit validate/render/export pipeline; no "
             "fabricated entities/relations/numbers. Relation semantics, categories "
             "and compartments use documented verb/descriptor heuristics flagged "
             "human_confirm; refine work/figure_ir.json and re-run assemble.py to "
             "improve.")

# ── verb -> relation grammar (rules/rules_mechanism.md + apparatus/schematic) ──
VERB_RULES = [
    ("modifies", r"(?:de)?phosphorylates?|ubiquitinates?|acetylates?|methylates?|cleaves?", True),
    ("inhibits", r"inhibits?|suppresses?|represses?|blocks?|downregulates?|silences?", False),
    ("activates", r"activates?|promotes?|induces?|stimulates?|upregulates?|enhances?", False),
    ("binds", r"binds?|interacts?\s+with|associates?\s+with|recruits?", False),
    ("transports", r"translocates?|imports?|exports?|shuttles?", False),
    ("contains", r"contains?|comprises?|consists?\s+of", False),
    ("part_of", r"is\s+(?:a\s+)?(?:part|component|subunit)\s+of|belongs?\s+to", False),
    ("causes", r"causes?|leads?\s+to|results?\s+in|triggers?|drives?", False),
    ("flows_to", r"flows?\s+(?:in)?to|feeds?|pumped?\s+(?:in)?to|delivered?\s+to|enters?", False),
    ("connects", r"connects?\s+(?:to|with)|connected\s+to|attached\s+to|linked\s+to|coupled\s+to", False),
    ("encodes", r"encodes?", False),
    ("compares", r"compared?\s+(?:to|with)", False),
]
ZH_VERB_RULES = [
    ("modifies", r"磷酸化|去磷酸化|泛素化|乙酰化|甲基化|切割"),
    ("inhibits", r"抑制|阻断|下调|阻遏"),
    ("activates", r"激活|促进|诱导|刺激|上调|增强"),
    ("binds", r"结合|招募|相互作用"),
    ("transports", r"转运|转位|入核|输出"),
    ("contains", r"包含|由.{0,12}组成"),
    ("part_of", r"属于|是.{0,12}的(?:一部分|组分|亚基)"),
    ("causes", r"导致|引起|触发|驱动"),
    ("flows_to", r"流入|流向|进入|输送至|泵入"),
    ("connects", r"连接|相连|接入"),
]
HEDGE_RE = re.compile(r"\b(may|might|could|suggest\w*|hypothes\w*|propos\w*|presum\w*|putative)\b|可能|推测|或许", re.I)

# descriptor -> (entity_kind, compartment band)  [rules_mechanism.md §3]
DESCRIPTORS = [
    ("receptor", "receptor", "membrane"),
    ("transcription factor", "transcription_factor", "nucleus"),
    ("phosphatase", "phosphatase", "cyto"),
    ("gtpase", "gtpase", "cyto"),
    ("kinase", "kinase", "cyto"),
    ("channel", "channel", "membrane"),
    ("transporter", "transporter", "membrane"),
]
COMPARTMENT_WORDS = {
    "membrane": ["plasma membrane", "cell membrane", "membrane", "细胞膜", "膜上"],
    "cyto": ["cytoplasm", "cytosol", "cytoplasmic", "细胞质", "胞质"],
    "nucleus": ["nucleus", "nuclear", "核内", "细胞核"],
}
COMPARTMENT_LABEL = {"membrane": "Membrane", "cyto": "Cytoplasm", "nucleus": "Nucleus"}

SYMBOL_RE = re.compile(r"\b(?:[A-Z][A-Z0-9]{1,11}(?:-[A-Z0-9]+)*|m[A-Z][A-Za-z0-9]{2,}|[A-Z][a-z]+[A-Z][A-Za-z0-9]*)\b")
SYMBOL_STOP = {
    "EXAMPLE", "EXAMPLES", "SYNTHETIC", "SOURCE", "MATERIAL", "MATERIALS", "SECTION",
    "ONLY", "NOTE", "NOTES", "TODO", "CSV", "TSV", "JSON", "SVG", "PNG", "PDF", "DPI",
    "RGB", "SD", "SE", "SEM", "CI", "IR", "TASK", "README", "INPUT", "OUTPUT", "CASE",
    "GTPase", "ATPase", "Kinase", "Phosphatase", "Western", "Figure", "Table", "Step",
    "ALL", "AND", "THE", "FOR", "WITH", "NOT",
}
ZH_TERM_STOP = set("的了和与在通过从而进而形成负反馈 loops 一个进行然后接着最后首先其中该此".split()) | {
    "一个", "进行", "然后", "接着", "最后", "首先", "其中", "从而", "进而", "形成",
    "通过", "负反馈", "正反馈", "反馈", "细胞膜", "细胞质", "细胞核", "核内", "胞质",
}


def clip(s, n=200):
    s = str(s)
    return s if len(s) <= n else s[:n] + "..."


def eid_of(label):
    e = re.sub(r"[^A-Za-z0-9_]+", "_", str(label)).strip("_")
    return e or "E"


# ── text reading (stdlib PDF salvage, same approach as auto_search) ──────────

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


def read_material_text(path):
    data = Path(path).read_bytes()
    if str(path).lower().endswith(".pdf") or data[:5] == b"%PDF-":
        return pdf_text(data)
    return data.decode("utf-8", errors="replace")


def split_sentences(text):
    # collapse line-wraps so a sentence broken across source lines stays whole
    flat = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?。！？])\s+", flat)
    return [p.strip() for p in parts if p and len(p.strip()) > 3]


# ── material store ───────────────────────────────────────────────────────────

class Store:
    def __init__(self, case, materials):
        self.case = case
        self.sources = []
        self.files = []
        self.tables = []      # {sid, path, name, rows, cols}
        self.texts = []       # {sid, path, name, text, sentences}
        self.uncertainty = []
        self.errors = []

    def register_sources(self, materials):
        for i, m in enumerate(materials, 1):
            sid = f"S{i}"
            ext = (m.get("ext") or "").lstrip(".") or "file"
            kind = "table" if ext in ("csv", "tsv", "tab", "json") else "text"
            self.sources.append({"id": sid, "locator": m["path"], "kind": kind,
                                 "name": m["name"], "version": "as-provided"})
            self.files.append({"sid": sid, "path": m["path"], "name": m["name"], "ext": ext})

    def add_unc(self, item, reason, handling="human_confirm"):
        self.uncertainty.append({"item": item, "reason": reason, "handling": handling})

    def parse_all(self):
        for f in self.files:
            try:
                self.parse_file(f)
            except Exception as e:
                self.errors.append(f"{f['name']}: {type(e).__name__}: {e}")
                self.add_unc(f["name"], f"extraction failed: {e}; file registered but not parsed")

    def parse_file(self, f):
        low = f["name"].lower()
        if low in ("case.json", "task.md") or low.startswith("readme"):
            return
        if f["ext"] in ("csv", "tsv", "tab"):
            rows = figkit.read_table(f["path"])
            if rows:
                self.tables.append({"sid": f["sid"], "path": f["path"], "name": f["name"],
                                    "rows": rows, "cols": list(rows[0].keys())})
            else:
                self.add_unc(f["name"], "table has no data rows", "note")
            return
        if f["ext"] == "json":
            try:
                rows = figkit.read_table(f["path"])
            except Exception:
                rows = []
            if rows and all(isinstance(r, dict) for r in rows):
                self.tables.append({"sid": f["sid"], "path": f["path"], "name": f["name"],
                                    "rows": rows, "cols": list(rows[0].keys())})
                return
            # not tabular -> treat as text (may hold prose/figure fragments)
        try:
            text = read_material_text(f["path"])
        except Exception as e:
            self.add_unc(f["name"], f"cannot read bytes: {e}")
            return
        self.texts.append({"sid": f["sid"], "path": f["path"], "name": f["name"],
                           "text": text, "sentences": split_sentences(text)})

    def task_sid(self):
        for f in self.files:
            if f["name"].lower() in ("task.md", "case.json"):
                return f["sid"]
        return self.sources[0]["id"] if self.sources else "S1"


# ── kind detection ───────────────────────────────────────────────────────────

def detect_kind(args_kind, case, store):
    if args_kind:
        k = args_kind.strip().replace("-", "_")
        if k in KINDS:
            return k
    skill = SCRIPT_DIR / "SKILL.md"
    if skill.exists():
        try:
            head = skill.read_text(encoding="utf-8", errors="replace")[:2000]
            m = re.search(r"^name:\s*([a-z0-9-]+)\s*$", head, re.M)
            if m and m.group(1) in SKILL_KIND:
                return SKILL_KIND[m.group(1)]
        except Exception:
            pass
    blob = ((case.get("task_md") or "") + " " +
            json.dumps(case.get("raw") or {}, ensure_ascii=False) + " " +
            " ".join(f["name"] for f in store.files)).lower()
    best, best_score = None, 0
    for kind, kws in KIND_KEYWORDS:
        score = sum(1 for kw in kws if kw.lower() in blob)
        if score > best_score:
            best, best_score = kind, score
    if best:
        return best
    return "source_value_chart" if store.tables else "mechanism_pathway"


# ── chart IR builder (real columns only) ─────────────────────────────────────

ERR_COL_RE = re.compile(r"^(sd|se|sem|stderr|std|error|err|ci|sd_|.*_sd|.*_err)$|error|std.?dev", re.I)
N_COL_RE = re.compile(r"^(n|n_.*|count|samples?|replicates?)$", re.I)
X_TIME_NAME_RE = re.compile(r"time|day|date|week|month|hour|year|dose|concentration|temp|^x$", re.I)
X_NAME_RE = re.compile(r"group|category|label|condition|sample|treatment|stage|step", re.I)
SERIES_NAME_RE = re.compile(r"group|series|category|type|condition|treatment|method|model|variant|class|cohort", re.I)
TIME_X_RE = re.compile(r"^(day|week|hour|month|year|t)\s*[-_]?\d+$|^\d+\s*(h|hr|hrs|d|days?|min|weeks?|months?)$", re.I)


def numeric_col(rows, col):
    vals = [r.get(col) for r in rows if r.get(col) not in (None, "")]
    if not vals:
        return False
    ok = sum(1 for v in vals if figkit.to_float(v) is not None)
    return ok >= max(1, int(0.8 * len(vals)))


def build_chart(store):
    """Pick the richest real table and bind x/y/series/error to ACTUAL columns."""
    if not store.tables:
        return None
    def score(t):
        num = sum(1 for c in t["cols"] if numeric_col(t["rows"], c))
        return (num, len(t["rows"]))
    t = max(store.tables, key=score)
    rows, cols = t["rows"], t["cols"]
    num_cols = [c for c in cols if numeric_col(rows, c)]
    err_cols = [c for c in num_cols if ERR_COL_RE.search(str(c))]
    n_cols = [c for c in cols if N_COL_RE.search(str(c))]
    y_cols = [c for c in num_cols if c not in err_cols and c not in n_cols]
    if not y_cols:
        store.add_unc(f"chart from {t['name']}",
                      "no numeric value column found in the table; cannot bind y without fabricating data")
        return None
    cat_cols = [c for c in cols if c not in num_cols]
    y = next((c for c in y_cols if re.search(r"expression|value|mean|score|rate|level|intensity|conc|response|signal|activity|y$", str(c), re.I)), y_cols[0])
    avail = [c for c in cols if c != y and c not in err_cols and c not in n_cols]
    # prefer a time/dose axis for x, then any categorical label column
    x = next((c for c in avail if X_TIME_NAME_RE.search(str(c))), None)
    if x is None:
        x = next((c for c in avail if c in cat_cols and X_NAME_RE.search(str(c))), None)
    if x is None:
        x = next((c for c in cat_cols if c != y), None)
    if x is None:
        x = next((c for c in avail if c != y), None)
    if x is None:
        x = next((c for c in y_cols if c != y), None)
    if x is None:
        store.add_unc(f"chart from {t['name']}", "no x/label column identified; y bound but x missing")
    series = None
    for c in cat_cols:
        if c == x:
            continue
        uniq = {str(r.get(c)) for r in rows if r.get(c) not in (None, "")}
        if 2 <= len(uniq) <= 8 and len(rows) > len(uniq):
            if series is None or (SERIES_NAME_RE.search(str(c)) and not SERIES_NAME_RE.search(str(series))):
                series = c
    err = err_cols[0] if err_cols else None
    # chart type: explicit task hint wins, else infer from ACTUAL x values
    blob = ((store.case.get("task_md") or "") + " " +
            json.dumps(store.case.get("raw") or {}, ensure_ascii=False)).lower()
    hint = None
    for pat, ct in ((r"grouped[\s-]*bar", "grouped_bar"), (r"\bbar\b|柱状", "bar"),
                    (r"\bline\b|折线", "line"), (r"scatter|散点", "scatter"),
                    (r"heatmap|热图", "heatmap"), (r"\bpie\b|饼图", "pie"),
                    (r"\bbox\b|箱线", "box")):
        if re.search(pat, blob):
            hint = ct
            break
    xvals = [str(r.get(x)) for r in rows if r.get(x) not in (None, "")] if x else []
    if hint:
        ctype = hint
    elif x and x in num_cols:
        ctype = "scatter"
    elif series:
        ctype = "grouped_bar"
    elif xvals and all(TIME_X_RE.match(v) for v in xvals):
        ctype = "line"
    else:
        ctype = "bar"
    y_label, unit = str(y), None
    um = re.search(r"[(\[]([^)\]]+)[)\]]\s*$", str(y))
    if um:
        unit = um.group(1)
        y_label = str(y)[:um.start()].strip()
    chart = {"chart_type": ctype, "data_source": t["sid"], "data_path": t["path"],
             "y": y, "y_label": y_label or str(y)}
    if x:
        chart["x"] = x
        chart["x_label"] = str(x)
    if series:
        chart["series"] = series
    if err:
        chart["error"] = err
        chart["error_kind"] = "sd" if re.search(r"sd|std", str(err), re.I) else (
            "sem" if re.search(r"sem|se|stderr", str(err), re.I) else "unknown")
    if n_cols:
        chart["n"] = n_cols[0]
    if unit:
        chart["unit"] = unit
    store.add_unc("chart encoding",
                  f"chart_type '{ctype}' and x/y/series/error columns auto-selected from "
                  f"{t['name']} headers/values ({', '.join(map(str, cols))}); confirm against the task")
    return chart


# ── entity / relation extraction from real text ──────────────────────────────

def find_symbols(text):
    out = []
    for m in SYMBOL_RE.finditer(text):
        s = m.group(0)
        if s in SYMBOL_STOP or s.upper() in SYMBOL_STOP or len(s) < 2:
            continue
        if s not in out:
            out.append(s)
    return out


def find_marked_terms(text):
    """Bold / quoted / list-head terms — real labels the author emphasized."""
    out = []
    for pat in (r"\*\*([^*\n]{2,40})\*\*", r"[“\"「]([^”\"」\n]{2,40})[”\"」]",
                r"^\s*[-*•]\s*([^:：\n]{2,40})[:：]", r"^\s*\d+[.)、]\s*([^:：\n]{2,40})[:：]"):
        for m in re.finditer(pat, text, re.M):
            s = m.group(1).strip()
            if s and s not in out and not s.isnumeric():
                out.append(s)
    return out


def find_zh_terms(text, sentences):
    """Chinese candidate terms adjacent to relation verbs (heuristic, flagged)."""
    out = []
    verbs = "|".join(p for _, p in ZH_VERB_RULES)
    for m in re.finditer(r"([\u4e00-\u9fffA-Za-z0-9α-ω\-]{2,16}?)(?:" + verbs + r")", text):
        s = m.group(1).strip()
        if s and s not in ZH_TERM_STOP and s not in out:
            out.append(s)
    for m in re.finditer(r"(?:" + verbs + r")([\u4e00-\u9fffA-Za-z0-9α-ω\-]{2,16})", text):
        s = m.group(1).strip()
        for stop in ("了", "的", "和", "与"):
            s = s.lstrip(stop)
        if s and s not in ZH_TERM_STOP and s not in out:
            out.append(s)
    return out


def mentions_in(sentence, labels):
    """(start, end, label) for every verbatim label occurrence in the sentence."""
    hits = []
    for lab in labels:
        if re.match(r"^[A-Za-z0-9_-]+$", lab):
            pat = r"(?<![A-Za-z0-9])" + re.escape(lab) + r"(?![A-Za-z0-9])"
        else:
            pat = re.escape(lab)
        for m in re.finditer(pat, sentence):
            hits.append((m.start(), m.end(), lab))
    return sorted(hits)


def extract_entities_relations(store, kind):
    """Deterministic symbol/term + verb-grammar extraction over REAL sentences."""
    entities, relations = [], []
    seen_e, seen_r = {}, set()
    texts = store.texts
    all_text = "\n".join(t["text"] for t in texts)
    # 1) candidate labels per text file
    per_file = []
    for t in texts:
        labels = find_symbols(t["text"])
        labels += [s for s in find_marked_terms(t["text"]) if s not in labels]
        if re.search(r"[\u4e00-\u9fff]", t["text"]):
            labels += [s for s in find_zh_terms(t["text"], t["sentences"]) if s not in labels]
        per_file.append((t, labels))
    # 2) register entities with descriptor-based category / compartment
    for t, labels in per_file:
        flat = re.sub(r"\s+", " ", t["text"])
        low = flat.lower()
        for lab in labels:
            eid = eid_of(lab)
            if eid in seen_e:
                continue
            pat = (r"(?<![A-Za-z0-9])" + re.escape(lab) + r"(?![A-Za-z0-9])") \
                if re.match(r"^[A-Za-z0-9_-]+$", lab) else re.escape(lab)
            m = re.search(pat, flat)
            if not m:
                continue
            # closest descriptor word within +/-35 chars of ANY mention names the kind
            ekind, band, category = None, None, ("protein" if kind == "mechanism_pathway" else "concept")
            best_d = 999
            mentions = list(re.finditer(pat, flat))
            for word, ek, bd in DESCRIPTORS:
                for dm in re.finditer(re.escape(word), low):
                    for mm in mentions:
                        d = min(abs(dm.start() - mm.start()), abs(dm.end() - mm.end()))
                        if d <= 35 and d < best_d:
                            best_d, ekind, band, category = d, ek, bd, "protein"
            if re.search(r"\bgene\b|基因", low[max(0, m.start() - 50):m.end() + 50]) and category == "concept":
                category = "gene"
            sent_idx = next((i for i, s in enumerate(t["sentences"]) if lab in s), 0)
            ent = {"id": eid, "label": lab, "category": category,
                   "source": t["sid"],
                   "source_locator": f"{t['name']} sentence {sent_idx + 1}: {clip(t['sentences'][sent_idx], 120)}",
                   "confidence": "high" if ekind else "medium"}
            if ekind:
                ent["entity_kind"] = ekind
            if band:
                ent["group"] = band
            entities.append(ent)
            seen_e[eid] = ent
    labels_all = [e["label"] for e in entities]
    # 3) relations: verb grammar per sentence, regulator -> target
    for t in texts:
        zh = bool(re.search(r"[\u4e00-\u9fff]", t["text"]))
        rules = [(ty, re.compile(p, re.I), mod) for ty, p, mod in VERB_RULES]
        if zh:
            rules += [(ty, re.compile(p), False) for ty, p in ZH_VERB_RULES]
        for si, sent in enumerate(t["sentences"]):
            hits = mentions_in(sent, labels_all)
            if len(hits) < 1:
                continue
            hedge = bool(HEDGE_RE.search(sent))
            for rtype, vre, is_mod in rules:
                for vm in vre.finditer(sent):
                    before, after = sent[:vm.start()], sent[vm.end():]
                    passive = bool(re.search(r"\b(?:is|are|was|were|be|been)\s+(?:[a-z]+\s+){0,3}$", before, re.I)
                                   and re.match(r"^\s*(?:by|through)\b", after, re.I))
                    if passive:
                        subj_hits = [h for h in hits if h[0] >= vm.end()]
                        obj_hits = [h for h in hits if h[1] <= vm.start()]
                        frm = subj_hits[0][2] if subj_hits else None
                        to = obj_hits[-1][2] if obj_hits else None
                    else:
                        which_m = re.search(r",?\s*(?:which|that)\b[^,]*$", before, re.I)
                        if which_m:
                            prior = [h for h in hits if h[1] <= vm.start() - len(which_m.group(0))]
                            frm = prior[-1][2] if prior else None
                        else:
                            prior = [h for h in hits if h[1] <= vm.start()]
                            frm = prior[-1][2] if prior else None
                        nxt = [h for h in hits if h[0] >= vm.end()]
                        to = nxt[0][2] if nxt else None
                    if not frm or not to or frm == to:
                        continue
                    key = (eid_of(frm), eid_of(to), rtype)
                    if key in seen_r:
                        continue
                    seen_r.add(key)
                    rel = {"id": f"r{len(relations) + 1}", "from": eid_of(frm), "to": eid_of(to),
                           "type": rtype, "direction": "forward",
                           "source": t["sid"],
                           "source_locator": f"{t['name']} sentence {si + 1}: {clip(sent, 140)}",
                           "evidence_strength": "hypothesized" if hedge else "established",
                           "confidence": "medium" if hedge else "high"}
                    if is_mod:
                        rel["modifiers"] = [vm.group(0).lower()]
                    if re.search(r"feedback|反馈", sent, re.I):
                        rel["label"] = ("negative " if re.search(r"negative|负", sent, re.I) else "") + "feedback"
                    if rtype == "transports" and re.search(r"nucleus|nuclear|入核|核内", sent, re.I):
                        rel["label"] = "nuclear translocation"
                    relations.append(rel)
                    if hedge:
                        store.add_unc(f"relation {rel['id']} ({frm}->{to})",
                                      "hedged source wording; evidence_strength=hypothesized (heuristic)")
    # conservative compartment propagation for signaling cascades: an ungrouped
    # entity adjacent (via an interaction edge) to an explicit cytoplasmic node
    # inherits cyto (intracellular signaling); flagged human_confirm, never membrane/nucleus.
    if kind == "mechanism_pathway":
        by_id = {e["id"]: e for e in entities}
        adj = {}
        for r in relations:
            adj.setdefault(r["from"], set()).add(r["to"])
            adj.setdefault(r["to"], set()).add(r["from"])
        changed = True
        while changed:
            changed = False
            for e in entities:
                if e.get("group"):
                    continue
                if any(by_id.get(n, {}).get("group") == "cyto" for n in adj.get(e["id"], ())):
                    e["group"] = "cyto"
                    e["confidence"] = "medium"
                    changed = True
        if any(e.get("group") == "cyto" and e.get("confidence") == "medium" for e in entities):
            store.add_unc("compartment propagation",
                          "ungrouped signaling nodes adjacent to explicit cytoplasmic nodes "
                          "assigned cyto by cascade heuristic; human_confirm")
    return entities, relations


def build_groups(store, entities, relations, kind):
    """Compartment groups for mechanism; only when the text localizes them."""
    groups = []
    text = "\n".join(t["text"] for t in store.texts).lower()
    tsid = store.texts[0]["sid"] if store.texts else store.task_sid()
    if kind in ("mechanism_pathway", "graphical_abstract"):
        for band, words in COMPARTMENT_WORDS.items():
            members = [e["id"] for e in entities if e.get("group") == band]
            if not members:
                continue
            hit = next((w for w in words if w in text), None)
            label = "Plasma membrane" if band == "membrane" and "plasma membrane" in text \
                else COMPARTMENT_LABEL[band]
            groups.append({"id": band, "label": label, "kind": "compartment",
                           "members": members, "source": tsid})
            if not hit:
                store.add_unc(f"compartment {band}",
                              "band assigned from entity descriptors/cascade heuristic; the "
                              "compartment word is not explicit in the source text; human_confirm")
    return groups


# ── apparatus / route extraction ─────────────────────────────────────────────

DEVICE_RE = re.compile(r"pump|sensor|valve|reactor|column|detector|controller|furnace|chamber|filter|membrane module|tank|mixer|heater|condenser|泵|传感器|阀|反应器|检测器|柱|炉|腔|罐", re.I)


def build_apparatus(store, kind):
    entities, relations, groups = [], [], []
    seen_r = set()
    for t in store.texts:
        text = t["text"]
        # numbered steps / Step N lines -> sequence chain in TEXT order
        steps = []
        for m in re.finditer(r"^\s*(?:step\s*)?(\d+)[.)、:：]\s*(.+)$|^\s*Step\s+(\d+)\s*[:：.]?\s*(.+)$",
                             text, re.M | re.I):
            num = m.group(1) or m.group(3)
            body = (m.group(2) or m.group(4) or "").strip()
            if body:
                steps.append((num, body))
        headings = [(m.start(), m.group(1).strip()) for m in re.finditer(r"^#{1,6}\s+(.+)$", text, re.M)]
        for num, body in steps:
            eid = f"STEP{num}"
            if any(e["id"] == eid for e in entities):
                continue
            pos = text.find(body)
            hd = next((h for p, h in reversed(headings) if p < pos), None)
            ent = {"id": eid, "label": f"{num}. {clip(body, 60)}", "category": "step",
                   "source": t["sid"], "source_locator": f"{t['name']} step {num}",
                   "confidence": "high"}
            if hd:
                ent["group"] = eid_of(hd)
            entities.append(ent)
        for a, b in zip(steps, steps[1:]):
            key = (f"STEP{a[0]}", f"STEP{b[0]}", "sequence")
            if key not in seen_r:
                seen_r.add(key)
                relations.append({"id": f"r{len(relations) + 1}", "from": f"STEP{a[0]}",
                                  "to": f"STEP{b[0]}", "type": "sequence", "direction": "forward",
                                  "source": t["sid"],
                                  "source_locator": f"{t['name']} numbered order {a[0]}->{b[0]}",
                                  "evidence_strength": "established", "confidence": "high"})
        for hd_pos, hd in headings:
            gid = eid_of(hd)
            members = [e["id"] for e in entities if e.get("group") == gid]
            if members:
                groups.append({"id": gid, "label": clip(hd, 40), "kind": "stage",
                               "members": members, "source": t["sid"]})
        # parts list bullets "Name: description" (not numbered steps)
        for m in re.finditer(r"^\s*[-*•]\s*([^:：\n]{2,40})[:：]\s*(.+)$", text, re.M):
            name, desc = m.group(1).strip(), m.group(2).strip()
            eid = eid_of(name)
            if any(e["id"] == eid for e in entities) or name.isnumeric():
                continue
            entities.append({"id": eid, "label": name,
                             "category": "device" if DEVICE_RE.search(name + " " + desc) else "part",
                             "source": t["sid"],
                             "source_locator": f"{t['name']} parts-list line: {clip(m.group(0), 120)}",
                             "confidence": "high"})
    # connections / flows stated in prose (reuse verb grammar over all labels)
    labels = [e["label"] for e in entities if e["category"] != "step"]
    extra_e, extra_r = extract_entities_relations(store, kind)
    have = {e["id"] for e in entities}
    for e in extra_e:
        if e["id"] not in have and (e["category"] in ("device", "part") or e["label"] in labels):
            entities.append(e)
            have.add(e["id"])
    for r in extra_r:
        if r["type"] in ("connects", "flows_to", "contains", "part_of", "sequence", "causes") \
                and r["from"] in have and r["to"] in have:
            key = (r["from"], r["to"], r["type"])
            if key not in seen_r:
                seen_r.add(key)
                r["id"] = f"r{len(relations) + 1}"
                relations.append(r)
    if not entities:
        # honest fallback: generic extraction, flagged
        entities, relations = extra_e, extra_r
        groups = build_groups(store, entities, relations, kind)
        if entities:
            store.add_unc("apparatus structure",
                          "no numbered steps/parts list recognized; generic symbol/term "
                          "extraction used; confirm parts & interfaces against the source")
    return entities, relations, groups


# ── per-kind IR finalizers ───────────────────────────────────────────────────

def base_ir(case, kind, store):
    task = (case.get("raw") or {}).get("task") or case.get("task_md") or ""
    title = clip(re.split(r"(?<=[.!?。])\s+", str(task).strip())[0], 120) if task else ""
    if not title and store.texts:
        first = store.texts[0]["text"].strip().splitlines()
        title = clip(re.sub(r"^#+\s*", "", first[0]) if first else "", 120)
    ir = {
        "ir_version": figkit.IR_VERSION,
        "case_id": case.get("case_id", "unknown-case"),
        "kind": kind,
        "title": title or f"Auto-extracted {kind} from provided materials",
        "caption": "Autopilot baseline: all elements extracted from the provided local "
                   "materials with source locators; heuristic fields flagged human_confirm.",
        "canvas": {"width_mm": 180, "height_mm": 120, "dpi": 300, "background": "#ffffff"},
        "style": {"preset": "nature", "font_family": "DejaVu Sans", "base_font_pt": 8,
                  "min_font_pt": 5, "line_width_pt": 0.6, "color_space": "RGB",
                  "palette": "okabe_ito"},
        "sources": store.sources,
        "exports": [{"format": "svg"}, {"format": "png", "dpi": 300}, {"format": "pdf"}],
        "provenance": {"pipeline": "material -> auto_extract -> IR -> validate -> editable source -> export",
                       "skill_version": figkit.SKILL_VERSION,
                       "changes": [{"step": "auto_extract", "at": figkit.utc_now(),
                                    "detail": f"deterministic extraction from {len(store.sources)} material files"}]},
        "uncertainty": [],
    }
    return ir


def finalize(ir, store, case, kind):
    chart = build_chart(store)
    if kind == "source_value_chart":
        if chart:
            ir["chart"] = chart
        else:
            store.add_unc("chart", "no usable data table found in materials; chart spec "
                          "cannot be bound without fabricating numbers")
    elif kind == "apparatus_route":
        ents, rels, groups = build_apparatus(store, kind)
        ir["entities"], ir["relations"], ir["groups"] = ents, rels, groups
        if chart:
            ir["chart"] = chart
    else:
        ents, rels = extract_entities_relations(store, kind)
        groups = build_groups(store, ents, rels, kind)
        ir["entities"], ir["relations"], ir["groups"] = ents, rels, groups
        if chart and kind == "graphical_abstract":
            ir["chart"] = chart  # result panel binding (assemble renders diagram when entities exist)
        if not ents:
            store.add_unc("entities", "no scientific entities recognized in the provided "
                          "text; nothing extracted (no fabricated nodes)")
        elif not rels:
            store.add_unc("relations", "entities found but no explicit relation verb located; "
                          "no edges invented")
        if ents or rels:
            store.add_unc("entity/relation semantics",
                          "categories, compartments, relation types and directions are "
                          "deterministic verb/descriptor heuristics over source sentences, "
                          "not expert curation; human_confirm all claims")
    if not store.sources:
        store.add_unc("materials", "input directory empty or unreadable; nothing to extract")
    for e in store.errors:
        store.add_unc("extraction", e)
    ir["uncertainty"] = list(store.uncertainty)
    return ir


# ── stdlib SVG fallback (renderer/matplotlib unavailable) ────────────────────

def _palette_colors():
    try:
        pal = figkit.load_json(SCRIPT_DIR / "palettes.json")
        return pal.get("okabe_ito", ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9"])
    except Exception:
        return ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9"]


def fallback_svg(ir, out_dir, reason):
    """Editable, source-bound figure.svg via svgkit only (no matplotlib)."""
    import svgkit
    canvas = ir.get("canvas", {})
    W, H = canvas.get("width_mm", 180), canvas.get("height_mm", 120)
    colors = _palette_colors()
    layers = []
    chart = ir.get("chart")
    if chart and (ir.get("kind") == "source_value_chart" or not ir.get("entities")):
        rows = figkit.read_table(chart["data_path"])
        xcol, ycol, scol = chart.get("x"), chart.get("y"), chart.get("series")
        xkeys = list(dict.fromkeys(str(r.get(xcol)) for r in rows)) if xcol else [str(i + 1) for i in range(len(rows))]
        skeys = list(dict.fromkeys(str(r.get(scol)) for r in rows)) if scol else [""]
        vals = []
        for r in rows:
            v = figkit.to_float(r.get(ycol))
            e = figkit.to_float(r.get(chart.get("error"))) if chart.get("error") else None
            if v is not None:
                vals.append(v + (e or 0))
        vmax = max(vals) if vals else 1.0
        vmax = vmax if vmax > 0 else 1.0
        x0, y0, pw, ph = 18, H - 18, W - 30, H - 34
        els = [{"type": "line", "x1": x0, "y1": y0, "x2": x0 + pw, "y2": y0},
               {"type": "line", "x1": x0, "y1": y0, "x2": x0, "y2": y0 - ph}]
        for i in range(5):
            yv = vmax * i / 4
            yy = y0 - ph * i / 4
            els.append({"type": "line", "x1": x0 - 1, "y1": yy, "x2": x0, "y2": yy})
            els.append({"type": "text", "x": x0 - 2, "y": yy, "text": f"{yv:.3g}",
                        "anchor": "end", "font_pt": 6})
        n_x, n_s = max(1, len(xkeys)), max(1, len(skeys))
        gw = pw / n_x
        bw = 0.8 * gw / n_s
        bars = []
        for si, sk in enumerate(skeys):
            grp = [r for r in rows if not scol or str(r.get(scol)) == sk]
            for xi, xk in enumerate(xkeys):
                match = [r for r in grp if not xcol or str(r.get(xcol)) == xk]
                if not match:
                    continue
                r0 = match[0]
                v = figkit.to_float(r0.get(ycol))
                if v is None:
                    continue
                h = ph * max(0.0, v) / vmax
                bx = x0 + xi * gw + 0.1 * gw + si * bw
                bars.append({"type": "rect", "x": bx, "y": y0 - h, "w": bw * 0.92, "h": h,
                             "fill": colors[si % len(colors)], "stroke": "#000000",
                             "stroke_width": 0.2,
                             "id": f"bar_{si}_{xi}", "source": chart.get("data_source"),
                             "source_locator": f"{chart.get('data_path')} row {rows.index(r0)} col {ycol}",
                             "value": v})
        for xi, xk in enumerate(xkeys):
            bars.append({"type": "text", "x": x0 + xi * gw + gw / 2, "y": y0 + 4,
                         "text": clip(xk, 14), "font_pt": 6})
        layers.append({"id": "data", "label": "data marks (source-bound)", "elements": bars})
        layers.append({"id": "axes", "label": "axes", "elements": els})
        labels = [{"type": "text", "x": W / 2, "y": 6, "text": clip(ir.get("title", ""), 90),
                   "font_pt": 9, "font_weight": "bold"},
                  {"type": "text", "x": x0 + pw / 2, "y": H - 4,
                   "text": chart.get("x_label", xcol or ""), "font_pt": 7},
                  {"type": "text", "x": 4, "y": y0 - ph - 3,
                   "text": chart.get("y_label", ycol or ""), "font_pt": 7, "anchor": "start"}]
        for si, sk in enumerate(skeys):
            if sk:
                labels.append({"type": "rect", "x": W - 26, "y": 12 + si * 6, "w": 4, "h": 3,
                               "fill": colors[si % len(colors)]})
                labels.append({"type": "text", "x": W - 20, "y": 13.5 + si * 6, "text": clip(sk, 16),
                               "font_pt": 6, "anchor": "start"})
        layers.append({"id": "labels", "label": "labels & legend", "elements": labels})
    else:
        ents = ir.get("entities", [])
        rels = ir.get("relations", [])
        n = max(1, len(ents))
        cols = max(1, math.ceil(math.sqrt(n)))
        rows_n = math.ceil(n / cols)
        cw, ch = (W - 20) / cols, (H - 20) / rows_n
        pos = {}
        nodes = []
        for i, e in enumerate(ents):
            cx = 10 + (i % cols) * cw + cw / 2
            cy = 12 + (i // cols) * ch + ch / 2
            pos[e["id"]] = (cx, cy)
            bw, bh = min(34, cw - 6), min(12, ch - 6)
            nodes.append({"type": "rect", "x": cx - bw / 2, "y": cy - bh / 2, "w": bw, "h": bh,
                          "rx": 1.5, "fill": "#ffffff",
                          "stroke": colors[i % len(colors)], "stroke_width": 0.5,
                          "id": f"node_{e['id']}", "source": e.get("source"),
                          "source_locator": e.get("source_locator"), "category": e.get("category")})
            nodes.append({"type": "text", "x": cx, "y": cy, "text": clip(e.get("label", e["id"]), 24),
                          "font_pt": 7, "id": f"label_{e['id']}", "source": e.get("source")})
        edges = []
        marker = {"activates": "arr-activate", "causes": "arr-activate", "sequence": "arr-activate",
                  "flows_to": "arr-activate", "upstream_of": "arr-activate", "feedback": "arr-activate",
                  "inhibits": "bar-inhibit", "modifies": "arr-activate", "transports": "arr-open",
                  "encodes": "arr-open"}
        for r in rels:
            a, b = pos.get(r["from"]), pos.get(r["to"])
            if not a or not b:
                continue
            el = {"type": "line", "x1": a[0], "y1": a[1], "x2": b[0], "y2": b[1],
                  "stroke": "#333333", "stroke_width": 0.4,
                  "id": f"edge_{r['id']}", "source": r.get("source"),
                  "source_locator": r.get("source_locator")}
            if marker.get(r["type"]):
                el["marker_end"] = marker[r["type"]]
            if r["type"] in ("modifies", "transports", "feedback"):
                el["dash"] = "2,1"
            edges.append(el)
            edges.append({"type": "text", "x": (a[0] + b[0]) / 2, "y": (a[1] + b[1]) / 2 - 1.5,
                          "text": r.get("label") or r["type"], "font_pt": 5, "fill": "#555555"})
        layers.append({"id": "edges", "label": "relations", "elements": edges})
        layers.append({"id": "nodes", "label": "entities", "elements": nodes})
        layers.append({"id": "labels", "label": "title", "elements": [
            {"type": "text", "x": W / 2, "y": 5, "text": clip(ir.get("title", ""), 90),
             "font_pt": 9, "font_weight": "bold"}]})
    scene = {"canvas": {"width_mm": W, "height_mm": H,
                        "background": canvas.get("background", "#ffffff")},
             "title": ir.get("title", ""),
             "desc": "auto_graphics stdlib fallback (renderer unavailable); editable, source-bound.",
             "layers": layers}
    path = svgkit.write_svg(Path(out_dir) / "figure.svg", scene)
    ir.setdefault("uncertainty", []).append(
        {"item": "render", "reason": f"matplotlib/renderer unavailable ({reason}); "
         "stdlib svgkit fallback layout produced an editable source-bound SVG "
         "(not the engine's compartment-aware layout); PNG/PDF not rendered",
         "impact": "fallback figure.svg only", "handling": "human_confirm"})
    emap = ir.setdefault("provenance", {}).setdefault("element_map", {})
    for e in ir.get("entities", []):
        emap[f"node_{e['id']}"] = {"source": e.get("source"), "source_locator": e.get("source_locator"),
                                   "glyph": "node", "label": e["label"]}
    for r in ir.get("relations", []):
        emap[f"edge_{r['id']}"] = {"source": r.get("source"), "source_locator": r.get("source_locator"),
                                   "glyph": "edge", "type": r["type"], "from": r["from"], "to": r["to"]}
    return [{"name": "figure.svg", "path": str(path), "format": "svg", "role": "svg"}]


# ── assemble.py-equivalent validate + build + result path ────────────────────

def compute_status(ir, validation, render_ok):
    if not validation.get("ok") or not render_ok:
        return "partial"
    for u in ir.get("uncertainty", []):
        if u.get("handling") == "human_confirm":
            return "partial"
    return "success"


def run(args):
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(args.work)
    work_dir.mkdir(parents=True, exist_ok=True)

    case = figkit.load_case(args.input)
    materials = figkit.list_materials(args.input)
    store = Store(case, materials)
    store.register_sources(materials)
    store.parse_all()
    kind = detect_kind(args.kind, case, store)
    ir = base_ir(case, kind, store)
    finalize(ir, store, case, kind)
    if case.get("case_id") and case["case_id"] != "unknown-case":
        ir["case_id"] = case["case_id"]
    figkit.write_json(work_dir / "figure_ir.json", ir)

    # ---- same path as assemble.py ----
    validation = figkit.validate_ir(ir)
    figkit.write_json(out_dir / "validation.json", validation)
    artifacts, render_info = [], {}
    render_ok = False
    if validation["ok"]:
        try:
            if kind == "source_value_chart" or (ir.get("chart") and kind == "graphical_abstract"
                                                and not ir.get("entities")):
                import render_chart
                render_info = render_chart.render(ir, out_dir, None)
            else:
                import render_diagram
                render_info = render_diagram.render(ir, out_dir)
            artifacts = render_info.get("artifacts", [])
            render_ok = True
        except Exception as e:  # noqa: BLE001 - honest fallback, never fabricate
            traceback.print_exc()
            try:
                artifacts = fallback_svg(ir, out_dir, f"{type(e).__name__}: {e}")
                render_info = {"fallback": True, "reason": str(e)}
            except Exception as e2:  # noqa: BLE001
                ir.setdefault("uncertainty", []).append(
                    {"item": "render", "reason": f"{type(e).__name__}: {e}; fallback also failed: {e2}",
                     "impact": "figure not rendered", "handling": "human_confirm"})
    else:
        ir.setdefault("uncertainty", []).append(
            {"item": "validation", "reason": "; ".join(validation["errors"]),
             "impact": "figure not rendered; IR saved for repair", "handling": "human_confirm"})
        # robustness: a diagram kind with no extractable entities but a REAL bound
        # data table can still deliver the chart (result panel) as an honest partial.
        ch = ir.get("chart") or {}
        if ch.get("data_path") and Path(ch["data_path"]).exists():
            try:
                import render_chart
                render_info = render_chart.render(ir, out_dir, None)
                artifacts = render_info.get("artifacts", [])
            except Exception as e:  # noqa: BLE001
                try:
                    artifacts = fallback_svg(ir, out_dir, f"{type(e).__name__}: {e}")
                    render_info = {"fallback": True, "reason": str(e)}
                except Exception:
                    artifacts = []
            if artifacts:
                ir["uncertainty"].append(
                    {"item": "partial figure", "reason": "entity/relation extraction incomplete; "
                     "rendered the bound data chart only (honest partial)", "handling": "human_confirm"})

    export_report = None
    if artifacts:
        try:
            import export_check
            export_report = export_check.check(ir, out_dir)
            figkit.write_json(out_dir / "export_report.json", export_report)
        except Exception as e:  # noqa: BLE001
            export_report = {"overall": "warn", "error": str(e)}

    figkit.write_json(out_dir / "figure_ir.json", ir)
    if ir.get("provenance", {}).get("element_map") or ir.get("provenance", {}).get("data_map"):
        figkit.write_json(out_dir / "provenance.json", ir["provenance"])

    status = compute_status(ir, validation, render_ok)
    notes = AUTO_NOTE
    if not validation["ok"]:
        notes += " IR validation errors: " + "; ".join(validation["errors"])
    elif validation["warnings"]:
        notes += " warnings: " + "; ".join(validation["warnings"][:6])
    result = figkit.build_result(case, ir, artifacts, status, validation, export_report, notes)
    result["render_info"] = {k: render_info.get(k) for k in
                             ("n_rows", "n_entities", "n_relations", "layout", "font_used",
                              "data_path", "fallback", "reason") if k in render_info}
    result["autopilot"] = {"kind": kind, "n_materials": len(materials),
                           "n_entities": len(ir.get("entities", [])),
                           "n_relations": len(ir.get("relations", [])),
                           "work_ir": str(work_dir / "figure_ir.json")}
    figkit.write_result(out_dir, result)
    print(json.dumps({"status": status, "case_id": case["case_id"], "kind": kind,
                      "validation_ok": validation["ok"], "errors": validation["errors"],
                      "n_artifacts": len(artifacts),
                      "export_overall": (export_report or {}).get("overall"),
                      "result": str(out_dir / "result.json")}, ensure_ascii=False, indent=2))
    return 0 if status in ("success", "partial") else 1


# ── honest fallbacks (NEVER exit without result.json) ────────────────────────

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


def main():
    ap = argparse.ArgumentParser(description="graphics track autopilot (auto-extract Figure IR + run engine)")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--kind", default=None)
    args = ap.parse_args()

    case, sources, kind = {}, [], None
    try:
        if figkit is None:
            raise RuntimeError("cannot import sibling figkit.py")
        return run(args)
    except Exception as e:
        traceback.print_exc()
        try:
            case = figkit.load_case(args.input) if figkit else {}
            kind = args.kind or "mechanism_pathway"
            try:
                mats = figkit.list_materials(args.input) if figkit else []
                sources = [{"id": f"S{i}", "locator": m["path"], "name": m["name"],
                            "kind": "table" if m.get("ext") in (".csv", ".tsv", ".json") else "text"}
                           for i, m in enumerate(mats, 1)]
            except Exception:
                sources = []
            ir = {"ir_version": "1.0", "case_id": case.get("case_id", "unknown-case"),
                  "kind": kind, "sources": sources,
                  "uncertainty": [{"item": "pipeline", "reason": f"{type(e).__name__}: {e}",
                                   "handling": "human_confirm"}]}
            result = figkit.build_result(case, ir, [], "failed",
                                         notes=AUTO_NOTE + f" FATAL: {e}")
            result["error"] = f"{type(e).__name__}: {e}"
            figkit.write_result(args.out, result)
        except Exception as e2:
            emergency_result(case, args.out, f"{e}; fallback also failed: {e2}",
                             sources=sources, kind=kind)
        print(json.dumps({"status": "failed", "error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())