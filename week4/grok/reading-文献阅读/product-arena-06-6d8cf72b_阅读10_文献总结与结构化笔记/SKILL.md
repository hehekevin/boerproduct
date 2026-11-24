---
name: arena-summary-notes
description: Source-bound structured literature summary and notes — read the ACTUAL organizer paper/workorder files under /input and produce section-aligned notes (research_question/data/methods/results/conclusion/limitations), one grounded result per requested note field with paragraph locators, verbatim quotes, reported-vs-inferred tagging and reported/not_reported/source_conflict/extraction_failed/insufficient_evidence status; deterministic stdlib engine checks field coverage and claim support and builds notes.json + paper-card markdown + result.json. Use for the "阅读10文献总结与结构化笔记" workorder (kind=summary_notes).
---

# 文献总结与结构化笔记 skill (summary_notes)

Source-bound reading skill. The Agent reads the ACTUAL material and fills the notes
IR (field-aligned items + claims with support + section alignment); `assemble.py`
deterministically validates coverage/locators/status and builds an editable paper
card + structured notes + honest result.json. Output triad: 解析结果 / 证据与边界 /
运行状态. The skeleton follows the PAPER's own sections, not a generic template.

## Focus (rubric)
- 对得上: notes skeleton aligned to the paper's actual section order (sections[]
  with paragraph_ids); per-section purpose/method/result/conclusion where present.
- 留得住: research question, data, method CONDITIONS, main findings AND limitations
  all recorded — especially the premises under which conclusions hold.
- 找得回: every note item carries exact section/paragraph/page locator + verbatim
  quote; reported vs inferred explicitly tagged; speculation never written as fact.
- 用得上: uniform field dictionary → notes.json is searchable/comparable across
  papers; claims with subclaim support degrees for downstream verification.

## Scope / trigger
Use when the case asks for 文献总结 / 结构化笔记 / paper card (kind=summary_notes).
Only given local material; no online retrieval; no generic template summaries.

## Inputs (runtime) — READ THESE ACTUAL FILES FIRST
1. `/input/case.json` — copy case_id, read output_contract.
2. `/input/task.md` — requested note fields / card schema / summary scope.
3. Workorder files when present: `target-fields.json` / `note-fields.json` /
   `workorder.json` (requested note field_ids). Engine auto-reads them for coverage.
4. ALL material files. Register every file actually used in sources[] (id + real path).

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_arena_read.py --input /input --out /app/output --work /app/work`
Auto-registers sources from the ACTUAL /input papers+workorders, auto-fills the complete reading IR
into /app/work (requested fields/claims with EXACT [Pn] quote locators; honest not_reported /
insufficient_evidence for missing), runs the SAME validate+build path as the package assembler, and
ALWAYS writes an honest result.json (try/except fallback preserves every output_contract key +
case_id) — even on empty input or failure. Never fabricated. THEN, within remaining budget, refine
the auto-filled IR in /app/work and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/<ir>.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory /input; open case.json + task.md + workorder + material; map the paper's
   real section structure first.
2. Fill IR per rules/rules_summary_notes.md: sources[], sections[] (id/title/level/
   paragraph_ids), items[] (one per requested field_id: value, kind reported|inferred,
   status, evidence[{source, paragraph_id, quote}], condition where relevant),
   claims[] (text + subclaims[{text, support, evidence}]), unanswered_parts,
   uncertainty, provenance.
3. Run exactly:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output`
   → validation.json → notes.json + summary_notes_result.md (paper card) →
   provenance.json (record_map + source sha256) → result.json.
4. Exit 0 = validation ok; exit 2 = errors → fix IR, re-run. Save honest partial
   early; budget 64 requests / 900 s; improve incrementally.

## IR schema (minimal)
```json
{"ir_version":"1.0","case_id":"...","kind":"summary_notes",
 "sources":[{"id":"S1","path":"paper.md"}],
 "sections":[{"id":"SEC3","title":"Results","level":1,"paragraph_ids":["P5"]}],
 "items":[{"field_id":"limitations","value":"...","kind":"reported","status":"reported",
   "evidence":[{"source":"S1","paragraph_id":"P6","quote":"verbatim..."}]}],
 "claims":[{"id":"C1","text":"...","subclaims":[{"text":"...","support":"supports",
   "evidence":[{"source":"S1","paragraph_id":"P5","quote":"..."}]}]}],
 "unanswered_parts":[],"uncertainty":[],"provenance":{}}
```
Default requested fields (when no workorder): research_question, data, methods,
results, conclusion, limitations. Status vocabulary per item: reported |
not_reported | source_conflict | extraction_failed | insufficient_evidence.
Gap statuses carry NO value + human_confirm:true. support ∈ supports | partial |
insufficient | unrelated | contradicts; "supports" requires evidence.

## Domain rules
See rules/rules_summary_notes.md (field dictionary, section alignment, conditions,
reported vs inferred, claim support, gap handling).

## Scripts & dependencies
assemble.py (CLI), arena_read_engine.py (validate_ir + coverage + build), readkit.py
(claim/support validation), figkit.py (case/result/provenance). Python 3.10+ stdlib only.

## Outputs (/app/output)
notes.json (fields + sections + claims), summary_notes_result.md (editable paper
card with per-field evidence), reading_ir.json, provenance.json, validation.json,
result.json (all output_contract fields + case_id, honest status/sources/uncertainty).

## Error handling (docs/ERROR_HANDLING.md)
Field absent (e.g. no limitations section) → not_reported + human_confirm, never
invent; unreadable material → extraction_failed + reason; conflicting reports →
source_conflict + both locators; inferred note → kind=inferred + uncertainty.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/summary_notes/`: input/ (incl. target-fields.json workorder) + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/summary_notes/ir.json --input examples/summary_notes/input --out /tmp/demo_sn`

## Self-check
- [ ] read ACTUAL /input workorder + material; sources registered with real paths
- [ ] one item per requested note field; coverage complete or unanswered_parts flagged
- [ ] skeleton matches paper's own sections; method conditions + limitations preserved
- [ ] every reported item has paragraph locator + verbatim quote; inferred tagged
- [ ] claims: support vocabulary valid; supports has evidence
- [ ] result.json honest; exit 0 on clean IR

## Runtime contract
Skill at /skills/weekly-skill; input /input/case.json + task.md + material; work
/app/work; output /app/output/result.json preserving every output_contract field +
case_id. No pre-baked notes; honest success/partial/failed with limits. Resources
≤50 UTF-8 text files, ≤500KB each, ≤2MB total, no binaries/symlinks/__pycache__
(PYTHONDONTWRITEBYTECODE=1).

## GitHub bonus (+5)
GITHUB_URL.txt at package root: line 1 public GitHub tree URL (git_sync), line 2
SKILL.md. Opens without login.