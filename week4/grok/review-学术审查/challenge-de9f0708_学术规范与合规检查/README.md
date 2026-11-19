# review-compliance-check — academic norms & compliance Skill

Bohrium weekly contest (play.bohrium.com, contest bohr-product, period 4),
REVIEW track, challenge-de9f0708 (学术规范与合规检查). Kind: `compliance_check`.

Source-bound Skill: the agent reads the ACTUAL organizer-provided local
material under /input, fills a structured Review IR (double-anchored checklist:
norm clause + manuscript locator), and a deterministic stdlib engine validates
it, verifies evidence quotes against the real text, computes per-category
coverage / compliance rate / missing-items list, and writes editable artifacts
+ provenance + an honest result.json. No pre-baked answers.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
See SKILL.md (workflow + IR schema), rules/rules_compliance_check.md,
docs/WORKFLOW.md, docs/ERROR_HANDLING.md.

## Files
- SKILL.md — skill entry (frontmatter + workflow + IR schema + self-check)
- assemble.py — CLI contract (validate → build → result.json)
- review_engine.py — shared deterministic engine for all 5 review kinds
- w4kit.py — shared source-bound core (case load, evidence, result)
- rules/rules_compliance_check.md — domain rules for filling the IR
- docs/ — workflow + error handling
- examples/compliance_check/ — SYNTHETIC interface demo (input/ + ir.json)

## Dependencies
Python 3.10+ standard library only (see requirements.txt). No network calls.

## Outputs
review.json (items + by-category coverage + compliance_rate + missing_items),
checklist.csv, report.md, provenance.json, validation.json, result.json
(echoes every output_contract key + case_id + honest status + sources +
uncertainty + change_log).

## Scope & limits
- Checks ethics/COI/data availability/authorship/reuse-risk/copyright/privacy/
  reporting-guideline/submission compliance of the PROVIDED manuscript.
- NOT a text-matching plagiarism service: reuse risk is flagged from observable
  signals with locators, never from fabricated similarity scores.
- Guideline texts not provided → named standard checklist with an explicit
  human_confirm uncertainty; approval numbers/registrations are never invented.
- Absence of a required STATEMENT → non_compliant; absence of underlying
  INFORMATION → insufficient_evidence (the distinction is enforced by rules).

## Self-test
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/compliance_check/ir.json \
  --input examples/compliance_check/input --out /tmp/demo-compliance
```
Expected: exit 0, no validation errors, status partial (CI2 consent + CI8 flow
insufficient_evidence), 3 non_compliant, 2 partial, 1 compliant,
compliance_rate 0.1667, 0 locator issues.

## Maintenance
Engine shared verbatim across the 5 review packages; keep copies in sync.
Record IR edits in provenance.changes. GITHUB_URL.txt is filled by git_sync.