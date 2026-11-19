# ERROR HANDLING — search track (multi_db_merge)

Principle: never fabricate records/citations/status, never silent-skip, never
present a finite local snapshot as live/global coverage.

| Situation | Handling | Status signal |
|-|-|-|
| IR unreadable / JSON broken | failed result.json with error + human_confirm | failed |
| build exception | keep validation + any artifacts; partial/failed + build_error | partial/failed |
| validation errors | honest partial; fix IR and re-run | partial |
| Record missing title AND doi | validation error — do not invent a record | partial |
| Metadata field absent | missing_fields computed; status not_reported, value null | partial if unresolved |
| Two sources disagree on a field | dedup cluster conflicts kept; source_conflict + both locators | partial |
| Query returns nothing | recorded as empty round / no_hits; never invented hits | partial |
| Unresolved gap needing a human | uncertainty[] {item, reason, handling: human_confirm} | partial |
| Record without database_id | validation error | partial |
| Unknown database_id / query.database_id | validation error | partial |
| No field_sources on a record | warning: per-field provenance missing | warning |
| No field_mapping | warning: raw names used as-is | warning |
| Database with 0 records | gap database_no_results, human_confirm | partial if unresolved |

Always save validation.json + whatever artifacts exist early, then fix and re-run.
result.json carries honest status + sources + uncertainty + change_log + limits.
