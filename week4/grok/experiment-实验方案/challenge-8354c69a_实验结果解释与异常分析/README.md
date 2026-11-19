# Experiment result interpretation & anomaly analysis (实验结果解释与异常分析)

Bohrium weekly contest · experiment track · kind result_anomaly
Source-bound Skill: agent reads actual /input material → fills Result IR →
deterministic stdlib engine validates/computes → editable artifacts + provenance +
honest result.json.

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir anomaly_ir.json --input /input --out /app/output
```

## Files
- SKILL.md — skill contract + workflow + IR schema + domain rules + self-check
- assemble.py — CLI pipeline (validate → build → result.json)
- experiment_engine.py — design/feasibility/param/compare/anomaly engine (stdlib)
- w4kit.py — shared core (case load, source check, describe, linreg, result.json)
- rules/rules_result_anomaly.md — kind-specific interpretation rules
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — method + failure handling
- examples/result_anomaly/ — SYNTHETIC interface demo (input + ir.json)
- requirements.txt — Python 3.10+ stdlib (no third-party)
- GITHUB_URL.txt — public repo link for the +5 bonus

## Kind
result_anomaly

## Honesty
Expected vs observed + tolerance recomputed; IQR outliers labelled inferred; causes
ranked by evidence support and never asserted as fact without data; unsupported →
insufficient_evidence + human_confirm; unexplained stated. Finding anomalies is
completion, not failure.