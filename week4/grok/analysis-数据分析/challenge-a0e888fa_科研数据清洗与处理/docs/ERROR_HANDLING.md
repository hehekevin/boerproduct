# Error handling — analysis-data-cleaning

Principle: identify, record, degrade honestly. Never silently modify or mask anomalies;
never overwrite the original; never impute missing/invalid source values.

| Situation | Engine behavior | Agent action |
|---|---|---|
| File missing / unreadable / corrupt | dataset status file_not_found / read_failed; ops on it failed with reason | register what exists; uncertainty + human_confirm; partial result |
| Empty table / all-missing column | status empty_table; missing_rate=1.0 reported | report the field-level issue; do not invent rows |
| Unknown sentinel code | not in sentinel_map → left as-is (not silently dropped) | extend sentinel_map from dictionary; if ambiguous, flag human_confirm |
| True zero vs missing | "0" never reclassified as missing | confirm semantics in dictionary; cite it in the op rule |
| Unknown unit label | unit_convert skips non-matching rows; no factor guessed | add explicit conversion op once unit verified; else uncertainty |
| Dedup key conflict (same key, different values) | keep=first/last applied; dropped row logged in full | state which record is authoritative + reason; surface field conflict |
| Outlier ambiguous (real high vs error) | action=flag default; bounds + method logged | uncertainty + human_confirm; remove only with explicit justified reason |
| Cast failure (text in numeric column) | logged cast_failed / extraction_failed; original kept | inspect encoding; fix rule or flag |
| Report number ≠ cleaned table | consistency_check.ok=false; status partial | investigate log vs table; fix IR; rerun |
| IR validation errors | validation.json lists them; result still written (partial) | fix IR; rerun |
| Build exception | honest partial/failed result.json + build_error | read traceback; fix; rerun; keep early partial |

Status vocabulary: result = success | partial | failed | stuck.
Record/cell status = reported | inferred | not_reported | source_conflict |
extraction_failed | insufficient_evidence.
Every gap carries {item, reason, impact?, handling: human_confirm} in uncertainty[].