# search-quality-appraisal — Bohrium week4 SEARCH track Skill

Source-bound Skill for **文献研究质量评价** (`challenge-bace1c46`, kind `quality_appraisal`).
The agent reads the ACTUAL organizer-provided local materials under /input,
fills a structured IR, and a deterministic stdlib engine (`search_engine.py`)
validates it and performs the real computation (dimension-level appraisal + evidence locators + honest aggregation). Outputs are
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
input file/response and locator.

## Quick start
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
Synthetic interface demo (NOT a formal answer):
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/quality_appraisal/ir.json --input examples/quality_appraisal/input --out /tmp/demo
```

## Files
- SKILL.md — trigger description, workflow, IR schema, domain rules, self-check
- assemble.py — CLI (validate -> build -> result.json)
- search_engine.py — deterministic engine (validate_ir + build; all 11 search kinds)
- w4kit.py — shared core (case load, source check, dedup, result assembly)
- rules/rules_quality_appraisal.md — domain rules the agent follows to fill the IR
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — step-by-step + failure handling
- examples/quality_appraisal/ — tiny SYNTHETIC input + accepted ir.json (labelled EXAMPLE)

## Dependencies
Python 3.10+ standard library only (see requirements.txt). No network access,
no third-party packages, no binaries.

## Scope & limits
- Finite organizer-provided snapshot only; NO live database coverage, global
  recall, latest-publication or novelty claims.
- Appraisal covers the provided documents and the chosen scale only; it is not peer review or a clinical/policy decision.
- Honest status: success / partial / failed / stuck; gaps flagged human_confirm.

## Self-check (before handover)
- [ ] scale defined with applicability; every applicable dimension judged or flagged
- [ ] every non-abstain judgment has sentence/table locator + quote + grade + rationale
- [ ] unreported -> abstain (unclear), never fabricated; critical abstain -> overall unclear
- [ ] aggregation rule stated; second reviewer can re-derive grades from locators

## Hard-constraint self-check
- <=50 UTF-8 text files, <=500KB each, <=2MB total; no binaries/__pycache__/symlinks.
- Run python with PYTHONDONTWRITEBYTECODE=1; result.json preserves every
  output_contract key + case_id.
