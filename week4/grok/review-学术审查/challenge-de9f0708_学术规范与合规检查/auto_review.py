"""auto_review.py — deterministic "autopilot" entry point for the week4 REVIEW track.

Reads the ACTUAL organizer-provided local materials under --input (manuscript,
references, data tables, guidelines), auto-extracts a complete Review IR
(sources / documents / findings / claims / stats_checks / arguments /
compliance_items / dimension_scores ...), runs the EXISTING review_engine
(validate_ir + build: quote verification + REAL statistical recomputation)
and writes an honest result.json preserving every output_contract key +
case_id. Stdlib only; additive — does not modify the engine.

Usage:
  PYTHONDONTWRITEBYTECODE=1 python auto_review.py --input /input --out /app/output \
      [--work /app/work] [--kind KIND]

Design rules:
  * Never fabricate: every quote is an EXACT substring of a real paragraph
    (engine._paragraphs splitting, so locators bind); every number comes from
    real file content or w4kit recomputation.
  * Judgment-heavy fields (support labels, validity, compliance status,
    quality scores) get deterministic, evidence-grounded heuristic defaults
    and are flagged human_confirm in uncertainty[] (=> honest status partial).
    Anything not locatable in the material -> insufficient_evidence/abstain.
  * Defensive extraction: a bad/missing file becomes an honest gap, never a crash.
  * The WHOLE pipeline is wrapped: on ANY exception an honest result.json is
    still written (status partial/failed) with contract keys + case_id + error.
  * After this baseline runs, the agent may refine /app/work/review_ir.json
    within budget and re-run assemble.py to improve judgment fields.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
import zlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    import w4kit as kit
    import review_engine as engine
except Exception:  # catastrophic import failure -> emergency writer below
    kit = None
    engine = None

AUTO_NOTE = ("auto_review autopilot: deterministic extraction from ACTUAL local "
             "materials + existing review_engine computation (quote verification, "
             "real statistical recomputation); no fabricated quotes/findings. "
             "Judgment fields use documented evidence-grounded heuristics flagged "
             "human_confirm; refine work/review_ir.json and re-run assemble.py "
             "to improve.")

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
    ("methods_stats_review", ["统计", "方法学", "recompute", "statistical",
                              "statistics", "sample size", "p-value", "p value",
                              "methods audit", "regression", "mean", "sd "]),
    ("citation_fact_check", ["引用", "参考文献", "citation", "fact-check",
                             "fact check", "claim", "reference support",
                             "overgeneralization", "mis-citation"]),
    ("logic_argument_review", ["逻辑", "论证", "argument", "fallacy", "premise",
                               "conclusion", "consistency", "inference",
                               "causal claim"]),
    ("compliance_check", ["合规", "伦理", "compliance", "consort", "prisma",
                          "arrive", "icmje", "ethics", "checklist",
                          "conflict of interest", "registration"]),
    ("quality_review", ["质量", "quality", "novelty", "rigor", "clarity",
                        "significance", "peer review", "overall recommendation",
                        "审稿"]),
]

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
             "twelve": 12, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
             "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
             "hundred": 100}

TEST_NAME_RE = re.compile(
    r"t[- ]?test|anova|analysis of variance|chi[- ]?square|chi2|mann[- ]?whitney|"
    r"wilcoxon|kruskal|fisher|pearson|spearman|log[- ]?rank|cox |regression|"
    r"mixed model|mixed-effect|permutation test|bootstrap|kaplan[- ]?meier", re.I)


# ── small helpers ────────────────────────────────────────────────────────────

def tokens(text):
    return {t for t in re.findall(r"[a-z0-9\u4e00-\u9fff]+", str(text or "").lower())
            if len(t) >= 3 and t not in STOPWORDS}


def clip(s, n=600):
    s = str(s)
    return s if len(s) <= n else s[:n] + "..."


def norm_ws(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def sentences(text):
    """Split a paragraph into sentences; each is an EXACT substring of text.
    Protects abbreviations (et al., e.g., ...) and author initials from splits."""
    t = str(text or "")
    t = re.sub(r"\b(et al|e\.g|i\.e|vs|Dr|Prof|Fig|No|cf|approx)\.",
               lambda m: m.group(1) + "\u0001", t)
    t = re.sub(r"\b([A-Z])\.(?=\s)", lambda m: m.group(1) + "\u0001", t)
    parts = re.split(r"(?<=[.!?])\s+|(?<=[。！？])", t)
    out = []
    for p in parts:
        p = p.replace("\u0001", ".").strip()
        if p:
            out.append(p)
    return out


def year_of(v):
    m = re.search(r"(18|19|20)\d{2}", str(v or ""))
    return int(m.group(0)) if m else None


def num_of(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


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


# ── material store ───────────────────────────────────────────────────────────

class Store:
    def __init__(self, case, materials):
        self.case = case
        self.sources = []
        self.documents = []        # {document_id, source_id, role, title, text, paragraphs, ...}
        self.by_name = {}
        self.tables = []           # {sid, did, name, rows, numeric_cols}
        self.manuscript = None
        self.errors = []
        self.uncertainty = []

    def add_unc(self, item, reason, handling="human_confirm", impact=None):
        u = {"item": item, "reason": reason, "handling": handling}
        if impact:
            u["impact"] = impact
        self.uncertainty.append(u)

    def register_sources(self, materials):
        for i, m in enumerate(materials, 1):
            sid = f"S{i}"
            ext = (m.get("ext") or "").lstrip(".") or "file"
            self.sources.append({"id": sid, "path": m["path"], "name": m["name"],
                                 "type": ext})
            self.by_name[m["name"].lower()] = {"sid": sid, "path": m["path"],
                                               "name": m["name"], "ext": ext}

    def parse_all(self):
        candidates = []
        for f in self.by_name.values():
            low = f["name"].lower()
            if low == "case.json" or low == "task.md" or low.startswith("readme"):
                continue
            try:
                self.parse_file(f, candidates)
            except Exception as e:
                self.errors.append(f"{f['name']}: {type(e).__name__}: {e}")
                self.add_unc(f["name"], f"extraction failed: {e}; file registered "
                             "but not parsed", "human_confirm")
        # manuscript election: explicit name > largest non-ref text document
        ms = [d for d in self.documents if d["role"] == "manuscript"]
        if not ms:
            texts = [d for d in self.documents
                     if d["role"] in ("other",) and d.get("text")]
            if texts:
                texts.sort(key=lambda d: len(d.get("text", "")), reverse=True)
                texts[0]["role"] = "manuscript"
                ms = texts[:1]
                self.add_unc("manuscript_id", "no file named manuscript*; elected "
                             f"largest text document '{texts[0]['title']}' as the "
                             "document under review", "human_confirm")
        if ms:
            self.manuscript = ms[0]
        else:
            self.add_unc("manuscript", "no manuscript-like document found in the "
                         "provided materials; review cannot bind evidence",
                         "human_confirm")

    def parse_file(self, f, candidates):
        low, ext, sid = f["name"].lower(), f["ext"], f["sid"]
        if ext in ("csv", "tsv", "tab") or (ext == "json" and low != "case.json"):
            rows = []
            try:
                rows = kit.read_table(f["path"])
            except Exception:
                rows = []
            if rows and isinstance(rows[0], dict):
                did = f"D{len(self.documents) + 1}"
                cols = list(rows[0])
                numeric = [c for c in cols
                           if sum(1 for r in rows if kit.to_float(r.get(c)) is not None)
                           >= max(1, len(rows) // 2)]
                doc = {"document_id": did, "source_id": sid, "role": "data",
                       "title": f"{f['name']} ({len(rows)} rows; columns: "
                                f"{', '.join(cols)})", "text": "", "paragraphs": []}
                self.documents.append(doc)
                self.tables.append({"sid": sid, "did": did, "name": f["name"],
                                    "rows": rows, "numeric_cols": numeric})
                return
            # json that is not a table -> fall through to text handling
        try:
            text = read_material_text(f["path"])
        except Exception as e:
            self.add_unc(f["name"], f"cannot read bytes: {e}", "human_confirm")
            return
        if ext in ("csv", "tsv", "tab", "json"):
            return  # non-tabular data-ish file; registered as source only
        if not text.strip():
            self.add_unc(f["name"], "file is empty", "note")
            return
        paras = engine._paragraphs(text) if engine else [
            {"id": f"p{i+1}", "page": 1, "text": b.strip()}
            for i, b in enumerate(re.split(r"\n\s*\n", text)) if b.strip()]
        head = text.strip().splitlines()[0]
        title = re.sub(r"^#+\s*", "", head).strip() or f["name"]
        if re.match(r"(ref\d*|reference)", low) or "reference" in low:
            role = "reference"
        elif re.search(r"guideline|consort|prisma|arrive|checklist|icmje", low):
            role = "guideline"
        elif "manuscript" in low or re.search(r"paper|article|main_text", low):
            role = "manuscript"
        else:
            role = "other"
        did = f"D{len(self.documents) + 1}"
        doc = {"document_id": did, "source_id": sid, "role": role,
               "title": clip(title, 300), "text": text, "paragraphs": paras,
               "name": f["name"]}
        if ext == "pdf":
            # engine cannot parse PDF bytes: transcribe salvaged paragraphs into IR
            doc["paragraphs"] = paras
            doc["_transcribe"] = True
        self.documents.append(doc)
        candidates.append(doc)

    # -- evidence helpers ------------------------------------------------------
    def locate(self, doc, pattern, flags=re.I):
        """First (paragraph, sentence, match) whose sentence matches pattern."""
        if not doc:
            return None
        rx = re.compile(pattern, flags)
        for par in doc.get("paragraphs", []):
            for sent in sentences(par["text"]):
                m = rx.search(sent)
                if m:
                    return par, sent, m
        return None

    def locate_all(self, doc, pattern, flags=re.I):
        out = []
        if not doc:
            return out
        rx = re.compile(pattern, flags)
        for par in doc.get("paragraphs", []):
            for sent in sentences(par["text"]):
                m = rx.search(sent)
                if m:
                    out.append((par, sent, m))
        return out

    def ev(self, doc, par, quote):
        """Locator-bound evidence; quote is an exact substring of the paragraph."""
        if not doc or not par or not quote:
            return None
        if norm_ws(quote) not in norm_ws(par["text"]):
            return None  # never emit an unverifiable quote
        e = {"source_id": doc["source_id"], "document_id": doc["document_id"],
             "paragraph_id": par["id"], "quote": quote}
        if par.get("page") is not None:
            e["page"] = par["page"]
        return e

    def quote_ev(self, doc, pattern, flags=re.I):
        hit = self.locate(doc, pattern, flags)
        if not hit:
            return None
        par, sent, _ = hit
        return self.ev(doc, par, sent)

    def first_ev(self, doc):
        """Fallback evidence: first non-heading sentence of the document."""
        if not doc:
            return None
        for par in doc.get("paragraphs", []):
            for sent in sentences(par["text"]):
                if sent.startswith("#"):
                    continue
                e = self.ev(doc, par, sent)
                if e:
                    return e
        return None


# ── kind detection ───────────────────────────────────────────────────────────

def detect_kind(args_kind, case, store):
    if args_kind:
        k = args_kind.strip().replace("-", "_")
        if not engine or k in engine.KINDS:
            return k
    skill = SCRIPT_DIR / "SKILL.md"
    if skill.exists():
        try:
            head = skill.read_text(encoding="utf-8", errors="replace")[:2000]
            m = re.search(r"^name:\s*review-([a-z0-9-]+)\s*$", head, re.M)
            if m:
                k = m.group(1).replace("-", "_")
                if not engine or k in engine.KINDS:
                    return k
        except Exception:
            pass
    blob = ((case.get("task_md") or "") + " " +
            json.dumps(case.get("raw") or {}, ensure_ascii=False)).lower()
    blob += " " + " ".join(f["name"].lower() for f in store.by_name.values())
    best, best_score = None, 0
    for kind, kws in KIND_KEYWORDS:
        score = sum(1 for kw in kws if kw.lower() in blob)
        if score > best_score:
            best, best_score = kind, score
    return best or "quality_review"


# ── shared IR finalize ───────────────────────────────────────────────────────

def finalize_common(ir, store, case):
    ir["sources"] = store.sources
    docs = []
    for d in store.documents:
        entry = {"document_id": d["document_id"], "source_id": d["source_id"],
                 "role": d["role"], "title": d["title"]}
        if d.get("_transcribe"):
            entry["paragraphs"] = d["paragraphs"]
        if d["role"] == "reference":
            meta = ref_metadata(d)
            if meta:
                entry["metadata"] = meta
        docs.append(entry)
    ir["documents"] = docs
    if store.manuscript:
        ir["manuscript_id"] = store.manuscript["document_id"]
    ir["uncertainty"] = list(store.uncertainty)
    ir["provenance"] = {
        "pipeline": "actual material -> auto_extract -> IR -> validate -> "
                    "recompute/verify -> artifact -> result",
        "changes": [{"at": kit.utc_now(), "step": "auto_extract",
                     "change": f"deterministic extraction from "
                               f"{len(store.sources)} material files"}]}
    for e in store.errors:
        ir["uncertainty"].append({"item": "extraction", "reason": e,
                                  "handling": "human_confirm"})


def ref_metadata(doc):
    """Title/DOI/year/authors from the ACTUAL reference file content."""
    text = doc.get("text", "")
    meta = {"title": doc.get("title")}
    doi = re.search(r"10\.\d{4,9}/[^\s,;\"')\]]+", text)
    if doi:
        meta["doi"] = doi.group(0)
    yr = re.search(r"\b(19|20)\d{2}\b", text)
    if yr:
        meta["year"] = int(yr.group(0))
    au = re.search(r"^([A-Z][A-Za-z'-]+(?:\s+et al\.?|,\s*[A-Z]\.[^\n]*))", text, re.M)
    if au:
        meta["authors"] = au.group(1).strip()
    return meta


def dedup_uncertainty(ir):
    seen, uniq = set(), []
    for u in ir.get("uncertainty", []):
        key = (u.get("item"), u.get("reason"))
        if key not in seen:
            seen.add(key)
            uniq.append(u)
    ir["uncertainty"] = uniq


# ── methods_stats_review builder ─────────────────────────────────────────────

def extract_reported_stats(store, ms):
    """Locate reported statistics in the manuscript with exact quote locators."""
    rep = {}
    hit = store.locate(ms, r"\bmean\b[^.\n]{0,60}?(-?\d+(?:\.\d+)?)\s*\(\s*SD\s*"
                           r"(-?\d+(?:\.\d+)?)")
    if hit:
        par, sent, m = hit
        rep["mean"] = {"value": float(m.group(1)), "ev": store.ev(ms, par, sent)}
        rep["sd"] = {"value": float(m.group(2)), "ev": store.ev(ms, par, sent)}
    else:
        h1 = store.locate(ms, r"\bmean\b[^.\n]{0,40}?(?:was|=|of|:)\s*(-?\d+(?:\.\d+)?)")
        if h1:
            rep["mean"] = {"value": float(h1[2].group(1)),
                           "ev": store.ev(ms, h1[0], h1[1])}
        h2 = store.locate(ms, r"\bSD\b\s*[:=]?\s*(-?\d+(?:\.\d+)?)")
        if h2:
            rep["sd"] = {"value": float(h2[2].group(1)),
                         "ev": store.ev(ms, h2[0], h2[1])}
    hn = store.locate(ms, r"\bn\s*=\s*(\d+)")
    if not hn:
        hn = store.locate(ms, r"\b(\d+)\s+(?:samples|patients|subjects|participants|"
                              r"replicates|observations|mice|animals)\b")
    if not hn:
        hn = store.locate(ms, r"\b(" + "|".join(NUM_WORDS) +
                          r")\s+(?:samples|patients|subjects|participants|"
                          r"replicates|observations|mice|animals)\b")
        if hn:
            rep["n"] = {"value": NUM_WORDS[hn[2].group(1).lower()],
                        "ev": store.ev(ms, hn[0], hn[1])}
    if hn and hn[2] is not None and "n" not in rep:
        rep["n"] = {"value": int(hn[2].group(1)), "ev": store.ev(ms, hn[0], hn[1])}
    hs = store.locate(ms, r"\bslope\s*(?:=|of|was|:)?\s*(-?\d+(?:\.\d+)?)")
    if hs:
        rep["slope"] = {"value": float(hs[2].group(1)),
                        "ev": store.ev(ms, hs[0], hs[1])}
    hr = store.locate(ms, r"\bR[2²]\s*(?:=|of|was|:)?\s*(-?\d+(?:\.\d+)?)")
    if hr:
        rep["r2"] = {"value": float(hr[2].group(1)), "ev": store.ev(ms, hr[0], hr[1])}
    hp = store.locate(ms, r"\bp\s*=\s*(\d+(?:\.\d+)?(?:e-?\d+)?)")
    if hp:
        rep["p"] = {"value": float(hp[2].group(1)), "ev": store.ev(ms, hp[0], hp[1])}
    hc = store.locate(ms, r"(?:confidence interval|\bCI\b)[^.\n]{0,60}?"
                          r"upper (?:limit|bound)[^.\n]{0,20}?(\d+(?:\.\d+)?)")
    if hc:
        rep["ci_upper"] = {"value": float(hc[2].group(1)),
                           "ev": store.ev(ms, hc[0], hc[1])}
    return rep


def pick_table(store):
    """Prefer a data table whose numeric column mean matches the reported mean."""
    return store.tables[0] if store.tables else None


def f_methods(ir, store, case):
    ms = store.manuscript
    findings, checks = [], []
    rep = extract_reported_stats(store, ms) if ms else {}
    text = (ms or {}).get("text", "")
    table = pick_table(store)
    ycol = xcol = None
    computed_desc = None
    if table and table["numeric_cols"]:
        cols = table["numeric_cols"]
        ycol = cols[-1]
        if "mean" in rep:
            best, bestd = None, None
            for c in cols:
                d = kit.describe([r.get(c) for r in table["rows"]])
                if d.get("n") and abs(d["mean"] - rep["mean"]["value"]) >= 0:
                    dist = abs(d["mean"] - rep["mean"]["value"])
                    if bestd is None or dist < bestd:
                        best, bestd = c, dist
            if best:
                ycol = best
        xcol = next((c for c in cols if c != ycol), None)
        computed_desc = kit.describe([r.get(ycol) for r in table["rows"]])

    def data_ev(col):
        t = table
        return {"source_id": t["sid"], "document_id": t["did"], "field": col,
                "quote": f"{col} column of {t['name']} ({len(t['rows'])} rows)"}

    # ST1: describe (recompute mean/SD/n of the outcome column)
    if table and ycol:
        reported = {}
        evs = []
        for k in ("mean", "sd", "n"):
            if k in rep:
                reported[k] = rep[k]["value"]
                if rep[k]["ev"] and rep[k]["ev"] not in evs:
                    evs.append(rep[k]["ev"])
        st = {"id": "ST1", "check_type": "describe",
              "description": f"Recompute mean/SD/n of '{ycol}' from {table['name']} "
                             "and compare with the manuscript (rel tolerance 5%).",
              "data": {"source_id": table["sid"], "field": ycol},
              "tolerance": {"rel": 0.05, "abs": 1e-9}}
        if reported:
            st["reported"] = reported
            st["evidence"] = evs or [data_ev(ycol)]
        checks.append(st)
    elif rep.get("mean") or rep.get("sd"):
        store.add_unc("reported statistics", "mean/SD reported but no data table "
                      "provided under input; cannot recompute (no fabricated data)",
                      "human_confirm")

    # ST2: linreg (slope/R2) when reported and two numeric columns exist
    if table and ycol and xcol and (rep.get("slope") or rep.get("r2")):
        reported, evs = {}, []
        for k in ("slope", "r2"):
            if k in rep:
                reported[k] = rep[k]["value"]
                if rep[k]["ev"]:
                    evs.append(rep[k]["ev"])
        checks.append({"id": "ST2", "check_type": "linreg",
                       "description": f"Recompute OLS slope/R2 of '{ycol}' on "
                                      f"'{xcol}' from {table['name']}; compare with "
                                      "the reported values (rel 5%).",
                       "data": {"source_id": table["sid"], "x_field": xcol,
                                "y_field": ycol},
                       "reported": reported, "evidence": evs or [data_ev(ycol)]})

    # ST3: internal CI arithmetic from REPORTED mean/SD/n (expr check)
    if rep.get("ci_upper") and rep.get("mean") and rep.get("sd") and rep.get("n"):
        checks.append({"id": f"ST{len(checks) + 1}", "check_type": "expr",
                       "description": "Internal consistency: 95% CI upper limit = "
                                      "mean + 1.96*sd/sqrt(n) using the REPORTED "
                                      "mean/SD/n (checks arithmetic, not the SD).",
                       "expr": "mean + 1.96 * sd / sqrt(n)",
                       "env": {"mean": rep["mean"]["value"],
                               "sd": rep["sd"]["value"], "n": rep["n"]["value"]},
                       "reported": {"value": rep["ci_upper"]["value"]},
                       "tolerance": {"rel": 0.005, "abs": 1e-9},
                       "evidence": [rep["ci_upper"]["ev"]]})

    # ── methodological findings (evidence-grounded heuristics) ──
    fid = 0

    def add_f(dim, sev, status, verdict, evs, rec, reason=None, polarity=None):
        nonlocal fid
        fid += 1
        f = {"id": f"M{fid}", "dimension": dim, "severity": sev, "status": status,
             "verdict": verdict, "recommendation": rec}
        if evs:
            f["evidence"] = [e for e in evs if e]
        if reason:
            f["reason"] = reason
        if polarity:
            f["polarity"] = polarity
        if status == "insufficient_evidence":
            f["handling"] = "human_confirm"
        findings.append(f)

    p_ev = rep.get("p", {}).get("ev")
    if rep.get("p") and not TEST_NAME_RE.search(text):
        add_f("statistical_test", "major", "confirmed",
              f"A significance claim reports p = {rep['p']['value']} but names no "
              "statistical test, statistic or degrees of freedom; the reader cannot "
              "judge whether the test fits the data.",
              [p_ev],
              "Name the test, report the statistic with df and the exact p-value.")
    if re.search(r"no sample size (calculation|justification|estimate)|no power "
                 r"(analysis|calculation)|sample size was not (calculated|justified)",
                 text, re.I):
        ev = store.quote_ev(ms, r"no sample size|no power|sample size was not")
        add_f("sample_size_power", "major", "confirmed",
              "The manuscript explicitly states that no sample-size calculation / "
              "power analysis was performed; the significant result may be "
              "underpowered or unstable.",
              [ev],
              "Add an a priori sample-size estimate (effect-size source, alpha, "
              "power) or explicitly label the study exploratory.")
    elif rep.get("n") and not re.search(r"power|a priori|sample size (calculation|"
                                        r"justification|estimate)|effect size",
                                        text, re.I):
        add_f("sample_size_power", "major", "suspected",
              f"n = {rep['n']['value']} is stated without any sample-size "
              "justification or power analysis located in the text.",
              [rep["n"]["ev"]],
              "Justify the sample size a priori or label the study exploratory.")
    elif not rep.get("n"):
        add_f("sample_size_power", "major", "insufficient_evidence",
              "No sample size or power statement located in the provided text; "
              "cannot determine whether the study was powered.",
              [], "Report n per group and an a priori sample-size justification.",
              reason="no sample-size/power statement found in the manuscript")
    # reported-vs-recomputed mismatch (REAL computation, both values shown)
    if computed_desc and computed_desc.get("n"):
        for k, label in (("mean", "mean"), ("sd", "SD")):
            if k in rep:
                rv, cv = rep[k]["value"], computed_desc[k]
                if abs(rv - cv) > max(1e-9, 0.05 * abs(cv)):
                    add_f("reporting", "minor" if k == "sd" else "major",
                          "confirmed",
                          f"Reported {label} {rv} does not match the provided data: "
                          f"recomputed {label} = {round(cv, 6)} "
                          f"(n={computed_desc['n']}, column '{ycol}' of "
                          f"{table['name']}). See stats check ST1.",
                          [rep[k]["ev"], data_ev(ycol)],
                          f"Correct the {label} to {round(cv, 4)} (or state the "
                          "estimator convention if a different formula was intended).")
    if rep.get("p") and not re.search(r"normality|normal distribution|independen|"
                                      r"homoscedastic|variance|distribution-free|"
                                      r"non-?parametric|shapiro", text, re.I):
        add_f("assumptions", "minor", "suspected",
              "Distributional assumptions and independence of the samples are never "
              "discussed; with the reported sample size a normality-based test may "
              "be fragile.",
              [p_ev],
              "State independence/normality checks or use and report a "
              "distribution-free alternative.")
    if rep.get("p") and not rep.get("ci_upper") and not re.search(
            r"effect size|cohen|hedge|odds ratio|risk ratio|mean difference", text, re.I):
        add_f("effect_size", "minor", "suspected",
              "Only a p-value is reported: no effect size or confidence interval "
              "for the main comparison was located in the text.",
              [p_ev],
              "Report the effect size with a 95% confidence interval alongside "
              "the p-value.")
    if rep.get("ci_upper") and rep.get("mean") and rep.get("sd") and rep.get("n"):
        expect = rep["mean"]["value"] + 1.96 * rep["sd"]["value"] / (rep["n"]["value"] ** 0.5)
        if abs(expect - rep["ci_upper"]["value"]) <= max(1e-9, 0.005 * abs(expect)):
            add_f("p_ci_interpretation", "suggestion", "confirmed",
                  f"The reported 95% CI upper limit {rep['ci_upper']['value']} is "
                  f"internally consistent with the reported mean/SD/n (recomputed "
                  f"{round(expect, 4)} via mean+1.96*sd/sqrt(n)); see the expr "
                  "stats check. It inherits any error in the reported SD.",
                  [rep["ci_upper"]["ev"]],
                  "Keep CI reporting; recompute the interval after fixing any "
                  "reported statistic.", polarity="strength")
    if not ms:
        add_f("reporting", "major", "insufficient_evidence",
              "No manuscript document was located in the provided materials; the "
              "methods audit cannot bind evidence.",
              [], "Supply the manuscript text under input.",
              reason="manuscript not found among input files")
    if not findings and not checks:
        add_f("reporting", "minor", "insufficient_evidence",
              "No checkable reported statistic or methods statement was located by "
              "the deterministic pass; human methods review required.",
              [], "Review the manuscript manually against the methods rules.",
              reason="no reported statistics/methods statements matched")
    ir["findings"] = findings
    ir["stats_checks"] = checks
    store.add_unc("methods judgments", "finding statuses/severities are deterministic "
                  "keyword/computation heuristics over the actual text and data, not "
                  "expert judgment; human_confirm all judgments", "human_confirm")


# ── citation_fact_check builder ──────────────────────────────────────────────

CITE_MARKER_RE = re.compile(r"\[(\d+(?:\s*[,，-]\s*\d+)*)\]|\(([A-Z][A-Za-z'-]+"
                            r"(?:\s+et al\.?)?,?\s*(?:19|20)\d{2}[a-z]?)\)")


def marker_numbers(sent):
    nums = []
    for m in re.finditer(r"\[(\d+(?:\s*[,，]\s*\d+)*)\]", sent):
        for part in re.split(r"[,，]", m.group(1)):
            if part.strip().isdigit():
                nums.append(int(part.strip()))
    return nums


def best_ref_paragraph(store, ref_doc, claim_text):
    """Reference paragraph with the highest token overlap with the claim."""
    ctok = tokens(claim_text)
    best, best_score = None, 0.0
    for par in ref_doc.get("paragraphs", []):
        for sent in sentences(par["text"]):
            if sent.startswith("#"):
                continue
            st = tokens(sent)
            if not st:
                continue
            score = len(ctok & st) / max(1, len(ctok))
            if score > best_score:
                best, best_score = (par, sent), score
    return best, best_score


def f_citation(ir, store, case):
    ms = store.manuscript
    claims, references = [], []
    # provided reference documents indexed by their filename number (ref1 -> [1])
    ref_docs = sorted((d for d in store.documents if d["role"] == "reference"),
                      key=lambda d: d.get("name", ""))
    by_num = {}
    for i, d in enumerate(ref_docs, 1):
        m = re.search(r"(\d+)", d.get("name", ""))
        by_num[int(m.group(1)) if m else i] = d
    # manuscript reference-list entries (if any) for cited metadata
    ref_list = {}
    if ms:
        for par, sent, m in store.locate_all(ms, r"^\s*\[?(\d+)[\].)]\s+\S"):
            num = int(m.group(1))
            entry = sent
            doi = re.search(r"10\.\d{4,9}/[^\s,;\"')\]]+", entry)
            ref_list[num] = {"title": clip(entry, 300),
                             "doi": doi.group(0) if doi else None,
                             "year": year_of(entry)}
    claim_sents = []
    if ms:
        for par in ms.get("paragraphs", []):
            for sent in sentences(par["text"]):
                if sent.startswith("#"):
                    continue
                if CITE_MARKER_RE.search(sent):
                    claim_sents.append((par, sent))
    ref_claims = {}
    for i, (par, sent) in enumerate(claim_sents, 1):
        cid = f"C{i}"
        nums = marker_numbers(sent)
        ev_loc = store.ev(ms, par, sent)
        claim = {"id": cid, "text": sent, "evidence": [ev_loc] if ev_loc else []}
        num = nums[0] if nums else None
        if num is not None:
            claim["citation_ref_ids"] = [f"R{num}"]
            ref_claims.setdefault(num, []).append(cid)
        ref_doc = by_num.get(num) if num is not None else None
        if ref_doc is None:
            claim["support"] = "insufficient"
            claim["rationale"] = (f"Reference [{num}] is not provided under input; "
                                  "its existence and content cannot be verified "
                                  "locally (never assumed).")
            claim["recommendation"] = (f"Supply reference [{num}] or remove/qualify "
                                       "the claim pending verification.")
            claims.append(claim)
            continue
        # compare the claim against the ACTUAL reference text
        best, overlap = best_ref_paragraph(store, ref_doc, sent)
        ref_text = ref_doc.get("text", "")
        support, rationale = None, ""
        evs = [ev_loc] if ev_loc else []
        ref_ev = None
        if best:
            ref_ev = store.ev(ref_doc, best[0], best[1])
        # year attribution mismatch (claim year vs actual reference year)
        meta = ref_metadata(ref_doc)
        claim_years = [int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", sent)]
        year_mismatch = (claim_years and meta.get("year")
                         and all(y != meta["year"] for y in claim_years))
        # absolute negation vs documented occurrence (e.g. 'no side effects')
        neg_absolute = re.search(r"\bno\b[^.\n]{0,30}(side effects?|adverse|"
                                 r"toxicity|risk|complications)", sent, re.I)
        ref_occurrence = re.search(r"(\d+(\.\d+)?%|observed|showed|documented|"
                                   r"reported)[^.\n]{0,80}(side effect|adverse|"
                                   r"toxicity|enzyme elevation|complication)",
                                   ref_text, re.I)
        # over-generalization ('all/every' vs explicit scope limitation)
        universal = re.search(r"\b(all|every|any)\b[^.\n]{0,40}(cancer|tumor|"
                              r"patient|model|type|case|population)", sent, re.I)
        limitation = re.search(r"single|did not examine|only one|one model|"
                               r"limited to|not examine other|in a mouse|"
                               r"in vitro|cell line", ref_text, re.I)
        if neg_absolute and ref_occurrence:
            support = "contradicts"
            rationale = ("The claim asserts absence of an effect, but the cited "
                         "source documents its occurrence (see quoted reference "
                         "sentence); direct contradiction.")
            if ref_ev:
                evs.append(ref_ev)
            claim["recommendation"] = ("Rewrite the claim to match what the source "
                                       "actually reports (quote the limited finding).")
        elif universal and limitation:
            support = "partial"
            rationale = ("Over-generalization: the claim extends to all cases, but "
                         "the cited source explicitly limits its scope (see quoted "
                         "reference sentence).")
            if ref_ev:
                evs.append(ref_ev)
            claim["recommendation"] = ("Restrict the claim to the studied model/"
                                       "population; remove the universal quantifier.")
        elif year_mismatch:
            support = "partial"
            rationale = (f"Attribution year mismatch: the claim cites "
                         f"{claim_years[0]}, but the provided reference is dated "
                         f"{meta['year']}; priority ('first reported') is also not "
                         "established by this source.")
            if ref_ev:
                evs.append(ref_ev)
            claim["recommendation"] = (f"Correct the year to {meta['year']} and drop "
                                       "unsupported priority wording.")
        elif overlap >= 0.45:
            support = "supports"
            rationale = (f"Lexical overlap {round(overlap, 2)} between claim and the "
                         "quoted reference sentence; deterministic heuristic, "
                         "human_confirm.")
            if ref_ev:
                evs.append(ref_ev)
        elif overlap >= 0.2:
            support = "partial"
            rationale = (f"Only partial lexical overlap ({round(overlap, 2)}) between "
                         "claim and reference text; part of the claim is not "
                         "addressed by the quoted source content.")
            if ref_ev:
                evs.append(ref_ev)
            claim["recommendation"] = ("Align the claim wording with what the source "
                                       "actually states; verify remaining elements.")
        else:
            support = "insufficient"
            rationale = (f"No lexical support path located between the claim and the "
                         f"provided reference text (overlap {round(overlap, 2)}); "
                         "cannot confirm support from the material — abstain.")
            claim["recommendation"] = ("Provide the exact supporting passage or "
                                       "remove the citation for this claim.")
        claim["support"] = support
        claim["rationale"] = rationale
        claim["evidence"] = evs
        claims.append(claim)
    # references[] registry with cited metadata from ACTUAL files / ref list
    for num in sorted(set(list(ref_claims) + list(by_num))):
        ref_doc = by_num.get(num)
        cited = {}
        if num in ref_list:
            cited = {k: v for k, v in ref_list[num].items() if v}
        if ref_doc is not None:
            meta = ref_metadata(ref_doc)
            cited.setdefault("title", meta.get("title"))
            cited.setdefault("doi", meta.get("doi"))
            # cited year = what the manuscript claims when explicit, else file year
            cy = None
            for cid in ref_claims.get(num, []):
                ctext = next(c["text"] for c in claims if c["id"] == cid)
                ys = re.findall(r"\b(?:19|20)\d{2}\b", ctext)
                if ys:
                    cy = int(ys[0])
                    break
            cited["year"] = cy if cy is not None else meta.get("year")
            if meta.get("authors"):
                cited.setdefault("authors", meta["authors"])
        else:
            cited.setdefault("title", f"(reference [{num}] not provided under input)")
        entry = {"ref_id": f"R{num}", "cited": cited,
                 "claim_ids": ref_claims.get(num, [])}
        if ref_doc is not None:
            entry["document_id"] = ref_doc["document_id"]
        references.append(entry)
    if not claims:
        store.add_unc("claims", "no citation-marked sentences located in the "
                      "manuscript; nothing to fact-check (no fabricated claims)",
                      "human_confirm")
        # honest empty-shell claim so validation reports the gap, not a crash
        if ms:
            ev = store.first_ev(ms)
            claims.append({"id": "C1",
                           "text": "(no citation-marked claim located in the provided "
                                   "manuscript text)",
                           "support": "insufficient",
                           "rationale": "deterministic scan found no [n]/(Author, year) "
                                        "markers; human review required",
                           "evidence": [ev] if ev else []})
    ir["claims"] = claims
    ir["references"] = references
    store.add_unc("support labels", "claim support labels are deterministic lexical/"
                  "negation/scope heuristics over the actual claim and reference text, "
                  "not expert judgment; human_confirm every label", "human_confirm")
    missing = [n for n in ref_claims if n not in by_num]
    if missing:
        store.add_unc("unprovided references",
                      f"references {missing} cited but not provided under input; "
                      "existence/support cannot be verified locally", "human_confirm")


# ── logic_argument_review builder ────────────────────────────────────────────

CONCLUSION_RE = re.compile(
    r"^(Therefore|Thus|Hence|We conclude|In conclusion|These (results|findings|data)"
    r" (demonstrate|show|suggest|indicate))\b|"
    r"\b(causes?|is safe|can be used|demonstrates that|proves that|confirms that)\b",
    re.I)
OBSERVATION_RE = re.compile(
    r"\b(experiment|observed|measured|grew|found|showed|were treated|we tested|"
    r"assay|recorded|increased|decreased|reduced)\b", re.I)
HYPOTHESIS_RE = re.compile(r"^\s*(We hypothesi[sz]ed|We aim(ed)?|Our goal|The "
                           r"(purpose|aim) of)\b", re.I)
NEG_ASSESS_RE = re.compile(
    r"\b(toxicity|safety|side effects?|efficacy|effectiveness|long[- ]term "
    r"(effects|outcomes)|mechanism)\b[^.\n]{0,60}\b(not|never|wasn't|were not)\b"
    r"[^.\n]{0,30}\b(assessed|measured|evaluated|tested|studied|examined|determined)\b",
    re.I)
ASSERT_SAFE_RE = re.compile(r"\b(is|are|was|were)\s+(safe|non[- ]?toxic|effective|"
                            r"harmless)\b|\bcan be used\b", re.I)


def f_logic(ir, store, case):
    ms = store.manuscript
    arguments, consistency, findings = [], [], []
    text = (ms or {}).get("text", "")
    # ordered content sentences with locators
    seq = []
    if ms:
        for par in ms.get("paragraphs", []):
            for sent in sentences(par["text"]):
                if sent.startswith("#"):
                    continue
                seq.append((par, sent))
    neg_assess = [(par, sent) for par, sent in seq if NEG_ASSESS_RE.search(sent)]
    aid = 0
    for idx, (par, sent) in enumerate(seq):
        if not CONCLUSION_RE.search(sent) or HYPOTHESIS_RE.search(sent):
            continue
        aid += 1
        a_id = f"A{aid}"
        con_ev = store.ev(ms, par, sent)
        # premises: nearest preceding observation sentences (skip conclusions);
        # for safety assertions the only safety-related statement is the premise
        premises = []
        if ASSERT_SAFE_RE.search(sent) and neg_assess:
            for npar, nsent in neg_assess:
                nev = store.ev(ms, npar, nsent)
                premises.append({"id": f"{a_id}P{len(premises) + 1}",
                                 "status": "reported",
                                 "text": nsent + " (the only safety-related "
                                         "statement offered)",
                                 "evidence": [nev] if nev else []})
        for j in range(idx - 1, -1, -1):
            if premises:
                break
            ppar, psent = seq[j]
            if CONCLUSION_RE.search(psent) or HYPOTHESIS_RE.search(psent):
                continue
            if OBSERVATION_RE.search(psent) or not premises:
                pev = store.ev(ms, ppar, psent)
                premises.append({"id": f"{a_id}P{len(premises) + 1}",
                                 "status": "reported", "text": psent,
                                 "evidence": [pev] if pev else []})
            if len(premises) >= 2:
                break
        if not premises:
            premises.append({"id": f"{a_id}P1", "status": "not_reported",
                             "text": "(no supporting premise located before this "
                                     "conclusion in the provided text)",
                             "handling": "human_confirm"})
        # inference type from the actual wording
        if re.search(r"\bcauses?\b|\bleads to\b|\bresults in\b|\bdue to\b", sent, re.I):
            itype = "causal"
        elif re.search(r"\bassociat|\bcorrelat", sent, re.I):
            itype = "correlational"
        elif re.search(r"^Therefore|^Thus|^Hence", sent, re.I):
            itype = "deductive"
        else:
            itype = "inductive"
        arg = {"id": a_id,
               "conclusion": {"text": sent, "evidence": [con_ev] if con_ev else []},
               "premises": premises, "inference_type": itype}
        prem_text = " ".join(p["text"] for p in premises)
        # fallacy: safety/efficacy assertion while assessment explicitly absent
        matched_neg = None
        if ASSERT_SAFE_RE.search(sent):
            for npar, nsent in neg_assess:
                if tokens(nsent) & tokens(sent) or re.search(r"toxicity|safety",
                                                             nsent, re.I):
                    matched_neg = (npar, nsent)
                    break
        if matched_neg:
            nev = store.ev(ms, matched_neg[0], matched_neg[1])
            arg["validity"] = "fallacy"
            arg["fallacy_type"] = "argument_from_ignorance"
            arg["note"] = ("Absence of assessment is treated as evidence for the "
                           "assertion; the quoted statement actually undermines it.")
            arg["recommendation"] = ("Delete or qualify the assertion; it requires "
                                     "dedicated assessment, not absence of testing.")
            consistency.append({"id": f"K{len(consistency) + 1}",
                                "a": {"text": sent,
                                      "evidence": [con_ev] if con_ev else []},
                                "b": {"text": matched_neg[1],
                                      "evidence": [nev] if nev else []},
                                "verdict": "inconsistent",
                                "note": "The assertion cannot stand alongside the "
                                        "explicit statement that the relevant "
                                        "property was never assessed."})
        elif itype == "causal":
            gaps = []
            if re.search(r"\b(patient|clinical|human|in vivo)\b", sent, re.I) and \
                    re.search(r"\b(cell|cultured|in vitro|mouse|mice|mouse model)\b",
                              prem_text, re.I):
                gaps.append("Extrapolation from the experimental model to patients/"
                            "clinical use is unsupported: no in vivo or human data "
                            "are presented.")
            if not re.search(r"randomi[sz]|mechanism|dose[- ]response|confound|"
                             r"control(led)? for", text, re.I):
                gaps.append("An uncontrolled association does not establish "
                            "causation (no mechanism, dose-response or confounder "
                            "control presented).")
            if gaps:
                arg["validity"] = "gap"
                arg["gaps"] = gaps
                arg["note"] = ("The premises support at most an association in the "
                               "studied model, not the stated causal conclusion.")
                arg["recommendation"] = ("Downgrade the conclusion to 'was associated "
                                         "with' in the studied model; remove the "
                                         "causal/clinical claim or add evidence.")
            else:
                arg["validity"] = "insufficient_evidence"
                arg["handling"] = "human_confirm"
                arg["note"] = ("Causal wording with some design controls mentioned; "
                               "validity cannot be decided by the deterministic "
                               "pass — abstain.")
        else:
            arg["validity"] = "insufficient_evidence"
            arg["handling"] = "human_confirm"
            arg["note"] = ("Validity of this inference requires expert judgment; the "
                           "deterministic pass abstains rather than guessing.")
        arguments.append(arg)
    # findings summarizing the argument audit (locator-bound)
    fid = 0
    for a in arguments:
        if a["validity"] in ("gap", "fallacy"):
            fid += 1
            evs = list(a["conclusion"].get("evidence", []))
            for p in a["premises"]:
                evs += p.get("evidence", [])
            findings.append({
                "id": f"L{fid}", "dimension": "argument_chain", "severity": "major",
                "status": "confirmed",
                "verdict": (f"Argument {a['id']}: "
                            + ("fallacy (" + a.get("fallacy_type", "") + ")"
                               if a["validity"] == "fallacy" else "inference gap")
                            + " — " + (a.get("note") or "")),
                "evidence": evs,
                "recommendation": a.get("recommendation",
                                        "Rewrite the conclusion to match the evidence.")})
    if ms and not re.search(r"\bp\s*=|\d+\s*%|effect size|confidence interval|"
                            r"\bn\s*=\s*\d", text, re.I):
        fid += 1
        ev = store.first_ev(ms)
        findings.append({
            "id": f"L{fid}", "dimension": "evidence_support", "severity": "minor",
            "status": "insufficient_evidence",
            "verdict": "No statistical test, effect size or quantified result is "
                       "reported, so whether the observations support even the "
                       "weakened claims cannot be determined from the material.",
            "reason": "no numeric results or statistics provided in the manuscript",
            "evidence": [ev] if ev else [],
            "recommendation": "Report quantified measurements with a test/effect "
                              "size; re-audit claim strength once numbers are supplied.",
            "handling": "human_confirm"})
    if not arguments:
        store.add_unc("arguments", "no conclusion-like sentences located in the "
                      "manuscript; argument audit is empty (no fabricated arguments)",
                      "human_confirm")
    ir["arguments"] = arguments
    ir["consistency_checks"] = consistency
    ir["findings"] = findings
    store.add_unc("validity judgments", "argument validity/fallacy labels are "
                  "deterministic wording/scope heuristics bound to exact quotes, "
                  "not expert logical analysis; human_confirm all labels",
                  "human_confirm")


# ── compliance_check builder ─────────────────────────────────────────────────

def f_compliance(ir, store, case):
    ms = store.manuscript
    text = (ms or {}).get("text", "")
    items = []
    iid = 0

    def add_item(cat, guideline, item, status, evs=None, reason=None,
                 missing=None, rec=None, severity="minor"):
        nonlocal iid
        iid += 1
        it = {"id": f"CI{iid}", "category": cat, "guideline": guideline,
              "item": item, "status": status, "severity": severity}
        if evs:
            it["evidence"] = [e for e in evs if e]
        if reason:
            it["reason"] = reason
        if missing:
            it["missing"] = missing
        if rec:
            it["recommendation"] = rec
        if status == "insufficient_evidence":
            it["handling"] = "human_confirm"
        items.append(it)

    def qev(pattern):
        return store.quote_ev(ms, pattern)

    # ethics approval
    ev = qev(r"approved by[^.\n]{0,80}(ethics|institutional|IRB|committee)|"
             r"ethics (approval|committee|board)[^.\n]{0,60}(number|no\.|#)\s*\S|"
             r"(ethics|IRB)[^.\n]{0,40}approval[^.\n]{0,40}(was|were)?\s*(obtained|granted)")
    ev_bare = qev(r"(ethics|institutional)[^.\n]{0,60}(board|committee|approval)|"
                  r"approved by")
    ev_denial = qev(r"no ethics approval|ethics approval was not|without ethics")
    if ev and re.search(r"(number|no\.|#|protocol)\s*[:.]?\s*[A-Za-z0-9-]", ev["quote"], re.I):
        add_item("ethics", "ICMJE / institutional ethics policy",
                 "Ethics approval stated with approving body and approval number",
                 "compliant", [ev], severity="major")
    elif ev_bare:
        add_item("ethics", "ICMJE / institutional ethics policy",
                 "Ethics approval stated with approving body, approval number and scope",
                 "partial", [ev_bare],
                 missing=["approval number", "scope of approval (which procedures covered)"],
                 rec="Add the ethics approval number and the approved scope; name the board.",
                 severity="major")
    elif ev_denial:
        add_item("ethics", "ICMJE / institutional ethics policy",
                 "Ethics approval or a justified exemption stated",
                 "partial", [ev_denial],
                 missing=["justification/basis for the exemption (e.g., cell-line "
                          "source, approval/exemption reference)"],
                 rec="State the ethics basis for the exemption; a bare denial is "
                     "not sufficient justification.", severity="major")
    else:
        add_item("ethics", "ICMJE / institutional ethics policy",
                 "Ethics approval stated with approving body, approval number and scope",
                 "insufficient_evidence",
                 reason="No ethics statement located in the provided manuscript text; "
                        "cannot distinguish 'not obtained' from 'not reported'.",
                 rec="Authors to add an ethics approval/exemption statement.",
                 severity="major")
    # informed consent
    ev = qev(r"informed consent|consent (was|were) (obtained|given|signed)|"
             r"participants (gave|provided)[^.\n]{0,30}consent")
    if ev:
        add_item("ethics", "ICMJE / Declaration of Helsinki",
                 "Informed consent obtained from human participants and stated",
                 "compliant", [ev], severity="major")
    else:
        add_item("ethics", "ICMJE / Declaration of Helsinki",
                 "Informed consent obtained from human participants and stated",
                 "insufficient_evidence",
                 reason="No consent statement appears anywhere in the provided "
                        "manuscript text; cannot determine whether consent was obtained.",
                 rec="Authors to state the informed-consent procedure; reviewer to "
                     "re-check once provided.", severity="major")
    # conflict of interest
    ev = qev(r"conflicts? of interest|competing interests|COI\b|declare[^.\n]{0,40}"
             r"(no conflict|financial)")
    if ev:
        add_item("coi", "ICMJE disclosure requirements",
                 "Conflict-of-interest declaration present", "compliant", [ev])
    else:
        add_item("coi", "ICMJE disclosure requirements",
                 "Conflict-of-interest declaration present", "insufficient_evidence",
                 reason="No COI/competing-interest statement located in the provided text.",
                 rec="Add an ICMJE-style conflict-of-interest disclosure.")
    # data availability
    ev_repo = qev(r"(data|dataset)[^.\n]{0,80}(available|deposited)[^.\n]{0,60}"
                  r"(repository|doi|accession|github|zenodo|figshare|dryad|osf)")
    ev_req = qev(r"(data|dataset)[^.\n]{0,80}(available|request)|available from the "
                 r"corresponding author")
    if ev_repo:
        add_item("data_availability", "journal data-availability policy (ICMJE-style)",
                 "Data availability statement with a concrete access route",
                 "compliant", [ev_repo])
    elif ev_req:
        add_item("data_availability", "journal data-availability policy (ICMJE-style)",
                 "Data availability statement with a concrete access route",
                 "partial", [ev_req],
                 missing=["repository name or accession/DOI for the study data"],
                 rec="Deposit de-identified data in a repository and cite the "
                     "accession; keep the request route as fallback.")
    else:
        add_item("data_availability", "journal data-availability policy (ICMJE-style)",
                 "Data availability statement with a concrete access route",
                 "insufficient_evidence",
                 reason="No data-availability statement located in the provided text.",
                 rec="Add a data-availability statement with a concrete access route.")
    # authorship contributions
    ev_neg = qev(r"(author )?contributions? (are|were) not (specified|stated|listed|"
                 r"described)|no author contributions")
    ev_pos = qev(r"author contributions?\s*[:：]|[A-Z]\.[A-Z]\.?\s*[:：][^.\n]{0,60}"
                 r"(designed|performed|wrote|analyzed)|CRediT|contributed to")
    if ev_neg:
        add_item("authorship", "ICMJE authorship criteria",
                 "Per-author contribution statements", "non_compliant", [ev_neg],
                 missing=["individual contribution description for each author"],
                 rec="Add a CRediT-style per-author contributions section.")
    elif ev_pos and re.search(r"contributions?\s*[:：]|CRediT|designed|performed|"
                              r"wrote|analyzed", ev_pos["quote"], re.I):
        add_item("authorship", "ICMJE authorship criteria",
                 "Per-author contribution statements", "compliant", [ev_pos])
    elif ev_pos:
        add_item("authorship", "ICMJE authorship criteria",
                 "Per-author contribution statements", "partial", [ev_pos],
                 missing=["individual contribution description for each author"],
                 rec="Replace the generic contribution sentence with per-author "
                     "CRediT-style contributions.")
    else:
        add_item("authorship", "ICMJE authorship criteria",
                 "Per-author contribution statements", "insufficient_evidence",
                 reason="No author-contribution statement located in the provided text.",
                 rec="Add per-author contribution statements.")
    # third-party material / copyright
    ev_adapt = qev(r"(adapted|reproduced|modified) from|reprinted (from|with)|"
                   r"figure \d+ (was )?(adapted|taken|reproduced)")
    ev_perm = qev(r"permission|license|creative commons|CC[- ]BY|copyright")
    if ev_adapt and not ev_perm:
        add_item("copyright", "publisher third-party material policy",
                 "Adapted/reproduced third-party figures carry source AND "
                 "permission/license", "non_compliant", [ev_adapt],
                 missing=["permission or license statement for the adapted material",
                          "full source citation with license type"],
                 rec="Obtain and state permission/license for the adapted material, "
                     "or replace it with an original figure.", severity="major")
    elif ev_adapt and ev_perm:
        add_item("copyright", "publisher third-party material policy",
                 "Adapted/reproduced third-party figures carry source AND "
                 "permission/license", "compliant", [ev_adapt, ev_perm],
                 severity="major")
    else:
        add_item("copyright", "publisher third-party material policy",
                 "Adapted/reproduced third-party figures carry source AND "
                 "permission/license", "not_applicable",
                 reason="No adapted/reproduced third-party material is mentioned in "
                        "the provided text; nothing to check.", severity="major")
    # study-type-specific reporting guideline
    is_trial = bool(re.search(r"randomi[sz]ed (trial|controlled)|\bRCT\b|clinical "
                              r"trial|patients were (randomly|allocated)", text, re.I))
    is_review = bool(re.search(r"systematic review|meta[- ]analysis|PRISMA", text, re.I))
    is_animal = bool(re.search(r"\b(mice|mouse|rat|rats|animal model|in vivo)\b",
                               text, re.I))
    guideline = ("CONSORT 2010" if is_trial else "PRISMA 2020" if is_review
                 else "ARRIVE 2.0" if is_animal else "journal reporting guide")
    ir["guidelines"] = [{"id": "G1", "name": guideline,
                         "version": "agent knowledge of the named standard; "
                                    "human_confirm clause numbering"},
                        {"id": "G2", "name": "ICMJE Recommendations",
                         "version": "agent knowledge, human_confirm"}]
    if is_trial:
        ev_reg = qev(r"(trial|study) (was |were )?(not registered|unregistered)|"
                     r"no (trial )?registration")
        ev_regpos = qev(r"registered (at|with|in)|registration (number|no\.|ID)|"
                        r"\bNCT\d{6,}|ChiCTR|ISRCTN")
        if ev_reg:
            add_item("reporting_guideline", f"{guideline} (trial registration)",
                     "Trial registration number and registry name reported",
                     "non_compliant", [ev_reg],
                     missing=["registry name", "registration number"],
                     rec="Register the trial (retrospectively if needed) and report "
                         "registry + ID; explain registration timing per CONSORT.",
                     severity="major")
        elif ev_regpos:
            add_item("reporting_guideline", f"{guideline} (trial registration)",
                     "Trial registration number and registry name reported",
                     "compliant", [ev_regpos], severity="major")
        else:
            add_item("reporting_guideline", f"{guideline} (trial registration)",
                     "Trial registration number and registry name reported",
                     "insufficient_evidence",
                     reason="No registration statement located in the provided text.",
                     rec="Report the registry name and registration number.",
                     severity="major")
        ev_flow = qev(r"flow (diagram|chart)|CONSORT flow|screened[^.\n]{0,60}"
                      r"(allocated|randomi[sz]ed)|were (screened|enrolled)[^.\n]{0,60}"
                      r"(analyzed|followed)")
        if ev_flow:
            add_item("reporting_guideline", f"{guideline} (participant flow)",
                     "Participant flow diagram/numbers through each stage",
                     "compliant", [ev_flow])
        else:
            add_item("reporting_guideline", f"{guideline} (participant flow)",
                     "Participant flow diagram/numbers through each stage",
                     "insufficient_evidence",
                     reason="No flow diagram or per-stage participant numbers are "
                            "present in the provided text, and figures cannot be read.",
                     rec="Provide the CONSORT flow diagram with numbers screened, "
                         "allocated, followed up and analyzed.")
    elif is_review or is_animal:
        ev_rep = qev(r"PRISMA|ARRIVE|search strategy|databases searched|"
                     r"sample size (calculation|justification)")
        if ev_rep:
            add_item("reporting_guideline", guideline,
                     f"{guideline} core reporting items present", "partial", [ev_rep],
                     missing=["full item-by-item checklist against the official "
                              f"{guideline} list"],
                     rec=f"Complete an item-by-item {guideline} checklist; the "
                         "deterministic pass only located partial coverage.")
        else:
            add_item("reporting_guideline", guideline,
                     f"{guideline} core reporting items present",
                     "insufficient_evidence",
                     reason=f"No {guideline}-related reporting statement located in "
                            "the provided text.",
                     rec=f"Report against the {guideline} checklist.")
    else:
        add_item("reporting_guideline", "journal reporting guide",
                 "Study-type reporting guideline followed", "insufficient_evidence",
                 reason="Study type not determinable from the provided text; cannot "
                        "select the applicable reporting guideline.",
                 rec="State the study design and report against the matching guideline.")
    # plagiarism risk: only flag observable signals, never accuse
    ev_dup = None
    if ms:
        seen = {}
        for par in ms.get("paragraphs", []):
            for sent in sentences(par["text"]):
                key = norm_ws(sent).lower()
                if len(key) > 60:
                    if key in seen:
                        ev_dup = store.ev(ms, par, sent)
                        break
                    seen[key] = True
            if ev_dup:
                break
    if ev_dup:
        add_item("plagiarism_risk", "COPE / journal originality policy",
                 "No verbatim duplicated passages within the manuscript",
                 "partial", [ev_dup],
                 missing=["originality check against the literature (no similarity "
                          "service available locally)"],
                 rec="Resolve the duplicated passage and run a similarity check.",
                 severity="major")
    else:
        add_item("plagiarism_risk", "COPE / journal originality policy",
                 "No verbatim duplicated passages within the manuscript",
                 "insufficient_evidence",
                 reason="No internal verbatim duplication detected by the deterministic "
                        "scan, but external similarity cannot be checked locally; "
                        "abstain from an originality verdict.",
                 rec="Run a similarity check against the literature before acceptance.")
    ir["compliance_items"] = items
    store.add_unc("guideline texts", "CONSORT/PRISMA/ARRIVE/ICMJE checklist texts are "
                  "not provided under input; item wording relies on agent knowledge "
                  "of the named standards — re-verify clause numbers against the "
                  "official checklists", "human_confirm")
    store.add_unc("compliance statuses", "statuses are deterministic statement-"
                  "presence/wording heuristics over the actual text; absent statements "
                  "are insufficient_evidence (never assumed 'not done'); human_confirm",
                  "human_confirm")


# ── quality_review builder ───────────────────────────────────────────────────

def f_quality(ir, store, case):
    ms = store.manuscript
    text = (ms or {}).get("text", "")
    findings = []
    fid = 0

    def add_f(dim, sev, status, verdict, evs, rec, reason=None, polarity=None):
        nonlocal fid
        fid += 1
        f = {"id": f"F{fid}", "dimension": dim, "severity": sev, "status": status,
             "verdict": verdict, "recommendation": rec}
        if evs:
            f["evidence"] = [e for e in evs if e]
        if reason:
            f["reason"] = reason
        if polarity:
            f["polarity"] = polarity
        if status == "insufficient_evidence":
            f["handling"] = "human_confirm"
        findings.append(f)
        return f

    has_cites = bool(CITE_MARKER_RE.search(text)) or bool(
        re.search(r"^\s*(References|参考文献)\s*$", text, re.M))
    has_refs_provided = any(d["role"] == "reference" for d in store.documents)
    p_hit = store.locate(ms, r"\bp\s*=\s*\d")
    causal_hit = store.locate(ms, r"\bcauses?\b|\bcan be used\b[^.\n]{0,60}"
                                  r"(clinical|patient)|\bin (clinical|patients)\b")
    novelty_hit = store.locate(ms, r"\bnovel\b|no prior (studies|work|research)|"
                                   r"first (report|study|demonstration)")
    ethics_hit = store.locate(ms, r"no ethics approval|ethics approval was not|"
                                  r"ethics[^.\n]{0,40}(not required|exempt)")
    design_hit = store.locate(ms, r"(cells|samples|patients|subjects|mice)[^.\n]{0,60}"
                                  r"(treated|observed|measured|enrolled|assigned)")
    # methods_design: missing n/control/replication detail
    if design_hit and not re.search(r"\bn\s*=\s*\d|\d+\s+(samples|patients|subjects|"
                                    r"replicates|mice)|randomi[sz]|control group|"
                                    r"replicat|blinded", text, re.I):
        add_f("methods_design", "major", "confirmed",
              "Methods omit sample size, control-group setup, replication and "
              "randomization detail; the design cannot support the comparison claimed.",
              [store.ev(ms, design_hit[0], design_hit[1])],
              "Report n per group, control conditions, number of independent "
              "replicates, and how the outcome was quantified.")
    # stats_reporting: bare p-value without test name / effect size / CI
    if p_hit and not TEST_NAME_RE.search(text):
        add_f("stats_reporting", "major", "confirmed",
              f"Only a bare p-value ({p_hit[1]}) is reported: no test name, effect "
              "size, confidence interval or exact statistic located in the text.",
              [store.ev(ms, p_hit[0], p_hit[1])],
              "Name the test, report effect size with 95% CI and the exact p-value.")
    # argument_chain: causal / clinical overreach
    if causal_hit and not re.search(r"randomi[sz]ed (trial|controlled)|in vivo "
                                    r"(study|data)|human (trial|data|subjects)",
                                    text, re.I):
        add_f("argument_chain", "major", "confirmed",
              "Causal/clinical conclusion exceeds the presented evidence: the claim "
              "jumps from the reported observation to causation or clinical use "
              "without supporting design or data.",
              [store.ev(ms, causal_hit[0], causal_hit[1])],
              "Downgrade to 'was associated with' in the studied model; remove the "
              "clinical-use claim or add supporting evidence.")
    # academic_norms: bare ethics denial / missing statements
    if ethics_hit:
        add_f("academic_norms", "major", "confirmed",
              "Ethics statement is a bare denial without justification located in "
              "the text.",
              [store.ev(ms, ethics_hit[0], ethics_hit[1])],
              "State the ethics basis (e.g., cell-line source and approval/exemption).")
    missing_norms = []
    if not re.search(r"conflicts? of interest|competing interests", text, re.I):
        missing_norms.append("conflict-of-interest statement")
    if not re.search(r"data (are|is|availability)|available from|deposited", text, re.I):
        missing_norms.append("data-availability statement")
    if missing_norms:
        ev = store.first_ev(ms)
        add_f("academic_norms", "minor", "suspected",
              "No " + " or ".join(missing_norms) + " located in the provided text.",
              [ev] if ev else [],
              "Add the missing declaration(s) per journal policy.")
    # fact_check: novelty assertion without provided literature
    if novelty_hit and not has_refs_provided:
        add_f("fact_check", "minor", "insufficient_evidence",
              "The novelty/priority assertion cannot be confirmed or refuted: no "
              "literature material was provided with this case.",
              [store.ev(ms, novelty_hit[0], novelty_hit[1])],
              "Authors must cite prior work or a documented search; reviewer to "
              "re-check once literature is supplied.",
              reason="no reference material under input")
    # strength: plainly stated objective
    obj_hit = store.locate(ms, r"^(We (investigated|examined|studied|aimed)|"
                               r"This (study|paper|work) (investigates|examines|presents))")
    if obj_hit:
        add_f("structure", "suggestion", "confirmed",
              "The research objective is stated plainly in the opening text.",
              [store.ev(ms, obj_hit[0], obj_hit[1])],
              "Keep this clarity; add explicit section headings.", polarity="strength")
    if not ms:
        add_f("methods_design", "major", "insufficient_evidence",
              "No manuscript document located in the provided materials; quality "
              "review cannot bind evidence.", [],
              "Supply the manuscript text under input.",
              reason="manuscript not found among input files")

    # dimension scores: deterministic signal-count heuristics, human_confirm
    def score_of(dim, signals, basis, evs):
        n_pos = sum(1 for ok, _ in signals if ok)
        score = max(0, min(5, round(5 * n_pos / max(1, len(signals)))))
        evs = [e for e in evs if e]
        if not evs:
            e = store.first_ev(ms)
            if e:
                evs = [e]
        return {"dimension": dim, "score": score, "scale": 5,
                "basis": basis + " (deterministic signal-count heuristic over the "
                         "actual text; human_confirm)",
                "evidence": evs}

    rigor_signals = [
        (bool(re.search(r"\bn\s*=\s*\d|\d+\s+(samples|patients|replicates)", text, re.I)),
         "sample size stated"),
        (bool(re.search(r"control|randomi[sz]|blinded|replicat", text, re.I)),
         "controls/randomization/replication"),
        (bool(TEST_NAME_RE.search(text)), "statistical test named"),
        (bool(re.search(r"confidence interval|\bCI\b|effect size", text, re.I)),
         "effect size / CI reported"),
    ]
    novelty_signals = [
        (bool(novelty_hit), "novelty asserted"),
        (has_refs_provided or has_cites, "prior work cited/provided to substantiate"),
    ]
    clarity_signals = [
        (bool(obj_hit), "objective stated plainly"),
        (bool(re.search(r"^#{1,3}\s+(Methods|Results|Introduction|Discussion|方法|结果)",
                        text, re.M | re.I)), "labeled sections"),
        (len(text) >= 400, "sufficient length/detail"),
    ]
    signif_signals = [
        (bool(re.search(r"clinical|patient|application|therap|treatment", text, re.I)),
         "potential application stated"),
        (not bool(causal_hit) or bool(re.search(r"randomi[sz]ed (trial|controlled)|"
                                                r"in vivo (study|data)", text, re.I)),
         "extrapolation supported by design"),
    ]
    ev_rigor = [store.ev(ms, p_hit[0], p_hit[1])] if p_hit else []
    if design_hit:
        ev_rigor.append(store.ev(ms, design_hit[0], design_hit[1]))
    ir["dimension_scores"] = [
        score_of("novelty", novelty_signals,
                 "Novelty asserted but not substantiated by provided literature"
                 if novelty_hit and not has_refs_provided else
                 "Novelty signals located in the text",
                 [store.ev(ms, novelty_hit[0], novelty_hit[1])] if novelty_hit else []),
        score_of("rigor", rigor_signals,
                 f"{sum(1 for ok, _ in rigor_signals if ok)}/{len(rigor_signals)} "
                 "rigor signals present (n, controls, test name, effect size/CI)",
                 ev_rigor),
        score_of("clarity", clarity_signals,
                 f"{sum(1 for ok, _ in clarity_signals if ok)}/{len(clarity_signals)} "
                 "clarity signals present (objective, sections, detail)",
                 [store.ev(ms, obj_hit[0], obj_hit[1])] if obj_hit else []),
        score_of("significance", signif_signals,
                 "Application potential weighed against whether the extrapolation "
                 "is supported by the presented design",
                 [store.ev(ms, causal_hit[0], causal_hit[1])] if causal_hit else []),
    ]
    # six-category checklist coverage
    ir["checklist"] = [
        {"category": "fact_check",
         "status": "uncheckable" if (novelty_hit and not has_refs_provided) else "checked",
         **({"reason": "novelty/priority assertion present but no literature material "
                       "provided under input; cannot verify locally"}
            if (novelty_hit and not has_refs_provided) else {}),
         "note": "deterministic fact-signal scan; see findings"},
        {"category": "citation_support",
         "status": "checked" if has_cites else "not_applicable",
         **({} if has_cites else
            {"reason": "The manuscript contains no citations or reference list; "
                       "nothing to verify against."})},
        {"category": "methods_design", "status": "checked"},
        {"category": "stats_reporting", "status": "checked"},
        {"category": "argument_chain", "status": "checked"},
        {"category": "academic_norms", "status": "checked"},
    ]
    n_major = sum(1 for f in findings if f["severity"] == "major"
                  and f.get("polarity", "issue") == "issue"
                  and f["status"] in ("confirmed", "suspected"))
    if not ms:
        decision, reason = "undetermined", ("no manuscript located in the provided "
                                            "materials; human review required")
    elif n_major >= 2:
        decision, reason = "major_revision", None
    elif n_major == 1:
        decision, reason = "minor_revision", None
    else:
        decision, reason = "undetermined", ("the deterministic pass located no "
                                            "checkable major defect; an accept/reject "
                                            "decision requires expert judgment — abstain")
    rec_ev = next((f["evidence"][0] for f in findings
                   if f.get("evidence") and f["severity"] == "major"), None)
    if rec_ev is None:
        rec_ev = store.first_ev(ms)
    ir["overall_recommendation"] = {
        "decision": decision,
        "rationale": reason or (
            f"{n_major} major issue(s) located by the evidence-bound deterministic "
            "pass must be fixed before the claims can be evaluated; scores are "
            "heuristic baselines requiring human confirmation."),
        "evidence": [rec_ev] if rec_ev else []}
    if reason:
        ir["overall_recommendation"]["reason"] = reason
    ir["findings"] = findings
    store.add_unc("quality scores/decision", "dimension scores are deterministic "
                  "signal-count heuristics and the recommendation is rule-based over "
                  "located findings, not expert peer-review judgment; human_confirm "
                  "all scores and the decision", "human_confirm")


FINALIZERS = {
    "methods_stats_review": f_methods,
    "citation_fact_check": f_citation,
    "logic_argument_review": f_logic,
    "compliance_check": f_compliance,
    "quality_review": f_quality,
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
    store = Store(case, materials)
    store.register_sources(materials)
    kind = detect_kind(args.kind, case, store)
    ir = kit.base_ir(case, kind)

    store.parse_all()
    finalize_common(ir, store, case)
    builder = FINALIZERS.get(kind)
    if builder is None:
        raise RuntimeError(f"no autopilot builder for kind '{kind}'")
    builder(ir, store, case)
    ir["uncertainty"] = list(ir.get("uncertainty", [])) + list(store.uncertainty)
    dedup_uncertainty(ir)
    if not store.sources:
        ir["uncertainty"].append({"item": "materials",
                                  "reason": "input directory empty or unreadable; "
                                            "nothing to extract",
                                  "handling": "human_confirm"})

    kit.write_json(work_dir / "review_ir.json", ir)

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
                                                   "work_ir": str(work_dir / "review_ir.json")}},
                              notes=notes)
    if build_error:
        result["build_error"] = build_error
    kit.write_result(out_dir, result)
    print(json.dumps({"status": status, "case_id": case["case_id"], "kind": kind,
                      "n_outputs": len(outputs), "summary": summary,
                      "errors": validation["errors"],
                      "warnings": validation["warnings"][:10]},
                     ensure_ascii=False, indent=2))
    return 0 if status in ("success", "partial") else 1


def main():
    ap = argparse.ArgumentParser(description="review track autopilot (auto-extract IR + run engine)")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--kind", default=None)
    args = ap.parse_args()

    case, sources, kind = {}, [], None
    try:
        if kit is None or engine is None:
            raise RuntimeError("cannot import sibling w4kit.py / review_engine.py")
        return run(args)
    except Exception as e:
        traceback.print_exc()
        # honest fallback: NEVER exit without result.json
        try:
            case = kit.load_case(args.input) if kit else {}
            kind = kind or (args.kind or "quality_review")
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