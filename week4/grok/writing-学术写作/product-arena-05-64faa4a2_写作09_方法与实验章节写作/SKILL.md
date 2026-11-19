---
name: arena-methods-section
description: Source-bound Methods/Experiments section writing (写作09方法与实验章节写作, kind=methods_section). The Agent reads the ACTUAL protocol/config/log/data under /input, fills a writing IR (claims+evidence, sections[], parameters[] with value/unit/target/source/status, equipment/reagents, statistical_methods, datasets, reproducibility), and a deterministic stdlib engine validates parameter sourcing + reported-vs-inferred + number-consistency, builds editable manuscript.md + .docx + parameters.csv + reproducibility.md, and writes provenance + honest result.json. Use when the workorder asks to write a reproducible Methods or Experiments section from provided protocol/data. Gaps flagged not_reported + human_confirm, never invented.
---

# 方法与实验章节写作 skill (methods_section)

Source-bound, reproducible Methods/Experiments writing. The Agent extracts elements
from real protocol/config/log/code/data; the engine enforces that every parameter
traces to a source, reported vs inferred vs not_reported is distinguished, numbers
match the material, and required elements are present. Never补出数值 for paragraph flow.

## Focus (rubric)
- 写得全: key steps, setup, parameters, dataset/split, controls, replicates all written.
- 写得准: parameter values, dataset version/split, train/eval conditions match
  config/log/code; no numbers invented for smoothness.
- 做得着: reader can reproduce — versions, environment, seed, commands given.
- 说得住: gaps/uncertainties explicitly flagged for author confirmation; limitations
  point to concrete failure scenarios, not boilerplate.

## Scope / trigger
Use when the case asks for 方法与实验章节写作 / Methods / Experiments section
(workorder kind=methods_section). IN: reproducible section from protocol/data +
editable delivery. OUT: polishing, references, intro, LaTeX, PPT.

## Inputs (runtime)
`/input/case.json` (copy `case_id`; read `output_contract`, audience/genre),
`/input/task.md`, ACTUAL protocol/config/log/code/data-description (txt/json/yaml/csv/
py/md). READ files; trust content over labels.

## Workflow (detail: docs/WORKFLOW.md)
1. Read & register sources (protocol/config/log/data) with locators.
2. Fill IR per `rules/rules_methods_section.md`: `claims[]`+evidence; `sections[]`
   Methods + Experiments; `parameters[]` {name, value, unit, target, status, source,
   locator}; `equipment[]`, `reagents[]`, `statistical_methods[]`, `datasets[]`,
   `reproducibility[]`; `numbers[]`; uncertainty for gaps.
3. Run:
   `python assemble.py --ir writing_ir.json --input /input --out /app/output`
   → validate (writekit + arena methods rules) → parameter-source + number checks →
   manuscript.md + .docx + parameters.csv + reproducibility.md → provenance.json
   (claim_map + parameter_map) → honest result.json.
4. Edit IR, re-run; keep revisions/provenance.changes[].

## IR schema (kind=methods_section)
```
ir_version "1.0", case_id, kind "methods_section", title, audience, genre,
sources[] {id, locator, kind, version, values[]},
claims[] {id, text, type, evidence[]{source, locator, strength, supports}, citation_ids[]},
numbers[] {value, unit, source, locator}, glossary[],
required_sections[] ["Methods","Experiments"],
sections[] {id, level, heading, role, paragraphs[]{id, text, claims[], source}},
parameters[] {name, value, unit, target, status, source, locator},
equipment[] {name, count, source, locator}, reagents[] {name, vendor, lot, source, locator},
statistical_methods[] {name, alpha, n, variability, source, locator},
datasets[] {name, version, size, split, seed, source, locator},
reproducibility {code_version, environment, seed, commands, data_access},
uncertainty[], provenance{pipeline, changes[]}
```
status ∈ reported/inferred/not_reported/source_conflict/extraction_failed/insufficient_evidence.

## Kind rules
See `rules/rules_methods_section.md`. Key: every parameter has source + status (no
source = validation error); reported vs inferred distinguished in text; dataset
version/split explicit; controls same-budget; statistical method stated; reproducibility
checklist with gaps → not_reported + human_confirm; number-consistency vs material.

## Scripts & dependencies
`assemble.py`, `arena_write_engine.py` (shared arena engine), `writekit.py`,
`docxkit.py` (stdlib md+docx), `w4kit.py` (case/result, read_table). Deps: Python 3.10+
stdlib only. Run with `PYTHONDONTWRITEBYTECODE=1`.

## Outputs (/app/output)
`manuscript.md` + `manuscript.docx` (editable Methods/Experiments), `parameters.csv`
(name/value/unit/target/status/source/locator), `reproducibility.md`, `writing_ir.json`,
`provenance.json` (claim_map + parameter_map), `validation.json`, `result.json`
(output_contract + case_id + honest status + extra_checks.number_issues +
n_parameters/n_inferred/n_not_reported).

## Error handling (docs/ERROR_HANDLING.md)
Missing config/parameter → not_reported + human_confirm (never invent a value);
config conflict → source_conflict + surface; dataset version unknown → flag;
parameter without source → validation error; inferred value → mark inferred +
distinguish; permission/file gap → extraction_failed + partial. Save honest partial early.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/methods_section/`: input/case.json + task.md + protocol.txt + ir.json + README.
`python assemble.py --ir examples/methods_section/ir.json --input examples/methods_section/input --out /tmp/demo`
9 parameters (weight_decay not_reported), reproducibility gaps flagged.

## Self-check
- [ ] every parameter has source + status; reported vs inferred distinguished
- [ ] dataset version/split, controls, statistical method present
- [ ] reproducibility checklist; gaps not_reported + human_confirm
- [ ] number_issues empty/reviewed; editable md+docx+csv
- [ ] result.json honest (status/sources/uncertainty/change_log); parameter_map complete

## Week4 concrete input interface (organizer revision)
组织方为本题准备 3 个固定案例。每个案例包含任务说明、科研材料、必要的输入约束和评分所需的证据范围；案例会以相同内容分别交给基础 Agent 和加载参赛 Skill 的 Agent。你不需要自带正式测试案例，也不需要提交预先写好的答案。

平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-parameter/per-step results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.