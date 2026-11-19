# Systematic literature review (系统性文献综述)

Bohrium weekly contest · research track · kind `systematic_review` · challenge challenge-51977f9b.
Source-bound Skill: the agent reads actual /input material -> fills a Research IR -> a
deterministic stdlib engine validates/recomputes PRISMA + dedup/re-verifies quotes ->
editable artifacts (md/docx/csv/svg) + bidirectional provenance + honest result.json. No
pre-baked answers.

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir research_ir.json --input /input --out /app/output
```
Synthetic demo:
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/systematic_review/ir.json \
  --input examples/systematic_review/input --out /tmp/demo
```

## Files
- SKILL.md — skill contract + workflow + IR schema + domain rules + self-check
- assemble.py — CLI pipeline (validate -> build -> summarize -> result.json)
- research_engine.py — validate_ir + compute_screening (PRISMA + dedup) / synthesis +
  check_quotes + build (md/docx/csv/svg) + provenance + summarize (stdlib)
- w4kit.py — shared core (case load, source check, dedup, stats, result.json)
- rules/rules_systematic_review.md — protocol-first, two-stage screening, quality appraisal
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — method + failure handling
- examples/systematic_review/ — SYNTHETIC interface demo (input + ir.json + README)
- requirements.txt — Python 3.10+ stdlib (no third-party; numpy optional)
- GITHUB_URL.txt — public repo link for the +5 bonus (placeholder until git sync)

## Scope & limits
- Bounded to the provided corpus (provided_sources_only). Protocol (criteria + executable
  queries with date/database) is written FIRST; screening decisions conform to it.
- PRISMA counts and dedup are recomputed by the engine (not hand-computed). Every included
  record needs a quality appraisal with located evidence. Quotes re-verified against real
  files; binary/PDF quotes `unverifiable` + declared uncertain.
- Conclusions supported by included evidence; conflicts surfaced; gaps grounded + human_confirm.

## Honesty
status success/partial/failed reflects real validation + build state. result.json keeps
every output_contract key + case_id + sources + uncertainty + change_log + prisma +
exclusion_reasons + quote_check_summary + human_confirm + boundary. Missing material ->
partial, never invent.

## Self-check
See the checklist in SKILL.md. Re-run assemble.py on the synthetic example: it must exit 0
with status success (0 errors / 0 warnings), balanced PRISMA and all example quotes verified.