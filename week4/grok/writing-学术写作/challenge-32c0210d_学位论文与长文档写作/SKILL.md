---
name: thesis-longdoc-writing
description: Thesis / long-document writing with chapter planning tied to outline/argument/word budget, cross-chapter consistency (terms/symbols/definitions/numbering/figure refs/conclusions), localized edits, and full traceability; editable deliverable + consistency checks + result.json. Use for the "学位论文与长文档写作" workorder (kind=thesis_longdoc).
---

# 学位论文与长文档写作 skill (thesis_longdoc)

Source-bound academic writing skill. The Agent reads the ACTUAL material and fills
the writing IR (claims+evidence, citations, sections, glossary, revisions, and
domain fields); the engine deterministically validates, builds the editable
deliverable, runs consistency checks, exports and writes result.json. Never add
facts outside the material; never fabricate citations/numbers.

## Focus (rubric)
- 立得住: chapter plan matches outline, argument chain, word allocation (not material piled into prose).
- 连得上: cross-chapter terms/definitions/symbols/numbering/figure refs/conclusions consistent; find affected paragraphs on edit.
- 改得动: local edits touch only what's needed, preserve author intent; author sees what/why changed.
- 查得清: every claim/citation traceable.

## Scope / trigger
Use when the case asks for 学位论文与长文档写作 (workorder kind=thesis_longdoc). IN: this writing
task + source-binding + editable delivery. OUT: unrelated tracks (data-viz
algorithms, experimental design, PPT software), per the statement.

## Inputs (runtime)
`/input/case.json` (copy case_id; read output_contract/audience/genre/format),
`/input/task.md`, actual materials (docx/pdf/csv/images) + template if provided.
Read files; trust content over labels.

## Workflow (detail: docs/WRITING_WORKFLOW.md)
1. AUTOPILOT FIRST (one command, budget-safe):
   `PYTHONDONTWRITEBYTECODE=1 python auto_write.py --input /input --out /app/output --work /app/work [--kind thesis_longdoc]`
   → auto-registers sources from the ACTUAL /input materials, auto-fills the complete
   writing IR (verbatim sections/claims+evidence/citations/numbers/glossary +
   chapter_plan), runs the SAME validate+build path as assemble_write.py, and ALWAYS
   writes an honest result.json (try/except fallback preserves output_contract +
   case_id; judgment fields flagged human_confirm → status partial). Then, within
   budget, refine /app/work/writing_ir.json and re-run step 3 to improve.
2. Manual path (only if refining): fill writing IR per `rules/rules_thesis_longdoc.md`
   (claims+evidence+strength, citations, sections, glossary, numbers, revisions,
   domain fields; uncertainty + human_confirm for gaps).
3. `python assemble_write.py --ir writing_ir.json --input /input --out /app/output`
   → validate → build (md+docx / mindmap / benchmark) → consistency checks →
   export (office-renderer, honest fallback) → result.json.
4. Source-preserving edit: edit IR, re-run; keep revisions/change log for rollback.

## Domain rules
See `rules/rules_thesis_longdoc.md`. Key:
- Plan chapters with per-section question + required evidence + word budget; avoid overlap/gaps.
- Maintain glossary/symbol/definition/conclusion registries; detect conflicting writes & duplicate definitions; on edit, locate affected cross-refs.
- Apply localized traceable revisions; preserve original phrasing elsewhere.
- Bind claims/citations; flag doubtful refs; run consistency checks.

## Scripts & dependencies
assemble_write.py, writekit.py (validation/consistency/citation/revision), docxkit.py (stdlib md+valid editable docx), mindmap.py (editable SVG/PNG/PDF), benchkit.py (tasks/rubric/eval), figkit.py (case/result). Deps: Python 3.10+ stdlib; matplotlib/numpy/Pillow for mindmap & previews; office-renderer for true docx/pdf render (honest fallback). No python-docx required.

## Outputs (/app/output)
Editable deliverable (manuscript.md+docx, or mindmap.svg/png/pdf, or
tasks.json+rubric.json+reference_answers.md+eval.py), writing_ir.json,
provenance.json (claim_map), validation.json, result.json (+export previews).

## Error handling (docs/ERROR_HANDLING.md + WRITING_WORKFLOW §4)
Missing material/full-text → state gap, write only supported, flag human_confirm;
unverifiable citation → mark uncertain; conflict → surface in uncertainty/待核清单;
template/style gap → documented fallback; over-length → compress without dropping
evidence. Save honest partial early; never fabricate.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/writing/` (prose), `examples/mindmap/`, `examples/bench/`. Run e.g.:
`python assemble_write.py --ir examples/writing/writing_ir.json --input examples/writing/input --out /tmp/demo`
Interface demonstration only.

## Self-check
- [ ] chapter plan matches outline/argument/budget
- [ ] cross-chapter consistency; affected paras found
- [ ] local edits preserve intent; traceable
- [ ] claims/citations traceable; editable output
- [ ] result.json honest (status/sources/uncertainty/change_log); claim_map complete


## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Organizer input repair v1: actual edit targets and offline local workflow scope are explicit in organizer-edit-workorder.json. W16 supplies the complete original source as sectioned editable working chapters, not a completed thesis. Original public scoring is unchanged.

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
