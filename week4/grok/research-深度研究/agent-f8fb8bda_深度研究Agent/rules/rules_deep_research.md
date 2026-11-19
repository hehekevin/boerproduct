# Domain rules — deep_research (filling the Research IR)

Goal: walk the full chain question decomposition -> retrieval planning -> multi-step
tool use -> evidence synthesis, and deliver conclusions usable for scientific judgment,
all bound to the provided corpus and independently re-checkable.

## R1. Sources first
- Inventory EVERY actual input file (w4kit.list_materials). Register each used file in
  sources[] {id, title, file, year?, doi?, type}. `file` is relative to /input.
- Read the real content. Never infer a paper's claim from its filename or domain label.
- Binary/PDF without a text layer: the engine marks its quotes `unverifiable`. If a PDF
  parser is available, extract text to /app/work and quote that with a page locator;
  otherwise declare uncertainty (human_confirm). Do not fabricate an extracted layer.

## R2. Question decomposition (问题拆解)
- research_question.main = the concrete question from task.md.
- subquestions[]: each {id, question, depends_on}. The dependency graph MUST be acyclic
  and every depends_on target must be defined (engine rejects cycles/undefined deps).
- Map each claim to a subquestion_id so the decomposition tree is traceable to evidence.

## R3. Retrieval planning & coverage (检索覆盖)
- protocol.inclusion/exclusion: write criteria ids (I*/E*) BEFORE screening.
- protocol.search_queries: {id, query, intent, executed, date, database}. Queries must be
  executable strings (boolean/field syntax), not vague topics. Only mark executed=true
  with a real date for searches actually run over the provided corpus.
- Screen records[] in two stages (title_abstract -> full_text). Every exclude needs a
  reason + criterion id. Duplicates set duplicate_of. The engine recomputes PRISMA and
  cross-checks dedup by DOI/fuzzy title — never hand-compute or hide duplicates.
- Empty retrieval -> record no_hits honestly; do not invent hits.

## R4. Evidence back-links (证据回链) — the claim-evidence rule
- Every claim needs >=1 evidence {source_id, paragraph_id, quote, stance}.
- quote MUST be an EXACT substring of the cited paragraph (whitespace-normalized). The
  engine re-verifies each quote against the real file; `not_found` is a validation error.
  Fix the quote or mark extraction_failed — never paraphrase into a fake "quote".
- strength in {established, supported, suggestive, contested, uncertain}. Match it to the
  evidence: any `contradicts` forbids `established` (use contested/supported). Weak
  strengths (suggestive/uncertain) need an uncertainty note.
- stance in {supports, contradicts, partial, context}. Use partial/context honestly.

## R5. Conflicting evidence (冲突证据)
- conflicts[]: >=2 positions, each with a source locator (source_id + quote/paragraph_id)
  and a stance. Add a handling note explaining how the disagreement is presented.
- Do NOT collapse a conflict into a single verdict; attribute differences (population,
  method, adherence, risk of bias) to the located sources.

## R6. Synthesis & gaps (综合结论 / 研究空白)
- Synthesize claims per theme/subquestion; the engine builds the evidence matrix and
  flags contested claims and registered-but-uncited sources.
- gaps[]: each needs evidence OR a documented search_scope_checked, and human_confirm.
  Allowed types: evidence_gap, conflict_unresolved, method_failure,
  repeated_open_question, coverage_gap. "Not found in this corpus" is NOT "nobody studied
  it" — scope every gap to the provided sources.

## R7. Replay, boundary, honesty
- tool_log[]: record each step {step, tool, params, result} so the path is re-runnable.
- proposal: prospective, bounded=true. No completed-experiment claims.
- uncertainty[]: declare conflicts, bias, scope limits, unverifiable quotes.
- Boundary scan: the engine rejects field-wide wording (world-first / 填补空白 / 无人研究 /
  experiments completed). Keep all conclusions scoped to provided_sources_only.
- Status: success only when validation clean + build complete; partial when gaps/errors/
  unverifiable quotes; failed on IR/build error. Save partial early; iterate.