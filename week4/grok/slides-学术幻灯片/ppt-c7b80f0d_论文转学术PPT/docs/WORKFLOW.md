# WORKFLOW — arena-paper-to-ppt

## 1. Read the actual paper
- `figkit.load_case("/input")` → case_id, task_md, output_contract, audience/duration/
  slide_count.
- Locate + READ the paper (pdf/md/txt), tables/figure data, and template .pptx if given.
- Register sources (paper sections/figures/tables; template) with locators.

## 2. Plan & fill the Deck IR (Agent judgment)
- Extract main line; plan backbone pages (question/method/result/limitation/conclusion).
- One claim/page; source-bound bullets (source + source_locator); data-bound or cited
  figures; notes (add, not repeat); evidence_strength; qa[]; template constraints.
- Save `deck_ir.json` under /app/work.

## 3. Assemble (deterministic)
```
PYTHONDONTWRITEBYTECODE=1 python assemble_deck.py --ir deck_ir.json --input /input --out /app/output [--template /input/template.pptx]
```
validate_deck → build_deck (python-pptx, template inheritance) → check_deck (count/
titles/notes/font-ladder/overflow/footer/figures) → export_deck (office-renderer true
PDF/PNG or honest labelled fallback) → outline.md + provenance.json (page_map) →
result.json (output_contract + case_id + page_map + deck_info + deck_check).
Exit 0 when validation ok; exit 2 honest partial.

## 4. Local edit & version
- Edit the IR, re-run; record provenance.changes[] {what, why, before, after}. The pptx
  stays editable per page; never break the master/template.

## 5. Verify
- Backbone + one claim/page; page_map traces every page to paper locators; numbers/
  units/figure refs match; notes add value; deck_check pass; export honest; result honest.