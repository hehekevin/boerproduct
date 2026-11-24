---
name: literature-reading-benchmark-eval
description: Build runnable, reusable, versioned reading benchmark task cards + unified runner + 0/1/2 scoring + failure analysis; scores traceable to original output/config; repeat-run stability recorded; verifiable result.json. Use for the "文献阅读 Benchmark 与评测工具" workorder (kind=reading_benchmark).
---

# 文献阅读 Benchmark 与评测工具 skill (reading_benchmark)

Source-bound literature-reading skill. The Agent reads the ACTUAL material and fills
the reading IR (items/answers with locators+status+reported/inferred, claims+support,
matrix, formulas, cleaning, reproduction, coverage); the engine deterministically
validates, runs the domain helper, emits the structured deliverable and result.json.
Output triad: 解析结果 / 证据与边界 / 运行状态. Never write can't-judge as fact.

## Focus (rubric)
- 判得动: task/input/reference/rubric complete so two graders agree.
- 跑得一致: repeat runs under fixed tools/budget stable; fluctuation recorded.
- 查得回: each score traceable via task ID to output/config/scoring record.
- 改得动: failure attributed to task type, feeds next revision.

## Scope / trigger
Use when the case asks for 文献阅读 Benchmark 与评测工具 (workorder kind=reading_benchmark). Only given material;
no online retrieval / pixel-guessing unless provided & asked.

## Inputs (runtime)
`/input/case.json` (copy case_id; read output_contract), `/input/task.md`, material
(paragraph/table text, figures, formulas) + workorder files when present
(target-fields.json / comparison-workorder.json / benchmark workorder).

## Autopilot — run this FIRST (complete baseline within budget)
`PYTHONDONTWRITEBYTECODE=1 python auto_read.py --input /input --out /app/output --work /app/work`
Auto-registers sources from the ACTUAL /input papers+workorders, auto-fills the complete reading IR
into /app/work (requested fields/claims with EXACT [Pn] quote locators; honest not_reported /
insufficient_evidence for missing), runs the SAME validate+build path as the package assembler, and
ALWAYS writes an honest result.json (try/except fallback preserves every output_contract key +
case_id) — even on empty input or failure. Never fabricated. THEN, within remaining budget, refine
the auto-filled IR in /app/work and re-run
`PYTHONDONTWRITEBYTECODE=1 python assemble_read.py --ir /app/work/<ir>.json --input /input --out /app/output`
to improve. Save partial early. If autopilot is unavailable, use the manual Workflow below.

## Workflow (detail: docs/READING_WORKFLOW.md)
1. Read & register sources (document_id + paragraph/page locator + version).
2. Fill reading IR per `rules/rules_reading_benchmark.md`.
3. `python assemble_read.py --ir reading_ir.json --input /input --out /app/output`
   → validate → domain helper (clean/formula/compare/benchmark) → reading_result.json
   + reading_result.md (+domain artifacts) → result.json.
4. Honest status: insufficient_evidence / input_error / partial with reason +
   human-takeover point; save partial early.

## Domain rules
See `rules/rules_reading_benchmark.md`. Key:
- Define task cards (task/input material/reference answer/rubric/difficulty/license); version snapshots.
- Unified runner fixes tools/prompt/budget/output format; normalize outputs to a scorable dir.
- Score 0/1/2 per task with rule + human review; keep raw output + config + scoring record.
- Run eval reproducibly; produce per-task scores + failure analysis; record stability.

## Scripts & dependencies
assemble_read.py, readkit.py (validation/evidence/status), clean.py (unit conversion/dedup), formula.py (LaTeX structure + safe numeric check), compare.py (matrix/comparability/conflict), benchkit.py (tasks/rubric/eval), figkit.py (case/result). Deps: Python 3.10+ stdlib (no third-party required for core).

## Outputs (/app/output)
reading_result.json + reading_result.md, domain artifacts (cleaned.json /
formula_check.json / comparison.json / benchmark), reading_ir.json, provenance.json
(item_map), validation.json, result.json.

## Error handling (docs/ERROR_HANDLING.md + READING_WORKFLOW §3)
Missing/unreported → insufficient_evidence + unanswered_parts; input read failure →
input_error; inferred → kind=inferred + uncertainty; conflict → surface + attribution;
unit/parse failure → keep original + pending. Never fabricate.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/read_ex/`: ir_extract / ir_clean / ir_formula / ir_compare + input. Run e.g.:
`python assemble_read.py --ir examples/read_ex/ir_extract.json --input examples/read_ex/input --out /tmp/demo`
Interface demonstration only.

## Self-check
- [ ] task cards decidable & complete
- [ ] runner fixed & reproducible
- [ ] 0/1/2 scores traceable
- [ ] failure analysis + versioning
- [ ] result.json honest (status/sources/uncertainty); item_map complete


## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Organizer revision2 supplies a four-item source-conditioned benchmark-DRAFT workorder. Provided sources are paragraph/table text, not PDF-pixel gold. Technical synthetic checker logs are not DSH scores or independent semantic validation. Public16scoring and original scientific source bytes remain unchanged.

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
