---
name: analysis-stats-analysis
description: Recompute descriptive statistics, group comparisons (Welch t / Mann-Whitney / one-way ANOVA), correlation and OLS regression from the actual organizer data tables, with effect sizes, 95% confidence intervals, assumption checks, Holm multiplicity adjustment and data-tied interpretation. Use when the task is 统计分析与结果解读 / descriptive or inferential statistics on provided CSV/TSV/JSON research data.
---

# Statistical analysis & interpretation (统计分析与结果解读)

A source-bound Skill for the Bohrium weekly contest (analysis track, challenge-c0e1e220).
The agent reads the ACTUAL organizer material under /input (data dictionary, field
semantics, the real data table), fills a structured IR, and a deterministic stdlib engine
RECOMPUTES every statistic from the real rows (w4kit.describe/correlation/linreg + a
stdlib incomplete-beta implementation for t/F p-values), attaches effect sizes + CIs +
assumption notes, and emits editable artifacts + provenance + an honest result.json.
No pre-baked numbers; every statistic traces to dataset + column + rows used.

## Focus (rubric points)
- 实际效果: descriptive stats, group comparison, correlation/regression actually computed
  on the real table; correct method for the design (2 groups → Welch; >2 → ANOVA, never
  a two-sample t-test on three groups); interpretation tied to the computed numbers.
- 创新增益: effect size + CI for every key estimate; normality/homoscedasticity screening;
  automatic Holm adjustment within declared test families; reported-vs-inferred separation.
- 可靠体验: missing excluded pairwise and counted (never treated as 0, never silently
  dropped); insufficient n / zero variance → insufficient_evidence, not a fake p-value.
- Organizer note: cases may be attributed UCI Concrete/Iris/Wine snapshots or SQLite
  exports — read the actual columns/units from the dictionary, never assume from labels.

## Inputs (runtime)
- /input/case.json — copy case_id; preserve every output_contract key.
- /input/task.md — the concrete analysis question for this case.
- Actual material: data table(s), data dictionary (field meaning, units, group design).

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_analysis.py --input /input --out /app/output --work /app/work`
Auto-extracts the IR from the ACTUAL /input materials (registers sources + datasets;
reads the data dictionary for units/outcome/group/design; recomputes real statistics
via w4kit.describe/correlation/linreg on the actual rows), runs the engine
(validate_ir + build), and writes a complete honest result.json preserving every
output_contract key + case_id. Judgment fields it cannot verify (expert interpretation,
practical significance) are flagged human_confirm — never fabricated; missing values
are excluded pairwise, never treated as 0, never imputed.
THEN, within remaining budget, refine judgment-heavy fields in /app/work/analysis_ir.json
(interpretations, assumptions, method choices) and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/analysis_ir.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Run `PYTHONDONTWRITEBYTECODE=1 python auto_analysis.py --input /input --out /app/output --work /app/work`
   to auto-extract materials and produce a complete baseline result.json. Then, within
   budget, refine judgment-heavy fields in /app/work/analysis_ir.json and re-run
   assemble.py to improve. Save partial early; never fabricate.
2. Inventory inputs; register sources[] + datasets[] (real paths).
3. Read the dictionary: which column is the outcome, which is the group/design factor,
   units, missing codes, pairing/independence structure. Fill the IR per
   rules/rules_stats_analysis.md — including an interpretation per analysis.
4. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir stats_ir.json --input /input --out /app/output`
   → validate_ir → recompute → stats_results.json + provenance.json + report.md → result.json.
5. Honest status: success only when all analyses computed, interpretations present, no
   gaps; partial on insufficient_evidence, failed analyses, missing interpretation, or
   declared uncertainty.

## IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto>
kind: "stats_analysis"
sources: [{id, path, description?}]
datasets: [{dataset_id, source_id, path, columns?}]
stats: {analyses: [{
  analysis_id, type, dataset_id,
  column?            # describe / compare_groups outcome
  group_column?      # compare_groups factor
  columns? [x, y]    # correlation / regression (or x?, y?)
  method?            # correlation: pearson|spearman; compare_groups: auto|mannwhitney
  family?            # tests sharing a family get Holm-adjusted p
  assumptions? [..]  # design notes (independence, pairing, units)
  interpretation     # REQUIRED: data-tied reading (effect direction, magnitude,
                     #   statistical vs practical significance, limits)
}]}
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes?}
```
Analysis types: describe | compare_groups | correlation | regression.
Engine adds: describe (n/mean/sd/var/quartiles/min/max/missing + skew/kurtosis + mean CI);
compare_groups (per-group describe, Welch t/df/p, Cohen's d, mean-diff CI, variance-ratio
F test, Mann-Whitney when non-normal, ANOVA F/p/eta² for >2 groups); correlation (r, t, p,
Fisher-z CI, optional Spearman); regression (slope/intercept/R², slope SE/t/p/CI, residual sd).

## Domain rules
See rules/rules_stats_analysis.md (method selection, assumptions, effect size + CI,
multiplicity, interpretation discipline, stdlib limits).

## Scripts & dependencies
assemble.py (CLI), analysis_engine.py (recompute + p-values via stdlib incomplete beta +
Holm + provenance), w4kit.py (describe/correlation/linreg/safe_eval/result.json).
Python 3.10+ standard library only. See requirements.txt.

## Outputs (/app/output)
stats_results.json (every statistic + status + evidence locator + assumptions +
auto_summary + agent interpretation + adjusted p), provenance.json, report.md,
validation.json, result.json (preserves output_contract + case_id + status + sources +
uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Missing/non-numeric → excluded pairwise and counted, never 0-filled; n<2 / zero variance →
insufficient_evidence with reason; >2 groups → ANOVA (post-hoc NOT performed, stated);
non-normal small sample → Mann-Whitney normal approximation (exact test not available in
stdlib, stated); missing interpretation → flagged human_confirm; unreadable table →
failed dataset + partial. Never report a p-value as proof of effectiveness.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/stats_analysis/`: input/ (dictionary + 12-row two-group table) + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/stats_analysis/ir.json --input examples/stats_analysis/input --out w4/.tmp_analysis/challenge-c0e1e220`
Demonstrates describe + Welch comparison + correlation + regression with CIs and effect size.

## Self-check
- [ ] dictionary read; outcome/group columns and units confirmed from real header
- [ ] every statistic recomputed from real rows; evidence carries dataset+column+n_rows_used
- [ ] method matches design (2 groups Welch, >2 ANOVA); assumptions stated
- [ ] effect size + 95% CI present for key estimates; missing counted, never 0-filled
- [ ] multiplicity handled (family → Holm); interpretation distinguishes stat vs practical
- [ ] insufficient n / zero variance → insufficient_evidence, not fabricated numbers
- [ ] result.json honest; output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt: line 1 = public GitHub tree URL, line 2 = SKILL.md. Opens without login.

## Runtime contract
Skill authoring task. Valid name/description frontmatter. No prepared answers. Evaluator
installs under /skills/weekly-skill, runs the official Harness on 3 fixed cases
(/input → /app/output/result.json preserving output_contract + case_id). Budget 64
requests / 900 s; save honest partial early. Resources ≤50 UTF-8 text files, ≤500KB each,
≤2MB total, no binaries/symlinks/__pycache__.