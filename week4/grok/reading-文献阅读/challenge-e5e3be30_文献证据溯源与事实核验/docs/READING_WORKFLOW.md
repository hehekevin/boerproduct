# READING WORKFLOW — material → reading IR → structured result → checks → result.json

The Agent reads the ACTUAL material (paragraph/table text, figures, formulas) and
fills the reading IR; the scripts deterministically validate, run domain helpers,
emit the structured deliverable and result.json. Output triad: 解析结果 (cover task,
traceable) / 证据与边界 (locators + unreported/uncertain; can't-judge ≠ fact) /
运行状态 (success/partial/cannot-judge/refuse + reason + human-takeover point).

## 0. Read actual input
- `/input/case.json` (copy case_id; read output_contract), `/input/task.md`.
- Read workorder files when present: `target-fields.json` (extraction),
  `comparison-workorder.json` + corpus (multi-doc), benchmark workorder.
- Register `sources[]` with document_id + paragraph/page locators + version.
- Only use given material; no online retrieval / pixel-guessing unless the task
  provides the image and asks for it; mark inferred vs reported.

## 1. Fill reading IR (`reading_ir.json`) per rules/rules_<kind>.md
- `items[]`: one per requested field/question; value/answer + units + statistic +
  condition + comparator; `kind` reported/inferred; `status`
  (answered/partial/insufficient_evidence/input_error); `evidence[]`
  ({source,document_id,paragraph_id,quote}); `unanswered_parts[]`; `coverage`.
- `claims[]` (verification): subclaims typed fact/comparison/causal/scope with
  support degree (supports/partial/insufficient/unrelated/contradicts) + minimal
  sufficient evidence; unrelated ≠ supports.
- `matrix` (multi-doc): common fields; rows per document; cells with
  source_document_id+paragraph_id+units+metric口径; comparability + conflict explanation.
- `formulas[]`: latex + variables (definition/unit/range/source/defined-in-paper) +
  derivation steps (assumptions) + numeric_check.
- `figures[]`: axis type/unit/scale, elements, data (CSV), interpretation + evidence.
- `cleaning`: field_mapping/allowed_values/target_unit/dedup_keys + records (original
  preserved) → anomalies + pending.
- `reproduction`: params (paper vs repo vs used, source), env, results (metric/paper/
  repro/tolerance/within), attribution.
- `uncertainty[]` + `human_confirm[]` for gaps; never write can't-judge as fact.

## 2. Validate + build + check + result (one command)
```
python assemble_read.py --ir reading_ir.json --input /input --out /app/output
```
- readkit.validate_reading: item locators/status/reported-inferred, claim support
  validity, matrix cell sources, cleaning original+conversion, reproduction tolerance.
- domain helper: clean.py / formula.py / compare.py / benchkit.py.
- emits reading_result.json + reading_result.md (+ cleaned/formula_check/comparison/
  benchmark artifacts); result.json preserves output_contract + case_id + honest
  status/sources/uncertainty.

## 3. Error handling (honest)
- Missing material/field not reported → status insufficient_evidence + unanswered_parts;
  do not fabricate. Input read failure → input_error.
- Inferred → kind=inferred + uncertainty; reported → quote locator.
- Conflict → surface with attribution + per-cell sources; don't hide.
- Unit/parse failure → keep original + pending; never silent wrong conversion.
- Save honest partial early; improve within budget (64 req/900 s).

## 4. Self-check
Cover all requested fields/questions; every value traceable (document+paragraph+quote);
units/conditions preserved; reported vs inferred distinct; support degrees valid;
can't-judge flagged; status honest; result.json complete.