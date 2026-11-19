# SYNTHETIC example — nanopublication

Interface demonstration ONLY. The "paper" and DOI in input/material.md are fabricated
toy content, not a real publication and not a formal case answer. Real cases are
supplied by the platform at evaluation time.

Run from the package root:
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/nanopublication/ir.json --input examples/nanopublication/input --out /tmp/demo_np
```
Expected: exit 0, validation ok, nanopubs.json with 3 atomic assertions (each with
minimal quote + locator + provenance), nanopubs.trig parseable TriG, result.json
status success.