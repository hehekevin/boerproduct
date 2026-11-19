# search-cross-language — Bohrium week4 SEARCH track Skill

Source-bound Skill for **跨语言文献检索** (`challenge-802a7115`, kind `cross_language`).
The agent reads the ACTUAL organizer-provided local materials under /input,
fills a structured IR, and a deterministic stdlib engine (`search_engine.py`)
validates it and performs the real computation (work/view identity + duplicate flags + term alignment). Outputs are
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
input file/response and locator.

## Quick start
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
Synthetic interface demo (NOT a formal answer):
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/cross_language/ir.json --input examples/cross_language/input --out /tmp/demo
```

## Files
- SKILL.md — trigger description, workflow, IR schema, domain rules, self-check
- assemble.py — CLI (validate -> build -> result.json)
- search_engine.py — deterministic engine (validate_ir + build; all 11 search kinds)
- w4kit.py — shared core (case load, source check, dedup, result assembly)
- rules/rules_cross_language.md — domain rules the agent follows to fill the IR
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — step-by-step + failure handling
- examples/cross_language/ — tiny SYNTHETIC input + accepted ir.json (labelled EXAMPLE)

## Dependencies
Python 3.10+ standard library only (see requirements.txt). No network access,
no third-party packages, no binaries.

## Scope & limits
- Finite organizer-provided snapshot only; NO live database coverage, global
  recall, latest-publication or novelty claims.
- Identity and alignment cover the provided works/views only; no live cross-language coverage or new-study claim.
- Honest status: success / partial / failed / stuck; gaps flagged human_confirm.

## Self-check (before handover)
- [ ] works established from actual documents; every view linked with language + body_language + version
- [ ] every view source-located; exact duplicates flagged, never double counted
- [ ] term alignments source-located and checkable; controlled translation recorded
- [ ] non-English counts over provided views only; no live-coverage claim

## Hard-constraint self-check
- <=50 UTF-8 text files, <=500KB each, <=2MB total; no binaries/__pycache__/symlinks.
- Run python with PYTHONDONTWRITEBYTECODE=1; result.json preserves every
  output_contract key + case_id.
