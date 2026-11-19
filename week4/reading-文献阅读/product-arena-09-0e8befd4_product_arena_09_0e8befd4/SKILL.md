---
name: nanopub-assertion-extractor
description: >
  Extract scientific assertions from a research paper and package each one as a
  standards-compliant nanopublication (TriG/RDF with head, assertion, provenance
  and publication-info named graphs), every assertion carrying a verbatim evidence
  quote and an exact source location (page, section, paragraph, sentence). Use
  when a task asks to read a paper or abstract and produce nanopublications,
  machine-readable RDF/Turtle/TriG assertions, claim decomposition with evidence
  binding, assertion-source comparison tables, or structured knowledge units from
  literature. Trigger words: nanopublication, assertion extraction, claim
  extraction, evidence binding, RDF, Turtle, TriG, provenance, pubinfo.
---


## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 6 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

1. 第0步先落盘骨架：读完 /input/case.json 与题面后，第一个写盘动作就是在 /app/output/result.json 写入骨架：case_id 取自 case.json；键名严格按 case.json 或 task.md 中 output_contract 声明的每个字段生成（当前无法完成的字段值填 unknown 或空数组，绝不省略键）；status 填运行时约定的部分完成值。此后任何时刻 /app/output/result.json 必须存在且 JSON 可解析。
2. 字段一个不缺：最终 result.json 必须包含 output_contract 的全部键。某项确实无法产出时，保留键并填 unknown、空数组或说明字符串，同时把原因写入 uncertainty/说明字段，不得删除键、不得编造数据。
3. 广度优先：先让全部要求的产物以最小合格版本存在，再对高价值部分加深。禁止在单一产物上耗尽预算。
4. 预算保护：模型请求已用超过 48 次或运行时间超过 700 秒时，立即停止新增处理，用现有中间结果完成 result.json 并收尾。每次写 result.json 都覆盖为当前最新完整状态。
5. 最终写盘前自检：JSON 可解析、output_contract 字段一个不缺、case_id 与输入一致、status 如实。自检不过先修复再交付。
6. 失败也要交付：处理中断或失败时，仍写 result.json（status 用题面约定的失败值，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。



# Nanopublication 论断抽取与打包 Skill

## 1. 用途

从科研论文（正文、摘要或片段）中抽取科学论断，把每条论断打包为一个符合 Nanopublication 规范的 RDF 单元（TriG 序列化，四命名图：head、assertion、provenance、pubinfo），并保证：

1. **拆得细**：一段结论拆成若干条单一、可独立判断真假的断言，不把整段话塞进一个字段。
2. **对得上**：每条断言绑定最小充分证据片段（逐字引用）与精确定位（页码、章节、段落、句序）。
3. **追得回**：断言、证据、论文、作者、年份、版本之间的链路完整，他人可据此回到原文。
4. **读得懂**：导出为合法 TriG 与结构化 result.json，下游程序可直接解析。

## 2. 适用条件

- 输入为文本型科研材料：PDF（有文本层）、纯文本、Markdown、XML、HTML 或内嵌在 case.json 中的文本。
- 材料含可用源文本；仅有题图且无文本层时按第 7 节异常分支降级。
- 不适用于：纯 bibliographic 元数据整理、无断言性内容的纯描述材料（此时诚实输出空结果并说明）。

## 3. 调用方式

Agent 收到任务（case.json + task.md）后自动执行本 Skill 流程；人工调用时按第 4 节步骤逐步执行即可。本 Skill 为纯流程与规范约束，不依赖外部库或网络；如需机械校验 TriG 结构，可选用 `scripts/validate_np.py`（仅 Python 标准库）。

## 4. 工作流程

执行预算约 64 次模型请求、900 秒，流程按经济原则设计，正常约 8 至 12 次请求即可完成。**先写中间结果再精修**，任何时刻保证 /app/output 中存在可读的部分结果。

### 步骤 1：读取输入与边界（1 次请求）

1. 读取 `/input/case.json` 与 `task.md`。记录 `case_id`、材料路径、`output_contract` 字段列表。
2. 明确输出字段约定：result.json 必须包含 `case_id` 以及 output_contract 要求的全部字段；若 case.json 未给出 output_contract，使用 `references/result-json-template.md` 的基础结构。
3. 识别材料形态（PDF/文本/内嵌文本），确认可访问性。

### 步骤 2：定位并通读相关材料（1 至 3 次请求）

1. 打开论文材料，优先通读摘要、结果与讨论中的结论性段落；方法与引言仅作为背景定位。
2. 确定页码基准：优先用论文自身标注的正文页码；若只有 PDF 页序，记录在 `location.page_basis` 字段（取值 `paper` 或 `pdf`），不得混用。

### 步骤 3：阶段一，抽取候选论断（1 次请求，批量）

按 `references/assertion-extraction-spec.md` 执行，产出候选论断清单（JSON 草稿，写入 /app/work/candidates.json）：

1. 以句子为单位扫描结论性段落，把每个复合句拆为单一主张（并列结构拆并列，因果结构拆为原因断言与结果断言两条）。
2. 每条候选记录：`id`（NP001 起编号）、`candidate_text`（用原文措辞，保留量词、限定词、否定与方向）、`source_span`（章节、段落号、句号）、`hedging_markers`（命中 hedging 词表的全部标记，如 may、suggests、approximately）、`numeric_items`（数值与单位，逐字抄录）。
3. 不在此时写 RDF，不此时判断证据是否充分。

### 步骤 4：阶段二，逐条回原文核对（1 至 2 次请求）

这是本 Skill 的核心增益闸门，逐条执行三项校验：

1. **忠实性校验**：候选文本与原文逐字对照。改写只允许语法层面的最小变化；量词（all、some、most）、限定条件（in mice、under hypoxia）、否定词、比较方向（increase 与 decrease）必须原样保留。发现偏差立即回改候选文本。
2. **证据最小充分性校验**：为每条断言选定最小充分证据片段（单独这一片段即足以支撑该断言，不含无关内容），逐字抄录为 `evidence_quote`（不超过 300 字符），并给出 `evidence_location`（page、section、paragraph、sentence 四字段全部必填，无法提供其一则按第 7 节降级）。区分 `evidence_type`：`direct`（原文直接陈述）或 `inferred`（需跨句或跨段落综合，须在 `inference_note` 写明推理步骤）。
3. **论断强度校验（hedging 闸门）**：原文含 hedging 标记的，断言文本必须保留同等强度；`may increase` 不得写成 `increase`。每条断言给出 `assertion_strength`（`definitive` / `suggestive` / `conditional` / `correlational`），依据为 hedging 标记表（见抽取规范）。把论文的 suggestive 结果写成 definitive 属于严重错误，直接删除该断言或降级改写。

核对完成后把逐条结论写入 /app/work/verified.json，并同步生成**论断-原文对照表**（Markdown，断言、证据引文、定位、强度四列并排），写入 /app/output/assertion-source-table.md。

### 步骤 5：生成 nanopublication（TriG）（1 至 2 次请求）

按 `references/turtle-templates.md` 与 `references/nanopub-structure.md` 执行：

1. 每条通过校验的断言生成一个独立 nanopublication（一个断言一个 np；同一断言图的多个三元组必须服务于同一主张，如主三元组加保留限定词的 rdfs:label）。
2. URI 约定：`this:` 为 nanopub 基 URI（无网络环境用 `https://w3id.org/np/LOCAL/{case_id}/{NP编号}` 占位并在 result.json 注明未签名）；四个部分用片段 `#assertion`、`#provenance`、`#pubinfo`、`#head`。
3. assertion 图：核心三元组（受控关系词表映射谓词，见抽取规范第 5 节）加 `rdfs:label "断言全文（保留 hedging）"`。
4. provenance 图：`prov:wasDerivedFrom`（论文 URI，含 DOI 或题目标识）、`npex:evidenceQuote`、`npex:evidenceLocation`（页/章节/段落/句四字段）、`npex:assertionStrength`、`npex:hedgingMarkers`、`npex:evidenceType`。
5. pubinfo 图：`pav:createdBy`、`prov:generatedAtTime`、`dcterms:license`、`foaf:primaryTopic`。
6. 写入 /app/output/nanopubs.trig（全部 np 合并一个 TriG 文件）。断言较多时分批追加写入，避免单次响应超限。

### 步骤 6：机械校验与写 result.json（1 至 2 次请求）

1. 运行 `python scripts/validate_np.py /app/output/nanopubs.trig`（或按其输出人工核对）：检查四图齐全且非空、head 三元组完整、花括号配平、必需前缀已声明。
2. 按 `references/result-json-template.md` 写 /app/output/result.json：包含 `case_id`、`status`、output_contract 全部字段、断言数组（含证据与定位）、输出文件清单、`uncertainties`、`unreported`、`change_log`、统计信息。
3. 对照第 8 节自检清单逐项自查，未通过项修正后重查一次。

### 步骤 7：收尾

- status 判定：全部断言通过校验且输出齐全为 `success`；存在降级或部分断言未通过为 `partial`（写明哪些条目、什么原因、人工接管位置）；材料不可读或无有效断言为 `failed` 或 `refused`，并写明原因。
- result.json 中 `change_log` 记录本次运行的增量动作（写入时间、动作、影响条目）。

## 5. 输入约定

| 输入 | 位置 | 必需 | 说明 |
|-|-|-|-|
| case.json | /input/case.json | 是 | 含 case_id、材料路径或内嵌文本、output_contract |
| task.md | /input/ 或与 case.json 同级 | 是 | 任务说明与评分证据范围 |
| 论文材料 | case.json 指定路径 | 是 | PDF 或文本；PDF 由平台直接提供 |

## 6. 输出约定

| 输出 | 路径 | 说明 |
|-|-|-|-|
| result.json | /app/output/result.json | 必含 case_id 与 output_contract 全字段，见模板 |
| nanopubs.trig | /app/output/nanopubs.trig | 全部 nanopublication，TriG 合并文件 |
| 对照表 | /app/output/assertion-source-table.md | 论断-原文对照表，供人工复核 |
| 中间产物 | /app/work/candidates.json、verified.json | 两阶段流程留痕 |

## 7. 异常处理分支

| 情形 | 处置 |
|-|-|
| PDF 无文本层（扫描版） | 尝试逐页 OCR 不可用时：status=partial，result.json 写明无文本层、已尝试动作、人工接管位置（人工提供文本层）；不得凭题名编造论断 |
| 原文论断本身模糊无法单义化 | 不强行改写为断言；把该片段记入 `uncertainties`（引原文并注明模糊点：量词不明/主体不明/条件缺失）；若可拆出其中清晰的部分则只输出清晰部分 |
| 断言找不到支撑片段 | 该条不进入 nanopubs.trig；记入 `unreported` 并注明原因（证据缺失/疑似引用他人结果）；疑似引用他人结果的，不作为本文论断输出 |
| 断言与证据冲突 | 以原文为准；断言文本回改；若属矛盾表述（同一论文前后不一致），两条均不输出，整体记入 `uncertainties` |
| 断言含数值或单位 | 数值与单位必须逐字保留（含精度与区间符号）；原文给区间则断言保留区间，不得取中值；数值项逐条列入 `numeric_items` 供核对 |
| 材料缺失或路径无效 | 重试一次列出目录确认路径；仍失败则 status=failed，result.json 写明缺失项与已检查路径 |
| 证据跨图表（正文断言依赖图示） | evidence_quote 引正文文字部分，`evidence_location.figure` 记图号；图内数值无法逐字引用时 evidence_type=inferred 并写明 |
| 多篇来源论文 | 每条断言的 provenance 只绑定直接支撑它的那篇；跨来源合并结论不输出为单条断言 |
| 页码基准不清 | location.page_basis 记录所用基准；正文页与 PDF 页都存在时优先正文页并注明 |

## 8. 自检清单

输出前逐项确认，全部为是才算 success：

1. 每条断言只有一个可判断真假的主张，无复合句整段塞入。
2. 每条断言的量词、限定词、否定、方向、数值单位与原文逐字一致。
3. 每条断言的 hedging 强度与原文一致（may 不得写成确定句）。
4. 每条断言的 evidence_quote 为逐字引用且独立充分；evidence_location 四字段齐全。
5. 主体与关系方向与原文一致（A 增加 B，不是 B 增加 A）。
6. TriG 通过 validate_np.py：四图齐全非空、head 三元组完整、花括号配平。
7. 每个 nanopublication 的 assertion 图只含一条主张（及其 label 三元组）。
8. provenance 图含来源论文标识与全部证据字段；pubinfo 图含创建者、时间、许可、主题。
9. result.json 含 case_id、status（诚实）、output_contract 全部字段、uncertainties、unreported、change_log。
10. 对照表已生成且与 nanopubs.trig 条目数一致。
11. 未编造任何不在原文中的内容；未把推论写成直接陈述而未标注 inferred。

## 9. 资源文件索引

| 文件 | 作用 |
|-|-|
| references/nanopub-structure.md | Nanopublication 四命名图结构与 np 前缀规范 |
| references/turtle-templates.md | TriG 可直接套用的模板与字段填法 |
| references/assertion-extraction-spec.md | 论断抽取规范：粒度判据、hedging 词表、受控关系词表、证据定位 |
| references/common-errors.md | 常见错误清单与修正方法 |
| references/result-json-template.md | result.json 字段字典与输出模板 |
| references/self-check.md | 自检清单详版（与第 8 节一致，含判据说明） |
| references/example-case.md | 示例：虚构论文片段到 20 条断言样例的完整推导（仅教学示意） |
| scripts/validate_np.py | 纯标准库 TriG 结构校验脚本 |

## 10. 维护信息

- 规范依据：Nanopublication 四命名图结构（np:nschema，nanopub.org 社区规范）；前缀写法以本 Skill references 为准。
- 版本：1.0；变更记录写在本文件底部。
- 已知限制：不做跨论文去重合并；不生成密码学签名与 trusty URI；OCR 依赖环境预装能力。
