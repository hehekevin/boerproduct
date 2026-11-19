# Experiment parameter optimization advice (实验参数优化建议)

Bohrium weekly contest · experiment track · kind param_optimize
Source-bound Skill: agent reads actual /input material → fills Parameter IR →
deterministic stdlib engine validates/computes → editable artifacts + provenance +
honest result.json.

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir params_ir.json --input /input --out /app/output
```

## Files
- SKILL.md — skill contract + workflow + IR schema + domain rules + self-check
- assemble.py — CLI pipeline (validate → build → result.json)
- experiment_engine.py — design/feasibility/param/compare/anomaly engine (stdlib)
- w4kit.py — shared core (case load, source check, safe_eval, stats, result.json)
- rules/rules_param_optimize.md — kind-specific optimization rules
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — method + failure handling
- examples/param_optimize/ — SYNTHETIC interface demo (input + ir.json)
- requirements.txt — Python 3.10+ stdlib (no third-party)
- GITHUB_URL.txt — public repo link for the +5 bonus

## Kind
param_optimize

## Honesty
Reported optimum vs inferred suggestion distinguished; recommendations checked against
range + device limits; observed-best recomputed from data; numeric checks via safe_eval;
missing → not_reported + human_confirm. Status reflects real gaps.