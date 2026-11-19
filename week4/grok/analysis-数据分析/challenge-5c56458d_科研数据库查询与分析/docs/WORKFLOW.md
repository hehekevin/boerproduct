# Workflow — analysis-db-query

Runtime: input /input, work /app/work, output /app/output.

1. **Inventory.** `w4kit.list_materials('/input')`; read case.json + task.md (the questions).
2. **Read material.** Locate the real database (.db/.sqlite/.sqlite3) or .sql dump and the data
   dictionary. Register sources[] + datasets[] (dataset path = the db/dump).
3. **Discover schema.** The engine runs PRAGMA table_info on every table at build; you may also
   add a PRAGMA query. Read the dictionary for field meaning, units, keys, join paths, encoded
   vs numeric fields.
4. **Write queries + fill IR** (db_ir.json) per rules/rules_db_query_analysis.md: queries[] each
   with question, dataset_id, parameterized read-only sql (? placeholders), params, and an
   interpretation. uncertainty for ambiguous fields/keys.
5. **Run.**
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir db_ir.json --input /input --out /app/output`
   Engine validates read-only + param count, discovers schema, executes mode=ro, exports
   query_<id>.csv + query_results.json + query_log.json + provenance.json + report.md + result.json.
6. **Inspect.** validation.json; query_log.json (status/row_count/error per query);
   query_results.json (schema + rows + evidence); result.json status.
7. **Iterate honestly.** Fix SQL/keys from the logged error and rerun. Empty results → verify
   filters/keys. Genuine gaps → partial + human_confirm. Never write to the db; never fabricate.

## Self-test (SYNTHETIC example)
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/db_query_analysis/ir.json --input examples/db_query_analysis/input \
  --out w4/.tmp_analysis/challenge-5c56458d
```
Expect exit 0, validation errors = [], status success. The .sql dump is restored to a working
copy under _db_work/ (runtime) and queried read-only; the package stays text-only.