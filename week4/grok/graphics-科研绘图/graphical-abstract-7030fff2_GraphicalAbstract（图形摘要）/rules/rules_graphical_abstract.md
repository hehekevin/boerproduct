# DOMAIN RULES — Graphical Abstract
(kind = `graphical_abstract`)

A single-page visual summary: research question → method → core result →
conclusion, in a self-consistent visual language that a reader can both skim and
audit back to the source. Focus: four-element coverage, correct entities/relations/
data encoding, stable reproducible layout, editable source.

## 1. Panel–point mapping (what goes on the figure)
- Build a "panel → key point" map before drawing:
  - **Problem** panel: the question / system / gap (entities + context).
  - **Method** panel: the approach / route / workflow (steps, apparatus, design).
  - **Result** panel: the core quantitative finding (a small chart or encoded marks).
  - **Conclusion** panel: the takeaway / implication (one claim, source-bound).
- Decide what MUST be on the figure vs what belongs only in the caption. Do not
  cram every detail; the abstract is a summary, not the whole paper.
- Model panels as `groups` kind `panel` (A,B,C,D) in reading order
  (problem→method→result→conclusion); the layout places them in that order.

## 2. Entities & spatial relations
- Molecules/cells/tissues/materials/devices/samples: correct hierarchy and scale;
  no entity confusion or level misplacement. Interaction directions correct.
- Use the mechanism/schematic grammar for the problem/method panels (semantic
  arrows, compartments) — a graphical abstract is not a decorative infographic.

## 3. Data encoding & legend
- Map the core result to a visual channel (color/length/area) with a legend whose
  scale/units match the source data exactly; bind via `chart` for the result panel
  so glyphs carry data_map provenance.
- Colorblind-safe + grayscale-print friendly; include scale bar / units / condition
  labels where the source provides them.

## 4. Layout & visual hierarchy
- Single page; reading order problem→method→result→conclusion; clear focal point;
  whitespace; font hierarchy; no overflow. Same input must reproduce the same
  structure (deterministic layout from the IR, not ad-hoc).
- Panel letters A–D; consistent style across panels.

## 5. Editable source & export
- Layered editable SVG (panels/groups/nodes/edges/labels/legend) + PNG/PDF at the
  target size/resolution; fonts embedded; export_check pass.
- Source-preserving edit: change a result value or label in the IR, re-run; the
  result panel, legend and exports update together.

## 6. Self-check
- [ ] all four elements present and in reading order; caption-only info excluded
- [ ] entities/relations/data traceable to source; no invented numbers
- [ ] result-panel encoding + legend + units match source data
- [ ] scale bar/condition labels present if in source; grayscale-safe
- [ ] stable layout; editable SVG + compliant exports; change log recorded