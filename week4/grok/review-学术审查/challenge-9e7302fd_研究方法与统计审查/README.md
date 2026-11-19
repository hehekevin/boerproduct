# review-methods-stats-review — methods & statistics audit Skill

Bohrium weekly contest (play.bohrium.com, contest bohr-product, period 4),
REVIEW track, challenge-9e7302fd (研究方法与统计审查). Kind: `methods_stats_review`.

Source-bound Skill: the agent reads the ACTUAL organizer-provided local
material under /input (manuscript + data tables), fills a structured Review IR,
and a deterministic stdlib engine validates it, verifies evidence quotes,
RECOMPUTES reported statistics from the real data (describe/correlation/linreg/
safe expression eval), compares with explicit tolerances, and writes editable
artifacts + provenance + an honest result.json. No pre-baked answers.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
See SKILL.md (workflow + IR schema), rules/rules_methods_stats_review.md,
docs/WORKFLOW.md, docs/ERROR_HANDLING.md.

## Files
- SKILL.md — skill entry (frontmatter + workflow + IR schema + self-check)
- assemble.py — CLI contract (validate → build → result.json)
- review_engine.py — shared deterministic engine for all 5 review kinds
- w4kit.py — shared source-bound core (case load, evidence, stats, result)
- rules/rules_methods_stats_review.md — domain rules for filling the IR
- docs/ — workflow + error handling
- examples/methods_stats_review/ — SYNTHETIC interface demo (input/ + ir.json)

## Dependencies
Python 3.10+ standard library only (see requirements.txt). No network calls.

## Outputs
review.json (findings + stats_checks with computed values and per-key
match/mismatch comparisons), checklist.csv, report.md, provenance.json,
validation.json, result.json (echoes every output_contract key + case_id +
honest status + sources + uncertainty + change_log).

## Scope & limits
- Audits design/variables/tests/power/reporting of the PROVIDED manuscript;
  does not run new analyses for the authors or replace peer review.
- Recomputation covers descriptive stats, Pearson correlation, OLS slope/R2 and
  AST-safe arithmetic expressions; no p-value distribution functions (stdlib
  only) — p/CI checks are consistency checks, clearly labeled as such.
- Missing data → not_recomputable + human_confirm; reported values are never
  silently replaced by computed ones.

## Self-test
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/methods_stats_review/ir.json \
  --input examples/methods_stats_review/input --out /tmp/demo-methods
```
Expected: exit 0, no validation errors, status partial (ST4 not_recomputable),
ST1 sd mismatch (1.5 reported vs 1.309307 computed), ST2/ST3 match,
0 locator issues.

## Maintenance
Engine shared verbatim across the 5 review packages; keep copies in sync.
Record IR edits in provenance.changes. GITHUB_URL.txt is filled by git_sync.