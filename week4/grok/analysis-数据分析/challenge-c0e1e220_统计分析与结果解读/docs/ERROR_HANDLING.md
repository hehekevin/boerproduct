# Error handling — analysis-stats-analysis

Principle: compute honestly from real rows; label approximations; never fabricate.

| Situation | Engine behavior | Agent action |
|---|---|---|
| Missing / non-numeric cells | excluded pairwise, counted in describe.missing; never 0-filled | state caliber + how many excluded |
| n<2 per group / <3 pairs / zero variance | insufficient_evidence + reason | report gap; do not invent a p-value |
| >2 groups | one-way ANOVA; post-hoc NOT performed (stated) | request post-hoc only via a method you can run; else human_confirm |
| Non-normal small sample | Mann-Whitney normal approximation (tie-corrected); exact test unavailable in stdlib (stated) | note approximation limit |
| Paired / repeated design | independent-sample tests flagged invalid for pairing | add assumption + human_confirm; provide paired analysis if possible |
| Heteroscedasticity | variance-ratio F-test reported; Welch used (not Student) | note in assumptions |
| Multiple tests | Holm adjustment within declared family | declare families; do not fish |
| Missing interpretation | interpretation_gap flagged; status partial | write a data-tied interpretation |
| Unreadable / empty table | dataset status recorded; analysis insufficient_evidence | register what exists; partial |
| IR validation errors | validation.json; result still written (partial) | fix IR; rerun |
| Build exception | honest partial/failed + build_error | read traceback; fix; rerun |

Status: result success|partial|failed|stuck; analysis computed|insufficient_evidence|failed.
p-values come from a stdlib regularized incomplete beta (t/F); CIs from bisection t_crit.
These are deterministic and recomputable — no scipy dependency, no hidden randomness.
Every gap: {item, reason, impact?, handling: human_confirm} in uncertainty[].