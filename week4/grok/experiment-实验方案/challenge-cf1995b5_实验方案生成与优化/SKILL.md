---
name: experiment-protocol-design
description: Generate and optimize an executable experiment protocol from a research objective, constraints and organizer-provided local material - hypothesis, operational variables, controls, steps bound to reagents/equipment/parameter ranges, time and budget arithmetic, risks with stop-loss, and evidence-backed optimization suggestions. Use when the task is 实验方案生成与优化 / designing or revising an experiment plan (kind protocol_design).
---

# Experiment protocol generation & optimization (实验方案生成与优化)

A source-bound Skill for the Bohrium weekly contest (experiment track). The agent
reads the ACTUAL organizer-provided local material under /input (scientific sources,
prospective resource/price/booking contracts, versioned candidate plans, finite
parameter domains), fills a structured Design IR, and a deterministic stdlib engine
validates it, computes time/cost/range arithmetic and six-element coverage, and emits
editable artifacts + provenance + an honest result.json. No pre-baked answers; every
step/parameter/optimization traces to a real input file and paragraph.

## When to use
Turn a research goal into a schedulable, executable, peer-reviewable protocol:
testable hypothesis, operational variables (independent/dependent/confounder),
controls that exclude specific confounders, steps bound to equipment models/reagent
specs/parameter ranges with units, duration and budget estimates, failure modes with
criteria/stop-loss/alternatives, and optimization suggestions marked reported vs
inferred. Trigger: workorder kind `protocol_design` (实验方案生成与优化).

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve every key).
- /input/task.md — the concrete objective, constraints and rules for this case.
- Actual material files: literature/methods, equipment manuals/specs, reagent lists,
  price/booking contracts, prior or versioned candidate plans, parameter domain tables.
Read and register the real files; trust file content over filename/domain labels.
Planning scenarios are NOT claimed actual labs/vendor quotes/safety approvals.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] + documents[] (+ protocols[] if versioned plans are provided).
2. Read the material; fill the IR per `rules/rules_protocol_design.md` and the schema below.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir design_ir.json --input /input --out /app/output`
   → validate_ir → build (duration/cost sums, parallel groups, parameter-range checks,
   six-element coverage) → protocol_design.json + report.md (editable protocol) +
   provenance.json → result.json.
4. Honest status: success only when all six elements are covered, every claim has a
   locator and no human_confirm gaps; partial when controls/specs/ranges/budget are
   missing, a value falls outside its range, optimizations are inferred, or quotes fail
   verification; failed on IR/build error. Save partial early; never write 未完成 as 完成.

## Design IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto from /input/case.json>
kind: "protocol_design"
sources: [{id, path}]                 # every actual input file used
documents: [{id, source_id, title, paragraphs?: [{id, text}]}]  # for quote verification
protocols: [{id, source_id, version?, title}]                   # versioned candidate plans
objective: {statement, hypothesis?, budget_cap?, evidence?}
variables: [{name, role: independent|dependent|confounder|controlled,
             operational_definition, unit?, range?, measurement?, evidence}]
design:
  steps: [{step_id, action, duration_min?, cost?, parallel_group?,
           parameters: [{name, value, unit, range?: [lo,hi], evidence, status}],
           reagents: [{name, spec?, evidence}], equipment: [{name, model?, spec?, range?, evidence}],
           evidence, status}]
  controls: [{control_id, type: blank|positive|negative|dose_gradient|other,
              purpose, excludes_confound?, evidence}]
  optimizations: [{id, target_step?, suggestion, rationale, status: reported|inferred, evidence}]
risks: [{id, failure_mode, criterion?, stop_loss?, alternative?, evidence?}]
confirmations: [{item, reason, handling: human_confirm}]   # safety/ethics/equipment availability
provenance: {pipeline, changes: []}
uncertainty: [{item, reason, impact?, handling}]
```
status vocabulary: reported | inferred | not_reported | source_conflict | extraction_failed | insufficient_evidence.
Evidence locator = {source_id, paragraph_id?, quote?, page?, table?, field?}.

## Domain rules — protocol_design (rules/rules_protocol_design.md)
1. Hypothesis must be testable; every variable gets an operational definition + measurement + unit. Name the confounders.
2. Controls: more than a single blank — positive/negative/dose-gradient as the objective demands; state which confounder each excludes.
3. Steps bind to concrete equipment model/range and reagent spec; mark substitutable vs non-substitutable. Parameter ranges come from device manuals, pilot data or literature — cite which.
4. Time & cost: duration_min per step (parallel_group for concurrency), cost per step; engine sums and checks against budget_cap. Never leave scheduling unquantified when material allows.
5. Risks: failure modes (contamination, no signal, poor reproducibility, insufficient sample) with judgement criterion, stop-loss point and alternative path.
6. Optimizations: reported (quoted from material) vs inferred (agent suggestion + rationale + uncertainty). Never present an inferred suggestion as an executable fact; route safety/ethics/equipment-availability to confirmations[].

## Scripts & dependencies
assemble.py (CLI), experiment_engine.py (validation + design arithmetic + coverage +
provenance + report), w4kit.py (case load / source check / safe_eval / stats /
result.json). Python 3.10+ standard library only — no third-party packages. See requirements.txt.

## Outputs (/app/output)
protocol_design.json (objective/variables/steps/controls/optimizations/risks + totals +
coverage + range_violations + confirmations), report.md (editable protocol),
provenance.json (claim → source locator map + source sha256), validation.json,
result.json (preserves output_contract + case_id + status + sources + uncertainty + change_log + limits).

## Error handling (docs/ERROR_HANDLING.md)
Missing spec/range/budget → not_reported + human_confirm (never guessed); value outside
range → range_violations + partial; inferred optimization → confirmation; conflicting
sources → source_conflict with both locators; unreadable file → file_not_found in
provenance; quote mismatch → locator_issues. Never fabricate; never silent-skip.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/protocol_design/`: input/ + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/protocol_design/ir.json --input examples/protocol_design/input --out /tmp/demo`
The example deliberately includes gaps (missing equipment model, an inferred
optimization, a parameter at its range edge) to demonstrate honest partial status.
Real cases are supplied only at evaluation.

## Self-check
- [ ] every used input file registered in sources[]; steps/controls/optimizations carry evidence locators
- [ ] hypothesis testable; variables operationalized with units; confounders named
- [ ] controls exclude specific confounders (not blank-only); types valid
- [ ] parameters have units + ranges with a cited basis; engine range check passes
- [ ] duration/cost quantified; budget_cap respected or flagged
- [ ] risks have criterion + stop-loss + alternative
- [ ] reported vs inferred distinguished; safety/ethics/availability in confirmations[]
- [ ] result.json honest (status/sources/uncertainty/change_log); output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL of this work,
line 2 = relative entry file (SKILL.md). Published under week4/grok in
github.com/hehekevin/boerproduct; opens without login.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared answers or
formal test outputs. Evaluator installs the Skill under /skills/weekly-skill and runs
the official DeepSeek Harness on each fixed original case (/input/case.json + task.md
→ /app/output/result.json preserving output_contract + case_id). Budget: 64 requests,
900 s, 16384 tokens/response — save honest partial deliverables early, improve incrementally.