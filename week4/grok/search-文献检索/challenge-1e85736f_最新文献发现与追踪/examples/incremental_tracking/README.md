# SYNTHETIC EXAMPLE — incremental_tracking

**SYNTHETIC interface demo — NOT a formal answer.** Labelled EXAMPLE only; not an
official case and not a prepared answer. `input/` holds tiny fake materials;
`ir.json` was filled from those actual example files and is accepted by
`search_engine.validate_ir`. Re-run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/incremental_tracking/ir.json --input examples/incremental_tracking/input --out /tmp/demo-incremental_tracking
```

Expected: exit 0, `validation.json` with no errors, main artifact
`incremental_state.json` + `report.md` + `records.csv` + `provenance.json` + `result.json`.
Expected status: success (contiguous windows, clean validation; version update and retraction correctly classified).
Real cases are supplied only at evaluation time under /input.
