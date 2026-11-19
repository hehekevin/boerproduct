# SYNTHETIC EXAMPLE — methods_section (interface demo, NOT a formal answer)

Tiny synthetic protocol demonstrating a reproducible Methods/Experiments section:
parameter table with source + reported/not_reported status (weight_decay absent ->
human_confirm), equipment/reagents, statistical methods, dataset version/split, and a
reproducibility checklist with gaps flagged.

Run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/methods_section/ir.json \
  --input examples/methods_section/input \
  --out /tmp/arena_methods_demo
```

Expected: exit 0, validation ok; manuscript.md + manuscript.docx + parameters.csv +
reproducibility.md; number_issues empty; result_extra n_inferred=0, n_not_reported=1.