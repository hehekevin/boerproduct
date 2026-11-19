---
name: arena-intro-related
description: Source-bound Introduction + Related Work writing (写作08引言与相关工作写作, kind=intro_related). The Agent reads the ACTUAL provided literature under /input, fills a writing IR (claims+evidence locators, citations[], grouped sections[], research_gap derived from cited limitations, contributions bound to evidence), and a deterministic stdlib engine validates claim-citation binding / gap derivation / number-consistency, builds editable manuscript.md + .docx, and writes provenance + honest result.json. Use when the workorder asks to write an Introduction, organize Related Work, justify a research gap, or state contributions grounded in provided literature. No unsupported claims.
---

# 引言与相关工作写作 skill (intro_related)

Source-bound Introduction + Related Work. The Agent does the scientific writing
judgment (grouping, gap derivation, contribution wording); the engine enforces that
every claim binds to evidence + citations, the gap is derived from cited literature,
contributions bind to evidence, and numbers match the material. Never fabricate
references or unsupported claims.

## Focus (rubric)
- 立得住: background points to a real research thread + concrete unsolved problem,
  not "recently attracted wide attention" filler.
- 分得清: Related Work grouped by problem/method/route with comparison dimensions,
  accurate paraphrase of each work's conclusion/conditions/limits (not abstract stacking).
- 说得实: research gap derived from cited gaps; assertions have evidence or are marked
  author judgment.
- 对得上: contributions correspond to actual method/figures/results; citation coverage
  and metadata verifiable item-by-item.

## Scope / trigger
Use when the case asks for 引言与相关工作写作 / Introduction / Related Work / research
gap / contributions (workorder kind=intro_related). IN: grounded intro+related writing
+ editable delivery. OUT: polishing, reference styling, methods, LaTeX, PPT.

## Inputs (runtime)
`/input/case.json` (copy `case_id`; read `output_contract`, audience/genre/citation
style), `/input/task.md`, ACTUAL provided literature (pdf/md/txt/bib) + any draft
method/results material. READ files; trust content over labels.

## Workflow (detail: docs/WORKFLOW.md)
1. Read & register literature sources with locators; build `citations[]` (accurate
   authors/year/title/journal/DOI from the material).
2. Fill IR per `rules/rules_intro_related.md`: `claims[]`+evidence+strength+citation_ids;
   `sections[]` Introduction / Related Work (grouped) / Research Gap / Contributions;
   `research_gap` {statement, derived_from[citation ids]}; `contributions[]` bound to
   claim_ids/evidence; `numbers[]`; glossary; uncertainty.
3. Run:
   `python assemble.py --ir writing_ir.json --input /input --out /app/output`
   → validate (writekit + arena intro rules) → claim-citation/gap/number checks →
   manuscript.md + manuscript.docx → provenance.json (claim_map + research_gap +
   contributions) → honest result.json.
4. Edit IR, re-run; keep revisions/provenance.changes[].

## IR schema (kind=intro_related)
```
ir_version "1.0", case_id, kind "intro_related", title, audience, genre,
sources[] {id, locator, kind, version, values[]},
citations[] {id, authors, year, title, journal, doi, source},
claims[] {id, text, type, evidence[]{source, locator, strength, supports}, citation_ids[], strength},
numbers[] {value, unit, source, locator}, glossary[] {term, render, source},
required_sections[] ["Introduction","Related Work","Research Gap","Contributions"],
sections[] {id, level, heading, role, paragraphs[]{id, text, claims[], source}},
research_gap {statement, derived_from[]}, contributions[] {id, text, claim_ids[], evidence[], status},
uncertainty[], provenance{pipeline, changes[]}
```

## Kind rules
See `rules/rules_intro_related.md`. Key: every substantive claim binds evidence +
citation_ids; group Related Work by route with comparison dimensions; gap.derived_from
must reference registered citations; contributions bind evidence (proposed vs
result-backed distinguished); no unsupported claims; missing literature → flag.

## Scripts & dependencies
`assemble.py`, `arena_write_engine.py` (shared arena engine), `writekit.py`
(claim/citation/number/terminology checks, claim_map), `docxkit.py` (stdlib md+docx),
`w4kit.py` (case/result). Deps: Python 3.10+ stdlib only. Run with `PYTHONDONTWRITEBYTECODE=1`.

## Outputs (/app/output)
`manuscript.md` + `manuscript.docx` (editable Introduction/Related Work/Gap/
Contributions + References), `writing_ir.json`, `provenance.json` (claim_map +
research_gap + contributions), `validation.json`, `result.json` (output_contract +
case_id + honest status/sources/uncertainty/change_log + extra_checks.number_issues).

## Error handling (docs/ERROR_HANDLING.md)
Empty/insufficient literature → state gap, write only supported claims, flag
human_confirm; citation not findable → mark uncertain, never invent metadata; gap
without basis → flag (do not assert); contribution beyond results → mark proposed +
human_confirm; unknown style → documented fallback. Save honest partial early.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/intro_related/`: input/case.json + task.md + literature.txt + ir.json + README.
`python assemble.py --ir examples/intro_related/ir.json --input examples/intro_related/input --out /tmp/demo`
3 refs, grouped related work, gap derived from ref1/ref2/ref3, proposed contribution flagged.

## Self-check
- [ ] every claim binds evidence + citation_ids; metadata accurate
- [ ] Related Work grouped by route with comparison dimensions
- [ ] research_gap.derived_from references registered citations
- [ ] contributions bound to evidence; proposed vs result-backed distinguished
- [ ] number_issues empty/reviewed; editable md+docx; result.json honest

## Week4 concrete input interface (organizer revision)
组织方为本题准备 3 个固定案例。每个案例包含任务说明、科研材料、必要的输入约束和评分所需的证据范围；案例会以相同内容分别交给基础 Agent 和加载参赛 Skill 的 Agent。你不需要自带正式测试案例，也不需要提交预先写好的答案。

平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.