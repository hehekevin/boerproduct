"""arena_write_engine — deterministic engine for the 5 product-arena WRITING variants.

Shared by: polish / reference_manage / intro_related / methods_section / latex.
The Agent reads the ACTUAL organizer material under /input and fills a kind-specific
IR (sources[] + claims/evidence + citations + segments/references/sections/parameters/
latex). This module validates the IR (reusing writekit's cross-cutting checks) and
deterministically builds editable artifacts + provenance + honest checks. It never
invents facts: missing material -> not_reported / insufficient_evidence + human_confirm.

stdlib only. docx via docxkit (OOXML zipfile). LaTeX is structure-validated locally;
a real compile is attempted only if a TeX compiler exists (runtime latex-compiler),
otherwise the result is honest about compile-not-run.
"""
from __future__ import annotations

import csv
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import w4kit
import writekit
import docxkit

ARENA_KINDS = {"polish", "reference_manage", "intro_related", "methods_section", "latex"}
CHANGE_TYPES = {"grammar", "syntax", "clarity", "terminology", "tone", "punctuation",
                "minimal_edit", "cohesion", "register"}
REF_STYLES = {"gb/t 7714", "gb/t7714", "gbt7714", "apa", "ieee"}
RECORD_STATUS = w4kit.RECORD_STATUS


# ── shared helpers ──────────────────────────────────────────────────────────

def _source_errors(ir: dict) -> list:
    """Every 'source'/'source_id' locator anywhere must reference a registered source."""
    ids = {s.get("id") for s in ir.get("sources", []) if s.get("id")}
    errs = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("source", "source_id") and isinstance(v, str) and v not in ids:
                    errs.append(f"locator references unknown source '{v}'")
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk({k: v for k, v in ir.items() if k != "sources"})
    return list(dict.fromkeys(errs))


def _nums(text):
    return writekit._nums_in(text)


_CITE_RE = (r"\[[A-Za-z]*\d+(?:[,;-]\s*[A-Za-z]*\d+)*\]|\\cite\{[^}]*\}|"
            r"\([A-Z][A-Za-z]+(?: et al\.)?,? \d{4}\)")


def _cite_markers(text):
    return set(re.findall(_CITE_RE, str(text)))


def _strip_cites(text):
    """Remove citation markers so their key digits aren't mistaken for data numbers."""
    return re.sub(_CITE_RE, "", str(text))


def _dedup(seq):
    return list(dict.fromkeys(seq))


# ── validation ──────────────────────────────────────────────────────────────

def validate_ir(ir: dict) -> dict:
    # writekit covers ir_version / case_id / kind / claims / citations / numbers /
    # sections / glossary / revisions; KINDS extended with the arena kinds.
    wv = writekit.validate_writing(ir)
    errors, warnings = list(wv["errors"]), list(wv["warnings"])
    errors += _source_errors(ir)
    kind = ir.get("kind")
    if kind == "polish":
        e, w = _val_polish(ir)
    elif kind == "reference_manage":
        e, w = _val_refs(ir)
    elif kind == "intro_related":
        e, w = _val_intro(ir)
    elif kind == "methods_section":
        e, w = _val_methods(ir)
    elif kind == "latex":
        e, w = _val_latex(ir)
    else:
        e, w = [], []
    errors += e
    warnings += w
    return {"ok": not errors, "errors": _dedup(errors), "warnings": _dedup(warnings)}


def _val_polish(ir):
    e, w = [], []
    segs = ir.get("segments", [])
    if not segs:
        e.append("polish requires segments[] (segment-level original<->revised)")
    for s in segs:
        sid = s.get("id", "?")
        if not s.get("original"):
            e.append(f"segment {sid}: missing original text")
        if not s.get("revised"):
            e.append(f"segment {sid}: missing revised text")
        if not s.get("reason"):
            w.append(f"segment {sid}: no reason (讲得清)")
        ct = s.get("change_type")
        if ct and ct not in CHANGE_TYPES:
            w.append(f"segment {sid}: unknown change_type '{ct}'")
        if s.get("meaning_preserved") is False:
            w.append(f"segment {sid}: meaning_preserved=false -> human_confirm")
    return e, w


def _val_refs(ir):
    e, w = [], []
    style = str(ir.get("target_style", "")).lower().strip()
    if style not in REF_STYLES:
        e.append(f"target_style must be one of GB/T 7714 / APA / IEEE (got '{ir.get('target_style')}')")
    refs = ir.get("references", [])
    if not refs:
        e.append("reference_manage requires references[]")
    rids = {r.get("id") for r in refs}
    for r in refs:
        if not r.get("title"):
            w.append(f"reference {r.get('id')}: missing title")
        if not r.get("source"):
            w.append(f"reference {r.get('id')}: no source (unverifiable)")
    for c in ir.get("in_text_citations", []):
        if not c.get("ref_id"):
            e.append(f"in_text {c.get('id')}: missing ref_id")
        elif c["ref_id"] not in rids:
            e.append(f"in_text {c.get('id')}: ref_id '{c['ref_id']}' not in references[]")
        if not c.get("marker"):
            w.append(f"in_text {c.get('id')}: no marker")
    return e, w


def _val_intro(ir):
    e, w = [], []
    have = {s.get("role") or s.get("heading") for s in ir.get("sections", [])}
    for r in ("Introduction", "Related Work"):
        if r not in have:
            w.append(f"intro_related: section '{r}' missing (flag explicitly)")
    cites = {c.get("id") for c in ir.get("citations", [])}
    gap = ir.get("research_gap", {})
    if gap:
        if not gap.get("statement"):
            w.append("research_gap: no statement")
        for d in gap.get("derived_from", []):
            if d not in cites:
                e.append(f"research_gap.derived_from '{d}' not in citations registry")
        if not gap.get("derived_from"):
            w.append("research_gap: not derived from cited literature (说得实)")
    for ct in ir.get("contributions", []):
        if not ct.get("text"):
            w.append(f"contribution {ct.get('id')}: empty text")
        if not (ct.get("evidence") or ct.get("claim_ids")):
            w.append(f"contribution {ct.get('id')}: no evidence/claim binding (对得上)")
    return e, w


def _val_methods(ir):
    e, w = [], []
    have = {s.get("role") or s.get("heading") for s in ir.get("sections", [])}
    for r in ("Methods", "Experiments"):
        if r not in have:
            w.append(f"methods_section: section '{r}' missing (flag explicitly)")
    params = ir.get("parameters", [])
    if not params:
        w.append("methods_section: no parameters[] table (写得全)")
    for p in params:
        pid = p.get("name", p.get("id", "?"))
        if p.get("value") is None:
            w.append(f"parameter {pid}: no value")
        if not p.get("source"):
            e.append(f"parameter {pid}: no source (写得准 — value must trace to material)")
        st = p.get("status", "reported")
        if st not in RECORD_STATUS:
            w.append(f"parameter {pid}: unknown status '{st}'")
        if st == "inferred":
            w.append(f"parameter {pid}: inferred (not reported) -> distinguish in text")
    if not ir.get("statistical_methods"):
        w.append("methods_section: statistical_methods not stated")
    return e, w


def _val_latex(ir):
    e, w = [], []
    lx = ir.get("latex", {})
    if not lx.get("documentclass"):
        e.append("latex requires latex.documentclass")
    if not lx.get("sections"):
        e.append("latex requires latex.sections[]")
    keys = [b.get("key") for b in ir.get("bib_entries", []) if b.get("key")]
    if len(keys) != len(set(keys)):
        e.append("bib_entries: duplicate keys")
    return e, w


# ── build dispatch ──────────────────────────────────────────────────────────

def build(ir: dict, case: dict, out_dir: Path):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    kind = ir.get("kind")
    if kind == "polish":
        return _build_polish(ir, out_dir)
    if kind == "reference_manage":
        return _build_refs(ir, out_dir)
    if kind == "latex":
        return _build_latex(ir, out_dir)
    return _build_manuscript(ir, out_dir)  # intro_related / methods_section


def _art(path, fmt, role, name=None):
    return {"name": name or Path(path).name, "path": str(path), "format": fmt, "role": role}


# ── polish ──────────────────────────────────────────────────────────────────

def _build_polish(ir, out_dir):
    segs = ir.get("segments", [])
    issues = []
    rows = []
    for s in segs:
        sid = s.get("id", "?")
        orig, rev = s.get("original", ""), s.get("revised", "")
        no, nr = set(_nums(orig)), set(_nums(rev))
        for lost in sorted(no - nr):
            issues.append({"segment": sid, "number": lost, "issue": "number dropped in revision (没改坏)"})
        for add in sorted(nr - no):
            issues.append({"segment": sid, "number": add, "issue": "number added; verify against source"})
        co, cr = _cite_markers(orig), _cite_markers(rev)
        for lost in sorted(co - cr):
            issues.append({"segment": sid, "citation": lost, "issue": "citation marker dropped (没改坏)"})
        rows.append({"id": sid, "change_type": s.get("change_type", "minimal_edit"),
                     "original": orig, "revised": rev, "reason": s.get("reason", ""),
                     "meaning_preserved": s.get("meaning_preserved", True),
                     "source": s.get("source"), "locator": s.get("locator")})
    # number consistency over the assembled revised text vs declared source numbers
    tmp = {"sections": [{"id": "polished", "paragraphs": [{"text": _strip_cites(s.get("revised", ""))} for s in segs]}],
           "numbers": ir.get("numbers", [])}
    num_issues = writekit.check_number_consistency(tmp)

    polished_text = "\n\n".join(s.get("revised", "") for s in segs)
    md = ["# " + ir.get("title", "Polished manuscript"), "", "## Polished text", "", polished_text, "",
          "## Segment-level changes (original <-> revised)", ""]
    for r in rows:
        md += [f"### {r['id']} — {r['change_type']}", "",
               f"- Original: {r['original']}", f"- Revised: {r['revised']}",
               f"- Reason: {r['reason']}", f"- Meaning preserved: {r['meaning_preserved']}",
               f"- Source: {r['source']} {r['locator'] or ''}", ""]
    (out_dir / "polished.md").write_text("\n".join(md), encoding="utf-8")
    w4kit.write_json(out_dir / "track_changes.json", {"segments": rows, "issues": issues})

    doc_ir = {"title": ir.get("title", "Polished manuscript"),
              "sections": [{"heading": "Polished text", "level": 1,
                            "paragraphs": [{"text": s.get("revised", "")} for s in segs]},
                           {"heading": "Change log", "level": 1,
                            "paragraphs": [{"text": f"[{r['id']}] ({r['change_type']}) {r['reason']}\n"
                                                    f"ORIG: {r['original']}\nREV: {r['revised']}"} for r in rows]}]}
    paths = docxkit.write_manuscript(doc_ir, out_dir)
    outputs = [_art(out_dir / "polished.md", "md", "md"),
               _art(paths["docx"], "docx", "docx", "polished.docx"),
               _art(out_dir / "track_changes.json", "json", "json")]
    prov = {"segment_map": {r["id"]: {"source": r["source"], "locator": r["locator"],
                                      "change_type": r["change_type"]} for r in rows}}
    extra = {"status": "success", "checks": {"preservation_issues": issues, "number_issues": num_issues},
             "provenance": prov, "result_extra": {"n_segments": len(rows), "n_preservation_issues": len(issues)}}
    return outputs, extra


# ── reference_manage ────────────────────────────────────────────────────────

def _fmt_ref(style, n, r):
    a = r.get("authors", "")
    y = r.get("year", "")
    t = r.get("title", "")
    j = r.get("journal", "")
    vol = r.get("volume", "")
    iss = r.get("issue", "")
    pp = r.get("pages", "")
    doi = w4kit.normalize_doi(r.get("doi")) or ""
    if style.startswith("gb"):
        s = f"[{n}] {a}. {t}[J]. {j}, {y}"
        if vol:
            s += f", {vol}"
            if iss:
                s += f"({iss})"
        if pp:
            s += f": {pp}"
        s += "."
        if doi:
            s += f" DOI: {doi}."
        return s
    if style == "apa":
        s = f"{a} ({y}). {t}. {j}"
        if vol:
            s += f", {vol}"
            if iss:
                s += f"({iss})"
        if pp:
            s += f", {pp}"
        s += "."
        if doi:
            s += f" https://doi.org/{doi}"
        return s
    # IEEE
    s = f"[{n}] {a}, \"{t},\" {j}"
    if vol:
        s += f", vol. {vol}"
    if iss:
        s += f", no. {iss}"
    if pp:
        s += f", pp. {pp}"
    if y:
        s += f", {y}"
    s += "."
    if doi:
        s += f" doi: {doi}."
    return s


def _bib_entry(r):
    key = r.get("key") or r.get("id", "ref")
    fields = []
    for k in ("author", "title", "journal", "year", "volume", "number", "pages", "doi"):
        src = "authors" if k == "author" else ("issue" if k == "number" else k)
        v = r.get(src)
        if k == "doi":
            v = w4kit.normalize_doi(v)
        if v:
            fields.append(f"  {k} = {{{v}}}")
    return "@article{" + key + ",\n" + ",\n".join(fields) + "\n}"


def _build_refs(ir, out_dir):
    style = str(ir.get("target_style", "")).lower().strip()
    refs = ir.get("references", [])
    dedup = w4kit.dedup_records(refs)
    by_id = {r.get("id"): r for r in refs}
    # representative per cluster + normalized fields
    clusters = []
    for c in dedup["clusters"]:
        rep = dict(c["records"][0])
        rep["doi"] = w4kit.normalize_doi(rep.get("doi"))
        rep["title_norm"] = w4kit.normalize_title(rep.get("title"))
        clusters.append({"cluster_id": c["cluster_id"], "members": c["members"],
                         "match": c["match"], "conflicts": c["conflicts"], "rep": rep})
    formatted = [_fmt_ref(style, i, c["rep"]) for i, c in enumerate(clusters, 1)]
    (out_dir / "references.md").write_text(
        "# References (" + ir.get("target_style", "") + ")\n\n" + "\n\n".join(formatted) + "\n", encoding="utf-8")
    (out_dir / "references.bib").write_text(
        "\n\n".join(_bib_entry(c["rep"]) for c in clusters) + "\n", encoding="utf-8")

    # in-text <-> list consistency
    rid_to_cluster = {}
    for c in clusters:
        for m in c["members"]:
            rid_to_cluster[m] = c["cluster_id"]
    cited = set()
    cmap = []
    missing = []
    for ct in ir.get("in_text_citations", []):
        rid = ct.get("ref_id")
        cl = rid_to_cluster.get(rid)
        if cl is None:
            missing.append({"in_text": ct.get("id"), "ref_id": rid, "issue": "no matching reference"})
        else:
            cited.add(cl)
        cmap.append({"id": ct.get("id"), "marker": ct.get("marker"), "ref_id": rid,
                     "cluster_id": cl, "claim_text": ct.get("claim_text"),
                     "source": ct.get("source"), "locator": ct.get("locator")})
    unused = [c["cluster_id"] for c in clusters if c["cluster_id"] not in cited]
    consistency = {"n_references_input": len(refs), "n_unique": len(clusters),
                   "n_duplicates_merged": dedup["n_duplicates_removed"],
                   "missing_in_text": missing, "uncited_references": unused,
                   "conflicts": [c["conflicts"] for c in clusters if c["conflicts"]]}
    w4kit.write_json(out_dir / "citation_map.json", {"in_text": cmap, "clusters": [
        {k: c[k] for k in ("cluster_id", "members", "match", "conflicts")} for c in clusters]})
    w4kit.write_json(out_dir / "dedup_report.json", dedup)
    w4kit.write_json(out_dir / "consistency.json", consistency)

    doc_ir = {"title": "References (" + ir.get("target_style", "") + ")",
              "sections": [{"heading": "Reference list", "level": 1,
                            "paragraphs": [{"text": f} for f in formatted]}]}
    paths = docxkit.write_manuscript(doc_ir, out_dir)
    outputs = [_art(out_dir / "references.md", "md", "md"),
               _art(out_dir / "references.bib", "bib", "bib"),
               _art(paths["docx"], "docx", "docx", "references.docx"),
               _art(out_dir / "citation_map.json", "json", "json"),
               _art(out_dir / "dedup_report.json", "json", "json"),
               _art(out_dir / "consistency.json", "json", "json")]
    prov = {"reference_map": {c["cluster_id"]: {"members": c["members"], "source": c["rep"].get("source"),
                                                "doi": c["rep"].get("doi")} for c in clusters}}
    status = "success" if not missing else "partial"
    extra = {"status": status, "checks": consistency, "provenance": prov,
             "result_extra": {"target_style": ir.get("target_style"), "n_unique": len(clusters),
                              "n_duplicates_merged": dedup["n_duplicates_removed"],
                              "n_missing_in_text": len(missing), "n_uncited": len(unused)}}
    if missing:
        ir.setdefault("uncertainty", []).append({"item": "in_text_citations", "reason": "some markers have no matching reference",
                                                 "impact": "citation list incomplete", "handling": "flagged missing; human_confirm"})
    return outputs, extra


# ── intro_related / methods_section (manuscript) ────────────────────────────

def _build_manuscript(ir, out_dir):
    paths = docxkit.write_manuscript(ir, out_dir)
    outputs = [_art(paths["md"], "md", "md", "manuscript.md"),
               _art(paths["docx"], "docx", "docx", "manuscript.docx")]
    # number-consistency over paragraph text with citation markers stripped (their
    # key digits are not data numbers); still uses writekit.check_number_consistency.
    cleaned = {"numbers": ir.get("numbers", []),
               "sections": [{"id": s.get("id"),
                             "paragraphs": [{"text": _strip_cites(p.get("text", ""))}
                                            for p in s.get("paragraphs", [])]}
                            for s in ir.get("sections", [])]}
    num_issues = writekit.check_number_consistency(cleaned)
    checks = {"number_issues": num_issues}
    prov = {}
    result_extra = {}
    if ir.get("kind") == "methods_section":
        params = ir.get("parameters", [])
        if params:
            with open(out_dir / "parameters.csv", "w", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["name", "value", "unit", "target", "status", "source", "locator"])
                for p in params:
                    w.writerow([p.get("name", ""), p.get("value", ""), p.get("unit", ""),
                                p.get("target", ""), p.get("status", "reported"),
                                p.get("source", ""), p.get("locator", "")])
            outputs.append(_art(out_dir / "parameters.csv", "csv", "csv"))
            prov["parameter_map"] = {p.get("name", p.get("id")): {"source": p.get("source"),
                                     "locator": p.get("locator"), "status": p.get("status", "reported")} for p in params}
            result_extra["n_parameters"] = len(params)
            result_extra["n_inferred"] = sum(1 for p in params if p.get("status") == "inferred")
            result_extra["n_not_reported"] = sum(1 for p in params if p.get("status") == "not_reported")
        repro = ir.get("reproducibility", {})
        if repro:
            lines = ["# Reproducibility checklist", ""]
            for k in ("code_version", "environment", "seed", "commands", "data_access"):
                v = repro.get(k)
                lines.append(f"- {k}: {v if v else 'not_reported (human_confirm)'}")
            (out_dir / "reproducibility.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
            outputs.append(_art(out_dir / "reproducibility.md", "md", "md"))
    if ir.get("kind") == "intro_related":
        gap = ir.get("research_gap", {})
        prov["research_gap"] = gap
        prov["contributions"] = ir.get("contributions", [])
        result_extra["n_contributions"] = len(ir.get("contributions", []))
    extra = {"status": "success", "checks": checks, "provenance": prov, "result_extra": result_extra}
    return outputs, extra


# ── latex ───────────────────────────────────────────────────────────────────

def _latex_source(ir):
    lx = ir.get("latex", {})
    dc = lx.get("documentclass", "article")
    opts = lx.get("options", "")
    lines = [f"\\documentclass[{opts}]{{{dc}}}" if opts else f"\\documentclass{{{dc}}}"]
    for p in lx.get("packages", []):
        if isinstance(p, dict):
            po = p.get("options", "")
            lines.append(f"\\usepackage[{po}]{{{p['name']}}}" if po else f"\\usepackage{{{p['name']}}}")
        else:
            lines.append(f"\\usepackage{{{p}}}")
    lines += ["\\begin{document}"]
    if lx.get("title"):
        lines.append(f"\\title{{{lx['title']}}}")
    if lx.get("author"):
        lines.append(f"\\author{{{lx['author']}}}")
    if lx.get("title"):
        lines.append("\\maketitle")
    if lx.get("abstract"):
        lines += ["\\begin{abstract}", lx["abstract"], "\\end{abstract}"]
    cmd = {1: "section", 2: "subsection", 3: "subsubsection"}
    for s in lx.get("sections", []):
        lvl = int(s.get("level", 1))
        lines.append(f"\\{cmd.get(lvl, 'section')}{{{s.get('heading', '')}}}")
        if s.get("label"):
            lines.append(f"\\label{{{s['label']}}}")
        lines.append(s.get("body", ""))
    for f in lx.get("figures", []):
        lines += ["\\begin{figure}[htbp]", "\\centering",
                  f"\\includegraphics[width={f.get('width', '0.8')}\\linewidth]{{{f.get('path', '')}}}",
                  f"\\caption{{{f.get('caption', '')}}}", f"\\label{{{f.get('label', f.get('ref', 'fig'))}}}",
                  "\\end{figure}"]
    if ir.get("bib_entries"):
        style = lx.get("bib_style", "plain")
        lines += [f"\\bibliographystyle{{{style}}}", "\\bibliography{references}"]
    lines += ["\\end{document}", ""]
    return "\n".join(lines)


def _structure_check(tex, ir):
    issues = []
    # balanced braces (ignore escaped \{ \})
    cleaned = re.sub(r"\\[{}]", "", tex)
    cleaned = re.sub(r"(?m)(?<!\\)%.*$", "", cleaned)  # strip comments
    depth = 0
    for ch in cleaned:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                issues.append("unbalanced braces: extra '}'")
                break
    if depth > 0:
        issues.append(f"unbalanced braces: {depth} unclosed '{{'")
    # environment stack
    stack = []
    for m in re.finditer(r"\\(begin|end)\{([^}]+)\}", tex):
        kind, env = m.group(1), m.group(2)
        if kind == "begin":
            stack.append(env)
        else:
            if not stack:
                issues.append(f"\\end{{{env}}} without \\begin")
            elif stack[-1] != env:
                issues.append(f"environment mismatch: \\begin{{{stack[-1]}}} closed by \\end{{{env}}}")
                stack.pop()
            else:
                stack.pop()
    for env in stack:
        issues.append(f"unclosed environment \\begin{{{env}}}")
    if "\\begin{document}" not in tex:
        issues.append("missing \\begin{document}")
    # required sections
    have = {s.get("heading", "").lower() for s in ir.get("latex", {}).get("sections", [])}
    for r in ir.get("latex", {}).get("required_sections", []):
        if r.lower() not in have:
            issues.append(f"required section '{r}' missing")
    # cite keys vs bib
    bibkeys = {b.get("key") for b in ir.get("bib_entries", []) if b.get("key")}
    cited = set()
    for m in re.finditer(r"\\cite\{([^}]+)\}", tex):
        cited.update(k.strip() for k in m.group(1).split(","))
    for k in sorted(cited - bibkeys):
        issues.append(f"\\cite key '{k}' not in references.bib")
    # ref labels vs defined labels
    labels = set(re.findall(r"\\label\{([^}]+)\}", tex))
    refs = set(re.findall(r"\\(?:ref|eqref|autoref)\{([^}]+)\}", tex))
    for k in sorted(refs - labels):
        issues.append(f"\\ref label '{k}' not defined")
    return {"ok": not issues, "issues": issues, "n_cite_keys": len(cited),
            "n_bib_entries": len(bibkeys), "n_labels": len(labels)}


def _try_compile(tex_path, bib_path, ir, out_dir):
    compiler = None
    for c in ("latexmk", "pdflatex", "xelatex"):
        if shutil.which(c):
            compiler = c
            break
    report = {"compiled": False, "compiler": compiler, "rounds": 0, "errors": [], "log_tail": ""}
    if not compiler:
        report["reason"] = "no local LaTeX compiler; structure validated only. Runtime latex-compiler required for true compile."
        w4kit.write_json(out_dir / "compile_report.json", report)
        return report
    work = Path(tempfile.mkdtemp(prefix="arena_tex_"))
    try:
        shutil.copy(tex_path, work / "main.tex")
        if bib_path.exists():
            shutil.copy(bib_path, work / "references.bib")
        for f in ir.get("latex", {}).get("figures", []):
            src = Path(f.get("path", ""))
            if src.exists():
                shutil.copy(src, work / src.name)
        cmd = ([compiler, "-pdf", "-interaction=nonstopmode", "main.tex"] if compiler == "latexmk"
               else [compiler, "-interaction=nonstopmode", "main.tex"])
        rounds = 2 if ir.get("bib_entries") else 1
        log = ""
        for _ in range(rounds):
            proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=180)
            log = proc.stdout + proc.stderr
            report["rounds"] += 1
        report["compiled"] = (work / "main.pdf").exists()
        report["errors"] = [ln for ln in log.splitlines() if ln.startswith("!")][:20]
        report["log_tail"] = "\n".join(log.splitlines()[-25:])
        if report["compiled"]:
            shutil.copy(work / "main.pdf", out_dir / "main.pdf")
    except Exception as e:  # noqa: BLE001
        report["reason"] = f"compile attempt failed: {e}"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    w4kit.write_json(out_dir / "compile_report.json", report)
    return report


def _build_latex(ir, out_dir):
    tex = _latex_source(ir)
    tex_path = out_dir / "main.tex"
    tex_path.write_text(tex, encoding="utf-8")
    bib_path = out_dir / "references.bib"
    bib_path.write_text("\n\n".join(_bib_entry(b) for b in ir.get("bib_entries", [])) + "\n", encoding="utf-8")
    struct = _structure_check(tex, ir)
    w4kit.write_json(out_dir / "structure_check.json", struct)
    comp = _try_compile(tex_path, bib_path, ir, out_dir)
    outputs = [_art(tex_path, "tex", "tex"), _art(bib_path, "bib", "bib"),
               _art(out_dir / "structure_check.json", "json", "json"),
               _art(out_dir / "compile_report.json", "json", "json")]
    if comp.get("compiled") and (out_dir / "main.pdf").exists():
        outputs.append(_art(out_dir / "main.pdf", "pdf", "pdf"))
    if not struct["ok"]:
        status = "partial"
    elif comp.get("compiled"):
        status = "success"
    elif not comp.get("compiler"):
        status = "success"  # structure valid; compile honestly deferred to runtime
        ir.setdefault("uncertainty", []).append({"item": "latex_compile",
            "reason": "no local LaTeX compiler", "impact": "compile not run locally; structure validated",
            "handling": "run runtime latex-compiler (latexmk -pdf) to confirm; human_confirm"})
    else:
        status = "partial"
        ir.setdefault("uncertainty", []).append({"item": "latex_compile", "reason": "compile failed",
            "impact": "PDF not produced", "handling": "see compile_report.json errors; fix and re-run"})
    prov = {"latex_map": {"sections": [s.get("heading") for s in ir.get("latex", {}).get("sections", [])],
                          "bib_keys": [b.get("key") for b in ir.get("bib_entries", [])]}}
    extra = {"status": status, "checks": {"structure": struct, "compile": comp}, "provenance": prov,
             "result_extra": {"structure_ok": struct["ok"], "compiled": comp.get("compiled", False),
                              "compiler": comp.get("compiler")}}
    return outputs, extra