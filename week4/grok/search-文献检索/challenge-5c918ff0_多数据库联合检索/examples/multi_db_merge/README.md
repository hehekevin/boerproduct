# SYNTHETIC EXAMPLE — multi_db_merge

**SYNTHETIC interface demo — NOT a formal answer.** Labelled EXAMPLE only; not an
official case and not a prepared answer. `input/` holds tiny fake materials;
`ir.json` was filled from those actual example files and is accepted by
`search_engine.validate_ir`. Re-run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/multi_db_merge/ir.json --input examples/multi_db_merge/input --out /tmp/demo-multi_db_merge
```

Expected: exit 0, `validation.json` with no errors, main artifact
`merged_records.json` + `report.md` + `records.csv` + `provenance.json` + `result.json`.
Expected status: success (clean validation; conflicts are retained data, not unresolved gaps).
Real cases are supplied only at evaluation time under /input.
