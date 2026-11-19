---
name: citation-consistency-audit
description: "Reference and citation management skill for academic manuscripts. Use when the task requires extracting in-text citations, checking citation-to-reference-list consistency, deduplicating repeated entries, renumbering citations, normalizing formats (BibTeX, GB/T 7714-2015, APA 7), completing or grading metadata completeness, and marking unverifiable entries. Trigger whenever the input includes a manuscript (text/Markdown/LaTeX/Office/PDF text) plus a reference library or embedded reference list, and the requested output is a cleaned manuscript, a synchronized reference list, or a structured citation audit result.json. Trigger on Chinese keywords such as 参考文献, 引用, 引文, 文献表, 去重, 编号, 格式规范."
---


## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 6 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

1. 第0步先落盘骨架：读完 /input/case.json 与题面后，第一个写盘动作就是在 /app/output/result.json 写入骨架：case_id 取自 case.json；键名严格按 case.json 或 task.md 中 output_contract 声明的每个字段生成（当前无法完成的字段值填 unknown 或空数组，绝不省略键）；status 填运行时约定的部分完成值。此后任何时刻 /app/output/result.json 必须存在且 JSON 可解析。
2. 字段一个不缺：最终 result.json 必须包含 output_contract 的全部键。某项确实无法产出时，保留键并填 unknown、空数组或说明字符串，同时把原因写入 uncertainty/说明字段，不得删除键、不得编造数据。
3. 广度优先：先让全部要求的产物以最小合格版本存在，再对高价值部分加深。禁止在单一产物上耗尽预算。
4. 预算保护：模型请求已用超过 48 次或运行时间超过 700 秒时，立即停止新增处理，用现有中间结果完成 result.json 并收尾。每次写 result.json 都覆盖为当前最新完整状态。
5. 最终写盘前自检：JSON 可解析、output_contract 字段一个不缺、case_id 与输入一致、status 如实。自检不过先修复再交付。
6. 失败也要交付：处理中断或失败时，仍写 result.json（status 用题面约定的失败值，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。



# 参考文献与引用管理 Skill

本 Skill 面向学术稿件中的引用整理任务，提供从引用抽取、一致性校验、去重归并、编号重排到格式规范化的完整流水线，并以结构化 result.json 交付可核验结果。核心设计是所有结论都基于一个可回溯的引用-条目双向映射矩阵，而不是凭印象核对。

## 一、用途与定位

解决四类高频问题：
1. 挂得对：判定每处正文引用是否落在真正需要来源支撑的句子位置，标注可疑的段末堆砌引用。
2. 编得顺：顺序编码制下保证正文编号与文末列表同步、连续、按首次出现顺序排列；著者-出版年制下保证年份与列表条目一致。
3. 收得净：识别同一文献的重复条目（中英题名、预印本与正式版、不同数据库导出），按可解释判据归并。
4. 对得上：逐条校验引用与文献条目的元数据匹配，分级标注元数据完整性与可核实性，无法核实的条目诚实标注而非编造。

本 Skill 不做正文润色、不做翻译、不自行补充材料之外的新文献。发现"缺引用的论断句"只做提示，不代为虚构来源。

## 二、适用条件

- 输入包含：稿件正文（可提取文本）+ 文献信息源（文末参考文献列表、独立文献库文件如 .bib/.ris/CSV，或两者皆有）。
- 目标格式已知（GB/T 7714-2015、APA 7、BibTeX 等）或在任务说明中可推断；无法推断时按异常分支处理。
- 运行环境约束：预算 64 次模型请求、900 秒、单响应 16384 tokens。本流程固定为 6 个阶段，正常情况下 8 到 14 次模型请求即可完成，超长稿件按分块规则处理。

## 三、调用方式

Agent 加载本 Skill 后，按第四节流程执行。资源文件位于本 Skill 目录的 references/ 下：
- references/workflow-checklists.md：各阶段核查清单与异常分支详表。
- references/format-mapping.md：BibTeX/RIS/CNKI/EndNote 字段到 GB/T 7714-2015、APA 7、BibTeX 输出的映射表。
- references/dedup-rules.md：去重合并判据与误合并防护。
- references/result-json-template.md：result.json 字段模板与填写规范。
- references/common-errors.md：常见错误清单与预防方法。

## 四、完整工作流程

### 阶段 0：读取任务契约（1 次请求）

1. 读取 /input/case.json 与 task.md。提取：case_id、任务说明、目标格式（若 output_contract 或任务说明指定）、output_contract 要求的全部字段、可用材料路径。
2. 必须读取实际材料文件内容，不依据文件名或标签假设内容。PDF 用平台提供的 pdf-text-tool 提取文本。
3. 在 /app/work/ 下建立工作记录 audit_state.md，先写入 case_id、目标格式、材料清单。此后所有中间结论追加到该文件，避免重复读大文件。
4. 若 case.json 缺失或无 output_contract：按第五节的默认输出契约执行并在 status 中说明。

### 阶段 1：抽取与结构化（2 到 4 次请求）

一次性完成两类抽取，输出写入 audit_state.md：

A. 正文引用点清单。逐段扫描稿件，每条记录：引用标记原文（如 [3]、[1,5-7]、(Wang et al., 2020)、上标形式）、所在位置锚点（章节号 + 段落序号 + 行号或引文句子原文片段，锚点必须能让人在原稿中定位）、所属句子的完整原文（用于判定挂靠位置是否合理）、是否上标、是否位于段末或图表注附近。

B. 文献条目清单。解析文末列表或文献库，每条记录：原始编号或键、作者、年份、题名、来源（期刊/会议/出版社）、卷期页、DOI 或其他标识符、文献类型、原始格式串全文。字段缺失时如实记 null，不猜测。

分块规则：稿件超过约 8000 字时按章节分块抽取，每块一次请求，最后合并去重。抽取务必穷尽：全部章节、图表注、附录都要扫到，漏扫是最大扣分来源。

### 阶段 2：去重归并（1 到 2 次请求）

按 references/dedup-rules.md 的判据处理：
1. 主判据依次为 DOI 相同、标识符相同、作者+年份+题名高相似。题名相似度用规范化后比对（去标点、统一大小写、中英题名互译情况人工判据处理）。
2. 预印本与正式版并存时保留正式版，合并记录中写明依据（如 arXiv ID 对应的 DOI 正式版）。
3. 每次合并必须写：保留条目、被并条目、判据、风险等级。同名作者的不同文献、同题名不同年份一律不合并，列为待人工确认。
4. 合并后重新编号映射（旧键到新键），后续阶段一律使用新键。

### 阶段 3：双向一致性校验（1 到 2 次请求）

构建引用-条目双向映射矩阵，这是本 Skill 的核心产物，写入 audit_state.md：

矩阵行 = 正文引用点（按出现顺序），列 = 文献条目，单元格 = 该引用点与该条目的匹配状态。据此产出三个清单：

1. 孤儿引用：正文有引用标记但文献列表无对应条目。给出标记原文与锚点。
2. 未引用条目：列表有条目但正文从未引用。核对图表注与附录后再判定。
3. 编号问题清单（顺序编码制）：编号不连续、首次出现顺序与列表顺序不一致、同一编号指向不同条目、上标与非上标混用、交叉引用缺失。按 references/workflow-checklists.md 的编号校验清单逐项过。
4. 挂靠位置审查：对每个引用点判定其所属句子是否为需要来源支撑的论断（含数据、方法出处、他人结论的句子）。段末堆砌、图表注旁孤立引用标记为"位置可疑"，给出建议位置。

### 阶段 4：元数据分级与核验（1 到 2 次请求）

对每个去重后的条目做三级分级：
- 完整：作者、年份、题名、来源、卷期页、类型齐备，DOI 或标识符存在且格式合法（DOI 用 10.xxxx/ 形式正则校验）。
- 可疑：字段互相矛盾（如年份与卷期不符）、题名疑似截断、DOI 格式非法、作者拼写异常。
- 缺失：关键字段为 null。

核验策略：优先使用案例材料内的证据（文献库原文、稿件中的对应信息）交叉核对；环境具备网络工具时用 DOI 反查元数据，仅当成功返回时才标记"已核实"，并记录核对到的字段；无网络或查询失败一律标记"未核实"，绝不在 result.json 中声称已核实。未核实但格式合法的 DOI 标注"DOI 存在性未核实"。
产出"需人工确认清单"：全部可疑与缺失条目、去重中的风险合并、位置可疑引用、材料内无法解决的孤儿引用。

### 阶段 5：格式规范化与修订稿生成（2 到 3 次请求）

1. 按 references/format-mapping.md 将去重后条目转换为目标格式。转换规则逐字段执行，保留 DOI、卷期页、文献类型标识；中文条目与英文条目按目标规范分别处理标点。
2. 生成修订稿：在原稿基础上修正引用标记（编号重排、去重后合并引用如 [1,2] 合并后重写）、同步文末列表。修订稿为可编辑文本（Markdown 或与原稿同构的格式），所有改动用行内标记或与 change_records 对应的编号标注。
3. 生成 audit_report.md：包含双向矩阵摘要、三清单（孤儿、未引用、编号问题）、元数据分级表、需人工确认清单、change_records（每条改动：位置锚点、改动前、改动后、依据）。
4. 目标格式未指定时的降级策略：保持原稿既有格式并只做一致性修复，在 result.json 中说明。

### 阶段 6：写出结果与自检（1 次请求）

1. 写出 /app/output/ 下文件：result.json（按 references/result-json-template.md，必须含 case_id 与 output_contract 要求的全部字段）、修订稿、references_final（目标格式文献表）、audit_report.md。
2. status 取值：complete（全链路完成）、partial（有阶段未完成或大量待人工确认项，必须在 limits 字段写明未完成范围）、failed（连材料都无法读取，也要写 result.json 说明原因）。
3. 执行 references/workflow-checklists.md 末尾的自检清单，逐项确认后把结果写入 result.json 的 self_check 字段。

预算控制要点：每个阶段一次成型，避免来回修改大文件；中间状态集中写 audit_state.md；抽取阶段宁可单响应内容偏长也不要拆成碎片请求。

## 五、输入输出约定

输入（来自 /input/）：
- case.json：案例说明、材料路径、output_contract 字段约定。
- 稿件与文献库：任意可提取文本格式；PDF 走平台 pdf-text-tool；.bib/.ris/CSV 直接文本解析。

输出（写入 /app/output/）：
- result.json：必含 case_id、status、output_contract 全部字段，以及 task_type、deliverables（产物文件路径清单）、citation_matrix_summary、orphan_citations、uncited_entries、numbering_issues、metadata_grades、dedup_records、manual_review_list、change_records、sources（证据定位）、uncertainty、limits、self_check。
- manuscript_revised.*：修订后可继续编辑的稿件。
- references_final.*：目标格式的同步文献表（如 references_final.bib 或 .md）。
- audit_report.md：人类可读的核对报告。

证据定位规范：所有 sources 字段使用"文件名 + 章节 + 段落序号 + 行号或原文片段"三层锚点，原文片段必须逐字摘自材料，不得改写。

## 六、异常处理分支

按 references/workflow-checklists.md 第二节详表执行，要点：
1. 稿件缺失或无法解析：status=failed，result.json 写明缺失对象与已尝试的解析方式，不编造。
2. 文献库缺失：只做正文引用抽取与编号校验，元数据分级标记"无文献库可比对"，uncertainty 说明。
3. 引用信息不全（如正文只有编号但列表无编号）：把编号当作待匹配键，列入 manual_review_list，不猜测对应关系。
4. 重复条目判据冲突（部分字段匹配部分冲突）：不合并，双条目保留并标记风险，写入人工确认清单。
5. 目标格式不明：按原稿格式做一致性修复，limits 中说明。
6. 材料超预算：优先完成抽取与校验并先写 partial 的 result.json（尽早保存诚实部分结果），再增量补充格式化产物。
7. 同名作者或同题名文献：默认不合并。中文作者姓名歧义（如同拼音不同人）标记待确认。
8. 编号冲突（如两个 [3]）：以首次出现顺序重排为准，原冲突写入 numbering_issues 留痕。

## 七、自检清单

写 result.json 前逐项确认：
1. result.json 含 case_id 且为实际案例 ID，含 output_contract 要求的全部字段，JSON 语法合法。
2. 抽取覆盖全部章节、图表注、附录；引用点总数与文献条目总数都有明确数字。
3. 三个清单（孤儿引用、未引用条目、编号问题）非空时每条都有锚点。
4. 所有"已核实"声明都有对应证据记录；核实不了的都标"未核实"。
5. 去重合并每条都有判据；未合并的可疑对都在人工确认清单中。
6. 修订稿中引用标记与 references_final 的序号一一对应，可继续编辑。
7. change_records 覆盖全部实际改动；未确认项全部标注而非静默处理。
8. status 与实际完成度一致；partial 时 limits 明确写出未完成内容。
