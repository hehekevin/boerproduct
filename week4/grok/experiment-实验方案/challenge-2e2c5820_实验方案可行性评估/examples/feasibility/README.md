# SYNTHETIC EXAMPLE — feasibility

Labelled EXAMPLE only; NOT an official case and NOT a prepared answer.
input/ holds a fabricated protocol + inventory; ir.json was filled from those files.
It deliberately includes a blocker (ethanol 800>500 mL), a risk (3.7/4 h = 92.5%
utilization) and a not_reported item (spectrophotometer absent from inventory) to
demonstrate honest verdicts and partial status. Re-run:

```
PYTHONDONTWRITEBYTECODE=1 python ../../assemble.py --ir ir.json --input input --out out
```