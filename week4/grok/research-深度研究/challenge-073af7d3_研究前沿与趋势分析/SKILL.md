---
name: research-trend-analysis
description: Analyze research fronts and trends over organizer-provided local materials - recompute a publication-year histogram, theme-by-year evolution and direction, divide phases with representative works whose years fall inside each window, and identify research gaps, all supported by the engine's own statistics. Use when the task is research-front / trend / evolution analysis on a provided corpus (kind trend_analysis), NOT a pre-baked frontier list.
---

# Research front & trend analysis (研究前沿与趋势分析)

A source-bound Skill for the Bohrium weekly research-efficiency contest (research track).
The agent reads the ACTUAL organizer-provided material under /input, fills a structured
Research IR, and a deterministic stdlib engine validates it, RECOMPUTES the year histogram,
theme-by-year matrix, early/late direction, year growth and phase consistency, re-verifies
every quoted excerpt against the real files, and emits editable artifacts (md/docx/csv/svg)
+ trend_stats.json + bidirectional provenance + an honest result.json. No pre-baked answers;
trends and gaps are supported by the engine's own descriptive statistics over the corpus.

## When to use
Use for kind `trend_analysis`: deliver four checkable products — 时间趋势 (time trend),
主题演化 (theme evolution), 代表性工作 (representative works), 研究空白 (research gaps) —
not a "frontier list" of search hits. Rubric checks: year basis, theme attribution,
representative works and conclusions consistent with the source text; trends/gaps supported
by own statistics; coverage of time span, theme hierarchy, per-phase representative works
and gap types; queries, time-slice basis, theme-merge rules, statistical tables and
conclusion back-links independently recomputable.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete task rules for this case.
- The actual material files (papers/docs/records with publication years). Read and register
  the real files; trust content over filename/domain labels. PDFs arrive without a
  pre-extracted answer layer — parse yourself if a tool exists, else mark unverifiable.

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
1. Inventory inputs (w4kit.list_materials); register every used file in sources[] with an
   accurate publication year (the year basis for all trend statistics).
2. Read material; fill research_ir.json per `rules/rules_trend_analysis.md` + schema below.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir research_ir.json --input /input --out /app/output`
   -> validate_ir -> compute_trend (year histogram / theme-year / direction / growth /
   phase_check) + screening/synthesis + check_quotes -> build artifacts + trend_chart.svg +
   trend_stats.json + provenance.json -> summarize -> result.json.
4. Honest status: success only when validation clean + build complete; partial when
   errors/missing years/unverifiable quotes; failed on IR/build error. Save partial early.

## Research IR schema (agent fills from ACTUAL material; validated by engine.validate_ir)
```
ir_version: "1.0"            # required literal
case_id: <auto from /input/case.json>
kind: "trend_analysis"
sources: [{id, title, file, year, doi?, type?}]   # year REQUIRED for the histogram
protocol: {inclusion: [{id, text}], exclusion: [{id, text}], search_queries?: [...]}
records: [{id, source_id, title, year?, doi?, stage, decision, criteria_applied?, reason?, duplicate_of?}]
  # included_source_ids define the trend scope; if no records, scope = all sources
research_question?: {main, subquestions?: [...]}
themes: [{id, name, basis}]   # theme hierarchy; basis = merge/induction rule from sources
claims: [{id, text, type?, strength, theme_id?, evidence: [{source_id, paragraph_id, quote, stance?}]}]
  # theme_id + evidence source-year drive the theme-by-year matrix (each claim counted once per source-year)
trend: {
  year_basis: "publication_year",          # state the year口径 explicitly
  phases: [{id, label, years: [lo, hi], basis,
            representative_works: [{source_id}]}]   # reps must be registered, in scope, year inside window
}
conflicts?: [{id, topic, positions: [...], handling}]
gaps: [{id, type?, text, evidence? | search_scope_checked?, human_confirm?}]
tool_log?: [{step, tool, params, result?}]
proposal?: {text, bounded: true}
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes: []}
```
Evidence locator = {source_id, paragraph_id, quote, page?, table?, field?}. Materials may
mark paragraphs as `[P3] ...`; the engine restricts quote search to that paragraph.

## Domain rules — trend_analysis (detail: rules/rules_trend_analysis.md)
1. Year basis: every in-scope source needs an accurate publication year read from the real
   file; state trend.year_basis. Missing years are listed (missing_year_sources) and
   excluded from the histogram — never guess a year. No year data at all is an error.
2. Scope: the trend is computed over included_source_ids (from screening) or all sources.
   The engine recomputes year_histogram, year_growth and theme_year_matrix — do not
   hand-compute or paste external trend numbers.
3. Theme evolution: themes[] carry a basis (the merge/induction rule). Each claim's
   theme_id + evidence source-year feeds the theme-by-year matrix; the engine derives an
   early/late direction (rising/declining/stable WITHIN SET) split at the median year.
4. Phases & representative works: trend.phases[] each {id, label, years[lo,hi], basis,
   representative_works[]}. Every representative work must be a registered source, in the
   included scope, with its year INSIDE the phase window (engine rejects out-of-window or
   unregistered reps). Phase basis must be consistent with the source text.
5. Gaps: gaps[] need evidence OR documented search_scope_checked + human_confirm; cover gap
   types (evidence_gap/coverage_gap/etc.). Trends and gaps must be supported by the
   engine's own statistics, not asserted.
6. Boundary: all trends are DESCRIPTIVE within the provided corpus (small-sample caveat is
   emitted automatically). No field-wide/global trend claims, no completed-experiment
   wording. Quote back-links re-verified; proposal prospective, bounded=true.

## Scripts & dependencies
assemble.py (CLI), research_engine.py (validate_ir + compute_trend/screening/synthesis +
check_quotes + build md/docx/csv/svg + trend_stats.json + provenance + summarize), w4kit.py
(case load / source check / dedup / stats / result.json). Python 3.10+ standard library
only — no third-party packages required (numpy optional, never needed). See requirements.txt.

## Outputs (/app/output)
research_report.md, research_report.docx, synthesis_matrix.csv, screening_log.csv,
prisma_flow.svg, trend_chart.svg (year histogram), trend_stats.json (histogram + theme-year
matrix + direction + growth + phase_check + caveat), provenance.json, validation.json,
result.json (preserves every output_contract key + case_id + status + sources + uncertainty
+ change_log + prisma + trend_summary + quote_check_summary + boundary).

## Error handling (docs/ERROR_HANDLING.md)
No year data in scope -> error; missing year for a source -> warning (listed, excluded);
phase rep unregistered or year outside window -> error; no phases -> warning; quote not in
file -> error; established+contradicts -> error; gap -> evidence or search scope +
human_confirm; over-boundary wording -> error; IR/build error -> honest failed/partial.
Never fabricate years/trends; never silent-skip.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/trend_analysis/`: input/ (8 fictional docs, years 2017-2023) + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/trend_analysis/ir.json --input examples/trend_analysis/input --out /tmp/demo`
The example has 3 phases (PH1 2017-2019, PH2 2020-2022, PH3 2023) with in-window
representative works, 3 themes, a recomputed year histogram and grounded gaps. Real cases
are supplied only at evaluation.

## Self-check
- [ ] every in-scope source has an accurate year; year_basis stated; missing years declared
- [ ] year histogram / theme-year / direction / growth RECOMPUTED by the engine
- [ ] themes carry a merge/induction basis; claims mapped to theme_id
- [ ] phases cover the time span; every representative work in scope + year inside window
- [ ] gaps grounded (evidence or search scope) + human_confirm; supported by own statistics
- [ ] quote back-links re-verified; descriptive within-corpus caveat present
- [ ] no field-wide trend/completeness wording; proposal bounded
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