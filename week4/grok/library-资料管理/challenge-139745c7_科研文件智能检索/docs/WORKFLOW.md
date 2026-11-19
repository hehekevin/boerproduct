# WORKFLOW — library track

## 0. Runtime
Inputs under /input (case.json, task.md, actual material). Outputs to /app/output.
Python 3.10+ stdlib only. Set PYTHONDONTWRITEBYTECODE=1 to keep the package text-only.

## 1. Inventory & register
- w4kit.list_materials("/input") → real file list (path/bytes/ext).
- Register each used file in sources[] {id, path}. One documents[] entry per logical
  document {document_id, source_id, title}. Do not infer content from labels.

## 2. Read & fill IR
- Open the actual documents/tables/notes. Fill metadata with {value,status,evidence}.
- Compute nothing by hand that the engine computes (hashes, ranking, matching) — the
  engine does it deterministically; the agent supplies judgment + locators.
- Follow rules/rules_<kind>.md for the kind-specific required arrays.

## 3. Assemble
python assemble.py --ir library_ir.json --input /input --out /app/output
- validate_ir → validation.json (errors → honest partial).
- build → library_index.json + kind artifact + provenance.json + report.md.
- compute_status → success/partial; build_result → result.json (output_contract echoed).

## 4. Verify & hand over
- Check coverage: every requested file/field/query/question/annotation has a result.
- Check traceability: every hit/answer/card has a real paragraph/quote locator.
- Check honesty: gaps are not_reported/insufficient_evidence/abstain/no_hits, not facts.
- report.md + provenance.json let a reviewer replay and judge correctness.

## 5. Iterate
- Re-run after fixing IR; the engine is deterministic so edits re-render reproducibly.
- Record changes in provenance.changes for the change_log.
