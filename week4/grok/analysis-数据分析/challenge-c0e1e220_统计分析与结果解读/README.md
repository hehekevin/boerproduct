# analysis-stats-analysis (challenge-c0e1e220)

Source-bound Skill for the Bohrium weekly contest ANALYSIS track — 统计分析与结果解读.
Agent reads the actual organizer data + dictionary under /input, fills an IR; a
deterministic stdlib engine recomputes descriptive stats, group comparisons (Welch /
Mann-Whitney / ANOVA), correlation and regression with effect sizes, 95% CIs, assumption
checks and Holm multiplicity adjustment, then writes editable artifacts + provenance +
honest result.json. Not pre-baked answers.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
See SKILL.md, rules/rules_stats_analysis.md, docs/WORKFLOW.md, docs/ERROR_HANDLING.md.

## Files
SKILL.md; assemble.py; analysis_engine.py; w4kit.py; rules/rules_stats_analysis.md;
docs/; examples/stats_analysis/ (SYNTHETIC input/ + ir.json + README).

## Dependencies
Python 3.10+ standard library only. p-values via a stdlib regularized incomplete beta
(t/F distributions); t critical values via bisection; no numpy/scipy required. See
requirements.txt.

## Scope & limits
- Descriptive + inferential stats on csv/tsv/json tables (or read-only SQLite exports).
- Independent-sample methods; paired designs flagged (human_confirm). >2 groups → ANOVA,
  post-hoc not performed. Mann-Whitney uses a normal approximation (exact test not in
  stdlib). Formal Shapiro-Wilk/Levene not available — documented screens used instead.
- Does NOT do experiment design, sample-size estimation, or paper writing.

## Self-check
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/stats_analysis/ir.json --input examples/stats_analysis/input \
  --out w4/.tmp_analysis/challenge-c0e1e220
```
Expect exit 0, no validation errors, status success. Delete any __pycache__.
Hard limits: ≤50 UTF-8 text files, ≤500KB each, ≤2MB total, no binaries/symlinks.