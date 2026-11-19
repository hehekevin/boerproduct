# arena-summary-notes (阅读10文献总结与结构化笔记, kind=summary_notes)

Source-bound Skill for the Bohrium weekly product-arena reading track. The Agent
reads the ACTUAL organizer material under /input, maps the paper's real section
structure and fills a notes IR (one grounded item per requested note field + claims
with support degrees); a deterministic stdlib engine validates coverage/locators/
status and builds an editable paper card + notes.json + honest result.json.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output
```
Exit 0 = validation ok; exit 2 = validation errors (honest partial result still written).

## Files
- SKILL.md — trigger, workflow, IR schema, self-check (entry point)
- assemble.py — CLI; arena_read_engine.py — validate_ir + coverage + build; readkit.py / figkit.py — reused reading core
- rules/rules_summary_notes.md — field dictionary & grounding rules
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md
- examples/summary_notes/ — SYNTHETIC interface demo (not a formal answer)

## Dependencies
Python 3.10+ standard library only. No third-party packages, no network.

## Scope & limits
- Summarizes provided local material only; skeleton follows the paper's own sections.
- No pre-baked notes; reported vs inferred tagged; gaps use the status vocabulary +
  human_confirm; result.json honest success/partial/failed.

## Self-check
Run the synthetic example (see SKILL.md): exit 0, validation ok, notes.json covers
every requested field, claims support vocabulary valid, result.json honest.