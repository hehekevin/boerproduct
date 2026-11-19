# Domain rules — screen_rank (文献筛选与智能排序)

Challenge `challenge-2dd1f64c`. The agent reads the ACTUAL organizer-provided
local materials and fills the IR; `search_engine.py` validates and computes.
These rules are what make the output source-bound, checkable and honest.

## Rules

1. Define criteria[] FIRST: each with id, type include/exclude and a decidable text (population, method, design, time range). Every record's reason_code must reference a criterion — 'not relevant' alone is not auditable.
2. Label every record keep / maybe / exclude. keep/exclude need an evidence locator (quote from the actual abstract/response). Abstract insufficient -> maybe + reason code for the human queue, never a confident exclude.
3. Score with features in 0..1: question_match, method_match, population_match, evidence_quality, recency, facet_coverage (weights overridable via ranking.weights; renormalized over present features). A record without features is NOT scored — it goes to human_review_queue, not to a fabricated position.
4. Preprint vs published: link with version_of (must reference a known record id). The engine builds version groups so the same study is not double counted; keep both records with their own sources. Different DOIs/years are fine — the explicit link carries the identity.
5. Ties and mixed-topic sets: the engine orders by tier (keep<maybe<exclude), then score desc, then year desc, then id asc — deterministic and reproducible. Do not hand-sort.
6. Conflicts (annotation disagreement, same study multiple reports): surface them, merge via version_of/dedup or escalate to maybe; never average away a substantive dispute.
7. graded_relevance labels (0..3) are YOUR judgments for metrics@k; the engine marks them agent_judged_not_ground_truth. Missing metadata stays not_reported.

## IR fields enforced by validate_ir (kind-specific)

```
criteria: [{id, type: include|exclude, text}]   # REQUIRED, checkable
records[] extras: label: keep|maybe|exclude (REQUIRED),
  reason_code: <criteria id> (REQUIRED), evidence: [locator] (keep/exclude),
  features: {0..1} (else unscored -> human queue),
  version_of?: <record id> (preprint -> published link),
  graded_relevance?: 0..3 (agent-judged)
ranking: {weights?, k?}
```

## Shared vocabularies
- record.status: reported | not_reported | source_conflict | extraction_failed | inferred | insufficient_evidence
- evidence locator: {source_id, paragraph_id?, page?, quote?, table?, field?} — source_id MUST be registered in sources[]
- features: 0..1 floats (question_match, method_match, population_match, evidence_quality, recency, facet_coverage)
- uncertainty: {item, reason, impact?, handling}; handling=human_confirm => honest partial status

## Self-check

- [ ] criteria decidable; every record label + reason_code + evidence (or maybe)
- [ ] features 0..1 with rationale; unscored records in human queue, not faked
- [ ] preprint/published linked via version_of; dedup provenance kept
- [ ] tie-break deterministic; metrics labelled agent-judged; gaps explicit
- [ ] no live remote search / global coverage / latest-publication claims
- [ ] every used input file registered; provenance.json sources_unused reconciled
