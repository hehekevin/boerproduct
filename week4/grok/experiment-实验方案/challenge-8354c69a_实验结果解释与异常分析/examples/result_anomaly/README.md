# SYNTHETIC EXAMPLE — result_anomaly

Labelled EXAMPLE only; NOT an official case and NOT a prepared answer.
input/ holds fabricated reference/calibration/log material + a replicate table;
ir.json was filled from those files. Yield r3=9.8 is IQR-flagged with two partially-
supported causes and one unsupported cause; purity is out of tolerance. Unsupported
causes become insufficient_evidence + human_confirm (partial) — demonstrating that a
cause is never asserted as fact without data. Re-run:

```
PYTHONDONTWRITEBYTECODE=1 python ../../assemble.py --ir ir.json --input input --out out
```