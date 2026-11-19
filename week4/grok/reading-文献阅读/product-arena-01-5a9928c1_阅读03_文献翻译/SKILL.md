---
name: arena-literature-translation
description: Source-bound faithful academic translation — read the ACTUAL organizer paper/workorder files under /input, translate the requested passages segment-aligned (source↔target) with locked glossary terminology, preserved numbers/units/citation markers, paragraph locators and reported/not_reported/source_conflict/extraction_failed/insufficient_evidence status; deterministic stdlib engine checks term consistency, number and citation preservation and builds bilingual.json + translation_check.json + result.json. Use for the "阅读03文献翻译" workorder (kind=translation).
---

# 文献翻译 skill (translation)

Source-bound reading skill. The Agent reads the ACTUAL material and fills the
translation IR (segment-aligned source↔target + glossary); `assemble.py`
deterministically validates locators/status and COMPUTES faithfulness checks
(glossary enforcement, number preservation, citation-marker preservation), then
builds editable bilingual artifacts + honest result.json. Output triad:
解析结果 / 证据与边界 / 运行状态. No omission, no addition, no silent paraphrase.

## Focus (rubric)
- 术语稳: one glossary, locked across title/abstract/body/captions/conclusion; the
  engine verifies every glossary term actually appears in each relevant target segment.
- 段落全: one segment per source paragraph/range; segment ids ↔ paragraph ids 1:1;
  no dropped, duplicated or reordered segments; cross-page continuation kept in order.
- 关系准: numbers, units, negation, hedges, causal/concessive relations, formulas and
  citation markers ([1], [2,3]) preserved exactly; engine checks numbers + citations.
- 可核验: every segment points back to source paragraph_id + verbatim source quote;
  uncertain terms flagged (human_confirm), never smoothed over.

## Scope / trigger
Use when the case asks for 文献翻译 / bilingual academic translation (kind=translation).
Only given local material; no online retrieval; translate the requested range fully.

## Inputs (runtime) — READ THESE ACTUAL FILES FIRST
1. `/input/case.json` — copy case_id, read output_contract.
2. `/input/task.md` — translation direction, requested passage range, glossary demands.
3. Workorder files when present (target-fields.json / workorder.json / glossary.json):
  requested segments/fields and any organizer-provided terminology.
4. ALL material files (paper text/markdown/JSON; PDFs: extract text with runtime
   tools first). Register every file actually used in sources[] with id + real path.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory /input; open case.json + task.md + workorder + material.
2. Build glossary FIRST (extract domain terms from the actual source; honor any
   organizer glossary). Then fill IR per rules/rules_translation.md:
   sources[], glossary[{source_term,target_term}], segments[{id, source_text,
   target_text, kind, status, evidence[{source, paragraph_id, quote}]}],
   unanswered_parts, uncertainty, provenance.
3. Run exactly:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output`
   → validation.json → bilingual.json + translation_check.json + translation_result.md
   → provenance.json → result.json.
4. translation_check.json issues (term_inconsistent / number_missing /
   citation_missing) are must_fix: correct the target text and re-run. Exit 0 =
   validation ok; exit 2 = errors. Save honest partial early; budget 64 req / 900 s.

## IR schema (minimal)
```json
{"ir_version":"1.0","case_id":"...","kind":"translation",
 "sources":[{"id":"S1","path":"paper.md"}],
 "glossary":[{"source_term":"perovskite","target_term":"钙钛矿"}],
 "segments":[{"id":"seg1","source_text":"...","target_text":"...",
   "kind":"reported","status":"reported",
   "evidence":[{"source":"S1","paragraph_id":"P1","quote":"verbatim source..."}]}],
 "unanswered_parts":[],"uncertainty":[],"provenance":{}}
```
Status vocabulary per segment: reported | not_reported | source_conflict |
extraction_failed | insufficient_evidence. Untranslatable segment (image formula,
garbled text) → extraction_failed + reason + human_confirm, target_text null.
Uncertain term choice → keep translation + uncertainty note (kind stays reported
only if the segment is fully grounded; otherwise insufficient_evidence).

## Domain rules
See rules/rules_translation.md (segmentation, glossary locking, faithfulness,
flagging uncertain terms, gap handling).

## Scripts & dependencies
assemble.py (CLI), arena_read_engine.py (validate_ir + deterministic faithfulness
checks + build), readkit.py / figkit.py (reused reading core). Python 3.10+ stdlib only.

## Outputs (/app/output)
bilingual.json (segment-aligned source↔target + glossary), translation_check.json
(computed issues + human_confirm list), translation_result.md (editable bilingual
table), reading_ir.json, provenance.json (record_map + source sha256), validation.json,
result.json (all output_contract fields + case_id, honest status).

## Error handling (docs/ERROR_HANDLING.md)
Missing text layer / image-only formula → extraction_failed + reason; ambiguous term
→ uncertainty + human_confirm; conflicting source versions → source_conflict with
both locators; never omit a requested segment silently — list it in unanswered_parts.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/translation/`: input/ + ir.json (EN→ZH, 3 segments, glossary). Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/translation/ir.json --input examples/translation/input --out /tmp/demo_tr`

## Self-check
- [ ] read ACTUAL /input workorder + material; sources registered with real paths
- [ ] every requested passage covered by exactly one aligned segment (no omission/addition)
- [ ] glossary locked: engine term check passes for all segments
- [ ] numbers/units/citation markers preserved (translation_check.json n_issues=0)
- [ ] each segment has paragraph_id + verbatim source quote; uncertain terms flagged
- [ ] result.json honest; exit 0 on clean IR

## Runtime contract
Skill at /skills/weekly-skill; input /input/case.json + task.md + material; work
/app/work; output /app/output/result.json preserving every output_contract field +
case_id. No pre-baked translations; honest success/partial/failed with limits.
Resources ≤50 UTF-8 text files, ≤500KB each, ≤2MB total, no binaries/symlinks/
__pycache__ (PYTHONDONTWRITEBYTECODE=1).

## GitHub bonus (+5)
GITHUB_URL.txt at package root: line 1 public GitHub tree URL (git_sync), line 2
SKILL.md. Opens without login.