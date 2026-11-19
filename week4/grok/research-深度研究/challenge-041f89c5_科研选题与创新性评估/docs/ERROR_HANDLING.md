# ERROR HANDLING — research track

Principle: never fabricate data/citations/remote results; never silent-skip; never
write an incomplete result as complete. Distinguish reported vs inferred vs not_reported.
Save validation.json + whatever artifacts exist early, then fix and re-run.

| Situation | Handling | Status signal |
|-|-|-|
| Source file missing / unreadable / no permission | source registered with file pointer; quotes `unverifiable`; declare uncertainty | partial (warning) |
| Binary PDF, no text layer | engine cannot auto-verify quote -> `unverifiable` + human_confirm note; extract text yourself if a parser exists | success-with-uncertainty or partial |
| Quote not present in source file | validation ERROR `quote not found`; fix the quote or mark extraction_failed; never invent | partial until fixed |
| Evidence without exact quote | validation ERROR (claim-evidence rule); add the exact substring | partial until fixed |
| Claim strength `established` but contradicting evidence | validation ERROR; downgrade to contested/supported | partial until fixed |
| Weak strength (suggestive/uncertain) without uncertainty note | warning; add an uncertainty note | declared |
| Conflicting study conclusions | conflicts[] with >=2 located positions + handling; present both, do not collapse | surfaced (contested claims) |
| Exclusion without rationale | validation ERROR; add reason + criterion id | partial until fixed |
| PRISMA counts do not add up | validation ERROR; fix record stages/decisions (engine recomputes) | partial until fixed |
| Undeclared duplicate (DOI/fuzzy title) | warning `possible undeclared duplicates`; verify and set duplicate_of | declared |
| Search query returns nothing | record no_hits honestly; do not invent hits; gap with search_scope_checked | partial / gap |
| "Not found => nobody studied it" | rejected: gap needs evidence OR documented search scope; flag human_confirm | partial until fixed |
| Included record lacks quality appraisal (systematic) | warning; add quality[] with overall grade + dimension evidence | declared |
| Trend phase representative work outside year window / not registered | validation ERROR; fix phase years or representative_works | partial until fixed |
| Missing publication year for a source | warning; excluded from year histogram, listed in missing_year_sources | declared |
| Novelty declared verdict != coverage-derived verdict | validation ERROR; align verdict with covered_by coverage | partial until fixed |
| Novelty item without uncertainty / covered_by without quote | validation ERROR; add them | partial until fixed |
| Feasibility `supported` without evidence | validation ERROR; add evidence or downgrade to assumption/unknown | partial until fixed |
| Feasibility assumption/unknown | auto human_confirm; declare risk | declared |
| Over-boundary wording (world-first / fills-gap / experiments completed) | validation ERROR; scope text to provided sources, prospective only | partial until fixed |
| proposal.bounded != true | validation ERROR; set bounded=true (prospective, source-scoped) | partial until fixed |
| IR unreadable / build exception | assemble writes honest failed/partial result.json + build_error.txt; partial artifacts saved | failed/partial |

result.json always carries honest status + sources + uncertainty + change_log + limits
(for partial/failed). The boundary is fixed: provided_sources_only; no field-wide
novelty/completeness; no completed experiments.