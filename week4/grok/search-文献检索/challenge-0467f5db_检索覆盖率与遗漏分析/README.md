# search-coverage-analysis — Bohrium week4 SEARCH track Skill

Source-bound Skill for **检索覆盖率与遗漏分析** (`challenge-0467f5db`, kind `coverage_analysis`).
The agent reads the ACTUAL organizer-provided local materials under /input,
fills a structured IR, and a deterministic stdlib engine (`search_engine.py`)
validates it and performs the real computation (independent recall + miss attribution + supplementary-round gain). Outputs are
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
input file/response and locator.

## Quick start
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
Synthetic interface demo (NOT a formal answer):
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/coverage_analysis/ir.json --input examples/coverage_analysis/input --out /tmp/demo
```

## Files
- SKILL.md — trigger description, workflow, IR schema, domain rules, self-check
- assemble.py — CLI (validate -> build -> result.json)
- search_engine.py — deterministic engine (validate_ir + build; all 11 search kinds)
- w4kit.py — shared core (case load, source check, dedup, result assembly)
- rules/rules_coverage_analysis.md — domain rules the agent follows to fill the IR
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — step-by-step + failure handling
- examples/coverage_analysis/ — tiny SYNTHETIC input + accepted ir.json (labelled EXAMPLE)

## Dependencies
Python 3.10+ standard library only (see requirements.txt). No network access,
no third-party packages, no binaries.

## Scope & limits
- Finite organizer-provided snapshot only; NO live database coverage, global
  recall, latest-publication or novelty claims.
- Recall is over the frozen provided known-item list, not global literature coverage; fuzzy matches keep a human arbitration entry. Base recall uses the final record set, so supplementary rounds document the query process and their gain is computed against remaining misses.
- Honest status: success / partial / failed / stuck; gaps flagged human_confirm.

## Self-check (before handover)
- [ ] reference set independent + frozen; every item source_id + inclusion_reason; unusable flagged
- [ ] hit table complete with match_method; recall uses usable denominator
- [ ] every miss attributed to specific query/field/window/source; residual explained
- [ ] supplementary rounds show real new hits / zero-gain honesty

## Hard-constraint self-check
- <=50 UTF-8 text files, <=500KB each, <=2MB total; no binaries/__pycache__/symlinks.
- Run python with PYTHONDONTWRITEBYTECODE=1; result.json preserves every
  output_contract key + case_id.
