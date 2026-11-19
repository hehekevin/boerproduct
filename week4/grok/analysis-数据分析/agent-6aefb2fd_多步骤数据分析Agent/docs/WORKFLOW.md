# Workflow — analysis-multi-step

Runtime: input /input, work /app/work, output /app/output.

1. **Inventory.** `w4kit.list_materials('/input')`; read case.json + task.md.
2. **Read material.** Open the dictionary + real tables. Identify fields, units, keys, design,
   and the end-to-end request (clean? compare? plot? report?).
3. **Decompose + fill IR** (pipeline_ir.json) per rules/rules_multi_step_analysis.md:
   sources[], datasets[], steps[] (load → clean → stats → viz → interpret) with depends_on
   ordering and per-step payloads (sibling schemas). interpret step: text + claims referencing
   computed metrics ("<analysis_id>.<key>"). uncertainty for ambiguous caliber/alignment.
4. **Run.**
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir pipeline_ir.json --input /input --out /app/output`
   Engine orchestrates steps in order over a shared data context (clean feeds stats/viz),
   writes per-step artifacts + pipeline.json + provenance.json + report.md + result.json,
   and cross-checks interpret claims against computed metrics.
5. **Inspect.** validation.json; pipeline.json (step statuses, metrics, backfill_check);
   per-step artifacts; report.md; result.json status.
6. **Iterate honestly.** Fix the failing step's payload and rerun (downstream recomputes).
   A failed step skips dependents with a reason; back-fill mismatch → fix text/analysis.
   Genuine gaps → partial + human_confirm. Save partial early; never fabricate downstream.

## Self-test (SYNTHETIC example)
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/multi_step_analysis/ir.json --input examples/multi_step_analysis/input \
  --out w4/.tmp_analysis/agent-6aefb2fd
```
Expect exit 0, validation errors = [], status success, back-fill checks pass (mean 17.0, d -5.0).