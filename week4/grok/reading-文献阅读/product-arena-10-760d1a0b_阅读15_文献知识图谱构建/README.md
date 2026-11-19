# arena-knowledge-graph (阅读15文献知识图谱构建, kind=knowledge_graph)

Source-bound Skill for the Bohrium weekly product-arena reading track. The Agent
reads the ACTUAL organizer material under /input, extracts real entities and typed
directed relations with evidence locators, normalizes aliases and answers >=3 real
queries; a deterministic stdlib engine validates relation vocabulary/endpoints/
status, computes graph stats and builds editable graph.json + layered graph.svg +
honest result.json.

## Usage
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output
```
Exit 0 = validation ok; exit 2 = validation errors (honest partial result still written).

## Files
- SKILL.md — trigger, workflow, IR schema, self-check (entry point)
- assemble.py — CLI; arena_read_engine.py — validate_ir + graph computation + build
- svgkit.py — layered editable SVG builder (stdlib); readkit.py / figkit.py — reused reading core
- rules/rules_knowledge_graph.md — entity/relation/alignment/query rules
- docs/WORKFLOW.md, docs/ERROR_HANDLING.md
- examples/knowledge_graph/ — SYNTHETIC interface demo (not a formal answer)

## Dependencies
Python 3.10+ standard library only. No third-party packages, no network, no graph
database (graph.json is the queryable artifact; queries answered with evidence).

## Scope & limits
- Builds from provided local material only; no commonsense entity/relation补全.
- No pre-baked graphs; gaps use the status vocabulary + human_confirm; result.json
  honest success/partial/failed. SVG is text (editable); no binary assets in package.

## Self-check
Run the synthetic example (see SKILL.md): exit 0, validation ok, graph.svg written
with data-source locators, graph_check.json stats computed, 3 queries answered,
result.json honest.