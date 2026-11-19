# Scientific drawing skill (source-bound, editable, export-compliant)

A reusable Agent skill for the Bohrium Playground graphics track. It converts real
research material into a **correct, editable, submittable** scientific figure and
a verifiable `result.json`.

## What it guarantees
- **Source-bound:** every entity, relation and numeric mark carries a pointer to
  the input material (`provenance.element_map` / `data_map`); nothing invented.
- **Editable:** layered SVG source with named layers, selectable text and
  data-source attributes; change the IR and re-render (no manual redraw).
- **Export-compliant:** PNG/PDF/EPS/TIFF checked for dpi, size, font embedding,
  color space, min font and line width against journal presets.
- **Honest:** `result.json` preserves every `output_contract` field + `case_id`,
  with status, sources, uncertainty and change log; partial results state limits.

## Layout
```
SKILL.md                 entry point (loaded by the Agent)
assemble.py              one-command pipeline: validate -> render -> check -> result
figkit.py                case loading, IR validation, provenance, result.json (stdlib)
render_chart.py          data-driven charts (matplotlib) + bidirectional data map
render_diagram.py        schematics/mechanisms/apparatus/abstract layout + render
svgkit.py                layered editable SVG builder (stdlib)
export_check.py          export compliance checker
schema/figure_ir.schema.json   the IR contract
rules/rules_*.md         domain scientific-correctness rules
docs/WORKFLOW.md         detailed pipeline
docs/ERROR_HANDLING.md   failure modes & handling
palettes.json            colorblind-safe palettes + semantic edge colors
journals.json            journal export presets
examples/                SYNTHETIC minimal interface examples (not formal answers)
```

## Install / dependencies
Python 3.10+ with `matplotlib`, `numpy`, `Pillow` (see requirements.txt; these are
preinstalled in the platform scientific-python runtime). `figkit.py` and
`svgkit.py` are stdlib-only. No other setup; no personal files; no symlinks.

## Quick start
```
python assemble.py --ir <figure_ir.json> --input /input --out /app/output
```
The Agent first fills `figure_ir.json` from the actual material (see SKILL.md and
docs/WORKFLOW.md); assemble then produces all deliverables.

## Reproduce / verify
Re-run the same command with the same IR + source to get the same figure.
`provenance.json`, `validation.json`, `export_report.json` let a reviewer audit
every mark and every export parameter independently.

## Limits
Does not choose statistical methods or compute significance; does not design
experiments; does not write paper prose. Missing/ambiguous input is reported as
uncertainty, never fabricated.