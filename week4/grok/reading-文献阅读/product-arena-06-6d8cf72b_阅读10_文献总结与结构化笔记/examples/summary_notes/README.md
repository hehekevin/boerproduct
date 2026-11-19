# SYNTHETIC example — summary_notes

Interface demonstration ONLY. The "paper" in input/material.md is fabricated toy
text, not a real publication and not a formal case answer. Real cases are supplied by
the platform at evaluation time.

Run from the package root:
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/summary_notes/ir.json --input examples/summary_notes/input --out /tmp/demo_sn
```
Expected: exit 0, validation ok, notes.json covers the 6 requested fields from
input/target-fields.json, claim C1 subclaim support=supported with evidence,
result.json status success.