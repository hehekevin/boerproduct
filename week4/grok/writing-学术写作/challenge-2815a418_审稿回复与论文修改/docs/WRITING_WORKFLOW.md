# WRITING WORKFLOW — material → writing IR → editable deliverable → checks → result.json

The Agent does the scientific/organisational judgment (read the real material,
extract claims+evidence, citations, structure, terminology, revisions); the scripts
do deterministic validation, building, consistency checks, export and result
assembly. Never add facts outside the material; never fabricate citations/numbers.

## 0. Read actual input
- `/input/case.json` (copy `case_id`, read `output_contract`, audience/genre/format),
  `/input/task.md`. Inventory `/input`; open docx/pdf/csv/images (pdf-text tool /
  actual PDF). Register `sources[]` with precise locators (file+page/section/row).
- For format/template tasks, read the template file and extract a checkable spec.

## 1. Fill the writing IR (`writing_ir.json`)
Follow the skill's `rules/rules_*.md`. Cross-cutting fields:
- `claims[]`: each substantive assertion with `evidence[]` ({source, locator,
  strength, supports}) + `citation_ids[]`; tag strength; no causal wording on
  correlational evidence.
- `citations[]`: authors/year/title/journal/doi + source; bind to claims.
- `sections[]`: level/heading/role/paragraphs (each paragraph cites claims/source);
  `required_sections[]` for completeness; figures with captions+source.
- `glossary[]`: single render per term (terminology uniformity).
- `numbers[]`: value/unit/source/locator for consistency checks.
- `revisions[]`: location/before/after/reason/status (traceable, accept/reject).
- domain fields: `alignment[]` (grant/plan goal-content-route-indicator),
  `comments[]` (reviewer: decision/response/edit refs), `nodes/relations` (mindmap),
  `tasks[]` (benchmark).
- `uncertainty[]` + `human_confirm[]` for gaps/conflicts (explicit, not hidden).

## 2. Validate + build + check + export + result (one command)
```
python assemble_write.py --ir writing_ir.json --input /input --out /app/output
```
- writekit.validate_writing: claim-evidence binding, citation registry/metadata/DOI,
  number source pointers, section completeness, terminology uniformity, revision
  traceability, alignment completeness, reviewer decisions.
- build: docxkit (manuscript.md + valid editable manuscript.docx) for prose kinds;
  mindmap (layered editable SVG + PNG/PDF) for mind_map; benchkit (tasks.json +
  rubric.json + reference_answers.md + eval.py) for writing_benchmark.
- check_number_consistency: paragraph numbers vs declared source numbers.
- export: office-renderer → PDF/PNG preview (honest labelled fallback if absent).
- result.json: every output_contract field + case_id, honest status, sources,
  provenance.claim_map, uncertainty, change_log, validation, extra_checks.

## 3. Source-preserving edit & version
Edit the IR (a claim/section/term/revision), re-run; deliverable + checks + exports
regenerate. Keep `provenance.changes[]` / `revisions[]` (before/after/location/reason)
so versions compare and rollback is possible; never silently rewrite whole sections.

## 4. Error handling (honest)
- Missing material/figure/full-text: state the gap; write only what is supported;
  flag human_confirm. Never invent data/citations.
- Citation unverifiable: mark uncertain, keep claim with caveat or drop claim.
- Conflict (text vs figure, abstract vs results): surface in uncertainty + 待核清单.
- Template gap / unknown citation style: documented fallback + record.
- Over-length / overflow: compress without dropping evidence; record.
- Save honest partial result.json early; improve within budget (64 req/900 s).

## 5. Self-check
Facts/numbers/units from source; citations support their claim & metadata accurate;
required sections/fields present (missing flagged); terminology uniform; revisions
traceable; editable md+docx (or mindmap/benchmark) produced; claim_map complete;
result.json honest.