# ERROR HANDLING — arena-methods-section

| Situation | Handling | status |
|-|-|-|
| Parameter value absent | status=not_reported; human_confirm; never invent | success (warn) |
| Parameter without source | validation error; add config/log/author locator | partial until fixed |
| Inferred parameter | status=inferred; show derivation; distinguish in text | success (warn) |
| Config conflict (two values) | status=source_conflict; surface both; human_confirm | partial / warn |
| Dataset version unknown | flag; do not guess version | success (warn) |
| Statistical method missing | validation warning; state test/alpha/n/variability | success (warn) |
| Reproducibility field missing | render "not_reported (human_confirm)" | success (warn) |
| Required section missing | flag explicitly | success (warn) |
| Number not in declared sources | number_issues flag; verify or add source | success (warn) |
| File unreadable / permission | extraction_failed; state limit; partial | partial |
| Build exception | IR + validation saved; uncertainty "build"; fix and re-run | partial |

Always: save honest partial early; never补出数值; distinguish reported vs inferred vs
not_reported vs source_conflict; mark gaps human_confirm.