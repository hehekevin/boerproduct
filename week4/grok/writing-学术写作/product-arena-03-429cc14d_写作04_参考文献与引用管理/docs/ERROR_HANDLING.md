# ERROR HANDLING — arena-reference-manage

| Situation | Handling | status |
|-|-|-|
| Library file missing/unreadable | state gap; manage what is parseable; uncertainty + human_confirm | partial |
| Reference missing title/year/doi | format gracefully; flag incomplete metadata | success (warn) |
| DOI parse failure | keep raw DOI string; flag suspicious format | success (warn) |
| Ambiguous merge (same author, diff work) | keep separate clusters; human_confirm | success (warn) |
| Field conflict within cluster | record conflicts in dedup_report; pick representative | success (warn) |
| In-text marker without reference | missing_in_text flag; do not invent a reference | partial |
| Reference never cited | uncited_references flag; human_confirm cite/remove | success (warn) |
| Unsupported library format | state limit; parse supported fields; note extraction_failed | partial |
| Unverifiable / suspected fabricated entry | mark uncertain; never invent metadata | partial / warn |
| Unknown target_style | validation error; choose GB/T 7714 / APA / IEEE | partial until fixed |
| Build exception | IR + validation saved; uncertainty "build"; fix and re-run | partial |

Always: save honest partial early; never fabricate references/metadata; distinguish
reported vs not_reported vs source_conflict; mark gaps human_confirm.