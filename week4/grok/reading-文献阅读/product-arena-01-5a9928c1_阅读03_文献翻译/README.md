# arena-literature-translation (阅读03文献翻译, kind=translation)

Source-bound Skill for the Bohrium weekly product-arena reading track. The Agent
reads the ACTUAL organizer material under /input, builds a locked glossary and fills
a segment-aligned translation IR; a deterministic stdlib engine validates locators/
status, COMPUTES faithfulness checks (glossary enforcement, number + citation-marker
preservation) and builds editable bilingual artifacts + honest result.json.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output
```
Exit 0 = validation ok; exit 2 = validation errors (honest partial result still written).

## Files
- SKILL.md — trigger, workflow, IR schema, self-check (entry point)
- assemble.py — CLI; arena_read_engine.py — validate_ir + checks + build; readkit.py / figkit.py — reused reading core
- rules/rules_translation.md — segmentation/glossary/faithfulness rules
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md
- examples/translation/ — SYNTHETIC interface demo (not a formal answer)

## Dependencies
Python 3.10+ standard library only. No third-party packages, no network, no MT API.

## Scope & limits
- Translates provided local material; the Agent produces the translations, the engine
  verifies terminology/numbers/citations deterministically (semantic quality beyond
  these checks remains human-reviewable via the bilingual table).
- No pre-baked answers; gaps use the status vocabulary + human_confirm; result.json
  honest success/partial/failed.

## Self-check
Run the synthetic example (see SKILL.md): exit 0, validation ok,
translation_check.json n_issues=0, bilingual.json segment-aligned, result.json honest.