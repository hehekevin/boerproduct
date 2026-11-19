---
name: search-query-planning
description: Plan and execute multi-round academic literature searches over organizer-provided local database responses: decompose the research question into facets, expand terms/synonyms, keep original queries and raw snippets, dedup candidates with provenance, and rank them with per-feature rationale. Use when the task is 学术文献检索 / finding relevant papers for a research topic with traceable candidate sets, ranking rationale and gap notes.
---

# Academic literature search & query planning (学术文献检索)

A source-bound Skill for the Bohrium weekly research-efficiency contest (search
track, `challenge-a2909a72`). The agent reads the ACTUAL organizer-provided local
materials under /input (scientific documents, real Crossref/EuropePMC/publisher
responses, retained reference graph, organizer-local import states, facsimiles —
whatever the case ships), fills a structured IR, and a deterministic stdlib
engine validates it, performs the real computation (dedup + facet recall + explainable ranking + metrics@k), and emits
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
source locator.

## When to use
The workorder asks to search and screen literature for a research question (topic/method/population), improve keyword coverage, combine databases, or deliver a traceable ranked candidate set with dedup and omission notes. NOT for full-text reading, translation, writing polish or library file management.

## Focus (rubric)
Actual effect 40 (completion/correctness/completeness/verifiability: real
records, accurate metadata, Precision@k / nDCG@k / Recall@k where applicable,
replayable evidence), usage gain 25 vs the no-Skill baseline, innovation gain 15
(facet-based multi-round query planning, term expansion with recall control, DOI+fuzzy dedup with provenance, explainable weighted ranking), reliable experience 10 (stable triggering, empty-result /
conflict / missing-metadata / permission handling), ecosystem contribution 10
(docs + reusable engine/rules/example). GitHub public link: +5 bonus.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete research question, constraints, evidence scope.
- The actual material files. Read and register the real files; trust file
  content over filename/database labels. Finite local snapshot only.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] {id, path, type, name}.
2. Read the material; fill the IR per `rules/rules_query_planning.md` and the schema below.
   Keep original queries, raw snippets, field-level sources; judge relevance /
   decisions / grades yourself and attach evidence locators.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir search_ir.json --input /input --out /app/output`
   -> validate_ir -> build -> candidate_set.json + report.md + records.csv +
   provenance.json + search_ir.json -> result.json.
4. Honest status: success only when validation is clean and no unresolved
   human_confirm gaps; partial on validation errors, build errors or open gaps;
   failed on unreadable IR / no artifacts. Save partial early; never fabricate.

## IR schema (agent fills from ACTUAL material; enforced by validate_ir)
```
ir_version: "1.0"            # required literal
case_id: <auto from /input/case.json>
kind: "query_planning"
sources: [{id, path, type?, name?}]   # every used input file; unique ids;
                                        # EVERY source_id anywhere must be registered
queries: [{id, query_string, ...}]    # ORIGINAL query strings preserved
records: [{id, title|doi, source_id, query_id?, snippet?, status?,
            authors?, year?, journal?, doi?, field_sources?, ...}]
research_question: {text, scope?, source_id?}   # REQUIRED text
facets: [{id, text, terms: [...], expanded_terms: [...]}]
queries: [{id, query_string, facet_id?, database?, round?, source_id?}]
records[] extras: matched_queries: [query_id, ...], features: {0..1},
  label?: keep|maybe|exclude, graded_relevance?: 0..3 (agent-judged),
  relevance_rationale?
gaps: [{item, reason, handling}]
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

## Domain rules — query_planning (full text: rules/rules_query_planning.md)
1. State the research question and scope (population/intervention/method/time window) from task.md; register it with a source locator. Decompose into facets (object, mechanism, method, outcome, population) — each facet gets terms + expanded_terms (synonyms, abbreviations, hypernyms, cross-language variants).
2. Plan queries per facet and round: keep the ORIGINAL query_string, the database it ran against (as named in the provided export), the round number and facet_id. Round 2+ queries must react to round 1 results (fill gaps, resolve conflicts) — record why.
3. Every candidate record needs id + title or doi + source_id + the raw response snippet. Record matched_queries so each hit's recall path is replayable. Never invent records that no provided response contains.
4. Judge relevance per record against the question: features in 0..1 (question_match, method_match, population_match, evidence_quality, recency, facet_coverage) plus a one-line relevance_rationale. Optionally label keep/maybe/exclude and graded_relevance 0..3 — these are AGENT judgments, never presented as organizer ground truth.
5. Dedup is computed by the engine (DOI exact after URL/doi: normalization, then fuzzy title+year). Do not delete duplicate rows yourself — keep them with their own source/snippet so merge provenance and field conflicts survive.
6. Missing metadata stays missing (missing_fields is computed); mark status not_reported / source_conflict with locators. Empty queries/rounds are recorded as no_hits, never padded with invented papers.
7. Record uncovered facets and gaps explicitly; add uncertainty entries with handling human_confirm for anything needing a researcher decision. The engine reports uncovered_facets and metrics@k from your labels.

## Scripts & dependencies
assemble.py (CLI), search_engine.py (validate_ir + build: dedup + facet recall + explainable ranking + metrics@k),
w4kit.py (case load / source check / dedup / result.json). Python 3.10+
standard library only — no third-party packages, no network. See requirements.txt.

## Outputs (/app/output)
candidate_set.json — research_question, facets with per-facet hit counts, original query plan, dedup clusters, ranked_records with score + per-feature contribution rationale, weights used, metrics_at_k (labelled agent_judged_not_ground_truth), uncovered_facets, gaps.
Plus report.md (editable, locators inline), records.csv (editable flat list),
provenance.json (record/edge/view -> source map + sources_used/unused),
search_ir.json (replay), validation.json, result.json (preserves every
output_contract key + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Empty result -> recorded no_hits round, not invented hits; duplicate exports -> merged with provenance + conflicts kept; missing metadata -> not_reported (never guessed); source disagreement -> source_conflict + both locators; unresolved gap -> uncertainty human_confirm => partial.
Never fabricate; never silent-skip; never claim live/global coverage.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/query_planning/`: tiny fake input/ + ir.json accepted by the engine. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/query_planning/ir.json --input examples/query_planning/input --out /tmp/demo`
The demo includes a duplicate export row (URL-form DOI) to show provenance-preserving dedup. Real cases are supplied only at evaluation.

## Self-check
- [ ] research_question + facets registered; every query keeps original string, database, round, facet
- [ ] every record has source_id + snippet + matched_queries; no invented records
- [ ] features/rationale per ranked record; duplicates kept with provenance (engine merges)
- [ ] uncovered facets / no_hits / missing metadata explicit; metrics labelled agent-judged
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
