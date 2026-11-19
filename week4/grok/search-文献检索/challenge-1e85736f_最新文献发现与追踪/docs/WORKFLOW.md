# WORKFLOW — search track (incremental_tracking)

## 0. Runtime
Inputs under /input (case.json, task.md, actual organizer-provided materials:
scientific documents, real database responses, retained reference graph,
import states, facsimiles — whatever this case ships). Outputs to /app/output.
Work under /app/work. Python 3.10+ stdlib only; set PYTHONDONTWRITEBYTECODE=1.
NO live remote search is performed or claimed; everything is source-bound to
the provided local snapshot.

## 1. Inventory & register
- `w4kit.list_materials("/input")` -> real file list (path/bytes/ext).
- Read case.json: copy case_id, note EVERY output_contract key (must be preserved).
- Read task.md: the concrete research question, constraints and evidence scope.
- Register each used file in `sources[]` {id, path, type, name}. Never infer
  content from a filename or database label — open the actual file/response.

## 2. Read & fill IR (agent judgment + locators)
- Follow `rules/rules_incremental_tracking.md` and the IR schema in SKILL.md.
- Keep ORIGINAL query strings, raw response snippets and field-level sources.
- Every record/edge/view/claim carries a source locator; missing data is
  `not_reported` / `insufficient_evidence` / UNKNOWN, never guessed.
- Do not hand-compute what the engine computes (dedup, scores, BFS, recall,
  PRISMA counts, number normalization) — supply judgment + evidence instead.

## 3. Assemble
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir search_ir.json --input /input --out /app/output
```
- `validate_ir` -> validation.json (errors -> honest partial, never silent).
- `build` -> incremental_state.json + report.md + records.csv + provenance.json + search_ir.json.
- `build_result` -> result.json (output_contract echoed + case_id + status +
  sources + uncertainty + change_log + summary).

## 4. Verify & hand over
- Coverage: every question/subquestion/facet/reference item asked about has a row.
- Traceability: every record/decision/edge/grade traces to a real locator.
- Honesty: gaps are explicit (uncovered facets, evidence_gaps, stub nodes,
  unattributed misses, abstains, UNKNOWN legal status), not fabricated facts.
- provenance.json lists sources_used / sources_unused — reconcile before handover.

## 5. Iterate
- Save a partial result EARLY, then improve the IR and re-run; the engine is
  deterministic so edits re-render reproducibly (idempotent).
- Record changes in `provenance.changes` for the change_log.
