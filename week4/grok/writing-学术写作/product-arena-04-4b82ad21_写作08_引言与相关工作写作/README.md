# arena-intro-related — 写作08 引言与相关工作写作 (kind=intro_related)

Source-bound Introduction + Related Work writing skill for the Bohrium weekly contest
(play.bohrium.com, contest=bohr-product, period 4, grok agent).

## What it does
The Agent reads the ACTUAL provided literature under `/input` and fills a writing IR
(claims+evidence locators, citations[], grouped sections[], research_gap derived from
cited limitations, contributions bound to evidence). The deterministic stdlib engine:
- validates claim-citation binding, gap derivation, contribution binding, required
  sections, terminology and number-consistency (writekit + arena intro rules),
- builds editable manuscript.md + manuscript.docx (Introduction / Related Work /
  Research Gap / Contributions + References),
- writes provenance.json (claim_map + research_gap + contributions) + honest result.json.

NOT pre-baked answers: the engine computes from the IR filled from real material.
Unsupported claims are flagged, never fabricated; proposed vs result-backed
contributions are distinguished.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
Exit 0 = validation ok; exit 2 = validation errors (honest partial result still written).

## Dependencies
Python 3.10+ standard library only (docx via stdlib zipfile OOXML). See requirements.txt.

## Files
SKILL.md; assemble.py; arena_write_engine.py (shared arena engine); writekit.py;
docxkit.py; w4kit.py; rules/rules_intro_related.md; docs/WORKFLOW.md + ERROR_HANDLING.md;
examples/intro_related/ (SYNTHETIC demo).

## Scope & limits
IN: grounded intro+related writing + editable delivery. OUT: polishing, reference
styling, methods, LaTeX, PPT. Scientific grouping/gap judgment is the Agent's; the
engine checks structural binding and consistency. Generated docx lives in /app/output
at runtime, never inside this package.

## Self-check
Run examples/intro_related/README.md; confirm exit 0, validation ok, number_issues
empty, gap derived_from registered citations, result.json honest. Hard limits: ≤50
UTF-8 text files, ≤500KB each, ≤2MB total, no binaries/__pycache__/symlinks.