# WORKFLOW — translation

1. **Inventory**: ls -R /input; open case.json (case_id, output_contract), task.md
   (direction, requested range), workorder/glossary files if present.
2. **Read material fully**; for PDFs extract text with runtime tools into /app/work
   and register it as a source with page/paragraph locators.
3. **Glossary first**: extract domain terms from the actual source; merge organizer
   glossary if provided; lock one translation per term.
4. **Fill IR** /app/work/ir.json per rules/rules_translation.md: sources[], glossary[],
   segments[] (verbatim source_text + faithful target_text + evidence locator),
   unanswered_parts, uncertainty, provenance.
5. **Run**:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output`
6. **Fix loop**: read translation_check.json; term_inconsistent/number_missing/
   citation_missing are must_fix → correct target text, re-run. validation errors
   (exit 2) → fix IR structure first.
7. **Honest partial early**: untranslated/unreadable segments get gap statuses;
   result.json partial with limits + human_confirm. Budget: 64 requests / 900 s.
8. **Verify**: bilingual.json covers the full requested range 1:1; result.json keeps
   case_id + every output_contract field; provenance record_map complete.