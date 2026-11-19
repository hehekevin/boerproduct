# WORKFLOW — review track (kind: logic_argument_review)

Step-by-step for the agent at runtime. All paths relative to the installed
skill directory (/skills/weekly-skill); work under /app/work.

## Step 1 — Load the case
```python
import w4kit
case = w4kit.load_case("/input")          # case_id, task_md, output_contract
materials = w4kit.list_materials("/input")
```
Read /input/task.md fully: it defines the concrete checks for THIS case.
Preserve every output_contract key in the final result.json (the engine does
this automatically via w4kit.build_result).

## Step 2 — Register sources & documents
For every actual file you use: sources[] {id, path}. For every logical
document: documents[] {document_id, source_id, role, title}. Role is one of
manuscript / reference / data / guideline / other. Set manuscript_id.
Never assume content from a filename; open and read the file.

## Step 3 — Read material and fill the IR
Start from `w4kit.base_ir(case, "logic_argument_review")`, then fill the kind-specific
arrays per `rules/rules_logic_argument_review.md` and the schema in SKILL.md.
Locators: paragraph ids p1..pN come from blank-line-split paragraphs of the
actual text file (engine recomputes the identical split). Quotes must be exact
substrings. For non-text files, transcribe readable paragraphs into
documents[].paragraphs and mark the rest honestly.

## Step 4 — Validate & build
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/review_ir.json --input /input --out /app/output
```
The CLI: loads case + IR → validate_ir → validation.json → build (quote
verification, recomputation, coverage) → review.json / checklist.csv /
report.md / provenance.json → result.json with honest status.
Exit code 0 for success/partial, 1 for failed. Read the printed summary.

## Step 5 — Fix or flag
- Validation errors: fix the IR (missing evidence, bad status vocab, unknown
  source) and re-run. Do not delete checks to make errors go away.
- quote_mismatch / paragraph_not_found: re-read the real paragraph, correct the
  locator or quote; if the text truly differs, record source_conflict.
- Gaps you cannot close: keep insufficient_evidence / uncheckable + uncertainty
  + human_confirm. A honest partial beats a fabricated success.

## Step 6 — Self-check before finishing
- result.json exists, echoes case_id + every output_contract key.
- status matches reality; limits listed when partial.
- Every finding/verdict has a verified locator; checklist.csv is assignable.
- No __pycache__ or binary files written into the skill directory.

## Re-run / replay
The same IR + same input must reproduce the same artifacts (deterministic
engine; only generated_at timestamps differ). Keep provenance.changes updated
when you edit the IR so a reviewer can replay your decisions.