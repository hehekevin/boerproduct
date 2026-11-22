---
name: arena-nanopublication
description: Source-bound nanopublication extraction — read the ACTUAL organizer paper/workorder files under /input, split key conclusions into atomic verifiable assertions (subject-predicate-object with conditions), bind each to minimal sufficient evidence quotes with paragraph locators, record real provenance metadata (authors/year/doi/version) and publication info, and export machine-readable nanopubs.json + TriG with reported/not_reported/source_conflict/extraction_failed/insufficient_evidence status; deterministic stdlib engine validates triples, controlled predicates, evidence and dedup. Use for the "阅读14Nanopublication" workorder (kind=nanopublication).
---

# Nanopublication skill (nanopublication)

Source-bound reading skill. The Agent reads the ACTUAL material and fills the
nanopub IR (assertion + provenance + publication info per nanopub); `assemble.py`
deterministically validates granularity/evidence/locators/status, checks controlled
predicates and duplicate triples, and builds machine-readable nanopubs.json +
nanopubs.trig + honest result.json. Output triad: 解析结果 / 证据与边界 / 运行状态.

## Focus (rubric)
- 拆得细: one independently truth-evaluable assertion per nanopub (subject,
  predicate, object + conditions/scope); never stuff a whole paragraph into one field.
- 对得上: minimal sufficient evidence quote that actually supports the assertion;
  exact paragraph/page locator; direct evidence vs inference distinguished (kind).
- 追得回: complete chain assertion → evidence → paper (authors, year, doi, version);
  missing metadata marked not_reported, never invented.
- 读得懂: exports follow the documented schema; nanopubs.trig is parseable TriG
  (np: hasAssertion/hasProvenance/hasPublicationInfo), nanopubs.json needs no cleanup.

## Scope / trigger
Use when the case asks for Nanopublication extraction / assertion decomposition
(kind=nanopublication). Only given local material; no online retrieval.

## Inputs (runtime) — READ THESE ACTUAL FILES FIRST
1. `/input/case.json` — copy case_id, read output_contract.
2. `/input/task.md` — target paragraphs/conclusions, requested nanopub count/schema.
3. Workorder files when present (target-fields.json / workorder.json): requested
   assertion scope or fields.
4. ALL material files (paper text + metadata). Register every file actually used in
   sources[] (id + real path).

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_arena_read.py --input /input --out /app/output --work /app/work`
Auto-registers sources from the ACTUAL /input materials, auto-fills a complete source-bound IR
into work/ir.json, runs the SAME validate+build path as the package assembler, and ALWAYS writes an
honest result.json (try/except fallback preserves every output_contract key + case_id) — even on
empty input or failure. Judgment it cannot verify is flagged human_confirm; never fabricated.
THEN, within remaining budget, refine /app/work/ir.json and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory /input; open case.json + task.md + workorder + material.
2. Fill IR per rules/rules_nanopublication.md: sources[], nanopubs[{id,
   assertion{subject, predicate, object, conditions?}, kind reported|inferred,
   status, evidence[{source, paragraph_id, quote}], provenance{source_id, authors?,
   year?, doi?, version?}, human_confirm?}], unanswered_parts, uncertainty, provenance.
3. Run exactly:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/ir.json --input /input --out /app/output`
   → validation.json → nanopubs.json + nanopubs.trig + nanopublication_result.md →
   provenance.json (record_map + source sha256) → result.json.
4. Exit 0 = validation ok; exit 2 = errors → fix IR, re-run. Save honest partial
   early; budget 64 requests / 900 s.

## IR schema (minimal)
```json
{"ir_version":"1.0","case_id":"...","kind":"nanopublication",
 "sources":[{"id":"S1","path":"paper.md"}],
 "nanopubs":[{"id":"NP1",
   "assertion":{"subject":"thermal annealing","predicate":"improves",
     "object":"perovskite film stability","conditions":"100 C, 10 min, nitrogen"},
   "kind":"reported","status":"reported",
   "evidence":[{"source":"S1","paragraph_id":"P5","quote":"verbatim minimal quote"}],
   "provenance":{"source_id":"S1","authors":["A. Example"],"year":"2024","doi":null}}],
 "unanswered_parts":[],"uncertainty":[],"provenance":{}}
```
Controlled predicates: increases decreases causes inhibits activates binds measures
uses compares outperforms supports contradicts part_of associated_with reports
contains produces improves (others allowed but flagged). Status vocabulary per
nanopub: reported | not_reported | source_conflict | extraction_failed |
insufficient_evidence. Gap statuses carry no assertion value + human_confirm:true.

## Domain rules
See rules/rules_nanopublication.md (atomicity criteria, minimal sufficient evidence,
provenance chain, dedup, gap handling).

## Scripts & dependencies
assemble.py (CLI), arena_read_engine.py (validate_ir + triple/dedup checks + TriG
export + build), readkit.py / figkit.py (reused reading core). Python 3.10+ stdlib only.

## Outputs (/app/output)
nanopubs.json (assertion/evidence/provenance/publication_info per nanopub),
nanopubs.trig (machine-readable TriG), nanopublication_result.md (editable review
table), reading_ir.json, provenance.json, validation.json, result.json (all
output_contract fields + case_id, honest status).

## Error handling (docs/ERROR_HANDLING.md)
No supporting fragment → insufficient_evidence + human_confirm (never fabricate an
assertion); assertion contradicts evidence → source_conflict + both locators;
unreadable source → extraction_failed + reason; missing authors/year/doi →
provenance fields null + not_reported note, not invented values.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/nanopublication/`: input/ + ir.json (3 nanopubs). Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/nanopublication/ir.json --input examples/nanopublication/input --out /tmp/demo_np`

## Self-check
- [ ] read ACTUAL /input workorder + material; sources registered with real paths
- [ ] each assertion atomic (single subject-predicate-object + conditions preserved)
- [ ] minimal sufficient evidence quote + exact locator per nanopub; inferred tagged
- [ ] provenance chain real (authors/year/doi from material; gaps not_reported)
- [ ] predicates controlled; no duplicate triples; TriG/JSON parseable
- [ ] result.json honest; exit 0 on clean IR

## Runtime contract
Skill at /skills/weekly-skill; input /input/case.json + task.md + material; work
/app/work; output /app/output/result.json preserving every output_contract field +
case_id. No pre-baked nanopubs; honest success/partial/failed with limits. Resources
≤50 UTF-8 text files, ≤500KB each, ≤2MB total, no binaries/symlinks/__pycache__
(PYTHONDONTWRITEBYTECODE=1).

## GitHub bonus (+5)
GITHUB_URL.txt at package root: line 1 public GitHub tree URL (git_sync), line 2
SKILL.md. Opens without login.