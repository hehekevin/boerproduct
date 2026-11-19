# SYNTHETIC EXAMPLE — polish (interface demo, NOT a formal answer)

Tiny synthetic input demonstrating the `polish` IR interface and the assemble pipeline.
All text is invented for interface illustration; it is not organizer material and not
a pre-baked contest answer.

Run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/polish/ir.json \
  --input examples/polish/input \
  --out /tmp/arena_polish_demo
```

Expected: exit 0, validation ok, artifacts `polished.md`, `polished.docx`,
`track_changes.json`, `provenance.json`, `validation.json`, `result.json`.
The change log shows segment-level original<->revised with type + reason; numbers
and citation [1] / Figure 2 are preserved (preservation_issues empty).