# analysis-db-query (challenge-5c56458d)

Source-bound Skill for the Bohrium weekly contest ANALYSIS track — 科研数据库查询与分析.
Agent reads the actual organizer SQLite database + dictionary under /input, writes parameterized
read-only queries into an IR; a deterministic stdlib engine discovers the schema, executes
SELECT/WITH/PRAGMA READ-ONLY (mode=ro), exports verifiable result tables (CSV+JSON), logs every
query, and attaches field/join interpretation with one-to-many inflation guards. Never writes to
the database. Provenance + honest result.json. Not pre-baked answers.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
See SKILL.md, rules/rules_db_query_analysis.md, docs/WORKFLOW.md, docs/ERROR_HANDLING.md.

## Files
SKILL.md; assemble.py; analysis_engine.py; w4kit.py; rules/rules_db_query_analysis.md; docs/;
examples/db_query_analysis/ (SYNTHETIC input/ with seed.sql + ir.json + README).

## Dependencies
Python 3.10+ standard library only (sqlite3). See requirements.txt.

## Scope & limits
- Read-only SELECT/WITH/PRAGMA over a provided SQLite db (.db/.sqlite/.sqlite3) or .sql dump
  (restored to a runtime working copy). Schema discovery, parameterized queries, CSV+JSON export,
  replayable query log, join-inflation warning.
- Does NOT write/modify the database, do DB administration/permissions, or invent field meanings.
  Encoded-vs-numeric aggregation and join cardinality are the agent's responsibility (guarded).
- The example uses a .sql dump so the package stays TEXT-ONLY (no binary .db shipped).

## Self-check
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/db_query_analysis/ir.json --input examples/db_query_analysis/input \
  --out w4/.tmp_analysis/challenge-5c56458d
```
Expect exit 0, no validation errors, status success; queries read-only; log replayable. Delete
any __pycache__ and the runtime _db_work copy is outside the package. Hard limits: ≤50 UTF-8 text
files, ≤500KB each, ≤2MB total, no binaries/symlinks.