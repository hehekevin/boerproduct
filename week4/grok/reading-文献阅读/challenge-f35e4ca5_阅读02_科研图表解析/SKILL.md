---
name: scientific-figure-parsing
description: Parse scientific figures accurately — axis type/unit/scale recognition, complete element & data extraction to CSV/structured form, evidence-backed trend interpretation with reported-vs-inferred distinction; traceable result + honest status. Use for the "科研图表解析" workorder (kind=figure_parse).
---

# 科研图表解析 skill (figure_parse)

Source-bound literature-reading skill. The Agent reads the ACTUAL material and fills
the reading IR (items/answers with locators+status+reported/inferred, claims+support,
matrix, formulas, cleaning, reproduction, coverage); the engine deterministically
validates, runs the domain helper, emits the structured deliverable and result.json.
Output triad: 解析结果 / 证据与边界 / 运行状态. Never write can't-judge as fact.

## Focus (rubric)
- 读得准: axis type (linear/log/dual), scale start/interval, unit magnitude correct (mV≠V, log≠linear).
- 提得全: curves/points/error bars/peaks/significance/scale bar/subplot ids fully restored; non-data not treated as data.
- 讲得清: trend/statistical conclusions backed by figure evidence; distinguish directly-readable vs inferred.

## Scope / trigger
Use when the case asks for 科研图表解析 (workorder kind=figure_parse). Only given material;
no online retrieval / pixel-guessing unless provided & asked.

## Inputs (runtime)
`/input/case.json` (copy case_id; read output_contract), `/input/task.md`, material
(paragraph/table text, figures, formulas) + workorder files when present
(target-fields.json / comparison-workorder.json / benchmark workorder).

## Workflow (detail: docs/READING_WORKFLOW.md)
1. Read & register sources (document_id + paragraph/page locator + version).
2. Fill reading IR per `rules/rules_figure_parse.md`.
3. `python assemble_read.py --ir reading_ir.json --input /input --out /app/output`
   → validate → domain helper (clean/formula/compare/benchmark) → reading_result.json
   + reading_result.md (+domain artifacts) → result.json.
4. Honest status: insufficient_evidence / input_error / partial with reason +
   human-takeover point; save partial early.

## Domain rules
See `rules/rules_figure_parse.md`. Key:
- Read axis type/scale/units first; record them; never assume linear.
- Extract data points/curves to CSV with coordinates+units; list error bars/peaks/significance/scale bar/subplots.
- Tag interpretation reported (directly readable) vs inferred; attach figure/panel locator; flag uncertainty.
- Output structured figure record + data CSV + evidence; honest status if image unreadable.

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
- [ ] axis/unit/scale correct
- [ ] elements & data complete (CSV)
- [ ] interpretation evidence-backed; reported vs inferred
- [ ] traceable + honest status
- [ ] result.json honest (status/sources/uncertainty); item_map complete


## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

组织方输入修订v2：按实际材料更正三例领域/图型标签；明确必做对象是每例给出的1张原图片及全部原表。未给像素的其他图注明确列缺口，不能构造，也不是要求补齐的隐藏任务。公开评分维度不变。

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
