# Error handling — analysis-db-query

Principle: read-only always; locate errors from the log; never fabricate a row or field meaning.

| Situation | Engine behavior | Agent action |
|---|---|---|
| Non-SELECT/WITH/PRAGMA sql | validation error; refused (also enforced by w4kit mode=ro) | rewrite as read-only |
| ? placeholder count != params | query failed with reason | fix params binding |
| Wrong table / field name | sqlite error logged (status failed) | discover schema; fix names; rerun |
| Syntax error | sqlite error logged | fix SQL; rerun |
| Empty result (0 rows) | empty_result_note "verify filters/keys"; n_empty counted | verify filters/join keys; partial |
| Multi-table without ON/WHERE | join_warning (inflation risk); n_join_warnings counted | add join condition; check cardinality |
| Encoded field aggregated as number | not auto-detected | interpret per dictionary; CAST explicitly |
| Unreadable / missing db | dataset status failed; query failed | register what exists; partial |
| .sql dump provided | restored to _db_work working copy; queried mode=ro; original untouched | note provenance |
| IR validation errors | validation.json; result still written (partial) | fix IR; rerun |
| Build exception | honest partial/failed + build_error | read traceback; fix; rerun |

Status: result success|partial|failed|stuck; query ok|failed.
The database is NEVER written (mode=ro); only SELECT/WITH/PRAGMA execute. query_log.json is the
replay record (sql + params + row_count + duration + read_only). Every gap:
{item, reason, impact?, handling: human_confirm} in uncertainty[].