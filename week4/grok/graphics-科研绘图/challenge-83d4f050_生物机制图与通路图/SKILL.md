---
name: bio-mechanism-pathway-figure
description: Generate and edit source-bound, editable biological mechanism and pathway diagrams (genes/proteins/complexes, activation vs inhibition, compartment topology, feedback) from real paper material, delivering a layered editable SVG plus compliant PNG/PDF exports and a verifiable result.json. Use when the task asks for a mechanism diagram, signaling pathway, regulatory network or any biological interaction figure.
---

# Biological mechanism & pathway figure skill

Turn a real mechanism description (paper text / PDF / table) into a **correct,
editable, exportable** pathway diagram. Every node and arrow is traceable to the
source; inhibition is never drawn as activation; compartments and direction are
preserved. This skill adds structure the base agent lacks: a source-bound
intermediate representation (IR), semantic arrow grammar, compartment-aware
layout, automatic legend, bidirectional provenance and a pre-export compliance
check.

## Scope
- IN: mechanism / pathway / regulatory-network figures; entity & interaction
  extraction; compartment layout; legend; editable SVG + PNG/PDF/EPS/TIFF export.
- OUT: statistical analysis, experimental design, paper prose, decorative art.

## Trigger
Use when the case asks to draw/edit a biological mechanism, signaling cascade,
pathway, or interaction network (workorder `biological_mechanism_pathway`).

## Inputs (runtime)
- `/input/case.json` (copy `case_id` verbatim; read `output_contract`), `/input/task.md`.
- Actual materials under `/input` (PDF via pdf-text tool, tables, text). **Read the
  files; never infer content from labels or domain tags.**

## Workflow (detail: docs/WORKFLOW.md)
1. **Autopilot first — one command yields a complete, genuinely-derived baseline.**
   `PYTHONDONTWRITEBYTECODE=1 python auto_graphics.py --input /input --out /app/output --work /app/work [--kind KIND]`
   It reads the ACTUAL `/input` materials, auto-registers `sources[]` with precise
   locators, detects the figure kind, and auto-fills a complete Figure IR from real
   data (CSV/JSON tables via `read_table` → x/y/series/error bound to actual columns
   for charts; symbol/term + verb→type grammar → entities/relations/compartments for
   diagrams), then runs the SAME validate+render+export+check path as `assemble.py`
   and writes an honest `result.json` preserving every `output_contract` key +
   `case_id`. Stdlib only; matplotlib is optional/lazy — a stdlib `svgkit` fallback
   still emits an editable, source-bound `figure.svg` when the renderer is absent.
   The whole pipeline is wrapped: on ANY exception it still writes an honest
   failed/partial `result.json` (never exits without one) and never fabricates data
   (missing/ambiguous → `uncertainty[]` + `human_confirm`, honest status `partial`).
   Use this baseline first to stay within budget; do NOT hand-fill the rigid IR from
   scratch.
2. **Refine the IR** (optional, within budget): open the autopilot's editable
   `work/figure_ir.json` (schema `schema/figure_ir.schema.json`) and improve the
   judgment fields following `rules/rules_mechanism.md`:
   - entities with exact source names, category (gene italic / protein upright /
     complex / compartment), group, source+locator, confidence;
   - relations with correct semantic type + direction (verb→type table in rules);
     inhibition≠activation; regulator→target; evidence strength;
   - compartments as `groups` (membrane/cytoplasm/nucleus) so topology is right;
   - `uncertainty[]` for anything missing/ambiguous (do not fabricate).
3. **Validate + render + export + check** in one command (re-run after refining):
   `python assemble.py --ir work/figure_ir.json --input /input --out /app/output`
   - validates the six checkpoints; renders a **layered editable SVG** (svgkit)
     with compartment bands, semantic arrows (activate filled head / inhibit flat
     bar / bind plain / transport dashed), reserved legend strip, curved feedback
     routing; writes consistent PNG/PDF from the same layout; runs export_check.
4. **Source-preserving edit:** change a label/relation in the IR (or source) and
   re-run assemble; figure+legend+provenance+exports regenerate. Log the change in
   `provenance.changes[]`.
5. **result.json** is written by assemble with every `output_contract` field +
   `case_id`, honest `status`, `sources`, `uncertainty`, `change_log`, `provenance`
   (element_map), `validation`, `export_check`. Partial results state limits.

## Scripts & dependencies
- `auto_graphics.py` (autopilot: auto-extract Figure IR from `/input` + run the
  validate/render/export/result pipeline in one command; stdlib only, matplotlib
  optional with a stdlib svgkit fallback; always writes an honest result.json).
- `assemble.py` (orchestrator), `figkit.py` (case/IR/validation/result, stdlib),
  `render_diagram.py` + `svgkit.py` (diagram + layered SVG), `render_chart.py`
  (chart panels), `export_check.py` (compliance).
- Deps: Python 3.10+, matplotlib, numpy, Pillow (preinstalled scientific-python).
  svgkit/figkit are stdlib-only. CJK font auto-fallback (Noto/WenQuanYi/YaHei).
- Presets: `journals.json` (Nature/Science/Cell/IEEE/Elsevier/ACS), `palettes.json`
  (Okabe-Ito colorblind-safe + semantic edge colors).

## Outputs (/app/output)
`figure.svg` (editable layered source), `figure.png`, `figure.pdf` (+eps/tiff),
`figure_ir.json`, `provenance.json`, `validation.json`, `export_report.json`,
`result.json`.

## Error handling (detail: docs/ERROR_HANDLING.md)
Missing material / ambiguous direction / gene-protein ambiguity / font missing /
export failure / overflow → identify, 处置 conservatively, record in
`uncertainty[]`, set honest `status` (partial if limited). Never fabricate data,
directions or scores. Save an honest partial result early, improve within budget.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/mechanism/`: input/case.json + input/material.txt + figure_ir.json.
Run from the skill dir:
`python assemble.py --ir examples/mechanism/figure_ir.json --input examples/mechanism/input --out /tmp/demo`
Produces an EGFR–MAPK cascade with membrane/cytoplasm/nucleus bands, activation
chain, DUSP6⊣ERK negative feedback, and a legend. `examples/chart/` shows the
data-chart panel interface. These illustrate the interface only.

## Self-check before delivery
Entities verbatim from source; edge types/directions correct; compartments right;
feedback/parallel present; legend matches arrows; editable SVG + compliant
exports; provenance complete; result.json honest.

## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

组织方具体输入修订
Concrete source-bound drawing workorder: biological_mechanism_pathway. Primary biological sources for figure03; actual source data for charts. Original own16rubric unchanged. Real editable SVG/PNG/PDF and source-preserving edit required; scientific judgement remains native/LLM Judge, not a literal quote or export pass.

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
