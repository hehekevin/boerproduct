---
name: search-quality-appraisal
description: Appraise provided papers dimension-by-dimension on an explicit scale: each judgment (yes/partial/no/insufficient_evidence) carries a sentence/table-level evidence locator in the actual document, a grade and a rationale; unreported items are ABSTAINED (grade unclear), never filled in; overall grade aggregates worst-domain with critical-dimension abstention forcing unclear. Use when the task is 文献研究质量评价 / risk-of-bias or reporting-quality assessment with verifiable evidence positions.
---

# Study quality & risk-of-bias appraisal (文献研究质量评价)

A source-bound Skill for the Bohrium weekly research-efficiency contest (search
track, `challenge-bace1c46`). The agent reads the ACTUAL organizer-provided local
materials under /input (scientific documents, real Crossref/EuropePMC/publisher
responses, retained reference graph, organizer-local import states, facsimiles —
whatever the case ships), fills a structured IR, and a deterministic stdlib
engine validates it, performs the real computation (dimension-level appraisal + evidence locators + honest aggregation), and emits
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
source locator.

## When to use
The workorder provides actual papers/documents and asks whether design, sampling, measurement, statistics and reporting support the conclusions, with every judgment traceable to a located passage. NOT a substitute for peer review, fact verification or clinical/policy decisions.

## Focus (rubric)
Actual effect 40 (completion/correctness/completeness/verifiability: real
records, accurate metadata, Precision@k / nDCG@k / Recall@k where applicable,
replayable evidence), usage gain 25 vs the no-Skill baseline, innovation gain 15
(dimension->judgment->locator->grade chain, abstain-instead-of-fabricate policy, critical-dimension abstention forcing overall unclear, applicability by study type), reliable experience 10 (stable triggering, empty-result /
conflict / missing-metadata / permission handling), ecosystem contribution 10
(docs + reusable engine/rules/example). GitHub public link: +5 bonus.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete research question, constraints, evidence scope.
- The actual material files. Read and register the real files; trust file
  content over filename/database labels. Finite local snapshot only.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] {id, path, type, name}.
2. Read the material; fill the IR per `rules/rules_quality_appraisal.md` and the schema below.
   Keep original queries, raw snippets, field-level sources; judge relevance /
   decisions / grades yourself and attach evidence locators.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir search_ir.json --input /input --out /app/output`
   -> validate_ir -> build -> appraisal.json + report.md + records.csv +
   provenance.json + search_ir.json -> result.json.
4. Honest status: success only when validation is clean and no unresolved
   human_confirm gaps; partial on validation errors, build errors or open gaps;
   failed on unreadable IR / no artifacts. Save partial early; never fabricate.

## IR schema (agent fills from ACTUAL material; enforced by validate_ir)
```
ir_version: "1.0"            # required literal
case_id: <auto from /input/case.json>
kind: "quality_appraisal"
sources: [{id, path, type?, name?}]   # every used input file; unique ids;
                                        # EVERY source_id anywhere must be registered
queries: [{id, query_string, ...}]    # ORIGINAL query strings preserved
records: [{id, title|doi, source_id, query_id?, snippet?, status?,
            authors?, year?, journal?, doi?, field_sources?, ...}]
appraisal_tool: {name, aggregation?: worst_domain,
  critical_dimensions?: [dim_id],
  dimensions: [{id, name, applies_to?: [study_type]}]}   # REQUIRED scale
records[] extras: study_type? (rct/cohort/...),
  dimensions: [{dimension_id, judgment: yes|partial|no|insufficient_evidence,
    grade?: low|some_concerns|high|unclear, rationale?,
    evidence: [{source_id, paragraph_id?|page?|table?, quote?}]}]
# non-abstain judgment REQUIRES evidence + grade;
# abstain MUST NOT carry a confident grade
ranking: {weights?: {question_match, method_match, population_match,
                     evidence_quality, recency, facet_coverage}, k?}
provenance: {pipeline, changes?}
uncertainty: [{item, reason, impact?, handling}]   # human_confirm => partial
```
record.status vocabulary: reported | not_reported | source_conflict |
extraction_failed | inferred | insufficient_evidence.
Evidence locator = {source_id, paragraph_id?, page?, quote?, table?, field?}.
Features are 0..1 floats; score = weighted sum (weights renormalized over the
features present); ties broken by tier -> score desc -> year desc -> id asc.
Records without features are NOT scored — they go to the human review queue.

## Domain rules — quality_appraisal (full text: rules/rules_quality_appraisal.md)
1. Define the scale FIRST (appraisal_tool.dimensions): design/allocation, sampling & power, measurement/outcomes, statistics, reporting completeness — each with what evidence decides it and when it is not assessable. Restrict applicability via applies_to + record study_type; judge every APPLICABLE dimension (missing ones are flagged, not fabricated).
2. Every judgment yes/partial/no needs an evidence locator at sentence or table level in the ACTUAL document: paragraph_id/page/table + the original quote. A grade without a locator is not reviewable; a locator without a real quote is not evidence.
3. If the document does not report what the dimension needs, judgment = insufficient_evidence (abstain) with grade unclear/not_assessable or none — NEVER a plausible-looking guess. Abstaining on a critical dimension forces overall unclear.
4. Grades: low / some_concerns / high / unclear per dimension; overall = worst_domain over judged dimensions (engine), with the abstain policy stated. Distinguish 'clearly present', 'possibly present', 'no sign' and 'insufficient evidence' for bias domains.
5. Read the actual methods/results, not the abstract's self-praise: 'reasonable design, adequate sample' without locators is exactly the failure mode this skill prevents.
6. Applicability mismatches (e.g. an RCT-only dimension on a cohort) are recorded as not applicable with basis, not silently skipped.
7. Output is appraisal assistance for a human reviewer — not peer review, not a clinical recommendation; a second person must be able to re-derive every grade from the locators.

## Scripts & dependencies
assemble.py (CLI), search_engine.py (validate_ir + build: dimension-level appraisal + evidence locators + honest aggregation),
w4kit.py (case load / source check / dedup / result.json). Python 3.10+
standard library only — no third-party packages, no network. See requirements.txt.

## Outputs (/app/output)
appraisal.json — appraisal_tool (scale + aggregation + critical dimensions), per-paper dimensions (judgment, grade, rationale, evidence + locator strings, abstain flag), overall_grade + overall_reason, n_abstain + abstained_dimensions, grade_scale, abstain_policy, scope_note.
Plus report.md (editable, locators inline), records.csv (editable flat list),
provenance.json (record/edge/view -> source map + sources_used/unused),
search_ir.json (replay), validation.json, result.json (preserves every
output_contract key + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Unreported item -> abstain (insufficient_evidence, grade unclear), never guessed; judgment without locator -> validation error; abstain with confident grade -> validation error; critical abstain -> overall unclear; non-applicable dimension -> recorded with basis.
Never fabricate; never silent-skip; never claim live/global coverage.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/quality_appraisal/`: tiny fake input/ + ir.json accepted by the engine. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/quality_appraisal/ir.json --input examples/quality_appraisal/input --out /tmp/demo`
The demo abstains on P2 statistics (adjustment not reported) to show the insufficient_evidence policy and worst-domain aggregation. Real cases are supplied only at evaluation.

## Self-check
- [ ] scale defined with applicability; every applicable dimension judged or flagged
- [ ] every non-abstain judgment has sentence/table locator + quote + grade + rationale
- [ ] unreported -> abstain (unclear), never fabricated; critical abstain -> overall unclear
- [ ] aggregation rule stated; second reviewer can re-derive grades from locators
- [ ] result.json honest (status/sources/uncertainty/change_log); output_contract preserved
- [ ] no live-coverage / latest-publication / fabricated-data claims anywhere

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL of this
work, line 2 = relative entry file (SKILL.md). Published under week4/grok in
github.com/hehekevin/boerproduct; opens without login.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared
answers or formal test outputs. Evaluator installs the Skill under
/skills/weekly-skill and runs the official DeepSeek Harness on each fixed
original case (/input/case.json + task.md -> /app/output/result.json preserving
output_contract + case_id). Work under /app/work; editable artifacts under
/app/output; honest partial identifies its limits. Budget: 64 model requests,
900s, 16384 tokens/response. Resources: <=50 UTF-8 text files, <=500KB each,
<=2MB total, no symlinks/binaries.
