# WORKFLOW — research track (deep_research / lit_review / systematic_review / trend_analysis / topic_novelty)

## 0. Runtime
Inputs under /input (case.json, task.md, actual material files). Work under /app/work.
Outputs to /app/output. Python 3.10+ stdlib only. Set PYTHONDONTWRITEBYTECODE=1 so the
package stays text-only (no __pycache__). Budget: 64 model requests / 900 s per case.

## 1. Inventory & register sources
- w4kit.list_materials("/input") -> real file list (path/bytes/ext).
- Register EVERY material file you use in sources[] {id, title, file, year?, doi?, type}.
  `file` is the path relative to /input (e.g. "docs/paper1.md"); the engine resolves it
  against the IR dir and the input dir. Read actual content; never trust filename labels.
- For PDFs/binary files the engine cannot auto-verify quotes: it marks them
  `unverifiable` and declares uncertainty (human_confirm). Extract text yourself first
  if a parser is available, and quote the extracted text with a page/paragraph locator.

## 2. Read material & fill the IR (agent judgment + locators)
Fill research_ir.json per rules/rules_<kind>.md and the SKILL.md schema:
- protocol: inclusion/exclusion criteria (ids I*/E*) + executable search_queries
  (query, intent, executed, date, database). Required for systematic_review.
- records: one per screening hit {id, source_id, title, year?, doi?, stage, decision,
  criteria_applied, reason?, reviewer?, duplicate_of?}. stage in {title_abstract,
  full_text}; decision in {include, exclude, pending}. Exclusions need a reason.
  Duplicates set duplicate_of (target must exist). The engine recomputes PRISMA counts
  and cross-checks dedup by DOI/fuzzy title — do not hand-compute them.
- research_question: main + subquestions (deep_research requires subquestions with an
  acyclic depends_on graph).
- themes: induced FROM sources, each with a basis (lit_review requires themes).
- claims: {id, text, type, strength, theme_id?, subquestion_id?, evidence[]}. Every claim
  needs >=1 evidence {source_id, paragraph_id, quote, stance}. quote must be an EXACT
  substring of the source paragraph. strength in {established, supported, suggestive,
  contested, uncertain}; an `established` claim cannot carry contradicting evidence.
- conflicts: >=2 positions, each with a source locator; add a handling note.
- gaps: evidence OR documented search_scope_checked; flag human_confirm. Never reason
  "not found => nobody studied it".
- quality (systematic_review): per included record {record_id, overall, dimensions[]}.
- trend (trend_analysis): year_basis + phases[] with representative_works whose years
  fall inside the phase window. The engine computes the year histogram, theme-by-year
  matrix and direction (descriptive, within-corpus only).
- topic (topic_novelty): question_definition {object, variables, baseline, falsifiable},
  comparison[], novelty[] (coverage-derived verdicts), feasibility[] (supported needs
  evidence; assumption/unknown -> human_confirm).
- proposal: prospective, bounded=true. uncertainty[]: declare conflicts/bias/scope.
- provenance.pipeline + changes[]; tool_log[] for replay (deep_research).

## 3. Assemble
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir research_ir.json --input /input --out /app/output
- validate_ir -> validation.json (errors -> honest partial; warnings declared).
- build -> research_report.md + .docx, synthesis_matrix.csv, screening_log.csv,
  prisma_flow.svg, provenance.json (+ trend_chart.svg/trend_stats.json for trend,
  + novelty_assessment.json for novelty).
- summarize + build_result -> result.json preserving every output_contract key + case_id,
  with honest status, sources, uncertainty, change_log, prisma, quote_check_summary.

## 4. Verify & hand over
- Coverage: every subquestion / theme / claim / record / novelty item asked for has a result.
- Traceability: every claim/conflict/gap/quality/comparison/novelty locator re-verified
  against the actual file (quote_check_summary). Fix `not_found` quotes; never fabricate.
- Honesty: conflicts presented both sides; gaps human_confirm; status success only when
  validation is clean and build complete; partial when gaps/unverifiable quotes exist.
- Boundary: no field-wide novelty/completeness, no completed-experiment claims.

## 5. Iterate
- Re-run after fixing the IR; the engine is deterministic so edits re-render reproducibly.
- Record edits in provenance.changes (echoed to result.change_log). Save partial early.