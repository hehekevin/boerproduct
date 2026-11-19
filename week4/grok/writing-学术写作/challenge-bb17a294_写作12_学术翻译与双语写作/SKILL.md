---
name: academic-translation-bilingual
description: Academic translation / bilingual writing with stable terminology, exact numbers/units, sentence-level alignment, preserved citations/formulas/tables, and academic style; editable bilingual deliverable + terminology/number checks + result.json. Use for the "学术翻译与双语写作" workorder (kind=translation).
---

# 学术翻译与双语写作 skill (translation)

Source-bound academic writing skill. The Agent reads the ACTUAL material and fills
the writing IR (claims+evidence, citations, sections, glossary, revisions, and
domain fields); the engine deterministically validates, builds the editable
deliverable, runs consistency checks, exports and writes result.json. Never add
facts outside the material; never fabricate citations/numbers.

## Focus (rubric)
- 术语稳: one translation per term across abstract/body/captions/appendix, discipline-idiomatic.
- 数字实: numbers/units/magnitude/ranges/years/stat口径 unchanged (no rounding/unit mismatch; 万/亿 vs million/billion).
- 对得齐: source-target sentence/paragraph aligned for bilingual editing; formulas/tables/captions/footnotes/refs preserved.
- 风格: academic register; semantic boundaries kept.

## Scope / trigger
Use when the case asks for 学术翻译与双语写作 (workorder kind=translation). IN: this writing
task + source-binding + editable delivery. OUT: unrelated tracks (data-viz
algorithms, experimental design, PPT software), per the statement.

## Inputs (runtime)
`/input/case.json` (copy case_id; read output_contract/audience/genre/format),
`/input/task.md`, actual materials (docx/pdf/csv/images) + template if provided.
Read files; trust content over labels.

## Workflow (detail: docs/WRITING_WORKFLOW.md)
1. Read & register sources with precise locators.
2. Fill writing IR per `rules/rules_translation.md` (claims+evidence+strength,
   citations, sections, glossary, numbers, revisions, domain fields; uncertainty +
   human_confirm for gaps).
3. `python assemble_write.py --ir writing_ir.json --input /input --out /app/output`
   → validate → build (md+docx / mindmap / benchmark) → consistency checks →
   export (office-renderer, honest fallback) → result.json.
4. Source-preserving edit: edit IR, re-run; keep revisions/change log for rollback.

## Domain rules
See `rules/rules_translation.md`. Key:
- Build a maintainable glossary; lock translations across the whole doc + captions.
- Check numbers/units/percent/sample/time-range/formula symbols; handle CN/EN numeric conventions.
- Produce sentence-level aligned bilingual pairs; preserve non-text elements & citations.
- Run terminology-uniformity + number-consistency checks; flag ambiguities.

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
- [ ] terminology uniform & idiomatic
- [ ] numbers/units exact
- [ ] bilingual aligned; refs/formulas preserved
- [ ] editable bilingual output; checks passed
- [ ] result.json honest (status/sources/uncertainty/change_log); claim_map complete


## Week4 concrete input interface (organizer revision)
平台固定运行 3 个案例，比较不加载 Skill 与加载参赛 Skill 时的实际结果。双方使用相同案例输入、任务要求和可比条件；需要相对比较的评分项使用组织方预先固定的白板。白板是对照结果，不是参赛者答案。

| 评分维度 | 分值 | 评分点及分值 | 考察内容 |
|-|-|-|-|
| 实际效果 | 40 分 | 任务完成度 15 分；结果正确性 15 分；结果完整性 5 分；结果可核验性 5 分 | 是否把给定原文整篇译出、按要求的输出形态（纯译文、双语对照或带修订标记）交付，并且可以直接进入作者的修改流程。；术语、数字、单位、引用、否定与限定条件是否与原文一致，是否存在凭空补写或删改科学判断。；是否覆盖原文章节、图表、公式、脚注与参考文献，以及任务要求的目标语言版本。；能否按句段追溯原文、术语依据、数字与引用核对结果以及人工修改痕迹。 |
| 使用增益 | 25 分 | 质量增益 15 分；效率增益 5 分；增益可验证性 5 分 | 相同原文与条件下加载 Skill、插件或工作流后，相比不加载的基础 Agent 是否稳定提升译文质量与可编辑性。；是否真实减少后编辑工时、术语统一、对照排版、数字与引用核对的人工量。；是否通过公平对照证明质量或效率改善。 |
| 创新增益 | 15 分 | 新增能力 5 分；方法改进 5 分；创新证据 5 分 | 是否形成基础 Agent 或现有方案不具备、或难以稳定实现的翻译与双语写作能力。；术语抽取、分块策略、对齐约束、二次校验、风格控制等方法是否带来实质改进。；是否证明创新点相对已有方案（通用翻译工具、写作00 现有能力等）的边界和价值。 |
| 可靠体验 | 10 分 | 调用与易用性 3 分；运行稳定性 4 分；异常处理 3 分 | Agent 是否能正确触发和调用，用户能否按说明完成一次整篇翻译或双语写作任务。；在不同文体、不同长度、不同语向和重复运行下能否持续产出可用结果。；对公式与表格、术语表冲突、超长文本、语向不支持、引用格式异常、输入编码错误等情况的识别与处置能力。 |
| 生态贡献 | 10 分 | 文档完整性 3 分；资源可复用性 4 分；分享推广价值 3 分 | 使用说明、依赖、配置、示例、适用范围、限制和维护信息是否齐全。；Skill 本体、脚本、术语表、对齐工具、题集和提示模板能否被他人复用。；是否沉淀可分享的真实稿件案例、术语资产、双语写作经验和实际应用价值。 |

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
