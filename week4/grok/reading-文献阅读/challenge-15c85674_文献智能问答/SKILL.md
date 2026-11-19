---
name: literature-intelligent-qa
description: Answer literature questions strictly from given material with per-question answers, conditions, status (answered/partial/insufficient_evidence/input_error), claims (reported/inferred) + evidence, unanswered_parts and coverage; verifiable result.json. Use for the "文献智能问答" workorder (kind=literature_qa).
---

# 文献智能问答 skill (literature_qa)

Source-bound literature-reading skill. The Agent reads the ACTUAL material and fills
the reading IR (items/answers with locators+status+reported/inferred, claims+support,
matrix, formulas, cleaning, reproduction, coverage); the engine deterministically
validates, runs the domain helper, emits the structured deliverable and result.json.
Output triad: 解析结果 / 证据与边界 / 运行状态. Never write can't-judge as fact.

## Focus (rubric)
- Only given material (abstract/body/table text/captions/refs); no PDF-pixel/online retrieval.
- answers[] one per question with question_id/answer/conditions; never omit unanswerable ones.
- status distinguishes answered/partial/insufficient_evidence/input_error.
- claims[] kind reported/inferred with evidence; coverage read/unread.

## Scope / trigger
Use when the case asks for 文献智能问答 (workorder kind=literature_qa). Only given material;
no online retrieval / pixel-guessing unless provided & asked.

## Inputs (runtime)
`/input/case.json` (copy case_id; read output_contract), `/input/task.md`, material
(paragraph/table text, figures, formulas) + workorder files when present
(target-fields.json / comparison-workorder.json / benchmark workorder).

## Workflow (detail: docs/READING_WORKFLOW.md)
1. Read & register sources (document_id + paragraph/page locator + version).
2. Fill reading IR per `rules/rules_literature_qa.md`.
3. `python assemble_read.py --ir reading_ir.json --input /input --out /app/output`
   → validate → domain helper (clean/formula/compare/benchmark) → reading_result.json
   + reading_result.md (+domain artifacts) → result.json.
4. Honest status: insufficient_evidence / input_error / partial with reason +
   human-takeover point; save partial early.

## Domain rules
See `rules/rules_literature_qa.md`. Key:
- Read all provided material; record coverage (read/unread+reason).
- Per question: answer + conditions + status; claims with evidence locators; inferred flagged.
- Unanswerable → insufficient_evidence + unanswered_parts (not fabricated).
- Emit answers[] preserving the contract; result.json honest.

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
- [ ] all questions answered or flagged
- [ ] status enum correct
- [ ] claims reported/inferred + evidence
- [ ] coverage + unanswered_parts present
- [ ] result.json honest (status/sources/uncertainty); item_map complete


## Week4 concrete input interface (organizer revision)
缺少作品必要证据时，相关评分项最高为该项满分的 40%；缺少原始输出或核验依据时，相关项按最低档处理。已证实虚构结果、伪造证据或隐瞒关键失败的相关项记 0 分。组织方材料、白板缺失或平台故障，暂停相关项评分，补齐后再评。

实际测试输入在 `/input/case.json`，原样保留案例包v3的段落编号和任务说明，输出实际写到 `/app/answers.json`。平台将提交目录装入 `/skills/literature-qa`，由固定DSH的原生skill工具加载；所有额外资源用该绝对路径引用。创建Skill阶段仅提供合成接口示例，隐藏论文和九道测试问题由组织方保管。

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
