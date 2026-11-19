# arena-document-parse (阅读01文献文档解析, kind=document_parse)

Source-bound Skill for the Bohrium weekly product-arena reading track. The Agent
reads the ACTUAL organizer material under /input, fills a reading IR (one result per
requested field_id with verbatim quotes + paragraph locators + honest status), and a
deterministic stdlib engine validates, builds editable artifacts and result.json.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output
```
Exit 0 = validation ok; exit 2 = validation errors (honest partial result still written).

## Files
- SKILL.md — trigger, workflow, IR schema, self-check (entry point)
- assemble.py — CLI; arena_read_engine.py — validate_ir + build; readkit.py / figkit.py — reused reading core
- rules/rules_document_parse.md — extraction & status rules
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md
- examples/document_parse/ — SYNTHETIC interface demo (not a formal answer)

## Dependencies
Python 3.10+ standard library only. No third-party packages, no network.

## Scope & limits
- Parses provided local material (text/markdown/JSON; PDF text must be extracted with
  runtime tools first). Does not do OCR itself; unreadable input → extraction_failed.
- No pre-baked answers: all field values come from the IR the Agent fills at runtime.
- Gaps use reported/not_reported/source_conflict/extraction_failed/insufficient_evidence
  + human_confirm; result.json is honest success/partial/failed.

## Self-check
Run the synthetic example (see SKILL.md), confirm exit 0, validation.ok=true,
fields.json covers every requested field_id, provenance.json record_map complete.