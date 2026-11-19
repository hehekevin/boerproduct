# WORKFLOW — nanopublication

1. **Inventory**: ls -R /input; open case.json (case_id, output_contract), task.md
   (target paragraphs/count/schema), workorder files if present.
2. **Read material fully** including metadata (authors/year/doi); for PDFs extract
   text with runtime tools into /app/work and register as source.
3. **Decompose**: split target conclusions into atomic assertions; keep conditions;
   map verbs to controlled predicates; select minimal sufficient quotes.
4. **Fill IR** /app/work/ir.json per rules/rules_nanopublication.md: sources[],
   nanopubs[] (assertion + evidence + provenance + status/kind), unanswered_parts,
   uncertainty, provenance.
5. **Run**:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output`
6. **Inspect** validation.json: duplicate-triple warnings → merge; predicate warnings
   → remap or justify; errors (exit 2) → fix IR, re-run.
7. **Honest partial early**: unsupported assertions → insufficient_evidence;
   result.json partial with limits + human_confirm. Budget 64 requests / 900 s.
8. **Verify**: nanopubs.json + nanopubs.trig parseable; every nanopub traceable to a
   quote; result.json keeps case_id + output_contract; provenance record_map complete.