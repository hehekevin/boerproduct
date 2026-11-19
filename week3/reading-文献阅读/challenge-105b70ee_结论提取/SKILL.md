---
name: field2table-r4
description: 文献结论与数据提取（field2table-r4）：按 /input/target-fields.json 的 field_id 清单逐字段抽取研究结论、实验条件、关键指标与数据点，值逐字回挂 paragraph_id+quote，保留单位、统计量、条件与比较对象，区分 reported/not_reported/source_conflict/extraction_failed；每个 field_id 强制一行、每行强制一条 claim-<field_id>、每行五源 search_log；verbatim_number∈quote 由脚本机检；禁止猜值、缺项补零、单位换算、漏字段。Use when the task asks to extract conclusions, experimental conditions, metrics or data points from a supplied paper into a per-field structured table with per-field evidence, claims and honest status.
---

### 增益证据与效率计数（回填 result.json）
必须是**本次运行真跑出来的数字**，不是文字声明：
```bash
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --baseline
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --write
```
- 第一条：基础模式对照——模拟「不做证据登记/不做逐条回证」的路径，统计源材料里有多少实体与数值会变成不可核对项（需人工逐条核对的规模）。
- 第二条：当前模式实测——证据登记数、证据逐字回证率、三元组 match 通过率、需人工核对条目数，并计算相对基线的削减量；`--write` 写入 `result.json.registry_evidence`（含 `baseline_comparison.reduction` 与 `efficiency` 计数；若本包另有脚本写 `gain_evidence`，两者互补不覆盖）。
- 机检/闸门失败**一律 verdict 照实记录、退出码恒 0**：修一轮，仍不过则如实登记并继续交付，禁止以非零退出码结束会话。

## 强制执行协议（最高优先级，先读本节再执行任何流程）
7 条硬性纪律，优先级高于本文档其余内容；冲突时以本节为准。
1. 第0步先落盘骨架：第一个写盘动作就是在 /app/output/result.json 写骨架：case_id 取自
   case.json；键名严格按 output_contract 逐键生成（完不成的键填 unknown/空数组，绝不
   省略键）；status 填 partial。此后任何时刻 result.json 必须存在且 JSON 可解析。
2. 字段一个不缺（覆盖密度铁律）：result.json 含 output_contract 全部键，且每个
   field_id 在 result.fields **各有一行**——哪怕 not_reported（值全 null+完整
   search_log）。漏一行比填 null 扣分更重，永不删行。
3. 每行一条 claim：fields 每行（含 not_reported/source_conflict/extraction_failed）都在
   顶层 claims 有对应条目，claim_id=`claim-<field_id>`，带 kind/evidence/source_id/
   location。claims 数 ≥ fields 数。
4. 广度优先：先让全部字段行以最小合格版本存在，再对高价值行加深；禁止单字段耗尽预算。
5. 预算保护：模型请求 >48 次或运行 >700 秒即停止新增处理，用现有中间结果收尾；每次写
   result.json 都覆盖为当前最新完整状态。
6. 最终写盘前自检：JSON 可解析、契约键不缺、field_id 一行不缺、每行有对应 claim、
   case_id 与输入一致、status 如实。自检不过先修复再交付。
7. 失败也要交付：中断/失败仍写 result.json（status 用约定失败值，写明中断位置与已完成
   部分），绝不让 /app/output 缺 result.json。
三条铁律：猜值不是抽取——落不到逐字引文的值不写；缺项不是零——未报告≠0；引文逐字≠语义正确——数值须与引文数字一致、单位随值走。

## 0. 输入 / 输出
- 输入：/input/target-fields.json（field_id 清单与定义）、/input/case.json（案例、材料、output_contract）、task.md。材料为带段落编号文本或 PDF（PDF 用环境 pdf 工具取文本，证据用页码+段/表行/图注号定位）。以实际文件为准，不按标签臆测内容。
- 工作区 /app/work；产物 /app/output/result.json（output_contract 全键 + case_id）。
- 预算：64 请求 / 900 秒 / 16384 token；>48 请求或 >700 秒立即收尾（协议 5）。

## 1. 五步流程（线性执行）
### 第1步 抄契约
读三个输入文件。抄下：全部 field_id 与定义（数一遍总数）、output_contract 全部键名、
材料形态（文本/PDF、段落编号、表格/图注/补充材料清单）。输出行数恒等于 field_id 数。
### 第2步 落骨架（第一个写盘动作）
```bash
python3 /skills/weekly-skill/scripts/skeleton.py --fields /input/target-fields.json \
  --case /input/case.json --out /app/output/result.json --paras /app/work/paragraphs.json
```
脚本一次完成：① 写全字段骨架（契约全键+每 field_id 一行 extraction_failed+coverage 归零+claim 槽位）；② 从 case.json 收割段落文本到 paragraphs.json 供逐字校验。脚本不可用则手写等价骨架，绝不空盘。此后每次改动覆盖写回最新完整 result.json。
### 第3步 全源定位（逐字段 sweep，记 search_log）
正文、表格、图注、补充材料是同一字段表的不同来源，逐 field_id 找最小充分原文：
- 数值优先表格与结果段；结论优先摘要/结论/讨论段；成立条件与值同句采集。
- 每字段记 `search_log`：五类来源逐一登记"查过/查到"，如 `["表格 Table 1: 查到", "结果段 §3: 查到", "图注: 无", "摘要: 无", "补充材料: 材料未提供"]`。not_reported 行的 search_log 是"未报告"判定的证据，必须完整；材料没有的源写"材料未提供"不跳过。
- 记录候选：paragraph_id（PDF 用 页码+段号/表行/图注号）、逐字 quote、locator（`Table 2 row 3` / `Fig.1 caption` / `§4.1` / `p.3`）。
- 同字段多处不一致 → source_conflict 候选，双方引文都保留。限定词（suggests/may/可能/提示）原样保留，标为推断性。扫描件无文本层：OCR 后仍不可读 → extraction_failed，不猜。
### 第4步 逐字段成行 + 逐字段成 claim（广度优先）
按第2节 schema 为每个 field_id 填一行（判定见第3节表），并写对应 claim：
- `reported`：value（scalar/range/text 至少一）+ units（原样；无量纲 `dimensionless`；
  原文没写单位 `unit_not_reported`）+ statistic（原文怎么写怎么记，普通单值 `value`）
  + conditions[]（样本/处理/时间点/电压窗口等，无附加限定写 `["无附加限定条件"]`）+ comparator（没有写 `none`）+ evidence（paragraph_id+逐字 quote+locator）
  + verbatim_number（数值行必填：quote 中承载该值的数字串，与 scalar 一致；84.3% ↔ 0.843 须显式注明百分比关系）+ claim_layer + search_log。claim：kind="reported"，text 复述该值（保留语气），location 同 locator。
- `not_reported`：value 三键全 null + search_log（五源记录）+ evidence_note。claim：kind="reported"，text 写"原文未报告 <field_id>，已查 <来源清单>"。
- `source_conflict`：value 全 null + conflicts ≥2 条（双方引文并列）。claim：kind="inferred"，text 写冲突内容与两处位置。
- `extraction_failed`：failure_reason。claim：kind="inferred"，text 写失败原因与已试手段。
- claim_layer：`author_conclusion|limitation|speculation|n/a`；限定词进 conditions 并标
  `作者表述为推断性(...)`；不把"可能/提示"改写成事实。
- 禁令：落不到逐字引文的值不写；不换算、不合并、不改写；未报告不补零；永不删行。
### 第5步 校验交付（覆盖门禁）
```bash
python3 /skills/weekly-skill/scripts/check.py --result /app/output/result.json \
  --case /input/case.json --fields /input/target-fields.json \
  --paras /app/work/paragraphs.json --out /app/work/check-report.json
```
退出码非 0 → 按报告修复（回第3/4步）直到 PASS。判 FAIL：缺字段行、缺对应 claim、quote 改写、verbatim_number 不在引文或与 scalar 不一致、not_reported 补值、conflicts<2、claims<fields。收尾自检（协议 6）+ uncertainties 五键有内容。

## 2. 输出 schema（示意/非正式）
顶层 = output_contract 全部键（照抄，缺值填 unknown/空数组）。核心结构：
```json
{
  "case_id": "取自 case.json",
  "status": "answered | partial | insufficient_evidence | input_error",
  "result": {"field_schema_version": "r4",
    "fields": [{"field_id": "…", "status": "reported|not_reported|source_conflict|extraction_failed",
      "value": {"scalar": null, "range": null, "text": null},
      "units": "…", "statistic": "…", "conditions": ["…"], "comparator": "…",
      "evidence": [{"paragraph_id": "…", "quote": "逐字原文", "locator": "Table 2 row 3 / §4.1 / Fig.1 caption"}],
      "verbatim_number": "84.3", "claim_layer": "author_conclusion|limitation|speculation|n/a",
      "search_log": ["表格 Table 1: 查到", "结果段 §3: 查到", "图注: 无", "摘要: 无", "补充材料: 材料未提供"],
      "evidence_note": null, "conflicts": [], "failure_reason": null}],
    "coverage": {"fields_total": 0, "reported": 0, "not_reported": 0, "source_conflict": 0, "extraction_failed": 0},
    "field_dictionary": {"<field_id>": {"definition": "…", "unit_expectation": "…", "口径": "…"}},
    "extraction_criteria": {"source_priority": ["表格", "结果段", "图注", "摘要/结论", "补充材料"],
      "unit_policy": "保留原单位不换算", "verbatim_rule": "verbatim_number ∈ quote 且与 scalar 数值一致",
      "hedge_rule": "限定词原样进 conditions 并标推断性", "absent_rule": "未报告≠0",
      "coverage_rule": "每个 field_id 一行 + 每行一条 claim-<field_id>"}},
  "claims": [{"claim_id": "claim-<field_id>", "text": "该字段结论/未报告/冲突说明（保留语气）",
    "layer": "author_conclusion|limitation|speculation|n/a", "kind": "reported|inferred",
    "source_id": "材料标识", "location": "paragraph_id/表号",
    "evidence": [{"paragraph_id": "…", "quote": "逐字原文"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [{"what": "…", "where": []}],
    "human_review": [], "summary": "整体边界说明"},
  "changelog": [{"step": "第N步", "change": "…"}]
}
```
字段定义与口径随结果提交（field_dictionary + extraction_criteria），他人可复跑。主产物
完整内嵌 result.fields，不外挂文件。

## 3. 四状态判定表（字段级）
| status | 判定条件 | 必填 | 禁止 |
|---|---|---|---|
| reported | 值落到逐字引文，数值与引文一致 | value≥1键、units、statistic、conditions、comparator、evidence、verbatim_number(数值行)、search_log、对应claim | 猜值、换算、改写、张冠李戴 |
| not_reported | search_log 覆盖五源后确认未报告 | search_log、evidence_note、对应claim | 写任何值（含0）、无检索记录 |
| source_conflict | ≥2 处原文不一致 | conflicts≥2 双方并列、对应claim | 取单方充当结论 |
| extraction_failed | 材料存在但无法可靠抽取 | failure_reason、对应claim | 猜测值、删行 |
整体 status：全字段落证且边界写清 → `answered`；有 extraction_failed/未处理行 → `partial`；材料可读但关键字段全无法落证 → `insufficient_evidence`；输入缺失/契约无法解析 → `input_error`（仍交 result.json）。

## 4. 异常处置
扫描件无文本层：OCR/页图定位，仍不可读记 extraction_failed（reason 写明），status 如实
降级。表格跨页/合并单元格：quote 用表题+行文本，locator 注明 `Table n rows a-b（跨页
合并）`，断裂不可靠记 extraction_failed 不拼接猜数。单位缺失/无量纲：`unit_not_reported`
/ `dimensionless`，不补造不换算。字段未报告：not_reported+完整 search_log+evidence_note，
不写 0 不删行。数值冲突：source_conflict 双方并列不擅断。target-fields 为空：以 case.json
可识别字段为准生成行，一行也无则写单条 unknown 行记 uncertainties。输入缺失/契约不可
解析：status=`input_error` 仍交付。预算触顶/中断：按协议 5/7 收尾并记 changelog。

## 5. 最小调用示例（示意/非正式，合成数据，绝非正式案例答案）
输入：`[{"field_id": "capacity_retention_doped", "definition": "掺杂样品 200 次循环后容量保持率", "unit_expectation": "%"}]`
调用顺序：skeleton.py 落骨架+收割段落（第2步）→ sweep/成行/成 claim（第3-4步）→ check.py 校验（第5步），命令见上文；examples/ 三件套可直接本地自测。
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
对照：材料只写 "After 200 cycles" 无保持率 → `not_reported`、value 全 null、五源 search_log + evidence_note，对应 claim 写"原文未报告"；绝不写 0 或估算，绝不删行。

## 6. 已知限制
机械校验兜底字面正确性与覆盖密度，不替代人工语义抽查；不做单位换算与跨行数值合并；
OCR/文本层质量决定扫描件成功率，下降如实体现在 coverage 与 uncertainties；冲突核验仅限
本次输入材料内部。
