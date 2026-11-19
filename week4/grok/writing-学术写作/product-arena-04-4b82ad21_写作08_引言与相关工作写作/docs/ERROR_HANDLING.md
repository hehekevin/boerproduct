# ERROR HANDLING — arena-intro-related

| Situation | Handling | status |
|-|-|-|
| Literature empty/insufficient | state gap; write only supported claims; uncertainty + human_confirm | partial |
| Claim without evidence | validation warning; bind evidence or mark interpretation/hypothesized | success (warn) |
| Citation not findable / metadata missing | mark uncertain; never invent authors/year/DOI | success (warn) / partial |
| Causal wording vs correlational evidence | writekit warning; soften wording or flag | success (warn) |
| research_gap.derived_from unknown id | validation error; fix to registered citations | partial until fixed |
| Gap without cited basis | flag; do not assert as established | success (warn) |
| Contribution beyond available results | mark status=proposed + human_confirm | success (warn) |
| Required section missing | flag explicitly (writekit warning) | success (warn) |
| Number not in declared sources | number_issues flag; verify or add source | success (warn) |
| Unknown citation style/genre | documented fallback; note limit | success (warn) |
| Build exception | IR + validation saved; uncertainty "build"; fix and re-run | partial |

Always: save honest partial early; never fabricate references/claims/results;
distinguish reported vs inferred vs not_reported; mark gaps human_confirm.