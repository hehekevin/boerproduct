# Workflow — analysis-data-viz

Runtime: input /input, work /app/work, output /app/output.

1. **Inventory.** `w4kit.list_materials('/input')`; read case.json + task.md.
2. **Read material.** Open the dictionary + real table. Confirm column meaning, units,
   grouping, missing/outlier caliber, and the analysis intent (distribution/comparison/
   correlation/trend/composition).
3. **Choose + fill IR** (viz_ir.json) per rules/rules_data_viz.md: sources[], datasets[],
   charts[] each with chart_type, real x/y/group_by columns, labels+units, caption (n +
   error-bar definition), rationale (and not-recommended types), width_mm. uncertainty for
   ambiguous caliber/encoding.
4. **Run.**
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir viz_ir.json --input /input --out /app/output`
   Engine renders editable data-bound SVG (+ optional 300 dpi PNG), builds data_map +
   provenance, writes charts.json + report.md + result.json.
5. **Inspect.** validation.json; charts.json (status, n_glyphs, n_rows_skipped_missing,
   series_names, png_status, data_map); open the SVG; result.json status.
6. **Iterate honestly.** Fix column/type/encoding errors and rerun. Skipped missing rows or
   ambiguous caliber → partial + human_confirm. Save partial early; never fabricate a figure.

## Self-test (SYNTHETIC example)
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/data_viz/ir.json --input examples/data_viz/input \
  --out w4/.tmp_analysis/challenge-9562cc8d
```
Expect exit 0, validation errors = [], status success (clean 10-row example). SVG is text
(editable); PNG (if matplotlib present) is a runtime binary in the out dir, not the package.