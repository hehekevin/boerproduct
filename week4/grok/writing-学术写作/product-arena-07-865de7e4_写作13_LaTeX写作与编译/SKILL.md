---
name: arena-latex
description: Source-bound LaTeX writing & compile (写作13LaTeX写作与编译, kind=latex). The Agent reads the ACTUAL content/template under /input, fills a LaTeX IR (documentclass, packages, sections, figures, bib_entries, claims+evidence), and a deterministic stdlib engine emits compilable main.tex + references.bib, validates structure (balanced braces, matched \begin/\end, required sections, \cite keys in bib, \ref labels defined), attempts a real compile only if a TeX compiler exists (runtime latex-compiler), and writes structure_check + compile_report + honest result.json. Use when the workorder asks to produce/maintain compilable LaTeX source from material. Honest about compile-not-run locally; never delivers a PDF/screenshot as the source.
---

# LaTeX写作与编译 skill (latex)

Source-bound LaTeX source generation + structural validation + honest compile. The
Agent maps real content into a LaTeX IR; the engine deterministically emits editable
.tex + .bib, checks structure, and compiles only when a TeX compiler is available.
Locally (no TeX) it validates structure and is explicit that compile is deferred to the
runtime latex-compiler. Never fabricate compile success or deliver a non-source artifact.

## Focus (rubric)
- 编译得通: source compiles under the target template/TeX distribution in expected
  rounds; errors located to file/line/root cause (when compiler available).
- 改得对: equation symbols/numbering, table values/columns, cross-refs/bibliography,
  layout/template required fields match intent + template.
- 交得可用: deliverable is clear, editable, maintainable SOURCE (.tex/.bib), not a PDF,
  screenshot, or uncompilable fragment.
- 复现得了: template version, packages/fonts, compile command + rounds recorded so
  others reproduce the same artifact.

## Scope / trigger
Use when the case asks for LaTeX写作与编译 / compilable LaTeX source / template migration
(workorder kind=latex). IN: .tex/.bib generation + structure check + honest compile.
OUT: prose polishing, references styling, intro/methods prose, PPT.

## Inputs (runtime)
`/input/case.json` (copy `case_id`; read `output_contract`, template/documentclass),
`/input/task.md`, ACTUAL content (md/txt/docx) + template (.cls/.sty) + bib + figures.
READ files; trust content over labels. Runtime HAS latex-compiler; local may not.

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_arena_write.py --input /input --out /app/output --work /app/work`
Auto-registers sources from the ACTUAL /input materials, auto-fills the complete writing IR
(verbatim sections/claims+evidence/citations/numbers/glossary) into work/writing_ir.json, runs
the SAME validate+build path as the package assembler, and ALWAYS writes an honest result.json
(try/except fallback preserves every output_contract key + case_id) — even on empty input or
failure. Targets/translations it cannot verify are null + human_confirm; never machine-invented.
THEN, within remaining budget, refine /app/work/writing_ir.json and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/writing_ir.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Read & register content/template/bib sources with locators.
2. Fill IR per `rules/rules_latex.md`: `latex` {documentclass, options, packages[],
   title, author, abstract, bib_style, required_sections[], sections[]{heading, level,
   label, body}, figures[]{path, caption, label, width}}; `bib_entries[]` {key, authors,
   year, title, journal, doi, source}; `claims[]`+evidence+citation_ids; `numbers[]`.
3. Run:
   `python assemble.py --ir writing_ir.json --input /input --out /app/output`
   → validate → emit main.tex + references.bib → structure_check (braces/environments/
   required sections/cite-ref) → compile if TeX present (latexmk/pdflatex, 2 rounds with
   bib) else honest defer → structure_check.json + compile_report.json → provenance.json
   → honest result.json.
4. Edit IR, re-run; keep provenance.changes[]; record compile command/rounds.

## IR schema (kind=latex)
```
ir_version "1.0", case_id, kind "latex", title,
sources[] {id, locator, kind, version},
latex {documentclass, options, packages[], title, author, abstract, bib_style,
       required_sections[], sections[]{heading, level, label, body}, figures[]{path, caption, label, width}},
bib_entries[] {key, authors, year, title, journal, volume, issue, pages, doi, source, locator},
citations[] {id, authors, year, title, journal, doi, source},
claims[] {id, text, type, evidence[]{source, locator, strength}, citation_ids[]},
numbers[] {value, unit, source, locator}, uncertainty[], provenance{pipeline, changes[]}
```

## Kind rules
See `rules/rules_latex.md`. Key: balanced braces + matched \begin/\end; required sections
present; every \cite key in references.bib; every \ref label defined; equation/table
content from material; template required fields; record TeX distribution/packages/
command/rounds; compile honestly (success only if PDF produced or structure-valid with
compiler absent + uncertainty; partial if compile fails).

## Scripts & dependencies
`assemble.py`, `arena_write_engine.py` (shared arena engine; LaTeX emit + structure check
+ compile), `writekit.py`, `w4kit.py` (case/result). Deps: Python 3.10+ stdlib only;
LaTeX compiler (latexmk/pdflatex/xelatex) OPTIONAL — present at runtime, absent locally
(honest fallback). Run with `PYTHONDONTWRITEBYTECODE=1`.

## Outputs (/app/output)
`main.tex` (editable source), `references.bib`, `structure_check.json`,
`compile_report.json`, `main.pdf` (only if a compiler ran successfully), `writing_ir.json`,
`provenance.json` (claim_map + latex_map), `validation.json`, `result.json`
(output_contract + case_id + honest status + structure_ok/compiled/compiler).

## Error handling (docs/ERROR_HANDLING.md)
No local compiler → structure validated, compile deferred + uncertainty (status success
if structure ok); compile error → locate file/line/root cause, partial, fix + re-run;
missing package/font/class → state dependency, partial; unbalanced brace/environment →
validation/structure error, fix; \cite key missing in bib / \ref undefined → flag, fix;
missing figure file → cite original or state limit (no placeholder). Save honest partial early.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/latex/`: input/case.json + task.md + content.md + ir.json + README.
`python assemble.py --ir examples/latex/ir.json --input examples/latex/input --out /tmp/demo`
Structure ok (2 cite keys, 4 labels); compile honestly deferred (no local TeX).

## Self-check
- [ ] main.tex structure ok (braces/environments/required sections/cite-ref)
- [ ] references.bib keys match \cite; content from material
- [ ] compile honest: PDF only if compiler ran; else uncertainty + human_confirm
- [ ] editable .tex/.bib (not PDF/screenshot); compile command/rounds recorded
- [ ] result.json honest (status/sources/uncertainty/change_log); latex_map complete

## Week4 concrete input interface (organizer revision)
组织方为本题准备 3 个固定案例。每个案例包含任务说明、科研材料、必要的输入约束和评分所需的证据范围；案例会以相同内容分别交给基础 Agent 和加载参赛 Skill 的 Agent。你不需要自带正式测试案例，也不需要提交预先写好的答案。

平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-section/field results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects or compile state; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.