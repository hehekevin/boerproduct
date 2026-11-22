---
name: field2table-r3
description: 文献结论与数据提取（field2table-r3）：按 /input/target-fields.json 的 field_id 清单逐字段抽取研究结论、实验条件、关键指标与数据点，值逐字回挂 paragraph_id+quote，保留单位、统计量、条件与比较对象，区分 reported/not_reported/source_conflict/extraction_failed；每个 field_id 强制一行、每行强制一条对应 claim、每行记录来源检索日志；禁止猜值、缺项补零、漏字段。Use when the task asks to extract conclusions, experimental conditions, metrics or data points from a supplied paper into a per-field structured table with per-field evidence, per-field claims and honest status.
---

## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 7 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

1. 第0步先落盘骨架：读完 /input/case.json 与题面后，第一个写盘动作就是在
   /app/output/result.json 写入骨架：case_id 取自 case.json；键名严格按 case.json
   或 task.md 中 output_contract 声明的每个字段生成（当前无法完成的字段值填
   unknown 或空数组，绝不省略键）；status 填运行时约定的部分完成值。此后任何
   时刻 /app/output/result.json 必须存在且 JSON 可解析。
2. 字段一个不缺（覆盖密度铁律）：最终 result.json 必须包含 output_contract 的全部键，
   且 target-fields.json 的**每个 field_id 在 result.fields 中各有一行**——哪怕该行是
   not_reported（值全 null + 检索说明）。漏一行比填 null 扣分更重，永远不删行。
3. 每行一条 claim：result.fields 的每一行（含 not_reported/source_conflict/
   extraction_failed）都必须在顶层 claims 有一条对应条目，claim_id 用
   `claim-<field_id>`，带 kind/evidence/source_id/location。claims 数 ≥ fields 数。
4. 广度优先：先让全部字段行以最小合格版本存在，再对高价值行加深。
   禁止在单一字段上耗尽预算。
5. 预算保护：模型请求已用超过 48 次或运行时间超过 700 秒时，立即停止新增处理，
   用现有中间结果完成 result.json 并收尾。每次写 result.json 都覆盖为当前最新
   完整状态。
6. 最终写盘前自检：JSON 可解析、契约键一个不缺、field_id 一行不缺、每行有对应
   claim、case_id 与输入一致、status 如实。自检不过先修复再交付。
7. 失败也要交付：处理中断或失败时，仍写 result.json（status 用题面约定的失败值，
   写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

三条铁律（与本协议同级）：猜值不是抽取——落不到逐字引文的值一律不写；缺项不是零——
未报告≠0；引文逐字≠语义正确——数值须与引文数字一致、单位随值走。

## 0. 输入 / 输出

- 输入：/input/target-fields.json（field_id 清单与字段定义）、/input/case.json（案例、
  材料、output_contract）、task.md。材料是带段落编号的文本或 PDF（PDF 用环境 pdf 工具
  取文本，证据用页码+段/表行/图注号定位）。以实际文件为准，不按标签臆测内容。
- 工作区 /app/work；最终产物 /app/output/result.json（含 output_contract 全部键 + case_id）。
- 预算：64 次模型请求 / 900 秒 / 单响应 16384 token；模型请求 >48 或时长 >700 秒
  立即收尾（协议 5）。

## 1. 五步流程（线性执行）

### 第1步 抄契约
读 /input/target-fields.json、/input/case.json、task.md。抄下：**全部 field_id 与字段
定义（名称/单位期望/口径，一个不漏，数一遍总数）**；output_contract 声明的 result.json
全部键名；材料形态（文本/PDF、段落编号方式、表格/图注/补充材料清单）。该清单是后续
唯一契约，输出行数恒等于 field_id 数。

### 第2步 落骨架（第一个写盘动作）
```bash
python /skills/weekly-skill/scripts/skeleton.py --fields /input/target-fields.json \
  --case /input/case.json --out /app/output/result.json --paras /app/work/paragraphs.json
```
脚本一次性完成两件事：① 写全字段骨架（契约全键 + 每 field_id 一行
status:"extraction_failed" + coverage 归零 + claim 槽位说明）；② 从 case.json 收割段落
文本到 /app/work/paragraphs.json 供逐字校验。脚本不可用则手写等价骨架，绝不空盘。
此后每次改动覆盖写回最新完整 result.json。

### 第3步 全源定位（逐字段 sweep，记录检索日志）
把**正文、表格、图注、补充材料**当作同一字段表的不同来源，逐 field_id 找最小充分原文：
- 数值优先表格与结果段；结论优先摘要/结论/讨论段；成立条件与值同句采集。
- 每个字段记 `search_log`：五类来源逐一登记"查过/查到"（如 `["表格 Table 1: 查到",
  "结果段 §3: 查到", "图注: 无", "摘要: 无", "补充材料: 材料未提供"]`）。
  not_reported 行的 search_log 是"未报告"判定的证据，必须完整。
- 记录候选：paragraph_id（PDF 用 页码+段号/表行/图注号）、逐字 quote、locator
  （如 `Table 2 row 3` / `Fig.1 caption` / `§4.1` / `p.3`）。
- 同一字段多处数值或表述不一致 → 记 source_conflict 候选，双方引文都保留。
- 限定词（suggests / may / 可能 / 提示）原样保留，标为推断性。
- 扫描件无文本层：OCR 后按页定位；仍不可读 → 记 extraction_failed 候选，不猜。

### 第4步 逐字段成行 + 逐字段成 claim（广度优先）
按第2节 schema 为**每个** field_id 填一行（状态判定见第3节表），并为每行写一条
`claim_id="claim-<field_id>"` 的 claim：
- `reported`：value（scalar/range/text 至少一）+ units（原样；无量纲写 `dimensionless`；
  原文没写单位写 `unit_not_reported`）+ statistic（mean/median/±sd/p/n 等原文怎么写怎么记，
  普通单值写 `value`）+ conditions[]（样本/处理/时间点/电压窗口等成立条件，无附加限定时
  写 `["无附加限定条件"]`）+ comparator（基线/对照/文献值，没有写 `none`）+ evidence
  （paragraph_id+逐字 quote+locator）+ verbatim_number（数值行必填：quote 中承载该值的
  数字串，与 scalar 数值一致；84.3% ↔ 0.843 必须显式注明百分比关系）+ claim_layer
  + search_log。对应 claim：kind="reported"，text 复述该值（保留语气），location 同 locator。
- `not_reported`：value 三键全 null + search_log（五源检索记录）+ evidence_note
  （为何判未报告）。对应 claim：kind="reported"，text 写"原文未报告 <field_id>，
  已查 <来源清单>"。
- `source_conflict`：value 全 null + conflicts ≥2 条（双方引文并列）。对应 claim：
  kind="inferred"，text 写明冲突内容与两处位置。
- `extraction_failed`：failure_reason（文本层缺失/表格跨页断裂/字段定义不明…）。
  对应 claim：kind="inferred"，text 写失败原因与已尝试手段。
- 结论分层 claim_layer：`author_conclusion|limitation|speculation|n/a`；限定词写进
  conditions 并标 `作者表述为推断性(...)`；不把"可能/提示"改写成事实。
- 禁令：落不到逐字引文的值不写；不换算、不合并、不改写单位与数值；未报告不补零；
  任何情况下不删字段行。

### 第5步 校验交付（覆盖门禁）
```bash
python /skills/weekly-skill/scripts/check.py --result /app/output/result.json \
  --case /input/case.json --fields /input/target-fields.json \
  --paras /app/work/paragraphs.json --out /app/work/check-report.json
```
退出码非 0 → 按报告修复（回第3/4步）直到 PASS，覆盖写 /app/output/result.json。
校验器把以下情况判 FAIL：缺字段行、缺对应 claim、quote 改写、数值不一致、
not_reported 补值、conflicts<2。收尾自检（协议 6）：JSON 可解析、契约键一个不缺、
field_id 一行不缺、claims 数 ≥ fields 数、case_id 一致、status 如实、uncertainties
五键（unreported/unverifiable/conflicts/human_review/summary）有内容。

## 2. 输出 schema（result.json，示意/非正式）

顶层 = 平台通用五键 + output_contract 声明的任何附加键（照抄，缺值填 unknown/空数组）
+ changelog：

```json
{
  "case_id": "取自 case.json",
  "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "field_schema_version": "r3",
    "fields": [{
      "field_id": "…", "status": "reported|not_reported|source_conflict|extraction_failed",
      "value": {"scalar": null, "range": null, "text": null},
      "units": "…", "statistic": "…", "conditions": ["…"], "comparator": "…",
      "evidence": [{"paragraph_id": "…", "quote": "逐字原文", "locator": "Table 2 row 3 / Fig.1 caption / §4.1"}],
      "verbatim_number": "84.3", "claim_layer": "author_conclusion|limitation|speculation|n/a",
      "search_log": ["表格 Table 1: 查到", "结果段 §3: 查到", "图注: 无", "摘要: 无", "补充材料: 材料未提供"],
      "evidence_note": null, "conflicts": [], "failure_reason": null
    }],
    "coverage": {"fields_total": 0, "reported": 0, "not_reported": 0, "source_conflict": 0, "extraction_failed": 0},
    "field_dictionary": {"<field_id>": {"definition": "…", "unit_expectation": "…", "口径": "…"}},
    "extraction_criteria": {"source_priority": ["表格", "结果段", "图注", "摘要/结论", "补充材料"],
      "unit_policy": "保留原单位不换算", "verbatim_rule": "verbatim_number ∈ quote 且与 scalar 数值一致",
      "hedge_rule": "限定词原样进 conditions 并标推断性", "absent_rule": "未报告≠0",
      "coverage_rule": "每个 field_id 一行 + 每行一条 claim-<field_id>"}
  },
  "claims": [{"claim_id": "claim-<field_id>", "text": "该字段结论/未报告/冲突说明（保留语气）",
    "layer": "author_conclusion|limitation|speculation|n/a",
    "kind": "reported|inferred", "source_id": "材料标识", "location": "paragraph_id/表号",
    "evidence": [{"paragraph_id": "…", "quote": "逐字原文"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [{"what": "…", "where": []}],
    "human_review": [], "summary": "整体边界说明"},
  "changelog": [{"step": "第N步", "change": "…"}]
}
```

字段定义与抽取口径随结果提交（result.field_dictionary + extraction_criteria），他人可按
同一口径复跑。主产物（结构化字段表）完整内嵌于 result.fields，不外挂文件。

## 3. 四状态判定表（字段级）

| status | 判定条件 | 必填 | 禁止 |
|---|---|---|---|
| reported | 值落到逐字引文，数值与引文数字一致 | value(scalar/range/text≥1)、units、statistic、conditions、comparator、evidence(paragraph_id+quote)、verbatim_number(数值行)、search_log、对应 claim | 猜值、换算、合并改写、张冠李戴 |
| not_reported | search_log 覆盖五类来源后确认原文未报告 | search_log（找过哪里）、evidence_note、对应 claim | 写任何值（含 0）、无检索记录 |
| source_conflict | ≥2 处原文数值/表述不一致 | conflicts≥2（双方引文并列）、对应 claim | 取单方充当结论、丢弃另一方 |
| extraction_failed | 材料存在但无法可靠抽取 | failure_reason、对应 claim | 用猜测或占位数值填充、删行 |

整体 status：全字段 reported 或明确 not_reported 且边界写清 → `answered`；有
extraction_failed 或未处理行 → `partial`；材料可读但关键字段全部无法落证 →
`insufficient_evidence`；输入缺失/不可读/契约无法解析 → `input_error`（仍交 result.json）。
material 未报告≠0。

## 4. 异常处置

- 扫描件无文本层：OCR/页图定位；OCR 后仍无可靠文本的字段记 extraction_failed
  （failure_reason 写"扫描件无文本层"），整体 status 如实降级。
- 表格跨页/合并单元格：quote 用表题+行文本，locator 注明 `Table n rows a-b（跨页合并）`；
  断裂不可靠的值记 extraction_failed，不拼接猜数。
- 单位缺失/无量纲：units 写 `unit_not_reported` / `dimensionless`，不补造、不换算。
- 字段原文未报告：not_reported + 完整 search_log + evidence_note，不写 0、不估算、不删行。
- 多处或多文献数值冲突：source_conflict，conflicts 双方引文并列，不擅自取其一。
- target-fields 为空/缺失：以 case.json 中一切可识别的字段要求为准生成行；一行也
  得不到时写单条 unknown 行并记 uncertainties。
- 权限不足/输入缺失/契约不可解析：status=`input_error`，写明原因与已完成部分，仍交付。
- 预算触顶或中断：按协议 5/7 立即收尾，status=`partial` 或 `input_error`，
  changelog 写明中断位置。

## 5. 最小调用示例（示意/非正式，合成数据，绝非正式案例答案）

输入片段（/input/target-fields.json）：
`[{"field_id": "capacity_retention_doped", "definition": "掺杂样品 200 次循环后容量保持率", "unit_expectation": "%"}]`

调用顺序：skeleton.py 落骨架+收割段落（第2步）→ 逐字段 sweep/成行/成 claim（第3-4步）
→ check.py 校验（第5步），命令见上文；examples/ 下三件套可直接本地自测。

输出片段（result.json 中该字段一行 + 对应 claim，示意/非正式）：

```json
{"field_id": "capacity_retention_doped", "status": "reported",
 "value": {"scalar": 84.3, "range": null, "text": null},
 "units": "%", "statistic": "value",
 "conditions": ["1C 倍率", "200 次循环", "2.8-4.3 V"], "comparator": "undoped baseline",
 "evidence": [{"paragraph_id": "p02", "quote": "the discharge capacity retention was 84.3%", "locator": "§Results"}],
 "verbatim_number": "84.3", "claim_layer": "n/a",
 "search_log": ["表格 Table 1: 查到", "结果段 §3: 查到", "图注: 无", "摘要: 无", "补充材料: 材料未提供"],
 "evidence_note": null, "conflicts": [], "failure_reason": null}
```

```json
{"claim_id": "claim-capacity_retention_doped", "text": "掺杂样品在 1C、200 次循环后放电容量保持率为 84.3%",
 "layer": "n/a", "kind": "reported", "source_id": "paper", "location": "p02 §Results",
 "evidence": [{"paragraph_id": "p02", "quote": "the discharge capacity retention was 84.3%"}]}
```

对照：若材料只写 "After 200 cycles" 而无保持率 → 该行 `status:"not_reported"`、value 全
null、search_log 记五源检索、evidence_note 写判定依据，对应 claim 写"原文未报告"；绝不
写 0 或估算值，绝不删行。

## 6. 已知限制

- 机械校验（verbatim_number ∈ quote、quote 逐字、数值一致、覆盖门禁）兜底字面正确性与
  覆盖密度，不能替代人工抽查语义。
- 不做单位换算、跨行数值合并推断——只随值记录原单位；换算留给下游。
- OCR/文本层质量决定扫描件抽取成功率；下降会在 coverage 与 uncertainties 如实体现。
- 冲突核验仅限本次输入材料内部，不做外部检索补数。
