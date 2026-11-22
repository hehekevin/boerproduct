---
name: editable-relationship-schematic
description: Generate and edit source-bound, editable scientific relationship/conceptual schematics (structure, hierarchy, process, containment vs parallel vs directed) from real material, delivering a layered editable SVG plus compliant PNG/PDF/EPS/TIFF exports and a verifiable result.json. Use when the task asks for a schematic, structural diagram, conceptual map or process flow that is not a statistical chart.
---

# Editable relationship / conceptual schematic skill

Turn real material (text / table / sketch) into a **correct, editable, exportable**
schematic. Entities, relations, hierarchy and every number/unit are traceable to
the source; containment is not drawn as parallel, upstream/downstream is not
reversed; the deliverable is a layered editable SVG plus journal-compliant
exports, not a flattened bitmap. Adds: source-bound IR, relation grammar,
hierarchy-aware layout, automatic legend, bidirectional provenance, export check.

## Scope
- IN: relationship/structural/conceptual/process schematics; entity & relation
  extraction; hierarchy & layout; legend; editable source + export adaptation.
- OUT: statistical chart numerics/methods, poster/cover art, paper prose.

## Trigger
Use when the case asks to draw/edit a schematic, structural or conceptual diagram,
or process flow (workorder `editable_relationship_schematic`).

## Inputs (runtime)
`/input/case.json` (copy `case_id`; read `output_contract`), `/input/task.md`, actual
materials under `/input`. Read files; do not infer from labels/domain tags.

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
1. **Read & register sources** with precise locators.
2. **Extract IR** (`rules/rules_schematic.md`): entities (exact names, attributes
   with units, category, group, source+locator); relations with correct semantics
   — containment (`contains`/`part_of`) ⇒ nested boundary, parallel ⇒ siblings,
   causal/temporal/upstream ⇒ directed edge in order; hierarchy depth via
   `groups.parent`; `uncertainty[]` for gaps.
3. **Validate + render + export + check**:
   `python assemble.py --ir figure_ir.json --input /input --out /app/output`
   - `render_diagram.py` + `svgkit.py`: grouped/topological layout, named layers
     (groups/edges/nodes/labels/legend), editable text, data-source attributes,
     reserved legend strip, curved long-edge routing; consistent PNG/PDF.
   - `export_check.py`: dpi/size/fonts/editable-text/layers/min-font/line-width.
4. **Source-preserving edit:** edit a label/relation/group in the IR, re-run;
   all layers and exports regenerate. Log in `provenance.changes[]`.
5. **result.json**: every `output_contract` field + `case_id`, honest `status`,
   `sources`, `uncertainty`, `change_log`, `provenance.element_map`, `validation`,
   `export_check`.

## Scripts & dependencies
`assemble.py`, `figkit.py` (stdlib), `render_diagram.py`, `svgkit.py` (stdlib SVG),
`render_chart.py` (if a data panel is needed), `export_check.py`.
Deps: Python 3.10+, matplotlib, numpy, Pillow (preinstalled). CJK auto-fallback.
Presets: `journals.json`, `palettes.json`.

## Outputs (/app/output)
`figure.svg` (layered editable), `figure.png`, `figure.pdf` (+eps/tiff),
`figure_ir.json`, `provenance.json`, `validation.json`, `export_report.json`,
`result.json`.

## Error handling (docs/ERROR_HANDLING.md)
Missing source / ambiguous relation / hierarchy conflict / label overflow / font
missing / export failure / canvas overflow → identify, 处置, record, honest
`status`. Never invent names/numbers/units. Save partial early.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/mechanism/` (diagram interface: compartments, typed directed edges,
legend) and `examples/chart/` (data-panel interface). Run:
`python assemble.py --ir examples/mechanism/figure_ir.json --input examples/mechanism/input --out /tmp/demo`
Interface demonstration only; not a formal case result.

## Self-check
Entities/relations traceable; containment vs parallel vs directed correct;
hierarchy depth right; no overlap/overflow; legend consistent; sub-figure numbers
if required; editable SVG + compliant exports; provenance complete; honest result.

## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

组织方具体输入修订
Concrete source-bound drawing workorder: editable_relationship_schematic. Primary biological sources for figure03; actual source data for charts. Original own16rubric unchanged. Real editable SVG/PNG/PDF and source-preserving edit required; scientific judgement remains native/LLM Judge, not a literal quote or export pass.

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
