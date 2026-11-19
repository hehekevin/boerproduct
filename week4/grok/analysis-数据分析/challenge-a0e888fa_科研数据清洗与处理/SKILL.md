---
name: analysis-data-cleaning
description: Clean real research data tables with field-level rules from the data dictionary - sentinel/missing classification (never impute source values), primary-key dedup with kept/removed provenance, reversible unit conversion, distribution-based outlier flags, and a quality report whose numbers are self-checked against the cleaned table. Use when the task is 科研数据清洗与处理 / cleaning missing values, duplicates, outliers, units or formats in organizer-provided CSV/TSV/JSON tables.
---

# Research data cleaning & processing (科研数据清洗与处理)

A source-bound Skill for the Bohrium weekly contest (analysis track, challenge-a0e888fa).
The agent reads the ACTUAL organizer material under /input (data dictionary, field
semantics, per-metric unit/QC rules, cleaning workorder, the fault-injected table),
fills a structured IR, and a deterministic stdlib engine applies the rules, recomputes
the quality report FROM the cleaned table, and emits editable artifacts + provenance +
an honest result.json. No pre-baked answers; every changed cell traces to a row locator.

## Focus (rubric points)
- 实际效果: all five treatment classes (missing / outlier / duplicate / format-unit /
  quality report) actually executed on the real table; report numbers == result table.
- 创新增益: dictionary-driven field-level strategy, real-primary-key dedup with
  normalization, REVERSIBLE unit conversion (inverse expression logged), and an
  automatic report↔table consistency self-check.
- 可靠体验: empty tables, all-missing columns, unknown units, key conflicts, unreadable
  files are identified and honestly reported, never silently patched.
- Organizer revision2 constraint: the material is published aggregate transcriptions
  with injected storage/encoding faults. DO NOT infer population statistics and DO NOT
  impute missing/invalid source values — flag them, preserve originals, log the rule.

## Inputs (runtime)
- /input/case.json — copy case_id; preserve every output_contract key.
- /input/task.md — the concrete cleaning workorder for this case.
- Actual material: data table(s) (csv/tsv/json), data dictionary, unit/QC rules.
Read and register the real files; trust file content over filename/domain labels.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] + datasets[].
2. Read the dictionary FIRST: field semantics, sentinel codes, true-zero meaning,
   primary keys, target units, QC bounds. Fill the IR per rules/rules_data_cleaning.md.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir cleaning_ir.json --input /input --out /app/output`
   → validate_ir → apply operations in order → cleaned_<dataset>.csv + original snapshot
   + cleaning_log.json (changes + quality report + consistency check) + provenance.json
   + report.md → result.json.
4. Honest status: success only when every op done, consistency OK, no gaps; partial when
   ops failed, sentinels/units ambiguous, outliers need human review, or files unreadable.

## IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto from /input/case.json>
kind: "data_cleaning"
sources: [{id, path, description?}]          # every actual file used
datasets: [{dataset_id, source_id, path, columns?, sha256?}]
cleaning: {operations: [{
  op_id, type, dataset_id, column?/columns?, rule, reason?, evidence?,
  params: {...}   # per type:
  # flag_missing: {sentinel_map: {"-999":"storage_fault_sentinel","":"missing_entry",
  #               "ND":"not_detected","<LOD":"below_detection_limit"}, blank_is_missing}
  # dedup:        {key_columns: [...real primary key...], keep: first|last}
  # unit_convert: {unit_column?, from_unit, to_unit, factor_expr}  # safe_eval, e.g. "1000"
  # outlier_flag: {method: iqr|zscore|bounds, k?/threshold?/min?/max?, action: flag|remove}
  # type_cast:    {to: float|int|str}
  # rename_column:{mapping: {old: new}}
  # drop_rows:    {where: "<safe_eval expression over numeric columns>"}  # needs reason
}]}
uncertainty: [{item, reason, impact?, handling: human_confirm}]
provenance: {pipeline, changes?}
```
Evidence locator = {source_id, paragraph_id?, quote?, field?}. Every op should cite the
dictionary/workorder passage that authorizes it. True zero ("0") is NEVER treated as missing.

## Domain rules
See rules/rules_data_cleaning.md (sentinel taxonomy, no-imputation rule, dedup key
selection, reversible conversion, outlier judgment, report consistency, replayability).

## Scripts & dependencies
assemble.py (CLI), analysis_engine.py (deterministic cleaning + quality report +
consistency self-check + provenance), w4kit.py (case load / safe_eval / source check /
result.json). Python 3.10+ standard library only. See requirements.txt.

## Outputs (/app/output)
cleaned_<dataset>.csv (editable), original_<dataset>.csv (untouched snapshot),
cleaning_log.json (per-change row locator + original + new + rule + evidence; quality
report per column: missing rate, outliers, conversions, duplicate groups; consistency
check), provenance.json, report.md, validation.json, result.json (preserves
output_contract + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Unreadable/empty table → dataset status recorded, ops on it failed with reason;
unknown unit → op skipped/failed, never guessed factor; ambiguous sentinel → flag +
human_confirm; dedup key conflict → kept/removed both logged with the deciding rule;
outlier → flag by default (remove only with explicit reason); report number mismatch →
consistency_check.ok=false and status partial. Never overwrite the original file.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/data_cleaning/`: input/ (dictionary + fault-injected table) + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/data_cleaning/ir.json --input examples/data_cleaning/input --out w4/.tmp_analysis/challenge-a0e888fa`
The example deliberately includes a spike outlier and a true-zero below the IQR fence
to demonstrate honest partial status + human_confirm. Real cases arrive only at evaluation.

## Self-check
- [ ] dictionary read first; every op cites a rule + evidence locator
- [ ] sentinels classified (not-detected / below-LOD / missing / fault); true 0 preserved
- [ ] NO imputation of missing/invalid source values (organizer revision2)
- [ ] dedup on real primary key with normalization; removed rows fully logged
- [ ] unit conversions reversible (factor + inverse_expr); original snapshot kept
- [ ] outliers flagged with diagnostic bounds + reason; removals justified
- [ ] quality report numbers recomputed from cleaned table (consistency_check.ok)
- [ ] result.json honest (status/sources/uncertainty/change_log); output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt at package root: line 1 = public GitHub tree URL, line 2 = SKILL.md.
Published under week4/grok in github.com/hehekevin/boerproduct; opens without login.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared answers or
formal test outputs. Evaluator installs the Skill under /skills/weekly-skill and runs
the official DeepSeek Harness on each fixed original case (/input/case.json + task.md
→ /app/output/result.json preserving output_contract + case_id). Budget: 64 requests /
900 s; save honest partial deliverables early. Resources ≤50 UTF-8 text files, ≤500KB
each, ≤2MB total, no binaries/symlinks/__pycache__.