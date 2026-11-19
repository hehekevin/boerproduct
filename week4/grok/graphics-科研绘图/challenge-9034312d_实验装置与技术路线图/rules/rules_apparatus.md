# DOMAIN RULES — Experimental apparatus & technical route
(kind = `apparatus_route`)

For apparatus assembly, process flow, material flow and research-roadmap figures.
Focus: parts & interfaces correct, connections/flow direction correct, step order
matches the text, stages show progression (not a flat list).

## 1. Apparatus structure
- Extract every part from the parts list / assembly description / methods paragraph
  as an entity (category `part`/`device`), with interfaces/ports in `attributes`.
- Distinguish same-type parts (Pump-1 vs Pump-2) — do not merge; label each.
- Connections (`connects`/`flows_to`) must match the described plumbing/wiring;
  **never invent a connection** that the source does not state. Interface alignment:
  connect port-to-port, not box-center-to-box-center semantics.
- Local enlargement / inset: model as a `group` (kind assembly) if the source zooms.

## 2. Process / step order
- Convert the procedure to a numbered flow (`sequence` edges). Numbering must match
  the text order exactly (step 1 = first described action). Main sequence + parallel
  branches + recycle loops + termination all represented.
- Use `groups` kind `stage` for phases; put step entities in their stage.

## 3. Material / energy / information flow
- `flows_to` arrows show material direction; split/merge/recycle/waste outlets all
  drawn with correct direction. A reversed flow arrow or a dead-end arrow is an error.
- Distinguish material (solid), energy (dashed), information (dotted) via edge
  style/legend if the source distinguishes them.

## 4. Technical route / roadmap
- Divide research content into stages with milestones; show each stage's goal,
  method, input/output and dependencies (`sequence`/`causes`), so the reader sees
  progression order, not a parallel bullet list.
- Time/phase axis if the source gives one; keep milestone labels source-bound.

## 5. Legend, editable, export
- Legend for part categories / flow types / stage colors, consistent with the figure.
- Layered editable SVG + PNG/PDF; fonts embedded (CJK fallback); export_check pass.
- Source-preserving edit: rename a part / reorder a step in the IR, re-run.

## 6. Self-check
- [ ] part names & counts match source; same-type parts distinguished
- [ ] every connection stated in source; none invented; interfaces aligned
- [ ] flow direction correct; no reversed/dead-end arrows; recycle/waste present
- [ ] step numbers match text order; stages show dependency order
- [ ] legend consistent; editable SVG + compliant exports