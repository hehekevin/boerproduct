# Domain rules — systematic_screening (系统性文献检索与纳排筛选)

Challenge `challenge-5b90f5e9`. The agent reads the ACTUAL organizer-provided
local materials and fills the IR; `search_engine.py` validates and computes.
These rules are what make the output source-bound, checkable and honest.

## Rules

1. Record the protocol: databases, fields, time range, language limits, search_date and the ORIGINAL query strings; map each criterion to the protocol. Freeze the criteria version — if criteria change mid-screening, re-screen earlier records and log the change (no silent criteria drift).
2. Dedup is computed (DOI exact + fuzzy title/year); preprint/published copies of the same study merge into one cluster with the merge basis kept. The PRISMA flow counts CLUSTERS, so identified - duplicates = unique and included + excluded + pending = unique must close (engine checks).
3. Every record needs reviewers[] with >=2 distinct reviewers judging INDEPENDENTLY: decision in {include, exclude, maybe} + reason_code from criteria + evidence snippet from the actual title/abstract. 'Not relevant' without a code is not auditable.
4. Disagreement (different decisions) REQUIRES adjudication: decision + rationale (+ adjudicator, reason_code). Never average or majority-vote away a substantive dispute; pending adjudication stays 'maybe' in the human_confirm queue.
5. Boundary cases: abstract-only -> maybe/MAY-style code pending full text; language mismatch -> explicit code; partial population overlap -> adjudicate with rationale. Exclusion reasons are counted per code for the audit.
6. Keep the flow log replayable: input/output counts per stage, who decided, on what evidence. A reviewer asking 'why 1832 -> 47' must get a code-level answer.
7. The engine does not replace researcher judgment: final scientific inclusion stays with the human adjudicator; unresolved items are honest partial.

## IR fields enforced by validate_ir (kind-specific)

```
protocol: {databases, search_date, criteria_version?, time_range?,
           languages?, query_strings?}
criteria: [{id, text, type?}]            # REQUIRED reason-code system (frozen)
records[] extras: reviewers: [{reviewer, decision: include|exclude|maybe,
    reason_code: <criteria id>, evidence: [locator]}]   # REQUIRED, >=2 distinct
  adjudication?: {decision, reason_code?, rationale, adjudicator?}
    # REQUIRED whenever reviewer decisions disagree
```

## Shared vocabularies
- record.status: reported | not_reported | source_conflict | extraction_failed | inferred | insufficient_evidence
- evidence locator: {source_id, paragraph_id?, page?, quote?, table?, field?} — source_id MUST be registered in sources[]
- features: 0..1 floats (question_match, method_match, population_match, evidence_quality, recency, facet_coverage)
- uncertainty: {item, reason, impact?, handling}; handling=human_confirm => honest partial status

## Self-check

- [ ] protocol + frozen criteria recorded; reason codes decidable
- [ ] every record dual-reviewed with code + evidence; disagreements adjudicated with rationale
- [ ] PRISMA counts close over dedup clusters; exclusion reasons counted
- [ ] pending items in human_confirm queue; change_log kept
- [ ] no live remote search / global coverage / latest-publication claims
- [ ] every used input file registered; provenance.json sources_unused reconciled
