# SYNTHETIC EXAMPLE — param_optimize

Labelled EXAMPLE only; NOT an official case and NOT a prepared answer.
input/ holds fabricated literature/device/cost material + a 5-row pilot table;
ir.json was filled from those files. Temperature is a reported optimum (matches the
observed best 55 C / 7.9); pH is an inferred suggestion (human_confirm) to demonstrate
the reported/inferred distinction and honest partial status. Re-run:

```
PYTHONDONTWRITEBYTECODE=1 python ../../assemble.py --ir ir.json --input input --out out
```