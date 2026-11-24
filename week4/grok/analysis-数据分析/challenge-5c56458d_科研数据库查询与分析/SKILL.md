---
name: analysis-db-query
description: Run read-only SQL (SELECT/WITH/PRAGMA, parameterized) over the organizer-provided SQLite database, discover the schema, export verifiable result tables (CSV + JSON), log every query (sql/params/row_count/duration/error), and interpret fields/joins against the data dictionary with one-to-many inflation guards. Never writes to the database. Use when the task is 科研数据库查询与分析 / querying and analyzing a provided research database.
---

# Research database query & analysis (科研数据库查询与分析)

A source-bound Skill for the Bohrium weekly contest (analysis track, challenge-5c56458d).
The agent reads the ACTUAL organizer database + data dictionary under /input, writes
parameterized read-only queries into an IR, and a deterministic stdlib engine discovers the
schema, executes the queries READ-ONLY (sqlite mode=ro), exports verifiable result tables,
logs every query, and attaches field/join interpretation. Provenance + honest result.json.
No pre-baked answers; every result row comes from executing the SQL on the real snapshot.

## Focus (rubric points)
- 实际效果: queries actually execute on the authorized snapshot; results match an independent
  recomputation/gold; field meaning + join path are reviewable from the record.
- 创新增益: automatic schema discovery (PRAGMA table_info), parameterized queries (placeholder
  count validated), one-to-many join-inflation warning (multi-table without ON/WHERE), and a
  replayable query log (sql + params + row_count + duration + read_only flag).
- 可靠体验: connection/table/field errors located and logged; empty results flagged (verify
  filters/keys); encoded fields not aggregated as numbers blindly; missing/duplicates noted.
- SAFETY: the database is opened mode=ro and NEVER written. A provided .sql dump is restored
  into a working copy under /app/output and queried read-only; the original is untouched.

## Inputs (runtime)
- /input/case.json — case_id + output_contract (preserve every key).
- /input/task.md — the concrete query/analysis questions.
- Actual material: SQLite database (.db/.sqlite/.sqlite3) or a .sql dump + data dictionary.

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_analysis.py --input /input --out /app/output --work /app/work`
Auto-registers sources from the ACTUAL /input materials, auto-fills a complete source-bound IR
into /app/work, runs the SAME validate+build path as the package assembler, and ALWAYS writes an
honest result.json (try/except fallback preserves every output_contract key + case_id) — even on
empty input or failure. Judgment it cannot verify is flagged human_confirm; never fabricated.
THEN, within remaining budget, refine the auto-filled IR in /app/work and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/<ir>.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory; register sources[] + datasets[] (dataset path = the real db/dump).
2. Discover schema (engine does PRAGMA table_info; you can also PRAGMA via a query). Read the
   dictionary: field meaning, units, keys, join paths, encoded vs numeric fields.
3. Write parameterized read-only queries + interpretation per question; fill the IR per
   rules/rules_db_query_analysis.md.
4. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir db_ir.json --input /input --out /app/output`
   → validate_ir → schema discovery → execute read-only → query_<id>.csv + query_results.json
   + query_log.json + provenance.json + report.md → result.json.
5. Honest status: success when all queries ok with interpretations and no gaps; partial on
   failed/empty queries, join warnings, missing interpretation, or declared uncertainty.

## IR schema (agent fills from ACTUAL material)
```
ir_version: "1.0"
case_id: <auto>
kind: "db_query_analysis"
sources: [{id, path, description?}]
datasets: [{dataset_id, source_id, path, columns?}]   # path = real .db/.sqlite/.sql
queries: [{
  query_id, question, dataset_id,
  sql,                  # SELECT / WITH / PRAGMA only; use ? placeholders
  params: [...],        # bound parameters (count must match ? placeholders)
  interpretation,       # REQUIRED: field meaning + caliber + join path reading
  max_rows?             # json row cap (default 500; full CSV exported)
}]
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes?}
```
Engine: validates read-only + placeholder/param count; discovers schema; executes via
w4kit.sqlite_query (mode=ro); exports query_<id>.csv + query_results.json (columns/rows/
row_count/truncated/evidence) + query_log.json; warns on multi-table queries lacking ON/WHERE.

## Domain rules
See rules/rules_db_query_analysis.md (read-only connection, schema discovery, query generation,
result extraction, field interpretation, cross-table join control, replayable log).

## Scripts & dependencies
assemble.py (CLI), analysis_engine.py (schema discovery + read-only execution + log + join
guard + provenance), w4kit.py (sqlite_tables/sqlite_query mode=ro / read_table / result.json).
Python 3.10+ standard library only (sqlite3). See requirements.txt.

## Outputs (/app/output)
query_<id>.csv (verifiable result tables), query_results.json (results + schema + evidence),
query_log.json (sql/params/status/row_count/duration/read_only), provenance.json, report.md,
validation.json, result.json. For a .sql dump, a working copy is restored under _db_work/
(runtime only); the original dump/db is never modified.

## Error handling (docs/ERROR_HANDLING.md)
Non-SELECT/WITH/PRAGMA → validation error (refused); placeholder/param mismatch → query failed
with reason; wrong table/field → sqlite error logged (locate + fix); empty result → flagged
"verify filters/keys"; multi-table without ON/WHERE → join-inflation warning; unreadable db →
failed dataset + partial. NEVER write to the database; never fabricate a result row.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/db_query_analysis/`: input/ (dictionary + seed.sql dump) + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/db_query_analysis/ir.json --input examples/db_query_analysis/input --out w4/.tmp_analysis/challenge-5c56458d`
The .sql dump keeps the example TEXT-ONLY (no binary db in the package); the engine restores a
working copy at runtime and queries it read-only. Demonstrates a GROUP BY count + a parameterized join.

## Self-check
- [ ] database opened read-only (mode=ro); original never written; .sql restored to working copy
- [ ] schema discovered; queries use real table/field names from the dictionary
- [ ] queries parameterized (? placeholders == params count); SELECT/WITH/PRAGMA only
- [ ] result tables exported (CSV+JSON); row_count + evidence (db/sql/params) recorded
- [ ] join keys correct; one-to-many inflation guarded (ON/WHERE); encoded fields not mis-aggregated
- [ ] every query has a field/caliber interpretation; empty results flagged
- [ ] query log replayable; result.json honest; output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt: line 1 = public GitHub tree URL, line 2 = SKILL.md. Opens without login.

## Runtime contract
Skill authoring task. Valid frontmatter. No prepared answers. Evaluator installs under
/skills/weekly-skill, runs the Harness on 3 fixed cases (/input → /app/output/result.json
preserving output_contract + case_id). Budget 64 requests / 900 s; save honest partial early.
Resources ≤50 UTF-8 text files, ≤500KB each, ≤2MB total, no binaries/symlinks/__pycache__
(the example uses a .sql dump, NOT a binary .db, to stay text-only).