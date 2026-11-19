# arena-paper-to-ppt — 论文转学术PPT (kind=paper_to_ppt)

Source-bound paper-to-deck conversion skill for the Bohrium weekly contest
(play.bohrium.com, contest=bohr-product, period 4, grok agent).

## What it does
The Agent reads the ACTUAL paper under `/input`, extracts the narrative main line
(question->method->result->limitation->conclusion), and fills a Deck IR where each
page's claim/bullets/figures trace to a paper paragraph/figure/table. The deterministic
engine (reused ppt-core):
- validates the Deck IR (deckkit: backbone, one claim/page, source binding, template
  font/overflow limits),
- builds an editable PPTX (python-pptx, template inheritance) + source-bound outline.md,
- runs check_deck (count/titles/notes/font-ladder/overflow/footer/figures),
- renders PDF/PNG via office-renderer (true render) or honest labelled fallback,
- writes provenance.json (page_map) + result.json (output_contract + case_id +
  page_map + deck_info + deck_check + honest status).

NOT pre-baked answers: the engine builds from the IR filled from real material. This is
a structural rewrite (paper narrative -> page claims), not paragraph cut-and-paste;
numbers/units/figure refs preserved; no schematic-as-data, no placeholder figures.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble_deck.py --ir <deck_ir.json> --input /input --out /app/output [--template /input/template.pptx]
```
Exit 0 = validation ok; exit 2 = validation errors (honest partial result still written).

## Dependencies
Python 3.10+, python-pptx, matplotlib, numpy, Pillow (preinstalled in the platform
image). office-renderer (LibreOffice) optional for true PDF/PNG (honest fallback
otherwise). See requirements.txt.

## Files
SKILL.md; assemble_deck.py; deckkit.py; build_deck.py; check_deck.py; export_deck.py;
figkit.py; render_chart.py; svgkit.py; journals.json; palettes.json;
schema/deck_ir.schema.json; rules/rules_paper_to_ppt.md; docs/WORKFLOW.md +
ERROR_HANDLING.md; examples/paper_to_ppt/ (SYNTHETIC demo).

## Scope & limits
IN: main-line extraction + page structure + evidence preservation + editable PPTX +
outline + render. OUT: paper deep-read conclusions, figure design/beautification, prose
polishing. Locally without office-renderer, PDF/PNG are honest labelled layout previews
(status partial); at runtime they are true renders (status success). Generated
pptx/pdf/png live in /app/output at runtime, never inside this package.

## Self-check
Run examples/paper_to_ppt/README.md; confirm exit 0, validation ok, 6 slides, deck_check
pass, page_map traces every page, outline.md present, result.json honest. Hard limits:
≤50 UTF-8 text files, ≤500KB each, ≤2MB total, no binaries/__pycache__/symlinks.