---
name: search-question-driven
description: Decompose a complex research question into searchable subquestions, plan ordered multi-round queries per subquestion with term expansion, screen EVERY candidate record with evidence locators, map included evidence back to subquestions, and record an explicit stopping decision. Use when the task is 科研问题驱动检索 / question-driven literature search with subquestion coverage and stopping justification.
---

# Research-question-driven search (科研问题驱动检索)

A source-bound Skill for the Bohrium weekly research-efficiency contest (search
track, `challenge-e7598a44`). The agent reads the ACTUAL organizer-provided local
materials under /input (scientific documents, real Crossref/EuropePMC/publisher
responses, retained reference graph, organizer-local import states, facsimiles —
whatever the case ships), fills a structured IR, and a deterministic stdlib
engine validates it, performs the real computation (subquestion evidence map + all-record screening + stopping audit), and emits
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
source locator.

## When to use
The workorder gives a fixed complex research question (object + mechanism + method + time range + evidence requirements) and asks for a decomposed, replayable search with all-record screening and a stopping rationale. NOT for single-paper reading, full-text translation or open-ended QA.

## Focus (rubric)
Actual effect 40 (completion/correctness/completeness/verifiability: real
records, accurate metadata, Precision@k / nDCG@k / Recall@k where applicable,
replayable evidence), usage gain 25 vs the no-Skill baseline, innovation gain 15
(structured question decomposition, subquestion->query->evidence mapping, all-record screening, explicit stopping conditions), reliable experience 10 (stable triggering, empty-result /
conflict / missing-metadata / permission handling), ecosystem contribution 10
(docs + reusable engine/rules/example). GitHub public link: +5 bonus.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete research question, constraints, evidence scope.
- The actual material files. Read and register the real files; trust file
  content over filename/database labels. Finite local snapshot only.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] {id, path, type, name}.
2. Read the material; fill the IR per `rules/rules_question_driven.md` and the schema below.
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
kind: "question_driven"
sources: [{id, path, type?, name?}]   # every used input file; unique ids;
                                        # EVERY source_id anywhere must be registered
queries: [{id, query_string, ...}]    # ORIGINAL query strings preserved
records: [{id, title|doi, source_id, query_id?, snippet?, status?,
            authors?, year?, journal?, doi?, field_sources?, ...}]
questions: [{id, text, source_id?, subquestions: [{id, text}]}]  # REQUIRED
queries: [{id, query_string, subquestion_id?, database?, round?}]
records[] extras: decision: include|exclude|maybe (REQUIRED for every record),
  reason_code?, rationale?, evidence: [locator], subquestion_ids: [sq_id]
stopping: {reason, rounds_run?}
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

## Domain rules — question_driven (full text: rules/rules_question_driven.md)
1. Copy the FIXED research question(s) from task.md into questions[] with a source locator; do not reword the organizer's question into something easier. Decompose each into subquestions covering object, mechanism, method, comparison, time range and evidence requirements.
2. Every query links to a subquestion_id and keeps its original query_string, database and round. Order queries by dependency (prerequisite vs parallel); round 2+ must react to round 1 (fill gaps, verify conflicting evidence).
3. Screen EVERY candidate record: decision in {include, exclude, maybe} with a reason_code and an evidence locator (quote/field from the actual response or document). include/exclude without evidence is flagged; if the material cannot support a decision use maybe or status insufficient_evidence — never guess.
4. Map included records to the subquestions they support (subquestion_ids). The engine computes per-subquestion evidence sufficiency; a subquestion with zero included evidence is an explicit gap, not a silent omission.
5. Term expansion (synonyms, abbreviations, cross-language renders) belongs in the query plan; keep both the original and expanded forms so recall is auditable.
6. Record stopping.reason: evidence sufficient / marginal gain too low / escalated to human. Never stop silently and never claim global recall — the snapshot is finite.
7. Open gaps (e.g. a subquestion with no hits) go to uncertainty[] with handling human_confirm => honest partial.

## Scripts & dependencies
assemble.py (CLI), search_engine.py (validate_ir + build: subquestion evidence map + all-record screening + stopping audit),
w4kit.py (case load / source check / dedup / result.json). Python 3.10+
standard library only — no third-party packages, no network. See requirements.txt.

## Outputs (/app/output)
candidate_set.json — questions + subquestions, original query plan, subquestion_evidence_map, sufficiency per subquestion (yes / no_gap), screened_records (every record decided, with evidence), screening_counts, dedup clusters, stopping decision, evidence_gaps.
Plus report.md (editable, locators inline), records.csv (editable flat list),
provenance.json (record/edge/view -> source map + sources_used/unused),
search_ir.json (replay), validation.json, result.json (preserves every
output_contract key + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Subquestion with no evidence -> evidence_gaps + human_confirm (partial); record undecidable from material -> maybe / insufficient_evidence, not a fabricated decision; empty query -> recorded, stopping reason updated; duplicate records -> dedup with provenance.
Never fabricate; never silent-skip; never claim live/global coverage.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/question_driven/`: tiny fake input/ + ir.json accepted by the engine. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/question_driven/ir.json --input examples/question_driven/input --out /tmp/demo`
The demo deliberately leaves SQ3 without evidence to show honest partial status and the stopping rationale. Real cases are supplied only at evaluation.

## Self-check
- [ ] fixed questions copied verbatim with locators; subquestions cover object/method/evidence needs
- [ ] every query linked to a subquestion; original strings kept; rounds react to prior results
- [ ] EVERY record has decision + reason + evidence (or maybe/insufficient_evidence)
- [ ] subquestion evidence map complete; gaps explicit; stopping.reason recorded
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
