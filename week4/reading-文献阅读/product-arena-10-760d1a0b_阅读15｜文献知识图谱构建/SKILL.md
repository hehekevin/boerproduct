---
name: lit-kg-builder
description: Build an evidence-grounded knowledge graph from scientific papers. Extracts typed entities (method, dataset, material, task, metric, result, disease, gene, researcher) and directed relation triples (uses, compares, improves, outperforms, achieves, supports, contradicts) where every triple carries paragraph-level citation and a short original quote. Normalizes aliases and abbreviations with explicit merge justification, keeps different papers as separate sources, annotates conflicts instead of merging them, and executes at least three real graph queries with cited answers. Use when the task asks to build a knowledge graph from papers, extract entities and relations with evidence, align entity aliases across papers, or answer graph queries that must cite the source text. Trigger on inputs such as /input/case.json, corpus-manifest.json, primary-material.json, secondary-material.json, or user requests mentioning knowledge graph, entity relation extraction, triples, or 实体关系抽取/知识图谱.
---

# 文献知识图谱构建 Skill（lit-kg-builder）

## 1. 用途

从一篇或多篇科研论文中构建带证据的知识图谱：

- 实体识别与类型标注：只抽取论文中真实出现的科研对象，保留原文表述。
- 关系抽取：只建立有原文证据支持的有向三元组，每条带段落定位与原文短引。
- 实体规范化与消歧：合并同一对象的不同写法，给出合并依据；跨篇同名默认不合并，冲突显式标注。
- 图谱查询：执行至少 3 个真实查询，结果附证据；无法确定的关系如实标注。
- 结构化输出：nodes.csv、edges.csv、triples.json、result.json（含 output_contract 全部字段与 case_id）。

核心原则：忠实原文，不编造实体、关系和页码。每条三元组没有证据定位就不许存在。

## 2. 适用条件与调用方式

适用：输入为论文全文或段落化文本（JSON 段落索引、Markdown、XML、纯文本均可），任务要求构建图谱、抽取实体关系、对齐别名或做带引用的图谱查询。

触发方式：Agent 读取本 Skill 后按第 3 节流程执行。用户指令中出现"知识图谱""实体关系""三元组""构建图谱"等，或输入目录出现 case.json、corpus-manifest.json、primary-material.json、secondary-material.json 时启用本 Skill。

调用约定：

1. 先读 /input/case.json 与 task.md，确认任务边界和 output_contract 字段。
2. 在 /app/work 下做中间产物，最终产物写入 /app/output/。
3. result.json 必须含 case_id 与 output_contract 要求的全部字段。
4. 预算敏感：整体流程控制在少量模型往返内完成，先写骨架结果再增量补全（契约要求尽早保存诚实的部分结果）。

## 3. 完整工作流程

### 步骤 S1 输入盘点（不耗模型推理，只做文件读取）

- 读取 case.json：提取 case_id、任务说明、output_contract 字段清单。output_contract 是硬约束，逐字段登记到工作清单。
- 读取 corpus-manifest.json（若存在）：登记每篇论文的 paper 标识（分配 source_id：P1、P2，按 manifest 顺序）、DOI、作者、许可证。根 DOI/title/authors 只属于第一篇，严禁套用到第二篇。
- 读取 material.json：获取段落索引（paragraph_id 列表），估计篇幅。
- 若是 PDF 输入：用平台 pdf-text-tool 解析；解析失败走 E1 异常分支。
- 篇幅判断：单篇正文超过约 8000 词或超过 60 个段落时，启用 S3 的分段抽取模式。

### 步骤 S2 建立实体登记表骨架

在 /app/work/entity-registry.json 建空登记表，字段：entity_id（P{编号}-E{两位序号}，论文内唯一且全局不冲突）、mention（原文表面形式）、normalized_name、type、aliases、source_id、evidence 数组（paragraph_id 加 quote）、attribution（self_reported 或 cited_other 或 unclear）、note。登记表是后续所有抽取的唯一事实源，防止重复编号和实体漂移。

### 步骤 S3 逐篇实体抽取（第一遍：只抽实体，不抽关系）

对每篇论文各做一次抽取，输出直接写入登记表：

- 类型必须来自 resources/types.md 的固定体系（method、dataset、material、task、metric、result、disease、gene、researcher、other）。体系外的对象归入 other 并在 note 写明真实类别，禁止强行套用近似类型。
- 每个实体必须至少有一条证据：paragraph_id 加不超过 60 字的原文短引。没有证据的常识性概念一律不抽。
- 区分归属：作者自述（self_reported）与他人转述（cited_other），依据句子主语和引文标记（如 refs、引述句式）判断，判断不了记 unclear。
- 缩写处理：遇到 "全称 (缩写)" 模式，把全称与缩写登记为同一实体的两个 mention，aliases 互相记录。
- 分段抽取模式：按章节分块抽取，每块完成后立即合并进登记表；同一实体再次出现时不新建条目，只在 aliases 和 evidence 中追加 paragraph_id。合并时以首次出现的完整全称为 normalized_name。

### 步骤 S4 逐篇关系抽取（第二遍：基于登记表抽关系）

对每篇论文各做一次抽取。只允许在登记表已有实体之间建边，禁止引入新实体（发现漏抽实体时先补登记再建边）。

- 每条三元组按 resources/triple-spec.md 的 schema 输出，必填：subject、predicate、object、direction、condition、stance、confidence、evidence（source_id、paragraph_id、quote）。
- 谓词类型与方向规则严格遵守 resources/types.md 第 2 节，例如 uses 的方向是使用者指向被用物；outperforms 的方向是优者指向劣者。方向写反的三元组视为错误。
- 证据句判断：
  - 肯定句：stance=affirmed，confidence=high。
  - 否定句（如 not、does not、fails to）：不建肯定三元组；若该否定本身有信息量（原文明确说 A 不使用 B），建一条 stance=negated 的三元组，confidence=high。
  - 比较句（如 outperforms、better than、higher than）：按谓词语义固定方向，direction 一律从优到劣或从主动到被动，并在 condition 记录比较基准与适用条件。
  - 推断或转述（综述句式、跨段推导）：confidence=medium 或 low，并在 note 写明推断理由。纯共现（同段出现但无关系语义）不建边。
- 适用条件：原文带限定语（如在特定数据集上、仅在特定条件下）时，必须写入 condition，不得把条件性结论抽成无条件事实。

### 步骤 S5 实体规范化与跨篇消歧

按 resources/normalization.md 执行，要点：

- 篇内合并：全称与缩写、大小写变体、连字符变体合并为同一 entity_id，合并依据写入 merges 记录。
- 跨篇合并门槛：只有满足显式依据才允许合并，例如第二篇明确引用第一篇并声明是同一对象。相同通用术语（如都叫 transformer、都叫 MRI）不代表相同物理样品、模型实例、数据集或实验条件，默认不合并；确实无法判断时记入 conflicts，注明"跨篇同名，依据不足，保留为独立节点"。
- 合并产生的规范节点使用 M{两位序号} 前缀的 canonical id，members 列出被合并的论文内实体。合并记录必须含 basis（依据）与 evidence。
- 冲突标注：两篇对同一对象给出矛盾结论（如数值、效果方向不一致）时，两条关系都保留，各挂各的 source_id，并在 conflicts 中登记，不得合成一个结论。

### 步骤 S6 图谱查询（至少 3 个，必须真实执行）

在已生成的三元组集合上执行查询并记录到 result.json 的 queries 字段。固定推荐查询（可按案例任务说明替换，但至少 3 个）：

1. Q1 一跳邻域：选一个核心实体（如第一篇的主方法），返回它的全部直接关系及证据。
2. Q2 谓词过滤：如列出所有 predicate=uses 的三元组，按论文分组。
3. Q3 跨篇对照：找出两篇中涉及同类对象或同谓词的三元组，标注哪些可对齐（有合并依据）、哪些不得合并（在 conflicts 中）。
4. Q4（可选）否定与不确定检索：列出 stance=negated 或 confidence=low 的三元组。

每个查询结果必须附 evidence（paragraph_id 加 quote）；查询无结果时如实返回空列表并说明检索范围，不得编造结果。

### 步骤 S7 输出落盘

全部写入 /app/output/：

- nodes.csv：entity_id、normalized_name、type、source_id、aliases、attribution、evidence_paragraph_ids、note。
- edges.csv：triple_id、subject_id、predicate、object_id、direction、condition、stance、confidence、source_id、paragraph_id、quote、note。
- triples.json：三元组完整列表（与 edges.csv 同源，JSON 便于程序复用）。
- merges.json：合并与冲突记录。
- result.json：按 resources/result-template.json 组装，必须含 case_id、output_contract 要求的全部字段、status、sources、uncertainty（unreported 与 limitations）、queries、change_record。
- 先写一份含已抽取内容的 result.json 骨架（status 如实），再做查询和收尾，最后更新为最终状态。防止超时丢失结果。

### 步骤 S8 自检

按 resources/checklist.md 逐项核对，未通过项就地修复；无法修复的写入 limitations 并相应调整 status。至少核对：每条三元组有 paragraph_id 与短引、方向与谓词定义一致、实体类型在体系内、跨篇合并均有依据、result.json 含 case_id 与 output_contract 全部字段、status 诚实、查询至少 3 个且已真实执行。

## 4. 输入输出约定

输入（按存在与否自适应）：

| 文件 | 用途 |
| - | - |
| /input/case.json | case_id、任务说明、output_contract |
| /input/task.md | 题目与约束 |
| /input/corpus-manifest.json | 论文清单：DOI、作者、哈希、许可证 |
| /input/material.json | 两篇正文段落汇总索引 |
| /input/primary-material.json | 第一篇论文原文 |
| /input/secondary-material.json | 第二篇论文原文 |
| 其他论文文本 | 同等处理，按 manifest 分配 source_id |

输出（/app/output/）：nodes.csv、edges.csv、triples.json、merges.json、result.json。

定位约定：paragraph_id 使用材料自带的组织方段落 ID（如 JATS 段落 ID）。本流程不生成也不输出 PDF 页码；若任务说明要求页码而材料不含页码，在 unreported 中说明"材料不含 PDF 页码，仅提供 paragraph_id 定位"。正文行内公式与上下标是线性化文本，引用短引时保持原样，不重排公式。

## 5. 异常处理分支

| 编号 | 情形 | 处置 |
| - | - | - |
| E1 | 论文文件缺失或解析失败 | 不编造内容。status=partial 或 failed，原因写入 limitations；能解析的部分照常产出 |
| E2 | output_contract 缺失或字段不明 | 按本 Skill 默认模板输出全部字段，并在 note 说明 contract 缺失 |
| E3 | 实体类型超出体系 | type=other 加 note，不强行归类 |
| E4 | 论文超长 | S3 分段抽取模式；预算不足时优先保证实体登记表完整和核心关系（uses、achieves、outperforms、supports、contradicts），其余记入 limitations，status=partial |
| E5 | 否定句与比较句 | 按 S4 规则处理方向与 stance；拿不准时 confidence=low 并在 note 说明 |
| E6 | 跨篇同名实体 | 默认不合并，进 conflicts；只有显式依据才合并 |
| E7 | 同篇内两处证据冲突 | 两条都保留，标注冲突于 conflicts，不择一删除 |
| E8 | 查询无结果 | 返回空结果加检索范围说明 |
| E9 | 材料为扫描件或图像 | 本 Skill 不做 OCR 内容推断；如平台有 ocr-tool 可调用后按正常流程处理，否则 status=failed 并说明 |
| E10 | 预算临近耗尽 | 立即落盘已完成的 result.json（status 如实标注 partial），放弃未开始的步骤 |

## 6. 增量更新约定

新论文加入时：既有 entity_id 与编号不变；新论文按下一个 P 编号抽取；候选合并走 S5 门槛并追加 merges 记录；新冲突追加 conflicts；result.json 的 change_record 中追加一条变更记录（时间、动作、影响范围）。

## 7. 资源文件

- resources/types.md：实体与关系类型体系（可配置扩展，供其他学科复用）。
- resources/triple-spec.md：三元组 schema、证据定位与置信度规范。
- resources/normalization.md：实体规范化与消歧规则。
- resources/result-template.json：result.json 模板。
- resources/checklist.md：交付前自检清单。

## 8. 自检清单（摘要，完整版见 resources/checklist.md）

1. 每条三元组：有 source_id、paragraph_id、原文短引；方向与谓词定义一致。
2. 每个实体：真实出现在原文；类型在体系内或 other 加 note。
3. 合并：均有 basis 与 evidence；冲突未合并且已标注。
4. result.json：含 case_id 与 output_contract 全部字段；status 诚实；至少 3 个已执行查询。
5. 未把自建编号当成 PDF 页码；未把共现或转述当直接证据；未把两篇的条件、样本或数值合成一个结论。
