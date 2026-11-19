# Deep research agent (深度研究 Agent)

Bohrium weekly contest · research track · kind `deep_research` · challenge agent-f8fb8bda.
Source-bound Skill: the agent reads actual /input material -> fills a Research IR -> a
deterministic stdlib engine validates/recomputes/re-verifies quotes -> editable artifacts
(md/docx/csv/svg) + bidirectional provenance + honest result.json. No pre-baked answers.

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir research_ir.json --input /input --out /app/output
```
Synthetic demo:
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/deep_research/ir.json \
  --input examples/deep_research/input --out /tmp/demo
```

## Files
- SKILL.md — skill contract + workflow + IR schema + domain rules + self-check
- assemble.py — CLI pipeline (validate -> build -> summarize -> result.json)
- research_engine.py — validate_ir + compute_screening/synthesis/trend/novelty +
  check_quotes + build (md/docx/csv/svg) + provenance + summarize (stdlib)
- w4kit.py — shared core (case load, source check, dedup, stats, result.json)
- rules/rules_deep_research.md — kind-specific scientific rules for filling the IR
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — method + failure handling
- examples/deep_research/ — SYNTHETIC interface demo (input + ir.json + README)
- requirements.txt — Python 3.10+ stdlib (no third-party; numpy optional)
- GITHUB_URL.txt — public repo link for the +5 bonus (placeholder until git sync)

## Scope & limits
- Bounded to the provided corpus (provided_sources_only). No field-wide novelty or
  completeness claims; no completed experiments. The proposal is prospective.
- Quotes are re-verified against real text files; binary/PDF quotes are `unverifiable`
  and declared uncertain (human_confirm). PRISMA counts and dedup are recomputed.
- Conflicts are presented both sides; gaps need evidence or a documented search scope.

## Honesty
status success/partial/failed reflects real validation + build state. result.json keeps
every output_contract key + case_id + sources + uncertainty + change_log + prisma +
quote_check_summary + human_confirm + boundary. Missing material -> partial, never invent.

## Self-check
See the checklist in SKILL.md. Re-run assemble.py on the synthetic example: it must exit 0
with status success (0 errors / 0 warnings) and all example quotes verified.