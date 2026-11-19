# Workflow — analysis-stats-analysis

Runtime: input /input, work /app/work, output /app/output.

1. **Inventory.** `w4kit.list_materials('/input')`; read case.json (case_id,
   output_contract) and task.md (the analysis question).
2. **Read material.** Open the dictionary + real table header/rows. Identify outcome
   column, group factor, units, missing codes, design (independent/paired, #groups).
3. **Fill IR** (stats_ir.json) per rules/rules_stats_analysis.md:
   sources[], datasets[], stats.analyses[] (describe / compare_groups / correlation /
   regression) each with an interpretation tied to the question; family for multiplicity;
   assumptions for design notes; uncertainty for anything ambiguous.
4. **Run.**
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir stats_ir.json --input /input --out /app/output`
   Engine recomputes every statistic from the real rows, adds effect sizes + CIs +
   assumption notes + Holm adjustment, writes stats_results.json + provenance.json +
   report.md + result.json.
5. **Inspect.** validation.json; stats_results.json (status per analysis, auto_summary,
   p/CI/effect size); report.md; result.json status.
6. **Iterate honestly.** Fix method/column errors and rerun. Genuine gaps (small n,
   paired design needing a paired test, missing interpretation) → partial + human_confirm.
   Save partial early; never fabricate a number or a test you cannot run.

## Self-test (SYNTHETIC example)
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/stats_analysis/ir.json --input examples/stats_analysis/input \
  --out w4/.tmp_analysis/challenge-c0e1e220
```
Expect exit 0, validation errors = [], status success (clean 12-row two-group example).