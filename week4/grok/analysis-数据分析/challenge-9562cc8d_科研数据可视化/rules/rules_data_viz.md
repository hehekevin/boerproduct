# Domain rules — data_viz (科研数据可视化)

Goal: a figure where every visual element corresponds to a source data row, the chart type
fits the data + intent, and the deliverable is publication-ready and replayable.

## 1. Confirm data caliber before plotting
- Read the dictionary: column meaning, units, grouping, what missing/outlier/duplicate mean.
- Decide how missing/outliers/duplicates were handled (clean first via sibling skill if
  needed); state the caliber in the caption. Never plot a missing value as 0.

## 2. Chart selection (match data structure + purpose)
- continuous vs continuous, correlation → scatter; trend over ordered x → line.
- categorical comparison → bar (length encoding, zero baseline); distribution of one
  numeric variable → histogram; group distribution comparison → box.
- composition → stacked bar with caution; do NOT use pie/angle/area to exaggerate differences.
- unordered categories → never a line; time series → never unordered parallel bars.
- Write a rationale: why this type, and which types are NOT recommended and why.

## 3. Encoding honesty
- Prefer position/length over area/angle. Bars MUST start at zero (engine enforces for
  bar/histogram); if a axis is truncated or log-transformed, label it explicitly.
- Map color to a real grouping column; legend names must equal the actual group values.
- Too many categories → histogram/box/facet or aggregate; do not cram unreadable bars.
- Large magnitude differences → consider log axis (labelled) or faceting, not a broken axis.

## 4. Annotation & caption (readable independent of the text)
- Axis labels WITH units; title; legend; sample size n; statistical method if aggregated.
- Error bars MUST be defined: sd vs se vs ci95 — say which in the caption (engine draws the
  chosen kind and tags data-error-kind). Never leave an error bar undefined.

## 5. Readability
- Colorblind-safe Okabe-Ito palette (engine default); distinguishable in grayscale.
- Font sizes legible at single-column width (~85 mm) / double (~180 mm); set width_mm.
- Minimal gridlines, adequate margins, panel labels/order if faceted.

## 6. Publication export
- Authoritative artifact = editable SVG (real selectable <text>, named groups, vector).
- Optional PNG at ≥300 dpi via matplotlib; if unavailable, honest fallback (SVG only) —
  never claim a PNG that was not rendered. PNG is a RUNTIME output (/app/output), never
  shipped inside the skill package (binary). Embed/avoid missing fonts; handle CJK labels.

## 7. Data binding & provenance (the core guarantee)
- Every data glyph carries data-row (single row) or data-rows (aggregate contributors) +
  data-value/data-x/data-y; charts.json data_map maps glyph_id → dataset_id + row index(es)
  + the plotted values. provenance.json maps each glyph to its source file.
- A reviewer must be able to pick any point/bar and find its exact source row(s).

## 8. Missing / failure honesty
- Missing/non-numeric x or y → row skipped AND counted (n_rows_skipped_missing); chart
  status partial. No plottable rows / empty / unreadable dataset → insufficient_evidence.
- Record uncertainty + human_confirm for ambiguous encoding or caliber. Result status honest.