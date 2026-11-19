# ERROR HANDLING — search track (quality_appraisal)

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
| dimensions[] missing on a paper | validation error | partial |
| Non-abstain judgment without evidence | validation error (or abstain) | partial |
| Abstain carrying low/high grade | validation error | partial |
| Unknown / duplicate dimension id | validation error | partial |
| Applicable dimension not judged | warning: flagged, do not fabricate | warning |
| Evidence without quote/page/paragraph | warning: locator too coarse | warning |

Always save validation.json + whatever artifacts exist early, then fix and re-run.
result.json carries honest status + sources + uncertainty + change_log + limits.
