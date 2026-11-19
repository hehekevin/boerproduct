# WORKFLOW — arena-methods-section

## 1. Read the actual material
- `w4kit.load_case("/input")` → case_id, task_md, output_contract.
- Locate + READ protocol/config/log/code/data (txt/json/yaml/csv/py/md).
- `w4kit.read_table` for csv/json data; register sources with locators.

## 2. Fill the IR (Agent judgment)
- `claims[]`+evidence; `sections[]` Methods + Experiments (ordered steps).
- `parameters[]` with value/unit/target/source/locator/status (reported/inferred/not_reported).
- equipment/reagents/statistical_methods/datasets/reproducibility; `numbers[]`; glossary.
- uncertainty for every gap (weight_decay, code_version, commands, dataset version...).
- Save `writing_ir.json` under /app/work.

## 3. Assemble (deterministic)
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir writing_ir.json --input /input --out /app/output
```
validate_ir (writekit + methods rules: parameter source required, status vocabulary,
required sections, statistical methods) → number-consistency → manuscript.md + .docx +
parameters.csv + reproducibility.md → provenance.json (claim_map + parameter_map) →
result.json (n_parameters/n_inferred/n_not_reported). Exit 0 ok; exit 2 honest partial.

## 4. Iterate
- Edit IR, re-run; record provenance.changes[]. csv/docx stay editable.

## 5. Verify
- Every parameter sourced + status correct; gaps not_reported + human_confirm;
  number_issues empty/reviewed; reproducibility checklist present; result honest.