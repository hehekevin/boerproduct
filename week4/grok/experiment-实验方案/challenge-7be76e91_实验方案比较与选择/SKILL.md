---
name: experiment-protocol-compare
description: Compare multiple candidate experiment protocols on a common weighted matrix (cost, time, yield, safety, reproducibility, ...) with per-cell source locators, min-max normalization, weighted scoring and ranking, a defensible recommendation, tradeoffs and weight-sensitivity analysis. Use when the task is 实验方案比较与选择 / choosing between versioned candidate plans (kind protocol_compare).
---

# Experiment protocol comparison & selection (实验方案比较与选择)

A source-bound Skill for the Bohrium weekly contest (experiment track). The agent
reads the ACTUAL organizer-provided local material under /input (versioned candidate
plans, price/time/yield/safety data, criteria definitions), fills a structured
Comparison IR, and a deterministic stdlib engine validates it, normalizes the matrix,
computes weighted scores/ranking/margin/tradeoffs/weight-sensitivity, and emits
editable artifacts + provenance + an honest result.json. No pre-baked answers; every
matrix cell traces to a real input file and paragraph.

## When to use
Put multiple candidate protocols on ONE comparable matrix, complete the comparison
and give a defensible choice. Cover the seven required fields (hypothesis & variables,
controls, equipment & materials, time & cost, parameter ranges, risks & anomalies,
ethics & safety) plus the key comparison dimensions. Numbers, sources and the final
choice must all withstand independent re-computation. Trigger: workorder kind
`protocol_compare` (实验方案比较与选择).

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve every key).
- /input/task.md — the criteria, weights and decision context.
- Actual material: the candidate plans (often 3 versioned plans), their cost/time/
  yield/safety/reproducibility figures, and any price/booking contracts. Register the
  real files; trust content over labels.

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
1. Inventory inputs (w4kit.list_materials); register sources[] + documents[] + protocols[] (one per candidate version).
2. Read material; fill comparison.criteria[] {id, name, direction, weight}, candidates[] {id, source_id, protocol_id, title}, and matrix cells {criterion_id, candidate_id, value, status, evidence}. Quote each figure from the actual plan text. Missing figure → status=not_reported (never guessed).
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir compare_ir.json --input /input --out /app/output`
   → validate_ir → build (min-max normalization, weighted sum, ranking, margin,
   per-criterion tradeoffs, ±20% weight sensitivity) → protocol_compare.json +
   report.md + provenance.json → result.json.
4. Honest status: success when the matrix is complete and the choice is robust; partial
   when cells are not_reported, coverage<60%, margin<0.05 (weight-sensitive →
   human_confirm), weights are inconsistent, or quotes fail verification; failed on
   build error. Save partial early.

## Comparison IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto>
kind: "protocol_compare"
sources: [{id, path}]
documents: [{id, source_id, title, paragraphs?: [{id, text}]}]
protocols: [{id, source_id, version?, title}]
comparison:
  criteria: [{id, name, direction: higher_better|lower_better, weight, unit?, evidence?}]
  candidates: [{id, title, source_id, protocol_id?, version?}]
  weights: {criterion_id: weight}        # optional alternative to criteria[].weight
  matrix: [{criterion_id, candidate_id, value, status, evidence}]
          # OR nested {criterion_id: {candidate_id: {value, status, evidence}}}
confirmations: [{item, reason, handling: human_confirm}]
provenance: {pipeline, changes: []}
uncertainty: [{item, reason, impact?, handling}]
```
cell status: reported | inferred | not_reported | source_conflict | extraction_failed.
Evidence locator = {source_id, paragraph_id?, quote?, table?, field?}.

## Domain rules — protocol_compare (rules/rules_protocol_compare.md)
1. Same matrix for all candidates: identical criteria, units and口径. Convert units explicitly; a cell with mixed units is invalid.
2. Every cell carries a source locator quoting the actual plan figure. A missing figure is not_reported (excluded from weighting, coverage reported) — never imputed.
3. direction: cost/time/risk lower_better; yield/safety/reproducibility higher_better. Weights ≥0; engine renormalizes to sum 1 (warns if raw sum ≠ 1).
4. Engine method: min-max normalize each criterion across candidates (lower_better inverted; all-equal → 0.5), weighted sum → score, rank, margin = top−second.
5. Defensibility: report per-criterion tradeoffs (winner + value + evidence) and ±20% weight sensitivity (does the winner flip?). margin<0.05 or coverage<60% → human_confirm; do not overclaim a robust choice.
6. Qualitative criteria: supply a justified 0-1 score (status=inferred + rationale) or leave not_reported; never silently turn text into a number.
7. Versioned plans: register each version in protocols[]; candidates reference protocol_id + version; cite the actual version text, not a label.

## Scripts & dependencies
assemble.py (CLI), experiment_engine.py (normalization + weighting + ranking +
sensitivity + provenance + report), w4kit.py (case load / source check / stats /
result.json). Python 3.10+ standard library only. See requirements.txt.

## Outputs (/app/output)
protocol_compare.json (criteria + candidates + normalized matrix + scores + coverage +
ranking + recommendation + margin + tradeoffs + weight_sensitivity_flips +
confirmations), report.md (editable comparison matrix), provenance.json,
validation.json, result.json (preserves output_contract + case_id + status + sources +
uncertainty + change_log + limits).

## Error handling (docs/ERROR_HANDLING.md)
Missing cell → not_reported + coverage; non-numeric value without score → excluded;
weight-sensitive choice → human_confirm; conflicting figures → source_conflict with
both locators; duplicate cell / unknown criterion or candidate → validation error;
quote mismatch → locator_issues. Never fabricate a figure or a winner.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/protocol_compare/`: input/ + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/protocol_compare/ir.json --input examples/protocol_compare/input --out /tmp/demo`
The example compares 3 plans on cost/time/yield/safety; the top-two margin is <0.05,
demonstrating a weight-sensitive (human_confirm) recommendation and partial status.

## Self-check
- [ ] every used input file registered; candidates reference real protocol versions
- [ ] every matrix cell has a locator quoting the actual figure; missing = not_reported
- [ ] criteria directions + units consistent; weights ≥0 and renormalized
- [ ] normalization + weighted score + ranking recomputable; margin reported
- [ ] tradeoffs + weight sensitivity reported; fragile choice → human_confirm
- [ ] recommendation defensible and traceable; no fabricated winner
- [ ] result.json honest; output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL, line 2 = SKILL.md.
Published under week4/grok in github.com/hehekevin/boerproduct; opens without login.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared answers.
Evaluator installs the Skill under /skills/weekly-skill and runs the official DeepSeek
Harness on each fixed original case (/input/case.json + task.md → /app/output/result.json
preserving output_contract + case_id). Budget: 64 requests, 900 s — save honest partial early.