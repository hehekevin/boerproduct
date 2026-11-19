# analysis-multi-step (agent-6aefb2fd)

Source-bound Skill for the Bohrium weekly contest ANALYSIS track — 多步骤数据分析Agent.
Agent reads the actual organizer material under /input, decomposes the task into an ordered
pipeline (load → clean → stats → viz → query → interpret), fills an IR; a deterministic stdlib
engine orchestrates the steps over a shared data context with per-step provenance, intermediate
artifacts, honest step status, and report-number back-fill verification. Not pre-baked answers.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
See SKILL.md, rules/rules_multi_step_analysis.md, docs/WORKFLOW.md, docs/ERROR_HANDLING.md.

## Files
SKILL.md; assemble.py; analysis_engine.py; w4kit.py; rules/rules_multi_step_analysis.md; docs/;
examples/multi_step_analysis/ (SYNTHETIC input/ + ir.json + README).

## Dependencies
Python 3.10+ standard library (reuses the cleaning/stats/charts/queries sub-engines).
matplotlib OPTIONAL (PNG previews only). See requirements.txt.

## Scope & limits
- Orchestrates load/clean/stats/viz/query/interpret steps with dependency ordering; clean
  feeds downstream via a shared data context; interpret claims cross-checked vs metrics.
- Each step uses the same deterministic logic as the sibling single-kind skills (see their
  limits: no imputation, Welch/ANOVA, stdlib p-values, data-bound SVG, read-only SQL).
- Does NOT do experiment design or paper writing; faceting/3D not implemented; paired designs
  flagged. A failed step skips dependents (honest cascade), never fabricates.

## Self-check
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/multi_step_analysis/ir.json --input examples/multi_step_analysis/input \
  --out w4/.tmp_analysis/agent-6aefb2fd
```
Expect exit 0, no validation errors, status success, back-fill checks pass. Delete any
__pycache__; keep PNG out of the package. Hard limits: ≤50 UTF-8 text files, ≤500KB each,
≤2MB total, no binaries/symlinks.