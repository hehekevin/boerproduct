# ERROR HANDLING — arena-latex

| Situation | Handling | status |
|-|-|-|
| No local TeX compiler | structure-validate; compile deferred + uncertainty latex_compile (human_confirm) | success if structure ok |
| Compile error (`!` lines) | locate file/line/root cause from log; fix IR; re-run | partial |
| Missing package/font/.cls | state dependency; do not fake compile | partial |
| Unbalanced braces / environment | structure_check issue; fix body | partial until fixed |
| Required section missing | structure_check issue; add section | partial until fixed |
| \cite key not in bib | structure_check issue; add bib entry or fix key | partial until fixed |
| \ref label undefined | structure_check issue; add \label or fix ref | partial until fixed |
| Missing figure file | cite original or state limit; no placeholder/invented curve | success (warn) / partial |
| Duplicate bib keys | validation error; dedup keys | partial until fixed |
| Invented number in table/body | number/source check; restore material value | partial until fixed |
| Build exception | IR + validation saved; uncertainty "build"; fix and re-run | partial |

Always: never claim compile success without a produced PDF; save honest partial early;
record compiler/rounds/command for reproducibility; mark gaps human_confirm.