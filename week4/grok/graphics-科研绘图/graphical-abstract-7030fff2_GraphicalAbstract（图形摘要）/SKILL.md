---
name: graphical-abstract-figure
description: Generate and edit a source-bound, editable single-page Graphical Abstract compressing research question, method, core result and conclusion into a self-consistent visual summary with correct entities/relations/data encoding, panel reading order, scale bars/units, layered editable SVG plus compliant PNG/PDF exports and a verifiable result.json. Use when the task asks for a graphical abstract or single-page visual summary of a study.
---

# Graphical Abstract skill

Produce a **single-page, source-bound, editable** visual summary in reading order
problem → method → core result → conclusion. Every entity, relation and number is
traceable to the source; the result panel's visual encoding matches the data; the
layout is deterministic (same input → same structure). Adds: panel–point mapping,
four-element coverage check, data-bound result panel, multi-panel layout,
provenance and export compliance check.

## Scope
- IN: single-page graphical abstract; panel–point mapping; entities/spatial
  relations; data encoding + legend; layout/hierarchy; editable source + export.
- OUT: paper prose, statistical analysis, experimental design.

## Trigger
Use when the case asks for a Graphical Abstract / single-page visual summary
(workorder `graphical_abstract`).

## Inputs (runtime)
`/input/case.json` (copy `case_id`; read `output_contract`), `/input/task.md`, actual
materials (paper PDF/text, result tables) under `/input`. Read files; trust content
over labels.

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_graphics.py --input /input --out /app/output --work /app/work`
Auto-registers sources from the ACTUAL /input materials, auto-fills a complete source-bound IR
into work/figure_ir.json, runs the SAME validate+build path as the package assembler, and ALWAYS writes an
honest result.json (try/except fallback preserves every output_contract key + case_id) — even on
empty input or failure. Judgment it cannot verify is flagged human_confirm; never fabricated.
THEN, within remaining budget, refine /app/work/figure_ir.json and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/figure_ir.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. **Read & register sources** (paper + result tables) with locators.
2. **Panel–point map + IR** (`rules/rules_graphical_abstract.md`):
   - panels A–D as `groups` kind `panel` in reading order (problem/method/result/
     conclusion); decide on-figure vs caption-only info;
   - problem/method panels: entities + semantic relations (mechanism/schematic
     grammar, compartments);
   - result panel: bind a `chart` to the real result table so glyphs carry
     data_map; encoding + legend + units match source; scale bar/condition labels
     if provided;
   - conclusion: one source-bound claim;
   - `uncertainty[]` for missing key numbers or ambiguity.
3. **Validate + render + export + check**:
   `python assemble.py --ir figure_ir.json --input /input --out /app/output`
   - `render_diagram.py`+`svgkit.py` lay out panels in reading order with named
     layers, semantic arrows, reserved legend; result panel data-bound;
     consistent PNG/PDF; `export_check.py` (dpi/size/fonts/editable/layers).
   - For a chart-heavy abstract, `render_chart.py` multi_panel is available.
4. **Source-preserving edit:** change a result value/label in the IR or table,
   re-run; result panel + legend + exports update together. Log changes.
5. **result.json**: every `output_contract` field + `case_id`, honest `status`,
   `sources`, `uncertainty`, `change_log`, `provenance` (element_map + data_map),
   `validation`, `export_check`.

## Scripts & dependencies
`assemble.py`, `figkit.py` (stdlib), `render_diagram.py`, `svgkit.py`,
`render_chart.py`, `export_check.py`.
Deps: Python 3.10+, matplotlib, numpy, Pillow (preinstalled). CJK auto-fallback.
Presets: `journals.json`, `palettes.json` (colorblind + grayscale-safe).

## Outputs (/app/output)
`figure.svg` (layered editable), `figure.png`, `figure.pdf` (+eps/tiff),
`figure_ir.json`, `provenance.json`, `validation.json`, `export_report.json`,
`result.json`.

## Error handling (docs/ERROR_HANDLING.md)
Missing key number / entity ambiguity / text overflow / font missing / canvas
over-limit / export failure → identify, 处置, record, honest `status`. Never
fabricate numbers. Save partial early.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/mechanism/` (panel entities + semantic relations + legend) and
`examples/chart/` (data-bound result panel). Run:
`python assemble.py --ir examples/mechanism/figure_ir.json --input examples/mechanism/input --out /tmp/demo`
Interface demonstration only; not a formal case result.

## Self-check
Four elements present in reading order; caption-only info excluded; entities/
relations/data traceable; result encoding+legend+units match source; scale bar/
conditions if in source; grayscale-safe; stable layout; editable SVG + compliant
exports; provenance complete; honest result.

## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

组织方具体输入修订
Concrete source-bound drawing workorder: graphical_abstract. Primary biological sources for figure03; actual source data for charts. Original own16rubric unchanged. Real editable SVG/PNG/PDF and source-preserving edit required; scientific judgement remains native/LLM Judge, not a literal quote or export pass.

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
