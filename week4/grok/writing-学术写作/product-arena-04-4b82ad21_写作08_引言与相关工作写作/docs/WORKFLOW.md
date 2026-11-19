# WORKFLOW — arena-intro-related

## 1. Read the actual literature
- `w4kit.load_case("/input")` → case_id, task_md, output_contract, citation style.
- Locate + READ provided literature (pdf/md/txt/bib) and any draft method/results.
- Build a material index; register sources with section/paragraph locators.

## 2. Fill the IR (Agent judgment)
- `citations[]` accurate metadata; `claims[]`+evidence+strength+citation_ids.
- `sections[]`: Introduction; Related Work grouped by route with comparison dimensions;
  Research Gap; Contributions. `research_gap.derived_from[]`; `contributions[]` bound.
- `numbers[]`, glossary, uncertainty (proposed contributions, missing literature).
- Save `writing_ir.json` under /app/work.

## 3. Assemble (deterministic)
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir writing_ir.json --input /input --out /app/output
```
validate_ir (writekit + intro rules: gap derivation, contribution binding, required
sections) → number-consistency (citation markers stripped) → manuscript.md + .docx →
provenance.json (claim_map + research_gap + contributions) → result.json.
Exit 0 ok; exit 2 honest partial.

## 4. Iterate
- Edit IR, re-run; record provenance.changes[] {what, why, before, after}.

## 5. Verify
- Every claim binds evidence + citation; gap derived_from registered citations;
  contributions bound (proposed flagged); number_issues empty/reviewed; result honest.