# arena-reference-manage — 写作04 参考文献与引用管理 (kind=reference_manage)

Source-bound reference & citation management skill for the Bohrium weekly contest
(play.bohrium.com, contest=bohr-product, period 4, grok agent).

## What it does
The Agent reads the ACTUAL manuscript + reference library under `/input` and fills an
IR (references[] + in_text_citations[] + target_style). The deterministic stdlib engine:
- normalizes DOI/title and deduplicates with explainable provenance + field conflicts
  (w4kit.dedup_records; every input record kept in exactly one cluster),
- formats the unique list to GB/T 7714 / APA / IEEE and exports BibTeX,
- checks in-text<->reference-list consistency (missing / uncited / duplicate flags),
- builds editable references.md + references.bib + references.docx + citation_map.json
  + dedup_report.json + consistency.json, and writes an honest result.json.

NOT pre-baked answers: the engine computes from the IR filled from real material.
Verification is against provided material (no live DOI lookup, no fabricated metadata).

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
Exit 0 = validation ok; exit 2 = validation errors (honest partial result still written).

## Dependencies
Python 3.10+ standard library only. No network, no third-party packages. See requirements.txt.

## Files
SKILL.md; assemble.py; arena_write_engine.py (shared arena engine); w4kit.py
(normalize/dedup/case/result); writekit.py; docxkit.py; rules/rules_reference_manage.md;
docs/WORKFLOW.md + ERROR_HANDLING.md; examples/reference_manage/ (SYNTHETIC demo).

## Scope & limits
IN: dedup + style conversion + consistency + editable delivery. OUT: prose polishing,
intro writing, LaTeX, PPT. Claim<->reference scientific match is Agent judgment; the
engine checks structural linkage and metadata, not scientific truth. Generated docx
lives in /app/output at runtime, never inside this package.

## Self-check
Run examples/reference_manage/README.md; confirm exit 0, dedup 4->3 (1 merged),
ref4 uncited flagged, result.json honest. Hard limits: ≤50 UTF-8 text files, ≤500KB
each, ≤2MB total, no binaries/__pycache__/symlinks.