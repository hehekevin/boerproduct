---
name: structured-paper-notes
description: Turns a research paper into a fixed-field structured note where every key claim carries a verifiable evidence anchor (page, section, paragraph, figure or table). Use when the user gives a paper (PDF or text) and asks to summarize it, take reading notes, build a paper card, or answer questions about the paper with citations. Trigger words: 文献总结, 结构化笔记, 论文卡片, 论文阅读笔记, summarize this paper, reading notes. The skill enforces a locate-then-excerpt workflow, separates paper facts from reader judgement, cross-checks numbers against tables, and writes result.json with honest status.
---


## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 6 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

1. 第0步先落盘骨架：读完 /input/case.json 与题面后，第一个写盘动作就是在 /app/output/result.json 写入骨架：case_id 取自 case.json；键名严格按 case.json 或 task.md 中 output_contract 声明的每个字段生成（当前无法完成的字段值填 unknown 或空数组，绝不省略键）；status 填运行时约定的部分完成值。此后任何时刻 /app/output/result.json 必须存在且 JSON 可解析。
2. 字段一个不缺：最终 result.json 必须包含 output_contract 的全部键。某项确实无法产出时，保留键并填 unknown、空数组或说明字符串，同时把原因写入 uncertainty/说明字段，不得删除键、不得编造数据。
3. 广度优先：先让全部要求的产物以最小合格版本存在，再对高价值部分加深。禁止在单一产物上耗尽预算。
4. 预算保护：模型请求已用超过 48 次或运行时间超过 700 秒时，立即停止新增处理，用现有中间结果完成 result.json 并收尾。每次写 result.json 都覆盖为当前最新完整状态。
5. 最终写盘前自检：JSON 可解析、output_contract 字段一个不缺、case_id 与输入一致、status 如实。自检不过先修复再交付。
6. 失败也要交付：处理中断或失败时，仍写 result.json（status 用题面约定的失败值，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。



# 文献总结与结构化笔记 Skill

把一篇真实论文变成一份字段齐备、每条关键结论可回链原文位置、可检索可复用的结构化笔记，同时输出平台要求的 result.json。

## 设计原则（对应评分四问）

1. 对得上：先抽取论文自身章节骨架，再按章节顺序填写，不套通用摘要模板。
2. 留得住：固定字段强制覆盖研究问题、数据、方法条件、主要发现、局限与前提条件。
3. 找得回：先定位后摘录。任何关键结论必须带锚点（页码、章节、段落、图表编号），禁止凭记忆总结。
4. 用得上：笔记为 Markdown，字段名固定，支持多篇合并对比；事实与评价分栏，评价不冒充论文内容。

## 调用方式

- 输入：/input/case.json（案例元信息与 output_contract 字段约定）、task.md、论文原文文件（PDF 或文本）。
- 工作目录：/app/work（中间文件）。
- 输出目录：/app/output/（笔记文件与 result.json）。
- 用户可直接说"给这篇论文做结构化笔记"或"读这篇论文并给出依据"。

## 工作流程（预算内经济执行，约 8 到 12 次模型请求）

### 第 0 步 输入识别与契约确认

1. 读取 case.json 与 task.md。记录 case_id，抄下 output_contract 要求的全部字段名，形成 result.json 必填字段清单。
2. 找到论文文件。判断类型：PDF 有无文字层（抽取首页文字，若为空或乱码走异常分支 A）、文本、扫描件。
3. 记录页数与篇幅。超过 40 页视为超长论文，走异常分支 C。
4. 在 /app/work 写入 plan.md：case_id、论文文件名、章节处理计划。尽早落盘，保证部分结果可留存。

### 第 1 步 章节对齐（骨架先行）

1. 从全文提取章节标题与层级（含 Abstract、Introduction、Methods、Results、Discussion、Conclusion、Limitations、References 等）。
2. 为每个章节记录起始页码，写入 /app/work/skeleton.md，格式：`章节号 | 章节名 | 页码范围`。
3. 后续所有笔记条目按此骨架顺序组织，不重排、不合并论文自身的章节顺序。

### 第 2 步 定位摘录（先定位后摘录）

按以下目标字段，逐章节定位后摘录。每次阅读只针对一类字段，减少往返：

| 目标字段 | 定位对象 | 摘录要求 |
|---|---|---|
| 研究问题 | Abstract 末段、Introduction 末段 | 抄录或紧缩改写，附锚点 |
| 数据 | Data/Experiments 章节 | 数据集名称、规模、来源、划分，逐项附锚点 |
| 方法条件 | Methods 章节 | 方法名、关键超参数、前提假设、实验设置 |
| 主要发现 | Results 章节与主图表 | 数字逐字抄录，禁止四舍五入或凭印象 |
| 局限 | Limitations/Discussion 章节 | 原文明说的局限逐条记录 |
| 结论 | Conclusion/Abstract | 区分结论与推广，附锚点 |

摘录规则：先写锚点再写内容。摘录时原文短语用引号，改写处注明"改写"。每条摘录单独成行，便于复核。

### 第 3 步 字段填写与事实评价分栏

按 templates/note-template.md 填写。硬性规则：

1. 每个字段分两栏：`论文事实`（原文说了什么）与`阅读者评价`（你的判断）。评价栏允许为空，事实栏不允许为空（除非标记未报告）。
2. 事实栏每条必须以锚点开头，锚点格式见 references/evidence-anchor-spec.md。
3. 图表数据：主结果数字优先从表格文字抄录。若图表为纯图片且无文字层数字，标记 `[图表数字不可读]`，不得估算。

### 第 4 步 数字一致性核对通道

1. 摘录 Abstract 与 Conclusion 中出现的所有关键数字（指标、样本量、提升幅度）。
2. 与正文表格中的对应数字逐一比对。
3. 一致：在笔记中标注 `[数字已核对]`。不一致：保留两个数字与各自锚点，标注 `[数字冲突]`，写入不确定性清单。表格中找不到对应数字：标注 `[数字无表格来源]`。
4. 核对结果写入笔记的"数字核对记录"区，供复核。

### 第 5 步 未报告与无法判断清单

逐字段检查并显式写出三类条目：

- `未报告`：论文没有提到该字段（例如未报告数据划分比例）。
- `无法判断`：材料中信息不足以确认（例如图表无数字、公式依赖被截断）。
- `材料冲突`：论文内部说法不一致（例如摘要与正文数字不符）。
禁止把未报告项写成事实，禁止补造数据。

### 第 6 步 输出与自检

1. 在 /app/output/ 写入笔记文件：`notes/case-{case_id}.md`（多篇时按此命名规则追加）。
2. 按 templates/result-json-template.json 生成 /app/output/result.json，包含 case_id、output_contract 全部字段、证据锚点清单、未报告清单、status、不确定性说明、变更记录。
3. 执行 references/self-check-list.md 全部检查项，不通过则就地修正后重新落盘。
4. status 取值：`成功`、`部分完成`（说明缺口与可人工接管位置）、`无法判断`（说明原因）、`失败`（说明失败环节）。诚实标注，不虚报。

## 异常处理分支

- 分支 A 扫描件或无文字层：先尝试用环境内可用 OCR 工具抽取文字；无可用工具则产出仅含元数据与章节占位的笔记，status=部分完成，注明"需要文字层或 OCR 接管"。
- 分支 B 图表为图片：无法读取数字时标注 `[图表数字不可读]`，改用正文文字描述该结论，附正文锚点。
- 分支 C 超长论文（超过 40 页）：按章节分批处理，每批处理 1 至 3 个章节并即时落盘到 work 目录，最后合并。分批间不依赖记忆，靠 skeleton.md 与已落盘摘录衔接。
- 分支 D 双栏 PDF 错序：抽取文字后按行宽与页眉页脚启发式重排；重排不确定时按视觉顺序人工标注存疑，不猜测合并。
- 分支 E 非中文论文：术语保留原文并在括号内给中文对照；关键摘录保留原文，翻译注明"译"。
- 分支 F 加密或权限受限文档：无法读取时直接输出 status=失败，原因写明"文档加密或权限受限"，不伪造内容。
- 分支 G 领域陌生：先从论文中提取术语表（术语、缩写、首次定义位置），再进入字段摘录；不做领域外推与背景补造。
- 分支 H 材料缺失：case.json 声明的材料不存在时，在 result.json 中列出缺失清单，已能完成的部分照常输出，status=部分完成。

## 输入输出约定

- 输入：论文文件（PDF/文本）、case.json、task.md。
- 中间产物：/app/work/plan.md、skeleton.md、excerpts.md（分批摘录）。
- 最终产物：/app/output/notes/case-{case_id}.md、/app/output/result.json。
- 多篇合并：多次运行后可用 templates/compare-template.md 将多篇笔记合并为对比表（字段为行，论文为列）。

## 自检清单（运行结束前逐项确认）

1. result.json 含 case_id 与 output_contract 声明的全部字段，JSON 可解析。
2. 笔记覆盖研究问题、数据、方法条件、主要发现、局限、结论六类字段，缺项在未报告清单中说明。
3. 每条事实栏结论都有锚点；抽查 3 个锚点回原文核对位置正确。
4. 所有数字与原文逐字一致；摘要数字与表格数字已核对并记录。
5. 评价与事实分栏，无评价混入事实栏。
6. 未报告、无法判断、材料冲突三类条目已显式列出。
7. status 如实标注；部分完成时写明缺口与人工接管位置。
8. 产物均在 /app/output/，单文件不超过 500KB。

## 资源文件清单

- templates/note-template.md：结构化笔记模板（固定字段、事实评价双栏、锚点占位）。
- templates/result-json-template.json：result.json 输出模板。
- templates/compare-template.md：多篇笔记合并对比模板。
- references/evidence-anchor-spec.md：证据锚点格式规范。
- references/field-dictionary.md：字段字典（每个字段的定义、来源章节、允许值）。
- references/self-check-list.md：完整自检清单（可独立执行）。
