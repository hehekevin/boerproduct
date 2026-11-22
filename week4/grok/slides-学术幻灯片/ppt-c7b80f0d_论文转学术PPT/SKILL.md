---
name: arena-paper-to-ppt
description: Convert a provided paper into a source-bound academic slide deck (论文转学术PPT, kind=paper_to_ppt). The Agent reads the ACTUAL paper under /input, extracts the narrative main line (question->method->result->limitation->conclusion), and fills a Deck IR where each page's claim/bullets/figures trace to a paper paragraph/figure/table. A deterministic engine (python-pptx) builds an editable PPTX + source-bound outline.md, runs structure/overflow/figure checks, renders PDF/PNG (office-renderer, honest labelled fallback), and writes provenance.page_map + honest result.json. Use when the workorder asks to turn a paper into a talk/defense/group-meeting deck. Not paragraph-cut-and-paste; numbers/units/figure refs preserved.
---

# 论文转学术PPT skill (paper_to_ppt)

Turn a real paper into a clear, evidence-traceable, editable academic deck. This is a
STRUCTURAL rewrite (paper narrative -> page-level claims), not slicing paragraphs into
slides. Every page's content traces to a specific paper figure/table/section/page;
numbers, units, method names and figure refs are preserved; schematic figures are never
passed off as experimental data.

## Focus (rubric)
- Main line matches the paper's contribution (question/method/result/conclusion), not
  paragraph order.
- Every page traces to a paper figure/table/section/page (provenance.page_map).
- Numbers/units/method names/conclusions match the paper; figure numbering matches
  in-text refs; no schematic-as-data, no others'-results-as-ours.
- Required main-line pages present; speaker notes add (not repeat) page text.
- Editable PPTX opens/plays/edits in the target template/software; export render matches.

## Scope / trigger
Use when the case asks to convert a paper into an academic presentation (workorder
kind=paper_to_ppt; Deck IR kind=paper_to_ppt). IN: main-line extraction + page structure
+ evidence preservation + editable PPTX + outline + render. OUT: paper deep-read
conclusions, scientific figure design/beautification, prose polishing (other tracks).

## Inputs (runtime)
`/input/case.json` (copy `case_id`; read `output_contract`, audience/duration/
slide_count), `/input/task.md`, ACTUAL paper (pdf/md/txt) + tables/figure data, and the
provided template .pptx if present. READ files; trust content over labels.

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_slides.py --input /input --out /app/output --work /app/work`
Auto-registers sources[] from the ACTUAL /input materials, extracts a complete source-bound
Deck IR (pages/claims/bullets/notes/data-bound figures) into work/deck_ir.json, and runs the
SAME validate+build+check+export path as assemble_deck.py. Always writes an honest result.json
(every output_contract key + case_id preserved) — even on empty input or failure. Judgment it
cannot verify is flagged human_confirm; never fabricated. THEN, within remaining budget, refine
work/deck_ir.json and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble_deck.py --ir /app/work/deck_ir.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Read & register sources (paper sections/figures/tables; template) with locators.
2. Plan & fill Deck IR per `rules/rules_paper_to_ppt.md`: backbone
   question->method->result->limitation->conclusion; one `claim`/page; `role`,`layout`;
   source-bound `bullets` (source + source_locator); `figures` (data-bound `chart` or
   cited `image_path`); `notes`; `evidence_strength`; audience/time/slide_count; `qa[]`;
   `uncertainty[]`.
3. Validate+build+check+render+result:
   `python assemble_deck.py --ir deck_ir.json --input /input --out /app/output [--template /input/template.pptx]`
   - python-pptx builds editable deck (claim as title; bullets; figures aspect-preserved;
     notes; footer + page number); inherits template layouts/theme if provided.
   - check_deck: count/titles/notes/font-ladder/overflow/footer/figures.
   - export_deck: office-renderer -> true PDF + per-slide PNG (honest labelled fallback
     if renderer absent; status partial locally, success at runtime).
   - outline.md (source-bound) + provenance.json (page_map) + result.json.
4. Local edit & version: edit the IR, re-run; record provenance.changes[] for rollback.

## IR schema (kind=paper_to_ppt)
```
ir_version "1.0", case_id, kind "paper_to_ppt", title, audience, goal, duration_min,
slide_count_target, template{theme_font, cjk_font, title_pt, body_pt, min_pt, accent,
footer, max_bullets, max_words_per_bullet},
sources[] {id, locator, kind, version},
pages[] {id, role, layout, claim, bullets[]{text, source, source_locator},
         figures[]{ref, chart{...}|image_path, caption, source, source_locator},
         notes, source, source_locator, evidence_strength},
qa[] {question, answer_points[], source, backup_page}, exports[], uncertainty[],
provenance{pipeline, changes[]}
```
role ∈ title/outline/background/question/method/result/discussion/limitation/conclusion/qa/backup/section.

## Kind rules
See `rules/rules_paper_to_ppt.md`. Key: extract main line (not paragraph order); one
claim/page; every bullet/figure binds a paper locator; preserve numbers/units/figure
refs; data-bound figures from real data (no placeholder/invented curve); notes add
transitions/emphasis/Q&A evidence; respect template font-ladder/overflow/footer.

## Scripts & dependencies
`assemble_deck.py`, `deckkit.py` (stdlib validation + page_map), `build_deck.py`
(python-pptx), `check_deck.py`, `export_deck.py`, `figkit.py` (case/result),
`render_chart.py` (data-bound figures), `svgkit.py`. Deps: Python 3.10+, python-pptx,
matplotlib, numpy, Pillow (preinstalled); office-renderer for true PDF/PNG (honest
fallback). CJK font auto-fallback. Run with `PYTHONDONTWRITEBYTECODE=1`.

## Outputs (/app/output)
`deck.pptx` (editable), `outline.md` (source-bound), `deck.pdf` + `slide-*.png` (true
render or labelled fallback), `deck_ir.json`, `provenance.json` (page_map),
`validation.json`, `deck_check.json`, `export_report.json`, `result.json` (output_contract
+ case_id + honest status + provenance.page_map + deck_info + deck_check).

## Error handling (docs/ERROR_HANDLING.md)
Missing figure/bitmap-only → cite original or state limit (no placeholder/invented
curve); missing number → keep source or flag; template gap → documented fallback; font
missing → CJK fallback; overflow/page-over → cut/split (never below min_pt); export
failure → honest fallback + partial. Save partial early; never fabricate.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/paper_to_ppt/`: input/case.json + task.md + paper.txt + data.csv + deck_ir.json
+ README. `python assemble_deck.py --ir examples/paper_to_ppt/deck_ir.json
--input examples/paper_to_ppt/input --out /tmp/demo` (6-slide committee talk, data-bound
Fig1, notes, outline). Interface demonstration only.

## Self-check
- [ ] backbone + one claim/page; main line matches paper contribution
- [ ] every page/bullet/figure traces to a paper locator (page_map)
- [ ] numbers/units/figure refs match paper; no schematic-as-data
- [ ] notes add (not repeat); template font/overflow/footer consistent
- [ ] editable pptx + outline; export honest; result.json status/sources/uncertainty honest

## Week4 concrete input interface (organizer revision)
组织方为本题准备 3 个固定案例。每个案例包含任务说明、科研材料、必要的输入约束和评分所需的证据范围；案例会以相同内容分别交给基础 Agent 和加载参赛 Skill 的 Agent。你不需要自带正式测试案例，也不需要提交预先写好的答案。

平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-page claim results with exact source locators (paper figure/table/section/page) and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.