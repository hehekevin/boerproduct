# Domain rules — trend_analysis (filling the Research IR)

Goal: deliver four checkable products — time trend, theme evolution, representative works,
research gaps — each supported by the engine's OWN descriptive statistics over the provided
corpus, not a "frontier list" of search hits and not external trend numbers.

## R1. Sources & year basis (年份口径)
- Inventory EVERY actual input file (w4kit.list_materials). Register each used file in
  sources[] {id, title, file, year, doi?, type}. The publication year MUST be read from the
  real file (or its metadata), not guessed. State trend.year_basis (e.g. publication_year).
- Missing years: the engine lists them in missing_year_sources and excludes them from the
  histogram. Never invent a year to fill a gap. No year data at all is a validation error.
- Binary/PDF without a text layer: quotes `unverifiable`; extract yourself if a parser
  exists, else declare uncertainty (human_confirm).

## R2. Scope & recomputation (统计可复算)
- The trend scope = included_source_ids from screening (records[]), or all sources if no
  records. Screen honestly with criteria + reasons; the engine recomputes PRISMA + dedup.
- The engine RECOMPUTES year_histogram, year_growth (delta between consecutive years),
  theme_year_matrix and theme_direction. Do not hand-compute or paste external statistics;
  supply the IR (sources/years/themes/claims) and let the engine derive the numbers.

## R3. Theme evolution (主题演化 / 主题层级)
- themes[] {id, name, basis}: the basis is the merge/induction rule naming the sources the
  theme grew from. Keep a clear theme hierarchy; do not impose an external taxonomy.
- Each claim's theme_id + evidence source-year feeds the theme-by-year matrix (each claim
  counted once per source-year). The engine splits early/late at the median year and labels
  direction rising/declining/stable WITHIN SET — descriptive only, not a field-wide claim.

## R4. Phases & representative works (时间跨度 / 各阶段代表作)
- trend.phases[] {id, label, years[lo,hi], basis, representative_works[{source_id}]}.
  Phases should cover the corpus time span; basis must be consistent with the source text.
- Every representative work MUST be: a registered source, inside the included scope, and
  its publication year INSIDE the phase window [lo,hi]. The engine rejects unregistered or
  out-of-window reps (phase_check). Pick reps whose year truly falls in the phase.

## R5. Research gaps (研究空白)
- gaps[] {id, type, text, evidence | search_scope_checked, human_confirm}. Cover gap types
  (evidence_gap, conflict_unresolved, method_failure, repeated_open_question, coverage_gap).
- Gaps must be supported by the corpus/statistics (e.g. a theme with no recent work, a
  missing year range, an unresolved conflict). "Not found here" is NOT "nobody studied it".

## R6. Evidence back-links, boundary, honesty
- Claims/conflicts/gaps bind EXACT quotes (source_id + paragraph_id) re-verified against the
  real file. strength matches evidence; any contradicts forbids established.
- All trends are DESCRIPTIVE within the provided corpus; the engine emits a small-sample
  caveat automatically. No field-wide/global trend or completeness claims, no
  completed-experiment wording (boundary scan rejects over-boundary agent prose).
- proposal prospective, bounded=true; uncertainty[] declares scope/bias/missing years.
- Status: success only when validation clean + build complete; partial on errors/missing
  years/unverifiable quotes; failed on IR/build error. Save partial early; iterate via
  provenance.changes (echoed to result.change_log).