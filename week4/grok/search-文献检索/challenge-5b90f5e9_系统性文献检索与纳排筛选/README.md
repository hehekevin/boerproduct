# search-systematic-screening — Bohrium week4 SEARCH track Skill

Source-bound Skill for **系统性文献检索与纳排筛选** (`challenge-5b90f5e9`, kind `systematic_screening`).
The agent reads the ACTUAL organizer-provided local materials under /input,
fills a structured IR, and a deterministic stdlib engine (`search_engine.py`)
validates it and performs the real computation (dual screening + adjudication + PRISMA count closure). Outputs are
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
input file/response and locator.

## Quick start
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
Synthetic interface demo (NOT a formal answer):
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/systematic_screening/ir.json --input examples/systematic_screening/input --out /tmp/demo
```

## Files
- SKILL.md — trigger description, workflow, IR schema, domain rules, self-check
- assemble.py — CLI (validate -> build -> result.json)
- search_engine.py — deterministic engine (validate_ir + build; all 11 search kinds)
- w4kit.py — shared core (case load, source check, dedup, result assembly)
- rules/rules_systematic_screening.md — domain rules the agent follows to fill the IR
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — step-by-step + failure handling
- examples/systematic_screening/ — tiny SYNTHETIC input + accepted ir.json (labelled EXAMPLE)

## Dependencies
Python 3.10+ standard library only (see requirements.txt). No network access,
no third-party packages, no binaries.

## Scope & limits
- Finite organizer-provided snapshot only; NO live database coverage, global
  recall, latest-publication or novelty claims.
- Screening is at title/abstract level over the provided export; full-text decisions and final scientific inclusion remain with researchers.
- Honest status: success / partial / failed / stuck; gaps flagged human_confirm.

## Self-check (before handover)
- [ ] protocol + frozen criteria recorded; reason codes decidable
- [ ] every record dual-reviewed with code + evidence; disagreements adjudicated with rationale
- [ ] PRISMA counts close over dedup clusters; exclusion reasons counted
- [ ] pending items in human_confirm queue; change_log kept

## Hard-constraint self-check
- <=50 UTF-8 text files, <=500KB each, <=2MB total; no binaries/__pycache__/symlinks.
- Run python with PYTHONDONTWRITEBYTECODE=1; result.json preserves every
  output_contract key + case_id.
