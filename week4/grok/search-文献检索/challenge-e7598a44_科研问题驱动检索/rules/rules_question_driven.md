# Domain rules — question_driven (科研问题驱动检索)

Challenge `challenge-e7598a44`. The agent reads the ACTUAL organizer-provided
local materials and fills the IR; `search_engine.py` validates and computes.
These rules are what make the output source-bound, checkable and honest.

## Rules

1. Copy the FIXED research question(s) from task.md into questions[] with a source locator; do not reword the organizer's question into something easier. Decompose each into subquestions covering object, mechanism, method, comparison, time range and evidence requirements.
2. Every query links to a subquestion_id and keeps its original query_string, database and round. Order queries by dependency (prerequisite vs parallel); round 2+ must react to round 1 (fill gaps, verify conflicting evidence).
3. Screen EVERY candidate record: decision in {include, exclude, maybe} with a reason_code and an evidence locator (quote/field from the actual response or document). include/exclude without evidence is flagged; if the material cannot support a decision use maybe or status insufficient_evidence — never guess.
4. Map included records to the subquestions they support (subquestion_ids). The engine computes per-subquestion evidence sufficiency; a subquestion with zero included evidence is an explicit gap, not a silent omission.
5. Term expansion (synonyms, abbreviations, cross-language renders) belongs in the query plan; keep both the original and expanded forms so recall is auditable.
6. Record stopping.reason: evidence sufficient / marginal gain too low / escalated to human. Never stop silently and never claim global recall — the snapshot is finite.
7. Open gaps (e.g. a subquestion with no hits) go to uncertainty[] with handling human_confirm => honest partial.

## IR fields enforced by validate_ir (kind-specific)

```
questions: [{id, text, source_id?, subquestions: [{id, text}]}]  # REQUIRED
queries: [{id, query_string, subquestion_id?, database?, round?}]
records[] extras: decision: include|exclude|maybe (REQUIRED for every record),
  reason_code?, rationale?, evidence: [locator], subquestion_ids: [sq_id]
stopping: {reason, rounds_run?}
```

## Shared vocabularies
- record.status: reported | not_reported | source_conflict | extraction_failed | inferred | insufficient_evidence
- evidence locator: {source_id, paragraph_id?, page?, quote?, table?, field?} — source_id MUST be registered in sources[]
- features: 0..1 floats (question_match, method_match, population_match, evidence_quality, recency, facet_coverage)
- uncertainty: {item, reason, impact?, handling}; handling=human_confirm => honest partial status

## Self-check

- [ ] fixed questions copied verbatim with locators; subquestions cover object/method/evidence needs
- [ ] every query linked to a subquestion; original strings kept; rounds react to prior results
- [ ] EVERY record has decision + reason + evidence (or maybe/insufficient_evidence)
- [ ] subquestion evidence map complete; gaps explicit; stopping.reason recorded
- [ ] no live remote search / global coverage / latest-publication claims
- [ ] every used input file registered; provenance.json sources_unused reconciled
