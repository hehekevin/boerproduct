---
name: research-translation-writing
description: Translate research outputs across genres/audiences (paper→public science, report→proposal) keeping it readable yet accurate — audience adaptation, evidence-preserving selection, evidence-matched claim strength, consistent terminology; editable deliverable + result.json. Use for the "科研成果转化写作" workorder (kind=sci_translation).
---

# 科研成果转化写作 skill (sci_translation)

Source-bound academic writing skill. The Agent reads the ACTUAL material and fills
the writing IR (claims+evidence, citations, sections, glossary, revisions, and
domain fields); the engine deterministically validates, builds the editable
deliverable, runs consistency checks, exports and writes result.json. Never add
facts outside the material; never fabricate citations/numbers.

## Focus (rubric)
- 读得懂: target reader understands without extra background (no unexpanded abbreviations/unexplained formulas/jargon).
- 留得住: key conclusions/data/limits/sample/metric口径/figure refs preserved; drop redundancy not evidence.
- 说得准: claim strength matches source (no correlation→causation, preliminary→definitive); one term one meaning.
- 接得住: genre conventions of the target form met.

## Scope / trigger
Use when the case asks for 科研成果转化写作 (workorder kind=sci_translation). IN: this writing
task + source-binding + editable delivery. OUT: unrelated tracks (data-viz
algorithms, experimental design, PPT software), per the statement.

## Inputs (runtime)
`/input/case.json` (copy case_id; read output_contract/audience/genre/format),
`/input/task.md`, actual materials (docx/pdf/csv/images) + template if provided.
Read files; trust content over labels.

## Workflow (detail: docs/WRITING_WORKFLOW.md)
1. Read & register sources with precise locators.
2. Fill writing IR per `rules/rules_sci_translation.md` (claims+evidence+strength,
   citations, sections, glossary, numbers, revisions, domain fields; uncertainty +
   human_confirm for gaps).
3. `python assemble_write.py --ir writing_ir.json --input /input --out /app/output`
   → validate → build (md+docx / mindmap / benchmark) → consistency checks →
   export (office-renderer, honest fallback) → result.json.
4. Source-preserving edit: edit IR, re-run; keep revisions/change log for rollback.

## Domain rules
See `rules/rules_sci_translation.md`. Key:
- Identify audience knowledge/purpose/needs; set explanation depth/term density/analogy/examples/length.
- Prioritize must-keep (conclusions/limits/method points/data) vs compressible vs deletable; never drop evidence.
- Keep numbers/units/comparisons/limits; match claim strength to source; unify terminology.
- Adapt to target genre structure; record what was compressed/removed and why.

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
- [ ] readable for target audience
- [ ] evidence/limits preserved
- [ ] claim strength matches source
- [ ] genre-appropriate; editable output; change log
- [ ] result.json honest (status/sources/uncertainty/change_log); claim_map complete


## Week4 concrete input interface (organizer revision)
组织方为本题准备 3 个固定案例。每个案例包含任务说明、科研材料、必要的输入约束和评分所需的证据范围；案例会以相同内容分别交给基础 Agent 和加载参赛 Skill 的 Agent。你不需要自带正式测试案例，也不需要提交预先写好的答案。

平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
