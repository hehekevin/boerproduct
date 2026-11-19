# review-logic-argument-review — logic & argumentation audit Skill

Bohrium weekly contest (play.bohrium.com, contest bohr-product, period 4),
REVIEW track, challenge-16d4414d (论文逻辑与论证审查). Kind: `logic_argument_review`.

Source-bound Skill: the agent reads the ACTUAL organizer-provided local
material under /input, fills a structured Review IR (claims, premise→conclusion
arguments, consistency pairs), and a deterministic stdlib engine validates it,
verifies evidence quotes against the real text, computes validity/consistency
summaries, and writes editable artifacts + provenance + an honest result.json.
No pre-baked answers; every reported problem points to a real sentence.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
See SKILL.md (workflow + IR schema), rules/rules_logic_argument_review.md,
docs/WORKFLOW.md, docs/ERROR_HANDLING.md.

## Files
- SKILL.md — skill entry (frontmatter + workflow + IR schema + self-check)
- assemble.py — CLI contract (validate → build → result.json)
- review_engine.py — shared deterministic engine for all 5 review kinds
- w4kit.py — shared source-bound core (case load, evidence, result)
- rules/rules_logic_argument_review.md — domain rules for filling the IR
- docs/ — workflow + error handling
- examples/logic_argument_review/ — SYNTHETIC interface demo (input/ + ir.json)

## Dependencies
Python 3.10+ standard library only (see requirements.txt). No network calls.

## Outputs
review.json (arguments + premises + validity + consistency checks + findings),
checklist.csv, report.md, provenance.json, validation.json, result.json
(echoes every output_contract key + case_id + honest status + sources +
uncertainty + change_log).

## Scope & limits
- Audits reasoning structure and internal consistency of the PROVIDED
  manuscript; does not rewrite the paper or judge scientific novelty.
- Validity/fallacy verdicts are agent judgments bound to verified quotes; the
  engine enforces structure (premises exist, locators resolve) and aggregates.
- Unstated assumptions are labeled inferred; absent premises not_reported +
  human_confirm — never invented to make an argument look valid.

## Self-test
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py \
  --ir examples/logic_argument_review/ir.json \
  --input examples/logic_argument_review/input --out /tmp/demo-logic
```
Expected: exit 0, no validation errors, status partial (L2 insufficient
evidence: no quantitative results provided), 1 gap + 1 fallacy
(argument_from_ignorance) + 1 inconsistent pair, 0 locator issues.

## Maintenance
Engine shared verbatim across the 5 review packages; keep copies in sync.
Record IR edits in provenance.changes. GITHUB_URL.txt is filled by git_sync.