# Example — data_cleaning (SYNTHETIC)

ALL files here are SYNTHETIC interface-demo data, NOT a formal contest case or answer.
Real cases are supplied by the organizer only at evaluation time.

## Contents
- input/case.json — example case_id + output_contract
- input/task.md — example cleaning workorder (Chinese)
- input/dictionary.md — example field semantics / sentinels / units / QC rules
- input/measurements.csv — 9-row fault-injected table (duplicate, -999 sentinel, blank,
  true zero, unit variant, spike)
- ir.json — agent-filled IR demonstrating the schema

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/data_cleaning/ir.json \
  --input examples/data_cleaning/input \
  --out w4/.tmp_analysis/challenge-a0e888fa
```

## Expected (demonstrates honest partial)
- exit 0; validation errors = []
- cleaned_meas.csv: 8 rows (duplicate removed), conc in ug/L, sentinels emptied
- original_meas.csv snapshot untouched; cleaning_log.json logs every change with row
  locator + original + new + rule + evidence; consistency_check.ok = true
- status = partial: the spike and the true-zero-below-fence are flagged human_confirm
- result.json preserves every output_contract key + case_id