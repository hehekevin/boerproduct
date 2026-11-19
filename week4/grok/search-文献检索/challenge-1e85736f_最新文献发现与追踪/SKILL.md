---
name: search-incremental-tracking
description: Diff organizer-local import snapshots window-by-window: detect genuinely new records vs version updates (preprint->published->revision) vs retractions, suppress duplicates via a stable normalized key, check window continuity, and keep a replayable watermark + full version record. Use when the task is 最新文献发现与追踪 / topic subscription, periodic incremental search or update alerts over provided import states. Never claims live or latest-publication coverage.
---

# New-literature discovery & incremental tracking (最新文献发现与追踪)

A source-bound Skill for the Bohrium weekly research-efficiency contest (search
track, `challenge-1e85736f`). The agent reads the ACTUAL organizer-provided local
materials under /input (scientific documents, real Crossref/EuropePMC/publisher
responses, retained reference graph, organizer-local import states, facsimiles —
whatever the case ships), fills a structured IR, and a deterministic stdlib
engine validates it, performs the real computation (snapshot diff + version chains + window audit + watermark), and emits
editable artifacts + bidirectional provenance + an honest result.json.
No pre-baked answers; no live remote search; every record traces to a real
source locator.

## When to use
The workorder provides successive organizer-local import states/snapshots for a topic and asks what is NEW in each window relative to the previous snapshot, with duplicates/version-updates/retractions distinguished and every increment replayable. NOT for unauthorized scheduled scraping or treating alerts as scientific conclusions.

## Focus (rubric)
Actual effect 40 (completion/correctness/completeness/verifiability: real
records, accurate metadata, Precision@k / nDCG@k / Recall@k where applicable,
replayable evidence), usage gain 25 vs the no-Skill baseline, innovation gain 15
(snapshot diff with stable dedup keys, version-chain grouping, retraction separation, window-drift detection, idempotent replay watermark), reliable experience 10 (stable triggering, empty-result /
conflict / missing-metadata / permission handling), ecosystem contribution 10
(docs + reusable engine/rules/example). GitHub public link: +5 bonus.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete research question, constraints, evidence scope.
- The actual material files. Read and register the real files; trust file
  content over filename/database labels. Finite local snapshot only.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register sources[] {id, path, type, name}.
2. Read the material; fill the IR per `rules/rules_incremental_tracking.md` and the schema below.
   Keep original queries, raw snippets, field-level sources; judge relevance /
   decisions / grades yourself and attach evidence locators.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir search_ir.json --input /input --out /app/output`
   -> validate_ir -> build -> incremental_state.json + report.md + records.csv +
   provenance.json + search_ir.json -> result.json.
4. Honest status: success only when validation is clean and no unresolved
   human_confirm gaps; partial on validation errors, build errors or open gaps;
   failed on unreadable IR / no artifacts. Save partial early; never fabricate.

## IR schema (agent fills from ACTUAL material; enforced by validate_ir)
```
ir_version: "1.0"            # required literal
case_id: <auto from /input/case.json>
kind: "incremental_tracking"
sources: [{id, path, type?, name?}]   # every used input file; unique ids;
                                        # EVERY source_id anywhere must be registered
queries: [{id, query_string, ...}]    # ORIGINAL query strings preserved
records: [{id, title|doi, source_id, query_id?, snippet?, status?,
            authors?, year?, journal?, doi?, field_sources?, ...}]
subscription: {topic, window_timezone?, dedup_key?, source_id?}
snapshots: [{id, window: {start, end}, imported_at?, record_ids: [...], source_id?}]
records[] extras: version_of?: <record id>, retracted?: bool
# live_claim is FORBIDDEN (validation error): organizer-local states only
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

## Domain rules — incremental_tracking (full text: rules/rules_incremental_tracking.md)
1. Use ONLY the organizer-local import states provided under /input. Register each snapshot with id, window.start/end (fixed timezone) and imported_at; record_ids must reference registered records. Never set live_claim or describe the output as 'the latest publications' — indexing lag means the snapshot is not live truth.
2. The dedup key is normalized DOI, else normalized title+year (engine). A record whose key was seen in an earlier snapshot is NOT new: if it is a different record id it is a version update (preprint->published etc.); if fields changed it is an update with changed_fields. Link versions explicitly with version_of when the material supports it.
3. Retracted records (retracted: true, per the actual source notice) are separated from new discoveries — a retraction is a correction alert, not a new paper. Never push a retracted record as a finding.
4. Windows must be contiguous (start == previous end). The engine flags gaps/overlaps as window_issues with human_confirm — decide backfill vs overlap dedup explicitly; do not let windows drift.
5. Keep the full version record: subscription config, windows, imported_at, counts, seen keys. Re-running the same snapshots yields identical increments (idempotent) — no double alerts on retry.
6. Alert design: merge/suppress duplicates, distinguish new vs version-update vs retraction, and state the watermark (last_window_end). Failures (rate limit/timeout/missing fields) are recorded as gaps with retry notes, not silent skips.
7. Old papers newly indexed are not 'new research': the increment is relative to the previous snapshot, and the report says so.

## Scripts & dependencies
assemble.py (CLI), search_engine.py (validate_ir + build: snapshot diff + version chains + window audit + watermark),
w4kit.py (case load / source check / dedup / result.json). Python 3.10+
standard library only — no third-party packages, no network. See requirements.txt.

## Outputs (/app/output)
incremental_state.json — subscription, snapshots, per-snapshot increments (new / version_updates / retracted with basis), window_issues, dedup_key_rule, seen_keys, version_groups, watermark (last_window_end, n_seen_keys), idempotent flag, scope_note (organizer-local only).
Plus report.md (editable, locators inline), records.csv (editable flat list),
provenance.json (record/edge/view -> source map + sources_used/unused),
search_ir.json (replay), validation.json, result.json (preserves every
output_contract key + case_id + status + sources + uncertainty + change_log).

## Error handling (docs/ERROR_HANDLING.md)
Window gap/overlap -> window_issues human_confirm; same-key later import -> version update, not new; retraction -> separated correction; live/latest claim -> validation error (forbidden); retry -> idempotent, no second push.
Never fabricate; never silent-skip; never claim live/global coverage.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/incremental_tracking/`: tiny fake input/ + ir.json accepted by the engine. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/incremental_tracking/ir.json --input examples/incremental_tracking/input --out /tmp/demo`
The demo shows a preprint->published version update (same DOI, later window) and a retracted record separated from new findings. Real cases are supplied only at evaluation.

## Self-check
- [ ] snapshots registered with windows + imported_at; record_ids all known
- [ ] new vs version-update vs retracted distinguished with basis; keys stable
- [ ] windows contiguous or issues flagged; watermark replayable; idempotent
- [ ] NO live_claim / latest-publication wording anywhere
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
