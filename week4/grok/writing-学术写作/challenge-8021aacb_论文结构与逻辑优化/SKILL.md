---
name: paper-structure-logic-optimization
description: Diagnose and fix paper structure/logic with executable, locatable edit actions — problem定位 to section/paragraph/sentence, argument-chain closure (question-method-result-conclusion), conclusion boundaries; deliver edit plan + revised editable manuscript + result.json. Use for the "论文结构与逻辑优化" workorder (kind=structure_logic).
---

# 论文结构与逻辑优化 skill (structure_logic)

Source-bound academic writing skill. The Agent reads the ACTUAL material and fills
the writing IR (claims+evidence, citations, sections, glossary, revisions, and
domain fields); the engine deterministically validates, builds the editable
deliverable, runs consistency checks, exports and writes result.json. Never add
facts outside the material; never fabricate citations/numbers.

## Focus (rubric)
- 诊得准: locate structure problems to specific section/paragraph/sentence and classify the type.
- 改得动: output executable edit actions (move/merge/split/narrow), not a disconnected rewrite.
- 链得通: question-method-result-conclusion closed loop; each claim has corresponding evidence.
- 结论边界: conclusions bounded by what was actually done.

## Scope / trigger
Use when the case asks for 论文结构与逻辑优化 (workorder kind=structure_logic). IN: this writing
task + source-binding + editable delivery. OUT: unrelated tracks (data-viz
algorithms, experimental design, PPT software), per the statement.

## Inputs (runtime)
`/input/case.json` (copy case_id; read output_contract/audience/genre/format),
`/input/task.md`, actual materials (docx/pdf/csv/images) + template if provided.
Read files; trust content over labels.

## Workflow (detail: docs/WRITING_WORKFLOW.md)
1. Read & register sources with precise locators.
2. Fill writing IR per `rules/rules_structure_logic.md` (claims+evidence+strength,
   citations, sections, glossary, numbers, revisions, domain fields; uncertainty +
   human_confirm for gaps).
3. `python assemble_write.py --ir writing_ir.json --input /input --out /app/output`
   → validate → build (md+docx / mindmap / benchmark) → consistency checks →
   export (office-renderer, honest fallback) → result.json.
4. Source-preserving edit: edit IR, re-run; keep revisions/change log for rollback.

## Domain rules
See `rules/rules_structure_logic.md`. Key:
- Extract claim-evidence pairs; find breaks/jumps/circular reasoning/unsupported claims.
- Check research question贯穿 & contribution matches actual work; section order/space serves argument.
- Produce a locatable edit-action list (from/to/merge/split/narrow) + apply as traceable revisions.
- Re-verify argument chain + conclusion boundary after edits.

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
- [ ] problems located & typed
- [ ] executable edit actions (not rewrite)
- [ ] argument chain closed; conclusion bounded
- [ ] revised editable ms + change log
- [ ] result.json honest (status/sources/uncertainty/change_log); claim_map complete


## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Concrete structural review scope
This revision corrects only wrong historical domain labels and makes the six-dimension source-grounded editing plan explicit. No predetermined defects or scientific answers are supplied. Editable JSON/Markdown suffice; optional PDFs and full unsolicited rewrites are not required.

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
