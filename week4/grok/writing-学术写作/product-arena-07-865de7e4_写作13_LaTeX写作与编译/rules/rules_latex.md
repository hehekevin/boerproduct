# Domain rules — latex (LaTeX写作与编译)

## 1. Source, not render (交得可用)
- Deliver editable `main.tex` + `references.bib`. Never deliver a PDF, screenshot, or
  uncompilable fragment as the source. Keep main-file/sub-file structure clear; organize
  the preamble; choose packages with correct load order.

## 2. Structure validity (engine-checked)
- Balanced braces (escaped `\{ \}` ignored); matched `\begin{env}`/`\end{env}` stack;
  `\begin{document}` present.
- `required_sections[]` present (e.g. Introduction/Methods/Results/Conclusion or template
  mandated sections). Missing → flag.
- Every `\cite{key}` resolves to a `bib_entries[]` key; every `\ref/\eqref/\autoref{label}`
  has a matching `\label{}`. The engine reports unresolved keys/labels.

## 3. Content fidelity (改得对)
- Equations: multi-line alignment, numbering/reference, symbol sub/superscripts, units
  upright vs variables italic, theorem/proof environments — meaning matches the prose.
- Tables: wide-table paging, column width/alignment, merged cells, three-line style;
  values from material (no invented numbers). Figures: caption + label + position; cite
  the original file (no placeholder/invented curve).
- Bibliography: .bib entries match in-text cite; style/sort; multi-round convergence.

## 4. Template adaptation
- Migrate content into the target class/.sty; respect layout constraints + required
  fields + file structure. Record template version, packages, fonts.

## 5. Honest compile (编译得通 / 复现得了)
- If a TeX compiler exists (latexmk/pdflatex/xelatex), compile in a temp dir (copy
  tex/bib/figures), 2 rounds when bib present; parse `!` error lines; emit main.pdf only
  on success. Record compiler + rounds + log tail + command.
- If NO compiler (local): structure-validate only; status success when structure ok, with
  uncertainty item latex_compile (compile deferred to runtime latex-compiler, human_confirm).
  NEVER claim compile success without a produced PDF.
- Compile failure → partial; locate file/line/root cause; fix IR and re-run. Missing
  package/font/class → state dependency, partial.

## 6. Source binding & reproducibility
- Register content/template/bib in `sources[]`; claims bind evidence locators; numbers
  from material. Record TeX distribution/package/font versions + compile command/rounds
  so others reproduce the same artifact. Editable source; traceable changes; honest status.