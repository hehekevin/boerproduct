---
name: multi-document-comparison
description: Build a common-field comparison matrix across papers with per-cell source_document_id+paragraph_id+units/metric, comparability testing, and conflict explanation attributed to sample/method/condition/metric; traceable result.json. Use for the "多文档比较与整合" workorder (kind=multi_doc_compare).
---

# 多文档比较与整合 skill (multi_doc_compare)

Source-bound literature-reading skill. The Agent reads the ACTUAL material and fills
the reading IR (items/answers with locators+status+reported/inferred, claims+support,
matrix, formulas, cleaning, reproduction, coverage); the engine deterministically
validates, runs the domain helper, emits the structured deliverable and result.json.
Output triad: 解析结果 / 证据与边界 / 运行状态. Never write can't-judge as fact.

## Focus (rubric)
- 对得齐: fields unified to one definition so cell-by-cell comparison is meaningful.
- 填得准: each cell from its labelled paper; units/dataset/metric口径 recorded with value.
- 说得清: consistency/conflict explained by sample/method/condition/metric with checkable source.
- 查得回: every value & difference conclusion traceable.

## Scope / trigger
Use when the case asks for 多文档比较与整合 (workorder kind=multi_doc_compare). Only given material;
no online retrieval / pixel-guessing unless provided & asked.

## Inputs (runtime)
`/input/case.json` (copy case_id; read output_contract), `/input/task.md`, material
(paragraph/table text, figures, formulas) + workorder files when present
(target-fields.json / comparison-workorder.json / benchmark workorder).

## Workflow (detail: docs/READING_WORKFLOW.md)
1. Read & register sources (document_id + paragraph/page locator + version).
2. Fill reading IR per `rules/rules_multi_doc_compare.md`.
3. `python assemble_read.py --ir reading_ir.json --input /input --out /app/output`
   → validate → domain helper (clean/formula/compare/benchmark) → reading_result.json
   + reading_result.md (+domain artifacts) → result.json.
4. Honest status: insufficient_evidence / input_error / partial with reason +
   human-takeover point; save partial early.

## Domain rules
See `rules/rules_multi_doc_compare.md`. Key:
- Define common fields (object/data/method/condition/metric/conclusion/limit); extract per doc with value rules.
- Normalize dataset version/sample/split/baseline/metric; decide comparable vs comparable-subset.
- Build matrix cells with source_document_id+paragraph_id+units; run compare.py for coverage/comparability/conflicts.
- Explain conflicts with attribution + per-cell sources; never hide disagreement.

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
- [ ] common fields unified
- [ ] cells sourced (doc+paragraph+units)
- [ ] comparability tested; conflicts explained
- [ ] traceable matrix + result.json
- [ ] result.json honest (status/sources/uncertainty); item_map complete


## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Concrete input interface (organizer revision v2)
Read /input/comparison-workorder.json and all supplied corpus documents. Build a common-field comparison matrix with exact source_document_id and paragraph_id, then test comparability of task, metric, units, material, pollutant and budget before quantitative synthesis. A single-paper summary does not satisfy multi-document comparison. Retain all noncomparable and unreported conditions; do not pool unlike datasets or dyes.
The public example remains synthetic. Real papers, concrete target values, hidden expected readings and formal claims are supplied only during evaluation, never during Skill authoring. Original public scoring remains unchanged.

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
