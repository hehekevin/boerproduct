# WORKFLOW — arena-polish

## 1. Read the actual material
- `w4kit.load_case("/input")` gives case_id, task_md, output_contract.
- `w4kit.list_materials("/input")` / `find_input` locate the text + glossary/style guide.
- READ the files (docx/pdf via available parsers; trust content over labels).

## 2. Fill the IR (Agent judgment)
- Register `sources[]` with locators; build `glossary[]`; declare `numbers[]`.
- Segment the text; for each segment write original/revised/change_type/reason/
  meaning_preserved/source/locator (see rules/rules_polish.md).
- Add `claims[]` (structural preservation claims ok), `revisions[]`, `uncertainty[]`.
- Save as `writing_ir.json` under /app/work.

## 3. Assemble (deterministic)
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir writing_ir.json --input /input --out /app/output
```
Pipeline: validate_ir (writekit + arena_write_engine) → validation.json →
build polished.md + polished.docx + track_changes.json → preservation +
number-consistency checks → writing_ir.json + provenance.json (claim_map +
segment_map) → result.json (output_contract + case_id + honest status).
Exit 0 when validation ok; exit 2 with honest partial result when errors.

## 4. Iterate / edit
- Edit the IR (not the binary), re-run. Record provenance.changes[] {what, why,
  before, after}. The docx stays editable (real runs + heading styles).

## 5. Verify
- extra_checks.preservation_issues should be empty (or justified).
- Review number_issues; confirm hedge strength unchanged; terminology uniform.
- result.json status honest; gaps marked human_confirm.