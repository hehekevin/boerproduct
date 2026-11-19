---
name: clean2table-r5
description: 文献数据清洗与标准化 Skill：编号规则库（FM/UC/SN/MM/AF/DD）驱动端到端清洗真实抽取记录，产出可统计数据表+逐格清洗台账+待人工确认清单；改动值沿 row_id+rule_id 回溯原值且逐条内嵌行级台账，换算带公式、精度与 trace 中间值（可复算），无法清洗的脏值逐条登记 uncertainties.dirty_values 不静默丢弃；全量机械校验以 {item,template_value,applied,match} 三元组逐条嵌入 result.machine_checks（含换算抽检机检与闸门四态枚举）；支持 --ablate 退化档做同输入双跑增益对照。触发词：文献数据清洗、数据标准化、clean、normalize、抽取数据去重、单位换算、字段映射、同义归一、changelog、待确认清单。
---

## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 7 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

1. 第0步先落盘骨架：读完 /input/case.json 与题面后，第一个写盘动作就是在 /app/output/result.json 写入骨架——case_id 取自 case.json；键名严格按 case.json 或 task.md 的 output_contract 声明逐个生成（无法完成的值填 unknown 或空数组，绝不省略键）；status 填部分完成值。此后任何时刻 /app/output/result.json 必须存在且 JSON 可解析。
2. 字段一个不缺：最终 result.json 必须包含 output_contract 的全部键；确实无法产出时保留键并填 unknown/空数组/说明字符串，原因写入 uncertainty，绝不删键、绝不编造数据。
3. 广度优先：先让全部要求的产物以最小合格版本存在，再对高价值部分加深；禁止在单一产物上耗尽预算。
4. 预算保护：模型请求已用超过 48 次或运行时间超过 700 秒时，立即停止新增处理，用现有中间结果完成 result.json 并收尾；每次写 result.json 都覆盖为当前最新完整状态。
5. 最终写盘前自检：JSON 可解析、output_contract 字段一个不缺、case_id 与输入一致、status 如实；不过先修复再交付。
6. 失败也要交付：中断或失败时仍写 result.json（status 如实降级，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。
7. 每步一个写盘动作：每完成一步立即把 /app/output/result.json 覆盖为当前最新完整状态（含 machine_checks 机检三元组），不留只在内存或日志里的结果。

## 0. 契约速览

- 输入 /input/case.json（抽取记录：行身份 row_id、来源、字段名/值/单位、条件上下文；组织方加入的格式差异、重复抽取、缺值、未知单位均有明确身份）。若行数据在独立文件（csv/tsv/json/jsonl）用 `--rows <文件>` 传入；长表（field/value/unit 三列）引擎自动透视成宽表。
- 工作区 /app/work；产物 /app/output/result.json（主）+ cleaned.csv / changelog.jsonl / pending_review.json / gain_evidence.json（辅助，内容已完整嵌入 result）。预算 64 次模型请求 / 900 秒 / 单响应 16384 token。
- 引擎命令一律用 `python3`（沙箱只有 python3.12，`python` 可能不存在）。脚本路径**不要写死**：先 `SCRIPT=$(find /skills /app -name clean_run.py 2>/dev/null | head -1)`，找不到再试 `ls /skills/*/scripts/clean_run.py`；仍找不到则按第4步内联手工执行同一清洗语义。
- 引擎子命令 skeleton|profile|run|check|evidence|selftest（零第三方依赖，异常全捕获，**任何路径退出码恒 0**，绝不让 Agent 因非零退出码中断）。
- 机检纪律：run/check 均执行 verify_result，每个校验点以 {item,template_value,applied,match} 三元组逐条嵌入 result.machine_checks；convert 变更逐条从 trace 复算 value_final==round(value_in×net_factor+offset,precision)（区间双端各算）写入 convert_spot_checks，不通过计入 fail（**verdict 照实嵌入，退出码恒 0，禁止中断交付**）；gates 每道闸门取 enforced/skipped_not_provided/not_found/unreadable 四态之一，未全部 enforced 时写 gate_note「下游不得宣称已核对」。
- 语义纪律：不同条件/来源上下文不错并（判定键含条件指纹）；字面换算不能替代科学冲突裁决；缺失保持空缺不编造；原值永不删除（__raw__ 影子 + changelog 双留痕）；**无法清洗的脏值逐条登记 uncertainties.dirty_values，绝不静默丢弃**。

## 1. 五步主流程（线性执行，不做分支漫游）

### 第1步 抄契约
1. 读 /input/case.json 与 task.md 全文（含评分维度表与「本版明确任务范围」）。
2. 抄下 output_contract 的每个键名（case.json 的 output_contract 字段，或 task.md「Skill 运行后的输出要求」表）；至少含 case_id/status/result/claims/uncertainties。
3. 记下：case_id、行数据所在键、行身份字段名（row_id/id）、是否有独立抽取记录文件。

### 第2步 落骨架（协议第 1 条的落地，立即执行）
```bash
python3 "$SCRIPT" skeleton --case /input/case.json --outdir /app/output
```
- 或手工写等价骨架：五字段齐全、status="partial"、contract 多出的键填 unknown/空数组。
- 之后每次写盘均覆盖为当前最新完整状态。

### 第3步 定规则（规则可改：改规则重跑即可）
```bash
python3 "$SCRIPT" profile --case /input/case.json --out /app/work/profile.json
```
1. 看 profile 的真实列名/单位/缺失/疑似重复/是否长表。
2. **优先直接用自动推导规则**（不手写、不烧预算）：`run` 时不给 `--rules` 即自动从输入列名别名与各列实际单位分布推导 FM/UC/SN/MM/DD 六类编号规则，每条带 rationale 与 on_fail。
3. 需要精细控制时，以 resources/rules-template.json 为模板实例化 /app/work/rules.json：FM 字段映射=字段规范；UC 单位换算=单位转换；SN 同义归一=同义词归一；MM 缺失标记+AF 异常标记=缺失与异常；DD 重复判定=重复记录；changelog 纪律=来源与变更记录（对应评分六方面）。
4. 每条规则含 rule_id/kind/priority/condition/action/rationale/on_fail；priority 小者先执行，冲突时先者生效并记录。
5. 规则分界：能写成条件+动作的（映射、换算、归一、判定键）→ 进规则库可改；规则写不动的（未知单位、同义跨组、科学冲突）→ 一律进 pending_review/human_review，不猜不裁决。

### 第4步 跑清洗（真实执行，禁止只写说明不产生产物）
```bash
python3 "$SCRIPT" run --case /input/case.json --rules /app/work/rules.json --outdir /app/output
```
- 产出并完整嵌入 result.json 的 result 字段：cleaned_table（含 row_id、__raw__ 原值影子、行级 __changes__ 台账索引）、changelog（逐格变更，convert 带 trace）、pending_review、dedup_report、missing_report、anomalies、conflicts、summary、rules_applied、field_mapping、efficiency。
- 三重留痕（逐条可核）：① 行级台账——每个被改格在 __raw__[field].ledger 内嵌 {change_id,kind,original,new,rule_id}，每行带 __changes__ 全部变更号，单行内即可核对全部改动，同时 result.changelog 保留全量台账；② 换算中间值——每条 convert 变更带 trace（factor_source=si_prefix|rule|identity、前后缀因子、net_factor、offset、value_in/value_out、precision、recompute 公式串），逐步复算可验证；③ 脏值登记——无法清洗的值（未知单位/不可解析格式）逐条进 uncertainties.dirty_values（row_id/field/value/reason/pending_id），原值保留不静默丢弃，与 pending_review 同号关联。
- 换算/归一/去重纪律：换算保留原值+公式+精度+trace；缺失保持空缺；重复判定键=(归一物质, 归一指标, 条件指纹)——键全同且值相容才合并为重复记录，条件指纹不同=重复实验绝不合并，同键异值=科学冲突只登记。
- run 末尾自动机检：verify_result 全量校验三元组 + 换算抽检机检 + 闸门四态，逐条嵌入 result.machine_checks 后才写盘；机检器异常时嵌入 unreadable 闸门如实登记，不假装通过。
- 脚本不可用时（找不到脚本/python3 缺失/引擎报错）：按本节产物结构内联手工执行同一清洗语义，绝不空手收尾；手工换算也必须写出 trace 中间值与脏值登记。

### 第5步 校验交付（校验点即预先定义的"算对"标准）
```bash
python3 "$SCRIPT" check --result /app/output/result.json --case /input/case.json
```
- 机检 FAIL 逐条修复后重跑**一轮**；仍失败则如实交付（**退出码恒 0**，verdict 照实嵌入 result.json，禁止以非零退出码结束会话）。check 把全部校验点以 {item,template_value,applied,match} 三元组逐条回写进 result.machine_checks（checks+convert_spot_checks+gates+problems+all_pass），评分器不开附件即可核对；problems 非空 ⇒ all_pass=false（照实嵌入）。
- 硬性校验点：JSON 可解析；output_contract 键一个不缺；case_id 与输入一致；changelog 条数=changed_cells；每条换算变更带 formula、precision 与 trace（含 value_out/net_factor 可复算）；每行 __changes__ 条数=该行 changelog 条数且 ledger 变更号一致；pending_review 非空 ⇒ uncertainties.human_review 非空；dirty_values 逐条登记且 == summary.unknown_units；rows_out=cleaned_table 行数=cleaned.csv 数据行数；status 如实。
- 闸门四态：case_read/contract_fields/rules_file/machine_verify 各取 enforced|skipped_not_provided|not_found|unreadable；没有跑 != 通过，任何非 enforced 闸门触发 gate_note「下游不得宣称已核对」。
- status 语义：清洗流程跑完且产物齐全=answered（待确认清单是交付物不是缺口，其数量与限制写进 uncertainties.summary）；处理中断/产物缺位/键填 unknown=partial（写明缺口）；无行数据=insufficient_evidence；输入不可解析=input_error。
- 交付前自查三问：每个被改动的值能沿 row_id+rule_id 回到原值吗（行内 ledger 即可核）？换算都带公式、精度与可复算 trace 吗？不敢确认的都逐条进 dirty_values/human_review 了吗？

### 第6步（有时间才做）增益对照：同输入双跑
```bash
python3 "$SCRIPT" evidence --case /input/case.json --rules /app/work/rules.json --outdir /app/output/evidence
```
- 同输入同规则真实跑多档：normal 全机制 vs ablate_unit/ablate_dirty/ablate_spot/ablate_dedup 单变量退化。
- 逐项对照指标（清洗正确率/换算错误漏检数/待人工核对条目数/步骤数/请求数）写入 result.result.gain_evidence，含机制→指标映射、边界与失效条件；换算错误漏检数用故障注入实测（污染结果→机检判→数漏检），不是估算。
- 对照是加分项，**不得因它挤占预算而拖延第1-5步与交付**；时间不够就跳过本步。

## 2. 输出 schema（result.json）

顶层五字段一个不缺：case_id / status（answered|partial|insufficient_evidence|input_error）
/ result / claims / uncertainties。extra 键按 case.json 的 output_contract 补。

result 内必含（完整 JSON 形态见 resources/result-schema.md）：cleaned_table（含 row_id、__raw__ 原值影子、__changes__ 台账索引、__units__）、changelog（逐格 change_id/row_id/field/original/new/rule_id/kind/formula/precision/trace）、pending_review（pending_id/kind/row_id/field/value/issue/suggest）、field_mapping（map+unmapped_fields+notes）、rules_applied、dedup_report（merged_groups+suspected_pairs）、missing_report、anomalies、conflicts、summary（12 项计数）、artifacts、check_standard（"算对"标准清单）、efficiency（可自动采集的效率计数+复现命令）、gain_evidence（双跑对照：机制→指标映射/逐项对照/边界/失效条件）、machine_checks（checks+convert_spot_checks+gates+problems+all_pass）。
三元组形态固定 {item, template_value, applied, match}；claims 每条带 claim_id/text/kind(reported|inferred)/source_id/location/evidence（逐字 quote）；uncertainties 六键固定 unreported/unverifiable/conflicts/human_review/dirty_values/summary。
复核式（机检逐条验）：换算 value_final == round(value_in × net_factor + offset, precision)，区间双端各算不取中点；每行 __changes__ 条数 == 该行 changelog 条数且 ledger 变更号在内；pending_review 非空 ⇒ human_review 非空；dirty_values 逐条登记且 == summary.unknown_units；rows_out == cleaned_table 行数 == cleaned.csv 数据行数。


## 3. 异常处置表（遇到即执行，不另行请示）

| 异常 | 处置 |
|------|------|
| 单位无法识别（解析失败/量纲不同） | 原值保留 + pending_review(kind=unknown_unit) + 逐条登记 dirty_values，不猜换算 |
| 同义冲突（成员跨组） | 双向登记 synonym_conflict，不归一，进 human_review |
| 缺失记号/空值 | 缺失→空缺不编造（missing_report）；越界→原值保留只标记（anomalies） |
| 编码错乱/列名全缺失 | 降级为逐行原样保留+全量待确认，status=partial/input_error，写明原因 |
| 空表（rows=0） | status=insufficient_evidence，summary 写明未发现行数据，骨架仍交付 |
| 重复记录 vs 重复实验 | 判定键含条件指纹：键全同且值相容→合并（kept_row_id+merged_row_ids）；指纹不同→绝不合并，登记 suspected_pairs 并逐条 dirty_values |
| 科学冲突（同键异值） | 只登记 conflicts+human_review，不裁决；字面换算不能替代科学裁决 |
| 长表输入（field/value/unit 三列） | 引擎自动透视成宽表；原始长表行留在 __source_rows__ 可逐行回溯 |
| 脚本/解释器不可用 | 按第4步产物结构内联手工执行同一清洗语义，绝不空手收尾 |
| 运行中断 | 按协议第 6 条仍写 result.json（status 如实+中断位置），绝不缺交付 |

## 4. 最小调用示例（示意，非正式答案）

输入（示意合成数据，非正式案例）：
```json
{"case_id": "demo-001", "records": [
  {"row_id": "r1", "source": "PaperA", "cap_ug_g": "250 ug/g", "condition": "25C pH7"},
  {"row_id": "r4", "source": "PaperA", "cap_ug_g": "250 ug/g", "condition": "25C pH7"},
  {"row_id": "r5", "source": "PaperB", "cap_ug_g": "12 xyz", "condition": "25C pH7"}]}
```
调用（示意）：
```bash
SCRIPT=$(find /skills /app -name clean_run.py 2>/dev/null | head -1)
python3 "$SCRIPT" skeleton --case /input/case.json --outdir /app/output
python3 "$SCRIPT" profile   --case /input/case.json --out /app/work/profile.json
# 据 profile 实例化 /app/work/rules.json（参照 resources/rules-template.json；也可不写→自动推导）
python3 "$SCRIPT" run       --case /input/case.json --rules /app/work/rules.json --outdir /app/output
python3 "$SCRIPT" check     --result /app/output/result.json --case /input/case.json
```
示意输出（示意/非正式，仅说明接口形态）：status="answered"；r1 的换算格内嵌 ledger={change_id:"C0001",original:"250 ug/g",new:0.25,rule_id:"UC01"} 与 trace（src_prefix_factor=1e-6、dst_prefix_factor=1e-3、net_factor=0.001、recompute="250 x (1e-06/0.001) +0 = 0.25"，可复算）；r4 以 kind="merge" 进 changelog；r5 的 "12 xyz" 无法清洗→pending P 项 + uncertainties.dirty_values 逐条登记（原值保留）。真实结果以 3 个固定案例实际运行为准。

## 5. 已知限制与维护

- 科学冲突只登记不裁决（裁决需领域判断）；温标等仿射换算须规则显式给 factor+offset；
  跨维度换算（质量↔摩尔、mg/L↔mg/g）不猜，须规则给显式系数；ppm↔mg/L 依赖密度，
  仅当规则显式声明近似系数才换算并在 rationale/claims 标注"近似"。
- 编码错乱/列名全缺失/嵌套过深时降级为原样保留+全量待确认，不强行清洗。
- dirty_values 是登记不是豁免：原值仍留在表中，统计时由使用者决定排除；引擎不改写不删除。
- 换一批表/换列名：改 rules.json 的 condition.column 与字段字典即可重跑，无需改代码；
  或不给 --rules 让引擎按新列名自动推导；重复运行结果一致（规则按 (priority,rule_id) 稳定排序，无随机性）。
- 维护：规则增删改只动 rules.json；单位换算表见 resources/units-table.md；
  输出契约见 resources/result-schema.md；引擎版本在 result.engine。
