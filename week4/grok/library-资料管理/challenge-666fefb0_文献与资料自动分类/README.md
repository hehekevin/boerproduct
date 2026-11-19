# Literature & material auto-classification (文献与资料自动分类)

Bohrium weekly contest · library track · kind library_classify
Source-bound Skill: agent reads actual /input material → fills Reading IR →
deterministic stdlib engine validates/computes → editable artifacts + provenance +
honest result.json.

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir library_ir.json --input /input --out /app/output
```

## Files
- SKILL.md — skill contract + workflow + IR schema + domain rules + self-check
- assemble.py — CLI pipeline (validate → build → result.json)
- library_engine.py — index/search/classify/QA/annotation engine (stdlib)
- w4kit.py — shared core (case load, source check, stats, result.json)
- rules/rules_library_classify.md — kind-specific scientific/organisational rules
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — method + failure handling
- examples/classify/ — SYNTHETIC interface demo (input + ir.json)
- requirements.txt — Python 3.10+ stdlib (no third-party)
- GITHUB_URL.txt — public repo link for the +5 bonus

## Kind
library_classify

## Honesty
Missing → not_reported/insufficient_evidence/abstain/no_hits; conflicts surfaced;
operations logged with reasons; status success/partial/failed reflects real gaps.
