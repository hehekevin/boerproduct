# Domain rules — cross_language (跨语言文献检索)

Challenge `challenge-802a7115`. The agent reads the ACTUAL organizer-provided
local materials and fills the IR; `search_engine.py` validates and computes.
These rules are what make the output source-bound, checkable and honest.

## Rules

1. Establish work-level identity first (works[] with canonical title + DOI from the actual document); every view links to a work_id. One study in 4 language/version forms is ONE work with 4 views — never 4 papers.
2. For each view record language (metadata language), body_language (the language the full text is actually in — an English abstract over a Portuguese body is abstract_only with body_language pt) and version from the fixed vocabulary. Mislabeling language/version mismatches queries to results.
3. Every view needs source_id + the actual title/snippet from that source; DOI normalized per view. Exact duplicates (same work+language+version+normalized title/DOI) are FLAGGED and kept, never silently dropped or counted twice.
4. Term alignment must be checkable: each term/language/render row carries source_id (the provided term table, dictionary entry or document occurrence). Handle synonyms, abbreviations (which may mean different concepts across languages), hypernyms, transliterations and local compound words — not literal machine translation of whole queries.
5. Controlled translation: record which translation service/version produced a query render and keep the original alongside; high-risk hits get back-translation or manual spot-check notes to catch 'same words, different meaning' false positives.
6. Report non-English recovery honestly: n_non_english_views over the PROVIDED works/views only — no claim of live cross-language coverage or unseen-language discovery.
7. If a view's language/version cannot be determined from the material, record it as unknown with an uncertainty entry — do not guess from the journal name.

## IR fields enforced by validate_ir (kind-specific)

```
works: [{id, canonical_title, doi?, source_id?}]    # REQUIRED work identity
views: [{id, work_id, language, body_language?, version, title?, doi?,
         source_id, snippet?}]                        # REQUIRED
  version: original | publisher_translation | abstract_only |
           exact_duplicate | bilingual
term_alignments: [{term, language, render, type?, source_id}]  # checkable
```

## Shared vocabularies
- record.status: reported | not_reported | source_conflict | extraction_failed | inferred | insufficient_evidence
- evidence locator: {source_id, paragraph_id?, page?, quote?, table?, field?} — source_id MUST be registered in sources[]
- features: 0..1 floats (question_match, method_match, population_match, evidence_quality, recency, facet_coverage)
- uncertainty: {item, reason, impact?, handling}; handling=human_confirm => honest partial status

## Self-check

- [ ] works established from actual documents; every view linked with language + body_language + version
- [ ] every view source-located; exact duplicates flagged, never double counted
- [ ] term alignments source-located and checkable; controlled translation recorded
- [ ] non-English counts over provided views only; no live-coverage claim
- [ ] no live remote search / global coverage / latest-publication claims
- [ ] every used input file registered; provenance.json sources_unused reconciled
