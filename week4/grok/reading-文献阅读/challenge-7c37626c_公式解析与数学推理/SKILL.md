---
name: formula-parsing-math-reasoning
description: Parse paper formulas preserving structure (LaTeX), explain variables (definition/unit/range/source), present derivation steps with assumptions, and verify by safe numeric substitution; structure/variable/numeric checks + verifiable result.json. Use for the "公式解析与数学推理" workorder (kind=formula_reasoning).
---

# 公式解析与数学推理 skill (formula_reasoning)

Source-bound literature-reading skill. The Agent reads the ACTUAL material and fills
the reading IR (items/answers with locators+status+reported/inferred, claims+support,
matrix, formulas, cleaning, reproduction, coverage); the engine deterministically
validates, runs the domain helper, emits the structured deliverable and result.json.
Output triad: 解析结果 / 证据与边界 / 运行状态. Never write can't-judge as fact.

## Focus (rubric)
- 认得准: structure/symbols fully restored (sub/superscript, brackets, greek, units; no lost terms).
- 讲得清: each variable has source-backed definition/range/unit; not guessed silently.
- 推得顺: derivation split into checkable steps with assumptions/approximations/boundaries.
- 核验: numeric substitution check.

## Scope / trigger
Use when the case asks for 公式解析与数学推理 (workorder kind=formula_reasoning). Only given material;
no online retrieval / pixel-guessing unless provided & asked.

## Inputs (runtime)
`/input/case.json` (copy case_id; read output_contract), `/input/task.md`, material
(paragraph/table text, figures, formulas) + workorder files when present
(target-fields.json / comparison-workorder.json / benchmark workorder).

## Workflow (detail: docs/READING_WORKFLOW.md)
1. Read & register sources (document_id + paragraph/page locator + version).
2. Fill reading IR per `rules/rules_formula_reasoning.md`.
3. `python assemble_read.py --ir reading_ir.json --input /input --out /app/output`
   → validate → domain helper (clean/formula/compare/benchmark) → reading_result.json
   + reading_result.md (+domain artifacts) → result.json.
4. Honest status: insufficient_evidence / input_error / partial with reason +
   human-takeover point; save partial early.

## Domain rules
See `rules/rules_formula_reasoning.md`. Key:
- Emit structure-checkable LaTeX; run formula.py structure check (balanced braces/left-right).
- Build variable table (definition/unit/range/first-definition locator; defined-in-paper vs inferred).
- Split derivation into steps with assumptions; mark cross-formula dependencies.
- Run safe numeric-substitution check (AST, no arbitrary eval); report match/tolerance.

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
- [ ] LaTeX structure valid; symbols complete
- [ ] variable table source-backed
- [ ] derivation steps with assumptions
- [ ] numeric check passed/flagged
- [ ] result.json honest (status/sources/uncertainty); item_map complete


## Week4 concrete input interface (organizer revision)
组织方为本题准备 3 个固定案例。每个案例包含任务说明、科研材料、必要的输入约束和评分所需的证据范围；案例会以相同内容分别交给基础 Agent 和加载参赛 Skill 的 Agent。你不需要自带正式测试案例，也不需要提交预先写好的答案。

平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
