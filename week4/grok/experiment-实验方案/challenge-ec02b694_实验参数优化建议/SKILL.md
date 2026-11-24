---
name: experiment-param-optimize
description: Suggest experiment parameter optimization (temperature, time, concentration, pH, etc.) from organizer-provided local data and literature/device ranges - recommended value + feasible range + rationale per parameter, reported optimum vs inferred suggestion, safe_eval numeric checks, observed-best recomputation and trial-cost arithmetic. Use when the task is 实验参数优化建议 (kind param_optimize).
---

# Experiment parameter optimization advice (实验参数优化建议)

A source-bound Skill for the Bohrium weekly contest (experiment track). The agent
reads the ACTUAL organizer-provided local material under /input (literature ranges,
device/manual limits, material constraints, pilot/data tables, price contracts),
fills a structured Parameter IR, and a deterministic stdlib engine validates it,
recomputes observed optima and numeric checks (safe_eval), verifies recommendations
against feasible ranges and device limits, and emits editable artifacts + provenance
+ an honest result.json. No pre-baked answers; every recommendation traces to a real
input file and paragraph/row.

## When to use
Given a research question and equipment/material constraints, produce an executable
parameter plan: key parameters, recommended values, feasible intervals, response
metric definition and verification method, search strategy and experiment cost.
Recommendations must fall inside device range, material limits and safety thresholds.
Trigger: workorder kind `param_optimize` (实验参数优化建议).

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve every key).
- /input/task.md — the research question, response metric and constraints.
- Actual material: literature optimum/range reports, device manuals (limits),
  material specs, pilot/data tables (parameter → response), price contracts.
Register the real files; trust content over labels.

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_experiment.py --input /input --out /app/output --work /app/work`
Auto-registers sources/documents from the ACTUAL /input materials, auto-fills the complete experiment
IR into /app/work, runs the SAME validate+build path as assemble.py, and ALWAYS writes an honest
result.json (try/except fallback preserves every output_contract key + case_id) — even on empty input
or failure. Judgment it cannot verify is flagged human_confirm; never fabricated. THEN, within remaining
budget, refine the auto-filled IR in /app/work and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/experiment_ir.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] + documents[].
2. Read material; fill params[] {name, current, recommended, range, unit, status, rationale, evidence}. Quote a literature optimum as source_optimum (status=reported); mark agent suggestions status=inferred. Register device/material limits[] and transcribe data rows as observations[] with row locators. Add numeric_checks[] (safe_eval expressions) and cost{}.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir params_ir.json --input /input --out /app/output`
   → validate_ir → build (in_range/in_limits checks, observed-best + response stats,
   safe_eval checks, trial-cost arithmetic) → param_optimize.json + report.md +
   provenance.json → result.json.
4. Honest status: success when every recommendation is reported/grounded, inside range
   and limits, with no gaps; partial when a value is inferred (human_confirm), outside
   range/limit, a check fails, data is missing, or quotes fail verification; failed on
   build error. Save partial early.

## Parameter IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto>
kind: "param_optimize"
sources: [{id, path}]
documents: [{id, source_id, title, paragraphs?: [{id, text}]}]
params: [{name, current?, recommended?, source_optimum?, range?: [lo,hi], unit?,
          response_metric?, response_direction?: higher_better|lower_better,
          status: reported|inferred, rationale, evidence}]
limits: [{param, range?: [lo,hi] / min? / max?, evidence}]   # device manual / material spec
observations: [{param, value, response, evidence}]           # actual data rows
numeric_checks: [{id, expr, env?: {sym: num}, min?, max?, equals?, tolerance?}]
cost: {per_trial?, n_trials?, budget?}
search_strategy: {method, n_trials?, stop_criterion?}
confirmations: [{item, reason, handling: human_confirm}]
provenance: {pipeline, changes: []}
uncertainty: [{item, reason, impact?, handling}]
```
status: reported (quoted optimum, evidence required) vs inferred (suggestion +
rationale + uncertainty). Evidence locator = {source_id, paragraph_id?, quote?, table?, field?}.
safe_eval whitelist: + - * / ** % // sqrt exp log log10 abs sin cos tan floor ceil min max pi e.

## Domain rules — param_optimize (rules/rules_param_optimize.md)
1. Every key parameter: recommended value + unit + feasible range [lo,hi] + rationale + evidence. A recommendation without a range or basis is incomplete.
2. Distinguish reported optimum (source_optimum quoted from literature/data, status=reported) from inferred suggestion (status=inferred + rationale + uncertainty + human_confirm). Never present an inference as a reported fact.
3. Recommendations must lie inside the feasible range AND device/material limits[]; the engine flags in_range/in_limits violations (partial). Cite the manual/spec for each limit.
4. Response metric: define how it is measured and its direction (higher_better/lower_better). When data rows exist, the engine recomputes the observed best + descriptive stats — do not hand-pick a best point the data contradicts.
5. Numeric checks via safe_eval (yield gain %, dose arithmetic, budget/trial count). Failed checks are surfaced, not hidden.
6. Cost: per_trial × n_trials vs budget; search strategy with a stop criterion. Keep units and cost口径 self-consistent.
7. Missing data/limit → not_reported + human_confirm; never fabricate an optimum or a device limit.

## Scripts & dependencies
assemble.py (CLI), experiment_engine.py (range/limit checks + observed-best + safe_eval
+ cost + provenance + report), w4kit.py (case load / source check / safe_eval / describe
/ linreg / result.json). Python 3.10+ standard library only. See requirements.txt.

## Outputs (/app/output)
param_optimize.json (params with checks/observed_best/response_stats + limits +
numeric_checks + cost + search_strategy + confirmations), report.md (editable parameter
plan), provenance.json, validation.json, result.json (preserves output_contract +
case_id + status + sources + uncertainty + change_log + limits).

## Error handling (docs/ERROR_HANDLING.md)
Inferred suggestion → human_confirm; value outside range/limit → violation + partial;
failed numeric check → surfaced; missing limit/data → not_reported; conflicting optima
→ source_conflict with both locators; quote mismatch → locator_issues. Never fabricate.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/param_optimize/`: input/ + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/param_optimize/ir.json --input examples/param_optimize/input --out /tmp/demo`
The example has a reported temperature optimum (matches observed best) and an inferred
pH suggestion (human_confirm) to demonstrate the reported/inferred distinction.

## Self-check
- [ ] every used input file registered; every parameter has range + unit + rationale + evidence
- [ ] reported optimum vs inferred suggestion distinguished; inferred → human_confirm
- [ ] recommendations inside feasible range AND device/material limits (engine checks pass)
- [ ] observed-best recomputed from actual data rows; response direction correct
- [ ] numeric_checks evaluated via safe_eval; failures surfaced
- [ ] trial cost arithmetic + budget + stop criterion present
- [ ] result.json honest; output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL, line 2 = SKILL.md.
Published under week4/grok in github.com/hehekevin/boerproduct; opens without login.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared answers.
Evaluator installs the Skill under /skills/weekly-skill and runs the official DeepSeek
Harness on each fixed original case (/input/case.json + task.md → /app/output/result.json
preserving output_contract + case_id). Budget: 64 requests, 900 s — save honest partial early.