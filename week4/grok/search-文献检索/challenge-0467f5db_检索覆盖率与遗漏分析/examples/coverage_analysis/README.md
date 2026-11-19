# SYNTHETIC EXAMPLE — coverage_analysis

**SYNTHETIC interface demo — NOT a formal answer.** Labelled EXAMPLE only; not an
official case and not a prepared answer. `input/` holds tiny fake materials;
`ir.json` was filled from those actual example files and is accepted by
`search_engine.validate_ir`. Re-run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/coverage_analysis/ir.json --input examples/coverage_analysis/input --out /tmp/demo-coverage_analysis
```

Expected: exit 0, `validation.json` with no errors, main artifact
`coverage_analysis.json` + `report.md` + `records.csv` + `provenance.json` + `result.json`.
Expected status: success (all usable references hit; retracted item flagged unusable; SR1 zero-gain accounted honestly).
Real cases are supplied only at evaluation time under /input.
