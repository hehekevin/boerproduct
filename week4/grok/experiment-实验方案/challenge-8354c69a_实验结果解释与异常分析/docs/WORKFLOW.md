# WORKFLOW — experiment track

## 0. Runtime
Inputs under /input (case.json, task.md, actual material). Outputs to /app/output.
Python 3.10+ stdlib only. Set PYTHONDONTWRITEBYTECODE=1 to keep the package text-only.
Budget: 64 model requests / 900 s — save an honest partial result early, then improve.

## 1. Inventory & register
- w4kit.list_materials("/input") → real file list (path/bytes/ext).
- Register each used file in sources[] {id, path}. Add documents[] {id, source_id,
  title} (transcribe key paragraphs for quote verification) and protocols[] for
  versioned candidate plans. Do not infer content from labels.

## 2. Read & fill IR
- Open the actual sources/contracts/tables. Fill the kind-specific arrays per
  rules/rules_<kind>.md. Every verdict/number gets an evidence locator
  {source_id, paragraph_id/field/table, quote}.
- Let the engine compute (sums, range checks, normalization, stats, outliers,
  safe_eval checks); the agent supplies scientific judgment + locators.
- Distinguish reported (quoted) vs inferred (suggested); missing → not_reported /
  insufficient_evidence + human_confirm. Never fabricate.

## 3. Assemble
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <kind>_ir.json --input /input --out /app/output
- validate_ir → validation.json (errors → honest partial).
- build → <kind>.json + report.md (editable) + provenance.json (claim→source map).
- compute_status → success/partial; build_result → result.json (output_contract echoed).

## 4. Verify & hand over
- Coverage: every requested item/parameter/candidate/metric has a result.
- Traceability: every verdict/number has a real locator; quotes verify against text.
- Honesty: gaps are not_reported/insufficient_evidence/human_confirm, not facts.
- report.md + provenance.json let a reviewer replay and recompute.

## 5. Iterate
- Re-run after fixing the IR; the engine is deterministic so edits re-render
  reproducibly. Record changes in provenance.changes for the change_log.