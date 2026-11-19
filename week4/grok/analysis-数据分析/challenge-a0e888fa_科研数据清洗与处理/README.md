# analysis-data-cleaning (challenge-a0e888fa)

Source-bound Skill for the Bohrium weekly contest ANALYSIS track — 科研数据清洗与处理.
Agent reads the actual organizer material under /input, fills an IR; a deterministic
stdlib engine applies field-level cleaning rules, recomputes the quality report from the
cleaned table, self-checks report↔table consistency, and writes editable artifacts +
provenance + honest result.json. Not pre-baked answers.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
See SKILL.md (workflow + IR schema), rules/rules_data_cleaning.md (domain rules),
docs/WORKFLOW.md and docs/ERROR_HANDLING.md.

## Files
- SKILL.md — skill entry (frontmatter + workflow + IR schema + self-check)
- assemble.py — CLI; analysis_engine.py — deterministic engine; w4kit.py — shared core
- rules/rules_data_cleaning.md — dictionary-first, no-imputation, reversible units, etc.
- examples/data_cleaning/ — SYNTHETIC interface demo (input/ + ir.json + README)

## Dependencies
Python 3.10+ standard library only (csv/json/math/hashlib/re/pathlib/sqlite3).
matplotlib is OPTIONAL and used only by the sibling viz kind for PNG previews; this
cleaning kind never requires it. See requirements.txt.

## Scope & limits
- Handles csv/tsv/json tables; five treatment classes: missing sentinels, duplicates,
  outliers, unit/format conversion, quality report.
- Does NOT impute missing/invalid source values (organizer revision2); flags + preserves.
- Does NOT do statistical modeling/hypothesis tests (sibling stats skill), publication
  figure styling, DB administration, or experiment design.
- Outlier removal and ambiguous sentinels/units require human_confirm; honest partial.

## Self-check
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/data_cleaning/ir.json --input examples/data_cleaning/input \
  --out w4/.tmp_analysis/challenge-a0e888fa
```
Expect exit 0, no validation errors, consistency_check.ok=true, status partial (example
intentionally includes a spike + true-zero below IQR fence). Delete any __pycache__.
Hard limits: ≤50 UTF-8 text files, ≤500KB each, ≤2MB total, no binaries/symlinks.