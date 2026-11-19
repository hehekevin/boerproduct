# WORKFLOW — summary_notes

1. **Inventory**: ls -R /input; open case.json (case_id, output_contract), task.md,
   workorder/note-fields files if present.
2. **Read material fully**; for PDFs extract text with runtime tools into /app/work,
   register as source with page/paragraph locators.
3. **Map structure**: sections[] from the paper's actual headings/order.
4. **Fill IR** /app/work/ir.json per rules/rules_summary_notes.md: one item per
   requested field_id (verbatim quote + locator + condition), claims with subclaim
   support, unanswered_parts, uncertainty, provenance.
5. **Run**:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output`
6. **Inspect** validation.json + stdout. Errors (exit 2) → fix IR, re-run. Warnings
   (uncovered fields, missing quotes, inferred without note) → improve within budget.
7. **Honest partial early**: absent fields → not_reported items; result.json partial
   with limits + human_confirm. Budget 64 requests / 900 s.
8. **Verify**: notes.json covers every requested field; paper card markdown readable;
   result.json keeps case_id + output_contract; provenance record_map complete.