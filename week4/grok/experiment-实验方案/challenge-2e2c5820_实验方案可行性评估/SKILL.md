---
name: experiment-feasibility-review
description: Assess whether a given experiment protocol is feasible against organizer-provided local inventory and contracts - per-item equipment/reagent/time/safety/budget/ethics verdicts (feasible/risk/blocker) with evidence locators, shortfall arithmetic, and an overall feasibility score. Use when the task is 实验方案可行性评估 / reviewing a protocol's executability (kind feasibility).
---

# Experiment protocol feasibility assessment (实验方案可行性评估)

A source-bound Skill for the Bohrium weekly contest (experiment track). The agent
reads the ACTUAL organizer-provided local material under /input (the protocol to
review, equipment/reagent inventory, price/booking contracts, time windows, safety
and ethics constraints), fills a structured Feasibility IR, and a deterministic
stdlib engine validates it, recomputes per-item verdicts from inventory arithmetic,
and emits editable artifacts + provenance + an honest result.json. No pre-baked
answers; every verdict traces to a real input file and paragraph.

## When to use
Review a concrete protocol item-by-item across seven constraint classes (hypothesis &
variables, controls, equipment & materials, time & cost, parameter ranges, risks &
anomalies, ethics & safety) and give an executable conclusion. Critically: do NOT
treat "the protocol does not mention X" as "the protocol satisfies X" — absence is
not_reported, not a pass. Trigger: workorder kind `feasibility` (实验方案可行性评估).

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve every key).
- /input/task.md — the protocol under review and the review scope.
- Actual material: the protocol text, equipment inventory (model/capacity/availability),
  reagent stock (quantity/spec), price/booking contracts, time windows, safety/ethics
  approvals. Register the real files; trust content over labels. Prospective contracts
  are NOT claimed actual labs/vendor quotes/safety approvals.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] + documents[]; register the protocol in protocols[].
2. Read the protocol; extract each requirement as an item {category, requirement, needed quantity/hours/cost, evidence}. Read the inventory; register each entry {name, category, available, available_qty/capacity, cost, approved, evidence}. Link items to inventory via inventory_id (or matching name).
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir feasibility_ir.json --input /input --out /app/output`
   → validate_ir → build (verdict recomputation, shortfall/utilization arithmetic,
   feasibility score) → feasibility.json + report.md + provenance.json → result.json.
4. Honest status: success when every item is assessed with traceable evidence (finding
   blockers is a valid completed review); partial when items lack inventory evidence
   (not_reported + human_confirm), quotes fail verification, or the IR has errors;
   failed on build error. Save partial early.

## Feasibility IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto>
kind: "feasibility"
sources: [{id, path}]
documents: [{id, source_id, title, paragraphs?: [{id, text}]}]
protocols: [{id, source_id, version?, title}]
protocol_id: <the protocol under review>
items: [{item_id, category: equipment|reagent|time|safety|budget|ethics|personnel|other,
         requirement, name?, inventory_id?,
         needed_qty? / needed_hours? / needed_cost?,
         available_qty? / window_hours? / budget_cap?,
         available?: bool, approved?: bool, spec_gap?, verdict?: <agent proposal>,
         evidence}]
inventory: [{id, name, category, available?: bool, available_qty?/capacity?,
             cost?, lead_time?, approved?: bool, evidence}]
confirmations: [{item, reason, handling: human_confirm}]
provenance: {pipeline, changes: []}
uncertainty: [{item, reason, impact?, handling}]
```
verdict vocabulary (engine-computed): feasible | risk | blocker | not_reported.
Evidence locator = {source_id, paragraph_id?, quote?, page?, table?, field?}.

## Domain rules — feasibility (rules/rules_feasibility.md)
1. One item per concrete requirement quoted from the protocol; cite the protocol paragraph. Never invent requirements the protocol does not state.
2. Link each item to actual inventory evidence. No inventory evidence → not_reported + human_confirm (NOT feasible). "Not mentioned" ≠ "satisfied".
3. Engine verdict rules: explicitly unavailable → blocker; need > available → blocker (shortfall computed); utilization > 90% → risk; spec_gap → risk; safety/ethics without confirmed approval → risk + human_confirm; availability reported with no quantity arithmetic → feasible.
4. Time: needed_hours vs window_hours. Budget: needed_cost vs budget_cap. Reagent/equipment: needed_qty vs available_qty/capacity. Units must match; convert explicitly and record the conversion.
5. Overall score = (n_feasible + 0.5*n_risk)/n_items; overall label blocked/feasible/conditional/high_risk/insufficient_evidence. Report blockers and risks separately.
6. If the agent proposes a verdict that differs from the engine recomputation, both are kept (agent_verdict) and a warning is raised — the arithmetic wins, the agent explains.
7. Safety/ethics/equipment-availability uncertainties go to confirmations[]; never write an unconfirmed approval as a fact.

## Scripts & dependencies
assemble.py (CLI), experiment_engine.py (verdict arithmetic + score + provenance +
report), w4kit.py (case load / source check / safe_eval / result.json). Python 3.10+
standard library only. See requirements.txt.

## Outputs (/app/output)
feasibility.json (items with verdict/reason/detail/matched_inventory + inventory +
counts + feasibility_score + overall + blockers/risks/not_reported + confirmations),
report.md (editable review table), provenance.json, validation.json, result.json
(preserves output_contract + case_id + status + sources + uncertainty + change_log + limits).

## Error handling (docs/ERROR_HANDLING.md)
No inventory evidence → not_reported + human_confirm; need>available → blocker with
shortfall; near capacity → risk; spec mismatch → risk; unconfirmed safety/ethics →
risk + human_confirm; conflicting availability → source_conflict; unreadable file →
file_not_found; quote mismatch → locator_issues. Never fabricate availability.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/feasibility/`: input/ + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/feasibility/ir.json --input examples/feasibility/input --out /tmp/demo`
The example includes a blocker (reagent shortfall), a risk (near-capacity time window)
and a not_reported item (no inventory evidence) to demonstrate honest verdicts.

## Self-check
- [ ] every used input file registered; every item quotes the protocol requirement
- [ ] every item linked to inventory evidence or marked not_reported (never assumed feasible)
- [ ] quantity/time/budget arithmetic correct and unit-consistent; shortfalls computed
- [ ] safety/ethics approvals confirmed or flagged human_confirm
- [ ] verdicts engine-recomputed; agent overrides surfaced with reason
- [ ] overall score + blockers/risks/not_reported reported separately
- [ ] result.json honest; output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL, line 2 = SKILL.md.
Published under week4/grok in github.com/hehekevin/boerproduct; opens without login.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared answers.
Evaluator installs the Skill under /skills/weekly-skill and runs the official DeepSeek
Harness on each fixed original case (/input/case.json + task.md → /app/output/result.json
preserving output_contract + case_id). Budget: 64 requests, 900 s — save honest partial early.