# SYNTHETIC EXAMPLE — paper_to_ppt (interface demo, NOT a formal answer)

Tiny synthetic paper (Sec1-5) + Fig1 data (data.csv) demonstrating paper->deck
conversion: narrative backbone (question/method/result/limitation/conclusion), one
claim per page, every bullet traced to a paper paragraph or the data table, a
data-bound figure (no placeholder), speaker notes, and a source-bound outline.md.

Run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble_deck.py \
  --ir examples/paper_to_ppt/deck_ir.json \
  --input examples/paper_to_ppt/input \
  --out /tmp/arena_paper2ppt_demo
```

Expected: exit 0, validation ok; deck.pptx (6 slides) + outline.md + provenance.json
(page_map) + deck_check.json + export_report.json + result.json. Locally without
office-renderer, PDF/PNG are honest labelled layout previews (status partial); at
runtime with office-renderer they are true renders (status success).