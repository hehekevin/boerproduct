# SYNTHETIC example — quality_review (interface demo, NOT a formal answer)

All material here is fabricated for demonstration only and is clearly marked
SYNTHETIC. Real contest cases are supplied by the organizer at evaluation time.

## Contents
- input/case.json — demo case_id + output_contract (review_json/report_md/checklist_csv)
- input/task.md — demo task statement
- input/manuscript.md — tiny fake manuscript with deliberate defects
- ir.json — agent-style IR filled from that manuscript (with locators/quotes)

## Run
```
PYTHONDONTWRITEBYTECODE=1 python ../../assemble.py --ir ir.json --input input --out /tmp/demo-quality
```
(from this directory; or use the package-root paths shown in README.md)

## Expected result
- exit 0, validation errors = []
- status = partial: F5 (novelty claim) is insufficient_evidence because no
  literature is provided — demonstrates honest gap handling, not fabrication
- n_locator_issues = 0 (every quote verifies against the real demo text)
- 6 findings (4 major issues, 1 evidence gap, 1 strength), decision major_revision
- outputs: review.json, checklist.csv, report.md, provenance.json, result.json