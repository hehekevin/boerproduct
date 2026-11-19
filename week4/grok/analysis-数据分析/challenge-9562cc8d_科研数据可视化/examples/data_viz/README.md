# Example — data_viz (SYNTHETIC)

ALL files here are SYNTHETIC interface-demo data, NOT a formal contest case or answer.

## Contents
- input/case.json — example case_id + output_contract
- input/task.md — example visualization task (Chinese)
- input/dictionary.md — column meaning / units / error-bar convention
- input/series.csv — 10-row two-series table (A/B × 5 x values)
- ir.json — agent-filled IR (grouped scatter + mean bar with SD error bars)

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/data_viz/ir.json --input examples/data_viz/input \
  --out w4/.tmp_analysis/challenge-9562cc8d
```

## Expected
- exit 0; validation errors = []; status success
- chart_scatter_xy.svg + chart_bar_mean_y.svg: editable text, colorblind-safe palette,
  zero-baseline bars, legend names == real groups (A/B), SD error bars tagged
- charts.json: data_map maps every glyph_id -> dataset + row_index/row_indices + values;
  png_status rendered (if matplotlib present) or honest SVG-only fallback
- PNG is a runtime binary in the OUT dir only — never inside the package
- result.json preserves every output_contract key + case_id