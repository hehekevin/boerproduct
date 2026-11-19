---
name: academic-talk-content-organization
description: Organize existing research material into a speakable, audience- and time-aware academic talk — checkable report goal, audience adaptation, narrative order, one key message per page with evidence strength, speaker notes, and Q&A prep with citable backup pages; delivers source-bound editable PPTX plus rendered PDF/PNG previews and a verifiable result.json. Use when the task asks to organize report content / narrative / audience targeting / Q&A preparation rather than merely typeset slides.
---

# Academic talk content organization skill

From existing material to a **speakable** deck: goal, audience, narrative order,
per-page key message and Q&A prep form a closed loop — not a section-by-section
compression of the paper. Adds: goal/audience-driven planning, narrative backbone
with evidence-strength tagging, one-claim-per-page compression, Q&A backup pages,
source-bound page map, template inheritance and render check.

## Scope
- IN: report goal, audience, narrative order, key information, Q&A prep; from已有
  content to speakable pages + delivery.
- OUT: paper deep-read, academic writing polish, figure material production.

## Trigger
Use when the case asks to organize academic report content / narrative / audience /
Q&A (workorder `content_organization`).

## Inputs (runtime)
`/input/case.json` (copy `case_id`; read `output_contract`, audience/duration/
slide_count), `/input/task.md`, actual material + provided template if present.
Read files; trust content over labels.

## Workflow (detail: docs/DECK_WORKFLOW.md)
1. **Read & register sources** with locators.
2. **Plan & fill Deck IR** (`rules/rules_content_org.md`):
   - checkable `goal`; `audience` (prior knowledge/concerns/challenges) driving
     background depth & terminology; `duration_min`, `slide_count_target`;
   - narrative backbone with 起承转合 (not paper TOC); one `claim`/page +
     evidence + figure; `evidence_strength` tagged;
   - `notes` = what to SAY (match claim, not repeat bullets);
   - `qa[]`: anticipated mechanism/data/control/limitation questions, answer_points,
     citable `backup_page`, consistent口径;
   - `uncertainty[]` for gaps (no fabrication).
3. **Validate+build+check+render+result**:
   `python assemble_deck.py --ir deck_ir.json --input /input --out /app/output [--template ...]`
   (template inheritance, notes, footer/page numbers, overflow/font guards,
   office-renderer true PDF/PNG or labelled fallback).
4. **Local edit & version:** edit IR, re-run; `provenance.changes[]` for rollback.
5. **result.json**: every `output_contract` field + `case_id`, honest `status`,
   `sources`, `provenance.page_map`, `uncertainty`, `change_log`, `deck_check`,
   `export_check`.

## Scripts & dependencies
`assemble_deck.py`, `deckkit.py`, `build_deck.py` (python-pptx), `check_deck.py`,
`export_deck.py`, `figkit.py`, `render_chart.py`.
Deps: Python 3.10+, python-pptx, matplotlib, numpy, Pillow; office-renderer for true
render. CJK auto-fallback.

## Outputs (/app/output)
`deck.pptx`, `deck.pdf` + `slide-*.png`, `deck_ir.json`, `provenance.json`,
`validation.json`, `deck_check.json`, `export_report.json`, `result.json`.

## Error handling (docs/ERROR_HANDLING.md + DECK_WORKFLOW §4)
Missing figure/number → cite or flag; audience/time conflict → rebalance pages and
record; template gap → fallback; font missing → CJK fallback; overflow → cut/split;
export failure → honest fallback + partial. Save partial early.

## Minimal example (SYNTHETIC — interface demo, not a formal answer)
`examples/deck/`: a 6-slide committee talk with goal/audience, per-page claims,
notes and Q&A backup. Run:
`python assemble_deck.py --ir examples/deck/deck_ir.json --input examples/deck/input --out /tmp/demo`
Interface demonstration only.

## Self-check
goal+audience+narrative+key message+Q&A closed loop; order serves audience/time;
one claim/page + evidence strength; notes correspond; Q&A backup citable; numbers/
refs match source; template inherited; export clean; page_map + change log complete.

## Week4 concrete input interface (organizer revision)
| 评分维度 | 分值 | 评分点及分值 | 考察内容 |
|-|-|-|-|
| 实际效果 | 40 分 | 任务完成度 15 分；结果正确性 15 分；结果完整性 5 分；结果可核验性 5 分 | \*\* 评价是否真正交付一份可直接上台的汇报材料：报告目标、听众定位、叙事顺序、逐页重点信息与问答准备是否形成闭环。**；** 评价页面上的科学内容、数字与图表引用是否与源材料一致，讲解备注是否与页面结论对应，结论强度是否与证据匹配。**；** 评价是否覆盖论文主线、页结构、图表引用、讲解逻辑、模板约束、导出渲染六个方面。**；** 评价从源材料到成稿的取舍、页级映射、导出链路能否被独立复核。\*\* |
| 使用增益 | 25 分 | 质量增益 15 分；效率增益 5 分；增益可验证性 5 分 | \*\* 评价相同输入、相同听众与时长设定下，加载作品后相比基础 Agent 是否提升汇报内容组织质量。**；** 评价是否减少从论文到可讲稿的人工修改量、返工页数与导出修正次数。**；** 评价是否通过公平对照证明质量或效率改善。\*\* |
| 创新增益 | 15 分 | 新增能力 5 分；方法改进 5 分；创新证据 5 分 | \*\* 评价是否形成基础 Agent 或现有方案不具备、或难以稳定实现的听众适配、页级规划与问答预演能力。**；** 评价叙事模板、内容取舍规则、图表引用绑定、模板约束与导出处理等方法是否带来实质改进。**；** 评价是否证明创新点相对已有方案的边界和价值。\*\* |
| 可靠体验 | 10 分 | 调用与易用性 3 分；运行稳定性 4 分；异常处理 3 分 | \*\* 评价 Agent 是否能在合适时机触发，用户能否按说明完成一次从源材料到导出文件的完整生成。**；** 评价在不同汇报类型、不同源材料长度与重复运行下能否持续产出可用页面。**；** 评价对论文缺图、图表分辨率不足、公式或符号丢失、模板与内容冲突、字体缺失、导出失败、超时等情况的识别与处置能力。\*\* |
| 生态贡献 | 10 分 | 文档完整性 3 分；资源可复用性 4 分；分享推广价值 3 分 | \*\* 评价使用说明、依赖、模板、导出设置、示例、适用范围与维护信息是否齐全。**；** 评价题集、页级金标准、叙事模板、模板文件、导出脚本等资源能否被他人复用。**；** 评价是否沉淀可分享的汇报案例、页级组织方法、问答准备经验与真实应用价值。\*\* |

Concrete editable presentation task
Concrete organizer-frozen slide task: actual master/layout-based editable template, actual starting deck where edit/adapt requires one, fixed audience/time/slide count and full-source/uncertainty rules. Original16rubric/scientific material unchanged. Technical file checks do not certify presentation science or quality.

Read the ACTUAL organizer workorder/material files named above from /input before filling the IR; trust file content over domain labels. Emit per-requested-field/claim results with exact source locators and the required status vocabulary (reported/not_reported/source_conflict/extraction_failed/insufficient_evidence). Do not fabricate missing objects; mark gaps human_confirm.

## GitHub bonus (+5)
This package includes GITHUB_URL.txt at its root: line 1 is the public GitHub tree URL of this work, line 2 the relative entry file (SKILL.md). The link is published under week4/grok in github.com/hehekevin/boerproduct and opens without login.
