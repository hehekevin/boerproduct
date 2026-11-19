# ERROR HANDLING — search track (query_planning)

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
| Facet with zero hits | uncovered_facets listed; plan a supplementary round or flag human_confirm | partial if unresolved |
| Record without matched_queries | warning: recall path unclear — add the query ids | warning |
| Duplicate export rows (DOI URL variants) | engine dedup merges; both snippets kept in cluster | n_duplicates_removed |
| No features for a record | unscored_needs_features -> human review queue, not a fake score | partial if unresolved |

Always save validation.json + whatever artifacts exist early, then fix and re-run.
result.json carries honest status + sources + uncertainty + change_log + limits.
