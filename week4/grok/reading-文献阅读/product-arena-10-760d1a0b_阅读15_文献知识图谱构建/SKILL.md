---
name: arena-knowledge-graph
description: Source-bound literature knowledge graph construction — read the ACTUAL organizer paper/workorder files under /input, extract real entities (researcher/material/method/task/metric/conclusion) and typed directed relations (uses/compares/outperforms/supports/contradicts/...), bind every node and edge to a paragraph locator + verbatim quote, normalize aliases with merge basis, answer >=3 real queries, and export editable graph.json + layered graph.svg + query results with reported/not_reported/source_conflict/extraction_failed/insufficient_evidence status; deterministic stdlib engine validates relation types, endpoints, duplicates and computes graph stats. Use for the "阅读15文献知识图谱构建" workorder (kind=knowledge_graph).
---

# 文献知识图谱构建 skill (knowledge_graph)

Source-bound reading skill. The Agent reads the ACTUAL material and fills the graph
IR (nodes + typed edges + queries, each with evidence); `assemble.py` deterministically
validates relation vocabulary/endpoints/locators/status, computes components/degrees/
query evidence, and builds editable graph.json + layered graph.svg + honest result.json.
Output triad: 解析结果 / 证据与边界 / 运行状态. Co-occurrence is NOT a relation.

## Focus (rubric)
- 抽得准: entities are objects that ACTUALLY appear in the material (researcher,
  material, method, task, metric, conclusion...); no commonsense补全; author claims
  vs third-party restatement distinguished (kind reported/inferred + note).
- 连得对: relation type + direction + conditions match原文; only evidence-backed
  edges; controlled vocabulary enforced by the engine.
- 对得齐: aliases/abbreviations/case variants normalized with explicit merge basis;
  engine flags duplicate labels; same-name different objects kept distinct.
- 查得到、回得去: >=3 real queries answered with node subgraph + supporting evidence;
  every node/edge carries source + paragraph_id + quote (also as data-source
  attributes in the editable SVG).

## Scope / trigger
Use when the case asks for 文献知识图谱 / entity-relation extraction (kind=knowledge_graph).
Only given local material; no online retrieval.

## Inputs (runtime) — READ THESE ACTUAL FILES FIRST
1. `/input/case.json` — copy case_id, read output_contract.
2. `/input/task.md` — topic scope, requested entity/relation types, query questions.
3. Workorder files when present (target-fields.json / workorder.json / queries.json).
4. ALL material files (one or more papers). Register every file actually used in
   sources[] (id + real path); cross-paper alignment keeps per-paper locators.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory /input; open case.json + task.md + workorder + material.
2. Fill IR per rules/rules_knowledge_graph.md: sources[], nodes[{id, label, type,
   aliases[]?, merge_basis?, kind, status, evidence[{source, paragraph_id, quote}]}],
   edges[{id, from, to, type, conditions?, kind, status, evidence[]}],
   queries[{id, question, answer, node_ids[]}], unanswered_parts, uncertainty, provenance.
3. Run exactly:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output`
   → validation.json → graph.json + graph.svg (editable layers) + graph_check.json
   (components/degrees/orphans/query evidence) + knowledge_graph_result.md →
   provenance.json → result.json.
4. Exit 0 = validation ok; exit 2 = errors → fix IR, re-run. Save honest partial
   early; budget 64 requests / 900 s.

## IR schema (minimal)
```json
{"ir_version":"1.0","case_id":"...","kind":"knowledge_graph",
 "sources":[{"id":"S1","path":"paper.md"}],
 "nodes":[{"id":"N1","label":"thermal annealing","type":"method","aliases":["annealing"],
   "kind":"reported","status":"reported",
   "evidence":[{"source":"S1","paragraph_id":"P2","quote":"verbatim..."}]}],
 "edges":[{"id":"E1","from":"N1","to":"N2","type":"improves","conditions":"100 C, 10 min",
   "kind":"reported","status":"reported",
   "evidence":[{"source":"S1","paragraph_id":"P4","quote":"verbatim..."}]}],
 "queries":[{"id":"Q1","question":"...","answer":"...","node_ids":["N1","N2"]}],
 "unanswered_parts":[],"uncertainty":[],"provenance":{}}
```
Node types: researcher material method task metric conclusion concept dataset
instrument organization other. Edge types (controlled): uses compares outperforms
supports contradicts causes increases decreases inhibits activates binds part_of
measures associated_with applied_to produces contains upstream_of reports.
Status vocabulary per node/edge: reported | not_reported | source_conflict |
extraction_failed | insufficient_evidence; gaps carry no label/type value +
human_confirm:true.

## Domain rules
See rules/rules_knowledge_graph.md (entity criteria, relation evidence, alias
normalization, queries, gap handling).

## Scripts & dependencies
assemble.py (CLI), arena_read_engine.py (validate_ir + graph computation + build),
svgkit.py (layered editable SVG, stdlib), readkit.py / figkit.py (reused reading
core). Python 3.10+ stdlib only.

## Outputs (/app/output)
graph.json (nodes/edges/queries with evidence), graph.svg (editable Inkscape-style
layers, data-source locator on every element), graph_check.json (n_components,
orphan nodes, degrees, query evidence), knowledge_graph_result.md, reading_ir.json,
provenance.json (record_map + source sha256), validation.json, result.json (all
output_contract fields + case_id, honest status).

## Error handling (docs/ERROR_HANDLING.md)
Entity not in material → do not create; relation without evidence → insufficient_evidence
+ human_confirm; conflicting relations across papers → source_conflict + both
locators; alias ambiguity → keep separate nodes + uncertainty until merge basis
found; query with no answer → answer="not_reported" + human_confirm.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/knowledge_graph/`: input/ + ir.json (4 nodes, 3 edges, 3 queries). Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/knowledge_graph/ir.json --input examples/knowledge_graph/input --out /tmp/demo_kg`

## Self-check
- [ ] read ACTUAL /input workorder + material; sources registered with real paths
- [ ] every entity appears in material; every edge has type+direction+evidence quote
- [ ] relation types within controlled vocabulary; endpoints exist
- [ ] aliases normalized with merge basis; no accidental duplicate nodes
- [ ] >=3 queries answered with node_ids + evidence; unanswerable flagged
- [ ] graph.svg editable with data-source locators; result.json honest; exit 0

## Runtime contract
Skill at /skills/weekly-skill; input /input/case.json + task.md + material; work
/app/work; output /app/output/result.json preserving every output_contract field +
case_id. No pre-baked graphs; honest success/partial/failed with limits. Resources
≤50 UTF-8 text files, ≤500KB each, ≤2MB total, no binaries/symlinks/__pycache__
(SVG is text; PYTHONDONTWRITEBYTECODE=1).

## GitHub bonus (+5)
GITHUB_URL.txt at package root: line 1 public GitHub tree URL (git_sync), line 2
SKILL.md. Opens without login.