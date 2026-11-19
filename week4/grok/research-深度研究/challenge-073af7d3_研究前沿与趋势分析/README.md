# Research front & trend analysis (研究前沿与趋势分析)

Bohrium weekly contest · research track · kind `trend_analysis` · challenge challenge-073af7d3.
Source-bound Skill: the agent reads actual /input material -> fills a Research IR -> a
deterministic stdlib engine RECOMPUTES year histogram / theme-year evolution / direction /
growth / phase consistency, re-verifies quotes -> editable artifacts (md/docx/csv/svg) +
trend_stats.json + provenance + honest result.json. No pre-baked frontier list.

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir research_ir.json --input /input --out /app/output
```
Synthetic demo:
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/trend_analysis/ir.json \
  --input examples/trend_analysis/input --out /tmp/demo
```

## Files
- SKILL.md — skill contract + workflow + IR schema + domain rules + self-check
- assemble.py — CLI pipeline (validate -> build -> summarize -> result.json)
- research_engine.py — validate_ir + compute_trend/screening/synthesis + check_quotes +
  build (md/docx/csv/svg) + trend_stats.json + provenance + summarize (stdlib)
- w4kit.py — shared core (case load, source check, dedup, stats, result.json)
- rules/rules_trend_analysis.md — year basis, theme evolution, phases, representative works
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — method + failure handling
- examples/trend_analysis/ — SYNTHETIC interface demo (input + ir.json + README)
- requirements.txt — Python 3.10+ stdlib (no third-party; numpy optional)
- GITHUB_URL.txt — public repo link for the +5 bonus (placeholder until git sync)

## Scope & limits
- Bounded to the provided corpus (provided_sources_only). All trends are DESCRIPTIVE
  small-sample statistics; the engine emits a caveat. No field-wide/global trend claims.
- Year histogram, theme-by-year matrix, direction and growth are RECOMPUTED from the IR
  (sources/years/themes/claims), not hand-computed. Missing years are declared, never guessed.
- Phase representative works must be registered, in scope, and year-inside-window. Quotes
  re-verified against real files; binary/PDF quotes `unverifiable` + declared uncertain.

## Honesty
status success/partial/failed reflects real validation + build state. result.json keeps
every output_contract key + case_id + sources + uncertainty + change_log + prisma +
trend_summary + quote_check_summary + boundary. Missing material -> partial, never invent.

## Self-check
See the checklist in SKILL.md. Re-run assemble.py on the synthetic example: it must exit 0
with status success (0 errors / 0 warnings), a non-empty year histogram and all phase
representative works in-window.