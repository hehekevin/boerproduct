# DECK WORKFLOW — material → Deck IR → editable PPTX → render → result.json

The Agent does the scientific/organisational judgment (read the real paper, decide
main line, per-page claims, bullets, figure refs, notes, Q&A); the scripts do the
deterministic build, checks, render and result assembly. Never skip source-binding.

## 0. Read actual input
- `/input/case.json` (copy `case_id`, read `output_contract`, audience/duration/
  slide_count), `/input/task.md`. Inventory `/input`; open the paper PDF (pdf-text
  tool / actual PDF), tables, and the **provided template .pptx** if present.
- Register `sources[]` with precise locators (page/section/figure/table/row).

## 1. Plan & fill Deck IR (`deck_ir.json`, schema schema/deck_ir.schema.json)
Follow the skill's `rules/rules_*.md`:
- backbone question→method→result→limitation→conclusion; one `claim` per page;
  `role`, `layout`, source-bound `bullets`, `figures` (data-bound `chart` OR cited
  `image_path`, never placeholder), `notes`, `evidence_strength`.
- audience/goal/duration/slide_count_target; `qa[]` with backup pages (content_org).
- template: use provided master path; font ladder; footer; max_bullets.
- `uncertainty[]` for missing figures/numbers/ambiguous claims (do not fabricate).

## 2. Validate + build + check + render + result (one command)
```
python assemble_deck.py --ir deck_ir.json --input /input --out /app/output [--template /input/template.pptx]
```
- `deckkit.validate_deck`: backbone, one claim/page, bullet/word limits, source
  pointers, figure binding, font ladder, page-count vs time.
- `build_deck` (python-pptx): inherit template layouts/placeholders, theme fonts/
  colors, claim as title, bullets, figures (redraw data-bound via render_chart or
  insert cited image, aspect preserved), speaker notes, footer+page number.
- `check_deck`: slide count, titles, notes, font ladder, overflow, footer/page
  numbers, figures, layout inheritance → deck_check.json.
- `export_deck`: office-renderer → true PDF + per-slide PNG; honest layout-preview
  fallback (labelled) if renderer absent → export_report.json.
- `result.json`: every output_contract field + case_id, honest status, sources,
  page_map (page→source), uncertainty, change_log, deck_check, export_check.

## 3. Source-preserving / local edit & version
Edit the Deck IR (a claim/bullet/figure/notes), re-run assemble; deck + checks +
exports regenerate. Record `provenance.changes[]` (what/why/before/after) so versions
are comparable and rollback possible. Never break the master for later pages.

## 4. Error handling (honest)
- Missing figure / bitmap-only (no data): cite original image or state limit; never
  invent a curve or placeholder.
- Missing number/ambiguous claim: keep source value or flag uncertainty; no rounding
  by impression.
- Template missing layout/placeholder: documented fallback textbox; record.
- Font missing: CJK fallback, record font_used; no box glyphs.
- Overflow / page-count over: cut or split, record; never shrink below min_pt.
- Export failure / no renderer: honest fallback preview + uncertainty; status partial.
- Save an honest partial result.json early; improve within budget (64 req/900 s).

## 5. Self-check before delivery
Backbone + one claim/page; numbers/refs/captions match source; notes correspond;
template inheritance recorded for all pages; font ladder/overflow/footer consistent;
export matches pptx; page_map + change log complete; result.json honest.