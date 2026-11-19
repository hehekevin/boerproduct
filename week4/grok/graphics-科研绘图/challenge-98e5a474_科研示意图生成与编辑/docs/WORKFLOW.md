# WORKFLOW — material → IR → editable source → compliant export

This is the deterministic pipeline every graphics-track skill follows. The Agent
does the **scientific judgment** (reading the real material, deciding entities,
relations, data); the scripts do the **deterministic rendering, validation and
export**. Never skip the source-binding step: a figure whose marks cannot be
traced to the input is not deliverable, however pretty.

## 0. Read the actual input (fact basis)
- Read `/input/case.json` and `/input/task.md`. Copy `case_id` verbatim.
- Inventory `/input` (`figkit.list_materials`). Open every material file that the
  task references: PDF (use the pdf-text tool / actual PDF, not a label), tables
  (CSV/XLSX/JSON), text, images. **Do not infer content from filenames or domain
  tags.** If a domain label conflicts with the actual file, trust the file.
- Record each material in `IR.sources[]` with a precise `locator`
  (file + page/section/row/column) and version/sha256 when available.

## 1. Extract into the Figure IR (`figure_ir.json`)
Fill the IR (schema: `schema/figure_ir.schema.json`). Rules per domain are in the
skill's `rules_*.md`. General invariants:
- **Entities**: exact display names as in the source; never invent gene names,
  concentrations, timepoints or units. Set `category`, `group` (compartment/stage/
  panel), `source` + `source_locator`, `confidence`.
- **Relations**: pick the correct semantic `type` (activates / inhibits / binds /
  modifies / transports / contains / sequence / flows_to / feedback / …) and
  `direction`. Inhibition is NOT activation; upstream/downstream must not reverse;
  containment is not parallel. Cite the source span for each edge.
- **Data (charts)**: bind `chart.data_path` to the real table; set `x/y/series/
  error/error_kind/n` to actual column names. Every glyph will be auto-bound to
  `{file,row,column,value}` by the renderer (bidirectional map).
- **Uncertainty**: list anything missing, ambiguous or conflicting in
  `IR.uncertainty[]` with reason/impact/handling. Do not fabricate to fill gaps.

## 2. Validate before rendering
`python figkit` validation runs inside `assemble.py`. It checks the six rubric
checkpoints: entities present & named; relations typed/directed with existing
endpoints; chart bound to data; legend/annotation consistency; editable SVG
planned; exports present; plus source pointers for verifiability. Fix **errors**
before rendering; record **warnings** as uncertainty if unresolved.

## 3. Render editable source + exports (one command)
```
python assemble.py --ir figure_ir.json --input /input --out /app/output
```
- kind=source_value_chart (or a pure chart) → `render_chart.py` (matplotlib):
  data-driven glyphs, auto legend from series, error bars, significance brackets.
- other kinds → `render_diagram.py`: compartment-aware layout, semantic arrow
  grammar, reserved legend strip; writes a **layered editable SVG** (`svgkit`)
  plus consistent PNG/PDF from the same layout.
- Outputs: `figure.svg` (editable source), `figure.png`, `figure.pdf` (+eps/tiff if
  requested), `figure_ir.json`, `provenance.json`, `validation.json`,
  `export_report.json`, `result.json`.

## 4. Export compliance check
`export_check.py` (run by assemble) verifies DPI, pixel/mm size, PDF font
embedding + selectable text, SVG editable text + layers + source binding, min
font size, line width, color space vs the target preset (`journals.json`).
Read `export_report.json`; fix any `fail`, justify any `warn` in uncertainty.

## 5. Source-preserving edit (required capability)
To change a label/value: edit `figure_ir.json` (or the source table) and re-run
`assemble.py`. The figure, legend, data_map and exports all regenerate from the
IR — no manual redraw. Demonstrate this in the change log
(`IR.provenance.changes[]`: what/why/before/after/confirmed_by).

## 6. Assemble result.json (honest)
`assemble.py` writes `result.json` preserving **every** original
`output_contract` field plus `case_id`, `status` (success/partial/failed/stuck),
`artifacts`, `sources`, `uncertainty`, `change_log`, `provenance`, `validation`,
`export_check`. A partial result must state its limits. Never invent benchmark
scores or software state.

## Budget discipline (runtime: 64 requests / 900 s / 16k tokens per response)
Save an honest partial `result.json` early (after step 2), then improve
incrementally. Prefer one well-formed IR + one assemble run over many redraws.