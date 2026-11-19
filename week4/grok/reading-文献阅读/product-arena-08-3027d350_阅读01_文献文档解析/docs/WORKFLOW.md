# WORKFLOW — document_parse

1. **Inventory**: `ls -R /input`. Open case.json (copy case_id, read output_contract),
   task.md, and any workorder file (target-fields.json / workorder.json).
2. **Read material**: open every material file. For PDFs use runtime extraction tools
   (pdftotext / office renderer) and save extracted text under /app/work; register it
   as a source with page locators. If extraction fails → extraction_failed records.
3. **Fill IR** at /app/work/ir.json per rules/rules_document_parse.md:
   sources[] → items[] (one per requested field_id, verbatim quote + paragraph_id) →
   sections[] hierarchy → unanswered_parts / uncertainty / provenance.
4. **Run**:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output`
5. **Inspect** stdout JSON + /app/output/validation.json. Errors → fix IR, re-run.
   Warnings (missing quotes, thin locators, uncovered fields) → improve if budget allows.
6. **Honest partial early**: if material is missing/unreadable, still run with gap
   statuses; result.json will be partial with limits + human_confirm points.
7. **Verify**: result.json contains case_id + every output_contract field; fields.json
   has one entry per requested field; provenance.json record_map covers all records.

Budget discipline: 64 model requests / 900 s. Save a first honest IR+result early,
then refine quotes/coverage incrementally.