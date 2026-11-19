# ERROR HANDLING — arena-paper-to-ppt

| Situation | Handling | status |
|-|-|-|
| Paper figure missing / bitmap-only | cite original figure or state limit; no placeholder/invented curve | partial / warn |
| Number absent in paper | keep source value or flag; never invent | success (warn) |
| Bullet/figure source unregistered | deckkit error; register source + locator | partial until fixed |
| Missing single claim / invalid role | deckkit error; fix page | partial until fixed |
| Template gap (no .pptx) | documented fallback layout/theme; note used_template=false | success (warn) |
| Font missing / CJK | CJK font auto-fallback; note limit | success (warn) |
| Overflow / too many pages | cut/split bullets; never below min_pt; respect slide_count_target | success (warn) |
| No office-renderer (local) | honest labelled layout previews; uncertainty export; true render at runtime | partial |
| Export failure | honest fallback + uncertainty; retry with office-renderer | partial |
| Schematic vs data confusion | label figure kind; never present schematic as experimental data | success (warn) |
| Build exception | IR + validation saved; uncertainty "build"; fix and re-run | partial |

Always: save honest partial early; never fabricate data/figures/compile state;
distinguish reported vs inferred vs not_reported; mark gaps human_confirm.