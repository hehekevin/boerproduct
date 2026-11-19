# Experiment protocol feasibility assessment (实验方案可行性评估)

Bohrium weekly contest · experiment track · kind feasibility
Source-bound Skill: agent reads actual /input material → fills Feasibility IR →
deterministic stdlib engine validates/recomputes verdicts → editable artifacts +
provenance + honest result.json.

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir feasibility_ir.json --input /input --out /app/output
```

## Files
- SKILL.md — skill contract + workflow + IR schema + domain rules + self-check
- assemble.py — CLI pipeline (validate → build → result.json)
- experiment_engine.py — design/feasibility/param/compare/anomaly engine (stdlib)
- w4kit.py — shared core (case load, source check, safe_eval, stats, result.json)
- rules/rules_feasibility.md — kind-specific review rules
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — method + failure handling
- examples/feasibility/ — SYNTHETIC interface demo (input + ir.json)
- requirements.txt — Python 3.10+ stdlib (no third-party)
- GITHUB_URL.txt — public repo link for the +5 bonus

## Kind
feasibility

## Honesty
No inventory evidence → not_reported + human_confirm (never assumed feasible);
need>available → blocker with shortfall; reported vs inferred distinguished;
status success/partial/failed reflects real gaps. Finding blockers is completion.