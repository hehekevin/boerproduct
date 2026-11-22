---
name: search-citation-tracking
description: Traverse the organizer-retained reference graph from seed papers: backward to methods/data origins, forward to improvements/critiques, multi-hop BFS with per-hop direction + source + context, identity merge of preprint/conference/journal versions, and labelled stubs for nodes without metadata. Use when the task is 引文追踪 / citation chaining, reference/citing-paper expansion or building an explainable citation network around seeds.
---

# Citation tracking & related-work discovery (引文追踪与关联文献发现)

A source-bound Skill for the Bohrium weekly research-efficiency contest (search
track, `challenge-60a8202d`). The agent reads the ACTUAL organizer-provided local
materials under /input (scientific documents, real Crossref/EuropePMC/publisher
responses, retained reference graph, organizer-local import states, facsimiles —
whatever the case ships), fills a structured IR, and a deterministic stdlib
engine validates it, performs the real computation (citation BFS + per-hop provenance paths + identity merge), and emits
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
source locator.

## When to use
The workorder asks to start from seed paper(s) and find foundational references, follow-up work, or parallel method-lineage papers via citation relations, with a replayable path for every expanded paper. NOT for plain keyword search, full-text reading or unauthorized scraping.

## Focus (rubric)
Actual effect 40 (completion/correctness/completeness/verifiability: real
records, accurate metadata, Precision@k / nDCG@k / Recall@k where applicable,
replayable evidence), usage gain 25 vs the no-Skill baseline, innovation gain 15
(direction-labelled multi-hop BFS with per-edge source paths, stub honesty, DOI+fuzzy identity merge with conflict retention), reliable experience 10 (stable triggering, empty-result /
conflict / missing-metadata / permission handling), ecosystem contribution 10
(docs + reusable engine/rules/example). GitHub public link: +5 bonus.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete research question, constraints, evidence scope.
- The actual material files. Read and register the real files; trust file
  content over filename/database labels. Finite local snapshot only.

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_search.py --input /input --out /app/output --work /app/work`
Auto-extracts the IR from the ACTUAL /input materials (registers sources; parses CSV /
Crossref-EuropePMC JSON exports / reference graphs / import states / paper text & PDF
facsimiles), runs the engine to compute real metrics, and writes a complete honest
result.json preserving every output_contract key + case_id. Judgment fields it cannot
verify are abstained (insufficient_evidence) and flagged human_confirm — never fabricated.
THEN, within remaining budget, refine judgment-heavy fields in /app/work/search_ir.json
(miss attributions, screening decisions, grades, term alignments) and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/search_ir.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] {id, path, type, name}.
2. Read the material; fill the IR per `rules/rules_citation_tracking.md` and the schema below.
   Keep original queries, raw snippets, field-level sources; judge relevance /
   decisions / grades yourself and attach evidence locators.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir search_ir.json --input /input --out /app/output`
   -> validate_ir -> build -> citation_expansion.json + report.md + records.csv +
   provenance.json + search_ir.json -> result.json.
4. Honest status: success only when validation is clean and no unresolved
   human_confirm gaps; partial on validation errors, build errors or open gaps;
   failed on unreadable IR / no artifacts. Save partial early; never fabricate.

## IR schema (agent fills from ACTUAL material; enforced by validate_ir)
```
ir_version: "1.0"            # required literal
case_id: <auto from /input/case.json>
kind: "citation_tracking"
sources: [{id, path, type?, name?}]   # every used input file; unique ids;
                                        # EVERY source_id anywhere must be registered
queries: [{id, query_string, ...}]    # ORIGINAL query strings preserved
records: [{id, title|doi, source_id, query_id?, snippet?, status?,
            authors?, year?, journal?, doi?, field_sources?, ...}]
seeds: [record_id, ...]                 # REQUIRED, must exist in records
edges: [{from, to, direction: forward|backward, source_id, context?}]  # REQUIRED
max_depth: int 1..5 (default 2)
records[]: metadata for every node you could verify (title/doi + source_id);
  nodes without metadata are kept as labelled stubs (warning, not error)
ranking: {weights?: {question_match, method_match, population_match,
                     evidence_quality, recency, facet_coverage}, k?}
provenance: {pipeline, changes?}
uncertainty: [{item, reason, impact?, handling}]   # human_confirm => partial
```
record.status vocabulary: reported | not_reported | source_conflict |
extraction_failed | inferred | insufficient_evidence.
Evidence locator = {source_id, paragraph_id?, page?, quote?, table?, field?}.
Features are 0..1 floats; score = weighted sum (weights renormalized over the
features present); ties broken by tier -> score desc -> year desc -> id asc.
Records without features are NOT scored — they go to the human review queue.

## Domain rules — citation_tracking (full text: rules/rules_citation_tracking.md)
1. Seeds come from task.md / the provided corpus; every seed must be a registered record. Traverse ONLY the organizer-retained reference graph — no live citation API calls or claims of complete forward coverage (new preprints often have no citing records yet).
2. Every edge needs from, to, direction and source_id. backward = 'to' is a reference OF 'from' (methods/data origins); forward = 'to' CITES 'from' (improvements/critiques). If a source gives only a cited list without direction, determine direction from the actual document and record the basis in context — never guess silently.
3. Keep citation context clues (which section/entry of the actual document lists the edge) so a reviewer can re-verify each hop. The engine records the full path seed->...->node with per-hop direction@source.
4. Identity merge: same work as preprint/conference/journal/supplement versions merges via DOI exact + fuzzy title/year (engine). Keep merge evidence and field conflicts; watch for same-title-different-work and different-title-same-work.
5. Nodes reached without metadata stay as not_reported_stub — list them, do not fabricate titles/DOIs. Seeds with no outgoing edges in the retained graph are reported explicitly.
6. Choose max_depth (1..5) and pruning deliberately; high citation count != high relevance. If you add relevance judgments, attach features/rationale as in screen_rank; otherwise the expansion is structural, not a relevance claim.
7. Gaps (missing forward records, stubs, unavailable sources) go to uncertainty[] human_confirm => honest partial.

## Scripts & dependencies
assemble.py (CLI), search_engine.py (validate_ir + build: citation BFS + per-hop provenance paths + identity merge),
w4kit.py (case load / source check / dedup / result.json). Python 3.10+
standard library only — no third-party packages, no network. See requirements.txt.

## Outputs (/app/output)
citation_expansion.json — seeds, max_depth, edge counts (forward/backward), the retained edges, expanded nodes with depth + seed + full per-hop path + directions, per_depth_counts, stub_nodes_no_metadata, seeds_without_outgoing_edges, dedup clusters, scope_note (finite snapshot).
Plus report.md (editable, locators inline), records.csv (editable flat list),
provenance.json (record/edge/view -> source map + sources_used/unused),
search_ir.json (replay), validation.json, result.json (preserves every
output_contract key + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Edge without direction/source -> validation error; node without metadata -> labelled stub (never fabricated); seed without edges -> explicit gap; duplicate versions -> merged with evidence; no live forward-coverage claim for recent preprints.
Never fabricate; never silent-skip; never claim live/global coverage.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/citation_tracking/`: tiny fake input/ + ir.json accepted by the engine. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/citation_tracking/ir.json --input examples/citation_tracking/input --out /tmp/demo`
The demo includes a depth-2 stub node (R5) to show honest not_reported handling. Real cases are supplied only at evaluation.

## Self-check
- [ ] seeds registered; every edge has direction + source_id + context
- [ ] BFS paths replayable hop-by-hop; depth within 1..5
- [ ] stubs labelled not_reported; versions merged with evidence
- [ ] no live-coverage claim; gaps in uncertainty with human_confirm
- [ ] result.json honest (status/sources/uncertainty/change_log); output_contract preserved
- [ ] no live-coverage / latest-publication / fabricated-data claims anywhere

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL of this
work, line 2 = relative entry file (SKILL.md). Published under week4/grok in
github.com/hehekevin/boerproduct; opens without login.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared
answers or formal test outputs. Evaluator installs the Skill under
/skills/weekly-skill and runs the official DeepSeek Harness on each fixed
original case (/input/case.json + task.md -> /app/output/result.json preserving
output_contract + case_id). Work under /app/work; editable artifacts under
/app/output; honest partial identifies its limits. Budget: 64 model requests,
900s, 16384 tokens/response. Resources: <=50 UTF-8 text files, <=500KB each,
<=2MB total, no symlinks/binaries.
