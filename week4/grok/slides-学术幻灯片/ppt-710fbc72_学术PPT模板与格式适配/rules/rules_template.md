# DOMAIN RULES — PPT template & format adaptation
(kind = `template_adaptation`)

Stably apply a given master/layout template to paper content: real inheritance,
layout constraints, font/color, figure fitting, batch consistency, clean export.
"Looks like a PPT" is not enough — the master/layout/placeholder inheritance must
be real and checkable.

## 1. Template application (real inheritance)
- Read the provided template's master, layouts and placeholders; write content into
  the CORRECT layout (title/content/picture/section), inheriting theme fonts/colors.
- Record `provenance.template_inheritance` (page → layout name) so inheritance is
  auditable. If a placeholder is missing, use a documented fallback (textbox at the
  layout's body region) — never silently drop content or overwrite the master.
- Apply to ALL pages (cover to conclusion), not just the first few.

## 2. Layout constraints
- Fixed body region: position/align elements inside it; handle long titles (wrap or
  shorten with note), multi-figure side-by-side, cross-page consistency.
- Explainable font & spacing ladder: title > body > caption > footer; never shrink
  below min_pt to force-fit; on overflow cut/split and record the change.

## 3. Font & color
- CJK+Latin pairing; theme color + accent; contrast & print readability. On missing
  font, fall back to an available CJK font and record font_used (no box glyphs, no
  layout collapse).

## 4. Figure adaptation
- Scale figures to the container preserving aspect (no distortion); keep axes/legend
  readable; unify figure numbers with in-text refs; handle vector+bitmap mix.
- Data-bound charts redrawn from source; cited originals inserted as-is; never a
  placeholder or stretched image.

## 5. Batch consistency
- Uniform footer, page number, title position, whitespace, font ladder across ALL
  slides; after batch processing verify file integrity + export (check_deck).

## 6. Export rendering (cross-cutting)
- pptx and exported PDF/PNG must agree; record font substitution / image loss /
  notes misplacement in export_report; use office-renderer; honest fallback if absent.

## 7. Self-check
- [ ] master/layout/placeholder inheritance real & recorded for every page
- [ ] content/numbers/figure numbers match source; figures undistorted & readable
- [ ] font ladder & spacing consistent; no overflow / unreadable text / box glyphs
- [ ] footer/page numbers/title position uniform across all slides
- [ ] export matches pptx; deviations recorded; change log kept