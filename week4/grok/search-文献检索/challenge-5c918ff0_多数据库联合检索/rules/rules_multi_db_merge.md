# Domain rules — multi_db_merge (多数据库联合检索)

Challenge `challenge-5c918ff0`. The agent reads the ACTUAL organizer-provided
local materials and fills the IR; `search_engine.py` validates and computes.
These rules are what make the output source-bound, checkable and honest.

## Rules

1. Register each database in databases[] with a merge priority (lower wins; default 99). Adapt the query to each database's syntax/field capability — keep each original query_string with its database_id; do not mechanically copy one string everywhere.
2. Build field_mapping from the ACTUAL raw field names in each export (TI/AU/PY/JO/DO, authorString/pubYear/journalTitle, ...). Missing != unknown: a field absent from every source is not_reported_by_any_source, never filled with a guess.
3. Every record needs database_id + source_id + the raw response snippet; keep raw_fields verbatim so normalization is auditable. field_sources gives per-field locators (which file/field the value came from).
4. Dedup + merge are computed: DOI exact first, then fuzzy title+year. Within a cluster the highest-priority source wins each field; alternatives and conflicts are retained with record/database attribution — a reviewer can overturn any merge.
5. Read the coverage matrix: databases with zero results (unavailable or query mismatch) and fields covered by only one database are explicit gaps with human_confirm / single-source notes — never silently swallowed.
6. Identifier semantics differ across databases (year of print vs online, DOI variants); normalize via w4kit rules and record conflicts instead of forcing equality.
7. Respect authorization: only provided/authorized exports; no paywall bypass, no uploading restricted data to unapproved services.

## IR fields enforced by validate_ir (kind-specific)

```
databases: [{id, name, priority?, source_id?}]   # REQUIRED; lower priority wins
field_mapping: {raw_field_name: canonical_name}   # e.g. TI->title, pubYear->year
queries: [{id, query_string, database_id?}]
records[] extras: database_id (REQUIRED, registered),
  raw_fields: {original field names/values}, snippet (raw response),
  field_sources: {canonical_field: {source_id, field?}}
```

## Shared vocabularies
- record.status: reported | not_reported | source_conflict | extraction_failed | inferred | insufficient_evidence
- evidence locator: {source_id, paragraph_id?, page?, quote?, table?, field?} — source_id MUST be registered in sources[]
- features: 0..1 floats (question_match, method_match, population_match, evidence_quality, recency, facet_coverage)
- uncertainty: {item, reason, impact?, handling}; handling=human_confirm => honest partial status

## Self-check

- [ ] databases registered with priorities; queries adapted per database, originals kept
- [ ] field_mapping covers actual raw names; raw_fields + snippets verbatim
- [ ] every record database_id + source_id + field_sources; merge alternatives kept
- [ ] coverage matrix read; empty databases / single-source fields explicit
- [ ] no live remote search / global coverage / latest-publication claims
- [ ] every used input file registered; provenance.json sources_unused reconciled
