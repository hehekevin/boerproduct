# arena-latex — 写作13 LaTeX写作与编译 (kind=latex)

Source-bound LaTeX writing & compile skill for the Bohrium weekly contest
(play.bohrium.com, contest=bohr-product, period 4, grok agent).

## What it does
The Agent reads the ACTUAL content/template under `/input` and fills a LaTeX IR
(documentclass, packages, sections, figures, bib_entries, claims+evidence). The
deterministic stdlib engine:
- emits compilable `main.tex` + `references.bib`,
- validates structure: balanced braces, matched \begin/\end, required sections,
  \cite keys present in bib, \ref labels defined,
- attempts a real compile ONLY if a TeX compiler exists (latexmk/pdflatex/xelatex;
  runtime latex-compiler), 2 rounds with bib; otherwise honestly defers compile,
- writes structure_check.json + compile_report.json (+ main.pdf if compiled),
  provenance.json (claim_map + latex_map) and an honest result.json.

NOT pre-baked answers: the engine computes from the IR filled from real material.
Locally (no TeX) it is explicit that compile is not run; it never claims compile success
without a produced PDF and never delivers a PDF/screenshot as the source.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
Exit 0 = validation ok; exit 2 = validation errors (honest partial result still written).

## Dependencies
Python 3.10+ standard library only. LaTeX compiler OPTIONAL (present at runtime, absent
locally → honest structure-only fallback). See requirements.txt.

## Files
SKILL.md; assemble.py; arena_write_engine.py (shared arena engine; LaTeX emit + structure
check + compile); writekit.py; w4kit.py; docxkit.py; rules/rules_latex.md;
docs/WORKFLOW.md + ERROR_HANDLING.md; examples/latex/ (SYNTHETIC demo).

## Scope & limits
IN: .tex/.bib generation + structure check + honest compile. OUT: prose polishing,
reference styling, intro/methods prose, PPT. Generated main.pdf (when compiled) lives in
/app/output at runtime, never inside this package.

## Self-check
Run examples/latex/README.md; confirm exit 0, structure ok, compile honestly deferred,
result.json honest. Hard limits: ≤50 UTF-8 text files, ≤500KB each, ≤2MB total, no
binaries/__pycache__/symlinks.