---
name: apparatus-and-technical-route
description: Generate and edit source-bound, editable experimental apparatus, process-flow, material-flow and technical-roadmap diagrams from real methods/parts-list material, with correct parts/interfaces, flow direction, step numbering matching the text, and stage dependencies; delivers layered editable SVG plus compliant PNG/PDF exports and a verifiable result.json. Use when the task asks for an apparatus/setup diagram, workflow/flowchart, material-flow or research roadmap.
---

# Experimental apparatus & technical route skill

Turn a methods paragraph / parts list / procedure into a **correct, editable,
exportable** apparatus or route diagram. Part names & counts match the source,
connections are only those stated, flow direction is preserved, step numbers match
the text order, and stages show progression. Adds: source-bound IR (parts–
connections–steps–flows), interface-aware layout, numbered flow, stage grouping,
automatic legend, provenance and export compliance check.

## Scope
- IN: apparatus structure, step order, material/energy/info flow, technical route;
  editable source + export.
- OUT: data analysis/fitting, judging experimental soundness, journal typesetting.

## Trigger
Use when the case asks for an apparatus/setup, process flow, material flow or
technical roadmap (workorder `apparatus_and_technical_route`).

## Inputs (runtime)
`/input/case.json` (copy `case_id`; read `output_contract`), `/input/task.md`, actual
materials under `/input`. Read files; trust content over labels.

## Workflow (detail: docs/WORKFLOW.md)
1. **Read & register sources** (parts list / methods / procedure) with locators.
2. **Extract IR** (`rules/rules_apparatus.md`):
   - parts/devices as entities (distinguish same-type parts; interfaces in
     `attributes`); connections (`connects`/`flows_to`) only as stated;
   - steps as entities with `sequence` edges numbered to match text order; stages
     as `groups` kind `stage`; parallel branches / recycle / waste represented;
   - roadmap stages with goal/method/input-output/dependencies;
   - `uncertainty[]` for missing parameters or ambiguous interfaces.
3. **Validate + render + export + check**:
   `python assemble.py --ir figure_ir.json --input /input --out /app/output`
   - `render_diagram.py`+`svgkit.py`: stage/compartment bands or topological flow,
     semantic arrows (flow/sequence/feedback), reserved legend, curved recycle
     routing; layered editable SVG + consistent PNG/PDF; `export_check.py`.
4. **Source-preserving edit:** rename a part / reorder a step in the IR, re-run;
   figure+legend+exports regenerate. Log in `provenance.changes[]`.
5. **result.json**: every `output_contract` field + `case_id`, honest `status`,
   `sources`, `uncertainty`, `change_log`, `provenance.element_map`, `validation`,
   `export_check`.

## Scripts & dependencies
`assemble.py`, `figkit.py` (stdlib), `render_diagram.py`, `svgkit.py`,
`render_chart.py` (data panel if needed), `export_check.py`.
Deps: Python 3.10+, matplotlib, numpy, Pillow (preinstalled). CJK auto-fallback.
Presets: `journals.json`, `palettes.json`.

## Outputs (/app/output)
`figure.svg` (layered editable), `figure.png`, `figure.pdf` (+eps/tiff),
`figure_ir.json`, `provenance.json`, `validation.json`, `export_report.json`,
`result.json`.

## Error handling (docs/ERROR_HANDLING.md)
Missing part parameter / ambiguous interface / conflicting connection / reversed
flow risk / font missing / export failure / canvas overflow → identify, 处置
conservatively (do not invent connections), record, honest `status`. Save partial
early.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/mechanism/` demonstrates the directed-flow / compartment / legend
interface used for apparatus & route figures; `examples/chart/` the data-panel
interface. Run:
`python assemble.py --ir examples/mechanism/figure_ir.json --input examples/mechanism/input --out /tmp/demo`
Interface demonstration only.

## Self-check
Part names/counts match; same-type parts distinguished; connections only as
stated; flow direction correct (no reversed/dead-end); step numbers match text;
stages show dependency order; legend consistent; editable SVG + compliant exports;
provenance complete; honest result.

## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

组织方具体输入修订
Concrete source-bound drawing workorder: apparatus_and_technical_route. Primary biological sources for figure03; actual source data for charts. Original own16rubric unchanged. Real editable SVG/PNG/PDF and source-preserving edit required; scientific judgement remains native/LLM Judge, not a literal quote or export pass.

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
