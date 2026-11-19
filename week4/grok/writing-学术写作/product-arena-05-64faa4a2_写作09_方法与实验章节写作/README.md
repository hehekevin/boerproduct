# arena-methods-section — 写作09 方法与实验章节写作 (kind=methods_section)

Source-bound, reproducible Methods/Experiments writing skill for the Bohrium weekly
contest (play.bohrium.com, contest=bohr-product, period 4, grok agent).

## What it does
The Agent reads the ACTUAL protocol/config/log/data under `/input` and fills a writing
IR (claims+evidence, sections[], parameters[] with value/unit/target/source/status,
equipment/reagents, statistical_methods, datasets, reproducibility). The deterministic
stdlib engine:
- validates parameter sourcing (no source = error), reported-vs-inferred status,
  required sections, statistical methods, terminology and number-consistency,
- builds editable manuscript.md + manuscript.docx + parameters.csv + reproducibility.md,
- writes provenance.json (claim_map + parameter_map) + honest result.json
  (n_parameters / n_inferred / n_not_reported).

NOT pre-baked answers: the engine computes from the IR filled from real material.
Absent parameters → not_reported + human_confirm, never invented for paragraph flow.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
Exit 0 = validation ok; exit 2 = validation errors (honest partial result still written).

## Dependencies
Python 3.10+ standard library only (docx via stdlib zipfile OOXML). See requirements.txt.

## Files
SKILL.md; assemble.py; arena_write_engine.py (shared arena engine); writekit.py;
docxkit.py; w4kit.py; rules/rules_methods_section.md; docs/WORKFLOW.md + ERROR_HANDLING.md;
examples/methods_section/ (SYNTHETIC demo).

## Scope & limits
IN: reproducible Methods/Experiments from protocol/data + editable delivery. OUT:
polishing, references, intro, LaTeX, PPT. Element extraction is the Agent's; the engine
checks sourcing/status/consistency. Generated docx/csv live in /app/output at runtime,
never inside this package.

## Self-check
Run examples/methods_section/README.md; confirm exit 0, validation ok, number_issues
empty, weight_decay not_reported flagged, result.json honest. Hard limits: ≤50 UTF-8
text files, ≤500KB each, ≤2MB total, no binaries/__pycache__/symlinks.