---
name: source-bound-data-chart
description: Generate and edit scientific data charts (bar/grouped bar/line/scatter/box/heatmap/pie/multi-panel) bound cell-by-cell to the real source table, with auto-aligned legend, correct units/error bars/significance, journal styling, editable SVG plus compliant PNG/PDF/EPS/TIFF exports and a verifiable result.json. Use when the task asks to plot, restyle or annotate a data chart from a table or statistical result.
---

# Source-bound scientific data chart skill

Turn a real data table into a **correct, editable, submittable** chart. Every bar,
point, cell or wedge is bound to its exact source `{file,row,column,value}`
(bidirectional map), the legend is generated from the same series mapping so it
cannot drift, and exports are checked against journal parameters before delivery.
This adds capabilities the base agent lacks: cell-level data binding, automatic
legend/series alignment, annotation validation, CJK font fallback, and a
pre-export compliance check.

## Scope
- IN: data-chart generation, style adjustment, annotation validation, source-data
  linkage, editable vector + raster export.
- OUT: choosing statistical methods / computing significance (out of scope),
  experimental design, paper prose.

## Trigger
Use when the case asks to generate/edit/restyle a data chart from a table or
statistical result (workorder `source_value_chart`).

## Inputs (runtime)
`/input/case.json` (copy `case_id`; read `output_contract`), `/input/task.md`, and
the actual table(s) under `/input` (CSV/XLSX/JSON). Read the header; never assume
column order or infer values from labels.

## Workflow (detail: docs/WORKFLOW.md)
1. **Read & register** the table in `sources[]` with locator (file + columns).
2. **Bind the chart** in `figure_ir.json` (`rules/rules_chart.md`):
   `chart.data_path` = real table; `x/y/series/error/error_kind/n` = real columns;
   `x_label/y_label/unit`; `significance[]` only if the source reports it.
   Set style from a journal preset (`journals.json`) or the task's template.
3. **Validate + render + export + check**:
   `python assemble.py --ir figure_ir.json --input /input --out /app/output`
   - `render_chart.py` reads the table and draws glyphs equal to source values;
     records `provenance.data_map[glyph]={file,row,column,value,x,series,error,…}`;
     auto legend from series (colorblind-safe palette); error bars with declared
     kind; significance brackets; multi-panel letters.
   - exports SVG (text editable, `svg.fonttype:none`), PNG ≥300 dpi, PDF embedded
     fonts (`pdf.fonttype:42`), EPS/TIFF if requested; `export_check.py` verifies
     dpi/size/fonts/colorspace/min-font/line-width.
4. **Data-update redraw:** edit the table or IR, re-run assemble; glyphs, legend,
   data_map and exports stay in sync. Log in `provenance.changes[]`.
5. **result.json** written by assemble: every `output_contract` field + `case_id`,
   honest `status`, `sources`, `uncertainty`, `change_log`, `provenance.data_map`,
   `validation`, `export_check`.

## Scripts & dependencies
`assemble.py`, `figkit.py` (stdlib), `render_chart.py` (matplotlib+numpy),
`render_diagram.py`+`svgkit.py` (for schematic panels), `export_check.py` (Pillow).
Deps: Python 3.10+, matplotlib, numpy, Pillow (preinstalled). CJK auto-fallback.
Presets: `journals.json`, `palettes.json` (Okabe-Ito / Tol / sequential / diverging).

## Outputs (/app/output)
`figure.svg`, `figure.png`, `figure.pdf` (+eps/tiff), `figure_ir.json`,
`provenance.json` (data_map), `validation.json`, `export_report.json`, `result.json`.

## Annotation checklist (rules/rules_chart.md)
axis labels+units+magnitude; tick range; legend==series; error-bar meaning
(sd≠sem); significance only if reported; n if reported; entity names as in source;
CJK renders; editable SVG; compliant exports.

## Error handling (docs/ERROR_HANDLING.md)
Missing column/empty/non-numeric → skip glyph, keep rest, record; magnitude/unit
anomaly → keep source value, flag; legend mismatch → rebuild from data; font
missing → fallback; export failure → skip format, keep others. Honest `status`;
never impute or fabricate. Save partial early.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/chart/`: input/case.json + input/data.csv + figure_ir.json.
`python assemble.py --ir examples/chart/figure_ir.json --input examples/chart/input --out /tmp/demo`
Produces a grouped bar chart (Control vs Treatment over Day3/7/14) with SD error
bars and auto legend; each bar traceable to a CSV row. `examples/mechanism/` shows
the diagram interface. Interface demonstration only.

## Self-check
Every glyph returns to a source cell; legend/series aligned; units/error/significance
correct; editable SVG + compliant exports; data_map complete; result.json honest.

## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

组织方具体输入修订
Concrete source-bound drawing workorder: source_value_chart. Primary biological sources for figure03; actual source data for charts. Original own16rubric unchanged. Real editable SVG/PNG/PDF and source-preserving edit required; scientific judgement remains native/LLM Judge, not a literal quote or export pass.

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
