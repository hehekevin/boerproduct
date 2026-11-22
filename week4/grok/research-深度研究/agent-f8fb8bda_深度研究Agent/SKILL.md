---
name: research-deep-research
description: Run a source-bound deep research workflow over organizer-provided local materials - decompose the question into an acyclic subquestion tree, plan executable retrieval, bind every conclusion to an exact source paragraph, surface conflicting evidence and research gaps, and deliver a bounded synthesis with a replayable tool log. Use when the task is multi-step deep research / evidence synthesis on a provided corpus (kind deep_research), NOT a pre-baked answer.
---

# Deep research agent (深度研究 Agent)

A source-bound Skill for the Bohrium weekly research-efficiency contest (research track).
The agent reads the ACTUAL organizer-provided material under /input, fills a structured
Research IR, and a deterministic stdlib engine validates it, recomputes screening /
synthesis, re-verifies every quoted excerpt against the real files, and emits editable
artifacts (md/docx/csv/svg) + bidirectional provenance + an honest result.json. No
pre-baked answers; every claim traces to a real source_id + paragraph_id + exact quote.

## When to use
Use for kind `deep_research`: a concrete research question over a provided local corpus
that requires question decomposition, retrieval planning, multi-step tool use, evidence
synthesis, conflict presentation and research-gap identification. The six rubric points
are: 问题拆解 (decomposition), 检索覆盖 (search coverage), 证据回链 (evidence back-links),
冲突证据 (conflicting evidence), 综合结论 (synthesis), 研究空白 (gaps). Everything must be
independently re-checkable and re-runnable (decomposition tree, queries, tool log,
evidence table, conclusions).

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete task rules for this case.
- The actual material files (papers/docs/tables). Read and register the real files;
  trust file content over filename/domain labels. PDFs arrive without a pre-extracted
  answer layer — parse them yourself if a tool exists, else mark quotes unverifiable.

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_research.py --input /input --out /app/output --work /app/work`
Auto-extracts the Research IR from the ACTUAL /input materials (registers sources with
real titles/years/DOIs; parses md/txt/PDF/docx text and CSV/JSON tables; screens records;
builds acyclic subquestions, themes, claims with EXACT re-verifiable quotes, conflicts,
gaps, tool_log and a bounded proposal, plus kind-specific trend/topic blocks), runs the
engine (validate_ir + build) and writes a complete honest result.json preserving every
output_contract key + case_id. Judgment fields it cannot verify are abstained and flagged
human_confirm — never fabricated. On ANY failure it still writes an honest partial/failed
result.json. THEN, within remaining budget, refine judgment-heavy fields in
/app/work/research_ir.json (screening decisions, claim strength, themes, novelty coverage)
and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/research_ir.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Run `PYTHONDONTWRITEBYTECODE=1 python auto_research.py --input /input --out /app/output --work /app/work`
   to auto-extract materials and produce a complete baseline result.json. Then, within
   budget, refine judgment-heavy fields in /app/work/research_ir.json and re-run
   assemble.py to improve. Save partial early; never fabricate.
2. Inventory inputs (w4kit.list_materials); register every used file in sources[].
   Read the material; fill/refine research_ir.json per `rules/rules_deep_research.md` + schema below.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir research_ir.json --input /input --out /app/output`
   -> validate_ir -> compute_screening/synthesis + check_quotes -> build artifacts +
   provenance.json -> summarize -> result.json.
4. Honest status: success only when validation is clean and build complete; partial when
   errors, missing files or unverifiable quotes exist; failed on IR/build error. Save
   partial early; never write an incomplete result as complete.

## Research IR schema (agent fills from ACTUAL material; validated by engine.validate_ir)
```
ir_version: "1.0"            # required literal
case_id: <auto from /input/case.json>
kind: "deep_research"
sources: [{id, title, file, year?, doi?, type?}]   # register every used file; file relative to /input
protocol: {
  inclusion: [{id, text}], exclusion: [{id, text}],
  search_queries: [{id, query, intent, executed?, date?, database?}]
}
records: [{id, source_id, title, year?, doi?, stage, decision,
           criteria_applied?, reason?, reviewer?, duplicate_of?}]
  # stage: title_abstract|full_text ; decision: include|exclude|pending
  # exclude needs reason; duplicate_of target must exist; engine recomputes PRISMA + dedup
research_question: {main, subquestions: [{id, question, depends_on?: [sq_id]}]}  # acyclic
themes: [{id, name, basis}]                       # induced FROM sources
claims: [{id, text, type?, strength, theme_id?, subquestion_id?, uncertainty?,
          evidence: [{source_id, paragraph_id, quote, stance?}]}]
  # type: fact|inference|gap|method|comparison
  # strength: established|supported|suggestive|contested|uncertain
  # stance: supports|contradicts|partial|context ; quote = EXACT substring of the paragraph
  # every claim needs >=1 evidence; established cannot carry contradicts
conflicts: [{id, topic, positions: [{source_id, paragraph_id, quote, stance?}], handling}]
gaps: [{id, type?, text, evidence? | search_scope_checked?, human_confirm?}]
  # type: evidence_gap|conflict_unresolved|method_failure|repeated_open_question|coverage_gap
tool_log: [{step, tool, params, result?}]         # replay path (deep_research)
proposal: {text, bounded: true}                   # prospective, source-scoped
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes: []}
```
Evidence locator = {source_id, paragraph_id, quote, page?, table?, field?}. Materials may
mark paragraphs as `[P3] ...`; the engine restricts quote search to that paragraph.

## Domain rules — deep_research (detail: rules/rules_deep_research.md)
1. Decompose the main question into subquestions with an ACYCLIC depends_on graph; map
   each claim to a subquestion_id. The engine rejects undefined dependencies and cycles.
2. Plan retrieval: protocol.search_queries with query text + intent; mark executed+date
   only for searches actually run over the provided corpus. Never invent remote hits.
3. Screen records in two stages with criteria + reasons; the engine recomputes PRISMA
   counts and cross-checks duplicates by DOI/fuzzy title (declare duplicate_of).
4. Claim-evidence rule: every conclusion binds >=1 exact quote located to source_id +
   paragraph_id. The engine re-verifies each quote against the real file; `not_found`
   is an error. Strength must match the evidence (contested if any contradicts).
5. Present conflicting evidence as conflicts[] with >=2 located positions + handling;
   do not collapse to one verdict. Identify gaps with evidence OR a documented search
   scope; flag human_confirm. "Not found" is NOT "nobody studied it".
6. Record a tool_log so the whole path is replayable. Keep the proposal prospective and
   bounded; declare uncertainty (conflicts/bias/scope). No field-wide novelty/completeness
   and no completed-experiment wording (the engine scans and rejects over-boundary text).

## Scripts & dependencies
auto_research.py (autopilot CLI: auto-extract IR from /input + run engine), assemble.py
(CLI), research_engine.py (validate_ir + compute_screening/synthesis/trend/
novelty + check_quotes + build md/docx/csv/svg + provenance + summarize), w4kit.py (case
load / source check / dedup / result.json). Python 3.10+ standard library only — no
third-party packages required (numpy optional, never needed). See requirements.txt.

## Outputs (/app/output)
research_report.md, research_report.docx, synthesis_matrix.csv, screening_log.csv,
prisma_flow.svg, provenance.json, validation.json, result.json (preserves every
output_contract key + case_id + status + sources + uncertainty + change_log + prisma +
quote_check_summary + human_confirm + boundary).

## Error handling (docs/ERROR_HANDLING.md)
Missing/unreadable file -> unverifiable quotes + uncertainty; quote not in file ->
validation error (fix, never fabricate); established+contradicts -> error; exclusion
without reason / PRISMA mismatch -> error; conflict -> both positions surfaced; gap ->
evidence or search scope + human_confirm; over-boundary wording -> error; IR/build error
-> honest failed/partial with build_error.txt. Never fabricate; never silent-skip.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/deep_research/`: input/ (8 fictional docs) + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/deep_research/ir.json --input examples/deep_research/input --out /tmp/demo`
The example includes a subquestion tree, a conflict (CF1), gaps (G1/G2) and a duplicate
record (R7) to demonstrate honest screening and bounded synthesis. Real cases are
supplied only at evaluation.

## Self-check
- [ ] every used input file registered in sources[] with a real file pointer
- [ ] subquestion tree acyclic; claims mapped to subquestions
- [ ] search queries executable + intent; executed searches dated; no invented hits
- [ ] every claim/conflict/gap binds an EXACT quote re-verified against the real file
- [ ] strength matches evidence; conflicts presented both sides; gaps human_confirm
- [ ] PRISMA counts recomputed and balanced; duplicates declared
- [ ] tool_log replayable; proposal bounded; no over-boundary wording
- [ ] result.json honest (status/sources/uncertainty/change_log); output_contract preserved

## GitHub bonus (+5)
GITHUB_URL.txt at this package root: line 1 = public GitHub tree URL of this work,
line 2 = relative entry file (SKILL.md). Published under week4/grok in
github.com/hehekevin/boerproduct; opens without login.

## Runtime contract
Skill authoring task. Valid name/description YAML frontmatter. No prepared answers or
formal test outputs. The evaluator installs the Skill under /skills/weekly-skill and runs
the official DeepSeek Harness on each fixed original case (/input/case.json + task.md ->
/app/output/result.json preserving every output_contract field + case_id). Work under
/app/work; editable artifacts + real rendered previews belong under /app/output. Honest
status/sources/uncertainty/change_log; partial results identify their limits; never
fabricate missing software state or scientific data. Resources: <=50 UTF-8 text files,
<=500KB each, <=2MB total, no symlinks/binaries/__pycache__. Run with PYTHONDONTWRITEBYTECODE=1.