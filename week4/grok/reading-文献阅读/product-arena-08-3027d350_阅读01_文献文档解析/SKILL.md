---
name: arena-document-parse
description: Source-bound scientific document parsing — read the ACTUAL organizer paper/workorder files under /input and parse the paper into structured fields (title/authors/abstract/methods/results/conclusion) plus section hierarchy, one result per requested field_id with exact paragraph/page locators, exact quotes and reported/not_reported/source_conflict/extraction_failed/insufficient_evidence status; deterministic stdlib engine validates coverage and builds editable fields.json + result.json. Use for the "阅读01文献文档解析" workorder (kind=document_parse).
---

# 文献文档解析 skill (document_parse)

Source-bound reading skill. The Agent reads the ACTUAL material and fills the
reading IR; `assemble.py` deterministically validates locators/status/coverage,
builds editable artifacts and an honest result.json. Output triad:
解析结果 / 证据与边界 / 运行状态. Never write can't-judge as fact; never fabricate.

## Focus (rubric)
- 提得全: cover every requested field (workorder) + key structure (title, authors,
  abstract, section hierarchy, captions/references when present in material).
- 排得对 / 拆得清: section hierarchy with levels + parent ids; paragraph ids preserve
  reading order; do not merge adjacent paragraphs or mix headers/footers into body.
- 核得回: every field value carries exact paragraph_id/page + verbatim quote.
- Read the ACTUAL organizer workorder file (e.g. `/input/target-fields.json`) and
  emit ONE result per requested field_id. Absent field ≠ zero; mark not_reported.

## Scope / trigger
Use when the case asks for 文献文档解析 / paper structure parsing (kind=document_parse).
Only given local material; no online retrieval, no guessing from domain labels.

## Inputs (runtime) — READ THESE ACTUAL FILES FIRST
1. `/input/case.json` — copy `case_id`, read `output_contract`.
2. `/input/task.md` — the concrete task and requested fields.
3. Workorder files when present: `target-fields.json` / `target_fields.json` /
   `workorder.json` (requested field_ids). The engine auto-reads these for coverage.
4. ALL material files (paper text/markdown/JSON; PDFs: extract text with available
   runtime tools first, register the extracted text as a source with page locators).
Register every file you actually used in `sources[]` with id + real path.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory `/input` (ls), open case.json + task.md + workorder + material.
2. Fill IR per `rules/rules_document_parse.md`: sources[], items[] (one per requested
   field_id: value, units?, kind reported|inferred, status, evidence[{source,
   paragraph_id, quote}]), sections[] (id/title/level/parent_id/paragraph_ids),
   coverage, unanswered_parts, uncertainty, provenance.
3. Run exactly:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output`
   → validation.json → fields.json + document_parse_result.md → provenance.json
   (record_map + source sha256) → result.json (all output_contract fields + case_id).
4. Exit 0 = validation ok; exit 2 = errors → fix IR and re-run. Save honest partial
   deliverables early (budget: 64 requests / 900 s); improve incrementally.

## IR schema (minimal)
```json
{"ir_version":"1.0","case_id":"...","kind":"document_parse",
 "sources":[{"id":"S1","path":"paper.md","title":"..."}],
 "items":[{"field_id":"title","value":"...","kind":"reported","status":"reported",
           "evidence":[{"source":"S1","paragraph_id":"P1","quote":"verbatim..."}]}],
 "sections":[{"id":"SEC1","title":"Methods","level":1,"parent_id":null,"paragraph_ids":["P3","P4"]}],
 "unanswered_parts":[],"uncertainty":[],"provenance":{}}
```
Status vocabulary (required per record): reported | not_reported | source_conflict |
extraction_failed | insufficient_evidence. Gap statuses carry NO value and set
`human_confirm:true`. kind=inferred needs an uncertainty note.

## Domain rules
See `rules/rules_document_parse.md` (field extraction, hierarchy, verbatim quotes,
multi-column order, gap handling).

## Scripts & dependencies
assemble.py (CLI), arena_read_engine.py (validate_ir + build), readkit.py (shared
reading validation), figkit.py (case load / result.json / provenance). Python 3.10+
stdlib only — no third-party packages required.

## Outputs (/app/output)
fields.json (per-field results + sections), document_parse_result.md (editable),
reading_ir.json, provenance.json (record_map + sha256 of actual source files),
validation.json, result.json (honest status/sources/uncertainty/change_log).

## Error handling (docs/ERROR_HANDLING.md)
Missing/unreported field → status not_reported + human_confirm (never invent);
unreadable material (encrypted PDF / no text layer) → extraction_failed + reason;
conflicting versions → source_conflict + both locators; inferred structure →
kind=inferred + uncertainty. Validation errors → honest partial result.json.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/document_parse/`: input/ (case.json, task.md, material.md, target-fields.json)
+ ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/document_parse/ir.json --input examples/document_parse/input --out /tmp/demo_dp`

## Self-check
- [ ] read ACTUAL /input workorder + material (not labels); sources registered with real paths
- [ ] one result per requested field_id; coverage complete or unanswered_parts flagged
- [ ] every reported value has paragraph_id/page + verbatim quote
- [ ] reported vs inferred; gaps use the status vocabulary + human_confirm
- [ ] section hierarchy levels/parents consistent; reading order preserved
- [ ] result.json honest (status/sources/uncertainty); exit code 0 on clean IR

## Runtime contract
Skill installed at /skills/weekly-skill; input /input/case.json + task.md + material;
work /app/work; output /app/output/result.json preserving every output_contract
field + case_id. No pre-baked answers; no fabricated data/citations. Honest
success/partial/failed with limits. Resources ≤50 UTF-8 text files, ≤500KB each,
≤2MB total, no binaries/symlinks/__pycache__ (run with PYTHONDONTWRITEBYTECODE=1).

## GitHub bonus (+5)
GITHUB_URL.txt at package root: line 1 public GitHub tree URL (filled by git_sync),
line 2 relative entry file (SKILL.md). Opens without login.