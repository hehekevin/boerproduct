---
name: search-systematic-screening
description: Run an auditable systematic-review screening pipeline over provided materials: frozen protocol + criteria with reason codes, dedup with merge basis, dual independent title/abstract screening with evidence snippets, disagreement adjudication, and a PRISMA-style count-closing flow (identified -> duplicates removed -> unique -> included/excluded/pending). Use when the task is 系统性文献检索与纳排筛选 / systematic review search, inclusion-exclusion screening or screening audit.
---

# Systematic search & PRISMA-style screening (系统性文献检索与纳排筛选)

A source-bound Skill for the Bohrium weekly research-efficiency contest (search
track, `challenge-5b90f5e9`). The agent reads the ACTUAL organizer-provided local
materials under /input (scientific documents, real Crossref/EuropePMC/publisher
responses, retained reference graph, organizer-local import states, facsimiles —
whatever the case ships), fills a structured IR, and a deterministic stdlib
engine validates it, performs the real computation (dual screening + adjudication + PRISMA count closure), and emits
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
source locator.

## When to use
The workorder asks for a reproducible systematic screening flow where a reviewer can replay every count and decision: protocol, criteria version, per-record dual judgments, adjudication log, exclusion reason codes. NOT for full-text quality appraisal (use search-quality-appraisal), data extraction or meta-analysis.

## Focus (rubric)
Actual effect 40 (completion/correctness/completeness/verifiability: real
records, accurate metadata, Precision@k / nDCG@k / Recall@k where applicable,
replayable evidence), usage gain 25 vs the no-Skill baseline, innovation gain 15
(dual-reviewer disagreement detection + mandatory adjudication, PRISMA count closure over dedup clusters, code-level exclusion audit), reliable experience 10 (stable triggering, empty-result /
conflict / missing-metadata / permission handling), ecosystem contribution 10
(docs + reusable engine/rules/example). GitHub public link: +5 bonus.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete research question, constraints, evidence scope.
- The actual material files. Read and register the real files; trust file
  content over filename/database labels. Finite local snapshot only.

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_search.py --input /input --out /app/output --work /app/work`
Auto-extracts the IR from the ACTUAL /input materials (registers sources; parses CSV /
Crossref-EuropePMC JSON exports / reference graphs / import states / paper text & PDF
facsimiles), runs the engine to compute real metrics, and writes a complete honest
result.json preserving every output_contract key + case_id. Judgment fields it cannot
verify are abstained (insufficient_evidence) and flagged human_confirm — never fabricated.
THEN, within remaining budget, refine judgment-heavy fields in /app/work/search_ir.json
(miss attributions, screening decisions, grades, term alignments) and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/search_ir.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] {id, path, type, name}.
2. Read the material; fill the IR per `rules/rules_systematic_screening.md` and the schema below.
   Keep original queries, raw snippets, field-level sources; judge relevance /
   decisions / grades yourself and attach evidence locators.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir search_ir.json --input /input --out /app/output`
   -> validate_ir -> build -> screening_audit.json + report.md + records.csv +
   provenance.json + search_ir.json -> result.json.
4. Honest status: success only when validation is clean and no unresolved
   human_confirm gaps; partial on validation errors, build errors or open gaps;
   failed on unreadable IR / no artifacts. Save partial early; never fabricate.

## IR schema (agent fills from ACTUAL material; enforced by validate_ir)
```
ir_version: "1.0"            # required literal
case_id: <auto from /input/case.json>
kind: "systematic_screening"
sources: [{id, path, type?, name?}]   # every used input file; unique ids;
                                        # EVERY source_id anywhere must be registered
queries: [{id, query_string, ...}]    # ORIGINAL query strings preserved
records: [{id, title|doi, source_id, query_id?, snippet?, status?,
            authors?, year?, journal?, doi?, field_sources?, ...}]
protocol: {databases, search_date, criteria_version?, time_range?,
           languages?, query_strings?}
criteria: [{id, text, type?}]            # REQUIRED reason-code system (frozen)
records[] extras: reviewers: [{reviewer, decision: include|exclude|maybe,
    reason_code: <criteria id>, evidence: [locator]}]   # REQUIRED, >=2 distinct
  adjudication?: {decision, reason_code?, rationale, adjudicator?}
    # REQUIRED whenever reviewer decisions disagree
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

## Domain rules — systematic_screening (full text: rules/rules_systematic_screening.md)
1. Record the protocol: databases, fields, time range, language limits, search_date and the ORIGINAL query strings; map each criterion to the protocol. Freeze the criteria version — if criteria change mid-screening, re-screen earlier records and log the change (no silent criteria drift).
2. Dedup is computed (DOI exact + fuzzy title/year); preprint/published copies of the same study merge into one cluster with the merge basis kept. The PRISMA flow counts CLUSTERS, so identified - duplicates = unique and included + excluded + pending = unique must close (engine checks).
3. Every record needs reviewers[] with >=2 distinct reviewers judging INDEPENDENTLY: decision in {include, exclude, maybe} + reason_code from criteria + evidence snippet from the actual title/abstract. 'Not relevant' without a code is not auditable.
4. Disagreement (different decisions) REQUIRES adjudication: decision + rationale (+ adjudicator, reason_code). Never average or majority-vote away a substantive dispute; pending adjudication stays 'maybe' in the human_confirm queue.
5. Boundary cases: abstract-only -> maybe/MAY-style code pending full text; language mismatch -> explicit code; partial population overlap -> adjudicate with rationale. Exclusion reasons are counted per code for the audit.
6. Keep the flow log replayable: input/output counts per stage, who decided, on what evidence. A reviewer asking 'why 1832 -> 47' must get a code-level answer.
7. The engine does not replace researcher judgment: final scientific inclusion stays with the human adjudicator; unresolved items are honest partial.

## Scripts & dependencies
assemble.py (CLI), search_engine.py (validate_ir + build: dual screening + adjudication + PRISMA count closure),
w4kit.py (case load / source check / dedup / result.json). Python 3.10+
standard library only — no third-party packages, no network. See requirements.txt.

## Outputs (/app/output)
screening_audit.json — protocol, criteria, prisma_flow (identification, duplicates_removed, unique_screened, included, excluded, pending_human, count_closure_ok, exclusion_reason_counts), per-record final_decision + decided_by (reviewer_agreement / adjudication / pending_adjudication) + cluster_id, disagreements log, dedup clusters, human_confirm_queue.
Plus report.md (editable, locators inline), records.csv (editable flat list),
provenance.json (record/edge/view -> source map + sources_used/unused),
search_ir.json (replay), validation.json, result.json (preserves every
output_contract key + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Reviewer disagreement without adjudication -> validation error; single reviewer -> flagged warning; count mismatch -> closure_ok false surfaced; criteria drift -> re-screen + change_log; abstract-only -> maybe + human queue.
Never fabricate; never silent-skip; never claim live/global coverage.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/systematic_screening/`: tiny fake input/ + ir.json accepted by the engine. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/systematic_screening/ir.json --input examples/systematic_screening/input --out /tmp/demo`
The demo includes a duplicate export (dedup), an animal-only exclusion and a dual-reviewer disagreement resolved to 'maybe' by adjudication. Real cases are supplied only at evaluation.

## Self-check
- [ ] protocol + frozen criteria recorded; reason codes decidable
- [ ] every record dual-reviewed with code + evidence; disagreements adjudicated with rationale
- [ ] PRISMA counts close over dedup clusters; exclusion reasons counted
- [ ] pending items in human_confirm queue; change_log kept
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
