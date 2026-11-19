# SYNTHETIC EXAMPLE — reference_manage (interface demo, NOT a formal answer)

Tiny synthetic manuscript + library demonstrating DOI/title normalization, dedup
(ref1/ref3 share a DOI -> merged), GB/T 7714 formatting, and in-text<->list
consistency (ref4 uncited -> flagged). All records are invented for illustration.

Run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/reference_manage/ir.json \
  --input examples/reference_manage/input \
  --out /tmp/arena_refmanage_demo
```

Expected: exit 0, validation ok; artifacts references.md, references.bib,
references.docx, citation_map.json, dedup_report.json, consistency.json, result.json.
dedup_report shows 4 input -> 3 unique (1 merged); consistency shows ref4 uncited.