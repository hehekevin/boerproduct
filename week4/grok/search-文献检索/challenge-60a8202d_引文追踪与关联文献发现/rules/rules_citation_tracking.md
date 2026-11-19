# Domain rules — citation_tracking (引文追踪与关联文献发现)

Challenge `challenge-60a8202d`. The agent reads the ACTUAL organizer-provided
local materials and fills the IR; `search_engine.py` validates and computes.
These rules are what make the output source-bound, checkable and honest.

## Rules

1. Seeds come from task.md / the provided corpus; every seed must be a registered record. Traverse ONLY the organizer-retained reference graph — no live citation API calls or claims of complete forward coverage (new preprints often have no citing records yet).
2. Every edge needs from, to, direction and source_id. backward = 'to' is a reference OF 'from' (methods/data origins); forward = 'to' CITES 'from' (improvements/critiques). If a source gives only a cited list without direction, determine direction from the actual document and record the basis in context — never guess silently.
3. Keep citation context clues (which section/entry of the actual document lists the edge) so a reviewer can re-verify each hop. The engine records the full path seed->...->node with per-hop direction@source.
4. Identity merge: same work as preprint/conference/journal/supplement versions merges via DOI exact + fuzzy title/year (engine). Keep merge evidence and field conflicts; watch for same-title-different-work and different-title-same-work.
5. Nodes reached without metadata stay as not_reported_stub — list them, do not fabricate titles/DOIs. Seeds with no outgoing edges in the retained graph are reported explicitly.
6. Choose max_depth (1..5) and pruning deliberately; high citation count != high relevance. If you add relevance judgments, attach features/rationale as in screen_rank; otherwise the expansion is structural, not a relevance claim.
7. Gaps (missing forward records, stubs, unavailable sources) go to uncertainty[] human_confirm => honest partial.

## IR fields enforced by validate_ir (kind-specific)

```
seeds: [record_id, ...]                 # REQUIRED, must exist in records
edges: [{from, to, direction: forward|backward, source_id, context?}]  # REQUIRED
max_depth: int 1..5 (default 2)
records[]: metadata for every node you could verify (title/doi + source_id);
  nodes without metadata are kept as labelled stubs (warning, not error)
```

## Shared vocabularies
- record.status: reported | not_reported | source_conflict | extraction_failed | inferred | insufficient_evidence
- evidence locator: {source_id, paragraph_id?, page?, quote?, table?, field?} — source_id MUST be registered in sources[]
- features: 0..1 floats (question_match, method_match, population_match, evidence_quality, recency, facet_coverage)
- uncertainty: {item, reason, impact?, handling}; handling=human_confirm => honest partial status

## Self-check

- [ ] seeds registered; every edge has direction + source_id + context
- [ ] BFS paths replayable hop-by-hop; depth within 1..5
- [ ] stubs labelled not_reported; versions merged with evidence
- [ ] no live-coverage claim; gaps in uncertainty with human_confirm
- [ ] no live remote search / global coverage / latest-publication claims
- [ ] every used input file registered; provenance.json sources_unused reconciled
