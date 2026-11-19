---
name: academic-ppt-generate-edit
description: Generate and edit source-bound, template-compliant academic presentations from a real paper — main-line page planning, one claim per page, correct numbers/figure refs, speaker notes, data-bound or cited figures, version-safe local edits, editable PPTX plus true rendered PDF/PNG previews and a verifiable result.json. Use when the task asks to build or edit an academic talk / defense / group-meeting / review deck from paper material.
---

# Academic PPT generation & editing skill

Turn a real paper into a **clear, evidence-traceable, editable, template-compliant**
talk. Adds capabilities the base agent lacks: source-bound Deck IR (page→claim→
evidence), narrative page planning, template layout/placeholder inheritance,
data-bound figure insertion (no placeholders), speaker notes, overflow/font-ladder
guards, batch footer/page-number consistency, version-safe local edit, and a
pre-export render check.

## Scope
- IN: academic page generation, content edit, figure insert, deck iteration,
  template constraint + export render.
- OUT: paper deep-read/literature review, data-viz algorithms, prose polishing,
  PPT software development.

## Trigger
Use when the case asks to generate/edit an academic presentation from paper or
research material (workorder `academic_ppt`).

## Inputs (runtime)
`/input/case.json` (copy `case_id`; read `output_contract`, audience/duration/
slide_count), `/input/task.md`, actual paper PDF/tables, and the **provided template
.pptx** if present. Read files; trust content over labels.

## Workflow (detail: docs/DECK_WORKFLOW.md)
1. **Read & register sources** (paper sections/figures/tables; template) with locators.
2. **Plan & fill Deck IR** (`rules/rules_ppt_generate.md`): backbone
   question→method→result→limitation→conclusion; one `claim`/page; `role`,`layout`;
   source-bound `bullets`; `figures` (data-bound `chart` or cited `image_path`);
   `notes`; `evidence_strength`; audience/time/slide_count; `uncertainty[]`.
3. **Validate+build+check+render+result**:
   `python assemble_deck.py --ir deck_ir.json --input /input --out /app/output [--template /input/template.pptx]`
   - python-pptx inherits template layouts/placeholders + theme fonts/colors;
     claim as title; bullets; figures aspect-preserved; notes; footer+page number.
   - check_deck: count/titles/notes/font-ladder/overflow/footer/figures/inheritance.
   - export_deck: office-renderer → true PDF + per-slide PNG (honest labelled
     fallback if renderer absent).
4. **Local edit & version:** edit the IR, re-run; record `provenance.changes[]`
   (what/why/before/after) for comparability + rollback; never break the master.
5. **result.json**: every `output_contract` field + `case_id`, honest `status`,
   `sources`, `provenance.page_map`, `uncertainty`, `change_log`, `deck_check`,
   `export_check`.

## Scripts & dependencies
`assemble_deck.py`, `deckkit.py` (stdlib validation), `build_deck.py` (python-pptx),
`check_deck.py`, `export_deck.py`, `figkit.py`, `render_chart.py` (data-bound figures).
Deps: Python 3.10+, python-pptx, matplotlib, numpy, Pillow (preinstalled);
office-renderer (LibreOffice) for true PDF/PNG. CJK font auto-fallback.

## Outputs (/app/output)
`deck.pptx` (editable), `deck.pdf` + `slide-*.png` (true render or labelled fallback),
`deck_ir.json`, `provenance.json` (page_map), `validation.json`, `deck_check.json`,
`export_report.json`, `result.json`.

## Error handling (docs/ERROR_HANDLING.md + DECK_WORKFLOW §4)
Missing figure/bitmap-only → cite original or state limit (no placeholder/invented
curve); missing number → keep source or flag; template gap → documented fallback;
font missing → CJK fallback; overflow/page-over → cut/split (never below min_pt);
export failure → honest fallback + partial. Save partial early.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/deck/`: input/case.json + material.txt + data.csv + deck_ir.json.
`python assemble_deck.py --ir examples/deck/deck_ir.json --input examples/deck/input --out /tmp/demo`
Produces a 6-slide committee talk with a data-bound result figure and notes.
Interface demonstration only.

## Self-check
Backbone + one claim/page; numbers/refs/captions match source; notes correspond;
template inherited on all pages; font/overflow/footer consistent; export matches
pptx; page_map + change log complete; result.json honest.

## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Concrete editable presentation task
Concrete organizer-frozen slide task: actual master/layout-based editable template, actual starting deck where edit/adapt requires one, fixed audience/time/slide count and full-source/uncertainty rules. Original16rubric/scientific material unchanged. Technical file checks do not certify presentation science or quality.

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
