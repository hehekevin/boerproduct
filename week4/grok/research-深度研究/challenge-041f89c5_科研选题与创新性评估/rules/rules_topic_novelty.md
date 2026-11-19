# Domain rules — topic_novelty (filling the Research IR)

Goal: advance a research idea to a decision-ready assessment with four consistent
deliverables — question definition, prior-work comparison, novelty identification,
feasibility judgment — all scoped to the provided corpus and bound to exact evidence.

## R1. Sources
- Inventory EVERY actual input file (w4kit.list_materials). Register each used prior-work
  file in sources[] {id, title, file, year?, doi?, type}; metadata read from the real paper.
- Binary/PDF without a text layer: quotes `unverifiable`; extract yourself if a parser
  exists, else declare uncertainty (human_confirm). Never fabricate a text layer.

## R2. Question definition (问题定义)
- topic.question_definition needs ALL FOUR: object (who/what is studied), variables
  (exposure/outcome/moderator), baseline (the comparator), falsifiable (a concrete condition
  that would refute the proposed benefit). A vague aspiration is not falsifiable.
- Decompose the topic into subquestions if helpful; screen prior work with criteria +
  reasons (records[]); the engine recomputes PRISMA + dedup.

## R3. Prior-work comparison (已有工作比较)
- topic.comparison[] rows {dimension, comparable, prior_work[{source_id, evidence}],
  proposed}. Choose comparison objects that TRULY match the proposed topic (right
  population/outcome/method), not loosely related papers.
- Each prior_work binds an exact quote (source_id + paragraph_id). Mark comparable=false
  when the dimension differs (e.g. self-report vs objective outcome). An empty comparison
  matrix is flagged.

## R4. Novelty identification (创新点识别) — coverage-derived verdicts
- topic.novelty[] {id, statement, type, covered_by[], verdict?, uncertainty}. type in
  {method, data, application, conclusion}. Every item needs an explicit uncertainty note.
- covered_by[] entries {source_id, paragraph_id, quote, coverage in full/partial/none}.
  quote MUST be an exact substring re-verified against the real file.
- The engine DERIVES the verdict from coverage: any full -> covered; any partial ->
  partially_overlapping; all none -> novel_within_sources; otherwise uncertain. A declared
  verdict that disagrees with the derived one is a validation ERROR — align them (or omit
  the declared verdict and let the engine derive it).
- "Not found in this corpus" is NOT global novelty. The strongest honest verdict is
  novel_WITHIN_SOURCES; never claim world-first / 填补空白 / 无人研究 (boundary scan rejects).

## R5. Feasibility judgment (可行性判断)
- topic.feasibility[] {id, premise, status, evidence?, human_confirm?, risk?}. status:
  supported REQUIRES located evidence; assumption / unknown are auto-flagged human_confirm.
- State the risk for each premise. Do not assert a premise holds without evidence — downgrade
  to assumption/unknown and flag it. The engine counts n_assumptions and lists human_confirm.

## R6. Evidence back-links, conflicts, gaps, boundary
- claims/conflicts/gaps bind EXACT quotes re-verified against the real file. strength matches
  evidence; any contradicts forbids established. Present conflicting evidence (conflicts[]
  >=2 located positions + handling). gaps need evidence OR search_scope_checked + human_confirm.
- All novelty/feasibility judgments are PROSPECTIVE and scoped to provided_sources_only.
  proposal.bounded must be true; no completed-experiment wording. uncertainty[] declares
  scope/bias/assumptions.
- Status: success only when validation clean + build complete; partial on errors/verdict
  mismatches/unverifiable quotes; failed on IR/build error. Save partial early; iterate via
  provenance.changes (echoed to result.change_log).