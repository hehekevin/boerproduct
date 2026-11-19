# Domain rules — incremental_tracking (最新文献发现与追踪)

Challenge `challenge-1e85736f`. The agent reads the ACTUAL organizer-provided
local materials and fills the IR; `search_engine.py` validates and computes.
These rules are what make the output source-bound, checkable and honest.

## Rules

1. Use ONLY the organizer-local import states provided under /input. Register each snapshot with id, window.start/end (fixed timezone) and imported_at; record_ids must reference registered records. Never set live_claim or describe the output as 'the latest publications' — indexing lag means the snapshot is not live truth.
2. The dedup key is normalized DOI, else normalized title+year (engine). A record whose key was seen in an earlier snapshot is NOT new: if it is a different record id it is a version update (preprint->published etc.); if fields changed it is an update with changed_fields. Link versions explicitly with version_of when the material supports it.
3. Retracted records (retracted: true, per the actual source notice) are separated from new discoveries — a retraction is a correction alert, not a new paper. Never push a retracted record as a finding.
4. Windows must be contiguous (start == previous end). The engine flags gaps/overlaps as window_issues with human_confirm — decide backfill vs overlap dedup explicitly; do not let windows drift.
5. Keep the full version record: subscription config, windows, imported_at, counts, seen keys. Re-running the same snapshots yields identical increments (idempotent) — no double alerts on retry.
6. Alert design: merge/suppress duplicates, distinguish new vs version-update vs retraction, and state the watermark (last_window_end). Failures (rate limit/timeout/missing fields) are recorded as gaps with retry notes, not silent skips.
7. Old papers newly indexed are not 'new research': the increment is relative to the previous snapshot, and the report says so.

## IR fields enforced by validate_ir (kind-specific)

```
subscription: {topic, window_timezone?, dedup_key?, source_id?}
snapshots: [{id, window: {start, end}, imported_at?, record_ids: [...], source_id?}]
records[] extras: version_of?: <record id>, retracted?: bool
# live_claim is FORBIDDEN (validation error): organizer-local states only
```

## Shared vocabularies
- record.status: reported | not_reported | source_conflict | extraction_failed | inferred | insufficient_evidence
- evidence locator: {source_id, paragraph_id?, page?, quote?, table?, field?} — source_id MUST be registered in sources[]
- features: 0..1 floats (question_match, method_match, population_match, evidence_quality, recency, facet_coverage)
- uncertainty: {item, reason, impact?, handling}; handling=human_confirm => honest partial status

## Self-check

- [ ] snapshots registered with windows + imported_at; record_ids all known
- [ ] new vs version-update vs retracted distinguished with basis; keys stable
- [ ] windows contiguous or issues flagged; watermark replayable; idempotent
- [ ] NO live_claim / latest-publication wording anywhere
- [ ] no live remote search / global coverage / latest-publication claims
- [ ] every used input file registered; provenance.json sources_unused reconciled
