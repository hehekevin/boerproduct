# SYNTHETIC example — citation_fact_check (interface demo, NOT a formal answer)

All material here is fabricated for demonstration only and is clearly marked
SYNTHETIC. Real contest cases are supplied by the organizer at evaluation time.

## Contents
- input/case.json — demo case_id + output_contract
- input/task.md — demo task statement
- input/manuscript.md — tiny fake manuscript with 4 cited claims
- input/ref1.md, input/ref2.md — fake provided reference texts
- ir.json — agent-style IR with claims/subclaims/references and locators

## Run
```
PYTHONDONTWRITEBYTECODE=1 python ../../assemble.py --ir ir.json --input input --out /tmp/demo-citation
```

## Expected result
- exit 0, validation errors = []
- status = partial (honest gaps deliberately included)
- C1: engine rollup overrides agent "partial" → insufficient (over-generalization
  subclaim C1b); C2: contradicts (side-effect claim vs safety study);
  C3: partial (year 2019 vs actual 2021); C4: insufficient (ref [3] unprovided)
- R1 metadata_mismatch (year), DOI URL prefix normalized away; R2 matched;
  R3 not_provided + human_confirm
- n_locator_issues = 0; outputs: review.json, checklist.csv, report.md,
  provenance.json, result.json