---
name: ppt-template-format-adaptation
description: Apply a given master/layout PPT template to paper content with real, auditable inheritance — correct layout/placeholder filling, theme fonts/colors, layout constraints and font ladder, aspect-preserving figure fitting, batch consistency (footer/page numbers/title position) across all slides, and export rendering that matches the PPTX; delivers editable PPTX plus true PDF/PNG previews and a verifiable result.json. Use when the task asks to adapt content to a specified template / enforce format / batch-consistency / fix export rendering.
---

# PPT template & format adaptation skill

Stably apply a provided master/layout template to paper content so the inheritance
is **real and checkable**, not "looks like a PPT". Adds: template master/layout/
placeholder inspection + auditable inheritance map, layout-constraint & font-ladder
engine, aspect-preserving figure fitting, batch consistency across ALL slides, and
a pptx-vs-export render check.

## Scope
- IN: template application, layout constraints, font/color, figure adaptation,
  batch consistency, export rendering (cross-cutting).
- OUT: content science judgment beyond source-binding, paper prose, data-viz algorithms.

## Trigger
Use when the case asks to adapt paper content to a specified template / enforce
format / batch consistency / fix export (workorder `template_adaptation`).

## Inputs (runtime)
`/input/case.json` (copy `case_id`; read `output_contract`), `/input/task.md`, actual
paper/tables, and the **provided master/layout template .pptx** (required for this
workorder; if absent, create a programmatic master and record that). Read files.

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_slides.py --input /input --out /app/output --work /app/work`
Auto-registers sources from the ACTUAL /input materials, auto-fills a complete source-bound IR
into /app/work, runs the SAME validate+build path as the package assembler, and ALWAYS writes an
honest result.json (try/except fallback preserves every output_contract key + case_id) — even on
empty input or failure. Judgment it cannot verify is flagged human_confirm; never fabricated.
THEN, within remaining budget, refine the auto-filled IR in /app/work and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble_deck.py --ir /app/work/<ir>.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/DECK_WORKFLOW.md)
1. **Inspect template**: read master/layouts/placeholders; register in `sources[]`;
   set `template` (theme font, cjk font, title/body/min pt, accent, footer).
2. **Fill Deck IR** (`rules/rules_template.md`): map each page to the CORRECT layout;
   source-bound claim/bullets/figures; notes; `uncertainty[]` for template gaps.
3. **Validate+build+check+render+result**:
   `python assemble_deck.py --ir deck_ir.json --input /input --out /app/output --template /input/template.pptx`
   - build_deck inherits layouts/placeholders + theme fonts/colors; records
     `provenance.template_inheritance` (page→layout) for audit; fallback textbox only
     when a placeholder is missing (documented).
   - font ladder (never below min_pt); overflow → cut/split + record; figures
     aspect-preserved, axes/legend readable, numbers unified with refs.
   - batch consistency: footer/page number/title position/whitespace on ALL slides.
   - check_deck verifies inheritance + consistency; export_deck renders true PDF/PNG
     (office-renderer) and records font substitution/image loss/notes misplacement.
4. **Local edit & version:** edit IR, re-run; `provenance.changes[]`; never break master.
5. **result.json**: every `output_contract` field + `case_id`, honest `status`,
   `sources`, `provenance.page_map` + `template_inheritance`, `uncertainty`,
   `change_log`, `deck_check`, `export_check`.

## Scripts & dependencies
`assemble_deck.py`, `deckkit.py`, `build_deck.py` (python-pptx), `check_deck.py`,
`export_deck.py`, `figkit.py`, `render_chart.py`.
Deps: Python 3.10+, python-pptx, matplotlib, numpy, Pillow; office-renderer for true
render. CJK auto-fallback (record font_used).

## Outputs (/app/output)
`deck.pptx`, `deck.pdf` + `slide-*.png`, `deck_ir.json`, `provenance.json`
(page_map + template_inheritance), `validation.json`, `deck_check.json`,
`export_report.json`, `result.json`.

## Error handling (docs/ERROR_HANDLING.md + DECK_WORKFLOW §4)
Missing layout/placeholder → documented fallback + record; font missing → CJK
fallback (no box glyphs); overflow → cut/split (never below min_pt); figure source
invalid → cite/flag (no distortion/placeholder); export failure → honest fallback +
partial; batch integrity verified after processing. Save partial early.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/deck/`: template-based 6-slide deck with inheritance map, font ladder,
footer/page numbers and a fitted data figure. Run:
`python assemble_deck.py --ir examples/deck/deck_ir.json --input examples/deck/input --out /tmp/demo`
Interface demonstration only.

## Self-check
master/layout/placeholder inheritance real & recorded for every page; content/
numbers/figure numbers match source; figures undistorted & readable; font ladder/
spacing consistent; footer/page numbers/title uniform across all slides; export
matches pptx with deviations recorded; change log kept; result.json honest.

## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Concrete editable presentation task
Concrete organizer-frozen slide task: actual master/layout-based editable template, actual starting deck where edit/adapt requires one, fixed audience/time/slide count and full-source/uncertainty rules. Original16rubric/scientific material unchanged. Technical file checks do not certify presentation science or quality.

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
