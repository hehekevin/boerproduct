# WORKFLOW — arena-reference-manage

## 1. Read the actual material
- `w4kit.load_case("/input")` → case_id, task_md, output_contract, target_style.
- Locate manuscript + library (`find_input`/`list_materials`); READ them.
- Parse library records (json/bib/ris/csv) into `references[]` with source locators.

## 2. Fill the IR (Agent judgment)
- `references[]`: raw records + source/locator. `in_text_citations[]`: marker → ref_id
  + claim_text + locator. `target_style`. Optional claims/evidence for topic match.
- Note uncertainty (ambiguous merges, unverifiable metadata, uncited entries).
- Save `writing_ir.json` under /app/work.

## 3. Assemble (deterministic)
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir writing_ir.json --input /input --out /app/output
```
validate_ir → normalize_doi/title + dedup_records → format unique list (GB/T 7714/APA/
IEEE) + BibTeX → in-text<->list consistency → references.md/.bib/.docx +
citation_map.json + dedup_report.json + consistency.json → provenance.json
(claim_map + reference_map) → result.json. Exit 0 ok; exit 2 honest partial.

## 4. Iterate
- Edit IR (reorder library to change representative, fix markers), re-run; record
  provenance.changes[]. The list/docx/bib stay editable.

## 5. Verify
- dedup_report: every input id in one cluster; merge basis + conflicts present.
- consistency: missing/uncited flagged; formatted style correct; DOI preserved.
- result.json honest; gaps human_confirm.