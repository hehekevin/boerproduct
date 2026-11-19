# SYNTHETIC EXAMPLE — intro_related (interface demo, NOT a formal answer)

Tiny synthetic literature (3 refs) demonstrating claim-citation binding, grouped
Related Work, a research gap derived from cited limitations, and a proposed
contribution bound to gap evidence (this-work results absent -> human_confirm).

Run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/intro_related/ir.json \
  --input examples/intro_related/input \
  --out /tmp/arena_intro_demo
```

Expected: exit 0, validation ok; manuscript.md + manuscript.docx with Introduction /
Related Work / Research Gap / Contributions; provenance.json claim_map + research_gap;
number_issues empty (0.92 / 0.80 declared).