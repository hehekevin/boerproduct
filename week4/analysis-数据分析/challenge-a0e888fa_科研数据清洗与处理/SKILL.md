---
name: sciclean-r1
description: 科研数据清洗与处理 Skill：数据字典+清洗工单驱动的规则事前声明式清洗，覆盖缺失值/异常值/重复记录/格式与单位转换/数据质量报告五类处理。每处修改留审计链（改前/改后/规则/依据逐条内嵌行级台账，row_id+rule_id 可回放），换算带公式、精度与 trace 中间值可复算，行数守恒与换算汇总守恒机检防静默删行/篡改；不可修复项逐条登记 dirty_values 不静默丢弃，缺失保持空缺绝不按均值或总体统计推断填补；全量机检以 {item,template_value,applied,match} 三元组嵌入 result.machine_checks，闸门四态显式枚举；支持 --ablate 多档退化与三型污染注入（篡改数值/静默删行/剥离审计）双跑增益对照。触发词：科研数据清洗、数据质量报告、缺失值、异常值、重复记录、单位换算、数据字典、清洗工单、审计链、changelog。
---

## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 7 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

1. 第0步先落盘骨架：读完 /input/case.json 与题面后，第一个写盘动作就是在 /app/output/result.json 写入骨架——case_id 取自 case.json；键名严格按 case.json 或 task.md 的 output_contract 声明逐个生成（无法完成的值填 unknown 或空数组，绝不省略键）；status 填部分完成值。此后任何时刻 /app/output/result.json 必须存在且 JSON 可解析。
2. 字段一个不缺：最终 result.json 必须包含 output_contract 的全部键；确实无法产出时保留键并填 unknown/空数组/说明字符串，原因写进 uncertainty，绝不删键、绝不编造数据。
3. 广度优先：先让全部要求的产物以最小合格版本存在，再对高价值部分加深；禁止在单一产物上耗尽预算。
4. 预算保护：模型请求已用超过 48 次或运行时间超过 700 秒时，立即停止新增处理，用现有中间结果完成 result.json 并收尾；每次写 result.json 都覆盖为当前最新完整状态。
5. 最终写盘前自检：JSON 可解析、output_contract 字段一个不缺、case_id 与输入一致、status 如实；不过先修复再交付。
6. 失败也要交付：中断或失败时仍写 result.json（status 如实降级，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。
7. 每步一个写盘动作：每完成一步立即把 /app/output/result.json 覆盖为当前最新完整状态（含 machine_checks 机检三元组），不留只在内存或日志里的结果。

## 0. 契约速览

- 输入 /input/case.json（聚合表转录：数据字典、逐指标单位/QC 规则、清洗工单；组织方注入的存储/编码故障均有明确身份）。行数据若在独立文件（csv/tsv/json/jsonl）用 `--rows <文件>` 传入；长表（field/value/unit 三列）自动透视成宽表。
- 工作区 /app/work；产物 /app/output/result.json（主）+ cleaned.csv / changelog.jsonl / pending_review.json / gain_evidence.json（辅助，内容已完整嵌入 result）。预算 64 次模型请求 / 900 秒 / 单响应 16384 token。
- 引擎命令一律用 `python3`（沙箱只有 python3.12，`python` 可能不存在）。脚本路径**不要写死**：先 `SCRIPT=$(find /skills /app -name clean_run.py 2>/dev/null | head -1)`，再校验命中标志 `grep -q "sciclean-r1" "$SCRIPT"`（校验式命中，防找错文件）；找不到再试 `ls /skills/*/scripts/clean_run.py`；仍找不到则按第4步内联手工执行同一清洗语义。
- 引擎子命令 skeleton|profile|run|check|evidence|selftest（零第三方依赖，异常全捕获，**任何路径退出码恒 0**，绝不让 Agent 因非零退出码中断）。
- 机检纪律：run/check 均执行 verify_result，每个校验点以 {item,template_value,applied,match} 三元组逐条嵌入 result.machine_checks；convert 变更逐条从 trace 复算 value_final==round(value_in×net_factor+offset,precision)（区间双端各算）写入 convert_spot_checks；**守恒机检**：行数守恒（rows_in==rows_out+合并行数，防静默删行）与换算汇总守恒（sum(new)==sum(trace.value_final)，防篡改）逐条三元组嵌入；闸门四态 enforced/skipped_not_provided/not_found/unreadable，未全部 enforced 写 gate_note「下游不得宣称已核对」。**verdict 照实嵌入，退出码恒 0，禁止中断交付**。
- 语义纪律：规则事前声明（工单与字典翻译成 rules.json 或用自动推导并留痕 rules_applied）；每处修改留审计链（改前/改后/规则/依据）；缺失保持空缺**绝不按均值或总体统计推断填补**（「未检测」「低于检出限」「录入缺失」「真值 0」四类分册登记不混淆）；原值永不删除（__raw__ 影子 + changelog 双留痕）；无法清洗的脏值逐条登记 uncertainties.dirty_values。

## 1. 五步主流程（线性执行，不做分支漫游）

### 第1步 抄契约
1. 读 /input/case.json 与 task.md 全文（含数据字典、逐指标单位/QC 规则、清洗工单）。
2. 抄下 output_contract 每个键名；至少含 case_id/status/result/claims/uncertainties。
3. 记下：case_id、行数据所在键、行身份字段（row_id/sample_id）、字典 QC 范围与工单条目。

### 第2步 落骨架（协议第 1 条的落地，立即执行）
```bash
python3 "$SCRIPT" skeleton --case /input/case.json --outdir /app/output
```

### 第3步 定规则（规则事前声明：先声明后执行，全程可审计）
```bash
python3 "$SCRIPT" profile --case /input/case.json --out /app/work/profile.json
```
1. 看 profile 的真实列名/单位分布/缺失/疑似重复/是否长表。
2. **把清洗工单逐条翻译成规则**：以 resources/rules-template.json 为模板实例化 /app/work/rules.json——UC=工单的单位换算条目（带依据=工单条目号）；AF=字典 QC 范围（物理上下限，只标记不改动）；DD=样品编号等真实主键+条件指纹；MM=缺失记号分册；FM=字典列名映射。每条规则必含 rule_id/kind/priority/condition/action/rationale（写明依据出处）/on_fail。
3. 时间紧张可不写规则文件：`run` 不给 `--rules` 即自动从列名别名与各列单位分布推导（留痕 rules_source=auto_derived），但显式规则的依据更可审计，优先显式。
4. 规则写不动的（未知单位、同义跨组、科学冲突）→ 进 pending_review/human_review，不猜不裁决。

### 第4步 跑清洗（真实执行，禁止只写说明不产生产物）
```bash
python3 "$SCRIPT" run --case /input/case.json --rules /app/work/rules.json --outdir /app/output
```
- 产出并完整嵌入 result：cleaned_table（含 __raw__ 影子/行级 ledger/__changes__/__units__）、changelog（逐格台账，convert 带 trace）、pending_review、dedup_report、missing_report、anomalies、conflicts、summary、rules_applied、field_mapping、efficiency。
- 三重留痕：① 行级台账——被改格 __raw__[field].ledger 内嵌 {change_id,kind,original,new,rule_id}，单行可核全部改动；② 换算中间值——每条 convert 带 trace（net_factor/offset/前后值/precision/recompute 公式串）可复算；③ 脏值登记——无法清洗的值逐条进 uncertainties.dirty_values，原值保留不静默丢弃。
- run 末尾自动机检：全量三元组 + 换算抽检复算 + **行数守恒与换算汇总守恒** + 闸门四态，逐条嵌入后才写盘。
- 异常值纪律：越界值只标记（anomalies + pending）不改数值——异常可能是真实高值，保留/剔除/盖帽由人工按 issue 建议核实。
- 脚本不可用时：按本节产物结构内联手工执行同一清洗语义，绝不空手收尾；手工换算也必须写出 trace 与脏值登记。

### 第5步 校验交付（机检 FAIL 修复一轮后重跑 check）
```bash
python3 "$SCRIPT" check --result /app/output/result.json --case /input/case.json
```
- 机检 FAIL 逐条修复后重跑一轮；仍失败则如实交付（**退出码恒 0**，verdict 照实嵌入，禁止非零退出码结束会话）。
- 硬性校验点：JSON 可解析；output_contract 键一个不缺；case_id 一致；changed_cells==changelog 条数；每条换算带 formula/precision/trace 且可复算；**行数守恒与换算汇总守恒成立**；每行 __changes__==该行 changelog 条数且 ledger 内嵌（审计链逐条可回放）；pending 非空⇒human_review 非空；dirty_values 逐条登记==unknown_units；rows_out==表行数==csv 行数；status 如实。
- status 语义：流程跑完且产物齐全=answered（待确认清单是交付物不是缺口）；中断/缺位/键填 unknown=partial；无行数据=insufficient_evidence；输入不可解析=input_error。
- 数据质量报告自洽：summary 12 项计数与 cleaned.csv/changelog/pending 逐项对得上（机检自动验），报告数字与结果表不一致=FAIL。
- 交付前三问：每个被改的值能沿 row_id+rule_id 回到原值吗？换算都带可复算 trace 吗？不敢确认的都逐条登记了吗？

### 第6步（有时间才做）增益对照：同输入双跑
```bash
python3 "$SCRIPT" evidence --case /input/case.json --rules /app/work/rules.json --outdir /app/output/evidence
```
- 同输入同规则真实跑多档：normal vs ablate_unit/dirty/dedup/anomaly/audit/spot/conserve 单变量退化，逐项指标差写入 result.gain_evidence 与 efficiency。
- 三型污染注入实测：篡改换算值/静默删行/剥离审计台账 注入同一污染副本，各档机检开关各判一次，报 caught/missed——不是估算。
- 对照是加分项，不得挤占第 1-5 步与交付；时间不够就跳过本步。

## 2. 输出 schema（result.json）

顶层五字段一个不缺：case_id / status（answered|partial|insufficient_evidence|input_error）/ result / claims / uncertainties；extra 键按 case.json 的 output_contract 补。result 完整形态见 resources/result-schema.md：cleaned_table（含 row_id/__raw__/ledger/__changes__/__units__）、changelog（change_id/row_id/field/original/new/rule_id/kind/formula/precision/trace）、pending_review、field_mapping、rules_applied、dedup_report、missing_report、anomalies、conflicts、summary（12 项计数）、artifacts、check_standard、efficiency、gain_evidence、machine_checks（checks+convert_spot_checks+gates+problems+all_pass）。三元组固定 {item,template_value,applied,match}；claims 每条带 claim_id/text/kind/source_id/location/evidence（逐字 quote）；uncertainties 六键固定 unreported/unverifiable/conflicts/human_review/dirty_values/summary。

## 3. 异常处置表（遇到即执行，不另行请示）

| 异常 | 处置 |
|------|------|
| 单位无法识别/量纲不同 | 原值保留 + pending(kind=unknown_unit) + 逐条登记 dirty_values，不猜换算 |
| 缺失记号/空值 | 保持空缺不填补（missing_report）；「未检测」「-999」「空格」分类登记不混作真值 0 |
| 越界异常 | 原值保留只标记（anomalies+pending），异常可能是真实高值，人工核实 |
| 重复记录 vs 重复实验 | 判定键含条件指纹：键全同且值相容→合并（kept_row_id+merged_row_ids）；指纹不同绝不合并，登记 suspected_pairs |
| 同键异值（科学冲突） | 只登记 conflicts+human_review，不裁决 |
| 编码错乱/列名全缺失 | 降级为逐行原样保留+全量待确认，status=partial/input_error |
| 空表（rows=0） | status=insufficient_evidence，骨架仍交付 |
| 行被合并 | 行数守恒机检：rows_in==rows_out+合并行数；守恒不成立=有静默删行=FAIL |
| 脚本/解释器不可用 | 按第4步产物结构内联手工执行同一清洗语义，绝不空手收尾 |
| 运行中断 | 按协议第 6 条仍写 result.json（status 如实+中断位置），绝不缺交付 |

## 4. 最小调用示例（示意，非正式答案）

```bash
SCRIPT=$(find /skills /app -name clean_run.py 2>/dev/null | head -1); grep -q sciclean-r1 "$SCRIPT" || SCRIPT=$(ls /skills/*/scripts/clean_run.py 2>/dev/null | head -1)
python3 "$SCRIPT" skeleton --case /input/case.json --outdir /app/output
python3 "$SCRIPT" profile   --case /input/case.json --out /app/work/profile.json
# 按数据字典+清洗工单实例化 /app/work/rules.json（参照 resources/rules-template.json）
python3 "$SCRIPT" run       --case /input/case.json --rules /app/work/rules.json --outdir /app/output
python3 "$SCRIPT" check     --result /app/output/result.json --case /input/case.json
```
示意输入（examples/example-case.json，合成数据非正式案例）：s01 "250 ug/L" → 0.25 mg/L（UC01，trace 可复算）；s02 与 s01 主键+条件全同→合并（DD01）；s03 "12 xyz" 脏值登记不丢弃；s04 "80 mg/L" 超 QC 上限只标记（AF01）；s05 空白缺失保持空缺（MM01）；s06 区间 "3.1-4.4 mg/L" 双端定型不取中点。示意输出见 examples/example-result.json（真实跑结果，run+check 30/30 match）。真实结果以 3 个固定案例实际运行为准。

## 5. 已知限制与维护

- 科学冲突只登记不裁决；温标等仿射换算须规则显式给 factor+offset；跨维度换算（mg/L↔mg/g）与密度依赖换算（ppm↔mg/L）不猜，须规则显式声明并在 rationale 标注。
- 不做统计建模/假设检验/图表排版/数据库运维；不推断总体统计，不填补缺失或无效源值——只登记、标记、留痕。
- 换表/换列名：改 rules.json 的 condition 与 field_dictionary 即可重跑，无需改代码；重复运行结果一致（规则按 (priority,rule_id) 稳定排序，无随机性）。
- 维护：规则增删改只动 rules.json；单位表见 resources/units-table.md；输出契约见 resources/result-schema.md；引擎版本在 result.engine。
