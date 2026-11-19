---
name: review-logic-argument-review
description: Manuscript logic and argumentation audit (论文逻辑与论证审查) over organizer-provided local material. Extracts the author's core claims with qualifiers, reconstructs premise-to-conclusion arguments, and checks validity, logical gaps, fallacies (causal-correlation confusion, circular reasoning, hasty generalization, argument from ignorance), claim-evidence alignment and cross-section consistency — every verdict bound to an exact sentence locator with an actionable fix. Use when the task is to audit a manuscript's reasoning chain, internal consistency, or whether conclusions exceed the data.
---

# Logic & argumentation review (论文逻辑与论证审查)

A source-bound Skill for the Bohrium weekly contest (REVIEW track, contest
bohr-product period 4). The agent reads the ACTUAL organizer-provided local
material under /input, fills a structured Review IR, and a deterministic stdlib
engine validates it, verifies every evidence quote against the real file text,
computes argument/consistency summaries, and emits editable artifacts +
provenance + an honest result.json. No pre-baked answers; every reported problem
must point back to a real sentence.

## When to use
The workorder asks to audit argument structure, reasoning gaps, claim-evidence
alignment, or internal consistency (kind `logic_argument_review`). NOT for
language polishing or re-writing the paper; recommendations say what evidence
to add, which sentence to change, or which claim strength to lower.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve every key).
- /input/task.md — the concrete task rules for this case.
- The actual manuscript (+ any provided data/references used as evidence).
Read and register the real files; trust file content over filename labels.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs; register sources[] + documents[]; set manuscript_id.
2. Extract core claims (distinguish author claims / cited views / hypotheticals);
   reconstruct arguments (premises → conclusion) and consistency pairs per
   `rules/rules_logic_argument_review.md`. Fill arguments[],
   consistency_checks[], findings[], uncertainty[].
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir review_ir.json --input /input --out /app/output`
   → validate_ir → quote verification + validity/consistency summaries →
   review.json + checklist.csv + provenance.json + report.md → result.json.
4. Honest status: success when all arguments are auditable and locators verify
   (gaps/fallacies found are review RESULTS); partial when premises are
   not_reported, validity is insufficient_evidence, consistency is unclear, or
   material is unreadable; failed on IR/build error.

## Review IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto>
kind: "logic_argument_review"
sources: [{id, path, role?}]
documents: [{document_id, source_id, role, title, content_path?, paragraphs?}]
manuscript_id: <document_id>
arguments: [{id,
  conclusion: {text, evidence[]},
  premises: [{id, text, status: reported|inferred|not_reported, evidence[]}],
  inference_type: deductive|inductive|causal|correlational|analogical|other,
  validity: valid|gap|fallacy|insufficient_evidence,
  fallacy_type?, gaps?: [...], note?, recommendation?}]
consistency_checks: [{id, a: {text, evidence[]}, b: {text, evidence[]},
                      verdict: consistent|inconsistent|unclear, note?}]
findings: [{id, dimension, severity, status, verdict, evidence[], recommendation}]
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes[]}
```
Evidence locator = {source_id, document_id?, paragraph_id?, quote?, page?, table?, field?}.
paragraph_id = pN from blank-line-split paragraphs of the real text file.
A premise that is an unstated assumption must be status=inferred (with note);
a premise the manuscript never provides is not_reported + human_confirm —
never invent a premise to make an argument look valid.

## Domain rules — logic_argument_review
Full rules: `rules/rules_logic_argument_review.md`. Key points:
1. Claim extraction with qualifiers; separate author assertions from cited
   views and hypotheticals; only audit what is asserted.
2. Validity: does the conclusion follow from the premises AT THE STATED
   STRENGTH? Name the missing link (gap) or the fallacy pattern precisely.
3. Common fallacies: correlation→causation, circular reasoning, hasty
   generalization, argument from ignorance, extrapolation beyond data range,
   moving the goalposts between sections.
4. Cross-section consistency: introduction promises vs methods/results
   delivery; abstract vs body conclusions; figures vs text.
5. Severity: affects main conclusion → major; local repairable jump → minor;
   wording strengthening → suggestion. Fixes must be executable at sentence level.

## Scripts & dependencies
assemble.py (CLI), review_engine.py (validation + quote verification +
summaries), w4kit.py (shared core). Python 3.10+ standard library only.

## Outputs (/app/output)
review.json (arguments + premises + validity + consistency checks + findings),
checklist.csv, report.md, provenance.json, validation.json, result.json
(preserves output_contract + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Missing premise material → not_reported + human_confirm; ambiguous wording →
insufficient_evidence/unclear, not a forced verdict; quote mismatch → flagged;
unreadable manuscript → honest content_status + partial. Never fabricate.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/logic_argument_review/`: input/ + ir.json. Run:
`python assemble.py --ir examples/logic_argument_review/ir.json --input examples/logic_argument_review/input --out /tmp/demo`
The demo shows a causal-overreach gap, an argument-from-ignorance fallacy, a
safety-vs-toxicity inconsistency, and an insufficient-evidence finding.

## Self-check
- [ ] every used input file registered; manuscript_id set
- [ ] every conclusion/premise has a real sentence locator + verified quote
- [ ] unstated assumptions marked inferred; absent premises not_reported
- [ ] fallacy types named precisely; gaps describe the missing link
- [ ] consistency pairs cover abstract/intro/methods/results/discussion as present
- [ ] recommendations executable at sentence level; result.json honest

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL (filled by
git_sync; currently PENDING_GIT_SYNC), line 2 = SKILL.md.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared
answers or formal test outputs. Evaluator installs the Skill under
/skills/weekly-skill and runs the official DeepSeek Harness on each fixed
original case (/input/case.json + task.md → /app/output/result.json preserving
output_contract + case_id). Partial results identify their limits.