# SYNTHETIC EXAMPLE — question_driven

**SYNTHETIC interface demo — NOT a formal answer.** Labelled EXAMPLE only; not an
official case and not a prepared answer. `input/` holds tiny fake materials;
`ir.json` was filled from those actual example files and is accepted by
`search_engine.validate_ir`. Re-run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/question_driven/ir.json --input examples/question_driven/input --out /tmp/demo-question_driven
```

Expected: exit 0, `validation.json` with no errors, main artifact
`candidate_set.json` + `report.md` + `records.csv` + `provenance.json` + `result.json`.
Expected status: partial (SQ3 causal-evidence gap flagged human_confirm) — this is the honest outcome, not a failure.
Real cases are supplied only at evaluation time under /input.
