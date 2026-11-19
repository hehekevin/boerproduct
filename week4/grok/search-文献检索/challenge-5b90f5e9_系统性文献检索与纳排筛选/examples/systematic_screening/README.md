# SYNTHETIC EXAMPLE — systematic_screening

**SYNTHETIC interface demo — NOT a formal answer.** Labelled EXAMPLE only; not an
official case and not a prepared answer. `input/` holds tiny fake materials;
`ir.json` was filled from those actual example files and is accepted by
`search_engine.validate_ir`. Re-run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/systematic_screening/ir.json --input examples/systematic_screening/input --out /tmp/demo-systematic_screening
```

Expected: exit 0, `validation.json` with no errors, main artifact
`screening_audit.json` + `report.md` + `records.csv` + `provenance.json` + `result.json`.
Expected status: partial (R4 pending human decision after adjudication) — honest outcome.
Real cases are supplied only at evaluation time under /input.
