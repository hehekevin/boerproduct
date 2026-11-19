# SYNTHETIC example — logic_argument_review (interface demo, NOT a formal answer)

All material here is fabricated for demonstration only and is clearly marked
SYNTHETIC. Real contest cases are supplied by the organizer at evaluation time.

## Contents
- input/case.json — demo case_id + output_contract
- input/task.md — demo task statement
- input/manuscript.md — tiny fake manuscript with deliberate reasoning defects
- ir.json — agent-style IR with 2 arguments, 1 consistency pair, 2 findings

## Run
```
PYTHONDONTWRITEBYTECODE=1 python ../../assemble.py --ir ir.json --input input --out /tmp/demo-logic
```

## Expected result
- exit 0, validation errors = []
- status = partial (L2: no quantitative results provided → insufficient_evidence)
- A1: causal gap (cell association → patient causation, two named missing links)
- A2: fallacy argument_from_ignorance (no toxicity assessment → "safe")
- K1: inconsistent (safety claim vs unassessed toxicity)
- 0 locator issues; outputs: review.json, checklist.csv, report.md,
  provenance.json, result.json