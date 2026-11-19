---
name: arena-polish
description: Source-bound academic language polishing (写作02学术语言润色, kind=polish). The Agent reads the ACTUAL organizer text under /input, fills a segment-level IR (original<->revised + change_type + reason), and a deterministic stdlib engine validates meaning/number/citation preservation, builds an editable polished.md + polished.docx + track_changes.json, and writes an honest result.json. Use when the workorder asks to polish/proofread academic language (grammar, clarity, terminology, tone) while preserving meaning, hedges, data, units and citations. NOT whole-paragraph rewrites or writing advice.
---

# 学术语言润色 skill (polish)

Source-bound, segment-level academic polishing. The Agent does the linguistic
judgment (what to fix and why); the engine deterministically checks that nothing
was broken (numbers, units, citation markers, figure pointers, hedge strength) and
builds editable deliverables + provenance. Never fabricate; never silently
strengthen/weaken a claim.

## Focus (rubric)
- 改得对: real grammar/syntax/collocation/punctuation fixes, not paraphrase masking.
- 说得像: target register/genre; terminology uniform across the whole text.
- 没改坏: original meaning, hedge strength, data, units, citation numbers and figure
  pointers preserved (engine preservation check).
- 讲得清: every edit has original + revised + change_type + reason so a third party
  can judge whether the edit should stand.

## Scope / trigger
Use when the case asks for 学术语言润色 / academic polishing / proofreading
(workorder kind=polish). IN: segment-level edit + preservation + editable delivery.
OUT: content generation, reference management, LaTeX compilation, PPT (other tracks).
Do NOT rewrite when the user only asks a content question.

## Inputs (runtime)
`/input/case.json` (copy `case_id`; read `output_contract`, audience/genre/language/
style rules), `/input/task.md`, and the ACTUAL text material (md/txt/docx/pdf/LaTeX
fragment) + glossary/style guide if provided. READ the files; trust content over
labels. Never assume the text from its filename.

## Workflow (detail: docs/WORKFLOW.md)
1. Read & register sources with precise locators (section/paragraph/sentence).
2. Build a glossary; segment the text; fill `segments[]` per
   `rules/rules_polish.md`: `{id, original, revised, change_type, reason,
   meaning_preserved, source, locator}`. Declare `numbers[]` from the material.
   Minimal-edit principle: keep hedges, causality-vs-correlation, negation, quantifiers.
3. Run:
   `python assemble.py --ir writing_ir.json --input /input --out /app/output`
   → validate (writekit + arena_write_engine) → preservation + number-consistency
   checks → build polished.md + polished.docx + track_changes.json → provenance.json
   → honest result.json.
4. Source-preserving edit: edit the IR, re-run; keep `revisions[]`/`provenance.changes[]`.

## IR schema (kind=polish)
```
ir_version "1.0", case_id, kind "polish", title, audience, genre,
sources[] {id, locator, kind, version, values[]},
glossary[] {term, render, source},
numbers[] {value, unit, source, locator},
segments[] {id, original, revised, change_type, reason, meaning_preserved, source, locator},
claims[] {id, text, type, evidence[]{source, locator, strength, supports}, citation_ids[]},
revisions[] {id, location, before, after, reason, status, source},
uncertainty[] {item, reason, impact, handling}, provenance{pipeline, changes[]}
```
change_type ∈ grammar/syntax/clarity/terminology/tone/punctuation/minimal_edit/cohesion/register.

## Kind rules
See `rules/rules_polish.md`. Key: segment-level (not whole-paragraph) edits; preserve
numbers/units/citations/figure refs exactly; preserve hedge strength; terminology
uniform via glossary; every edit justified; gaps/overclaims flagged human_confirm
(not "fixed" by inventing evidence).

## Scripts & dependencies
`assemble.py` (CLI), `arena_write_engine.py` (validate+build, shared across the 5
arena writing kinds), `writekit.py` (cross-cutting writing checks, claim_map,
number-consistency), `docxkit.py` (stdlib md + valid editable OOXML docx),
`w4kit.py` (case/result/provenance). Deps: Python 3.10+ stdlib only. No python-docx,
no network. Run with `PYTHONDONTWRITEBYTECODE=1`.

## Outputs (/app/output)
`polished.md` (full polished text + change log), `polished.docx` (editable),
`track_changes.json` (segments + preservation issues), `writing_ir.json`,
`provenance.json` (claim_map + segment_map), `validation.json`, `result.json`
(every output_contract field + case_id, honest status/sources/uncertainty/change_log,
extra_checks.preservation_issues + number_issues).

## Error handling (docs/ERROR_HANDLING.md)
Missing/unclear original → state gap, polish only supported segments, flag
human_confirm; terminology conflict → surface in uncertainty; overclaim in source →
keep author wording, flag (do not strengthen/weaken); encoding/mixed-script →
normalize conservatively, note limits; over-length → segment, never drop evidence.
Save honest partial early; never fabricate.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/polish/`: input/case.json + task.md + material.txt + ir.json + README.
`python assemble.py --ir examples/polish/ir.json --input examples/polish/input --out /tmp/demo`
Interface demonstration only.

## Self-check
- [ ] every segment has original + revised + change_type + reason
- [ ] preservation_issues empty (numbers/units/citations/figure refs intact)
- [ ] number_issues reviewed; hedge strength unchanged
- [ ] terminology uniform (glossary); editable md+docx
- [ ] result.json honest (status/sources/uncertainty/change_log); segment_map complete

## Week4 concrete input interface (organizer revision)
组织方为本题准备 3 个固定案例。每个案例包含任务说明、科研材料、必要的输入约束和评分所需的证据范围；案例会以相同内容分别交给基础 Agent 和加载参赛 Skill 的 Agent。你不需要自带正式测试案例，也不需要提交预先写好的答案。

平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-segment results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.