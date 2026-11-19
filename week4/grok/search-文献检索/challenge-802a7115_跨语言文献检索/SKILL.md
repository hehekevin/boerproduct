---
name: search-cross-language
description: Recover non-English literature via source-located term alignment (synonyms, abbreviations, transliterations, local renders), group language/version views under work-level identity (original / publisher_translation / abstract_only / exact_duplicate / bilingual), preserve body_language vs metadata language, and flag exact duplicates instead of double counting. Use when the task is 跨语言文献检索 / cross-language query expansion, translation-view matching or language/version identification of hits.
---

# Cross-language literature search & identity (跨语言文献检索)

A source-bound Skill for the Bohrium weekly research-efficiency contest (search
track, `challenge-802a7115`). The agent reads the ACTUAL organizer-provided local
materials under /input (scientific documents, real Crossref/EuropePMC/publisher
responses, retained reference graph, organizer-local import states, facsimiles —
whatever the case ships), fills a structured IR, and a deterministic stdlib
engine validates it, performs the real computation (work/view identity + duplicate flags + term alignment), and emits
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
source locator.

## When to use
The workorder involves the same study appearing in multiple languages/versions and asks to find non-English originals, align terminology checkably, and state for every hit which language and version it is — without inflating metrics by counting translations as separate studies. NOT for whole-document translation or writing polish.

## Focus (rubric)
Actual effect 40 (completion/correctness/completeness/verifiability: real
records, accurate metadata, Precision@k / nDCG@k / Recall@k where applicable,
replayable evidence), usage gain 25 vs the no-Skill baseline, innovation gain 15
(work/view identity model with body_language preserved, exact-duplicate flagging, checkable source-located term alignment table), reliable experience 10 (stable triggering, empty-result /
conflict / missing-metadata / permission handling), ecosystem contribution 10
(docs + reusable engine/rules/example). GitHub public link: +5 bonus.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete research question, constraints, evidence scope.
- The actual material files. Read and register the real files; trust file
  content over filename/database labels. Finite local snapshot only.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] {id, path, type, name}.
2. Read the material; fill the IR per `rules/rules_cross_language.md` and the schema below.
   Keep original queries, raw snippets, field-level sources; judge relevance /
   decisions / grades yourself and attach evidence locators.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir search_ir.json --input /input --out /app/output`
   -> validate_ir -> build -> works_views.json + report.md + records.csv +
   provenance.json + search_ir.json -> result.json.
4. Honest status: success only when validation is clean and no unresolved
   human_confirm gaps; partial on validation errors, build errors or open gaps;
   failed on unreadable IR / no artifacts. Save partial early; never fabricate.

## IR schema (agent fills from ACTUAL material; enforced by validate_ir)
```
ir_version: "1.0"            # required literal
case_id: <auto from /input/case.json>
kind: "cross_language"
sources: [{id, path, type?, name?}]   # every used input file; unique ids;
                                        # EVERY source_id anywhere must be registered
queries: [{id, query_string, ...}]    # ORIGINAL query strings preserved
records: [{id, title|doi, source_id, query_id?, snippet?, status?,
            authors?, year?, journal?, doi?, field_sources?, ...}]
works: [{id, canonical_title, doi?, source_id?}]    # REQUIRED work identity
views: [{id, work_id, language, body_language?, version, title?, doi?,
         source_id, snippet?}]                        # REQUIRED
  version: original | publisher_translation | abstract_only |
           exact_duplicate | bilingual
term_alignments: [{term, language, render, type?, source_id}]  # checkable
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

## Domain rules — cross_language (full text: rules/rules_cross_language.md)
1. Establish work-level identity first (works[] with canonical title + DOI from the actual document); every view links to a work_id. One study in 4 language/version forms is ONE work with 4 views — never 4 papers.
2. For each view record language (metadata language), body_language (the language the full text is actually in — an English abstract over a Portuguese body is abstract_only with body_language pt) and version from the fixed vocabulary. Mislabeling language/version mismatches queries to results.
3. Every view needs source_id + the actual title/snippet from that source; DOI normalized per view. Exact duplicates (same work+language+version+normalized title/DOI) are FLAGGED and kept, never silently dropped or counted twice.
4. Term alignment must be checkable: each term/language/render row carries source_id (the provided term table, dictionary entry or document occurrence). Handle synonyms, abbreviations (which may mean different concepts across languages), hypernyms, transliterations and local compound words — not literal machine translation of whole queries.
5. Controlled translation: record which translation service/version produced a query render and keep the original alongside; high-risk hits get back-translation or manual spot-check notes to catch 'same words, different meaning' false positives.
6. Report non-English recovery honestly: n_non_english_views over the PROVIDED works/views only — no claim of live cross-language coverage or unseen-language discovery.
7. If a view's language/version cannot be determined from the material, record it as unknown with an uncertainty entry — do not guess from the journal name.

## Scripts & dependencies
assemble.py (CLI), search_engine.py (validate_ir + build: work/view identity + duplicate flags + term alignment),
w4kit.py (case load / source check / dedup / result.json). Python 3.10+
standard library only — no third-party packages, no network. See requirements.txt.

## Outputs (/app/output)
works_views.json — per-work identity rows (canonical title, DOI, n_views, languages, versions, views with source/body_language/version/snippet, exact_duplicate_flags), term_alignments (source-located), n_works/n_views/n_non_english_views, exact_duplicates, identity_rule, scope_note.
Plus report.md (editable, locators inline), records.csv (editable flat list),
provenance.json (record/edge/view -> source map + sources_used/unused),
search_ir.json (replay), validation.json, result.json (preserves every
output_contract key + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Translation counted as separate study -> work/view grouping prevents it; exact duplicate -> flagged + kept; abstract-only translation -> version abstract_only + body_language preserved; unalignable term -> no row invented, uncertainty noted; unknown language -> explicit, not guessed.
Never fabricate; never silent-skip; never claim live/global coverage.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/cross_language/`: tiny fake input/ + ir.json accepted by the engine. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/cross_language/ir.json --input examples/cross_language/input --out /tmp/demo`
The demo includes a Portuguese original, a publisher translation, an English abstract-only view and an exact duplicate copy (flagged). Real cases are supplied only at evaluation.

## Self-check
- [ ] works established from actual documents; every view linked with language + body_language + version
- [ ] every view source-located; exact duplicates flagged, never double counted
- [ ] term alignments source-located and checkable; controlled translation recorded
- [ ] non-English counts over provided views only; no live-coverage claim
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
