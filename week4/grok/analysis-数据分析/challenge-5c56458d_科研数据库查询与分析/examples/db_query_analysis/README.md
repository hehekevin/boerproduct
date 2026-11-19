# Example — db_query_analysis (SYNTHETIC)

ALL files here are SYNTHETIC interface-demo data, NOT a formal contest case or answer.

## Contents
- input/case.json — example case_id + output_contract
- input/task.md — example query questions (Chinese)
- input/dictionary.md — field meaning / units / join path / cardinality
- input/seed.sql — TEXT SQL dump (samples + measurements); keeps the package text-only
- ir.json — agent-filled IR (GROUP BY count + parameterized join)

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/db_query_analysis/ir.json --input examples/db_query_analysis/input \
  --out w4/.tmp_analysis/challenge-5c56458d
```

## Expected
- exit 0; validation errors = []; status success
- engine restores seed.sql to a working copy under _db_work/ (runtime, OUT dir) and queries
  it READ-ONLY (mode=ro); the original dump is never modified
- query_results.json: schema (samples, measurements) + q1 (A:2, B:2) + q2 (A mean 28.33 n_meas 3,
  B mean 34.0 n_meas 2) with evidence {db, sql, params}
- query_q1_count.csv + query_q2_mean_strength.csv exported; query_log.json replayable (read_only=true)
- q2 has ON + WHERE → no join-inflation warning; interpretation explains one-to-many grain
- result.json preserves every output_contract key + case_id