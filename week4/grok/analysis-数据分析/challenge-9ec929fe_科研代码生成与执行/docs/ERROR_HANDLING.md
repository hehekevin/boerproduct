# Error handling — analysis-code-gen-exec

Principle: preserve the failure scene; verify numbers; never fabricate a plausible result.

| Situation | Engine behavior | Agent action |
|---|---|---|
| Non-zero exit code | status failed; stderr + exit preserved in execution_log | read traceback; fix code/caliber; rerun |
| Ran but no results.json / JSON stdout | status partial + reason | make code write results.json or print JSON |
| Check mismatch (|actual-expected|>tol) | check fail; verification.ok=false; status partial | investigate silent error (missing-as-0, un-deduped, wrong filter); fix |
| Timeout | process killed; logged "timeout after Ns" | reduce work / raise timeout_s; rerun |
| Missing column / type mismatch | code raises clear error → failed + stderr | align fields to dictionary; cast explicitly |
| Empty result / overflow | code should detect + report; logged | handle explicitly; human_confirm if unexplainable |
| Missing dependency | ImportError → failed + stderr | declare dep or use stdlib fallback |
| Dangerous pattern (os.system/subprocess/eval/exec/network) | static_scan warnings | review; remove; analysis code should not need them |
| safe_eval unknown symbol / unsupported expr | check error logged | use whitelisted ops/symbols only |
| IR validation errors | validation.json; result still written (partial) | fix IR; rerun |
| Build exception | honest partial/failed + build_error | read traceback; fix; rerun |

Status: result success|partial|failed|stuck; code executed|partial|failed; check pass|fail|error.
Execution is isolated (python -I -B), timeout-bounded, streams captured; python version +
platform recorded for replay. Generated code writes only to its work dir; source data is
never modified. Every gap: {item, reason, impact?, handling: human_confirm} in uncertainty[].