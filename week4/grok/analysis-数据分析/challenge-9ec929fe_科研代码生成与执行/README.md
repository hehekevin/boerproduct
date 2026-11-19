# analysis-code-gen-exec (challenge-9ec929fe)

Source-bound Skill for the Bohrium weekly contest ANALYSIS track — 科研代码生成与执行.
Agent reads the actual organizer spec + dictionary + data under /input, writes runnable
analysis code into an IR; a deterministic engine executes it safely (isolated subprocess
python -I -B, or AST-whitelist safe_eval), captures a full execution log, and VERIFIES results
against expected values (tolerance checks + row-count cross-checks) to catch silent errors.
Writes editable code + log + verified results + provenance + honest result.json. Not pre-baked.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
See SKILL.md, rules/rules_code_gen_exec.md, docs/WORKFLOW.md, docs/ERROR_HANDLING.md.

## Files
SKILL.md; assemble.py; analysis_engine.py; w4kit.py; rules/rules_code_gen_exec.md; docs/;
examples/code_gen_exec/ (SYNTHETIC input/ + ir.json with real code + README).

## Dependencies
Python 3.10+ standard library. Generated code should prefer stdlib (csv/json/math/sqlite3).
Execution uses subprocess (stdlib) with isolation + timeout; safe_eval uses an AST whitelist.
See requirements.txt.

## Scope & limits
- Generates + executes + verifies Python analysis code on csv/tsv/json tables or read-only
  SQLite. Two modes: subprocess (real code) and safe_eval (arithmetic only).
- Verification catches "ran but wrong" via expected-value + row-count checks; it does not
  prove correctness beyond the declared checks. Static scan flags dangerous patterns.
- Does NOT do experiment design, mechanism explanation, or paper writing. No network/system/
  destructive operations; generated code writes only to its work dir.

## Self-check
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/code_gen_exec/ir.json --input examples/code_gen_exec/input \
  --out w4/.tmp_analysis/challenge-9ec929fe
```
Expect exit 0, no validation errors, status success, verification 2/2. Delete any __pycache__
(the engine runs python -B and sets PYTHONDONTWRITEBYTECODE). Hard limits: ≤50 UTF-8 text
files, ≤500KB each, ≤2MB total, no binaries/symlinks.