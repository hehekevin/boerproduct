---
name: experiment-result-anomaly
description: Interpret provided experimental results and diagnose anomalies - expected vs observed with tolerance arithmetic, replicate statistics, IQR outlier flags, trend regression, candidate causes ranked by evidence support (never asserted as fact), corrective actions and follow-up experiments. Use when the task is 实验结果解释与异常分析 (kind result_anomaly).
---

# Experiment result interpretation & anomaly analysis (实验结果解释与异常分析)

A source-bound Skill for the Bohrium weekly contest (experiment track). The agent
reads the ACTUAL organizer-provided local material under /input (result tables,
reference/expected values, tolerances, calibration/run logs, method notes), fills a
structured Result IR, and a deterministic stdlib engine validates it, recomputes
deviations/tolerance checks/replicate stats/outliers/trends, ranks candidate causes by
evidence support, and emits editable artifacts + provenance + an honest result.json.
No pre-baked answers; every conclusion traces to a real data file, field and threshold.

## When to use
Turn a dataset into five checkable conclusion segments: trend, anomaly points, possible
causes, verification steps, and follow-up experiment suggestions. Trend direction/
inflection/magnitude must match the raw readings; anomalies must flag the truly
abnormal objects; cause conclusions must be data-supported. Cover all metrics,
controls, replicates and edge cases, and state the unexplained part. Trigger: workorder
kind `result_anomaly` (实验结果解释与异常分析).

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve every key).
- /input/task.md — the metrics, expected values, tolerances and analysis scope.
- Actual material: result data tables (replicates/series), reference methods, expected
  values + tolerances, calibration records, run logs, control measurements. Register
  the real files; trust content over labels.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] + documents[].
2. Read material; fill results[] {metric, expected, observed (value or replicate list), tolerance (abs or {abs,pct}), unit, evidence, series?}. Transcribe anomalies[] {id, observation, candidate_causes[{cause, support, evidence, status}], action}. A cause asserted as supported REQUIRES evidence; unsupported → unknown/insufficient_evidence. Add follow_up[] and unexplained[].
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir anomaly_ir.json --input /input --out /app/output`
   → validate_ir → build (deviation + within-tolerance, describe stats, IQR outlier
   flags, linreg trend, cause ranking by support) → result_anomaly.json + report.md +
   provenance.json → result.json.
4. Honest status: success when every metric is interpreted with traceable evidence and
   causes are appropriately supported; partial when expected/tolerance is missing
   (within unknown), a cause lacks evidence (insufficient_evidence + human_confirm),
   replicates are too few for outlier stats, or quotes fail verification; failed on
   build error. Finding anomalies is completion, not failure. Save partial early.

## Result IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto>
kind: "result_anomaly"
sources: [{id, path}]
documents: [{id, source_id, title, paragraphs?: [{id, text}]}]
results: [{metric, expected?, observed: num|[nums], tolerance?: num|{abs?,pct?},
           unit?, evidence, series?: [{x,y}]}]
anomalies: [{id, observation, metric?,
             candidate_causes: [{cause, support: supported|partially_supported|contradicted|unknown,
                                 status?: reported|inferred, evidence?}],
             action, evidence?}]
follow_up: [{action, rationale, evidence?}]
unexplained: [{item, reason}]
confirmations: [{item, reason, handling: human_confirm}]
provenance: {pipeline, changes: []}
uncertainty: [{item, reason, impact?, handling}]
```
Evidence locator = {source_id, paragraph_id?, quote?, table?, field?}.
support vocabulary: supported | partially_supported | contradicted | unknown.

## Domain rules — result_anomaly (rules/rules_result_anomaly.md)
1. Every metric: expected vs observed with unit + tolerance. Engine computes deviation and within_tolerance (abs and/or pct; all provided tolerances must hold). Missing expected/tolerance → within=null + note, never guessed.
2. Replicates: engine computes describe (n/mean/sd/quartiles). Outlier flags use the IQR rule (1.5×IQR, n≥4) and are labelled inferred flags, not confirmed errors. n<4 → state insufficient replicates.
3. Trend: when a series {x,y} exists, engine runs linreg (slope/intercept/r2) and labels direction; interpretation must match the raw readings.
4. Candidate causes: rank by evidence support (supported>partially_supported>unknown>contradicted). A cause marked supported/partially_supported/contradicted REQUIRES an evidence locator — never assert a cause as fact without data. No evidence → insufficient_evidence + human_confirm.
5. Always give a corrective action per anomaly and follow-up experiments to discriminate between candidate causes. State the unexplained part explicitly.
6. Cover controls, replicates and edge cases; do not cherry-pick. Distinguish reported (quoted) vs inferred (diagnosed) conclusions.
7. Never fabricate a reading, an expected value, a tolerance or a cause. Conflicting records → source_conflict with both locators.

## Scripts & dependencies
assemble.py (CLI), experiment_engine.py (tolerance arithmetic + describe + IQR outliers
+ linreg + cause ranking + provenance + report), w4kit.py (case load / source check /
describe / linreg / result.json). Python 3.10+ standard library only. See requirements.txt.

## Outputs (/app/output)
result_anomaly.json (results with stats/deviation/within_tolerance/outlier_flags/trend +
anomalies with ranked candidate_causes + follow_up + unexplained + confirmations),
report.md (editable interpretation), provenance.json, validation.json, result.json
(preserves output_contract + case_id + status + sources + uncertainty + change_log + limits).

## Error handling (docs/ERROR_HANDLING.md)
Missing expected/tolerance → within=null + note; cause without evidence →
insufficient_evidence + human_confirm (never a fact); n<4 replicates → outlier rule not
applied; conflicting readings → source_conflict; quote mismatch → locator_issues;
unreadable data → file_not_found. Never fabricate a cause as fact.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/result_anomaly/`: input/ + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/result_anomaly/ir.json --input examples/result_anomaly/input --out /tmp/demo`
The example has a yield outlier (r3=9.8, IQR-flagged) with two partially-supported
causes + one unsupported cause, and an out-of-tolerance purity metric — demonstrating
honest ranked causes and partial status.

## Self-check
- [ ] every used input file registered; every metric/cause has a data/field locator
- [ ] expected vs observed + tolerance arithmetic correct; within unknown when missing
- [ ] replicate stats + IQR outliers recomputed; flags labelled inferred
- [ ] trend matches raw readings (linreg) when series provided
- [ ] causes ranked by support; supported claims have evidence; unsupported → human_confirm
- [ ] corrective actions + follow-up + unexplained stated; controls/replicates covered
- [ ] result.json honest; output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL, line 2 = SKILL.md.
Published under week4/grok in github.com/hehekevin/boerproduct; opens without login.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared answers.
Evaluator installs the Skill under /skills/weekly-skill and runs the official DeepSeek
Harness on each fixed original case (/input/case.json + task.md → /app/output/result.json
preserving output_contract + case_id). Budget: 64 requests, 900 s — save honest partial early.