---
name: research-topic-novelty
description: Evaluate a proposed research topic against organizer-provided local materials - define a falsifiable question, compare against correctly-chosen prior work, identify novelty items with coverage-derived verdicts (novel_within_sources / partially_overlapping / covered / uncertain), and judge feasibility premises (supported / assumption / unknown). Use when the task is research-topic selection / novelty / innovation assessment on a provided corpus (kind topic_novelty), NOT a pre-baked verdict.
---

# Research topic selection & novelty assessment (科研选题与创新性评估)

A source-bound Skill for the Bohrium weekly research-efficiency contest (research track).
The agent reads the ACTUAL organizer-provided material under /input, fills a structured
Research IR, and a deterministic stdlib engine validates it, DERIVES each novelty verdict
from the declared coverage, re-verifies every quoted excerpt against the real files, and
emits editable artifacts (md/docx/csv/svg) + novelty_assessment.json + bidirectional
provenance + an honest result.json. No pre-baked answers; novelty is scoped to the provided
sources and every judgment binds a real source_id + paragraph_id + exact quote.

## When to use
Use for kind `topic_novelty`: advance a research idea to a decision-ready assessment with
four consistent deliverables — 问题定义 (question definition), 已有工作比较 (prior-work
comparison), 创新点识别 (novelty identification), 可行性判断 (feasibility judgment). Rubric
checks: papers really exist; comparison objects correctly chosen; novelty items correctly
judged as covered/overlapping by prior work; feasibility premises hold; coverage of the six
points (decomposition, search coverage, evidence back-links, conflicting evidence,
synthesis, gaps); queries, screening criteria, evidence table and judgment reasons
independently re-checkable.

## Inputs (runtime)
- /input/case.json — copy case_id; read output_contract (preserve EVERY key).
- /input/task.md — the concrete task rules + the proposed topic for this case.
- The actual material files (prior-work papers/docs/records). Read and register the real
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
1. Inventory inputs (w4kit.list_materials); register every used prior-work file in sources[].
2. Read material; fill research_ir.json per `rules/rules_topic_novelty.md` + schema below.
3. Run:
   `PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir research_ir.json --input /input --out /app/output`
   -> validate_ir -> compute_novelty (derive verdicts + feasibility) + screening/synthesis +
   check_quotes -> build artifacts + novelty_assessment.json + provenance.json ->
   summarize -> result.json.
4. Honest status: success only when validation clean + build complete; partial when
   errors/verdict mismatches/unverifiable quotes; failed on IR/build error. Save partial early.

## Research IR schema (agent fills from ACTUAL material; validated by engine.validate_ir)
```
ir_version: "1.0"            # required literal
case_id: <auto from /input/case.json>
kind: "topic_novelty"
sources: [{id, title, file, year?, doi?, type?}]
protocol: {inclusion: [{id, text}], exclusion: [{id, text}], search_queries?: [...]}
records: [{id, source_id, title, year?, doi?, stage, decision, criteria_applied?, reason?, duplicate_of?}]
research_question?: {main, subquestions?: [{id, question, depends_on?}]}
themes: [{id, name, basis}]
claims: [{id, text, type?, strength, theme_id?, evidence: [{source_id, paragraph_id, quote, stance?}]}]
topic: {
  question_definition: {object, variables, baseline, falsifiable},   # ALL FOUR required
  comparison: [{dimension, comparable?, prior_work: [{source_id, evidence}], proposed}],
  novelty: [{id, statement, type, covered_by: [{source_id, paragraph_id, quote, coverage}],
             verdict?, uncertainty}],
    # type: method|data|application|conclusion ; coverage: full|partial|none
    # verdict DERIVED from coverage: full->covered, partial->partially_overlapping,
    #   all none->novel_within_sources, else uncertain; declared verdict must match
    # uncertainty REQUIRED on every novelty item; covered_by needs an exact quote
  feasibility: [{id, premise, status, evidence?, human_confirm?, risk?}]
    # status: supported (needs evidence) | assumption | unknown (auto human_confirm)
}
conflicts?: [{id, topic, positions: [...], handling}]
gaps: [{id, type?, text, evidence? | search_scope_checked?, human_confirm?}]
proposal: {text, bounded: true}     # prospective; no completed experiments
uncertainty: [{item, reason, impact?, handling}]
provenance: {pipeline, changes: []}
```
Evidence locator = {source_id, paragraph_id, quote, page?, table?, field?}. Materials may
mark paragraphs as `[P3] ...`; the engine restricts quote search to that paragraph.

## Domain rules — topic_novelty (detail: rules/rules_topic_novelty.md)
1. Question definition: topic.question_definition needs ALL of object, variables, baseline,
   falsifiable. The question must be falsifiable (a concrete condition that would refute the
   proposed benefit), not a vague aspiration.
2. Prior-work comparison: comparison[] rows {dimension, comparable, prior_work[{source_id,
   evidence}], proposed}. Choose comparison objects that truly match the proposed topic;
   each prior_work binds an exact quote. Mark comparable=false when dimensions differ.
3. Novelty identification: novelty[] {id, statement, type, covered_by[], verdict?,
   uncertainty}. type in {method, data, application, conclusion}. Each covered_by entry
   {source_id, paragraph_id, quote, coverage in full/partial/none}. The engine DERIVES the
   verdict from coverage (full->covered; partial->partially_overlapping; all none->
   novel_within_sources; else uncertain); a declared verdict that disagrees is an error.
   Every novelty item needs an explicit uncertainty note. "Not found here" is NOT global
   novelty — verdicts are novel_WITHIN_SOURCES only.
4. Feasibility judgment: feasibility[] {id, premise, status, evidence?, human_confirm?,
   risk?}. status supported REQUIRES evidence; assumption/unknown are auto-flagged
   human_confirm. State the risk for each premise. Do not assert a premise holds without
   located evidence.
5. Evidence back-links + conflicts + gaps: claims/conflicts/gaps bind EXACT quotes
   re-verified against the real file; strength matches evidence (contradicts forbids
   established). Present conflicting evidence; gaps need evidence OR search_scope_checked +
   human_confirm.
6. Boundary: novelty/feasibility are prospective and scoped to provided_sources_only. No
   field-wide/global novelty or completeness, no completed-experiment wording (engine scans
   and rejects). proposal.bounded must be true. Declare uncertainty (scope/bias/assumptions).

## Scripts & dependencies
assemble.py (CLI), research_engine.py (validate_ir + compute_novelty/screening/synthesis +
check_quotes + build md/docx/csv/svg + novelty_assessment.json + provenance + summarize),
w4kit.py (case load / source check / dedup / result.json). Python 3.10+ standard library
only — no third-party packages required (numpy optional, never needed). See requirements.txt.

## Outputs (/app/output)
research_report.md, research_report.docx, synthesis_matrix.csv, screening_log.csv,
prisma_flow.svg, novelty_assessment.json (novelty_items + derived verdicts +
verdict_mismatches + feasibility + n_assumptions + comparison stats + caveat),
provenance.json, validation.json, result.json (preserves every output_contract key +
case_id + status + sources + uncertainty + change_log + prisma + novelty_summary +
human_confirm + quote_check_summary + boundary).

## Error handling (docs/ERROR_HANDLING.md)
question_definition missing a key -> error; no novelty items -> error; declared verdict !=
coverage-derived -> error; novelty without uncertainty / covered_by without quote -> error;
invalid novelty type/coverage -> error; feasibility supported without evidence -> error;
assumption/unknown -> auto human_confirm; empty comparison -> warning; quote not in file ->
error; over-boundary wording / proposal.bounded!=true -> error; IR/build error -> honest
failed/partial. Never fabricate novelty/feasibility; never silent-skip.

## Minimal example (SYNTHETIC — interface demo, NOT a formal answer)
`examples/topic_novelty/`: input/ (8 fictional prior-work docs) + ir.json. Run:
`PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/topic_novelty/ir.json --input examples/topic_novelty/input --out /tmp/demo`
The example defines a falsifiable question, 3 comparison dimensions, 3 novelty items
(N1/N2 partially_overlapping, N3 novel_within_sources — verdicts derived from coverage),
and 3 feasibility premises (F1 supported, F2 assumption, F3 unknown -> human_confirm).
Real cases are supplied only at evaluation.

## Self-check
- [ ] question_definition has object + variables + baseline + falsifiable
- [ ] comparison objects correctly chosen; each prior_work binds an exact quote
- [ ] novelty items have type + uncertainty + located covered_by; verdicts match coverage
- [ ] feasibility supported has evidence; assumption/unknown flagged human_confirm + risk
- [ ] every claim/conflict/gap/novelty/feasibility quote re-verified against the real file
- [ ] conflicts surfaced; gaps grounded + human_confirm
- [ ] novelty scoped to provided sources; no global novelty/completed-experiment wording
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