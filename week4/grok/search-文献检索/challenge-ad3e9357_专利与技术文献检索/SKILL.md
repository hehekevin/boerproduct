---
name: search-patent-search
description: Search a finite authorized patent corpus + scientific comparison literature: normalize publication/application/grant numbers (kept distinct), union families over OBSERVED source-located links only (not exhaustive official families), keep claim versions with locators (scope not assumed equal across versions), default legal status to UNKNOWN unless source-located with as_of, and record green/yellow/red authorization tiers + OCR boundaries. Use when the task is 专利与技术文献检索 / patent family, claim, legal-status or tech-topic intelligence over provided sources.
---

# Patent & technical literature search (专利与技术文献检索)

A source-bound Skill for the Bohrium weekly research-efficiency contest (search
track, `challenge-ad3e9357`). The agent reads the ACTUAL organizer-provided local
materials under /input (scientific documents, real Crossref/EuropePMC/publisher
responses, retained reference graph, organizer-local import states, facsimiles —
whatever the case ships), fills a structured IR, and a deterministic stdlib
engine validates it, performs the real computation (number normalization + observed families + claim versions + UNKNOWN status policy), and emits
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
source locator.

## When to use
The workorder asks what a patent protects, how family members relate, whether it is in force, who else works on the topic, and whether the data may be displayed — answered only from authorized provided sources with number/version/status discipline. NOT for patent drafting, infringement/FTO conclusions, valuation, or paywall bypass.

## Focus (rubric)
Actual effect 40 (completion/correctness/completeness/verifiability: real
records, accurate metadata, Precision@k / nDCG@k / Recall@k where applicable,
replayable evidence), usage gain 25 vs the no-Skill baseline, innovation gain 15
(number-kind normalization, observed-link family union with basis evidence, claim-version locators, honest UNKNOWN legal status, authorization-tier degradation), reliable experience 10 (stable triggering, empty-result /
conflict / missing-metadata / permission handling), ecosystem contribution 10
(docs + reusable engine/rules/example). GitHub public link: +5 bonus.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete research question, constraints, evidence scope.
- The actual material files. Read and register the real files; trust file
  content over filename/database labels. Finite local snapshot only.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] {id, path, type, name}.
2. Read the material; fill the IR per `rules/rules_patent_search.md` and the schema below.
   Keep original queries, raw snippets, field-level sources; judge relevance /
   decisions / grades yourself and attach evidence locators.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir search_ir.json --input /input --out /app/output`
   -> validate_ir -> build -> patent_families.json + report.md + records.csv +
   provenance.json + search_ir.json -> result.json.
4. Honest status: success only when validation is clean and no unresolved
   human_confirm gaps; partial on validation errors, build errors or open gaps;
   failed on unreadable IR / no artifacts. Save partial early; never fabricate.

## IR schema (agent fills from ACTUAL material; enforced by validate_ir)
```
ir_version: "1.0"            # required literal
case_id: <auto from /input/case.json>
kind: "patent_search"
sources: [{id, path, type?, name?}]   # every used input file; unique ids;
                                        # EVERY source_id anywhere must be registered
queries: [{id, query_string, ...}]    # ORIGINAL query strings preserved
records: [{id, title|doi, source_id, query_id?, snippet?, status?,
            authors?, year?, journal?, doi?, field_sources?, ...}]
patents: [{id, title?, numbers: {publication?, application?, grant?},
  source_id, authorization?: green|yellow|red, assignee?, filing_date?,
  publication_date?,
  claims: [{version, locator: {source_id, page?, quote?}, text_snippet?}],
  family_links: [{to: <patent id>, basis, source_id}],   # OBSERVED links only
  legal_status?: {value, source_id, as_of},              # else UNKNOWN
  ocr_boundary?, risk_flags: [...]}]                     # REQUIRED >=1 number
records[]: scientific/technical literature (title|doi + source_id + snippet)
queries: [{id, query_string, database?}]
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

## Domain rules — patent_search (full text: rules/rules_patent_search.md)
1. Use ONLY authorized provided sources (facsimiles, authorized records, provided papers); register each with source_id and an authorization tier green/yellow/red. Red-tier restricted content is never displayed; yellow-tier gets field-level display limits noted. Record database name, version and query date for every conclusion.
2. Numbers: publication != application != grant != priority. Keep each kind separate (numbers.publication/application/grant); the engine normalizes formatting (spaces/dashes/slashes removed, uppercased) but never converts one kind into another. Filing date != priority date != publication date.
3. Families are unioned over OBSERVED links only: each family_link needs a basis (e.g. 'claims priority of X', 'same family listed in record Y') + source_id. Keyword similarity is NOT a family link. The output states explicitly that observed links are not exhaustive official families and claim scopes are not assumed equal.
4. Claims: every version (as-published A1, granted B2, amended...) needs a version label + source locator (page/quote in the actual facsimile). Quote scope per version; OCR boundaries (cut margins, merged WO OCR) are retained as ocr_boundary, not silently repaired.
5. Legal status: UNKNOWN unless a provided source states it with an as_of date (status reported + lag note). A years-old reprint/aggregator page is NOT a register entry. Never present UNKNOWN as 'in force' or 'expired'.
6. Tech-topic search: combine keywords, IPC/CPC classes, assignees and citation clues into explainable queries; keep patent and scientific-literature search logic distinct (records[] for papers, patents[] for patents).
7. Risk-grade every conclusion: missing fields, stale status, unknown family scope, partial coverage -> risk_flags + uncertainty human_confirm. This is intelligence support, not legal advice.

## Scripts & dependencies
assemble.py (CLI), search_engine.py (validate_ir + build: number normalization + observed families + claim versions + UNKNOWN status policy),
w4kit.py (case load / source check / dedup / result.json). Python 3.10+
standard library only — no third-party packages, no network. See requirements.txt.

## Outputs (/app/output)
patent_families.json — patents (numbers_raw + numbers_normalized + kind note, assignee/dates, authorization, family_id, claims with version + locator + scope note, legal_status reported/UNKNOWN + note, ocr_boundary, risk_flags), families (observed basis links, scope note), tech_literature (normalized), queries, legal_status_policy, scope_note.
Plus report.md (editable, locators inline), records.csv (editable flat list),
provenance.json (record/edge/view -> source map + sources_used/unused),
search_ir.json (replay), validation.json, result.json (preserves every
output_contract key + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
No official register -> legal status UNKNOWN + human_confirm (never guessed); restricted source -> red tier, content not displayed; OCR cut -> ocr_boundary retained; keyword-similar patents -> NOT merged into a family; stale reprint status -> not treated as register.
Never fabricate; never silent-skip; never claim live/global coverage.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/patent_search/`: tiny fake input/ + ir.json accepted by the engine. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/patent_search/ir.json --input examples/patent_search/input --out /tmp/demo`
The demo shows an observed priority link (P1->P2), a source-located claim version, an OCR boundary and honest UNKNOWN legal status. Real cases are supplied only at evaluation.

## Self-check
- [ ] only authorized sources used; tiers + query dates recorded; red content not displayed
- [ ] number kinds distinct + normalized; dates not conflated
- [ ] family links observed + basis + source; claim versions located; OCR boundaries kept
- [ ] legal status UNKNOWN unless source+as_of; risk flags + human_confirm on gaps
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
