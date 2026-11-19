---
name: review-methods-stats-review
description: Research methods and statistics audit (研究方法与统计审查) over organizer-provided local material. Checks design/controls/blinding, variable definitions, test-choice appropriateness and assumptions, sample size and power, p-value/CI/effect-size reporting — and RECOMPUTES reported statistics from the actual provided data with a stdlib engine (describe/correlation/linreg/safe expression eval), flagging reported-vs-recomputed mismatches with exact locators. Use when the task is to audit a manuscript's methodology and statistical reporting and verify its numbers against provided data.
---

# Methods & statistics review (研究方法与统计审查)

A source-bound Skill for the Bohrium weekly contest (REVIEW track, contest
bohr-product period 4). The agent reads the ACTUAL organizer-provided local
material under /input (manuscript + data tables), fills a structured Review IR,
and a deterministic stdlib engine validates it, verifies evidence quotes,
RECOMPUTES statistics from the real data files, compares reported vs computed
values with explicit tolerances, and emits editable artifacts + provenance +
an honest result.json. No pre-baked answers; every numeric verdict is replayable.

## When to use
The workorder asks to audit study design, variable definitions, statistical
methods, sample size/power, or results reporting (kind `methods_stats_review`).
Distinguish "method itself flawed" from "method acceptable but reporting
incomplete". NOT for doing new data analysis/modeling for the authors.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve every key).
- /input/task.md — the concrete task rules for this case.
- The actual manuscript + provided data tables (csv/tsv/json) + any protocol.
Read and register the real files; trust file content over filename labels.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs; register sources[] + documents[] (manuscript/data/...);
   set manuscript_id.
2. Audit methods per `rules/rules_methods_stats_review.md`; fill findings[].
   For every checkable reported statistic, add a stats_checks[] entry pointing
   at the ACTUAL data file/fields (or IR-transcribed values with locators).
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir review_ir.json --input /input --out /app/output`
   → validate_ir → quote verification + REAL recomputation
   (w4kit.describe/correlation/linreg/safe_eval) → tolerance comparison →
   review.json + checklist.csv + provenance.json + report.md → result.json.
4. Honest status: success when all checks recomputable and locators verify
   (mismatches are confirmed review RESULTS, not failures); partial when data
   is missing/unreadable, a check is not_recomputable, or evidence is
   insufficient; failed on IR/build error.

## Review IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto>
kind: "methods_stats_review"
sources: [{id, path, role?}]
documents: [{document_id, source_id, role, title, content_path?, paragraphs?}]
manuscript_id: <document_id>
findings: [{id, dimension: design|variables|statistical_test|assumptions|
            sample_size_power|effect_size|p_ci_interpretation|reporting,
            severity: major|minor|suggestion,
            status: confirmed|suspected|insufficient_evidence|not_applicable,
            polarity?: issue|strength, verdict, evidence[], recommendation}]
stats_checks: [{id, description,
   check_type: describe|correlation|linreg|expr,
   data?: {source_id, field?, x_field?, y_field?},   # real data file
   values?: [...] | xs?: [...], ys?: [...],          # or IR-transcribed series
   expr?: "mean + 1.96*sd/sqrt(n)", env?: {mean:..., sd:..., n:...},
   reported?: {mean?, sd?, n?, min?, max?, median?, r?, slope?, intercept?, r2?, value?},
   tolerance?: {rel: 0.05, abs: 1e-9},
   evidence[]}]                                       # locator of reported values
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes[]}
```
Evidence locator = {source_id, document_id?, paragraph_id?, quote?, page?, table?, field?}.
Recomputation is deterministic: describe → n/mean/sd/var/min/max/quartiles;
correlation → Pearson r; linreg → slope/intercept/r2/n; expr → AST-whitelisted
arithmetic (sqrt/exp/log/sin/cos/min/max/pi...). Comparison verdicts per key:
match / mismatch / not_comparable; check verdict: match / mismatch /
recomputed_only / partial_compare / not_recomputable (with reason).

## Domain rules — methods_stats_review
Full rules: `rules/rules_methods_stats_review.md`. Key points:
1. Design: type vs research question, controls, grouping, blinding, bias
   control, pre-specified primary endpoint/hypothesis.
2. Variables: definitions, measurement, coding, cut-points, units, missing-data
   handling; variable type must fit the statistical model.
3. Tests: match test to data structure/distribution/independence; multiple
   comparisons, repeated measures, interactions, sensitivity analyses.
4. Power: sample-size justification, effect-size source, alpha/power settings,
   actual enrollment vs planned, dropout/exclusion handling.
5. Reporting: effect size + CI, exact p, statistic + df, figure/text numeric
   consistency; recompute whenever data is provided — never eyeball.
6. Severity matched to defect nature; reporting gaps ≠ design flaws.

## Scripts & dependencies
assemble.py (CLI), review_engine.py (validation + recomputation + comparison),
w4kit.py (shared core incl. stats). Python 3.10+ standard library only.

## Outputs (/app/output)
review.json (findings + stats_checks with computed values and per-key
comparisons), checklist.csv, report.md, provenance.json, validation.json,
result.json (preserves output_contract + case_id + status + sources +
uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Missing data file/field → not_recomputable + reason (reported values kept as
reported); n<2 or zero variance → not_recomputable; bad expression → recompute
failed note; unreadable manuscript → honest content_status; quote mismatch →
flagged + human_confirm. Never fabricate a computed value.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/methods_stats_review/`: input/ (manuscript + data.csv) + ir.json. Run:
`python assemble.py --ir examples/methods_stats_review/ir.json --input examples/methods_stats_review/input --out /tmp/demo`
The demo shows a real SD mismatch (reported 1.5 vs recomputed 1.309), a matching
regression, a CI consistency check, and a not_recomputable check (missing column).

## Self-check
- [ ] every used input file registered; manuscript_id set
- [ ] findings cover design/variables/test/power/reporting as applicable
- [ ] every checkable reported statistic has a stats_check with data locator
- [ ] recomputation ran on REAL data (computed values present, tolerances explicit)
- [ ] mismatches reported with both values; not_recomputable reasons recorded
- [ ] result.json honest; output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL (filled by
git_sync; currently PENDING_GIT_SYNC), line 2 = SKILL.md.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared
answers or formal test outputs. Evaluator installs the Skill under
/skills/weekly-skill and runs the official DeepSeek Harness on each fixed
original case (/input/case.json + task.md → /app/output/result.json preserving
output_contract + case_id). Partial results identify their limits.