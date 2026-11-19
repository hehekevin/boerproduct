# review-quality-review — manuscript quality audit Skill

Bohrium weekly contest (play.bohrium.com, contest bohr-product, period 4),
REVIEW track, challenge-0999879e (论文质量审查). Kind: `quality_review`.

Source-bound Skill: the agent reads the ACTUAL organizer-provided local
material under /input, fills a structured Review IR, and a deterministic
stdlib engine validates it, verifies evidence quotes against the real text,
computes coverage/scores, and writes editable artifacts + provenance + an
honest result.json. No pre-baked answers.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
See SKILL.md (agent workflow + IR schema), rules/rules_quality_review.md
(domain rules), docs/WORKFLOW.md (steps), docs/ERROR_HANDLING.md (failure modes).

## Files
- SKILL.md — skill entry (frontmatter + workflow + IR schema + self-check)
- assemble.py — CLI contract (validate → build → result.json)
- review_engine.py — shared deterministic engine for all 5 review kinds
- w4kit.py — shared source-bound core (case load, evidence, stats, result)
- rules/rules_quality_review.md — domain rules for filling the IR
- docs/ — workflow + error handling
- examples/quality_review/ — SYNTHETIC interface demo (input/ + ir.json)

## Dependencies
Python 3.10+ standard library only (see requirements.txt). No network calls.

## Outputs
review.json, checklist.csv, report.md, provenance.json, validation.json,
result.json (echoes every output_contract key + case_id + honest status +
sources + uncertainty + change_log).

## Scope & limits
- Reviews overall quality/structure/factual consistency/publishability of the
  provided manuscript; NOT language polishing, translation, text-matching
  plagiarism detection, or typesetting.
- Judgments are only as good as the provided material: missing references/data
  → insufficient_evidence / uncheckable + human_confirm, never invented.
- Quote verification works on readable text; scanned PDFs need honest
  transcription limits recorded.

## Self-test
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/quality_review/ir.json \
  --input examples/quality_review/input --out /tmp/demo-quality
```
Expected: exit 0, no validation errors, status partial (the demo deliberately
contains an unverifiable novelty claim), 0 locator issues.

## Maintenance
Engine shared verbatim across the 5 review packages; keep copies in sync.
Record IR edits in provenance.changes. GITHUB_URL.txt is filled by git_sync.