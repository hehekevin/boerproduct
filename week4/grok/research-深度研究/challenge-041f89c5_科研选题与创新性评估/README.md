# Research topic selection & novelty assessment (科研选题与创新性评估)

Bohrium weekly contest · research track · kind `topic_novelty` · challenge challenge-041f89c5.
Source-bound Skill: the agent reads actual /input prior work -> fills a Research IR -> a
deterministic stdlib engine DERIVES novelty verdicts from coverage, re-verifies quotes ->
editable artifacts (md/docx/csv/svg) + novelty_assessment.json + provenance + honest
result.json. No pre-baked verdict.

## Run
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir research_ir.json --input /input --out /app/output
```
Synthetic demo:
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/topic_novelty/ir.json \
  --input examples/topic_novelty/input --out /tmp/demo
```

## Files
- SKILL.md — skill contract + workflow + IR schema + domain rules + self-check
- assemble.py — CLI pipeline (validate -> build -> summarize -> result.json)
- research_engine.py — validate_ir + compute_novelty/screening/synthesis + check_quotes +
  build (md/docx/csv/svg) + novelty_assessment.json + provenance + summarize (stdlib)
- w4kit.py — shared core (case load, source check, dedup, stats, result.json)
- rules/rules_topic_novelty.md — falsifiable question, comparison, coverage-derived novelty, feasibility
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — method + failure handling
- examples/topic_novelty/ — SYNTHETIC interface demo (input + ir.json + README)
- requirements.txt — Python 3.10+ stdlib (no third-party; numpy optional)
- GITHUB_URL.txt — public repo link for the +5 bonus (placeholder until git sync)

## Scope & limits
- Bounded to the provided corpus (provided_sources_only). Novelty verdicts are DERIVED from
  declared coverage (full->covered, partial->partially_overlapping, all none->
  novel_within_sources); a declared verdict that disagrees is rejected. No global novelty.
- Four deliverables must be consistent: falsifiable question definition, correctly-chosen
  prior-work comparison, novelty items with uncertainty, feasibility premises (supported
  needs evidence; assumption/unknown -> human_confirm). All judgments prospective; no
  completed experiments. Quotes re-verified; binary/PDF quotes `unverifiable` + uncertain.

## Honesty
status success/partial/failed reflects real validation + build state. result.json keeps
every output_contract key + case_id + sources + uncertainty + change_log + prisma +
novelty_summary + human_confirm + quote_check_summary + boundary. Missing material ->
partial, never invent.

## Self-check
See the checklist in SKILL.md. Re-run assemble.py on the synthetic example: it must exit 0
with status success (0 errors / 0 warnings), all novelty verdicts matching coverage and all
example quotes verified.