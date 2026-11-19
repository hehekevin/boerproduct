# SYNTHETIC example — methods_stats_review (interface demo, NOT a formal answer)

All material here is fabricated for demonstration only and is clearly marked
SYNTHETIC. Real contest cases are supplied by the organizer at evaluation time.

## Contents
- input/case.json — demo case_id + output_contract
- input/task.md — demo task statement
- input/manuscript.md — tiny fake manuscript with reported statistics
- input/data.csv — 8-row dose/response table (the REAL recomputation input)
- ir.json — agent-style IR with findings + 4 stats_checks

## Run
```
PYTHONDONTWRITEBYTECODE=1 python ../../assemble.py --ir ir.json --input input --out /tmp/demo-methods
```

## Expected result
- exit 0, validation errors = [] (one benign warning: ST4 recompute-only)
- status = partial (ST4 not_recomputable: column biomarker_x absent)
- ST1 describe: mean 12.0 match, n 8 match, SD mismatch (reported 1.5 vs
  computed 1.309307) — a confirmed review result, not an engine failure
- ST2 linreg: slope 0.285714 / R2 0.285714 vs reported 0.29/0.29 → match
- ST3 expr: mean+1.96*sd/sqrt(n) = 13.039447 vs reported 13.04 → match
- 5 findings (2 major, 2 minor, 1 strength); 0 locator issues
- outputs: review.json, checklist.csv, report.md, provenance.json, result.json