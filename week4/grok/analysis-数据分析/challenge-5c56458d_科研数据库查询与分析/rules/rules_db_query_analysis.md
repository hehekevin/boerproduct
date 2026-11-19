# Domain rules — db_query_analysis (科研数据库查询与分析)

Goal: queries that execute on the authorized snapshot, results that match an independent
recomputation, and field meanings + join paths that a reviewer can verify from the record.

## 1. Connection — read-only, discover, version
- Open the organizer database READ-ONLY (engine uses sqlite mode=ro). NEVER write/UPDATE/DELETE/
  DROP/INSERT/ATTACH. Only SELECT / WITH / PRAGMA are allowed (validation refuses others).
- A provided .sql dump is restored into a working copy under /app/output/_db_work and queried
  read-only; the original dump/db is never modified. Record the snapshot path + sha256.
- Discover tables (sqlite_tables) and columns (PRAGMA table_info) before writing queries;
  never guess a table/field name from a label.

## 2. Query generation — executable, parameterized
- Translate each question into SQL using the REAL schema; handle time ranges, filters, sort,
  paging (LIMIT/OFFSET). Use ? placeholders with a params list (count must match).
- After an error, locate the cause (wrong table/field/syntax) from the logged sqlite message
  and fix it — do not blindly retry random variants.

## 3. Result extraction — stable, verifiable
- Export each result as query_<id>.csv + structured JSON (columns, rows, row_count, truncated).
- Mind field types/units/encoding: do NOT aggregate an encoded/categorical field as a number;
  CAST explicitly when needed and state it. Note missing values and duplicate rows in results.
- Cap rows in JSON (max_rows, default 500) but export the full CSV; mark truncated honestly.

## 4. Field interpretation — dictionary-grounded
- Interpret each field's meaning, value range, and statistical caliber from the data dictionary.
- Identify easily-confused fields (e.g., sample status vs experiment status) and explain the choice.
- Every query carries an interpretation tied to its question + the actual columns returned.

## 5. Cross-table analysis — control inflation
- Choose the correct join key + path; verify cardinality. A one-to-many join inflates row counts
  and biases aggregates — aggregate at the right grain or dedup first.
- Multi-table queries MUST have ON/WHERE; the engine warns when they are missing (inflation risk).
- Cross-check row counts against an independent count query; give a reviewable cross-table conclusion.

## 6. Replayable log & honesty
- query_log.json records sql + params + status + row_count + duration + db + read_only for every
  query; another person must reproduce the results exactly.
- Empty result → flag "verify filters/keys" (not silently treated as a real zero finding).
- Failed query → status failed + error preserved; continue other queries; overall partial.
- Never fabricate a result row or a field meaning. Gaps → uncertainty + human_confirm.