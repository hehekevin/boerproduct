# SYNTHETIC EXAMPLE — cross_language

**SYNTHETIC interface demo — NOT a formal answer.** Labelled EXAMPLE only; not an
official case and not a prepared answer. `input/` holds tiny fake materials;
`ir.json` was filled from those actual example files and is accepted by
`search_engine.validate_ir`. Re-run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/cross_language/ir.json --input examples/cross_language/input --out /tmp/demo-cross_language
```

Expected: exit 0, `validation.json` with no errors, main artifact
`works_views.json` + `report.md` + `records.csv` + `provenance.json` + `result.json`.
Expected status: success (clean validation; exact duplicate flagged as data, not an unresolved gap).
Real cases are supplied only at evaluation time under /input.
