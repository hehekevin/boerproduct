---
name: review-quality-review
description: Overall manuscript quality audit (论文质量审查) over organizer-provided local material. Scores novelty/rigor/clarity/significance with evidence locators, covers the six check categories (fact_check, citation_support, methods_design, stats_reporting, argument_chain, academic_norms), and delivers an itemized, locator-bound findings list with severity, strengths/weaknesses and an overall recommendation. Use when the task is to review a manuscript's overall quality, structure completeness, factual consistency or publishability and hand over a checkable problem list.
---

# Manuscript quality review (论文质量审查)

A source-bound Skill for the Bohrium weekly contest (REVIEW track, contest
bohr-product period 4). The agent reads the ACTUAL organizer-provided local
material under /input, fills a structured Review IR, and a deterministic stdlib
engine validates it, verifies every evidence quote against the real file text,
computes coverage/scores, and emits editable artifacts + provenance + an honest
result.json. No pre-baked answers; every judgment traces to a real paragraph.

## When to use
The workorder asks for an overall quality / structure / factual-consistency /
publishability review of a manuscript (kind `quality_review`). NOT for language
polishing, translation, plagiarism text-matching, or typesetting.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve every key).
- /input/task.md — the concrete task rules for this case.
- The actual manuscript file(s) + any provided references/data/notes.
Read and register the real files; trust file content over filename labels.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] + documents[]
   (role: manuscript/reference/data/guideline/other); set manuscript_id.
2. Read the manuscript fully; fill the IR per `rules/rules_quality_review.md`:
   dimension_scores[], checklist[] (all six categories), findings[],
   overall_recommendation, uncertainty[].
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir review_ir.json --input /input --out /app/output`
   → validate_ir → quote verification + coverage computation → review.json +
   checklist.csv + provenance.json + report.md → result.json.
4. Honest status: success only when every category is checked or justified
   not_applicable and all locators verify; partial when insufficient_evidence,
   uncheckable categories, unreadable material, locator issues or uncertainty
   exist; failed on IR/build error. Confirmed major findings do NOT downgrade
   status — finding real problems is a successful review.

## Review IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto from /input/case.json>
kind: "quality_review"
sources: [{id, path, role?}]            # every actual input file used
documents: [{document_id, source_id, role, title, content_path?, paragraphs?}]
manuscript_id: <document_id under review>
dimension_scores: [{dimension, score, scale, basis, evidence[]}]
checklist: [{category, status: checked|not_applicable|uncheckable, reason?, note?, evidence?}]
findings: [{id, dimension, severity: major|minor|suggestion,
            status: confirmed|suspected|insufficient_evidence|not_applicable,
            polarity: issue|strength, verdict, evidence[], recommendation, reason?}]
overall_recommendation: {decision: accept|minor_revision|major_revision|reject|undetermined,
                         rationale, reason?, evidence[]}
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes[]}
```
Evidence locator = {source_id, document_id?, paragraph_id?, quote?, page?, table?, field?}.
paragraph_id = pN from blank-line-split paragraphs of the real text file (the
engine recomputes the same split; "Page N" marker lines set the page number).
Alternatively transcribe actual paragraphs into documents[].paragraphs.

## Domain rules — quality_review
Full rules: `rules/rules_quality_review.md`. Key points:
1. Itemized findings, never a prose essay. Each finding: exact locator + quote,
   severity matched to defect nature (major = affects main conclusion/reproducibility;
   minor = fixable reporting gap; suggestion = style/optional), actionable fix.
2. Cover ALL six categories; a category with no issues is `checked` with zero
   findings; irrelevant → not_applicable WITH reason; material missing →
   uncheckable WITH reason (never silently skip).
3. Distinguish factual error (confirmed) vs evidence gap (insufficient_evidence
   + human_confirm) vs norm issue vs suggestion. Suppress false positives: do
   not flag discipline conventions, journal format differences, or deliberate
   author choices as defects.
4. Scores need a basis + evidence; missing information is not_reported, never guessed.
5. Recommendation must follow from the findings; undetermined requires a reason.

## Scripts & dependencies
assemble.py (CLI), review_engine.py (validation + quote verification + coverage
+ report), w4kit.py (case load / source check / stats / result.json). Python
3.10+ standard library only. See requirements.txt.

## Outputs (/app/output)
review.json (scores + checklist coverage + findings + recommendation),
checklist.csv (handoff problem list), report.md, provenance.json,
validation.json, result.json (preserves output_contract + case_id + status +
sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Unreadable/binary manuscript → content_status recorded, affected checks
insufficient_evidence + human_confirm; missing references → citation_support
not_applicable/uncheckable with reason; quote not found in real text →
locator_status quote_mismatch + human_confirm (never silently kept); IR errors
→ honest partial result.json with validation.json. Never fabricate; never
silent-skip.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/quality_review/`: input/ + ir.json. Run:
`python assemble.py --ir examples/quality_review/ir.json --input examples/quality_review/input --out /tmp/demo`
The example deliberately includes an unverifiable novelty claim to demonstrate
honest partial status. Real cases are supplied only at evaluation.

## Self-check
- [ ] every used input file registered in sources[]; manuscript_id set
- [ ] all six checklist categories present with justified status
- [ ] every confirmed/suspected finding has a real paragraph locator + quote
- [ ] quotes verify against actual text (n_locator_issues = 0 or flagged)
- [ ] severity matches defect nature; false positives suppressed
- [ ] scores carry basis + evidence; recommendation follows from findings
- [ ] result.json honest (status/sources/uncertainty/change_log); output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL of this
work (filled by git_sync; currently PENDING_GIT_SYNC), line 2 = relative entry
file (SKILL.md). Must open without login.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared
answers or formal test outputs. Evaluator installs the Skill under
/skills/weekly-skill and runs the official DeepSeek Harness on each fixed
original case (/input/case.json + task.md → /app/output/result.json preserving
output_contract + case_id). Work under /app/work; editable artifacts under
/app/output; partial results identify their limits.