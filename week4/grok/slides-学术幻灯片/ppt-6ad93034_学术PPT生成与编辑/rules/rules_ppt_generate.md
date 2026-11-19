# DOMAIN RULES — Academic PPT generation & editing
(kind = `academic_ppt`)

Turn a paper into a clear, evidence-traceable, editable, template-compliant talk.
Focus: content selection & page order, one claim per page, correct numbers/figure
refs, speaker notes, template inheritance, version-safe iteration, clean export.

## 1. Main line & page planning
- Extract question → method → result → limitation → conclusion as the backbone.
- Decide which results deserve their own page; compress methods to a few lines;
  order figures by narrative (not paper order). Assign each page a `role` and a
  single `claim` (one sentence the page asserts).
- Respect audience / duration / slide_count_target; ~1–1.5 slides per minute.
- First page role=title; include outline/section pages only if they aid navigation.

## 2. Content correctness
- Every number on a page must equal the source (no rounding by impression); cite
  `source`+`source_locator` per bullet and per page.
- Figure refs (Fig3/Table2) must match the paper's numbering; captions match the
  figure; units preserved. Redraw only data-bound charts (bind `chart` to the real
  table); cite original images (`image_path`) when not redrawable — never a
  placeholder or invented curve.
- Keep terminology/symbols identical to the paper.

## 3. Speaker notes
- Notes correspond to the page claim (what to SAY), not a verbatim repeat of
  bullets; include the evidence pointer and any caveat.

## 4. Template & export
- Use the runtime-provided master/layout template; write into the correct layout
  placeholders; keep theme fonts/colors; footer + page number on every slide.
- Font ladder: title > body > caption; never shrink below min_pt to force-fit;
  if overflow, cut content or split the page (record the change).
- Export PDF/PNG via office-renderer; verify no font substitution / overflow /
  cropped image; pptx and export must agree.

## 5. Iteration & version
- Edit via the Deck IR (local edit), re-run assemble; keep `provenance.changes[]`
  (what/why/before/after) so versions are comparable and rollback is possible.
- Never edit the master in a way that breaks later pages; batch-apply rules.

## 6. Self-check
- [ ] backbone covered; page count fits audience/time; one claim per page
- [ ] numbers/figure refs/captions match source; no placeholder figures
- [ ] notes present & correspond to claims; template inherited; footer/page numbers
- [ ] no overflow / unreadable font; export matches pptx; change log recorded