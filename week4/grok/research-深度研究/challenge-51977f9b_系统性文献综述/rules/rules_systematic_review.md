# Domain rules — systematic_review (filling the Research IR)

Goal: walk the full chain question decomposition -> search-query construction ->
inclusion/exclusion screening -> quality appraisal -> evidence-bound review conclusions,
with every step pre-specified, auditable and re-runnable by another person.

## R1. Sources
- Inventory EVERY actual input file (w4kit.list_materials). Register each used file in
  sources[] {id, title, file, year?, doi?, type}; metadata read from the real paper.
- Binary/PDF without a text layer: quotes `unverifiable`; extract text yourself if a
  parser exists, else declare uncertainty (human_confirm). Never fabricate a text layer.

## R2. Protocol FIRST (检索式构造)
- protocol.inclusion/exclusion: write criteria ids (I*/E*) with explicit text BEFORE
  screening. Both lists must be defined.
- protocol.search_queries REQUIRED: each {id, query, intent, executed, date, database}.
  query must be an executable string (boolean/field syntax) that could hit core literature,
  not a vague topic. Mark executed=true only with a real date + database for searches
  actually run over the provided corpus. Never invent remote database hits.

## R3. Two-stage screening (纳排筛选)
- records[]: {id, source_id, title, year?, doi?, stage, decision, criteria_applied,
  reason?, reviewer?, duplicate_of?}. stage title_abstract -> full_text; decision
  include/exclude/pending. Every decision must conform to a pre-written criterion id.
- Every exclude needs a reason + criterion. Duplicates set duplicate_of (target exists).
- The engine recomputes PRISMA: identified -> duplicates_removed -> title_abstract_screened
  -> title_abstract_excluded -> full_text_assessed -> full_text_excluded -> included.
  Counts MUST balance (engine rejects mismatches). It also cross-checks undeclared
  duplicates by DOI exact + fuzzy title-year; declare duplicate_of for true duplicates.
- A full-text round is expected; title-only screening is flagged. Empty retrieval ->
  record no_hits honestly.

## R4. Quality appraisal (质量评价)
- Every INCLUDED record needs quality[] {record_id, overall, dimensions[]}. overall in
  {high, moderate, low, unclear}. Each dimension {name, rating?, evidence} should carry a
  source locator (source_id + paragraph_id + quote) so the appraisal basis is re-checkable.
- Missing appraisals for included records are flagged. Do not grade without evidence.

## R5. Evidence-bound conclusions (证据回链 / 综合结论)
- Every claim needs >=1 evidence {source_id, paragraph_id, quote, stance}; quote is an
  EXACT substring re-verified against the real file (`not_found` is an error). Conclusions
  must be supported by INCLUDED evidence and not overstep the corpus.
- strength matches the evidence: established/supported/suggestive/contested/uncertain;
  any contradicts forbids established; weak strengths need an uncertainty note.
- themes[] induced from sources (basis); map claims to theme_id/subquestion_id.

## R6. Conflicts, gaps, replay, boundary
- conflicts[]: >=2 located positions + handling; present divergence, do not collapse.
- gaps[]: evidence OR documented search_scope_checked + human_confirm. "Not found in this
  corpus" is NOT "nobody studied it".
- Keep query text/date/database, screening_log.csv, quality basis and citation locators
  auditable; provenance.json maps every claim/record/source. tool_log[] aids replay.
- proposal prospective, bounded=true; uncertainty[] declares conflicts/bias/scope.
- Boundary scan rejects field-wide novelty/completeness and completed-experiment wording.
  Status: success only when validation clean + build complete; partial on gaps/errors/
  unverifiable quotes/missing appraisals; failed on IR/build error. Save partial early.