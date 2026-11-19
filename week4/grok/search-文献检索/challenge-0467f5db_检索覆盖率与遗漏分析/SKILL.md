---
name: search-coverage-analysis
description: Measure recall of retrieved results against an INDEPENDENT frozen known-item reference set (never derived from the results), compute per-reference hit status (DOI exact then fuzzy title+year), attribute every miss to a specific query/field/source category, run supplementary rounds and report real marginal gain plus residual misses. Use when the task is 检索覆盖率与遗漏分析 / coverage measurement, known-item recall or miss attribution.
---

# Search coverage & miss analysis (检索覆盖率与遗漏分析)

A source-bound Skill for the Bohrium weekly research-efficiency contest (search
track, `challenge-0467f5db`). The agent reads the ACTUAL organizer-provided local
materials under /input (scientific documents, real Crossref/EuropePMC/publisher
responses, retained reference graph, organizer-local import states, facsimiles —
whatever the case ships), fills a structured IR, and a deterministic stdlib
engine validates it, performs the real computation (independent recall + miss attribution + supplementary-round gain), and emits
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
source locator.

## When to use
The workorder provides a known-item list (from reviews/guidelines/expert lists) and retrieved results, and asks which known papers were missed, why (specific query/field/window/source), and whether supplementary search actually reduced misses. NOT for formal systematic-review screening or database access.

## Focus (rubric)
Actual effect 40 (completion/correctness/completeness/verifiability: real
records, accurate metadata, Precision@k / nDCG@k / Recall@k where applicable,
replayable evidence), usage gain 25 vs the no-Skill baseline, innovation gain 15
(independent denominator discipline, per-miss actionable attribution taxonomy, marginal-gain accounting for supplementary rounds, residual-gap honesty), reliable experience 10 (stable triggering, empty-result /
conflict / missing-metadata / permission handling), ecosystem contribution 10
(docs + reusable engine/rules/example). GitHub public link: +5 bonus.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete research question, constraints, evidence scope.
- The actual material files. Read and register the real files; trust file
  content over filename/database labels. Finite local snapshot only.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] {id, path, type, name}.
2. Read the material; fill the IR per `rules/rules_coverage_analysis.md` and the schema below.
   Keep original queries, raw snippets, field-level sources; judge relevance /
   decisions / grades yourself and attach evidence locators.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir search_ir.json --input /input --out /app/output`
   -> validate_ir -> build -> coverage_analysis.json + report.md + records.csv +
   provenance.json + search_ir.json -> result.json.
4. Honest status: success only when validation is clean and no unresolved
   human_confirm gaps; partial on validation errors, build errors or open gaps;
   failed on unreadable IR / no artifacts. Save partial early; never fabricate.

## IR schema (agent fills from ACTUAL material; enforced by validate_ir)
```
ir_version: "1.0"            # required literal
case_id: <auto from /input/case.json>
kind: "coverage_analysis"
sources: [{id, path, type?, name?}]   # every used input file; unique ids;
                                        # EVERY source_id anywhere must be registered
queries: [{id, query_string, ...}]    # ORIGINAL query strings preserved
records: [{id, title|doi, source_id, query_id?, snippet?, status?,
            authors?, year?, journal?, doi?, field_sources?, ...}]
reference_set: [{id, title, doi?, year?, source_id, inclusion_reason?,
                 unusable?}]              # REQUIRED; independent frozen denominator
records[]: the retrieved results (source_id + snippet + query_id)
miss_attributions: [{reference_id, category, explanation}]
  category: term_not_covered | field_too_narrow | time_window |
            source_not_indexed | identifier_anomaly | other
supplementary_rounds: [{id, query_ids: [...], new_record_ids: [...], basis?}]
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

## Domain rules — coverage_analysis (full text: rules/rules_coverage_analysis.md)
1. Build the reference set from the PROVIDED independent sources (review reference lists, guidelines, expert lists) — never from your own results ('defining the denominator by the numerator' fakes ~100% coverage). Freeze it: each item gets id + title + source_id + inclusion_reason; verify identifiers.
2. Mark unusable items explicitly (unusable: 'retracted' / 'no full text' / ...) with the source notice; they are excluded from the usable denominator but stay listed — never silently delete a known item.
3. Hit matching is computed: normalized DOI exact first, then fuzzy title (>=0.85 token overlap) with year compatibility (±1). Every reference gets a hit row with match_method; 'not found' is a MISS to attribute, not 'not relevant'.
4. Attribute EVERY miss to a category with a specific explanation naming the query string, field restriction, time window or source that caused it ('database coverage insufficient' alone is not actionable). Unattributed misses are listed as human_confirm.
5. Supplementary rounds must be designed from the miss categories (new terms/fields/sources), registered as queries, and linked via supplementary_rounds.query_ids + new_record_ids. The engine computes new reference hits and recall_after; a round with zero new hits is a zero_stop_candidate — report it honestly, do not claim misses dropped.
6. Report residual misses after all rounds with reasons; state when to stop supplementing (marginal gain zero / source not indexed / escalation).
7. Spot-check hit judgments (identifier anomalies, same-title-different-work) and record agreement; coverage numbers always carry the usable-denominator count.

## Scripts & dependencies
assemble.py (CLI), search_engine.py (validate_ir + build: independent recall + miss attribution + supplementary-round gain),
w4kit.py (case load / source check / dedup / result.json). Python 3.10+
standard library only — no third-party packages, no network. See requirements.txt.

## Outputs (/app/output)
coverage_analysis.json — reference_set (with unusable flags), n_reference_total/usable, denominator_note (independent), hit_table per reference (hit, method, matched records), recall, misses with attribution, miss_category_counts, supplementary_rounds (new hits, recall_after, marginal_gain), residual_misses, unattributed_misses, retrieved_records.
Plus report.md (editable, locators inline), records.csv (editable flat list),
provenance.json (record/edge/view -> source map + sources_used/unused),
search_ir.json (replay), validation.json, result.json (preserves every
output_contract key + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Miss without attribution -> unattributed + human_confirm; retracted/ungettable reference -> unusable flag (kept listed); zero-gain round -> zero_stop_candidate, no fake improvement; identifier anomaly -> identifier_anomaly category with evidence.
Never fabricate; never silent-skip; never claim live/global coverage.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/coverage_analysis/`: tiny fake input/ + ir.json accepted by the engine. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/coverage_analysis/ir.json --input examples/coverage_analysis/input --out /tmp/demo`
The demo includes a retracted (unusable) reference and a documented supplementary round. Note: base recall is computed over the final record set, so the round shows honest zero marginal gain (the no-DOI item was already recovered by Q2). Real cases are supplied only at evaluation.

## Self-check
- [ ] reference set independent + frozen; every item source_id + inclusion_reason; unusable flagged
- [ ] hit table complete with match_method; recall uses usable denominator
- [ ] every miss attributed to specific query/field/window/source; residual explained
- [ ] supplementary rounds show real new hits / zero-gain honesty
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
