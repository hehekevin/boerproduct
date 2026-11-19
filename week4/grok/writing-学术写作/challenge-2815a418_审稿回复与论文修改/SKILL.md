---
name: reviewer-response-revision
description: Point-by-point reviewer response + revision with full coverage, locatable edits, verifiable evidence, and three-way consistency (response letter / revised manuscript / version); editable deliverables + result.json. Use for the "审稿回复与论文修改" workorder (kind=reviewer_response).
---

# 审稿回复与论文修改 skill (reviewer_response)

Source-bound academic writing skill. The Agent reads the ACTUAL material and fills
the writing IR (claims+evidence, citations, sections, glossary, revisions, and
domain fields); the engine deterministically validates, builds the editable
deliverable, runs consistency checks, exports and writes result.json. Never add
facts outside the material; never fabricate citations/numbers.

## Focus (rubric)
- 答得全: every comment and its sub-requests identified with a clear disposition, not half-answered.
- 改得准: each claimed edit actually lands in the text, locatable in the specified version.
- 证得住: added experiment/data/literature/analysis is verifiable, or why it cannot be done is explained.
- 对得上: response letter, revised manuscript, and version are consistent.

## Scope / trigger
Use when the case asks for 审稿回复与论文修改 (workorder kind=reviewer_response). IN: this writing
task + source-binding + editable delivery. OUT: unrelated tracks (data-viz
algorithms, experimental design, PPT software), per the statement.

## Inputs (runtime)
`/input/case.json` (copy case_id; read output_contract/audience/genre/format),
`/input/task.md`, actual materials (docx/pdf/csv/images) + template if provided.
Read files; trust content over labels.

## Workflow (detail: docs/WRITING_WORKFLOW.md)
1. Read & register sources with precise locators.
2. Fill writing IR per `rules/rules_reviewer_response.md` (claims+evidence+strength,
   citations, sections, glossary, numbers, revisions, domain fields; uncertainty +
   human_confirm for gaps).
3. `python assemble_write.py --ir writing_ir.json --input /input --out /app/output`
   → validate → build (md+docx / mindmap / benchmark) → consistency checks →
   export (office-renderer, honest fallback) → result.json.
4. Source-preserving edit: edit IR, re-run; keep revisions/change log for rollback.

## Domain rules
See `rules/rules_reviewer_response.md`. Key:
- Decompose comments by id/type/severity/action; split multi-subrequest comments.
- Per comment: decision (accept/partial/reject)+reason; map 'modified' to a concrete locatable edit.
- Provide verifiable evidence for additions, or a honest reason if not feasible.
- Cross-check response letter vs revised ms vs version; keep revision log + diff.

## Scripts & dependencies
assemble_write.py, writekit.py (validation/consistency/citation/revision), docxkit.py (stdlib md+valid editable docx), mindmap.py (editable SVG/PNG/PDF), benchkit.py (tasks/rubric/eval), figkit.py (case/result). Deps: Python 3.10+ stdlib; matplotlib/numpy/Pillow for mindmap & previews; office-renderer for true docx/pdf render (honest fallback). No python-docx required.

## Outputs (/app/output)
Editable deliverable (manuscript.md+docx, or mindmap.svg/png/pdf, or
tasks.json+rubric.json+reference_answers.md+eval.py), writing_ir.json,
provenance.json (claim_map), validation.json, result.json (+export previews).

## Error handling (docs/ERROR_HANDLING.md + WRITING_WORKFLOW §4)
Missing material/full-text → state gap, write only supported, flag human_confirm;
unverifiable citation → mark uncertain; conflict → surface in uncertainty/待核清单;
template/style gap → documented fallback; over-length → compress without dropping
evidence. Save honest partial early; never fabricate.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/writing/` (prose), `examples/mindmap/`, `examples/bench/`. Run e.g.:
`python assemble_write.py --ir examples/writing/writing_ir.json --input examples/writing/input --out /tmp/demo`
Interface demonstration only.

## Self-check
- [ ] all comments/subrequests dispositioned
- [ ] claimed edits locatable in version
- [ ] evidence verifiable or limitation explained
- [ ] letter/ms/version consistent; change log
- [ ] result.json honest (status/sources/uncertainty/change_log); claim_map complete


## Week4 concrete input interface (organizer revision)
| 评分维度 | 分值 | 评分点及分值 | 考察内容 |
|-|-|-|-|
| 实际效果 | 40 分 | 任务完成度 15 分；结果正确性 15 分；结果完整性 5 分；结果可核验性 5 分 | 是否把一份真实的返修材料（审稿意见清单加指定版本稿件）处理成可直接提交给编辑部的修改稿与逐条回复。；回应中的事实、数据、引用和专业判断是否准确，以及"已修改"的声明是否与稿件真实状态一致。；是否覆盖意见条目、一条意见内的多个子要求，以及回复信与修订稿的格式要求。；回复信中的每一处定位能否在指定版本稿件中被独立核对。 |
| 使用增益 | 25 分 | 质量增益 15 分；效率增益 5 分；增益可验证性 5 分 | 在相同稿件版本、相同意见清单、相同工具权限下，加载成果后返修交付质量是否稳定提升。；是否减少逐条比对意见、人工查找行号、重写语气和补齐证据清单的时间。；"有改善"的结论是否有公平对照与逐条证据支撑。 |
| 创新增益 | 15 分 | 新增能力 5 分；方法改进 5 分；创新证据 5 分 | 是否形成基础 Agent 不具备、或难以稳定实现的返修处理能力。；意见拆解、定位方式、证据组织与语气控制的方法是否带来实质改进。；创新点相对已有返修工具或通用写作 Agent 的边界与价值是否被证明。 |
| 可靠体验 | 10 分 | 调用与易用性 3 分；运行稳定性 4 分；异常处理 3 分 | Agent 能否在真实返修场景中被正确触发，作者能否按说明完成一次完整返修。；长稿件、多意见、多轮返修与重复运行下能否持续产出可用结果。；对意见互相冲突、意见本身有误、稿件缺章节、无法补实验、版本不匹配、权限不足等情况的识别与处置能力。 |
| 生态贡献 | 10 分 | 文档完整性 3 分；资源可复用性 4 分；分享推广价值 3 分 | 使用说明、输入模板、依赖、示例、边界与维护信息是否齐全。；题集、意见分类法、回复信模板、定位脚手架与评分表能否被他人直接复用。；是否沉淀可分享的返修案例、意见分类经验与真实应用价值。 |

本固定案例是组织方提供基线与意见摘要的受控修订演练。materials/manuscript-baseline.md 是组织方基线摘要，materials/reviewer-comments.md 是组织方整理的意见摘要，不是完整原稿或审稿报告逐字全文。只修订这个指定基线，逐条处理实际给出的意见，交付可编辑修订稿、回复信草案、修改定位和未到位证据清单。公开论文/报告链接是来源身份，不表示已联网核验原评审全文。不得冒称真实审稿人逐字要求、真实补做实验、原作者已改稿、编辑部已接收或整篇全文返修完成。意见摘要中的实质性修改仍须真实落在本演练的指定基线中；不能仅声明缺材料后跳过可执行修改。
以上输入同时提供给基础Agent与Skill Agent；原公开评分分项及分档保持，缺失、部分完成和有效低分不冒充满分或完整原研究复现。

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
