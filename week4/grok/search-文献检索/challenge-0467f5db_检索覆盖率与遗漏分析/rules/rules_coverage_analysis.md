# Domain rules — coverage_analysis (检索覆盖率与遗漏分析)

Challenge `challenge-0467f5db`. The agent reads the ACTUAL organizer-provided
local materials and fills the IR; `search_engine.py` validates and computes.
These rules are what make the output source-bound, checkable and honest.

## Rules

1. Build the reference set from the PROVIDED independent sources (review reference lists, guidelines, expert lists) — never from your own results ('defining the denominator by the numerator' fakes ~100% coverage). Freeze it: each item gets id + title + source_id + inclusion_reason; verify identifiers.
2. Mark unusable items explicitly (unusable: 'retracted' / 'no full text' / ...) with the source notice; they are excluded from the usable denominator but stay listed — never silently delete a known item.
3. Hit matching is computed: normalized DOI exact first, then fuzzy title (>=0.85 token overlap) with year compatibility (±1). Every reference gets a hit row with match_method; 'not found' is a MISS to attribute, not 'not relevant'.
4. Attribute EVERY miss to a category with a specific explanation naming the query string, field restriction, time window or source that caused it ('database coverage insufficient' alone is not actionable). Unattributed misses are listed as human_confirm.
5. Supplementary rounds must be designed from the miss categories (new terms/fields/sources), registered as queries, and linked via supplementary_rounds.query_ids + new_record_ids. The engine computes new reference hits and recall_after; a round with zero new hits is a zero_stop_candidate — report it honestly, do not claim misses dropped.
6. Report residual misses after all rounds with reasons; state when to stop supplementing (marginal gain zero / source not indexed / escalation).
7. Spot-check hit judgments (identifier anomalies, same-title-different-work) and record agreement; coverage numbers always carry the usable-denominator count.

## IR fields enforced by validate_ir (kind-specific)

```
reference_set: [{id, title, doi?, year?, source_id, inclusion_reason?,
                 unusable?}]              # REQUIRED; independent frozen denominator
records[]: the retrieved results (source_id + snippet + query_id)
miss_attributions: [{reference_id, category, explanation}]
  category: term_not_covered | field_too_narrow | time_window |
            source_not_indexed | identifier_anomaly | other
supplementary_rounds: [{id, query_ids: [...], new_record_ids: [...], basis?}]
```

## Shared vocabularies
- record.status: reported | not_reported | source_conflict | extraction_failed | inferred | insufficient_evidence
- evidence locator: {source_id, paragraph_id?, page?, quote?, table?, field?} — source_id MUST be registered in sources[]
- features: 0..1 floats (question_match, method_match, population_match, evidence_quality, recency, facet_coverage)
- uncertainty: {item, reason, impact?, handling}; handling=human_confirm => honest partial status

## Self-check

- [ ] reference set independent + frozen; every item source_id + inclusion_reason; unusable flagged
- [ ] hit table complete with match_method; recall uses usable denominator
- [ ] every miss attributed to specific query/field/window/source; residual explained
- [ ] supplementary rounds show real new hits / zero-gain honesty
- [ ] no live remote search / global coverage / latest-publication claims
- [ ] every used input file registered; provenance.json sources_unused reconciled
