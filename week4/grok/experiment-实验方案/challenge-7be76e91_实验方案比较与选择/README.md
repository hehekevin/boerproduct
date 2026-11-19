# Experiment protocol comparison & selection (实验方案比较与选择)

Bohrium weekly contest · experiment track · kind protocol_compare
Source-bound Skill: agent reads actual /input material → fills Comparison IR →
deterministic stdlib engine validates/computes → editable artifacts + provenance +
honest result.json.

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir compare_ir.json --input /input --out /app/output
```

## Files
- SKILL.md — skill contract + workflow + IR schema + domain rules + self-check
- assemble.py — CLI pipeline (validate → build → result.json)
- experiment_engine.py — design/feasibility/param/compare/anomaly engine (stdlib)
- w4kit.py — shared core (case load, source check, safe_eval, stats, result.json)
- rules/rules_protocol_compare.md — kind-specific comparison rules
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — method + failure handling
- examples/protocol_compare/ — SYNTHETIC interface demo (input + ir.json)
- requirements.txt — Python 3.10+ stdlib (no third-party)
- GITHUB_URL.txt — public repo link for the +5 bonus

## Kind
protocol_compare

## Honesty
Every cell traceable; missing = not_reported (excluded, coverage reported);
normalization + weighted score + ranking + margin + tradeoffs + weight sensitivity
recomputable; fragile choice → human_confirm. Status reflects real gaps.