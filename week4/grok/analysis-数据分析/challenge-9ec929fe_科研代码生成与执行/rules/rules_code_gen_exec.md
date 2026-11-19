# Domain rules — code_gen_exec (科研代码生成与执行)

Goal: code that truly runs on the given data/environment, computes the right numbers per the
dictionary/caliber, and whose process + failures are reviewable. Catch "ran but wrong".

## 1. Generate from the spec + dictionary (not generic boilerplate)
- Read the data dictionary: exact field names, types, units, missing codes, primary key.
- Align code fields to the REAL header; never hardcode a column name you have not verified.
- Make the caliber explicit in code + comments: how missing values are excluded (NOT 0-filled),
  whether/how duplicates are removed before group stats, which units are used.
- Prefer stdlib (csv/json/math/sqlite3/statistics). If a third-party package is needed, declare
  it and provide a stdlib fallback; never assume a package is installed.

## 2. Environment & reproducibility
- Read data via ANALYSIS_DATA (JSON dataset_id→resolved path) or ANALYSIS_INPUT dir — never
  hardcode an author-machine absolute path.
- Record python version, platform, dependency versions, and any random seed (engine logs
  python/platform; put seed in code + spec). Same input → same numbers on rerun.
- Write outputs only to the working directory (results.json); never modify the source data.

## 3. Safe execution
- subprocess mode runs `python -I -B` (isolated, no bytecode) with a timeout; cwd is a work
  dir under /app/output. stdout/stderr/exit/duration are captured.
- safe_eval mode evaluates only AST-whitelisted arithmetic over a data-derived env — no
  arbitrary code, no imports, no attribute access.
- Static scan flags os.system / subprocess / shutil.rmtree / __import__ / eval / exec /
  socket / requests / urllib. Review every flag; generated analysis code should not need them.
- No network calls, no destructive filesystem ops, no writing outside the work dir.

## 4. Verification (the key anti-silent-error layer)
- Declare checks[]: {expr, expected, tolerance}. expr is evaluated by safe_eval over the
  numeric results + n_rows_<dataset_id> + exec.env. Compare |actual-expected| <= tolerance.
- Cross-check row counts against the source (n_rows_<did>) to catch un-deduped inflation or
  over-filtering. Verify means/sums against an independent recomputation or gold value.
- A check that fails means "ran but computed wrong" → status partial, investigate, do not
  just swap code until a number looks plausible.

## 5. Error handling (identify → retry/degrade/terminate/human)
- Missing column / type mismatch / empty result / overflow / missing dependency: code should
  raise a CLEAR error message; the engine preserves the failure scene (stderr + exit).
- Timeout → process killed + logged. Non-zero exit → failed. Ran but no results → partial.
- Decide explicitly: retry with a fix, degrade to a stdlib method, terminate, or human_confirm.
  Record the decision + reason in uncertainty/provenance. Never invent a plausible number.

## 6. Honesty & provenance
- code_results.json carries results + checks + verification + static_scan + execution_log.
- provenance maps the code artifact to the spec + sources. result.json status honest
  (success only if executed AND all checks pass). Every gap → human_confirm.