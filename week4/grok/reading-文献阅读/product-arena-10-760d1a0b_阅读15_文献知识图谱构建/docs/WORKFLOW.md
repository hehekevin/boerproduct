# WORKFLOW — knowledge_graph

1. **Inventory**: ls -R /input; open case.json (case_id, output_contract), task.md
   (topic, requested types, query questions), workorder files if present.
2. **Read ALL material**; for PDFs extract text with runtime tools into /app/work,
   register as sources with page/paragraph locators.
3. **Extract entities** actually present; record aliases + evidence quotes.
4. **Extract relations** with type/direction/conditions + minimal evidence; reject
   co-occurrence-only pairs. Normalize aliases with merge basis.
5. **Fill IR** /app/work/ir.json per rules/rules_knowledge_graph.md: sources[],
   nodes[], edges[], queries[] (>=3), unanswered_parts, uncertainty, provenance.
6. **Run**:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output`
7. **Inspect** validation.json + graph_check.json: duplicate-label warnings → merge
   or justify; orphan nodes → connect with evidence or remove; errors (exit 2) → fix
   IR, re-run.
8. **Honest partial early**: unsupported relations → insufficient_evidence;
   result.json partial with limits + human_confirm. Budget 64 requests / 900 s.
9. **Verify**: graph.svg opens as editable layered SVG with data-source attributes;
   queries answered with evidence; result.json keeps case_id + output_contract.