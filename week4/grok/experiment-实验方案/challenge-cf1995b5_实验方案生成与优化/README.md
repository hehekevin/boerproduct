# Experiment protocol generation & optimization (实验方案生成与优化)

Bohrium weekly contest · experiment track · kind protocol_design
Source-bound Skill: agent reads actual /input material → fills Design IR →
deterministic stdlib engine validates/computes → editable artifacts + provenance +
honest result.json.

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir design_ir.json --input /input --out /app/output
```

## Files
- SKILL.md — skill contract + workflow + IR schema + domain rules + self-check
- assemble.py — CLI pipeline (validate → build → result.json)
- experiment_engine.py — design/feasibility/param/compare/anomaly engine (stdlib)
- w4kit.py — shared core (case load, source check, safe_eval, stats, result.json)
- rules/rules_protocol_design.md — kind-specific scientific rules
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — method + failure handling
- examples/protocol_design/ — SYNTHETIC interface demo (input + ir.json)
- requirements.txt — Python 3.10+ stdlib (no third-party)
- GITHUB_URL.txt — public repo link for the +5 bonus

## Kind
protocol_design

## Honesty
Missing → not_reported/insufficient_evidence + human_confirm; reported vs inferred
distinguished; range violations surfaced; status success/partial/failed reflects real
gaps. Finding risks is completion, not failure.