# Example — multi_step_analysis (SYNTHETIC)

ALL files here are SYNTHETIC interface-demo data, NOT a formal contest case or answer.

## Contents
- input/case.json — example case_id + output_contract
- input/task.md — example end-to-end request (Chinese)
- input/dictionary.md — fields / units / primary key
- input/measurements.csv — 7-row table with one duplicate (group+x)
- ir.json — agent-filled IR: load → clean → stats → viz → interpret

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/multi_step_analysis/ir.json --input examples/multi_step_analysis/input \
  --out w4/.tmp_analysis/agent-6aefb2fd
```

## Expected
- exit 0; validation errors = []; status success
- pipeline.json: 5 steps done; clean removes 1 row (7→6); stats metrics desc_val.mean=17.0,
  cmp.cohens_d=-5.0; interpret backfill_check both pass
- per-step artifacts: step_s2_clean_cleaned_m.csv + cleaning_log.json, step_s3_stats_stats_results.json,
  step_s4_viz_chart_scatter_x_val.svg (+ optional PNG), provenance.json, report.md
- downstream stats/viz consume the CLEANED 6-row context
- result.json preserves every output_contract key + case_id