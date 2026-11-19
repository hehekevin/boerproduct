# SYNTHETIC EXAMPLE — patent_search

**SYNTHETIC interface demo — NOT a formal answer.** Labelled EXAMPLE only; not an
official case and not a prepared answer. `input/` holds tiny fake materials;
`ir.json` was filled from those actual example files and is accepted by
`search_engine.validate_ir`. Re-run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/patent_search/ir.json --input examples/patent_search/input --out /tmp/demo-patent_search
```

Expected: exit 0, `validation.json` with no errors, main artifact
`patent_families.json` + `report.md` + `records.csv` + `provenance.json` + `result.json`.
Expected status: partial (legal status UNKNOWN + OCR boundary flagged human_confirm) — honest outcome.
Real cases are supplied only at evaluation time under /input.
