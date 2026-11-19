# DOMAIN RULES — Scientific data charts
(kind = `source_value_chart`)

The deliverable is a chart whose every mark returns to a source cell. Apply these
when binding data and checking annotations (rubric: 数值与图元一致、标注校验、源数据关联).

## 1. Bind to the real table
- Set `chart.data_path` to the actual CSV/XLSX/JSON; `x/y/series/error/n` to real
  column names. Read the header first; do not assume column order.
- The renderer records `provenance.data_map[glyph] = {file,row,column,value,…}`
  for every bar/point/cell/wedge. This is the bidirectional trace: figure→data and
  data→figure. Keep it; it is the verifiability evidence.
- **Never type numbers by hand into the figure.** If a value is not in the table,
  it must not appear.

## 2. Data → glyph mapping correctness
- Bar height / point y / cell color / wedge angle must equal the source value
  (renderer reads the column directly). After any data edit, re-run assemble so
  glyphs, legend and data_map stay in sync.
- **Units & magnitude**: put the unit on the axis (`y_label` + `unit`); keep the
  source's scale (do not rescale silently). If the source is log-scale, set the
  axis accordingly and note it.
- **Error bars**: set `error` column + `error_kind` (sd/sem/ci95/range). The meaning
  must match the source caption; SD ≠ SEM. If unknown, set `error_kind:unknown` and
  flag in uncertainty rather than guessing.
- **Sample size**: carry `n` column; mention n in caption if the source does.
- **Significance**: only draw brackets the source actually reports
  (`chart.significance[]` with a,b,p,label). Do not compute or invent p-values
  (statistics is out of scope for this skill).

## 3. Legend / series alignment
- Legend is generated from the `series` column's unique values, in data order,
  with the palette assigned deterministically — legend and glyphs cannot drift.
- Colorblind-safe palette default (okabe_ito); keep category count == legend count.
- For multi-panel, label panels A,B,C… and keep each panel's legend local.

## 4. Annotation checklist (six checkpoints)
- [ ] axis labels + units present and correct magnitude
- [ ] tick range covers data without truncation misleading the reader
- [ ] legend entries == series categories, colors match glyphs
- [ ] error bar meaning stated (sd/sem/ci) and matches source
- [ ] significance markers only if reported; n stated if reported
- [ ] scientific entity names (gene/protein/species/compound) spelled as in source
- [ ] CJK labels render (font fallback), not boxes

## 5. Editable + export
- `figure.svg` keeps text as text (`svg.fonttype:none`) — editable, not outlined.
- Export PNG at ≥300 dpi, PDF with embedded fonts (`pdf.fonttype:42`); EPS/TIFF if
  the journal requires. Run export_check and resolve fails.