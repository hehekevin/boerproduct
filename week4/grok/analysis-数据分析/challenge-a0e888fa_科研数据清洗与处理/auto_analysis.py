"""auto_analysis.py — deterministic "autopilot" entry point for the week4 ANALYSIS track.

Reads the ACTUAL organizer-provided local materials under --input, auto-extracts
a complete IR (sources / datasets / stats analyses / charts / generated code /
cleaning operations / SQL queries / pipeline steps), runs the EXISTING
analysis_engine (validate_ir + build) and writes an honest result.json preserving
every output_contract key + case_id. Stdlib only; additive — does not modify the
engine or w4kit.

Usage:
  PYTHONDONTWRITEBYTECODE=1 python auto_analysis.py --input /input --out /app/output \
      [--work /app/work] [--kind KIND]

Design rules:
  * Never fabricate: every number/quote/column comes from real file content;
    statistics in interpretations are recomputed via w4kit.describe/correlation/
    linreg on the actual rows (same functions the engine uses).
  * Judgment-heavy fields (interpretations, chart-type choice, cleaning rules,
    generated-code scope) get deterministic, evidence-grounded defaults and are
    flagged human_confirm in uncertainty[] (=> honest status "partial").
  * Defensive extraction: a bad/missing file becomes an honest gap, never a crash.
  * The WHOLE pipeline is wrapped: on ANY exception an honest result.json is still
    written (status partial/failed) with contract keys + case_id + sources + error.
  * After this baseline runs, the agent may refine /app/work/analysis_ir.json
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
    import analysis_engine as engine
except Exception:  # catastrophic import failure -> emergency writer below
    kit = None
    engine = None

AUTO_NOTE = ("auto_analysis autopilot: deterministic extraction from ACTUAL local "
             "materials + existing analysis_engine computation (every statistic "
             "recomputed from real rows; databases read-only; missing never treated "
             "as 0, never imputed). Judgment fields use documented evidence-grounded "
             "heuristics flagged human_confirm; refine work/analysis_ir.json and "
             "re-run assemble.py to improve.")

KIND_KEYWORDS = [
    ("code_gen_exec", ["编写并执行", "生成代码", "代码生成", "results.json",
                       "analysis_data", "code_gen", "code generation", "执行日志",
                       "runnable", "一段分析代码", "generated code"]),
    ("db_query_analysis", ["sqlite", "sql", "数据库", "查询", "join", "db_query",
                           "select ", "seed.sql", "只读", "read-only"]),
    ("data_cleaning", ["清洗", "哨兵", "去重", "单位换算", "data cleaning", "dedup",
                       "sentinel", "质量报告", "缺失值", "异常值"]),
    ("multi_step_analysis", ["多步", "流水线", "pipeline", "multi-step", "multi step",
                             "全流程", "multi_step", "步骤依赖"]),
    ("data_viz", ["可视化", "散点", "柱状", "图型", "图表", "svg", "visualization",
                  "chart", "scatter", "误差线", "data_viz", "坐标轴"]),
    ("stats_analysis", ["统计", "均值", "相关", "回归", "检验", "效应量", "置信区间",
                        "statistical", "welch", "anova", "correlation", "regression",
                        "describe", "描述", "分位数"]),
]

ID_NAMES = {"id", "sample", "sample_id", "index", "no", "row", "row_id", "uid",
            "record_id", "subject", "subject_id"}


# ── small helpers ────────────────────────────────────────────────────────────

def clip(s, n=600):
    s = str(s)
    return s if len(s) <= n else s[:n] + "..."


def fmt(x, nd=4):
    if x is None:
        return "n/a"
    try:
        return f"{float(x):.{nd}g}"
    except Exception:
        return str(x)


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


def read_material_text(path):
    data = Path(path).read_bytes()
    if str(path).lower().endswith(".pdf") or data[:5] == b"%PDF-":
        return pdf_text(data)
    return data.decode("utf-8", errors="replace")


def exact_line(text, needle):
    """Return the exact dictionary line containing needle (evidence quote)."""
    if not text or not needle:
        return None
    for ln in text.splitlines():
        if needle in ln:
            return ln.strip()
    return None


# ── dictionary parsing (field semantics / units / design / sentinels) ───────

def parse_dictionary(text):
    info = {"columns": {}, "text": text, "design_notes": [], "sentinels": {},
            "conversions": [], "key_columns": []}
    for ln in text.splitlines():
        m = re.match(r"^\s*[-*]\s*([A-Za-z_]\w*)\s*[:：]\s*(.+)$", ln)
        if m:
            col, desc = m.group(1), m.group(2)
            unit_m = re.search(r"单位\s*([A-Za-z0-9µμ/\^\-_.%·]+)", desc)
            info["columns"][col] = {
                "line": ln.strip(),
                "unit": unit_m.group(1) if unit_m else None,
                "numeric": "数值" in desc or "numeric" in desc.lower(),
                "categorical": "分类" in desc or "categor" in desc.lower(),
                "primary_key": "主键" in desc or "primary key" in desc.lower(),
                "outcome": ("结果变量" in desc or "响应" in desc
                            or "outcome" in desc.lower()),
                "group": ("分组" in desc or "处理组" in desc
                          or "group" in desc.lower()),
                "covariate": ("协变量" in desc or "自变量" in desc
                              or "covariate" in desc.lower()),
            }
            if info["columns"][col]["primary_key"]:
                # key may be composite: 'sample_id + timestamp'
                keys = re.findall(r"[A-Za-z_]\w*", desc.split("；")[0].split(";")[0])
                info["key_columns"] = [k for k in keys if k != col] or [col]
                if col not in info["key_columns"]:
                    info["key_columns"].insert(0, col)
        if re.search(r"独立|配对|非配对|independen|paired", ln):
            info["design_notes"].append(ln.strip())
        if re.search(r"哨兵|缺失|未检出|低于检测|sentinel|missing|not detected", ln, re.I):
            for tok in re.findall(r"(?<![\w.])(-?\d{2,}|ND|<LOD|N/A|NA)(?![\w.])", ln):
                if tok in ("ND",):
                    info["sentinels"][tok] = "not_detected"
                elif tok == "<LOD":
                    info["sentinels"][tok] = "below_detection_limit"
                elif tok in ("NA", "N/A"):
                    info["sentinels"][tok] = "missing_entry"
                else:
                    info["sentinels"][tok] = ("storage_fault_sentinel"
                                              if re.search(r"故障|fault", ln)
                                              else "missing_sentinel")
            info["missing_line"] = ln.strip()
        for cm in re.finditer(r"1\s*([A-Za-zµμ][A-Za-z0-9µμ/^.\-]*)\s*=\s*"
                              r"([\d.]+)\s*([A-Za-zµμ][A-Za-z0-9µμ/^.\-]*)", ln):
            info["conversions"].append({"from_unit": cm.group(1),
                                        "factor_expr": cm.group(2),
                                        "to_unit": cm.group(3),
                                        "line": ln.strip()})
    return info


# ── material store ───────────────────────────────────────────────────────────

class Store:
    def __init__(self, case, materials, work_dir):
        self.case = case
        self.work_dir = Path(work_dir)
        self.sources = []
        self.files = []
        self.tables = []        # parsed table datasets (real rows)
        self.databases = []     # {sid, did, path, kind: db|sql}
        self.dictionary = None  # parsed dictionary info
        self.documents = []     # other text files
        self.errors = []
        self.uncertainty = []
        self._did_seen = set()

    def register_sources(self, materials):
        for i, m in enumerate(materials, 1):
            sid = f"S{i}"
            ext = (m.get("ext") or "").lstrip(".") or "file"
            self.sources.append({"id": sid, "path": m["path"], "name": m["name"],
                                 "type": ext})
            self.files.append({"sid": sid, "path": m["path"], "name": m["name"],
                               "ext": ext, "role": None})

    def add_unc(self, item, reason, handling="human_confirm"):
        self.uncertainty.append({"item": item, "reason": reason, "handling": handling})

    def new_did(self, stem):
        did = re.sub(r"\W+", "_", str(stem)).strip("_") or "data"
        if did[0].isdigit():
            did = "d_" + did
        base, k = did, 2
        while did in self._did_seen:
            did = f"{base}_{k}"
            k += 1
        self._did_seen.add(did)
        return did

    def parse_all(self):
        # dictionaries FIRST so table classification can use field semantics
        ordered = []
        for f in self.files:
            is_dict = "dictionary" in f["name"].lower() or "字典" in f["name"]
            if not is_dict and f["ext"] in ("md", "txt", "markdown") and \
                    f["name"].lower() not in ("task.md",) and \
                    not f["name"].lower().startswith("readme"):
                try:
                    head = read_material_text(f["path"])[:2000]
                    is_dict = bool(re.search(r"数据字典|data dictionary", head, re.I))
                except Exception:
                    pass
            (ordered.insert(0, f) if is_dict else ordered.append(f))
        for f in ordered:
            try:
                self.parse_file(f)
            except Exception as e:
                self.errors.append(f"{f['name']}: {type(e).__name__}: {e}")
                self.add_unc(f["name"],
                             f"extraction failed: {e}; file registered but not parsed",
                             "human_confirm")

    def parse_file(self, f):
        low = f["name"].lower()
        if low == "case.json" or low == "task.md" or low.startswith("readme"):
            f["role"] = "task"
            return
        if f["ext"] in ("db", "sqlite", "sqlite3", "sql"):
            f["role"] = "database"
            self.databases.append({"sid": f["sid"], "path": f["path"],
                                   "did": self.new_did(Path(f["name"]).stem),
                                   "name": f["name"],
                                   "kind": "sql" if f["ext"] == "sql" else "db"})
            return
        if f["ext"] in ("csv", "tsv", "tab", "json"):
            try:
                rows = kit.read_table(f["path"])
            except Exception as e:
                f["role"] = "unparsed"
                self.add_unc(f["name"], f"table unreadable: {e}", "human_confirm")
                return
            if isinstance(rows, list) and rows and all(isinstance(r, dict) for r in rows):
                self.add_table(f, rows)
                return
            if f["ext"] == "json":
                f["role"] = "json"
                try:
                    f["json"] = kit.load_json(f["path"])
                except Exception:
                    pass
                self.add_unc(f["name"], "JSON is not a row table; registered as source only",
                             "note")
                return
            f["role"] = "empty_table"
            self.add_unc(f["name"], "table has no data rows", "human_confirm")
            return
        # text-ish (md/txt/pdf/anything else)
        try:
            text = read_material_text(f["path"])
        except Exception as e:
            self.add_unc(f["name"], f"cannot read bytes: {e}", "human_confirm")
            return
        f["text"] = text
        if "dictionary" in low or "字典" in f["name"] or \
                re.search(r"数据字典|data dictionary", text, re.I):
            f["role"] = "dictionary"
            self.dictionary = parse_dictionary(text)
            return
        f["role"] = "document"
        self.documents.append(f)

    def add_table(self, f, rows):
        columns = list(rows[0].keys())
        dinfo = (self.dictionary or {}).get("columns", {})
        n = len(rows)
        numeric, categorical = [], []
        for c in columns:
            vals = [r.get(c) for r in rows]
            nonempty = [v for v in vals if v not in (None, "")]
            nums = [kit.to_float(v) for v in nonempty]
            frac = (sum(1 for v in nums if v is not None) / len(nonempty)) if nonempty else 0.0
            distinct = len({str(v) for v in nonempty})
            dc = dinfo.get(c, {})
            id_like = (dc.get("primary_key") or c.lower() in ID_NAMES
                       or (nonempty and distinct == len(nonempty) and frac == 1.0
                           and all(float(v).is_integer() for v in nums if v is not None)
                           and c == columns[0] and not dc.get("numeric")))
            if dc.get("categorical"):
                categorical.append(c)
            elif dc.get("numeric") or (frac >= 0.8 and not id_like):
                if not id_like:
                    numeric.append(c)
            elif nonempty and 1 < distinct <= max(10, int(0.4 * n)):
                categorical.append(c)
        group_col = next((c for c in columns if dinfo.get(c, {}).get("group")
                          and c in categorical), None)
        if group_col is None:
            group_col = next((c for c in categorical
                              if "group" in c.lower() or "组" in c), None)
        if group_col is None:
            group_col = next((c for c in categorical
                              if 2 <= len({str(r.get(c)) for r in rows
                                           if r.get(c) not in (None, "")}) <= 8), None)
        outcome = next((c for c in numeric if dinfo.get(c, {}).get("outcome")), None)
        if outcome is None and numeric:
            outcome = numeric[-1]
        covariates = [c for c in numeric if c != outcome]
        covariates.sort(key=lambda c: 0 if dinfo.get(c, {}).get("covariate") else 1)
        id_cols = [c for c in columns if dinfo.get(c, {}).get("primary_key")
                   or c.lower() in ID_NAMES]
        key_cols = [c for c in (self.dictionary or {}).get("key_columns", [])
                    if c in columns] or id_cols[:1]
        t = {"sid": f["sid"], "did": self.new_did(Path(f["name"]).stem),
             "path": f["path"], "name": f["name"], "rows": rows, "columns": columns,
             "numeric": numeric, "categorical": categorical, "group": group_col,
             "outcome": outcome, "covariates": covariates, "id_cols": id_cols,
             "key_columns": key_cols, "n": n}
        f["role"] = "table"
        f["table"] = t
        self.tables.append(t)

    # -- shared dataset registration ----------------------------------------
    def register_datasets(self, ir):
        ir["sources"] = self.sources
        datasets = []
        for t in self.tables:
            datasets.append({"dataset_id": t["did"], "source_id": t["sid"],
                             "path": t["path"], "columns": t["columns"]})
        for d in self.databases:
            datasets.append({"dataset_id": d["did"], "source_id": d["sid"],
                             "path": d["path"]})
        ir["datasets"] = datasets

    def unit_of(self, col):
        dc = (self.dictionary or {}).get("columns", {}).get(col, {})
        return dc.get("unit")

    def unit_suffix(self, col):
        u = self.unit_of(col)
        return f" ({u})" if u else ""

    def dict_quote_ev(self, col):
        dc = (self.dictionary or {}).get("columns", {}).get(col, {})
        if dc.get("line") and self.dictionary:
            sid = next((f["sid"] for f in self.files if f.get("role") == "dictionary"),
                       None)
            if sid:
                return {"source_id": sid, "quote": dc["line"]}
        return None


def table_stats(t, col):
    return kit.describe([r.get(col) for r in t["rows"]])


def group_stats(t, col, gcol):
    groups = {}
    for r in t["rows"]:
        g = str(r.get(gcol)) if r.get(gcol) not in (None, "") else "(missing)"
        groups.setdefault(g, []).append(r.get(col))
    return {g: kit.describe(vals) for g, vals in groups.items()}


# ── kind detection ───────────────────────────────────────────────────────────

def apply_task_dataset_ids(store, case):
    """Honor dataset_id assignments explicitly stated in task.md (e.g.
    '读取 data.csv（... dataset_id = d）') so gold checks like n_rows_d resolve."""
    task = case.get("task_md") or ""
    for ln in task.splitlines():
        m = re.search(r"dataset_id\s*[=:：]\s*([A-Za-z_]\w*)", ln)
        if not m:
            continue
        new_id = m.group(1)
        fm = re.search(r"([A-Za-z0-9_.\-]+\.(?:csv|tsv|tab|json|db|sqlite|sqlite3|sql))", ln)
        target = None
        if fm:
            target = next((t for t in store.tables if t["name"] == fm.group(1)), None)
            if target is None:
                target = next((d for d in store.databases if d["name"] == fm.group(1)), None)
        if target is None and len(store.tables) == 1 and not store.databases:
            target = store.tables[0]
        if target is not None and new_id != target["did"] and \
                new_id not in store._did_seen:
            store._did_seen.discard(target["did"])
            target["did"] = new_id
            store._did_seen.add(new_id)


def detect_kind(args_kind, case, store):
    if args_kind:
        k = args_kind.strip().replace("-", "_")
        if not engine or k in engine.KINDS:
            return k
    skill = SCRIPT_DIR / "SKILL.md"
    if skill.exists():
        try:
            head = skill.read_text(encoding="utf-8", errors="replace")[:2000]
            m = re.search(r"^name:\s*analysis-([a-z0-9-]+)\s*$", head, re.M)
            if m:
                k = m.group(1).replace("-", "_")
                if not engine or k in engine.KINDS:
                    return k
        except Exception:
            pass
    blob = ((case.get("task_md") or "") + " " +
            json.dumps(case.get("raw") or {}, ensure_ascii=False)).lower()
    blob += " " + " ".join(f["name"].lower() for f in store.files)
    best, best_score = None, 0
    for kind, kws in KIND_KEYWORDS:
        score = sum(1 for kw in kws if kw.lower() in blob)
        if score > best_score:
            best, best_score = kind, score
    if best is None and store.databases:
        return "db_query_analysis"
    return best or "stats_analysis"


# ── per-kind builders ────────────────────────────────────────────────────────

def build_analyses(store, t):
    """Real stats analyses with data-tied interpretations (w4kit recomputation)."""
    analyses = []
    did = t["did"]
    design = list((store.dictionary or {}).get("design_notes", []))
    base_assumptions = ["missing/non-numeric cells excluded pairwise, never treated "
                        "as 0, never imputed (dictionary caliber)"] + design
    for col in t["numeric"]:
        d = table_stats(t, col)
        u = store.unit_suffix(col)
        skew = ""
        if d.get("n", 0) >= 3 and d.get("sd"):
            if d["mean"] > d["median"] * 1.05:
                skew = " The mean exceeds the median, suggesting right skew; median/quartiles may describe it better."
            elif d["mean"] < d["median"] * 0.95:
                skew = " The mean is below the median, suggesting left skew; median/quartiles may describe it better."
        interp = (f"Auto-extracted from the actual rows: {col}{u} has n={d.get('n', 0)} "
                  f"valid values ({d.get('missing', 0)} missing excluded), "
                  f"mean={fmt(d.get('mean'))}, sd={fmt(d.get('sd'))}, "
                  f"median={fmt(d.get('median'))}, IQR=[{fmt(d.get('q25'))}, "
                  f"{fmt(d.get('q75'))}], range=[{fmt(d.get('min'))}, {fmt(d.get('max'))}]."
                  + skew +
                  " This is a descriptive summary of the provided sample only; "
                  "practical significance requires a domain tolerance (human_confirm).")
        analyses.append({"analysis_id": f"desc_{col}", "type": "describe",
                         "dataset_id": did, "column": col,
                         "assumptions": list(base_assumptions),
                         "interpretation": interp})
    outcome, gcol = t["outcome"], t["group"]
    if outcome and gcol:
        gs = group_stats(t, outcome, gcol)
        levels = sorted(gs)
        parts = [f"{g}: n={gs[g].get('n', 0)}, mean={fmt(gs[g].get('mean'))}"
                 for g in levels]
        diff_txt = ""
        if len(levels) == 2:
            a, b = levels
            ma, mb = gs[a].get("mean"), gs[b].get("mean")
            if ma is not None and mb is not None:
                diff_txt = (f" Observed mean difference ({b} - {a}) = "
                            f"{fmt(mb - ma)}{store.unit_suffix(outcome)}.")
        method = "Welch t-test" if len(levels) == 2 else "one-way ANOVA"
        interp = (f"Auto-extracted group summaries of {outcome}{store.unit_suffix(outcome)} "
                  f"by {gcol}: " + "; ".join(parts) + "." + diff_txt +
                  f" The engine applies {method} with effect size and 95% CI "
                  "(see stats_results.json); independence is assumed from the "
                  "dictionary design. Statistical significance does not by itself "
                  "establish practical importance — judge the CI against the domain "
                  "tolerance (human_confirm).")
        analyses.append({"analysis_id": f"cmp_{gcol}_{outcome}", "type": "compare_groups",
                         "dataset_id": did, "column": outcome, "group_column": gcol,
                         "family": f"fam_{did}",
                         "assumptions": list(base_assumptions),
                         "interpretation": interp})
    if outcome:
        for cov in t["covariates"][:3]:
            xs = [r.get(cov) for r in t["rows"]]
            ys = [r.get(outcome) for r in t["rows"]]
            r_val = kit.correlation(xs, ys)
            direction = "positive" if (r_val or 0) > 0 else "negative"
            strength = ("strong" if abs(r_val or 0) >= 0.7 else
                        "moderate" if abs(r_val or 0) >= 0.4 else "weak")
            interp = (f"Auto-extracted from the actual rows: Pearson r({cov}, {outcome}) "
                      f"= {fmt(r_val)} — a {strength} {direction} LINEAR association "
                      f"(pairwise-complete cases). Association is not causation; a "
                      f"curved monotonic relation can understates |r| (Spearman may "
                      f"differ); CI and p are in stats_results.json (human_confirm).")
            analyses.append({"analysis_id": f"corr_{cov}_{outcome}", "type": "correlation",
                             "dataset_id": did, "columns": [cov, outcome],
                             "method": "pearson", "family": f"fam_{did}",
                             "assumptions": ["pairwise-complete observations; linear association only"],
                             "interpretation": interp})
            lr = kit.linreg(xs, ys)
            if lr:
                interp = (f"Auto-extracted OLS fit on the actual rows: {outcome} = "
                          f"{fmt(lr['intercept'])} + {fmt(lr['slope'])} * {cov} "
                          f"(n={lr['n']}, R2={fmt(lr['r2'])}). Each +1{store.unit_suffix(cov)} "
                          f"of {cov} corresponds to an average change of "
                          f"{fmt(lr['slope'])}{store.unit_suffix(outcome)} in {outcome}. "
                          "A linear model is an approximation; inspect residuals before "
                          "extrapolating; slope CI expresses uncertainty (human_confirm).")
            else:
                interp = ("Insufficient paired numeric data for a regression; the engine "
                          "will report insufficient_evidence (no fabricated fit).")
            analyses.append({"analysis_id": f"reg_{cov}_{outcome}", "type": "regression",
                             "dataset_id": did, "columns": [cov, outcome],
                             "assumptions": ["OLS on pairwise-complete cases; linear approximation"],
                             "interpretation": interp})
    return analyses


def f_stats(ir, store, case):
    analyses = []
    for t in store.tables:
        analyses.extend(build_analyses(store, t))
    ir["stats"] = {"analyses": analyses}
    if not analyses:
        store.add_unc("stats.analyses", "no numeric data table recognized in materials; "
                      "nothing to compute (cannot fabricate)", "human_confirm")
    store.add_unc("interpretations", "interpretations are auto-generated data-tied "
                  "summaries (numbers recomputed via w4kit on real rows), not expert "
                  "judgment; refine within budget", "human_confirm")


def build_charts(store, t):
    charts = []
    did, nums, gcol = t["did"], t["numeric"], t["group"]
    outcome = t["outcome"]
    if len(nums) >= 2:
        x = t["covariates"][0] if t["covariates"] else nums[0]
        y = outcome if outcome and outcome != x else next(c for c in nums if c != x)
        gs = group_stats(t, y, gcol) if gcol else {}
        n_txt = (", ".join(f"{g}: n={gs[g].get('n', 0)}" for g in sorted(gs))
                 if gs else f"n={t['n']}")
        ch = {"chart_id": f"scatter_{x}_{y}", "chart_type": "scatter",
              "dataset_id": did, "x": x, "y": y,
              "title": f"{y} vs {x}" + (f" by {gcol}" if gcol else ""),
              "x_label": x + store.unit_suffix(x), "y_label": y + store.unit_suffix(y),
              "caption": (f"{n_txt}; points are individual observations; no error bars "
                          "(raw scatter). Missing/non-numeric rows are skipped and "
                          "counted, never drawn as 0."),
              "rationale": ("Two continuous variables with association intent -> scatter "
                            "with position encoding. NOT recommended: pie (no composition), "
                            "line (x is not an ordered time series)."),
              "width_mm": 180, "height_mm": 120}
        if gcol:
            ch["group_by"] = gcol
        charts.append(ch)
    if gcol and outcome:
        gs = group_stats(t, outcome, gcol)
        n_txt = ", ".join(f"{g}: n={gs[g].get('n', 0)}" for g in sorted(gs))
        charts.append({"chart_id": f"bar_mean_{outcome}", "chart_type": "bar",
                       "dataset_id": did, "x": gcol, "y": outcome,
                       "aggregate": "mean", "error_bars": "sd",
                       "title": f"Mean {outcome} by {gcol} (SD)",
                       "x_label": gcol, "y_label": f"mean {outcome}" + store.unit_suffix(outcome),
                       "caption": (f"Bars = mean {outcome} per {gcol} ({n_txt}); error bars = "
                                   "standard deviation (sd), NOT se or CI; bars start at "
                                   "zero baseline; missing excluded, never 0."),
                       "rationale": ("Categorical comparison of a numeric outcome -> bar with "
                                     "length encoding and zero baseline. NOT recommended: "
                                     "pie/area (exaggerates differences), truncated axis."),
                       "width_mm": 120, "height_mm": 100})
    if not charts and nums:
        col = nums[0]
        d = table_stats(t, col)
        charts.append({"chart_id": f"hist_{col}", "chart_type": "histogram",
                       "dataset_id": did, "x": col, "bins": 8,
                       "title": f"Distribution of {col}",
                       "x_label": col + store.unit_suffix(col), "y_label": "count",
                       "caption": (f"n={d.get('n', 0)} valid values ({d.get('missing', 0)} "
                                   "missing skipped and counted); 8 equal-width bins over "
                                   "the observed range; counts are raw rows."),
                       "rationale": ("Single continuous variable, distribution intent -> "
                                     "histogram. NOT recommended: pie (no composition)."),
                       "width_mm": 140, "height_mm": 100})
    if not charts and gcol:
        charts.append({"chart_id": f"bar_count_{gcol}", "chart_type": "bar",
                       "dataset_id": did, "x": gcol, "aggregate": "count",
                       "title": f"Row count by {gcol}", "x_label": gcol, "y_label": "count",
                       "caption": f"Bars = raw row counts per {gcol} (n={t['n']} total); zero baseline.",
                       "rationale": "Categorical frequency -> count bar; not pie.",
                       "width_mm": 120, "height_mm": 100})
    return charts


def f_viz(ir, store, case):
    charts = []
    for t in store.tables:
        charts.extend(build_charts(store, t))
    ir["charts"] = charts
    if not charts:
        store.add_unc("charts", "no plottable numeric/categorical table recognized in "
                      "materials; nothing to render (cannot fabricate)", "human_confirm")
    store.add_unc("chart-type choice / captions", "chart types and captions are "
                  "auto-derived from column kinds and real counts (heuristic design "
                  "choice); human_confirm against the workorder", "human_confirm")


CODE_TEMPLATE = '''import csv, json, os

# Auto-generated by auto_analysis.py from the ACTUAL materials.
# Paths come from the engine-provided env (no hardcoded machine path).
paths = json.loads(os.environ.get("ANALYSIS_DATA", "{}"))
inp = os.environ.get("ANALYSIS_INPUT", ".")
FILES = __FILES__          # dataset_id -> fallback filename (auto-registered)
NUMERIC = __NUMERIC__      # dataset_id -> numeric columns (auto-detected from real rows)

def load(did):
    p = paths.get(did) or os.path.join(inp, FILES[did])
    delim = "\\t" if str(p).lower().endswith((".tsv", ".tab")) else ","
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=delim))

def stats(vals):
    # Caliber per dictionary: blank/non-numeric excluded; NEVER treat missing as 0.
    nums = []
    for v in vals:
        s = str(v).strip() if v is not None else ""
        if s == "":
            continue
        try:
            nums.append(float(s))
        except ValueError:
            continue
    n = len(nums)
    mean = sum(nums) / n if n else None
    sd = (sum((x - mean) ** 2 for x in nums) / (n - 1)) ** 0.5 if n > 1 else None
    return {"n_numeric": n, "mean": mean, "sd": sd,
            "min": min(nums) if nums else None, "max": max(nums) if nums else None}

res = {}
primary = __PRIMARY__
for did in FILES:
    rows = load(did)
    per = {"n": len(rows)}
    for col in NUMERIC.get(did, []):
        per[col] = stats([r.get(col) for r in rows])
    if did == primary:
        res["n"] = len(rows)
        for col, st in per.items():
            if isinstance(st, dict):
                res["n_numeric_" + col] = st["n_numeric"]
                res["mean_" + col] = st["mean"]
                res["sd_" + col] = st["sd"]
        # convenience aliases requested by the task spec (auto-detected)
        for alias, col in __ALIASES__.items():
            if col in per:
                res[alias] = per[col]["mean"]
        if __OUTCOME__ and __OUTCOME__ in per:
            res["n_numeric"] = per[__OUTCOME__]["n_numeric"]
    else:
        res[did] = per

with open("results.json", "w", encoding="utf-8") as fh:
    json.dump(res, fh)
print(json.dumps(res))
'''


def f_code(ir, store, case):
    task = case.get("task_md") or ""
    tables = store.tables
    primary = tables[0] if tables else None
    files = {t["did"]: t["name"] for t in tables}
    numeric = {t["did"]: t["numeric"] for t in tables}
    outcome = primary["outcome"] if primary else None
    # task-requested mean columns (e.g. 'strength 的均值' / 'mean strength')
    requested = []
    for m in re.finditer(r"([A-Za-z_]\w*)\s*的均值|mean\s+([A-Za-z_]\w*)", task):
        c = m.group(1) or m.group(2)
        if primary and c in primary["columns"] and c not in requested:
            requested.append(c)
    if not requested and outcome:
        requested = [outcome]
    aliases = {f"mean_{c}": c for c in requested}
    # 'n_numeric' alias: task may name the outcome explicitly
    src = (CODE_TEMPLATE
           .replace("__FILES__", json.dumps(files, ensure_ascii=False))
           .replace("__NUMERIC__", json.dumps(numeric, ensure_ascii=False))
           .replace("__PRIMARY__", repr(primary["did"] if primary else None))
           .replace("__ALIASES__", json.dumps(aliases, ensure_ascii=False))
           .replace("__OUTCOME__", repr(outcome)))
    expected_outputs = ["n", "n_numeric"] + [f"mean_{c}" for c in requested]
    ir["code"] = {
        "spec": {"task": clip(task.strip(), 1200) or
                         "(task.md absent; compute per-column summary stats from the actual tables)",
                 "inputs": [t["did"] for t in tables],
                 "expected_outputs": expected_outputs, "language": "python"},
        "generated": {"source": src},
        "exec": {"mode": "subprocess", "timeout_s": 60},
        "checks": [],
    }
    checks = ir["code"]["checks"]
    # gold expectations explicitly stated in the task (never invented)
    for m in re.finditer(r"([A-Za-z_]\w*)\s*(?:应等于|等于|should equal|must equal)\s*"
                         r"(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", task):
        name, val = m.group(1), float(m.group(2))
        tail = task[m.end():m.end() + 40]
        tol_m = re.search(r"容差\s*([0-9.eE+-]+)|tolerance\s*([0-9.eE+-]+)", tail)
        tol = float(tol_m.group(1) or tol_m.group(2)) if tol_m else 1e-6
        checks.append({"check_id": f"gold_{name}", "expr": name, "expected": val,
                       "tolerance": tol,
                       "description": f"expected value stated in task.md: {name} = {val}"})
    # real-data cross-checks (row counts computed from the actual files)
    for t in tables:
        checks.append({"check_id": f"rows_{t['did']}", "expr": f"n_rows_{t['did']}",
                       "expected": t["n"], "tolerance": 0,
                       "description": f"row count cross-check vs actual source {t['name']}"})
    if not tables:
        store.add_unc("code.inputs", "no data table recognized in materials; generated "
                      "code has no inputs (honest gap)", "human_confirm")
    if not any(c["check_id"].startswith("gold_") for c in checks):
        store.add_unc("code.checks", "no gold expected values stated in task.md; "
                      "verification limited to real row-count cross-checks", "human_confirm")
    store.add_unc("generated code scope", "code is an auto-generated stdlib template "
                  "computing per-column summary stats (missing excluded, never 0) from "
                  "the real tables; task-specific logic beyond detected mean columns "
                  "needs human review/refinement", "human_confirm")


def f_cleaning(ir, store, case):
    ops = []
    dinfo = store.dictionary or {}
    for t in store.tables:
        did = t["did"]
        sentinels = dict(dinfo.get("sentinels", {}))
        sentinels.setdefault("", "missing_entry")
        ev = None
        if dinfo.get("missing_line"):
            sid = next((f["sid"] for f in store.files if f.get("role") == "dictionary"), None)
            if sid:
                ev = {"source_id": sid, "quote": dinfo["missing_line"]}
        op = {"op_id": f"op_flag_missing_{did}", "type": "flag_missing",
              "dataset_id": did, "columns": t["columns"],
              "params": {"sentinel_map": sentinels, "blank_is_missing": True},
              "rule": "dictionary caliber: sentinels/blanks are missing or faults, not measurements; true 0 is valid",
              "reason": "distinguish missing/sentinel cells from true zeros; no imputation"}
        if ev:
            op["evidence"] = ev
        ops.append(op)
        # dedup ONLY when real duplicate keys exist in the actual rows
        keys = t["key_columns"]
        if keys:
            seen, dups = set(), 0
            for r in t["rows"]:
                k = tuple(str(r.get(c)) for c in keys)
                if k in seen:
                    dups += 1
                seen.add(k)
            if dups:
                ops.append({"op_id": f"op_dedup_{did}", "type": "dedup",
                            "dataset_id": did,
                            "params": {"key_columns": keys, "keep": "first"},
                            "rule": f"primary key {' + '.join(keys)} (dictionary/id column); keep first",
                            "reason": f"{dups} duplicate-key row(s) actually present in the source; removed rows logged in full",
                            "evidence": store.dict_quote_ev(keys[0]) or
                                        {"source_id": t["sid"], "field": "+".join(keys)}})
        # unit conversion ONLY when the dictionary states a real factor and the
        # source unit actually occurs in the data
        unit_col = next((c for c in t["columns"] if c.lower() in ("unit", "units", "单位")), None)
        if unit_col:
            present = {str(r.get(unit_col)) for r in t["rows"]}
            for i, cv in enumerate(dinfo.get("conversions", []), 1):
                target_col = t["outcome"] or (t["numeric"][0] if t["numeric"] else None)
                if cv["from_unit"] in present and target_col:
                    ops.append({"op_id": f"op_unit_{did}_{i}", "type": "unit_convert",
                                "dataset_id": did,
                                "column": target_col,
                                "params": {"unit_column": unit_col,
                                           "from_unit": cv["from_unit"],
                                           "to_unit": cv["to_unit"],
                                           "factor_expr": cv["factor_expr"]},
                                "rule": f"1 {cv['from_unit']} = {cv['factor_expr']} {cv['to_unit']} (dictionary); reversible, original preserved",
                                "reason": f"harmonize to dictionary target unit {cv['to_unit']}",
                                "evidence": {"source_id": next((f["sid"] for f in store.files if f.get("role") == "dictionary"), t["sid"]),
                                             "quote": cv["line"]}})
        if t["outcome"]:
            ops.append({"op_id": f"op_outlier_{did}", "type": "outlier_flag",
                        "dataset_id": did, "column": t["outcome"],
                        "params": {"method": "iqr", "k": 1.5, "action": "flag"},
                        "rule": "Tukey IQR fence k=1.5 on actual values; flag only, no deletion",
                        "reason": "diagnostic outlier screening; flagged values may be real extremes — human review",
                        "evidence": {"source_id": t["sid"], "field": t["outcome"]}})
    ir["cleaning"] = {"operations": ops}
    if not ops:
        store.add_unc("cleaning.operations", "no data table recognized in materials; "
                      "no cleaning ops derivable (cannot fabricate)", "human_confirm")
    store.add_unc("cleaning rules", "operations auto-derived from dictionary caliber and "
                  "real duplicate/sentinel/unit evidence; destructive ops are logged and "
                  "reversible; human_confirm the rule set", "human_confirm")


def _db_working_path(store, d):
    """Real .db -> use as-is (read-only). .sql dump -> restore a working copy
    under --work for schema discovery (original never modified)."""
    p = Path(d["path"])
    if d["kind"] != "sql":
        return str(p)
    work = store.work_dir / "_db_discover"
    work.mkdir(parents=True, exist_ok=True)
    copy = work / (p.stem + ".db")
    if not copy.exists():
        import sqlite3
        con = sqlite3.connect(str(copy))
        try:
            con.executescript(read_material_text(p))
            con.commit()
        finally:
            con.close()
    return str(copy)


def f_db(ir, store, case):
    queries = []
    for d in store.databases:
        did = d["did"]
        try:
            dbp = _db_working_path(store, d)
            tables = kit.sqlite_tables(dbp)
        except Exception as e:
            store.add_unc(f"database {d['name']}", f"schema discovery failed: {e}",
                          "human_confirm")
            continue
        for tbl in tables[:4]:
            try:
                cnt = kit.sqlite_query(dbp, f'SELECT COUNT(*) AS n FROM "{tbl}"')
                n = cnt["rows"][0][0] if cnt["rows"] else 0
                queries.append({"query_id": f"q_count_{tbl}", "dataset_id": did,
                                "question": f"How many rows does {tbl} contain?",
                                "sql": f'SELECT COUNT(*) AS n FROM "{tbl}"', "params": [],
                                "interpretation": (f"Auto-executed read-only on the actual "
                                                   f"database: {tbl} contains {n} rows "
                                                   f"(sample grain; no join, no inflation).")})
                cols = kit.sqlite_query(dbp, f'PRAGMA table_info("{tbl}")')
                colnames = [r[1] for r in cols["rows"]]
                sample = kit.sqlite_query(dbp, f'SELECT * FROM "{tbl}" LIMIT 200')
                rows = [dict(zip(sample["columns"], r)) for r in sample["rows"]]
                # categorical group column with few levels -> grouped counts
                gcol = next((c for c in colnames
                             if rows and 1 < len({str(r.get(c)) for r in rows}) <= 8
                             and not all(isinstance(r.get(c), (int, float)) for r in rows)),
                            None)
                if gcol:
                    q = (f'SELECT "{gcol}", COUNT(*) AS n FROM "{tbl}" '
                         f'GROUP BY "{gcol}" ORDER BY "{gcol}"')
                    gr = kit.sqlite_query(dbp, q)
                    txt = ", ".join(f"{r[0]}: n={r[1]}" for r in gr["rows"])
                    queries.append({"query_id": f"q_groups_{tbl}", "dataset_id": did,
                                    "question": f"Row counts per {gcol} in {tbl}?",
                                    "sql": q, "params": [],
                                    "interpretation": (f"Auto-executed read-only: {gcol} is a "
                                                       f"categorical code, counted not averaged. "
                                                       f"Actual counts: {txt}.")})
                # numeric summary
                numcols = [c for c in colnames
                           if rows and all(r.get(c) is None or isinstance(r.get(c), (int, float))
                                           for r in rows)
                           and any(isinstance(r.get(c), (int, float)) for r in rows)]
                if numcols:
                    c = numcols[-1]
                    q = (f'SELECT COUNT("{c}") AS n_valid, AVG("{c}") AS mean_{c}, '
                         f'MIN("{c}") AS min_{c}, MAX("{c}") AS max_{c} FROM "{tbl}"')
                    sr = kit.sqlite_query(dbp, q)
                    if sr["rows"]:
                        nv, mean, lo, hi = sr["rows"][0]
                        queries.append({"query_id": f"q_summary_{tbl}_{c}", "dataset_id": did,
                                        "question": f"Summary of {c} in {tbl} (NULLs excluded)?",
                                        "sql": q, "params": [],
                                        "interpretation": (f"Auto-executed read-only: {c} has "
                                                           f"{nv} non-NULL values; SQL AVG ignores "
                                                           f"NULL (never 0): mean={fmt(mean)}, "
                                                           f"range=[{fmt(lo)}, {fmt(hi)}].")})
            except Exception as e:
                store.add_unc(f"table {tbl}", f"auto query failed: {e}", "human_confirm")
    ir["queries"] = queries[:10]
    if not queries:
        store.add_unc("queries", "no SQLite database/dump recognized in materials; "
                      "no queries derivable (cannot fabricate)", "human_confirm")
    store.add_unc("query set", "queries are auto-generated exploratory summaries "
                  "executed read-only on the actual database; task-specific questions "
                  "need human refinement", "human_confirm")


def f_multi(ir, store, case):
    steps = []
    dids = [t["did"] for t in store.tables] + [d["did"] for d in store.databases]
    steps.append({"step_id": "s1_load", "kind": "load", "depends_on": [],
                  "payload": {"dataset_ids": dids}})
    prev = "s1_load"
    # clean step: dedup only when real duplicates exist
    clean_ops, deduped = [], {}
    for t in store.tables:
        keys = t["key_columns"]
        if not keys:
            continue
        seen, dups, kept = set(), 0, []
        for r in t["rows"]:
            k = tuple(str(r.get(c)) for c in keys)
            if k in seen:
                dups += 1
                continue
            seen.add(k)
            kept.append(r)
        if dups:
            clean_ops.append({"op_id": f"dedup_{t['did']}", "type": "dedup",
                              "dataset_id": t["did"],
                              "params": {"key_columns": keys, "keep": "first"},
                              "rule": f"primary key {' + '.join(keys)}; keep first",
                              "reason": f"{dups} duplicate-key row(s) actually present; removed rows logged",
                              "evidence": {"source_id": t["sid"], "field": "+".join(keys)}})
            deduped[t["did"]] = kept
    if clean_ops:
        steps.append({"step_id": "s2_clean", "kind": "clean", "depends_on": [prev],
                      "payload": {"operations": clean_ops}})
        prev = "s2_clean"
    analyses = []
    for t in store.tables:
        tt = dict(t)
        if t["did"] in deduped:
            tt["rows"] = deduped[t["did"]]
            tt["n"] = len(tt["rows"])
        analyses.extend(build_analyses(store, tt))
    if analyses:
        steps.append({"step_id": "s3_stats", "kind": "stats", "depends_on": [prev],
                      "payload": {"analyses": analyses}})
    charts = []
    for t in store.tables:
        tt = dict(t)
        if t["did"] in deduped:
            tt["rows"] = deduped[t["did"]]
            tt["n"] = len(tt["rows"])
        charts.extend(build_charts(store, tt)[:2])
    if charts:
        steps.append({"step_id": "s4_viz", "kind": "viz", "depends_on": [prev],
                      "payload": {"charts": charts}})
    deps = [s["step_id"] for s in steps if s["kind"] in ("stats", "viz")] or [prev]
    # interpret step: text + claims back-filled from REAL recomputed numbers
    text_parts, claims = [], []
    for t in store.tables:
        rows = deduped.get(t["did"], t["rows"])
        if t["outcome"]:
            d = kit.describe([r.get(t["outcome"]) for r in rows])
            aid = f"desc_{t['outcome']}"
            text_parts.append(f"{t['name']}: n={len(rows)} rows"
                              + (f" after dedup (from {t['n']})" if t["did"] in deduped else "")
                              + f"; {t['outcome']} mean={fmt(d.get('mean'))}"
                              + store.unit_suffix(t["outcome"])
                              + f", sd={fmt(d.get('sd'))}, median={fmt(d.get('median'))} "
                              f"(missing excluded, never 0).")
            if d.get("n"):
                claims.append({"metric": f"{aid}.mean", "value": d["mean"],
                               "tolerance": 1e-6})
    text = ("Auto pipeline summary computed from the actual materials: "
            + " ".join(text_parts) +
            " Numbers are back-filled from w4kit recomputation on the real rows and "
            "cross-checked against the engine metrics; interpretation beyond these "
            "descriptives requires human judgment (human_confirm).")
    steps.append({"step_id": "s5_interpret", "kind": "interpret", "depends_on": deps,
                  "payload": {"text": text, "claims": claims}})
    ir["steps"] = steps
    if not store.tables and not store.databases:
        store.add_unc("steps", "no data materials recognized; pipeline has only a "
                      "load/interpret shell (honest gap)", "human_confirm")
    store.add_unc("pipeline interpretation", "step payloads and interpretation are "
                  "auto-derived from real data; human_confirm the analysis plan",
                  "human_confirm")


FINALIZERS = {
    "stats_analysis": f_stats,
    "data_viz": f_viz,
    "code_gen_exec": f_code,
    "data_cleaning": f_cleaning,
    "db_query_analysis": f_db,
    "multi_step_analysis": f_multi,
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
    store = Store(case, materials, work_dir)
    store.register_sources(materials)
    store.parse_all()
    apply_task_dataset_ids(store, case)
    kind = detect_kind(args.kind, case, store)
    ir = kit.base_ir(case, kind)
    ir["_ir_dir"] = str(work_dir.resolve())
    store.register_datasets(ir)
    ir["provenance"] = {"pipeline": "actual material -> auto_extract -> IR -> validate "
                                    "-> compute -> artifact -> result",
                        "changes": [{"step": "auto_extract", "at": kit.utc_now(),
                                     "detail": f"deterministic extraction from "
                                               f"{len(store.sources)} material files"}]}
    FINALIZERS[kind](ir, store, case)
    ir["uncertainty"] = list(store.uncertainty)
    for e in store.errors:
        ir["uncertainty"].append({"item": "extraction", "reason": e,
                                  "handling": "human_confirm"})
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

    kit.write_json(work_dir / "analysis_ir.json", ir)

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
    n_items = (len(ir.get("stats", {}).get("analyses", []))
               or len(ir.get("charts", [])) or len(ir.get("queries", []))
               or len(ir.get("cleaning", {}).get("operations", []))
               or len(ir.get("steps", [])))
    result = kit.build_result(case, ir, outputs, status, validation=validation,
                              extra={"summary": summary,
                                     "autopilot": {"kind": kind,
                                                   "n_materials": len(materials),
                                                   "n_datasets": len(ir.get("datasets", [])),
                                                   "n_items": n_items,
                                                   "work_ir": str(work_dir / "analysis_ir.json")}},
                              notes=notes)
    if build_error:
        result["build_error"] = build_error
    kit.write_result(out_dir, result)
    print(json.dumps({"status": status, "case_id": case["case_id"], "kind": kind,
                      "n_outputs": len(outputs), "n_datasets": len(ir.get("datasets", [])),
                      "n_items": n_items, "summary": summary,
                      "errors": validation["errors"],
                      "warnings": validation["warnings"][:10]},
                     ensure_ascii=False, indent=2))
    return 0 if status in ("success", "partial") else 1


def main():
    ap = argparse.ArgumentParser(description="analysis track autopilot (auto-extract IR + run engine)")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--kind", default=None)
    args = ap.parse_args()

    case, sources, kind = {}, [], None
    try:
        if kit is None or engine is None:
            raise RuntimeError("cannot import sibling w4kit.py / analysis_engine.py")
        return run(args)
    except Exception as e:
        traceback.print_exc()
        # honest fallback: NEVER exit without result.json
        try:
            case = kit.load_case(args.input) if kit else {}
            kind = kind or (args.kind or "stats_analysis")
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