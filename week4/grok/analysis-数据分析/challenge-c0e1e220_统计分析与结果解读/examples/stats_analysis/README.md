# Example — stats_analysis (SYNTHETIC)

ALL files here are SYNTHETIC interface-demo data, NOT a formal contest case or answer.

## Contents
- input/case.json — example case_id + output_contract
- input/task.md — example analysis question (Chinese)
- input/dictionary.md — field meaning / units / design
- input/groups.csv — 12-row two-group table (A/B × 6 ages)
- ir.json — agent-filled IR (describe + compare_groups + correlation + regression)

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/stats_analysis/ir.json --input examples/stats_analysis/input \
  --out w4/.tmp_analysis/challenge-c0e1e220
```

## Expected
- exit 0; validation errors = []; status success
- stats_results.json: describe (n/mean/sd/quartiles/skew + mean CI), Welch t + Cohen's d +
  mean-diff CI + variance-ratio F, Pearson r + Fisher CI, OLS slope/R² + slope CI
- every analysis carries evidence {source_id, dataset_id, column, n_rows_used} + assumptions
  + auto_summary + agent interpretation
- result.json preserves every output_contract key + case_id