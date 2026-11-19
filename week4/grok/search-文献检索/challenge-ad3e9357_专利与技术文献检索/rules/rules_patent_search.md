# Domain rules — patent_search (专利与技术文献检索)

Challenge `challenge-ad3e9357`. The agent reads the ACTUAL organizer-provided
local materials and fills the IR; `search_engine.py` validates and computes.
These rules are what make the output source-bound, checkable and honest.

## Rules

1. Use ONLY authorized provided sources (facsimiles, authorized records, provided papers); register each with source_id and an authorization tier green/yellow/red. Red-tier restricted content is never displayed; yellow-tier gets field-level display limits noted. Record database name, version and query date for every conclusion.
2. Numbers: publication != application != grant != priority. Keep each kind separate (numbers.publication/application/grant); the engine normalizes formatting (spaces/dashes/slashes removed, uppercased) but never converts one kind into another. Filing date != priority date != publication date.
3. Families are unioned over OBSERVED links only: each family_link needs a basis (e.g. 'claims priority of X', 'same family listed in record Y') + source_id. Keyword similarity is NOT a family link. The output states explicitly that observed links are not exhaustive official families and claim scopes are not assumed equal.
4. Claims: every version (as-published A1, granted B2, amended...) needs a version label + source locator (page/quote in the actual facsimile). Quote scope per version; OCR boundaries (cut margins, merged WO OCR) are retained as ocr_boundary, not silently repaired.
5. Legal status: UNKNOWN unless a provided source states it with an as_of date (status reported + lag note). A years-old reprint/aggregator page is NOT a register entry. Never present UNKNOWN as 'in force' or 'expired'.
6. Tech-topic search: combine keywords, IPC/CPC classes, assignees and citation clues into explainable queries; keep patent and scientific-literature search logic distinct (records[] for papers, patents[] for patents).
7. Risk-grade every conclusion: missing fields, stale status, unknown family scope, partial coverage -> risk_flags + uncertainty human_confirm. This is intelligence support, not legal advice.

## IR fields enforced by validate_ir (kind-specific)

```
patents: [{id, title?, numbers: {publication?, application?, grant?},
  source_id, authorization?: green|yellow|red, assignee?, filing_date?,
  publication_date?,
  claims: [{version, locator: {source_id, page?, quote?}, text_snippet?}],
  family_links: [{to: <patent id>, basis, source_id}],   # OBSERVED links only
  legal_status?: {value, source_id, as_of},              # else UNKNOWN
  ocr_boundary?, risk_flags: [...]}]                     # REQUIRED >=1 number
records[]: scientific/technical literature (title|doi + source_id + snippet)
queries: [{id, query_string, database?}]
```

## Shared vocabularies
- record.status: reported | not_reported | source_conflict | extraction_failed | inferred | insufficient_evidence
- evidence locator: {source_id, paragraph_id?, page?, quote?, table?, field?} — source_id MUST be registered in sources[]
- features: 0..1 floats (question_match, method_match, population_match, evidence_quality, recency, facet_coverage)
- uncertainty: {item, reason, impact?, handling}; handling=human_confirm => honest partial status

## Self-check

- [ ] only authorized sources used; tiers + query dates recorded; red content not displayed
- [ ] number kinds distinct + normalized; dates not conflated
- [ ] family links observed + basis + source; claim versions located; OCR boundaries kept
- [ ] legal status UNKNOWN unless source+as_of; risk flags + human_confirm on gaps
- [ ] no live remote search / global coverage / latest-publication claims
- [ ] every used input file registered; provenance.json sources_unused reconciled
