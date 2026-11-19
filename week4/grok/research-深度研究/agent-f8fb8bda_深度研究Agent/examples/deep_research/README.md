# SYNTHETIC EXAMPLE - deep_research

Labelled EXAMPLE only; NOT an official case and NOT a prepared answer.
input/ holds a fictional 8-document corpus (evening blue light & sleep onset);
ir.json was filled from those actual example files. Every quote is an exact
substring of a [P#] paragraph, so the engine re-verifies it. Re-run:

```
PYTHONDONTWRITEBYTECODE=1 python ../../assemble.py --ir ir.json --input input --out out
```

The example deliberately includes a conflict (CF1), gaps (G1/G2) and a duplicate
record (R7) to demonstrate honest screening and bounded synthesis.
