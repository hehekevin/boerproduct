---
name: analysis-data-viz
description: Build publication-oriented, source-bound scientific charts from the actual organizer data - chart-type selection rationale, honest axes (zero baseline for bars, labelled log), colorblind-safe encoding, units/legend/error-bar definitions, an editable SVG where EVERY glyph carries data-row attributes tracing to a source row (data_map), plus optional 300 dpi PNG with honest fallback. Use when the task is 科研数据可视化 / plotting research data tables.
---

# Research data visualization (科研数据可视化)

A source-bound Skill for the Bohrium weekly contest (analysis track, challenge-9562cc8d).
The agent reads the ACTUAL organizer data + dictionary under /input, chooses chart types
and encodings with a stated rationale, fills a structured IR, and a deterministic stdlib
engine renders editable SVG charts where every data glyph (point/bar/box/bin) carries
data-row / data-rows attributes tracing back to the registered dataset rows (data_map).
Optional matplotlib PNG (300 dpi) is attempted with an honest fallback to SVG. No pre-baked
figures; the chart is recomputed from the real rows each run.

## Focus (rubric points)
- 实际效果: chart type matches data structure + analysis purpose; axes/legend/series match
  the real data columns; every visual element corresponds one-to-one to source data.
- 创新增益: per-glyph data_map (glyph_id → dataset + row_index/row_indices + values), so a
  reviewer can trace any point/bar to its row; chart-choice rationale + not-recommended notes.
- 可靠体验: missing/non-numeric rows skipped AND counted (status partial), never silently
  plotted as 0; empty/unreadable data → insufficient_evidence; matplotlib absent → SVG only.
- 发表级: editable vector SVG (real selectable text, named groups), colorblind-safe Okabe-Ito
  palette, zero baseline for bars, units + error-bar definition in caption, single-column width.

## Inputs (runtime)
- /input/case.json — case_id + output_contract (preserve every key).
- /input/task.md — the concrete visualization task.
- Actual material: data table(s) + dictionary (column meaning, units, grouping, error type).

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_analysis.py --input /input --out /app/output --work /app/work`
Auto-extracts the IR from the ACTUAL /input materials (registers sources + datasets;
reads the data dictionary for units/outcome/group/design; recomputes real statistics
via w4kit.describe/correlation/linreg on the actual rows), runs the engine
(validate_ir + build), and writes a complete honest result.json preserving every
output_contract key + case_id. Judgment fields it cannot verify (expert interpretation,
practical significance) are flagged human_confirm — never fabricated; missing values
are excluded pairwise, never treated as 0, never imputed.
THEN, within remaining budget, refine judgment-heavy fields in /app/work/analysis_ir.json
(interpretations, assumptions, method choices) and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/analysis_ir.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory; register sources[] + datasets[] (real paths/columns).
2. Confirm data caliber (missing/outlier/duplicate handling) and the analysis intent
   (distribution / comparison / correlation / trend / composition). Choose chart type +
   encoding with rationale; fill the IR per rules/rules_data_viz.md.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir viz_ir.json --input /input --out /app/output`
   → validate_ir → render → chart_<id>.svg (+ optional .png) + charts.json (spec + data_map)
   + provenance.json + report.md → result.json.
4. Honest status: success when all charts rendered with no skipped rows/gaps; partial when
   rows skipped (missing), charts insufficient/failed, or uncertainty declared.

## IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto>
kind: "data_viz"
sources: [{id, path, description?}]
datasets: [{dataset_id, source_id, path, columns?}]
charts: [{
  chart_id, chart_type, dataset_id,
  x, y?, group_by?,            # columns from the REAL header
  aggregate?,                  # bar: mean|sum|median|count (default mean)
  bins?,                       # histogram: integer bin count
  error_bars?,                 # bar: sd|se|ci95|none  (DEFINE in caption!)
  title, x_label, y_label,     # include units
  caption,                     # n, error-bar definition, method, units
  rationale,                   # why this chart type; what is NOT recommended and why
  width_mm?, height_mm?        # default 180x120 (single/double column)
}]
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes?}
```
chart_type: scatter | line | bar | histogram | box.
- scatter/line: numeric x + y; group_by → one series per group (legend matches names).
- bar: categorical x; y aggregated per category (or count); error_bars from group stats.
- histogram: numeric x binned into counts. box: group_by (or x) categories, y (or x) values.

## Domain rules
See rules/rules_data_viz.md (chart selection, encoding honesty, annotation, readability,
publication export, data binding, missing handling).

## Scripts & dependencies
assemble.py (CLI), analysis_engine.py (stdlib SVG renderer + data_map + optional matplotlib
PNG), w4kit.py (describe/correlation for aggregates + result.json). Python 3.10+ stdlib for
the authoritative SVG; matplotlib OPTIONAL (PNG only). See requirements.txt.

## Outputs (/app/output)
chart_<id>.svg (editable, data-bound), chart_<id>.png (optional, 300 dpi, runtime only —
NOT shipped in the package), charts.json (spec + series + data_map + png_status),
provenance.json (glyph → source row), report.md, validation.json, result.json.

## Error handling (docs/ERROR_HANDLING.md)
Missing/non-numeric x/y → row skipped + counted (n_rows_skipped_missing), status partial;
no plottable rows → insufficient_evidence; unreadable/empty dataset → insufficient_evidence;
matplotlib missing/failing → png_status records honest fallback, SVG remains authoritative;
too many categories → consider histogram/box or facet (rationale), never cram unreadable bars.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/data_viz/`: input/ (dictionary + 10-row two-series table) + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/data_viz/ir.json --input examples/data_viz/input --out w4/.tmp_analysis/challenge-9562cc8d`
Demonstrates a grouped scatter + a mean bar chart with SD error bars; every glyph in data_map.

## Self-check
- [ ] chart type matches data + intent; rationale (and not-recommended) stated
- [ ] series/legend names == real group values; axes labels carry units
- [ ] bars start at zero; error bars DEFINED (sd/se/ci95) in caption; n stated
- [ ] every glyph has data-row/data-rows; data_map maps glyph → dataset + row + value
- [ ] missing rows skipped AND counted (partial), never plotted as 0
- [ ] editable SVG authoritative; PNG optional with honest fallback; colorblind-safe palette
- [ ] result.json honest; output_contract preserved; no binary shipped in package

## GitHub bonus (+5)
GITHUB_URL.txt: line 1 = public GitHub tree URL, line 2 = SKILL.md. Opens without login.

## Runtime contract
Skill authoring task. Valid frontmatter. No prepared answers. Evaluator installs under
/skills/weekly-skill, runs the Harness on 3 fixed cases (/input → /app/output/result.json
preserving output_contract + case_id). Runtime artifacts may be binary (PNG) and live in
/app/output, NOT in the skill package. Budget 64 requests / 900 s. Resources ≤50 UTF-8 text
files, ≤500KB each, ≤2MB total, no binaries/symlinks/__pycache__.