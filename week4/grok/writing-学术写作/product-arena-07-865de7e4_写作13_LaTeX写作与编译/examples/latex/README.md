# SYNTHETIC EXAMPLE — latex (interface demo, NOT a formal answer)

Tiny synthetic content demonstrating LaTeX source generation: main.tex + references.bib,
structure validation (balanced braces, matched \begin/\end, required sections, \cite
keys in bib, \ref labels defined). No local LaTeX compiler -> compile honestly deferred
to the runtime latex-compiler (status success with a latex_compile uncertainty item).

Run from the package root:

```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/latex/ir.json \
  --input examples/latex/input \
  --out /tmp/arena_latex_demo
```

Expected: exit 0, validation ok; main.tex + references.bib + structure_check.json
(ok=true) + compile_report.json (compiled=false, reason=no local compiler) + result.json.
At runtime with a TeX compiler, the engine runs latexmk/pdflatex and emits main.pdf.