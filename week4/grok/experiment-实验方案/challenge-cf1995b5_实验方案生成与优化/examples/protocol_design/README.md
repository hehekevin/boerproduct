# SYNTHETIC EXAMPLE — protocol_design

Labelled EXAMPLE only; NOT an official case and NOT a prepared answer.
input/ holds a fabricated 3-paragraph material (literature + device manual + price
contract); ir.json was filled from those actual example files. It deliberately
includes gaps (missing spectrophotometer model, an inferred optimization) to
demonstrate honest partial status. Re-run:

```
PYTHONDONTWRITEBYTECODE=1 python ../../assemble.py --ir ir.json --input input --out out
```