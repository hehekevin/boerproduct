# review-citation-fact-check — citation & fact verification Skill

Bohrium weekly contest (play.bohrium.com, contest bohr-product, period 4),
REVIEW track, challenge-cbe96f01 (引用与事实核验). Kind: `citation_fact_check`.

Source-bound Skill: the agent reads the ACTUAL organizer-provided local
material under /input (manuscript + provided reference texts), fills a
structured Review IR, and a deterministic stdlib engine validates it, verifies
evidence quotes against the real text, normalizes DOI/title, rolls up subclaim
support, and writes editable artifacts + provenance + an honest result.json.
No pre-baked answers; citation existence is never treated as citation support.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
See SKILL.md (workflow + IR schema), rules/rules_citation_fact_check.md,
docs/WORKFLOW.md, docs/ERROR_HANDLING.md.

## Files
- SKILL.md — skill entry (frontmatter + workflow + IR schema + self-check)
- assemble.py — CLI contract (validate → build → result.json)
- review_engine.py — shared deterministic engine for all 5 review kinds
- w4kit.py — shared source-bound core (case load, evidence, DOI/title, result)
- rules/rules_citation_fact_check.md — domain rules for filling the IR
- docs/ — workflow + error handling
- examples/citation_fact_check/ — SYNTHETIC interface demo (input/ + ir.json)

## Dependencies
Python 3.10+ standard library only (see requirements.txt). No network calls.

## Outputs
review.json (claims + subclaim support + reference metadata checks + flags),
checklist.csv, report.md, provenance.json, validation.json, result.json
(echoes every output_contract key + case_id + honest status + sources +
uncertainty + change_log).

## Scope & limits
- Verifies claims/citations against PROVIDED source material only; no live
  lookup of publishers, databases or retraction registries.
- Unprovided references → not_provided + human_confirm; existence never assumed.
- Support grades are agent judgments bound to verified quotes; the engine
  computes the claim-level rollup deterministically (worst subclaim wins).

## Self-test
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/citation_fact_check/ir.json \
  --input examples/citation_fact_check/input --out /tmp/demo-citation
```
Expected: exit 0, no validation errors, status partial (over-generalized claim,
contradicted claim, year mis-citation, unprovided reference [3]), 0 locator
issues, 1 reference metadata_mismatch, 1 not_provided.

## Maintenance
Engine shared verbatim across the 5 review packages; keep copies in sync.
Record IR edits in provenance.changes. GITHUB_URL.txt is filled by git_sync.