# SYNTHETIC example — translation

Interface demonstration ONLY. The source text in input/material.md is fabricated toy
text, not a real publication and not a formal case answer. Real cases are supplied by
the platform at evaluation time.

Run from the package root:
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/translation/ir.json --input examples/translation/input --out /tmp/demo_tr
```
Expected: exit 0, validation ok, translation_check.json n_issues=0 (glossary locked,
numbers 100/10/95/500/70 and citations [1]/[2,3] preserved), bilingual.json aligned
1:1 with P1-P3, result.json status success.