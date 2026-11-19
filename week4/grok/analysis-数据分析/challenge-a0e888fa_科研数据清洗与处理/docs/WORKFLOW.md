# Workflow — analysis-data-cleaning

Runtime: input /input (case.json + task.md + material), work /app/work, output /app/output.

1. **Inventory.** `python -c "import w4kit; print(w4kit.list_materials('/input'))"`.
   Read case.json (case_id, output_contract) and task.md (the cleaning workorder).
2. **Read material.** Open the data dictionary, unit/QC rules and the actual table.
   Note sentinel codes, true-zero semantics, primary key, target units, bounds, encoding.
   Peek at real rows (head) — never assume content from filenames.
3. **Fill IR** (cleaning_ir.json) per rules/rules_data_cleaning.md and the SKILL.md schema:
   - sources[]: every actual file used, with real paths.
   - datasets[]: dataset_id + source_id + path (+ columns from the real header).
   - cleaning.operations[]: ordered ops (flag_missing → dedup → unit_convert →
     outlier_flag → type_cast/rename as needed). Each op: rule + reason + evidence
     locator citing the dictionary/workorder.
   - uncertainty[]: ambiguous sentinels/units, spikes needing domain review, conflicts.
4. **Run the engine.**
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir cleaning_ir.json --input /input --out /app/output`
   The engine validates the IR, loads the real files (sha256 recorded), applies ops,
   recomputes the quality report from the cleaned table, runs the consistency self-check,
   writes artifacts + provenance.json + report.md + result.json.
5. **Inspect outputs.** validation.json (errors/warnings), cleaning_log.json
   (consistency_check.ok must be true), report.md, result.json status.
6. **Iterate honestly.** If ops failed or consistency mismatched: fix the IR rule or the
   data reading, rerun. If material is genuinely missing/ambiguous: keep partial status,
   add uncertainty + human_confirm. Save partial deliverables early; never fabricate.

## Self-test (SYNTHETIC example)
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/data_cleaning/ir.json \
  --input examples/data_cleaning/input \
  --out w4/.tmp_analysis/challenge-a0e888fa
```
Expect exit 0, validation errors = [], status partial (the example intentionally contains
a spike + a true-zero below the IQR fence → human_confirm).