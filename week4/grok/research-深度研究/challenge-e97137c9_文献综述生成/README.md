# Literature review generation (文献综述生成)

Bohrium weekly contest · research track · kind `lit_review` · challenge challenge-e97137c9.
Source-bound Skill: the agent reads actual /input literature -> fills a Research IR -> a
deterministic stdlib engine validates/recomputes/re-verifies quotes -> an editable review
draft (md/docx) + evidence matrix (csv) + screening log + PRISMA svg + provenance + honest
result.json. No pre-baked answers.

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir research_ir.json --input /input --out /app/output
```
Synthetic demo:
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/lit_review/ir.json \
  --input examples/lit_review/input --out /tmp/demo
```

## Files
- SKILL.md — skill contract + workflow + IR schema + domain rules + self-check
- assemble.py — CLI pipeline (validate -> build -> summarize -> result.json)
- research_engine.py — validate_ir + compute_screening/synthesis + check_quotes + build
  (md/docx/csv/svg) + provenance + summarize (stdlib)
- w4kit.py — shared core (case load, source check, dedup, stats, result.json)
- rules/rules_lit_review.md — kind-specific rules (theme induction, claim-evidence, strength)
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — method + failure handling
- examples/lit_review/ — SYNTHETIC interface demo (input + ir.json + README)
- requirements.txt — Python 3.10+ stdlib (no third-party; numpy optional)
- GITHUB_URL.txt — public repo link for the +5 bonus (placeholder until git sync)

## Scope & limits
- Bounded to the provided literature (provided_sources_only). Themes are induced FROM the
  sources; no external taxonomy imposed. No field-wide completeness/novelty claims.
- Every claim binds an EXACT quote re-verified against the real file; citation strength
  matches the original. Binary/PDF quotes are `unverifiable` + declared uncertain.
- Pro/con evidence and conclusion divergence are surfaced (conflicts, contested claims);
  gaps are grounded with evidence or a documented search scope + human_confirm.

## Honesty
status success/partial/failed reflects real validation + build state. result.json keeps
every output_contract key + case_id + sources + uncertainty + change_log + prisma +
synthesis_stats + quote_check_summary + boundary. Missing material -> partial, never invent.

## Self-check
See the checklist in SKILL.md. Re-run assemble.py on the synthetic example: it must exit 0
with status success (0 errors / 0 warnings) and all example quotes verified.