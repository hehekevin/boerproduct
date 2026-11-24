"""auto_arena_read.py — deterministic "autopilot" for the week4 READING track
(product-arena architecture: assemble.py + arena_read_engine.py + readkit/figkit).

Reads the ACTUAL organizer-provided local materials under --input, auto-extracts
a complete arena reading IR (sources + items/segments/nanopubs/nodes+edges with
exact paragraph locators and verbatim quotes), writes it to --work, then runs the
PACKAGE'S OWN assemble.py (arena_read_engine.validate_ir + build + figkit result
writer) so the validate+build path is identical to the manual workflow.
Stdlib only; additive — does not modify any sibling module.

Usage:
  PYTHONDONTWRITEBYTECODE=1 python auto_arena_read.py --input /input --out /app/output \
      [--work /app/work] [--kind KIND]

Design rules (mirrors engines/search/auto_search.py):
  * Never fabricate: every value/quote comes from real file content; missing ->
    not_reported / insufficient_evidence + human_confirm, never invented.
  * Judgment-heavy output (translation draft, entity typing, assertion splitting)
    uses deterministic evidence-grounded heuristics flagged kind=inferred +
    human_confirm => overall run status forced to "partial" (honest).
  * Defensive extraction: a bad/missing file becomes an honest gap, never a crash.
  * The WHOLE pipeline is wrapped: on ANY exception an honest result.json is
    still written (status partial/failed) preserving output_contract + case_id.
  * After this baseline runs, the agent may refine work/ir.json within budget and
    re-run assemble.py to improve judgment fields.
"""
from __future__ import annotations

import argparse
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
    import arena_read_engine as engine
except Exception:  # catastrophic import failure -> emergency writer below
    figkit = None
    readkit = None
    engine = None

AUTO_NOTE = ("auto_arena_read autopilot: deterministic extraction from ACTUAL local "
             "materials + the package's own assemble.py (arena_read_engine validate "
             "+ build + result writer). No online retrieval, no fabricated "
             "values/quotes/metadata. Judgment fields use documented evidence-grounded "
             "heuristics flagged human_confirm; refine work/ir.json and re-run "
             "assemble.py to improve.")

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
    "arena-literature-translation": "translation",
    "arena-document-parse": "document_parse",
    "arena-nanopublication": "nanopublication",
    "arena-knowledge-graph": "knowledge_graph",
}

NOTICE_RE = re.compile(r"^\s*(?:SYNTHETIC\b|EXAMPLE SOURCE MATERIAL)|"
                       r"\bNOT a real paper\b|interface demo", re.I)

NUM_RE = re.compile(r"\d+(?:\.\d+)?")
CITE_RE = re.compile(r"\[\d+(?:[,\u2013\-]\s*\d+)*\]")

# Controlled predicate verbs (engine NP_PREDICATES) + past-tense normalization.
PRED_VERBS = {"increases": "increases", "increase": "increases", "increased": "increases",
              "decreases": "decreases", "decrease": "decreases", "decreased": "decreases",
              "causes": "causes", "cause": "causes", "caused": "causes",
              "inhibits": "inhibits", "inhibit": "inhibits", "inhibited": "inhibits",
              "activates": "activates", "activate": "activates", "activated": "activates",
              "binds": "binds", "bind": "binds", "bound": "binds",
              "measures": "measures", "measure": "measures", "measured": "measures",
              "uses": "uses", "use": "uses", "used": "uses",
              "compares": "compares", "compare": "compares", "compared": "compares",
              "outperforms": "outperforms", "outperform": "outperforms",
              "outperformed": "outperforms",
              "supports": "supports", "support": "supports", "supported": "supports",
              "contradicts": "contradicts", "contradict": "contradicts",
              "reports": "reports", "report": "reports", "reported": "reports",
              "contains": "contains", "contain": "contains", "contained": "contains",
              "produces": "produces", "produce": "produces", "produced": "produces",
              "improves": "improves", "improve": "improves", "improved": "improves",
              "retained": "reports", "retains": "reports", "retain": "reports"}
PRED_RE = re.compile(r"\b(" + "|".join(sorted(PRED_VERBS, key=len, reverse=True)) + r")\b", re.I)
# improves is in NP_PREDICATES but not EDGE_TYPES -> documented normalization
EDGE_MAP = {"improves": "increases"}

INSTRUMENTS = ["XRD", "SEM", "TEM", "NMR", "FTIR", "UV-Vis", "UV\u2013Vis", "HPLC",
               "GC-MS", "AFM", "DLS", "PCR", "qPCR", "ELISA", "XPS", "Raman", "EDS",
               "STM", "SAXS", "WAXS", "TGA", "DSC", "ICP-MS", "LC-MS", "FIB", "EIS"]
METRIC_WORDS = {"stability", "efficiency", "crystallinity", "expression", "yield",
                "accuracy", "sensitivity", "selectivity", "capacity", "retention",
                "performance", "activity", "strength", "conductivity", "purity",
                "viability", "growth", "rate", "score", "auc", "f1"}
METHOD_WORDS = {"annealing", "coating", "spin-coating", "synthesis", "treatment",
                "assay", "screening", "sequencing", "microscopy", "spectroscopy",
                "simulation", "model", "modeling", "modelling", "training",
                "intervention", "randomization", "randomisation", "profiling",
                "staining", "centrifugation", "electrophoresis", "chromatography",
                "anneal", "doping", "sintering", "etching", "deposition"}

# Compact EN->ZH academic lexicon for the deterministic translation DRAFT.
# The draft is flagged kind=inferred + human_confirm; it is a starting point for
# the agent/human translator, never presented as a verified translation.
TERM_ZH = {
    "perovskite": "钙钛矿", "annealing": "退火", "thermal annealing": "热退火",
    "crystallinity": "结晶度", "stability": "稳定性", "efficiency": "效率",
    "solar cell": "太阳能电池", "solar cells": "太阳能电池", "film": "薄膜",
    "films": "薄膜", "thin film": "薄膜", "thin films": "薄膜",
    "nanoparticle": "纳米颗粒", "nanoparticles": "纳米颗粒", "graphene": "石墨烯",
    "catalyst": "催化剂", "catalysts": "催化剂", "battery": "电池",
    "batteries": "电池", "electrode": "电极", "electrodes": "电极",
    "protein": "蛋白质", "proteins": "蛋白质", "gene": "基因", "genes": "基因",
    "cell": "细胞", "cells": "细胞", "tissue": "组织", "tumor": "肿瘤",
    "tumour": "肿瘤", "patient": "患者", "patients": "患者", "cohort": "队列",
    "trial": "试验", "randomized": "随机", "randomised": "随机",
    "placebo": "安慰剂", "dose": "剂量", "dosage": "剂量",
    "expression": "表达", "marker": "标志物", "biomarker": "生物标志物",
    "pathway": "通路", "mechanism": "机制", "mutation": "突变",
    "sample": "样品", "samples": "样品", "specimen": "标本",
    "method": "方法", "methods": "方法", "result": "结果", "results": "结果",
    "conclusion": "结论", "conclusions": "结论", "abstract": "摘要",
    "introduction": "引言", "background": "背景", "discussion": "讨论",
    "limitation": "局限", "limitations": "局限性", "reference": "参考文献",
    "references": "参考文献", "study": "研究", "studies": "研究",
    "experiment": "实验", "experiments": "实验", "analysis": "分析",
    "measurement": "测量", "measurements": "测量", "data": "数据",
    "dataset": "数据集", "model": "模型", "models": "模型",
    "network": "网络", "networks": "网络", "algorithm": "算法",
    "training": "训练", "testing": "测试", "performance": "性能",
    "accuracy": "准确率", "precision": "精确率", "recall": "召回率",
    "temperature": "温度", "pressure": "压力", "concentration": "浓度",
    "solution": "溶液", "solvent": "溶剂", "reaction": "反应",
    "synthesis": "合成", "structure": "结构", "structures": "结构",
    "surface": "表面", "layer": "层", "layers": "层", "device": "器件",
    "devices": "器件", "material": "材料", "materials": "材料",
    "improved": "改善了", "improves": "改善", "improve": "改善",
    "increased": "增加了", "increases": "增加", "increase": "增加",
    "decreased": "降低了", "decreases": "降低", "decrease": "降低",
    "retained": "保留了", "retains": "保留", "retain": "保留",
    "observed": "观察到", "observe": "观察", "shows": "表明", "show": "表明",
    "showed": "表明", "suggests": "提示", "suggest": "提示",
    "indicates": "表明", "indicate": "表明", "demonstrates": "证明",
    "demonstrate": "证明", "conclude": "得出结论", "concluded": "得出结论",
    "we": "我们", "our": "我们的", "this": "该", "these": "这些",
    "those": "那些", "the": "", "a": "", "an": "", "of": "的", "and": "和",
    "or": "或", "with": "与", "without": "无", "for": "对于",
    "in": "在", "on": "在", "at": "在", "by": "通过", "from": "从",
    "to": "到", "as": "作为", "is": "是", "are": "是", "was": "曾",
    "were": "曾", "be": "是", "been": "已", "it": "它", "its": "其",
    "than": "比", "versus": "对比", "vs": "对比", "after": "之后",
    "before": "之前", "during": "期间", "under": "条件下", "over": "超过",
    "between": "之间", "both": "两者", "each": "每个", "all": "所有",
    "only": "仅", "also": "也", "however": "然而", "therefore": "因此",
    "thus": "因此", "moreover": "此外", "furthermore": "此外",
    "moderate": "适度", "initial": "初始", "final": "最终",
    "control": "对照", "controls": "对照组", "unannealed": "未退火",
    "annealed": "退火后", "tested": "测试", "test": "测试",
    "conditions": "条件", "condition": "条件", "batch": "批次",
    "outdoor": "户外", "degradation": "降解", "studied": "研究",
    "not": "未", "no": "无", "one": "一个", "two": "两个",
    "that": "", "which": "", "who": "", "whom": "", "whose": "",
    "where": "", "while": "", "when": "", "then": "然后", "than": "比",
    "under the tested conditions": "在所测试的条件下",
    "was used to": "被用于", "were used to": "被用于", "used to": "用于",
    "patterns": "图谱", "pattern": "图谱", "recorded": "记录",
    "check": "检查", "decomposition": "分解", "nitrogen": "氮气",
    "spin-coated": "旋涂", "spin": "旋", "coated": "涂覆",
    "before": "之前", "after": "之后", "initial": "初始",
}
UNIT_WORDS = {"C", "K", "F", "min", "h", "s", "ms", "nm", "um", "mm", "cm", "m",
              "km", "mg", "g", "kg", "mL", "L", "uL", "M", "mM", "uM", "nM",
              "mol", "mmol", "Pa", "kPa", "MPa", "GPa", "Hz", "kHz", "MHz",
              "GHz", "V", "mV", "A", "mA", "W", "kW", "eV", "keV", "MeV",
              "wt", "vol", "rpm", "kDa", "Da", "bp", "kb", "%"}


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
    """Paragraphs with ids. Explicit [Pn] markers / markdown headers are kept
    verbatim (marked=True); unmarked blank-line blocks get auto ids X1..Xn."""
    paras = []
    cur_id, cur_page, cur_section, marked, buf = None, None, None, False, []

    def flush():
        nonlocal buf, cur_id, cur_page, cur_section, marked
        body = "\n".join(buf).strip()
        if body:
            pid = cur_id or f"X{len(paras) + 1}"
            paras.append({"id": pid, "text": body, "page": cur_page,
                          "section": cur_section, "marked": marked})
        buf = []

    for ln in text.splitlines():
        hm = re.match(r"^#{1,6}\s+(.+?)\s*(?:\(([^)]*)\))?\s*$", ln)
        pm = re.match(r"^\s*\[(P\d+)\]\s*(.*)$", ln)
        if hm:
            flush()
            cur_id, marked = hm.group(1).strip(), True
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
            cur_id, cur_page, cur_section, marked = pm.group(1), None, None, True
            if pm.group(2):
                buf.append(pm.group(2))
            continue
        if not ln.strip():
            flush()
            cur_id, cur_page, cur_section, marked = None, None, None, False
            continue
        buf.append(ln)
    flush()
    if not paras and text.strip():
        paras.append({"id": "X1", "text": text.strip(), "page": None,
                      "section": None, "marked": False})
    # de-duplicate ids (keep first; later collisions get _2/_3 suffix)
    seen = {}
    for p in paras:
        if p["id"] in seen:
            seen[p["id"]] += 1
            p["id"] = f"{p['id']}_{seen[p['id']]}"
        else:
            seen[p["id"]] = 1
    for p in paras:
        if not p["section"]:
            m = re.match(r"^\s*(Abstract|Background|Introduction|Methods?|Materials?|"
                         r"Results?|Discussion|Conclusion|Limitations|References)\b\s*[:：]?",
                         p["text"], re.I)
            if m:
                p["section"] = m.group(1).strip()
    return paras


# ── material store ───────────────────────────────────────────────────────────

class Store:
    def __init__(self, case, materials):
        self.case = case
        self.sources = []
        self.files = []
        self.documents = []
        self.workorder_raw = {}
        self.errors = []
        self.uncertainty = []

    def register(self, materials):
        for i, m in enumerate(materials, 1):
            sid = f"S{i}"
            ext = (m.get("ext") or "").lstrip(".") or "file"
            self.sources.append({"id": sid, "path": m["path"], "name": m["name"],
                                 "type": ext})
            self.files.append({"sid": sid, "path": m["path"], "name": m["name"],
                               "ext": ext, "role": None})

    def add_unc(self, item, reason, handling="human_confirm"):
        self.uncertainty.append({"item": item, "reason": reason, "handling": handling})

    def parse_all(self, input_dir):
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
            self.workorder_raw[f["name"]] = data
            return
        text = read_material_text(f["path"])
        f["text"] = text
        f["paragraphs"] = parse_paragraphs(text)
        f["role"] = "document"
        self.documents.append(f)

    def body_paragraphs(self):
        """Non-notice paragraphs of document materials (the actual paper body)."""
        for d in self.documents:
            for p in d.get("paragraphs", []):
                if NOTICE_RE.search(p["text"]) and len(p["text"]) < 200:
                    continue
                yield d, p

    def ev(self, d, p, quote):
        e = {"source": d["sid"], "source_id": d["sid"],
             "paragraph_id": p["id"], "quote": clip(quote, 400)}
        if p.get("page") is not None:
            e["page"] = p["page"]
        return e


def gap_record(rid, reason, **extra):
    rec = {"id": rid, "status": "insufficient_evidence", "kind": "reported",
           "human_confirm": True, "reason": reason, "evidence": [],
           "note": reason + "; needs human_confirm"}
    rec.update(extra)
    return rec


# ── kind detection ───────────────────────────────────────────────────────────

def detect_kind(args_kind, case, store):
    valid = engine.KINDS if engine else {"document_parse", "translation",
                                         "summary_notes", "nanopublication",
                                         "knowledge_graph"}
    if args_kind:
        k = args_kind.strip().replace("-", "_")
        if k in valid:
            return k
    skill = SCRIPT_DIR / "SKILL.md"
    if skill.exists():
        try:
            head = skill.read_text(encoding="utf-8", errors="replace")[:2500]
            m = re.search(r"^name:\s*([a-z0-9-]+)\s*$", head, re.M)
            if m and m.group(1) in SKILL_KIND:
                return SKILL_KIND[m.group(1)]
        except Exception:
            pass
    blob = ((case.get("task_md") or "") + " " +
            " ".join(f["name"].lower() for f in store.files)).lower()
    for kind, kws in (("translation", ["translat", "bilingual", "glossary"]),
                      ("nanopublication", ["nanopub", "assertion", "trig"]),
                      ("knowledge_graph", ["knowledge graph", "graph", "entities", "relations"]),
                      ("summary_notes", ["summary", "notes"]),
                      ("document_parse", ["parse", "target-fields", "fields"])):
        if any(kw in blob for kw in kws):
            return kind
    return "document_parse"


# ── shared extraction primitives ─────────────────────────────────────────────

def best_sentence(store, query_text, min_hits=1):
    qtok = tokens(query_text)
    if not qtok:
        return None
    best = None
    for d, p in store.body_paragraphs():
        for s in sentences(p["text"]):
            hits = qtok & tokens(s)
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


def provenance_meta(store):
    """Real authors/year/doi from the material (never invented)."""
    meta = {}
    for d, p in store.body_paragraphs():
        t = p["text"]
        if "authors" not in meta:
            am = re.search(r"Authors?\s*[:：]\s*([^\n]+?)(?=\.\s*(?:Year|DOI|Affiliations?)\s*[:：]|\.\s*$|$)", t)
            names = None
            if am:
                names = am.group(1)
            elif re.search(r"\b(?:University|Institute|Department|Laboratory|College|"
                           r"School|Academy)\b", t) and len(t) < 300 and \
                    not re.match(r"^\s*(Abstract|Methods|Results)", t, re.I):
                names = re.sub(r"\([^)]*\)", "", t)
                names = re.sub(r"^\s*Authors?\s*[:：]\s*", "", names, flags=re.I)
            if names:
                names = re.sub(r"\([^)]*\)", "", names)
                parts = [x.strip(" .") for x in re.split(r"\s+and\s+|,\s*|;\s*", names)
                         if x.strip(" .")]
                if parts and all(len(x) < 60 for x in parts):
                    meta["authors"] = parts
        if "doi" not in meta:
            dm = re.search(r"10\.\d{4,9}/[^\s,;\"'\])]+", t)
            if dm:
                meta["doi"] = dm.group(0)
        if "year" not in meta:
            ym = re.search(r"\bYear\s*[:：]\s*((?:19|20)\d{2})\b", t) or \
                re.search(r"\b(?:19|20)\d{2}\b", t)
            if ym:
                meta["year"] = ym.group(1) if ym.lastindex else ym.group(0)
    return meta


def split_triples(store):
    """Deterministic atomic-assertion split: sentences containing a controlled
    predicate verb -> (subject, predicate, object, conditions, doc, para, sentence)."""
    out = []
    seen = set()
    lead = re.compile(r"^(?:we\s+(?:conclude|find|found|show|showed|observe|observed|"
                      r"demonstrate|demonstrated|report|reported)\s+that|"
                      r"(?:the|our)\s+(?:results?|study|findings?|data)\s+"
                      r"(?:show|shows|showed|indicate|indicates|suggest|suggests|demonstrate|"
                      r"demonstrates|confirm|confirms)\s+that|"
                      r"(?:this|the)\s+(?:study|paper|work)\s+|"
                      r"it\s+(?:is|was)\s+(?:shown|found|reported)\s+that|"
                      r"the\s+|these\s+|this\s+|our\s+)", re.I)
    for d, p in store.body_paragraphs():
        for s in sentences(p["text"]):
            m = PRED_RE.search(s)
            if not m:
                continue
            pred = PRED_VERBS[m.group(1).lower()]
            subj = s[:m.start()].strip(" ,;:")
            # strip section-label prefix ("Conclusion: ...") and leading connectives
            subj = re.sub(r"^(?:Abstract|Methods?|Results?|Conclusion|Discussion|"
                          r"Background|Introduction|Limitations)\s*[:：]\s*", "",
                          subj, flags=re.I)
            subj = lead.sub("", subj).strip(" ,;:")
            # passive voice: "XRD was used ..." -> drop trailing auxiliary
            passive = bool(re.search(r"\b(?:was|were|is|are|has|have|had|been|being)\s*$",
                                     subj, re.I))
            subj = re.sub(r"\s+(?:was|were|is|are|has|have|had|can|could|will|would|"
                          r"may|might|did|does|do|been|being)\s*$", "", subj,
                          flags=re.I).strip(" ,;:")
            obj_full = s[m.end():].strip(" ,;:")
            obj_full = re.sub(r"^(?:that|the|a|an)\s+", "", obj_full, flags=re.I)
            # "used to check crystallinity" -> object "crystallinity"
            obj_full = re.sub(r"^to\s+[a-z]+\s+", "", obj_full, flags=re.I)
            cm = re.search(r"\b(under|after|when|while|at)\b", obj_full, re.I)
            obj, cond = obj_full, None
            if cm and cm.start() > 3:
                obj = obj_full[:cm.start()].strip(" ,;:")
                cond = obj_full[cm.start():].strip(" ,;:.")
            obj = obj.rstrip(" .;:")
            if len(subj) < 3 or len(obj) < 3:
                continue
            key = (subj.lower(), pred, obj.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append({"subject": clip(subj, 120), "predicate": pred,
                        "object": clip(obj, 160), "conditions": cond,
                        "passive": passive, "orig_verb": m.group(1).lower(),
                        "doc": d, "para": p, "sentence": s})
    return out


# ── document_parse / summary_notes ───────────────────────────────────────────

FIELD_LABELS = {
    "title": r"标题|title", "authors": r"作者|authors?",
    "abstract": r"摘要|abstract", "methods": r"方法|methods?|materials?\s+and\s+methods?",
    "results": r"结果|results?", "conclusion": r"结论|conclusions?",
    "limitations": r"局限|limitations?", "research_question": r"研究问题|research\s+question",
    "data": r"数据|data", "doi": r"doi", "year": r"年份|year",
    "keywords": r"关键词|keywords?",
}


def locate_field(store, fid, ftext=None):
    """Return (value, doc, para, quote) or None for a requested field."""
    label = re.sub(r"[_\-]+", " ", str(ftext or fid)).strip()
    lab_re = FIELD_LABELS.get(str(fid).lower(), re.escape(label))
    # 1) labeled paragraph "Abstract: ..." / "Methods: ..."
    pat = re.compile(r"^\s*(?:" + lab_re + r")\s*[:：]\s*(.+)", re.I | re.S)
    for d, p in store.body_paragraphs():
        m = pat.match(p["text"])
        if m:
            return m.group(1).strip(), d, p, p["text"]
    # 2) heading paragraph equal to the label -> its body is the next paragraph
    paras = list(store.body_paragraphs())
    for i, (d, p) in enumerate(paras):
        if p.get("marked") and re.fullmatch(r"(?:" + lab_re + r")", p["text"].strip(), re.I):
            if i + 1 < len(paras):
                d2, p2 = paras[i + 1]
                return p2["text"], d2, p2, p2["text"]
            return p["text"], d, p, p["text"]
    low = str(fid).lower()
    if low == "title":
        for d, p in store.body_paragraphs():
            t = p["text"]
            tm = re.match(r"^\s*Title\s*[:：]\s*(.+?)(?=\.\s*(?:Authors?|Year|DOI|"
                          r"Affiliations?)\s*[:：]|\.\s*$|$)", t, re.I | re.S)
            if tm:
                return tm.group(1).strip(), d, p, t
            return t, d, p, t
    if low in ("authors", "author"):
        for d, p in store.body_paragraphs():
            t = p["text"]
            am = re.search(r"Authors?\s*[:：]\s*([^\n]+?)(?=\.\s*(?:Year|DOI|"
                           r"Affiliations?)\s*[:：]|\.\s*$|$)", t)
            names = None
            if am:
                names = am.group(1)
            elif re.search(r"\b(?:University|Institute|Department|Laboratory|College|"
                           r"School|Academy)\b", t) and len(t) < 300:
                names = re.sub(r"\([^)]*\)", "", t)
            elif re.match(r"^\s*[A-Z]\.\s*[A-Za-z_]+", t) and len(t) < 300:
                names = re.sub(r"\([^)]*\)", "", t)
            if names:
                names = re.sub(r"\([^)]*\)", "", names)
                parts = [x.strip(" .") for x in re.split(r"\s+and\s+|,\s*|;\s*", names)
                         if x.strip(" .")]
                return (parts or t), d, p, t
    if low == "doi":
        for d, p in store.body_paragraphs():
            dm = re.search(r"10\.\d{4,9}/[^\s,;\"'\])]+", p["text"])
            if dm:
                return dm.group(0), d, p, exact_quote(p["text"], dm.group(0)) or p["text"]
    if low == "year":
        for d, p in store.body_paragraphs():
            ym = re.search(r"\b(?:19|20)\d{2}\b", p["text"])
            if ym:
                return ym.group(0), d, p, exact_quote(p["text"], ym.group(0)) or p["text"]
    # 3) full-token lexical sentence match
    qtok = tokens(label)
    if qtok:
        for d, p in store.body_paragraphs():
            for s in sentences(p["text"]):
                if qtok <= tokens(s):
                    return s, d, p, s
    return None


def build_parse(ir, store, case, input_dir):
    kind = ir["kind"]
    requested = None
    if engine is not None:
        try:
            requested = engine.load_requested_fields(input_dir)
        except Exception:
            requested = None
    if not requested:
        requested = (engine.DEFAULT_FIELDS[kind] if engine else
                     ["title", "authors", "abstract", "methods", "results", "conclusion"])
    ftexts = {}
    for name, data in store.workorder_raw.items():
        def walk(o):
            if isinstance(o, dict):
                rid = o.get("field_id") or o.get("id")
                tx = o.get("text") or o.get("description") or o.get("label")
                if rid and tx:
                    ftexts[str(rid)] = str(tx)
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(data)
    for fid in requested:
        if not fid:
            continue
        found = locate_field(store, fid, ftexts.get(fid))
        if found:
            val, d, p, quote = found
            ir["items"].append({"id": fid, "field_id": fid, "value": val,
                                "kind": "reported", "status": "reported",
                                "evidence": [store.ev(d, p, quote)]})
        else:
            ir["items"].append({"id": fid, "field_id": fid, "value": None,
                                "kind": "reported", "status": "not_reported",
                                "human_confirm": True, "evidence": [],
                                "reason": "requested field not located in provided material",
                                "note": "not reported in the provided material; never fabricated"})
    # section hierarchy from labeled / heading paragraphs
    sec_ids = set()
    for d, p in store.body_paragraphs():
        title = None
        m = re.match(r"^\s*(Abstract|Background|Introduction|Methods?|Materials?|"
                     r"Results?|Discussion|Conclusion|Limitations|References|"
                     r"Title(?:\s+and\s+authors)?)\s*[:：]?\s*$", p["text"], re.I)
        m2 = re.match(r"^\s*(Abstract|Methods?|Results?|Conclusion|Limitations|"
                      r"Introduction|Background|Discussion)\s*[:：]", p["text"], re.I)
        if p.get("marked") and m:
            title = m.group(1)
        elif m2:
            title = m2.group(1)
        elif p.get("marked") and len(p["text"]) < 80 and not NOTICE_RE.search(p["text"]):
            title = p["text"].strip()
        if title:
            sid = f"SEC{len(ir['sections']) + 1}"
            while sid in sec_ids:
                sid += "x"
            sec_ids.add(sid)
            ir["sections"].append({"id": sid, "title": title, "level": 1,
                                   "parent_id": None, "paragraph_ids": [p["id"]],
                                   "source_id": d["sid"]})
    if not ir["sections"]:
        store.add_unc("sections", "no explicit section headings located; section "
                      "hierarchy left empty (honest gap)", "note")


# ── translation ──────────────────────────────────────────────────────────────

def collect_glossary(store, case):
    pairs = []
    seen = set()

    def add(st, tt):
        st, tt = str(st).strip(), str(tt).strip()
        if st and tt and (st.lower(), tt) not in seen:
            seen.add((st.lower(), tt))
            pairs.append({"source_term": st, "target_term": tt})

    for name, data in store.workorder_raw.items():
        def walk(o):
            if isinstance(o, dict):
                if o.get("source_term") and o.get("target_term"):
                    add(o["source_term"], o["target_term"])
                for k, v in o.items():
                    if isinstance(v, str) and re.search(r"[\u4e00-\u9fff]", v) and \
                            re.match(r"^[A-Za-z][A-Za-z \-]*$", str(k)):
                        add(k, v)
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(data)
    task = case.get("task_md") or ""
    for m in re.finditer(r"([A-Za-z][A-Za-z \-]{2,})\s*(?:->|→|:|：)\s*"
                         r"([\u4e00-\u9fff]{2,})", task):
        add(m.group(1), m.group(2))
    # term lists like "lock the glossary (perovskite/annealing/crystallinity)":
    # lock standard terminology from the built-in academic lexicon
    for m in re.finditer(r"glossary[^(\n]*\(([^)]+)\)", task, re.I):
        for term in re.split(r"[/,;、]", m.group(1)):
            term = term.strip()
            if term and term.lower() in TERM_ZH and TERM_ZH[term.lower()]:
                add(term, TERM_ZH[term.lower()])
    return pairs


def translate_draft(text, glossary):
    """Deterministic glossary+lexicon draft. Numbers, units and citation markers
    are preserved VERBATIM (protected placeholders). Flagged inferred downstream."""
    protected = []

    def protect(m):
        protected.append(m.group(0))
        # private-use-area placeholder: contains NO digits/letters, so the
        # number/word passes below can never re-match inside a placeholder
        return "\x00" + chr(0xE000 + len(protected) - 1) + "\x00"

    work = CITE_RE.sub(protect, text)
    work = re.sub(r"\d+(?:\.\d+)?(?:\s*(?:%|" + "|".join(
        re.escape(u) for u in sorted(UNIT_WORDS, key=len, reverse=True)) + r"))?",
        protect, work)
    # longest-first phrase replacement; glossary wins ties (locked terminology)
    entries = [(g["source_term"], g["target_term"], 0) for g in glossary]
    entries += [(st, tt, 1) for st, tt in TERM_ZH.items()]
    entries.sort(key=lambda e: (-len(e[0]), e[2]))
    done = set()
    for st, tt, _prio in entries:
        if st.lower() in done:
            continue
        done.add(st.lower())
        if not tt:
            work = re.sub(r"\b" + re.escape(st) + r"\b", "", work, flags=re.I)
        else:
            work = re.sub(r"\b" + re.escape(st) + r"\b", tt, work, flags=re.I)
    # word-level fallback for remaining English words
    def word_sub(m):
        w = m.group(0)
        if w in UNIT_WORDS:
            return w
        zh = TERM_ZH.get(w.lower())
        if zh is None and w.lower().endswith("s"):
            zh = TERM_ZH.get(w.lower()[:-1])
        return zh if zh is not None else w
    work = re.sub(r"[A-Za-z][A-Za-z\-']*", word_sub, work)
    for i, orig in enumerate(protected):
        work = work.replace("\x00" + chr(0xE000 + i) + "\x00", orig)
    # tidy spacing around CJK
    work = re.sub(r"[ \t]+", " ", work).strip()
    work = re.sub(r"\s*([，。；：、])\s*", r"\1", work)
    work = re.sub(r"(?<=[\u4e00-\u9fff]) (?=[\u4e00-\u9fff])", "", work)
    work = re.sub(r"\s+([,.!?;:])", r"\1", work)
    return work.strip()


def build_translation(ir, store, case, input_dir=None):
    glossary = collect_glossary(store, case)
    # paragraph range from task.md (e.g. "P1-P3"), else all body paragraphs
    task = case.get("task_md") or ""
    rng = re.search(r"\bP(\d+)\s*(?:[-–~]|\bto\b)\s*P?(\d+)\b", task, re.I)
    lo, hi = (int(rng.group(1)), int(rng.group(2))) if rng else (None, None)
    chosen = []
    for d, p in store.body_paragraphs():
        if lo is not None:
            pm = re.fullmatch(r"P(\d+)", p["id"])
            if pm and not (lo <= int(pm.group(1)) <= hi):
                continue
            if not pm and not p.get("marked"):
                continue
        chosen.append((d, p))
    if not chosen:
        chosen = list(store.body_paragraphs())
    # keep only glossary entries actually relevant (source term appears)
    all_text = " ".join(p["text"] for _, p in chosen).lower()
    used = [g for g in glossary if g["source_term"].lower() in all_text]
    for g in glossary:
        if g not in used and g["source_term"].lower() in TERM_ZH:
            used.append(g)
    ir["glossary"] = used
    for i, (d, p) in enumerate(chosen, 1):
        src = p["text"]
        tgt = translate_draft(src, used)
        ir["segments"].append({
            "id": f"seg{i}", "paragraph_id": p["id"],
            "source_text": src, "target_text": tgt,
            "kind": "inferred", "status": "reported", "human_confirm": True,
            "note": "deterministic glossary+lexicon DRAFT translation (numbers/units/"
                    "citations preserved verbatim); not a verified human translation; "
                    "human_confirm",
            "uncertainty": "machine draft; terminology/fluency require human review",
            "evidence": [store.ev(d, p, src)]})
    if not ir["segments"]:
        ir["segments"].append(gap_record("seg1", "no translatable source paragraph "
                                         "located in provided material",
                                         source_text=None, target_text=None))
    ir["uncertainty"].append({"item": "translation draft",
                              "reason": "target_text is a deterministic stdlib glossary/lexicon "
                                        "draft, NOT a verified translation; every segment "
                                        "requires human_confirm",
                              "handling": "human_confirm"})


# ── nanopublication ──────────────────────────────────────────────────────────

def build_nanopubs(ir, store, case, input_dir=None):
    meta = provenance_meta(store)
    triples = [t for t in split_triples(store) if not t.get("passive")]
    for i, t in enumerate(triples[:15], 1):
        assertion = {"subject": t["subject"], "predicate": t["predicate"],
                     "object": t["object"]}
        if t["conditions"]:
            assertion["conditions"] = t["conditions"]
        prov = {"source_id": t["doc"]["sid"]}
        prov.update(meta)
        if not meta:
            prov["note"] = "authors/year/doi not present in provided material; not invented"
        note = ("atomic assertion split deterministically at a controlled predicate "
                "verb; quote is the verbatim source sentence")
        if t.get("orig_verb") and t["orig_verb"] != t["predicate"]:
            note += f"; source verb '{t['orig_verb']}' normalized to '{t['predicate']}'"
        ir["nanopubs"].append({
            "id": f"NP{len(ir['nanopubs']) + 1}", "assertion": assertion,
            "kind": "reported", "status": "reported",
            "evidence": [store.ev(t["doc"], t["para"], t["sentence"])],
            "provenance": prov, "note": note})
    # explicit limitation statements -> "this study contains limitation: ..."
    for d, p in store.body_paragraphs():
        if not re.match(r"^\s*Limitations?\s*[:：]", p["text"], re.I) and \
                (p.get("section") or "").lower() != "limitations":
            continue
        body = re.sub(r"^\s*Limitations?\s*[:：]\s*", "", p["text"], flags=re.I)
        for s in sentences(body):
            if len(s) < 10:
                continue
            prov = {"source_id": d["sid"]}
            prov.update(meta)
            ir["nanopubs"].append({
                "id": f"NP{len(ir['nanopubs']) + 1}",
                "assertion": {"subject": "this study", "predicate": "contains",
                              "object": "limitation: " + clip(s.rstrip(" .;"), 160)},
                "kind": "reported", "status": "reported",
                "evidence": [store.ev(d, p, s)],
                "provenance": prov,
                "note": "verbatim limitation statement from the material"})
    # workorder-requested assertions not covered -> honest gaps
    req_ids = []
    for name, data in store.workorder_raw.items():
        def walk(o):
            if isinstance(o, dict):
                rid = o.get("assertion_id") or o.get("nanopub_id") or o.get("id")
                if rid:
                    req_ids.append((str(rid), o.get("text") or o.get("assertion_text")))
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(data)
    for rid, tx in req_ids:
        if not any(n["id"] == rid for n in ir["nanopubs"]):
            ir["nanopubs"].append(gap_record(rid, "requested assertion not extractable "
                                             "from provided material",
                                             assertion_text=tx or None))
    if not ir["nanopubs"]:
        ir["nanopubs"].append(gap_record("NP1", "no controlled-predicate conclusion "
                                         "sentence located in provided material",
                                         assertion_text=None))
        ir["nanopubs"][0]["assertion_text"] = ("no atomic assertion could be extracted "
                                               "from the provided material (honest gap)")
    if not meta:
        ir["uncertainty"].append({"item": "provenance metadata",
                                  "reason": "authors/year/doi absent from material; marked "
                                            "as gaps, never invented",
                                  "handling": "human_confirm"})


# ── knowledge_graph ──────────────────────────────────────────────────────────

def node_type(label):
    low = label.lower()
    for inst in INSTRUMENTS:
        if re.search(r"\b" + re.escape(inst.lower()) + r"\b", low):
            return "instrument"
    if any(re.search(r"\b" + re.escape(w) + r"\b", low) for w in METRIC_WORDS):
        return "metric"
    if any(re.search(r"\b" + re.escape(w) + r"\b", low) for w in METHOD_WORDS):
        return "method"
    if re.search(r"\b(?:films?|materials?|nanoparticles?|cells?|proteins?|"
                 r"perovskite|graphene|electrodes?|samples?|cohort|patients?)\b", low):
        return "material"
    return "concept"


def build_graph(ir, store, case, input_dir=None):
    nodes, edges = [], []
    by_label = {}

    def add_node(label, ntype, d, p, quote, aliases=None):
        key = re.sub(r"\s+", " ", label.strip().lower())
        if not key:
            return None
        if key in by_label:
            return by_label[key]
        nid = f"N{len(nodes) + 1}"
        n = {"id": nid, "label": clip(label.strip(), 100), "type": ntype,
             "aliases": aliases or [], "kind": "inferred", "status": "reported",
             "human_confirm": True,
             "note": "label verbatim from material; type assigned by deterministic "
                     "keyword heuristic; human_confirm",
             "evidence": [store.ev(d, p, quote)]}
        nodes.append(n)
        by_label[key] = nid
        return nid

    triples = split_triples(store)
    for t in triples:
        s_type = node_type(t["subject"])
        o_type = node_type(t["object"])
        sid = add_node(t["subject"], s_type, t["doc"], t["para"], t["sentence"])
        oid = add_node(t["object"], o_type, t["doc"], t["para"], t["sentence"])
        etype = EDGE_MAP.get(t["predicate"], t["predicate"])
        enote = (f"relation read from the verbatim sentence; predicate "
                 f"'{t['predicate']}'")
        if t.get("passive"):
            # passive voice: direction not safely invertible. Only the documented
            # "INSTRUMENT was used to VERB OBJECT" pattern yields an edge
            # (instrument measures object); other passives keep nodes, no edge.
            if t["predicate"] == "uses" and s_type == "instrument":
                etype = "measures"
                enote += ("; passive 'was used to' normalized to instrument measures "
                          "object (documented rule)")
            else:
                continue
        if etype != t["predicate"]:
            enote += f" normalized to '{etype}' (controlled vocabulary)"
        enote += "; human_confirm"
        if sid and oid and sid != oid and etype in (engine.EDGE_TYPES if engine else {
                "uses", "compares", "outperforms", "supports", "contradicts", "causes",
                "increases", "decreases", "inhibits", "activates", "binds", "part_of",
                "measures", "associated_with", "applied_to", "produces", "contains",
                "upstream_of", "reports"}):
            if any(e["from"] == sid and e["to"] == oid and e["type"] == etype
                   for e in edges):
                continue
            e = {"id": f"E{len(edges) + 1}", "from": sid, "to": oid, "type": etype,
                 "kind": "inferred", "status": "reported", "human_confirm": True,
                 "note": enote,
                 "evidence": [store.ev(t["doc"], t["para"], t["sentence"])]}
            if t["conditions"]:
                e["conditions"] = t["conditions"]
            edges.append(e)
    # standalone instruments mentioned in the material
    for d, p in store.body_paragraphs():
        for inst in INSTRUMENTS:
            if re.search(r"\b" + re.escape(inst) + r"\b", p["text"]):
                q = exact_quote(p["text"], inst) or p["text"]
                add_node(inst, "instrument", d, p, q)
    # researchers from the author paragraph (affiliation or explicit Authors: label)
    meta = provenance_meta(store)
    for d, p in store.body_paragraphs():
        if (re.search(r"\b(?:University|Institute|Department|Laboratory|College|"
                      r"School|Academy)\b", p["text"]) or
                re.search(r"Authors?\s*[:：]", p["text"])) and len(p["text"]) < 400:
            names = re.sub(r"\([^)]*\)", "", p["text"])
            am = re.search(r"Authors?\s*[:：]\s*([^\n]+?)(?=\.\s*(?:Year|DOI)\s*[:：]|\.\s*$|$)",
                           p["text"])
            if am:
                names = am.group(1)
            else:
                names = re.sub(r"^\s*(?:Title\s*[:：][^\n]*?\.)?\s*", "", names)
            for nm in re.split(r"\s+and\s+|,\s*|;\s*", names):
                nm = nm.strip(" .")
                if 3 <= len(nm) < 60 and not re.search(r"Year|DOI|Title|10\.\d{4}", nm):
                    add_node(nm, "researcher", d, p, p["text"])
            break
    ir["nodes"], ir["edges"] = nodes, edges
    # >=3 real queries answered from the ACTUAL graph
    def q(qid, question, answer, nids):
        ir["queries"].append({"id": qid, "question": question, "answer": answer,
                              "node_ids": nids,
                              "evidence": [ev for n in nodes if n["id"] in nids
                                           for ev in n.get("evidence", [])][:4]})
    methods = [n for n in nodes if n["type"] == "method"]
    instrs = [n for n in nodes if n["type"] == "instrument"]
    metrics = [n for n in nodes if n["type"] == "metric"]
    if methods:
        q("Q1", "Which methods are reported in the provided material?",
          "; ".join(n["label"] for n in methods), [n["id"] for n in methods])
    if instrs:
        q("Q2", "Which instruments/characterization techniques are mentioned?",
          "; ".join(n["label"] for n in instrs), [n["id"] for n in instrs])
    if edges:
        q("Q3", "What typed relations were extracted from the material?",
          "; ".join(f"{e['from']} -{e['type']}-> {e['to']}" for e in edges),
          list(dict.fromkeys([e["from"] for e in edges] + [e["to"] for e in edges])))
    if metrics:
        q("Q4", "Which outcome metrics appear in the material?",
          "; ".join(n["label"] for n in metrics), [n["id"] for n in metrics])
    if len(ir["queries"]) < 3 and nodes:
        q(f"Q{len(ir['queries']) + 1}",
          "Which entities were extracted from the provided material?",
          "; ".join(f"{n['label']} ({n['type']})" for n in nodes),
          [n["id"] for n in nodes])
    if not nodes:
        ir["nodes"].append(gap_record("N1", "no entity extractable from provided "
                                      "material", label=None, type="other"))
        ir["uncertainty"].append({"item": "graph", "reason": "no nodes/edges extracted; "
                                  "graph empty (honest gap, no commonsense completion)",
                                  "handling": "human_confirm"})
    else:
        ir["uncertainty"].append({"item": "entity types / relation normalization",
                                  "reason": "types assigned by keyword heuristic; improves->"
                                            "increases normalization documented per edge; "
                                            "human_confirm",
                                  "handling": "human_confirm"})


BUILDERS = {
    "document_parse": build_parse,
    "summary_notes": build_parse,
    "translation": build_translation,
    "nanopublication": build_nanopubs,
    "knowledge_graph": build_graph,
}


# ── status / fallback helpers ────────────────────────────────────────────────

def has_gaps(ir):
    recs = engine.records_of(ir) if engine else []
    for r in recs:
        if r.get("status") != "reported" or r.get("human_confirm") or \
                r.get("kind") == "inferred":
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
    ir.setdefault("uncertainty", []).append(
        {"item": "pipeline", "reason": f"{type(error).__name__}: {error}",
         "handling": "human_confirm"})
    validation = None
    if engine is not None:
        try:
            validation = engine.validate_ir(ir, case.get("input_dir"))
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

    ir = {"ir_version": "1.0", "case_id": case.get("case_id"), "kind": kind,
          "sources": store.sources, "items": [], "segments": [], "nanopubs": [],
          "nodes": [], "edges": [], "queries": [], "glossary": [], "sections": [],
          "claims": [], "unanswered_parts": [], "uncertainty": [],
          "provenance": {"pipeline": "material -> auto_extract -> arena IR -> "
                                     "assemble (validate+build) -> result",
                         "changes": [{"step": "auto_extract",
                                      "detail": f"deterministic extraction from "
                                                f"{len(materials)} material files; "
                                                "paragraph ids [Pn]/headers kept verbatim, "
                                                "unmarked blocks auto-id X*"}]}}
    BUILDERS.get(kind, build_parse)(ir, store, case, args.input)

    for e in store.errors:
        ir["uncertainty"].append({"item": "extraction", "reason": e,
                                  "handling": "human_confirm"})
    ir["uncertainty"].extend(store.uncertainty)
    if not materials:
        ir["uncertainty"].append({"item": "materials",
                                  "reason": "input directory empty or unreadable; nothing to extract",
                                  "handling": "human_confirm"})
    seen, uniq = set(), []
    for u in ir["uncertainty"]:
        key = (u.get("item"), u.get("reason"))
        if key not in seen:
            seen.add(key)
            uniq.append(u)
    ir["uncertainty"] = uniq

    work_ir = work_dir / "ir.json"
    figkit.write_json(work_ir, ir)

    # run the PACKAGE'S OWN assemble.py (same validate+build+result path)
    cmd = [sys.executable, str(SCRIPT_DIR / "assemble.py"),
           "--ir", str(work_ir), "--input", str(args.input), "--out", str(out_dir)]
    if has_gaps(ir):
        cmd += ["--status", "partial"]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(cmd, cwd=str(SCRIPT_DIR), env=env, capture_output=True,
                          text=True, timeout=300)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)
    if not (out_dir / "result.json").exists():
        raise RuntimeError(f"assemble.py exited {proc.returncode} without result.json: "
                           f"{(proc.stderr or proc.stdout or '')[-500:]}")
    result = figkit.load_json(out_dir / "result.json")
    nrec = len(engine.records_of(ir)) if engine else 0
    print(json.dumps({"autopilot": "auto_arena_read", "kind": kind,
                      "status": result.get("status"),
                      "case_id": result.get("case_id"),
                      "n_records": nrec, "n_materials": len(materials),
                      "work_ir": str(work_ir)}, ensure_ascii=False))
    return 0 if result.get("status") in ("success", "partial") else 1


def main():
    ap = argparse.ArgumentParser(description="reading track autopilot (product-arena architecture)")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--kind", default=None)
    args = ap.parse_args()

    case, sources, kind = {}, [], None
    try:
        if figkit is None or engine is None:
            raise RuntimeError("cannot import sibling figkit.py / arena_read_engine.py")
        return run(args)
    except Exception as e:
        traceback.print_exc()
        # honest fallback: NEVER exit without result.json
        try:
            case = figkit.load_case(args.input) if figkit else {}
            kind = args.kind or "document_parse"
            try:
                mats = figkit.list_materials(args.input) if figkit else []
                sources = [{"id": f"S{i}", "path": m["path"], "name": m["name"],
                            "type": (m.get("ext") or "").lstrip(".")}
                           for i, m in enumerate(mats, 1)]
            except Exception:
                sources = []
            ir = {"ir_version": "1.0", "case_id": case.get("case_id"), "kind": kind,
                  "sources": sources,
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