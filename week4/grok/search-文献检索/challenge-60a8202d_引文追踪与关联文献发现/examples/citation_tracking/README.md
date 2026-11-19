# SYNTHETIC EXAMPLE — citation_tracking

**SYNTHETIC interface demo — NOT a formal answer.** Labelled EXAMPLE only; not an
official case and not a prepared answer. `input/` holds tiny fake materials;
`ir.json` was filled from those actual example files and is accepted by
`search_engine.validate_ir`. Re-run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/citation_tracking/ir.json --input examples/citation_tracking/input --out /tmp/demo-citation_tracking
```

Expected: exit 0, `validation.json` with no errors, main artifact
`citation_expansion.json` + `report.md` + `records.csv` + `provenance.json` + `result.json`.
Expected status: partial (R5 stub flagged human_confirm) — honest outcome.
Real cases are supplied only at evaluation time under /input.
