# 学术语言润色 Skill 使用说明

本 Skill 面向科研学术文本的语言润色：在最小编辑原则下修正语法、句法、术语一致性与语域问题，产出润色后完整文本、逐句修改说明与结构化 result.json，同时严格保持原文的限定强度、数据、单位、引用编号与图表指向。

## 目录结构

```
submission/
  SKILL.md                                 Skill 主文件（Agent 加载入口）
  resources/
    glossary-template.md                   术语表模板与建立规则
    style-rules.md                         分语域风格规则（期刊论文、学位论文、基金申请书、审稿回复、英文摘要）
    revision-log-template.md               逐句修改说明模板
    result-template.json                   result.json 输出模板
    semantic-preservation-checklist.md     语义保持核查清单（含限定强度守恒表）
  README.md                                本文件
  worklog.md                               开发记录
```

## 适用场景

1. 期刊论文、学位论文、基金申请书、审稿回复、英文摘要的语言润色。
2. 中译英稿件的表达质量修正（直译腔、名词化冗余、信息重心调整）。
3. 长稿术语全篇一致性整理（同义混用、缩写漂移、跨章节不统一）。

不适用：纯内容问答（不触发改写）、要求加强或削弱结论的请求（拒绝，语义保持约束）、整段重写需求（说明最小编辑原则后按句子级处理）。

## 调用方式

平台运行时：Skill 安装于 /skills/weekly-skill，Agent 在 /app/work 工作，读取 /input/case.json 与 task.md，产出写入 /app/output/，含 polished_text.md、revision_log.md、result.json（含 case_id 与 output_contract 全部字段）。

人工会话调用：将待润色文本连同以下信息交给加载了本 Skill 的 Agent 即可，缺失项按默认处理：目标文体（默认期刊论文体）、目标语言、已有术语表（可选）、特殊约束（如期刊词数限制）。

## 工作流程概要

1. 解析输入，建术语表（术语、统一写法、缩写首次展开、同义变体）。
2. 超长文本按章节分段，术语表作为共享状态。
3. 分句级最小编辑，按优先级处理硬错误、术语一致性、语域、简洁化、直译腔；每处修改登记原文、改文、类型标签、理由。
4. 限定强度守恒检查：按四档强度表核对每个被修改句子前后档位一致。
5. 全篇一致性回扫：以术语表为索引统一残留写法。
6. 回读校验：段落结构比对、数字与引用与图表指向集合比对，通过后写出三份产物。

## 输出解释

1. polished_text.md：润色后完整文本，结构与原文一致，可直接继续编辑。
2. revision_log.md：逐句修改表，每条含编号、位置、原文、改文、修改类型（受控词表）、理由、风险、人工确认标记，文末附统计。
3. result.json：结构化结果，含 case_id、status、修改记录、术语表、事实与来源映射（evidence）、人工确认项、不确定性与统计。

人工确认项（manual_review_items）是需要作者核定的内容，例如疑似引用编号错误、术语表冲突、编码异常，Skill 一律保持原样并标注，不擅自修正。

## 最小调用示例

输入（示意）：

> 我们提出一种新型深度学习方法，the experimental datas prove it is much better than other methods，详细见图 3。

调用：向加载本 Skill 的 Agent 发出指令：请按期刊论文体润色以下段落，并给出逐句修改说明。

示意输出，非正式案例结果：

润色文（节选）：We propose a deep learning method. The experimental data demonstrate that it outperforms the compared baselines; see Figure 3.

修改说明（节选）：

| 编号 | 原文 | 改文 | 类型 | 理由 |
| --- | --- | --- | --- | --- |
| R001 | 新型深度学习方法 | a deep learning method | register | 删除宣传化修饰 novel，属语域规则 |
| R002 | the experimental datas | the experimental data | grammar | datas 属不可数名词复数误用，硬错误 |
| R003 | prove it is much better | demonstrate that it outperforms | hedge-preserving via register | prove 属绝对化，demonstrate 同档；much better 口语化，对比范围依原文图表指向，不虚构指标数 |
| R004 | 图 3 | Figure 3 | consistency | 混排图表指向统一为英文格式，编号 3 保持不变 |

以上为示意输出，仅说明接口与格式，非正式案例结果。

## 自查方法

使用者可按以下方式复核输出质量：

1. 抽取润色文与原文中的数字、引用编号、图表指向三个集合，应完全相等。
2. 抽查修改表中任意一条，原文应能在原始输入中逐字找到，改文应能在润色文中逐字找到。
3. 检查术语表中每个术语在全文中的写法是否唯一。
4. 核对 manual_review_items 是否都已得到作者处理。

## 限制与失败处理

1. 极长文本（超过 6000 词）自动分段处理，单段结果先落盘，状态可能为 partial。
2. 编码异常、公式与代码混杂、多语混排按 SKILL.md 第 7 节分支处置，不可编辑单元原样保留。
3. 预算或时间不足时立即写出已完成部分，status 置 partial，uncertainty 说明剩余范围。
4. 重复运行同一输入结论不漂移：术语规则、标签词表与守恒表均为确定性规则。

## 维护信息

规则文件（style-rules.md、semantic-preservation-checklist.md、glossary-template.md）彼此独立，可按学科补充术语条目或增删语域规则而无需改动 SKILL.md 主流程。扩展新语域时在 style-rules.md 增加规则组并在 SKILL.md 第 2 节登记适用条件即可。
