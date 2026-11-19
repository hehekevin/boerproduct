# SYNTHETIC example — compliance_check (interface demo, NOT a formal answer)

All material here is fabricated for demonstration only and is clearly marked
SYNTHETIC. Real contest cases are supplied by the organizer at evaluation time.

## Contents
- input/case.json — demo case_id + output_contract
- input/task.md — demo task statement
- input/manuscript.md — tiny fake trial manuscript with deliberate norm gaps
- ir.json — agent-style IR with 8 double-anchored compliance items

## Run
```
PYTHONDONTWRITEBYTECODE=1 python ../../assemble.py --ir ir.json --input input --out /tmp/demo-compliance
```

## Expected result
- exit 0, validation errors = []
- status = partial (CI2 informed consent + CI8 participant flow are
  insufficient_evidence — absent information, not proven violations)
- CI1 ethics partial (approval without number/scope); CI3 COI compliant;
  CI4 data availability partial; CI5 authorship non_compliant;
  CI6 copyright non_compliant (adapted figure without permission);
  CI7 CONSORT item 23 non_compliant (unregistered trial)
- compliance_rate 0.1667 (1/6 assessed); missing_items list actionable
- 0 locator issues; outputs: review.json, checklist.csv, report.md,
  provenance.json, result.json