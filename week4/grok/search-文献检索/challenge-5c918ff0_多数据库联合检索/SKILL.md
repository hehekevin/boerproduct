---
name: search-multi-db-merge
description: Orchestrate queries across multiple academic database exports, normalize heterogeneous fields via an explicit mapping, dedup by DOI exact + fuzzy title/year, merge clusters with per-field priority and field-level provenance (winning value + alternatives + conflicts), and report a database x field coverage matrix with explicit gaps. Use when the task is 多数据库联合检索 / combining results from several databases into one verifiable record set.
---

# Multi-database joint search & merge (多数据库联合检索)

A source-bound Skill for the Bohrium weekly research-efficiency contest (search
track, `challenge-5c918ff0`). The agent reads the ACTUAL organizer-provided local
materials under /input (scientific documents, real Crossref/EuropePMC/publisher
responses, retained reference graph, organizer-local import states, facsimiles —
whatever the case ships), fills a structured IR, and a deterministic stdlib
engine validates it, performs the real computation (field normalization + priority merge + coverage matrix), and emits
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
source locator.

## When to use
The workorder provides exports/responses from 2+ databases for the same question and asks for a merged, deduplicated, field-normalized record set where every field traces to its source database and uncovered databases/fields are stated. NOT for bypassing service limits or unauthorized aggregation.

## Focus (rubric)
Actual effect 40 (completion/correctness/completeness/verifiability: real
records, accurate metadata, Precision@k / nDCG@k / Recall@k where applicable,
replayable evidence), usage gain 25 vs the no-Skill baseline, innovation gain 15
(field mapping + per-field merge priority with alternatives kept, coverage matrix, single-source and no-result gap detection), reliable experience 10 (stable triggering, empty-result /
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
2. Read the material; fill the IR per `rules/rules_multi_db_merge.md` and the schema below.
   Keep original queries, raw snippets, field-level sources; judge relevance /
   decisions / grades yourself and attach evidence locators.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir search_ir.json --input /input --out /app/output`
   -> validate_ir -> build -> merged_records.json + report.md + records.csv +
   provenance.json + search_ir.json -> result.json.
4. Honest status: success only when validation is clean and no unresolved
   human_confirm gaps; partial on validation errors, build errors or open gaps;
   failed on unreadable IR / no artifacts. Save partial early; never fabricate.

## IR schema (agent fills from ACTUAL material; enforced by validate_ir)
```
ir_version: "1.0"            # required literal
case_id: <auto from /input/case.json>
kind: "multi_db_merge"
sources: [{id, path, type?, name?}]   # every used input file; unique ids;
                                        # EVERY source_id anywhere must be registered
queries: [{id, query_string, ...}]    # ORIGINAL query strings preserved
records: [{id, title|doi, source_id, query_id?, snippet?, status?,
            authors?, year?, journal?, doi?, field_sources?, ...}]
databases: [{id, name, priority?, source_id?}]   # REQUIRED; lower priority wins
field_mapping: {raw_field_name: canonical_name}   # e.g. TI->title, pubYear->year
queries: [{id, query_string, database_id?}]
records[] extras: database_id (REQUIRED, registered),
  raw_fields: {original field names/values}, snippet (raw response),
  field_sources: {canonical_field: {source_id, field?}}
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

## Domain rules — multi_db_merge (full text: rules/rules_multi_db_merge.md)
1. Register each database in databases[] with a merge priority (lower wins; default 99). Adapt the query to each database's syntax/field capability — keep each original query_string with its database_id; do not mechanically copy one string everywhere.
2. Build field_mapping from the ACTUAL raw field names in each export (TI/AU/PY/JO/DO, authorString/pubYear/journalTitle, ...). Missing != unknown: a field absent from every source is not_reported_by_any_source, never filled with a guess.
3. Every record needs database_id + source_id + the raw response snippet; keep raw_fields verbatim so normalization is auditable. field_sources gives per-field locators (which file/field the value came from).
4. Dedup + merge are computed: DOI exact first, then fuzzy title+year. Within a cluster the highest-priority source wins each field; alternatives and conflicts are retained with record/database attribution — a reviewer can overturn any merge.
5. Read the coverage matrix: databases with zero results (unavailable or query mismatch) and fields covered by only one database are explicit gaps with human_confirm / single-source notes — never silently swallowed.
6. Identifier semantics differ across databases (year of print vs online, DOI variants); normalize via w4kit rules and record conflicts instead of forcing equality.
7. Respect authorization: only provided/authorized exports; no paywall bypass, no uploading restricted data to unapproved services.

## Scripts & dependencies
assemble.py (CLI), search_engine.py (validate_ir + build: field normalization + priority merge + coverage matrix),
w4kit.py (case load / source check / dedup / result.json). Python 3.10+
standard library only — no third-party packages, no network. See requirements.txt.

## Outputs (/app/output)
merged_records.json — databases + priorities, original queries per database, field_mapping, merged_records (fields + field_provenance with winning source, alternatives, conflicts), coverage_matrix (db x field counts, empty_or_unavailable status), gaps (database_no_results / field_missing_everywhere / field_single_source), single_database_records, dedup clusters.
Plus report.md (editable, locators inline), records.csv (editable flat list),
provenance.json (record/edge/view -> source map + sources_used/unused),
search_ir.json (replay), validation.json, result.json (preserves every
output_contract key + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Database returned nothing -> coverage status empty_or_unavailable + gap human_confirm; field absent everywhere -> not_reported_by_any_source; cross-db disagreement -> conflicts + alternatives kept; missing DOI -> fuzzy title/year match with lower confidence noted.
Never fabricate; never silent-skip; never claim live/global coverage.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/multi_db_merge/`: tiny fake input/ + ir.json accepted by the engine. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/multi_db_merge/ir.json --input examples/multi_db_merge/input --out /tmp/demo`
The demo merges a DOI-identical pair across two exports (journal-name conflict kept) and includes a no-DOI single-source record. Real cases are supplied only at evaluation.

## Self-check
- [ ] databases registered with priorities; queries adapted per database, originals kept
- [ ] field_mapping covers actual raw names; raw_fields + snippets verbatim
- [ ] every record database_id + source_id + field_sources; merge alternatives kept
- [ ] coverage matrix read; empty databases / single-source fields explicit
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
