# DOMAIN RULES — Relationship / conceptual schematics
(kind = `relationship_schematic`)

For structural, conceptual and process schematics (not statistical charts, not
decorative illustration). Focus: correct entities, correct relation grammar,
correct hierarchy, readable layout, editable source.

## 1. Extract entities & relations
- Identify every scientific entity and its attributes (with units) from the text /
  table / sketch; record `source` + `source_locator`.
- Classify relation semantics precisely:
  - **containment** (part_of / contains) ⇒ nested boundary, NOT side-by-side boxes.
  - **parallel / coordinate** ⇒ same-level siblings, NOT nested.
  - **upstream/downstream, causal, temporal** ⇒ directed edge in the right order.
  - Drawing containment as parallel (or vice versa) is a structural error.
- Hierarchy depth must match the source (a sub-sub-component stays inside its
  parent group). Use `groups` with `parent` for nesting.

## 2. Layout & figure grammar
- Partition into regions; align siblings; keep whitespace; avoid overlap, text
  overflow and crossing leader lines. The renderer's grouped/topological layout
  handles this; assign `group` so related entities cluster.
- Font-size hierarchy: title > group label > node label > annotation. Respect
  `min_font_pt` so the figure stays legible at print size.
- Number sub-figures (A,B,…) if the task requires; keep numbering consistent.

## 3. Legend & data mapping
- Any color/shape/size channel must have a legend entry whose meaning matches the
  data/categories; legend count == category count.
- If a value is encoded (length/area/color), bind it to the source and keep units.

## 4. Editable source & export
- Deliver layered SVG (named layers: groups/edges/nodes/labels/legend) with
  editable text and data-source attributes; plus PNG/PDF (and EPS/TIFF if asked).
- Source-preserving edit: change a label in the IR, re-run, all exports update.

## 5. Self-check
- [ ] entities/relations traceable to source; no invented names/numbers/units
- [ ] containment vs parallel vs directed drawn correctly; hierarchy depth right
- [ ] no overlap/overflow/crossing leaders; legible at target size
- [ ] legend consistent; sub-figure numbers present if required
- [ ] editable SVG + compliant exports produced and checked