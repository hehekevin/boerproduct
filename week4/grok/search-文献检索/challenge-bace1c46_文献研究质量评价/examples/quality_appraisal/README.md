# SYNTHETIC EXAMPLE — quality_appraisal

**SYNTHETIC interface demo — NOT a formal answer.** Labelled EXAMPLE only; not an
official case and not a prepared answer. `input/` holds tiny fake materials;
`ir.json` was filled from those actual example files and is accepted by
`search_engine.validate_ir`. Re-run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/quality_appraisal/ir.json --input examples/quality_appraisal/input --out /tmp/demo-quality_appraisal
```

Expected: exit 0, `validation.json` with no errors, main artifact
`appraisal.json` + `report.md` + `records.csv` + `provenance.json` + `result.json`.
Expected status: partial (P2/D3 abstention flagged human_confirm) — honest outcome.
Real cases are supplied only at evaluation time under /input.
