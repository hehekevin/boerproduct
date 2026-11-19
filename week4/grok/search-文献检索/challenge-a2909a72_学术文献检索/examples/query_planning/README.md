# SYNTHETIC EXAMPLE — query_planning

**SYNTHETIC interface demo — NOT a formal answer.** Labelled EXAMPLE only; not an
official case and not a prepared answer. `input/` holds tiny fake materials;
`ir.json` was filled from those actual example files and is accepted by
`search_engine.validate_ir`. Re-run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/query_planning/ir.json --input examples/query_planning/input --out /tmp/demo-query_planning
```

Expected: exit 0, `validation.json` with no errors, main artifact
`candidate_set.json` + `report.md` + `records.csv` + `provenance.json` + `result.json`.
Expected status: success (clean validation; dedup merges R1/R3).
Real cases are supplied only at evaluation time under /input.
