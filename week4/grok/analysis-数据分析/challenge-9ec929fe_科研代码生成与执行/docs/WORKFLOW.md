# Workflow — analysis-code-gen-exec

Runtime: input /input, work /app/work, output /app/output.

1. **Inventory.** `w4kit.list_materials('/input')`; read case.json + task.md (the spec).
2. **Read material.** Open the dictionary + real data header/rows. Confirm field names,
   types, units, missing codes, primary key, and the requested outputs.
3. **Write code + fill IR** (code_ir.json) per rules/rules_code_gen_exec.md:
   - sources[], datasets[] (real paths).
   - code.spec (task, inputs, expected_outputs).
   - code.generated.source: runnable Python reading ANALYSIS_DATA/ANALYSIS_INPUT, computing
     results with explicit caliber, writing results.json in cwd (or printing a JSON line).
   - code.exec (mode subprocess|safe_eval, timeout_s, env/env_from_dataset/expressions).
   - code.checks[]: expr + expected + tolerance (verify numbers + row counts).
   - uncertainty for anything ambiguous.
4. **Run.**
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir code_ir.json --input /input --out /app/output`
   Engine static-scans, executes isolated, captures the log, verifies checks, writes
   analysis_code.py + execution_log.json + code_results.json + provenance.json + report.md
   + result.json.
5. **Inspect.** validation.json; execution_log.json (exit/stdout/stderr); code_results.json
   (verification.ok, per-check pass/fail); result.json status.
6. **Iterate honestly.** On failed checks/exit: read the failure scene, fix the code/caliber,
   rerun. Do NOT swap code until a number looks plausible. Genuine limits → partial +
   human_confirm. Save partial early; never fabricate a result.

## Self-test (SYNTHETIC example)
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/code_gen_exec/ir.json --input examples/code_gen_exec/input \
  --out w4/.tmp_analysis/challenge-9ec929fe
```
Expect exit 0, validation errors = [], status success, verification 2/2 checks pass.