# Example — code_gen_exec (SYNTHETIC)

ALL files here are SYNTHETIC interface-demo data, NOT a formal contest case or answer.

## Contents
- input/case.json — example case_id + output_contract
- input/task.md — example code-generation spec (Chinese)
- input/dictionary.md — field meaning / units / missing caliber
- input/data.csv — 6-row cement/strength table (mean strength = 35.0)
- ir.json — agent-filled IR with REAL runnable Python code + verification checks

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/code_gen_exec/ir.json --input examples/code_gen_exec/input \
  --out w4/.tmp_analysis/challenge-9ec929fe
```

## Expected
- exit 0; validation errors = []; status success
- analysis_code.py written (editable artifact); executed isolated (python -I -B)
- execution_log.json: exit_code 0, stdout JSON, python version + platform, duration
- code_results.json: results {n:6, n_numeric:6, mean_strength:35.0}; verification 2/2 pass
  (c_mean expected 35.0; c_rows n_rows_d == 6); static_scan warnings = []
- result.json preserves every output_contract key + case_id