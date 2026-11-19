---
name: grant-proposal-writing
description: Grant proposal writing with defensible necessity, verifiable innovation vs prior work, one-to-one goal/content/route/indicator alignment, and traceable references; editable deliverable + alignment checks + result.json. Use for the "基金申请书写作" workorder (kind=grant_proposal).
---

# 基金申请书写作 skill (grant_proposal)

Source-bound academic writing skill. The Agent reads the ACTUAL material and fills
the writing IR (claims+evidence, citations, sections, glossary, revisions, and
domain fields); the engine deterministically validates, builds the editable
deliverable, runs consistency checks, exports and writes result.json. Never add
facts outside the material; never fabricate citations/numbers.

## Focus (rubric)
- 立得住: necessity argues why worth doing & why now (others' progress, gap, why us), not policy slogans.
- 说得准: innovation states difference vs specific prior work; no unverifiable '首次/国际领先/填补空白'.
- 对得上: goals, content, technical route, assessment indicators correspond one-to-one.
- 查得到: key claims & references traceable.

## Scope / trigger
Use when the case asks for 基金申请书写作 (workorder kind=grant_proposal). IN: this writing
task + source-binding + editable delivery. OUT: unrelated tracks (data-viz
algorithms, experimental design, PPT software), per the statement.

## Inputs (runtime)
`/input/case.json` (copy case_id; read output_contract/audience/genre/format),
`/input/task.md`, actual materials (docx/pdf/csv/images) + template if provided.
Read files; trust content over labels.

## Workflow (detail: docs/WRITING_WORKFLOW.md)
1. Read & register sources with precise locators.
2. Fill writing IR per `rules/rules_grant_proposal.md` (claims+evidence+strength,
   citations, sections, glossary, numbers, revisions, domain fields; uncertainty +
   human_confirm for gaps).
3. `python assemble_write.py --ir writing_ir.json --input /input --out /app/output`
   → validate → build (md+docx / mindmap / benchmark) → consistency checks →
   export (office-renderer, honest fallback) → result.json.
4. Source-preserving edit: edit IR, re-run; keep revisions/change log for rollback.

## Domain rules
See `rules/rules_grant_proposal.md`. Key:
- Derive necessity from field status/bottleneck/applicant's prior observation.
- Converge to answerable, bounded scientific questions; decompose into assessable goals.
- Align goal-content-route-indicator tuples; check completeness (no orphan goal/route/indicator).
- State innovation against cited prior work; keep references traceable; flag missing applicant evidence.

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
- [ ] necessity defensible
- [ ] innovation verifiable vs prior work
- [ ] goal/content/route/indicator aligned
- [ ] references traceable; editable output
- [ ] result.json honest (status/sources/uncertainty/change_log); claim_map complete


## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

组织方输入修订v1：三案例公开补充写作要求与七要素/计划一致性约束。它不是现实资助机构政策；原论文和既有成果归外部作者，真实申请人证据仍明确缺失。详见运行时case.json和organizer-workorder.json。

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
