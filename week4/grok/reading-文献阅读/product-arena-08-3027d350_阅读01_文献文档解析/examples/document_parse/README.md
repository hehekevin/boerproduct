# SYNTHETIC example — document_parse

Interface demonstration ONLY. The "paper" in input/material.md is fabricated toy
text, not a real publication and not a formal case answer. Real cases are supplied
by the platform at evaluation time.

Run from the package root:
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/document_parse/ir.json --input examples/document_parse/input --out /tmp/demo_dp
```
Expected: exit 0, validation ok, fields.json with 6 requested fields, result.json
status success. input/target-fields.json demonstrates the workorder coverage check.