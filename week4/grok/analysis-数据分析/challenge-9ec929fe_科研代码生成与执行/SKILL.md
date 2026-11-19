---
name: analysis-code-gen-exec
description: Generate runnable research-analysis Python code from a spec + data dictionary, execute it safely in an isolated subprocess (python -I -B) or AST-whitelist safe_eval, capture the full execution log (command/exit/stdout/stderr/duration/env), and VERIFY results against expected values with tolerance checks to catch "ran but computed wrong" silent errors. Use when the task is 科研代码生成与执行 / generating and running analysis code on provided data.
---

# Research code generation & execution (科研代码生成与执行)

A source-bound Skill for the Bohrium weekly contest (analysis track, challenge-9ec929fe).
The agent reads the ACTUAL organizer spec + data dictionary + data under /input, writes
real runnable analysis code into the IR, and a deterministic engine executes it safely,
captures outputs + a full execution log, and verifies the results against expected values
(safe_eval tolerance checks + dataset row-count cross-checks). Editable code artifact +
execution log + verified results + provenance + honest result.json. No pre-baked answers;
the code runs on the real data each time.

## Focus (rubric points)
- 实际效果: code actually runs on the given data/environment; numbers match the dictionary/
  caliber/expected; process + failures are reviewable.
- 创新增益: a verification layer that catches SILENT errors (missing-as-0, un-deduped group
  stats, wrong query filters) via expected-value checks + row-count cross-checks, not just
  "it ran". Static safety scan; isolated execution; env/version recorded for replay.
- 可靠体验: missing column / type mismatch / missing dependency / empty result / overflow /
  timeout → identified, logged, degraded or turned to human_confirm; failure scene preserved.
- Two execution modes: subprocess (real Python, isolated -I -B, timeout, captured streams)
  and safe_eval (AST-whitelist arithmetic over data-derived env, no arbitrary code).

## Inputs (runtime)
- /input/case.json — case_id + output_contract (preserve every key).
- /input/task.md — the concrete code-generation spec.
- Actual material: data table(s)/database + data dictionary (field names, types, units, caliber).

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory; register sources[] + datasets[] (real paths). Read the spec + dictionary.
2. Write runnable code (stdlib preferred) that reads the REAL data via the ANALYSIS_DATA env
   (JSON map dataset_id→path) or ANALYSIS_INPUT dir, computes the requested results, and
   writes results.json in its cwd (or prints a JSON line). Fill code.spec/generated/exec/checks.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir code_ir.json --input /input --out /app/output`
   → validate_ir → static scan → execute → capture log → verify checks → analysis_code.py +
   execution_log.json + code_results.json + provenance.json + report.md → result.json.
4. Honest status: success when code executed and all checks pass; partial on failed checks,
   no results, or warnings; failed on non-zero exit / no code.

## IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto>
kind: "code_gen_exec"
sources: [{id, path, description?}]
datasets: [{dataset_id, source_id, path, columns?}]
code: {
  spec: {task, inputs: [dataset_id], expected_outputs: [...], language: "python"},
  generated: {source: "<runnable python>"} | {path: "<code file>"},
  exec: {
    mode: "subprocess" | "safe_eval",   # default subprocess
    timeout_s?: 120,
    env?: {name: value},                 # constants for safe_eval / extra env
    env_from_dataset?: {name: {dataset_id, column, row}},  # pull a REAL cell
    expressions?: [{name, expr}]         # safe_eval mode: AST-whitelist arithmetic
  },
  checks: [{check_id, description, expr, expected, tolerance?}]  # safe_eval over results
}
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes?}
```
Execution env passed to subprocess: ANALYSIS_INPUT (input dir), ANALYSIS_DATA (JSON
dataset_id→resolved path). Results read from work/results.json or last JSON stdout line.
Check env = numeric results (flattened) + n_rows_<dataset_id> + exec.env. expr uses the
w4kit safe_eval whitelist (+ - * / ** % // sqrt exp log abs sin cos tan floor ceil min max pi e).

## Domain rules
See rules/rules_code_gen_exec.md (field alignment, explicit caliber, env/version, safe
execution, verification against expected, error handling, reproducibility).

## Scripts & dependencies
assemble.py (CLI), analysis_engine.py (static scan + isolated execution + log + verification),
w4kit.py (safe_eval / read_table / result.json). Python 3.10+ stdlib; generated code should
prefer stdlib (csv/json/math/sqlite3). See requirements.txt.

## Outputs (/app/output)
analysis_code.py (editable artifact), execution_log.json (command/cwd/exit/stdout/stderr/
duration/python/platform), code_results.json (results + checks + verification + static_scan),
provenance.json, report.md, validation.json, result.json.

## Error handling (docs/ERROR_HANDLING.md)
Non-zero exit → failed + stderr preserved; ran but no results.json/JSON line → partial;
check mismatch → fail (silent-error caught) → partial; timeout → killed + logged; missing
column/type → code should raise a clear error (logged); dangerous patterns (os.system,
subprocess, eval/exec, network) → static_scan warnings for review; safe_eval unknown symbol/
unsupported expr → error logged. Never fabricate a result the code did not produce.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/code_gen_exec/`: input/ (dictionary + 6-row table + spec) + ir.json with real code.
Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/code_gen_exec/ir.json --input examples/code_gen_exec/input --out w4/.tmp_analysis/challenge-9ec929fe`
Demonstrates subprocess execution + mean/row-count verification (expected 35.0 / 6).

## Self-check
- [ ] code reads the REAL data (ANALYSIS_DATA/ANALYSIS_INPUT), fields aligned to dictionary
- [ ] caliber explicit: missing excluded (not 0), duplicates handled, units stated
- [ ] execution isolated (-I -B), timeout set, full log captured (exit/stdout/stderr/env)
- [ ] checks verify results vs expected with tolerance + row-count cross-check
- [ ] static scan reviewed; no network/system/destructive calls; writes only to work dir
- [ ] python version/platform/seed recorded; replayable
- [ ] result.json honest (success/partial/failed); output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt: line 1 = public GitHub tree URL, line 2 = SKILL.md. Opens without login.

## Runtime contract
Skill authoring task. Valid frontmatter. No prepared answers. Evaluator installs under
/skills/weekly-skill, runs the Harness on 3 fixed cases (/input → /app/output/result.json
preserving output_contract + case_id). Budget 64 requests / 900 s; save honest partial early.
Resources ≤50 UTF-8 text files, ≤500KB each, ≤2MB total, no binaries/symlinks/__pycache__.