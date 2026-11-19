# WORKFLOW — arena-latex

## 1. Read the actual material
- `w4kit.load_case("/input")` → case_id, task_md, output_contract, template.
- Locate + READ content (md/txt/docx), template (.cls/.sty), bib, figures.
- Register sources with locators.

## 2. Fill the IR (Agent judgment)
- `latex`: documentclass/options/packages/title/author/abstract/bib_style/
  required_sections/sections (heading/level/label/body)/figures.
- `bib_entries[]` (key + metadata + source); `citations[]`; `claims[]`+evidence;
  `numbers[]`. Body is real LaTeX (balanced braces, valid environments).
- Save `writing_ir.json` under /app/work.

## 3. Assemble (deterministic)
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir writing_ir.json --input /input --out /app/output
```
validate_ir → emit main.tex + references.bib → structure_check (braces/environments/
required sections/cite-ref) → compile if TeX present (latexmk -pdf or pdflatex, 2 rounds
with bib) else honest defer → structure_check.json + compile_report.json (+ main.pdf if
compiled) → provenance.json (claim_map + latex_map) → result.json. Exit 0 ok; exit 2 partial.

## 4. Compile-fix loop (runtime)
- If compile errors: read compile_report.json errors/log_tail, locate root cause, fix the
  IR (body/packages/bib), re-run. Record command + rounds + TeX/package versions.

## 5. Verify
- structure ok; cite keys in bib; ref labels defined; content from material; compile
  honest (PDF only if ran); editable .tex/.bib; result.json honest.