# Domain rules — lit_review (filling the Research IR)

Goal: on a batch of REAL provided literature, complete screening -> theme induction ->
evidence organization -> review draft, delivering text that can enter scientific
discussion. Every substantive claim must be truly supported by its citation, and citation
strength must match the original.

## R1. Sources & metadata accuracy
- Inventory EVERY actual input file (w4kit.list_materials). Register each used paper in
  sources[] {id, title, file, year?, doi?, type}. Read title/authors/year/venue/doi from
  the real paper (or its companion metadata table), NOT from the filename/domain label.
- The engine hashes each cited file into provenance.source_map so a reviewer can confirm
  the paper really exists and which version was used.
- Binary/PDF without a text layer: quotes become `unverifiable`. Extract text yourself if
  a parser exists (quote it with a page locator); else declare uncertainty (human_confirm).

## R2. Screening (筛选)
- protocol.inclusion/exclusion: write criteria ids (I*/E*) before screening.
- records[]: one per hit {id, source_id, title, year?, doi?, stage, decision,
  criteria_applied, reason?, reviewer?, duplicate_of?}. stage title_abstract -> full_text.
  Every exclude needs a reason + criterion. Duplicates set duplicate_of (target exists).
- The engine recomputes PRISMA counts and cross-checks dedup by DOI/fuzzy title-year.
  Never hand-compute counts or hide duplicates; screening_log.csv keeps the list auditable.

## R3. Theme induction (主题归纳) — REQUIRED
- themes[] MUST be induced FROM the sources, not imposed from an external taxonomy.
- Each theme {id, name, basis}: the basis names the papers/observations it grew from.
- Map every claim to a theme_id. The engine reports claims_per_theme so coverage of the
  corpus's main themes and method routes is visible. A theme without a basis is flagged.

## R4. Evidence organization (证据组织) — the claim-evidence rule
- Every claim needs >=1 evidence {source_id, paragraph_id, quote, stance}. quote MUST be
  an EXACT substring of the cited paragraph; the engine re-verifies it against the real
  file. `not_found` is an error — fix the quote or mark extraction_failed, never fabricate.
- strength MUST match the original text: established (multiple confirming, no
  contradiction), supported, suggestive (weak/preliminary), contested (any contradicts),
  uncertain. `established` + contradicts is rejected. Weak strengths need uncertainty.
- stance supports/contradicts/partial/context: organize BOTH pro and con evidence per
  claim. The engine builds synthesis_matrix.csv and flags contested claims +
  registered-but-uncited sources (so you can see coverage holes).

## R5. Conclusion divergence & conflicts
- conflicts[]: >=2 positions, each with a source locator + stance, plus a handling note.
  Present divergence honestly; attribute it to population/method/bias via located sources.
  Do not collapse a disagreement into one verdict.

## R6. Review draft, gaps, boundary (综述草稿 / 研究空白)
- The engine renders research_report.md/.docx from the IR (themes -> claims -> evidence ->
  conflicts -> gaps -> proposal). Fill claim text as review-ready prose bound to quotes.
- gaps[]: evidence OR documented search_scope_checked + human_confirm. Types:
  evidence_gap, conflict_unresolved, method_failure, repeated_open_question, coverage_gap.
  "Not found in this corpus" is NOT "nobody studied it".
- proposal prospective, bounded=true. uncertainty[] declares conflicts/bias/scope.
- Boundary: no field-wide completeness/novelty, no completed-experiment wording (engine
  scans agent prose and rejects over-boundary text). Keep everything provided_sources_only.
- Status: success only when validation clean + build complete; partial on gaps/errors/
  unverifiable quotes; failed on IR/build error. Save partial early; iterate via
  provenance.changes (echoed to result.change_log).