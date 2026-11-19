# Domain rules — query_planning (学术文献检索)

Challenge `challenge-a2909a72`. The agent reads the ACTUAL organizer-provided
local materials and fills the IR; `search_engine.py` validates and computes.
These rules are what make the output source-bound, checkable and honest.

## Rules

1. State the research question and scope (population/intervention/method/time window) from task.md; register it with a source locator. Decompose into facets (object, mechanism, method, outcome, population) — each facet gets terms + expanded_terms (synonyms, abbreviations, hypernyms, cross-language variants).
2. Plan queries per facet and round: keep the ORIGINAL query_string, the database it ran against (as named in the provided export), the round number and facet_id. Round 2+ queries must react to round 1 results (fill gaps, resolve conflicts) — record why.
3. Every candidate record needs id + title or doi + source_id + the raw response snippet. Record matched_queries so each hit's recall path is replayable. Never invent records that no provided response contains.
4. Judge relevance per record against the question: features in 0..1 (question_match, method_match, population_match, evidence_quality, recency, facet_coverage) plus a one-line relevance_rationale. Optionally label keep/maybe/exclude and graded_relevance 0..3 — these are AGENT judgments, never presented as organizer ground truth.
5. Dedup is computed by the engine (DOI exact after URL/doi: normalization, then fuzzy title+year). Do not delete duplicate rows yourself — keep them with their own source/snippet so merge provenance and field conflicts survive.
6. Missing metadata stays missing (missing_fields is computed); mark status not_reported / source_conflict with locators. Empty queries/rounds are recorded as no_hits, never padded with invented papers.
7. Record uncovered facets and gaps explicitly; add uncertainty entries with handling human_confirm for anything needing a researcher decision. The engine reports uncovered_facets and metrics@k from your labels.

## IR fields enforced by validate_ir (kind-specific)

```
research_question: {text, scope?, source_id?}   # REQUIRED text
facets: [{id, text, terms: [...], expanded_terms: [...]}]
queries: [{id, query_string, facet_id?, database?, round?, source_id?}]
records[] extras: matched_queries: [query_id, ...], features: {0..1},
  label?: keep|maybe|exclude, graded_relevance?: 0..3 (agent-judged),
  relevance_rationale?
gaps: [{item, reason, handling}]
```

## Shared vocabularies
- record.status: reported | not_reported | source_conflict | extraction_failed | inferred | insufficient_evidence
- evidence locator: {source_id, paragraph_id?, page?, quote?, table?, field?} — source_id MUST be registered in sources[]
- features: 0..1 floats (question_match, method_match, population_match, evidence_quality, recency, facet_coverage)
- uncertainty: {item, reason, impact?, handling}; handling=human_confirm => honest partial status

## Self-check

- [ ] research_question + facets registered; every query keeps original string, database, round, facet
- [ ] every record has source_id + snippet + matched_queries; no invented records
- [ ] features/rationale per ranked record; duplicates kept with provenance (engine merges)
- [ ] uncovered facets / no_hits / missing metadata explicit; metrics labelled agent-judged
- [ ] no live remote search / global coverage / latest-publication claims
- [ ] every used input file registered; provenance.json sources_unused reconciled
