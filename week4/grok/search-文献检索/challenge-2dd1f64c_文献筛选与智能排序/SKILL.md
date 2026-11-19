---
name: search-screen-rank
description: Screen a large candidate paper set against a checkable include/exclude criteria system (keep/maybe/exclude + reason codes + evidence snippets), then rank with explainable weighted features and deterministic tie-breaks; merge preprint/published versions without double counting and route ambiguous records to a human review queue. Use when the task is 文献筛选与智能排序 / relevance screening and priority ranking of retrieved candidates.
---

# Literature screening & explainable ranking (文献筛选与智能排序)

A source-bound Skill for the Bohrium weekly research-efficiency contest (search
track, `challenge-2dd1f64c`). The agent reads the ACTUAL organizer-provided local
materials under /input (scientific documents, real Crossref/EuropePMC/publisher
responses, retained reference graph, organizer-local import states, facsimiles —
whatever the case ships), fills a structured IR, and a deterministic stdlib
engine validates it, performs the real computation (criteria-based screening + version groups + explainable ranking), and emits
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
source locator.

## When to use
The workorder provides a candidate set and asks which papers are relevant, why each was kept/excluded, and a stable explainable priority order that puts key papers where users actually look. NOT for database access, full-text reading or formal systematic-review inclusion/exclusion workflow (use search-systematic-screening for that).

## Focus (rubric)
Actual effect 40 (completion/correctness/completeness/verifiability: real
records, accurate metadata, Precision@k / nDCG@k / Recall@k where applicable,
replayable evidence), usage gain 25 vs the no-Skill baseline, innovation gain 15
(checkable label system with reason codes, per-feature score contributions, version-group merging, explicit human queue instead of fake scores), reliable experience 10 (stable triggering, empty-result /
conflict / missing-metadata / permission handling), ecosystem contribution 10
(docs + reusable engine/rules/example). GitHub public link: +5 bonus.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete research question, constraints, evidence scope.
- The actual material files. Read and register the real files; trust file
  content over filename/database labels. Finite local snapshot only.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] {id, path, type, name}.
2. Read the material; fill the IR per `rules/rules_screen_rank.md` and the schema below.
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
kind: "screen_rank"
sources: [{id, path, type?, name?}]   # every used input file; unique ids;
                                        # EVERY source_id anywhere must be registered
queries: [{id, query_string, ...}]    # ORIGINAL query strings preserved
records: [{id, title|doi, source_id, query_id?, snippet?, status?,
            authors?, year?, journal?, doi?, field_sources?, ...}]
criteria: [{id, type: include|exclude, text}]   # REQUIRED, checkable
records[] extras: label: keep|maybe|exclude (REQUIRED),
  reason_code: <criteria id> (REQUIRED), evidence: [locator] (keep/exclude),
  features: {0..1} (else unscored -> human queue),
  version_of?: <record id> (preprint -> published link),
  graded_relevance?: 0..3 (agent-judged)
ranking: {weights?, k?}
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

## Domain rules — screen_rank (full text: rules/rules_screen_rank.md)
1. Define criteria[] FIRST: each with id, type include/exclude and a decidable text (population, method, design, time range). Every record's reason_code must reference a criterion — 'not relevant' alone is not auditable.
2. Label every record keep / maybe / exclude. keep/exclude need an evidence locator (quote from the actual abstract/response). Abstract insufficient -> maybe + reason code for the human queue, never a confident exclude.
3. Score with features in 0..1: question_match, method_match, population_match, evidence_quality, recency, facet_coverage (weights overridable via ranking.weights; renormalized over present features). A record without features is NOT scored — it goes to human_review_queue, not to a fabricated position.
4. Preprint vs published: link with version_of (must reference a known record id). The engine builds version groups so the same study is not double counted; keep both records with their own sources. Different DOIs/years are fine — the explicit link carries the identity.
5. Ties and mixed-topic sets: the engine orders by tier (keep<maybe<exclude), then score desc, then year desc, then id asc — deterministic and reproducible. Do not hand-sort.
6. Conflicts (annotation disagreement, same study multiple reports): surface them, merge via version_of/dedup or escalate to maybe; never average away a substantive dispute.
7. graded_relevance labels (0..3) are YOUR judgments for metrics@k; the engine marks them agent_judged_not_ground_truth. Missing metadata stays not_reported.

## Scripts & dependencies
assemble.py (CLI), search_engine.py (validate_ir + build: criteria-based screening + version groups + explainable ranking),
w4kit.py (case load / source check / dedup / result.json). Python 3.10+
standard library only — no third-party packages, no network. See requirements.txt.

## Outputs (/app/output)
candidate_set.json — criteria, label_counts, reason_code_counts, dedup clusters, version_groups (preprint/published linked), ranked_records with score + per-feature contributions, weights, tie_break_rule, human_review_queue, metrics_at_k (agent-judged).
Plus report.md (editable, locators inline), records.csv (editable flat list),
provenance.json (record/edge/view -> source map + sources_used/unused),
search_ir.json (replay), validation.json, result.json (preserves every
output_contract key + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Ambiguous abstract -> maybe + human queue (not fake score/exclude); preprint+published -> version group, both kept; missing DOI -> missing_fields, fuzzy title match only; label without reason code -> validation error; disagreement -> surfaced, not averaged.
Never fabricate; never silent-skip; never claim live/global coverage.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/screen_rank/`: tiny fake input/ + ir.json accepted by the engine. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/screen_rank/ir.json --input examples/screen_rank/input --out /tmp/demo`
The demo includes a preprint/published pair (version_of) and an ambiguous no-DOI record routed to the human queue. Real cases are supplied only at evaluation.

## Self-check
- [ ] criteria decidable; every record label + reason_code + evidence (or maybe)
- [ ] features 0..1 with rationale; unscored records in human queue, not faked
- [ ] preprint/published linked via version_of; dedup provenance kept
- [ ] tie-break deterministic; metrics labelled agent-judged; gaps explicit
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
