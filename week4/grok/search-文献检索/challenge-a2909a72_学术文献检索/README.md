# search-query-planning — Bohrium week4 SEARCH track Skill

Source-bound Skill for **学术文献检索** (`challenge-a2909a72`, kind `query_planning`).
The agent reads the ACTUAL organizer-provided local materials under /input,
fills a structured IR, and a deterministic stdlib engine (`search_engine.py`)
validates it and performs the real computation (dedup + facet recall + explainable ranking + metrics@k). Outputs are
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
input file/response and locator.

## Quick start
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output
```
Synthetic interface demo (NOT a formal answer):
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/query_planning/ir.json --input examples/query_planning/input --out /tmp/demo
```

## Files
- SKILL.md — trigger description, workflow, IR schema, domain rules, self-check
- assemble.py — CLI (validate -> build -> result.json)
- search_engine.py — deterministic engine (validate_ir + build; all 11 search kinds)
- w4kit.py — shared core (case load, source check, dedup, result assembly)
- rules/rules_query_planning.md — domain rules the agent follows to fill the IR
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md — step-by-step + failure handling
- examples/query_planning/ — tiny SYNTHETIC input + accepted ir.json (labelled EXAMPLE)

## Dependencies
Python 3.10+ standard library only (see requirements.txt). No network access,
no third-party packages, no binaries.

## Scope & limits
- Finite organizer-provided snapshot only; NO live database coverage, global
  recall, latest-publication or novelty claims.
- Ranking metrics use agent-judged graded labels, not organizer ground truth; recall is over the provided finite exports only.
- Honest status: success / partial / failed / stuck; gaps flagged human_confirm.

## Self-check (before handover)
- [ ] research_question + facets registered; every query keeps original string, database, round, facet
- [ ] every record has source_id + snippet + matched_queries; no invented records
- [ ] features/rationale per ranked record; duplicates kept with provenance (engine merges)
- [ ] uncovered facets / no_hits / missing metadata explicit; metrics labelled agent-judged

## Hard-constraint self-check
- <=50 UTF-8 text files, <=500KB each, <=2MB total; no binaries/__pycache__/symlinks.
- Run python with PYTHONDONTWRITEBYTECODE=1; result.json preserves every
  output_contract key + case_id.
