---
name: research-systematic-review
description: Run a source-bound systematic review over organizer-provided local materials - predefine inclusion/exclusion criteria and executable search queries (with date + database), screen records in two stages with reasons, appraise quality of every included study, recompute PRISMA counts, and synthesize conclusions bound to exact evidence locators. Use when the task is a systematic review / PRISMA-style evidence synthesis on a provided corpus (kind systematic_review), NOT a pre-baked answer.
---

# Systematic literature review (系统性文献综述)

A source-bound Skill for the Bohrium weekly research-efficiency contest (research track).
The agent reads the ACTUAL organizer-provided material under /input, fills a structured
Research IR, and a deterministic stdlib engine validates it, recomputes the PRISMA flow +
dedup cross-check + synthesis, re-verifies every quoted excerpt against the real files,
and emits editable artifacts (md/docx/csv/svg) + bidirectional provenance + an honest
result.json. No pre-baked answers; screening decisions follow pre-written criteria and
every conclusion binds a real source_id + paragraph_id + exact quote.

## When to use
Use for kind `systematic_review`: the full chain question decomposition -> search-query
construction -> inclusion/exclusion screening -> quality appraisal -> evidence-bound
review conclusions. Rubric checks: queries truly executable and hitting core literature;
screening decisions conform to pre-defined criteria; cited papers + metadata real;
conclusions supported by included evidence without overstepping; coverage of the six
points (decomposition, search coverage, evidence back-links, conflicting evidence,
synthesis, gaps); query text + search date + database + screening log + quality-appraisal
basis + citation locators independently re-runnable and re-checkable.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete task rules for this case.
- The actual material files (papers/docs/records/metadata). Read and register the real
  files; trust content over filename/domain labels. PDFs arrive without a pre-extracted
  answer layer — parse yourself if a tool exists, else mark quotes unverifiable.

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_research.py --input /input --out /app/output --work /app/work`
Auto-extracts the Research IR from the ACTUAL /input materials (registers sources; reads
PDF/text into paragraphs; builds records/screening, an acyclic subquestion tree, themes,
claims bound to EXACT re-verified quotes, conflicts, gaps, tool_log and a bounded proposal),
runs the engine to recompute screening/synthesis and re-verify every quote, and writes a
complete honest result.json preserving every output_contract key + case_id. Quotes it cannot
verify against binary/missing files are declared unverifiable + human_confirm — never fabricated.
THEN, within remaining budget, refine claims/conflicts/gaps in /app/work/research_ir.json and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir /app/work/research_ir.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/WORKFLOW.md)
1. Inventory inputs (w4kit.list_materials); register every used file in sources[].
2. Write the protocol FIRST (criteria + executable queries), then read + screen + appraise;
   fill research_ir.json per `rules/rules_systematic_review.md` + schema below.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir research_ir.json --input /input --out /app/output`
   -> validate_ir -> compute_screening (PRISMA + dedup) / synthesis + check_quotes ->
   build artifacts + provenance.json -> summarize -> result.json.
4. Honest status: success only when validation clean + build complete; partial when
   errors/missing files/unverifiable quotes/missing appraisals; failed on IR/build error.

## Research IR schema (agent fills from ACTUAL material; validated by engine.validate_ir)
```
ir_version: "1.0"            # required literal
case_id: <auto from /input/case.json>
kind: "systematic_review"
sources: [{id, title, file, year?, doi?, type?}]
protocol: {
  inclusion: [{id, text}], exclusion: [{id, text}],          # both defined BEFORE screening
  search_queries: [{id, query, intent, executed?, date?, database?}]  # REQUIRED
}
records: [{id, source_id, title, year?, doi?, stage, decision,
           criteria_applied?, reason?, reviewer?, duplicate_of?}]
  # stage: title_abstract|full_text ; decision: include|exclude|pending ; exclude needs reason
  # two-stage flow expected; engine recomputes PRISMA + cross-checks dedup (DOI/fuzzy title)
research_question: {main, subquestions?: [{id, question, depends_on?}]}
themes: [{id, name, basis}]
claims: [{id, text, type?, strength, theme_id?, subquestion_id?, uncertainty?,
          evidence: [{source_id, paragraph_id, quote, stance?}]}]
  # strength: established|supported|suggestive|contested|uncertain ; stance: supports|contradicts|partial|context
  # quote = EXACT substring; every claim needs >=1 evidence; established cannot carry contradicts
quality: [{record_id, overall, dimensions: [{name, rating?, evidence?}]}]
  # REQUIRED appraisal for each INCLUDED record; overall: high|moderate|low|unclear
conflicts: [{id, topic, positions: [{source_id, paragraph_id, quote, stance?}], handling}]
gaps: [{id, type?, text, evidence? | search_scope_checked?, human_confirm?}]
tool_log?: [{step, tool, params, result?}]
proposal?: {text, bounded: true}
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes: []}
```
Evidence locator = {source_id, paragraph_id, quote, page?, table?, field?}. Materials may
mark paragraphs as `[P3] ...`; the engine restricts quote search to that paragraph.

## Domain rules — systematic_review (detail: rules/rules_systematic_review.md)
1. Protocol first: write inclusion/exclusion criteria (I*/E*) and executable
   search_queries (query text + intent + executed + date + database) BEFORE screening.
   Queries are REQUIRED; executed queries need a real date. Never invent remote hits.
2. Two-stage screening: records[] title_abstract -> full_text, each decision conforming
   to a pre-written criterion; every exclude needs a reason + criterion id. Duplicates
   set duplicate_of. The engine recomputes PRISMA counts (identified -> duplicates removed
   -> screened -> excluded -> full-text assessed -> included) and rejects mismatches; it
   also cross-checks undeclared duplicates by DOI/fuzzy title-year.
3. Quality appraisal: every INCLUDED record needs a quality[] entry {record_id, overall
   (high/moderate/low/unclear), dimensions[] with evidence locators}. Missing appraisals
   are flagged. Appraisal basis must be re-checkable against the real paper.
4. Claim-evidence rule: every conclusion binds >=1 EXACT quote (source_id + paragraph_id),
   re-verified against the real file. Strength matches the evidence; any contradicts
   forbids established. Conclusions must be supported by INCLUDED evidence, not overstep.
5. Conflicts + gaps: present conflicting evidence as conflicts[] (>=2 located positions +
   handling); gaps need evidence OR documented search_scope_checked + human_confirm.
   "Not found" is NOT "nobody studied it".
6. Replay + boundary: keep query text/date/database, screening log, quality basis and
   citation locators auditable (screening_log.csv, provenance.json). Proposal prospective,
   bounded=true. No field-wide novelty/completeness, no completed-experiment wording.

## Scripts & dependencies
assemble.py (CLI), research_engine.py (validate_ir + compute_screening/synthesis +
check_quotes + build md/docx/csv/svg + provenance + summarize), w4kit.py (case load /
source check / dedup / result.json). Python 3.10+ standard library only — no third-party
packages required (numpy optional, never needed). See requirements.txt.

## Outputs (/app/output)
research_report.md, research_report.docx, synthesis_matrix.csv, screening_log.csv,
prisma_flow.svg, provenance.json (PRISMA + record_map + claim_map + source_map +
quote_checks), validation.json, result.json (preserves every output_contract key +
case_id + status + sources + uncertainty + change_log + prisma + exclusion_reasons +
quote_check_summary + human_confirm + boundary).

## Error handling (docs/ERROR_HANDLING.md)
Missing search_queries -> error; executed query without date -> warning; exclusion without
reason / PRISMA mismatch -> error; undeclared duplicate -> warning; included record without
quality appraisal -> warning; quote not in file -> error; established+contradicts -> error;
conflict -> both positions; gap -> evidence or search scope + human_confirm; over-boundary
wording -> error; IR/build error -> honest failed/partial. Never fabricate; never silent-skip.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/systematic_review/`: input/ (8 fictional docs) + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/systematic_review/ir.json --input examples/systematic_review/input --out /tmp/demo`
The example has a predefined protocol (I1/I2/E1/E2 + Q1/Q2), two-stage screening (6
included, 2 excluded, 1 duplicate), quality appraisal for all 6 included records, a
conflict (CF1) and grounded gaps (G1/G2). Real cases are supplied only at evaluation.

## Self-check
- [ ] protocol criteria + executable search_queries written first; executed queries dated
- [ ] two-stage screening; every decision conforms to a criterion; exclusions have reasons
- [ ] PRISMA recomputed and balanced; duplicates declared (DOI/fuzzy cross-check clean)
- [ ] every INCLUDED record has a quality appraisal with overall grade + located evidence
- [ ] every claim binds an EXACT quote re-verified against the real file; strength matches
- [ ] conflicts presented both sides; gaps grounded + human_confirm
- [ ] query/date/database + screening log + quality basis + locators re-runnable
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