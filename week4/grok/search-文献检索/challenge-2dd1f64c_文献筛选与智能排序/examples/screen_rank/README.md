# SYNTHETIC EXAMPLE — screen_rank

**SYNTHETIC interface demo — NOT a formal answer.** Labelled EXAMPLE only; not an
official case and not a prepared answer. `input/` holds tiny fake materials;
`ir.json` was filled from those actual example files and is accepted by
`search_engine.validate_ir`. Re-run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/screen_rank/ir.json --input examples/screen_rank/input --out /tmp/demo-screen_rank
```

Expected: exit 0, `validation.json` with no errors, main artifact
`candidate_set.json` + `report.md` + `records.csv` + `provenance.json` + `result.json`.
Expected status: partial (R4 ambiguous record flagged human_confirm) — honest outcome.
Real cases are supplied only at evaluation time under /input.
