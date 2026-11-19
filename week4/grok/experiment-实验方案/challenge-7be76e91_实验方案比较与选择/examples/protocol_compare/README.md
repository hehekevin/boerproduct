# SYNTHETIC EXAMPLE — protocol_compare

Labelled EXAMPLE only; NOT an official case and NOT a prepared answer.
input/ holds three fabricated candidate plans; ir.json was filled from those files.
The top-two weighted margin (A vs C) is < 0.05, so the recommendation is weight-
sensitive (human_confirm) and status is partial — demonstrating honest defensibility.
Re-run:

```
PYTHONDONTWRITEBYTECODE=1 python ../../assemble.py --ir ir.json --input input --out out
```