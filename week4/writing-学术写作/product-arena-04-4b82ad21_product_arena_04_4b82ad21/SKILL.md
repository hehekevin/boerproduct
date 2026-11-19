---
name: intro-related-work-writer
description: >
  Academic writing skill for drafting the Introduction and Related Work
  sections of a research paper from provided materials only. Triggers on
  requests to write an introduction, organize related work, derive a
  research gap, state contributions, or place citations. Core mechanisms:
  claim-to-source mapping (every factual claim traces to a source
  location), grouped comparison of related work, gap derived only from
  cited limitations, and contribution-evidence alignment. Writes an
  early result.json skeleton, then embeds the full draft text into
  result.json fields (not only external files), marking material gaps
  with explicit markers instead of fabricating. Use for any paper-writing
  task mentioning Introduction, Related Work, research gap, contribution
  bullets, or citation placement.
---

# 引言与相关工作写作 Skill（极简线性流程）

为论文撰写引言（Introduction）与相关工作（Related Work）。所有事实仅来自输入材料；材料不足处标注 `[材料缺口]`，绝不编造。

预算约束：64 次模型请求、900 秒、单响应 16384 tokens。本流程按 6-8 次响应设计。**若已用超过 40 次请求或 700 秒，跳到第 5 步立即收尾**：把已有内容嵌入 result.json，status 如实填 partial。

## 第 1 步：读取契约与材料

1. 完整读取 `/input/case.json` 与 `task.md`。
2. 抄写两样东西，供后续所有步骤使用：
   - `case_id` 的值。
   - `output_contract` 的**全部键名**（原样照抄，不增不减）。
3. 记录约束：语言、受众、引用格式、篇幅限制。
4. 通读案例材料（论文正文、笔记、参考文献等）。以实际文件内容为准，不根据文件名或领域标签假设内容。

## 第 2 步：立即落盘 result.json 骨架

用第 1 步抄下的键名，写入 `/app/output/result.json`：

```json
{
  "case_id": "<第1步抄的值>",
  "<output_contract 的每个键>": "",
  "status": "partial"
}
```

规则：
- 每个契约键都必须存在，值为空串、空数组或 null（绝不省略键）。
- 若 case.json 未给出 output_contract，用以下默认键：`case_id`、`introduction`、`related_work`、`claim_source_map`、`gaps`、`status`，并在 result.json 中加 `"output_contract_fields"` 数组说明实际使用的键。
- 写完即验证：`result.json` 可被 JSON 解析。此后任何时刻该文件必须存在且可解析。

## 第 3 步：建立论断-来源映射与贡献-证据对齐

1. 从材料中抽取事实单元：数字、术语、方法名、他人工作结论、图表指涉。为每份材料编号 S1、S2…，每条事实记录来源定位（文件名+章节/段落号）。写入 `/app/work/claim_map.md`，每行一条：

   `C1 | 论断内容 | S1 §2 段3 | 可直接引用/作者判断`

2. 从摘要、方法、实验、图表标题中抽取本文贡献条目，每条登记证据位置（方法章节号、表号、图号），追加到同一文件：

   `CT1 | 贡献表述 | 证据位置 | 对齐/降级`

3. 硬规则：映射表中没有的事实，写作时要么不写，要么明确标注为作者判断；找不到正文证据的贡献降级表述或标注 `[待确认]`。

## 第 4 步：撰写正文

1. **引言**：漏斗结构四段——具体研究背景（不用"近年来受到广泛关注"式空转铺垫，写真实脉络与具体问题）→ 现有方法与不足（引用具体文献）→ 研究空白（只能由已引文献的共同局限、未覆盖场景或冲突结论推出，并说明本文如何填补）→ 贡献条目（逐条来自贡献-证据表）。写入 `/app/output/introduction.md`。
2. **相关工作**：按问题设定/方法路线/数据与评价维度分组，每段一个组：组内共识、代表工作、各工作在同一维度上的取舍与局限，段末衔接本文与该组的关系。禁止逐篇摘要拼接。写入 `/app/output/related_work.md`。
3. 引用纪律：沿用材料中已有编号；无编号时用 `[作者, 年份]`；无法确认元数据的引用用 `[CITE?: 待查]` 占位，绝不编造作者、年份、来源。
4. 每条事实性论断在行文中带来源定位（如 `[S1 §2]`），与 claim_map 对应。

## 第 5 步：嵌入正文并收尾 result.json

1. 把引言全文、相关工作全文作为**字符串**完整嵌入 result.json 对应字段（嵌入正文内容本身，不是文件路径；字段名以 output_contract 为准；契约未指明时用 `introduction`、`related_work` 并在 `output_contract_fields` 中透传）。
2. 同时另存外部文件 `/app/output/introduction.md`、`/app/output/related_work.md`（内容与嵌入文本一致）。
3. 补全其余字段：`claim_source_map`（论断-来源映射，逐条可回溯）、`gaps`（材料缺口清单，逐条具体）、`status`（全部完成且契约字段齐全填 `success`，否则如实填 `partial` 并在 gaps/说明字段写明缺什么）、`uncertainty`/`human_confirm`（如有）、`change_log`（相对原文的修改差异）。
4. 终检，逐项核对后交付：
   - result.json 可被 JSON 解析。
   - output_contract 的每个键都存在且非空（无法产出的键保留键名，填说明字符串并计入 gaps）。
   - case_id 与输入一致；status 如实。
   - 嵌入正文为完整终稿文本，与外部 .md 文件一致。

## 异常处置

| 情形 | 处置 |
|-|-|
| 材料不足（缺方法章节/实验结果等） | 可写部分照常产出，缺口处插 `[材料缺口：缺少XX]`，gaps 逐条列出，status=partial |
| 参考文献列表为空 | 相关工作用 `[CITE?: 待补充]` 占位，不虚构文献 |
| 材料内部事实冲突 | 两条都登记进 claim_map，草稿采用与摘要一致的一条，冲突写入 change_log |
| 输入文件不可读 | gaps 记录该文件及原因，继续处理可读部分 |
| 中断/失败 | 仍写 result.json：status 如实，说明中断位置与已完成部分 |

## 自检要点（收尾前过一遍）

- 契约键一个不缺；正文嵌在 result.json 内而非只有文件。
- 每条关键论断有来源定位；无编造的数字、作者、年份。
- 相关工作分组建段；空白由已引文献推出且与贡献对应。
- 每条贡献有正文证据位置。
