# analysis-data-viz (challenge-9562cc8d)

Source-bound Skill for the Bohrium weekly contest ANALYSIS track — 科研数据可视化.
Agent reads the actual organizer data + dictionary under /input, chooses chart types with
rationale, fills an IR; a deterministic stdlib engine renders editable SVG charts where
every glyph carries data-row attributes tracing to source rows (data_map), plus optional
300 dpi PNG with honest fallback. Writes provenance + honest result.json. Not pre-baked figures.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
See SKILL.md, rules/rules_data_viz.md, docs/WORKFLOW.md, docs/ERROR_HANDLING.md.

## Files
SKILL.md; assemble.py; analysis_engine.py; w4kit.py; rules/rules_data_viz.md; docs/;
examples/data_viz/ (SYNTHETIC input/ + ir.json + README).

## Dependencies
Python 3.10+ standard library for the authoritative editable SVG (no third-party needed).
matplotlib OPTIONAL — only for 300 dpi PNG previews; honest fallback to SVG if absent.
See requirements.txt.

## Scope & limits
- chart types: scatter, line, bar (mean/sum/median/count + sd/se/ci95 error bars),
  histogram, box; group_by → multi-series with matching legend.
- Colorblind-safe Okabe-Ito palette; zero baseline for bars; units + error-bar definition
  required in caption. Every glyph bound to source row(s) via data_map.
- Does NOT do statistical method innovation, experiment design, paper writing, or raster
  image post-processing/beautification. Faceting/3D/insets not implemented (state limit).
- PNG is a runtime binary output (/app/output), never shipped in the package.

## Self-check
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/data_viz/ir.json --input examples/data_viz/input \
  --out w4/.tmp_analysis/challenge-9562cc8d
```
Expect exit 0, no validation errors, status success; SVG text editable; data_map present.
Delete any __pycache__; keep PNG out of the package. Hard limits: ≤50 UTF-8 text files,
≤500KB each, ≤2MB total, no binaries/symlinks.