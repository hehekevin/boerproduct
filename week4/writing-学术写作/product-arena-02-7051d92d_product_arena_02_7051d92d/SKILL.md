---
name: academic-language-polisher
description: "Academic language polishing skill for scientific manuscripts. Performs sentence-level minimal editing of academic texts (journal papers, theses, grant proposals, reviewer responses, English abstracts, Chinese-to-English drafts) to fix grammar, syntax, terminology consistency, and register issues, while strictly preserving hedging strength, data, units, citation numbers, and figure references. Produces a polished full text plus a sentence-by-sentence revision log with edit type tags and reasons, and a structured result.json. Trigger when the user asks to polish, proofread, refine, edit, or improve academic writing, or when a manuscript is submitted with polishing intent. Do NOT trigger for pure content questions, fact lookups, or summarization requests that do not ask for text improvement."
---


## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 6 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

1. 第0步先落盘骨架：读完 /input/case.json 与题面后，第一个写盘动作就是在 /app/output/result.json 写入骨架：case_id 取自 case.json；键名严格按 case.json 或 task.md 中 output_contract 声明的每个字段生成（当前无法完成的字段值填 unknown 或空数组，绝不省略键）；status 填运行时约定的部分完成值。此后任何时刻 /app/output/result.json 必须存在且 JSON 可解析。
2. 字段一个不缺：最终 result.json 必须包含 output_contract 的全部键。某项确实无法产出时，保留键并填 unknown、空数组或说明字符串，同时把原因写入 uncertainty/说明字段，不得删除键、不得编造数据。
3. 广度优先：先让全部要求的产物以最小合格版本存在，再对高价值部分加深。禁止在单一产物上耗尽预算。
4. 预算保护：模型请求已用超过 48 次或运行时间超过 700 秒时，立即停止新增处理，用现有中间结果完成 result.json 并收尾。每次写 result.json 都覆盖为当前最新完整状态。
5. 最终写盘前自检：JSON 可解析、output_contract 字段一个不缺、case_id 与输入一致、status 如实。自检不过先修复再交付。
6. 失败也要交付：处理中断或失败时，仍写 result.json（status 用题面约定的失败值，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。



# 学术语言润色 Skill

## 1. 用途

对学术文本执行分句级最小编辑润色，产出三类结果：

1. 润色后的完整文本（保持原文结构与段落划分）。
2. 逐句修改说明（原文、改文、修改类型标签、理由）。
3. 结构化 result.json（含 case_id、状态、修改记录、术语表、人工确认项）。

核心设计原则是最小编辑：只改必须改的，每处修改可追溯、可否决。守护四条底线：改得对（真正消除语法句法硬错误）、说得像（符合目标语域且术语全篇统一）、没改坏（限定强度、数据、单位、引用编号、图表指向原样保留）、讲得清（每处修改有据可查）。

## 2. 适用条件

适用：期刊论文、学位论文、基金申请书、审稿回复、英文摘要的英文或中文学术文本；中译英稿件的表达质量修正；术语一致性整理；语法与语域修正。

不适用（应拒绝或转说明）：纯内容问答、事实查询、文献综述撰写、数据造假请求、整段重写要求（应向用户说明最小编辑原则后按句子级处理）、要求加强或削弱论文结论的请求（必须拒绝并说明语义保持约束）。

## 3. 触发判断

满足以下任一条件则触发润色流程：用户明确使用润色、校对、修改语言、语法检查、术语统一、中译英润色等指令；输入为完整或成段学术文本且任务描述要求改进表达。

以下情况不触发改写，仅回答问题：用户在提问（这段讲了什么、这个术语什么意思）；用户要求摘要或翻译之外的评价。拿不准时询问用户一句：需要润色输出还是仅解答疑问。

## 4. 输入约定

运行时读取 /input/case.json 与 task.md。case.json 中的关键字段：案例材料（待润色文本）、output_contract（结果字段约定）、目标文体与语言（若有）。所有输出写入 /app/output/。

对输入做三项预处理检查：

1. 编码检查：发现乱码或替换字符时，保留原样并在人工确认项中标注，不猜测修复。
2. 文体判断：case.json 未指定目标文体时，默认按期刊论文体处理并在结果中注明该默认假设。
3. 术语表：case.json 提供术语表则加载为基线；未提供则在流程内新建。

## 5. 工作流程

预算为 64 次模型请求、900 秒，流程按 6 步执行，正常消耗 8 次以内请求。

### 第 1 步：解析输入与建表（1 次请求）

通读全文一次，产出：文体判定、语言方向（中文润色或中译英）、章节结构清单、术语表初稿。术语表按 resources/glossary-template.md 建立，逐条记录：术语原文写法、统一写法、缩写全称展开、首次出现位置、同义变体（如 "deep learning" 与 "DL"）。缩写规则：首次出现给全称加缩写，其后统一用缩写。

### 第 2 步：长文分段（不消耗请求）

超过约 1200 词或 2000 字时按章节切分为多个片段，每段 600 至 900 词。术语表在分段间作为共享状态传递。每段独立处理但回扫阶段全局统一。

### 第 3 步：分句级最小编辑（每段 1 次请求）

对每个句子执行最小编辑，逐句记录修改。编辑优先级从高到低：

1. 硬错误：主谓一致、时态、冠词、介词、单复数、悬垂修饰、拼写、标点。这类必须改。
2. 术语一致性：对照术语表统一同一概念的写法，处理同义混用与缩写漂移。
3. 语域修正：消除口语化（a lot of 改 many 或 numerous）、绝对化（prove 在非数学语境改为 demonstrate 或 provide evidence that）、宣传化与人称误用（期刊论文慎用 we believe，改 the results suggest）。
4. 简洁化：删除冗余名词化与重复连接词，仅当不损失信息时执行。
5. 中译英直译腔：调整主语与信息重心，按 resources/style-rules.md 对应语域规则执行。

禁止动作：不得改变句子承载的信息；不得增删限定词强度（见第 4 步守恒表）；不得改动数字、单位、引用编号（如 [12]）、图表指向（如 Figure 3、Table 1）、公式、变量名、专有名词大小写约定。引用编号与图表指向若原文疑似有误，保持原样并记入人工确认项，不擅自修正。

每处修改登记到修改说明表，字段与标签见 resources/revision-log-template.md。修改类型标签受控词表：grammar、syntax、punctuation、spelling、terminology、consistency、register、conciseness、chinese-english。

### 第 4 步：限定强度守恒检查（与第 3 步同请求内完成）

对每个被修改的句子，按 resources/semantic-preservation-checklist.md 的限定强度等级表核对：修改前后句子的强度等级必须处于同一档。等级表（从弱到强）：第 1 档 may、might、could、possibly、perhaps；第 2 档 suggest、indicate（弱用）、appear to、tend to、likely；第 3 档 show、demonstrate、confirm、is associated with；第 4 档 prove、establish、ensure、unambiguously。

规则：同档内可换词（may 换 might）；跨档升级或降级一律禁止，若不改就存在硬错误才允许跨档，且必须标记 manual_review 为 true 并在理由中写明冲突。同时核对：否定范围未移位、条件句未被改写为陈述句、因果与相关表述未被互换、量词（all、some、few、most）未变。

### 第 5 步：全篇一致性回扫（1 次请求）

全部段落处理完后，以术语表为索引做一次全局回扫：同一概念的多种写法是否已统一；缩写是否首次出现展开、后文统一；章节之间术语是否漂移；修改说明表中的 revised 文本拼回全文后是否连贯。发现残留不一致则做最小修正并补充记录。

### 第 6 步：回读校验与输出（1 次请求）

将润色全文与原文逐段对照回读一遍，验证：段落数与结构一致；修改说明表可逐条在全文中定位原文与改文；无遗漏的硬错误；数字、单位、引用编号、图表指向集合与原文完全一致（集合比对）。校验通过后写出 /app/output/ 下的润色全文文件、修改说明表文件与 result.json（字段见 resources/result-template.json）。若 output_contract 另有约定字段，以 output_contract 为准补齐。

## 6. 输出约定

/app/output/ 至少包含三个文件：

1. polished_text.md：润色后完整文本，保留原章节标题与段落结构。
2. revision_log.md：逐句修改说明，按 resources/revision-log-template.md 格式，含统计（每类修改条数、总修改句数占比）。
3. result.json：结构化结果，字段包括 case_id、status（success 或 partial）、polished_text、revision_log（条目数组）、glossary、manual_review_items、uncertainty、stats。partial 时在 uncertainty 中写明未覆盖范围与原因。

事实与来源映射要求：数字、术语、引用、图表在 result.json 的 evidence 字段中逐条回溯到原文位置，不新增材料外事实。

## 7. 异常处理

| 异常 | 处置 |
| --- | --- |
| 输入超长（全文超过 6000 词） | 按第 2 步切分为多段处理，逐步写出中间结果，避免单次响应超 token 限制；在 stats 中记录分段数 |
| 编码混乱或乱码 | 不猜测修复，保留原样，写入 manual_review_items，status 置 partial |
| 公式、LaTeX、代码混杂 | 公式与代码块整体视为不可编辑单元原样保留，只处理周边自然语言 |
| 引用编号与图表指向疑似错误 | 保持原样，写入 manual_review_items |
| 术语表内部冲突（同一术语两种规定写法） | 采用文中出现频次高的写法，冲突记入 manual_review_items |
| 目标文体不明 | 默认期刊论文体并在 uncertainty 中注明；若用户在场则先询问 |
| 中英日多语混排 | 仅处理任务目标语言的句子，其他语言句子原样保留并记录 |
| 请求预算或时间接近上限 | 立即写出已完成的段落到 /app/output/，status 置 partial，uncertainty 说明剩余未处理段落 |
| 空输入或无文本材料 | status 置 partial，uncertainty 写明输入缺失，不编造内容 |

重复运行同一输入必须收敛：术语表建立规则、修改标签、守恒表均为确定性规则，同一输入重复润色的结果差异仅允许出现在标注理由的措辞上，不允许修改集合漂移。

## 8. 自检清单

输出前逐项确认：

1. 润色后全文段落与章节结构和原文一致。
2. 每处修改在修改说明表中有原文、改文、类型标签、理由四项。
3. 所有硬错误已被修正而非改写掩盖（换同义说法不算修正）。
4. 术语表中每个术语在全文中写法唯一，缩写首次出现已展开。
5. 每个被修改句子的限定强度档位前后一致。
6. 数字、单位、引用编号、图表指向集合与原文完全一致。
7. 无新增材料外事实。
8. result.json 含 case_id 与 output_contract 要求的全部字段。
9. 状态与不确定性如实标注，无 fabricated 内容。
10. 人工确认项清单完整（疑似引用错误、术语表冲突、编码问题等）。
