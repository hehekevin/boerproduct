---
name: analysis-multi-step
description: Orchestrate a multi-step research-data analysis pipeline (load -> clean -> stats -> visualize -> interpret) over the actual organizer data, with per-step provenance, intermediate artifacts, dependency ordering, honest step status (done/partial/failed/skipped), and a report whose numbers are back-filled from and cross-checked against the computed metrics. Use when the task is 多步骤数据分析Agent / an end-to-end orchestrated analysis of provided tables.
---

# Multi-step data analysis Agent (多步骤数据分析Agent)

A source-bound Skill for the Bohrium weekly contest (analysis track, agent-6aefb2fd).
The agent reads the ACTUAL organizer material under /input, decomposes the task into an
ordered pipeline of steps, fills a structured IR, and a deterministic stdlib engine
orchestrates load → clean → stats → viz → query → interpret, sharing a data context so each
step consumes the previous step's real output. Every step has provenance + intermediate
artifacts + honest status; the final report's numbers are cross-checked against computed
metrics (back-fill check). No pre-baked answers; the whole pipeline recomputes from real rows.

## Focus (rubric points)
- 实际效果: a real multi-step pipeline runs end-to-end on the given tables; each step's
  caliber is explicit; report numbers/tables/figures are same-source and recomputable.
- 创新增益: per-step provenance (inputs sha → outputs → status), dependency-ordered execution,
  automatic report-number back-fill verification (claimed value vs computed metric), and
  honest cascade (a failed step skips its dependents with a reason, never fabricates).
- 可靠体验: field alignment across tables, cleaning impact on row count/distribution recorded,
  stats assumption checks, viz consistency; failure is locatable and recoverable per step.
- Reuses the same deterministic sub-engines as the sibling single-kind skills (cleaning/stats/
  charts/queries), so each step is independently verifiable.

## Inputs (runtime)
- /input/case.json — case_id + output_contract (preserve every key).
- /input/task.md — the concrete multi-step analysis request.
- Actual material: one or more data tables/databases + dictionary (fields, units, keys, design).

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_analysis.py --input /input --out /app/output --work /app/work`
Auto-registers sources from the ACTUAL /input materials, auto-fills a complete source-bound IR
into /app/work, runs the SAME validate+build path as the package assembler, and ALWAYS writes an
honest result.json (try/except fallback preserves every output_contract key + case_id) — even on
empty input or failure. Judgment it cannot verify is flagged human_confirm; never fabricated.
THEN, within remaining budget, refine the auto-filled IR in /app/work and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/<ir>.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory; register sources[] + datasets[] (real paths/columns). Read the dictionary.
2. Decompose into steps[] (load/clean/stats/viz/query/interpret) with depends_on ordering and
   per-step payload (same schemas as the sibling skills). Fill interpret claims referencing
   computed metrics. Follow rules/rules_multi_step_analysis.md.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir pipeline_ir.json --input /input --out /app/output`
   → validate_ir → orchestrate steps in order → per-step artifacts (step_<id>_*) + pipeline.json
   + provenance.json + report.md → result.json.
4. Honest status: success when every step done and back-fill checks pass; partial on any
   partial/failed/skipped step, back-fill mismatch, or declared uncertainty.

## IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto>
kind: "multi_step_analysis"
sources: [{id, path, description?}]
datasets: [{dataset_id, source_id, path, columns?}]
steps: [{
  step_id, kind, depends_on: [earlier step_id],
  payload: {...},        # per kind:
  # load:    {dataset_ids: [...]}
  # clean:   {operations: [...]}        # same as data_cleaning ops
  # stats:   {analyses: [...]}          # same as stats_analysis analyses
  # viz:     {charts: [...]}            # same as data_viz charts
  # query:   {queries: [...]}           # same as db_query_analysis queries
  # interpret: {text, claims: [{metric, value, tolerance?}]}
}]
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes?}
```
Data context is shared: a clean step replaces ctx[dataset].rows with the cleaned rows, so
downstream stats/viz/query steps consume the CLEANED data. interpret claims reference metrics
as "<analysis_id>.<key>" (e.g. "desc_val.mean", "cmp.cohens_d"); the engine compares the
claimed value to the computed metric (back-fill check). Step status: done|partial|failed|skipped.

## Domain rules
See rules/rules_multi_step_analysis.md (decomposition, field alignment, cleaning impact,
assumption checks, viz consistency, report back-fill, dependency cascade, recovery).

## Scripts & dependencies
assemble.py (CLI), analysis_engine.py (orchestrator + cleaning/stats/charts/queries sub-engines
+ back-fill check + provenance), w4kit.py. Python 3.10+ stdlib; matplotlib optional (PNG only).
See requirements.txt.

## Outputs (/app/output)
Per-step intermediate artifacts (step_<id>_cleaned_*.csv / cleaning_log.json / stats_results.json
/ chart_*.svg / query_*.csv ...), pipeline.json (step statuses + metrics + back-fill checks),
provenance.json (step → inputs/outputs/status), report.md, validation.json, result.json.

## Error handling (docs/ERROR_HANDLING.md)
A failed step → its dependents skipped with reason (cascade), overall partial; a partial step
(missing data, failed ops, insufficient stats, skipped viz rows) propagates partial; interpret
back-fill mismatch → partial (report numbers not same-source); unreadable dataset → load partial;
IR forward-dependency → validation error. Never fabricate a downstream result from a failed step.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/multi_step_analysis/`: input/ (dictionary + 7-row table with a duplicate) + ir.json
(load → clean → stats → viz → interpret). Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/multi_step_analysis/ir.json --input examples/multi_step_analysis/input --out w4/.tmp_analysis/agent-6aefb2fd`
Demonstrates dedup feeding stats/viz + back-filled report numbers (mean 17.0, Cohen's d -5.0).

## Self-check
- [ ] steps decomposed with valid depends_on ordering; payloads match sibling schemas
- [ ] clean step impact recorded (rows before/after); downstream consumes cleaned data
- [ ] stats assumptions stated; viz glyphs data-bound; query read-only
- [ ] interpret claims cross-checked vs computed metrics (back-fill pass)
- [ ] per-step provenance + intermediate artifacts; failed step → dependents skipped
- [ ] result.json honest (success/partial); output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt: line 1 = public GitHub tree URL, line 2 = SKILL.md. Opens without login.

## Runtime contract
Skill authoring task. Valid frontmatter. No prepared answers. Evaluator installs under
/skills/weekly-skill, runs the Harness on 3 fixed cases (/input → /app/output/result.json
preserving output_contract + case_id). Budget 64 requests / 900 s; save honest partial early.
Resources ≤50 UTF-8 text files, ≤500KB each, ≤2MB total, no binaries/symlinks/__pycache__.