# sciclean-r1 — 科研数据清洗与处理 Skill（README）

对应赛道：week4「科研数据分析」之「科研数据清洗与处理」（challenge-a0e888fa）。

在 week3 冠军骨架（clean2table-r5，文献数据清洗）机制之上做科研数据清洗领域化：

1. **规则事前声明**：数据字典 + 清洗工单逐条翻译成 rules.json（每条带 rationale 依据出处与 on_fail），先声明后执行；不给规则时引擎自动推导并留痕。
2. **审计链完整**：每处修改内嵌行级台账（改前/改后/规则/依据），row_id+rule_id 逐条可回放；换算带公式、精度与 trace 中间值可复算。
3. **数据完整性守恒机检（新增）**：行数守恒（rows_in == rows_out + 合并行数，防静默删行）+ 换算汇总守恒（sum(new) == sum(trace.value_final)，防篡改/复算失真）逐条三元组嵌入 machine_checks。
4. **不填补纪律（新增）**：缺失保持空缺，绝不按均值或总体统计推断填补；「未检测/低于检出限/录入缺失/真值 0」分册登记。
5. **三型污染注入（增强）**：篡改数值/静默删行/剥离审计台账注入同一污染副本，同输入双跑实测各档抓出与漏检数。

---

## 1. 最小可运行自检清单（复制即跑，实测退出码全 0）

```bash
# ① 全链路自检：skeleton→profile→run→check→evidence 依次实跑（用自带示例）
python3 scripts/clean_run.py selftest --outdir /tmp/sc-selftest
# 期望末行：[selftest] 结论: PASS

# ② 画像：看真实列名/单位分布/缺失/疑似重复（换成你的 case.json）
python3 scripts/clean_run.py profile --case /input/case.json --out /app/work/profile.json

# ③ 清洗并产出 result.json（--rules 传工单翻译出的规则；不给则自动推导）
python3 scripts/clean_run.py run --case /input/case.json --rules /app/work/rules.json --outdir /app/output

# ④ 机检：三元组逐条回写 result.json（FAIL 也返回 0，verdict 照实嵌入）
python3 scripts/clean_run.py check --result /app/output/result.json --case /input/case.json
# 期望：[check] PASS（…） 或 [check] FAIL（n 处，已嵌入 result.json）

# ⑤ 增益对照：同输入多档双跑 + 三型污染注入，写入 /app/output/evidence/gain_evidence.json
python3 scripts/clean_run.py evidence --case /input/case.json --rules /app/work/rules.json --outdir /app/output/evidence
```

脚本定位（不要写死路径）：`SCRIPT=$(find /skills /app -name clean_run.py 2>/dev/null | head -1)`，
再校验命中标志 `grep -q sciclean-r1 "$SCRIPT"`（校验式命中，防找错文件）；找不到按 SKILL.md 第 4 步内联手工执行同一语义。

---

## 2. 依赖版本与安装

| 项 | 要求 |
|---|---|
| Python | ≥3.8（沙箱实测 3.12） |
| 第三方依赖 | **零**（仅标准库 argparse/csv/json/os/re/sys/time/hashlib/shutil/traceback） |
| 安装 | 无需安装；平台装入 `/skills/weekly-skill` 后脚本位于 `scripts/clean_run.py` |
| 编码 | 全文件 UTF-8；读入自动尝试 utf-8-sig/utf-8/gbk/latin-1；输出 ensure_ascii=false |

---

## 3. 输入与输出

**输入**：`/input/case.json`（数据字典、逐指标单位/QC 规则、清洗工单、聚合表转录记录）；
可选 `--rows <csv/tsv/json/jsonl>`；可选规则文件 `/app/work/rules.json`。

**输出**：`/app/output/result.json`（主产物，契约字段+result 全量内嵌，评分器不开附件即可核对）、
`cleaned.csv`（清洗后可统计宽表）、`changelog.jsonl`（逐格台账）、`pending_review.json`（待人工确认）、
`evidence/gain_evidence.json`（双跑对照）。字段语义见 `resources/result-schema.md`。

---

## 4. 五类处理怎么做（对应评分五方面）

| 处理 | 机制 | 依据留痕 |
|---|---|---|
| 缺失值 | 记号分册识别（空格/-999/未检测/N/A…），保持空缺不填补，missing_report 逐格登记 | MM 规则 rationale=字典/工单出处 |
| 异常值 | 字典 QC 物理上下限+允许值集合判定，只标记不改动（异常可能是真实高值） | AF 规则 min/max + anomalies.issue |
| 重复记录 | 主键+条件指纹判定：键全同且值相容才合并；指纹不同绝不合并；同键异值只登记 | DD 规则 key_fields/context_fields + dedup_report |
| 格式与单位转换 | SI 前缀自动净因子、仿射显式 factor+offset、区间双端不取中点、数值定型不丢精度 | UC 规则 + trace 公式串可复算 |
| 数据质量报告 | summary 12 项计数与结果表/台账机检自动核对，报告数字不一致=FAIL | machine_checks.checks 三元组 |

---

## 5. 验收标准（check 子命令逐条跑成三元组）

1. output_contract 字段一个不缺；case_id 一致；status 四级合法。
2. changed_cells == changelog 条数；rows_out == 表行数 == cleaned.csv 行数。
3. **行数守恒**：rows_in == rows_out + 合并行数（防静默删行）。
4. **换算汇总守恒**：sum(new) == sum(trace.value_final)（防篡改）。
5. 每条 convert：value_final == round(value_in×net_factor+offset, precision)，区间双端各算。
6. 每行 __changes__ == 该行 changelog 条数；换算/归一/缺失格内嵌 ledger（审计链可回放）。
7. pending 非空 ⇒ human_review 非空；dirty_values 逐条登记 == unknown_units。
8. 闸门四态显式枚举，非 enforced 写 gate_note。**problems 非空 ⇒ all_pass=false，退出码恒 0。**

---

## 6. 最小调用示例（示意，非正式答案）

输入 `examples/example-case.json`（合成聚合表，含字典+工单+6 行记录）。调用见第 1 节 ③④⑤。
示意输出 `examples/example-result.json`（真实跑结果）：6 行进 5 行出，s01 "250 ug/L"→0.25（UC01，
trace 可复算）；s01/s02 主键+条件全同合并（DD01）；s03 "12 xyz" 脏值登记（dirty_values+P 项）；
s04 "80 mg/L" 超上限只标记（AF01）；s05 空白缺失保持空缺（MM01）；s06 区间双端定型。
check 结果 30/30 match、all_pass=true。

---

## 7. 增益证据怎么读（同输入双跑，实测对照数字见 worklog.md）

| 档 | 关闭机制 | 实测指标差（示例案例） |
|---|---|---|
| ablate_unit | 单位换算 | convert 9→0；且无归一导致去重失效（merged 1→0） |
| ablate_dirty | 脏值登记 | dirty_values 1→0（静默丢弃）；机检 problems 0→2 |
| ablate_dedup | 重复判定 | merged 1→0，rows_out 5→6 |
| ablate_anomaly | 异常检测 | anomalies 2→0，pending 3→1 |
| ablate_audit | 审计台账 | 机检 problems 0→7（审计链缺失被逐条抓出），all_pass=false |
| ablate_spot | 换算抽检 | 污染抓出 15→4，漏检 1→12 |
| ablate_conserve | 守恒校验 | 污染抓出 15→14，漏检 1→2 |

污染注入（injected=16：篡改数值 13/静默删行 1/剥离审计 2）由 `_inject_faults` 生成同一污染副本，
各档机检开关各判一次统计 caught/missed——实测非估算。抽检上限每档 8 条，守恒与抽检互为冗余防线。

---

## 8. FAQ

**Q：check 报 FAIL 是不是失败了？** 不是。FAIL 照实嵌入 machine_checks.problems 与 all_pass=false，
退出码仍 0；修复一轮重跑即可，仍失败如实交付。

**Q：规则文件没写会怎样？** 自动推导（rules_source=auto_derived）；想精细控制照
resources/rules-template.json 实例化，每条规则带依据出处。

**Q：会填补缺失吗？** 不会。缺失保持空缺只登记；题目明令不做总体统计推断、不填补缺失/无效源值。

**Q：两条数值一样的记录会合并吗？** 必须主键+条件指纹全同且值相容才合并；指纹不同=重复实验绝不合并。

**Q：换输入要重跑对照吗？** 要。对照只在同输入同规则下成立；换输入重跑 evidence 即可，命令见 gain_evidence.reproduce。

---

## 9. 限制

科学冲突只登记不裁决；仿射/跨维度换算须显式系数；编码错乱/列名全缺失时降级原样保留+全量待确认；
dirty_values 是登记不是豁免（原值留在表中，统计时由使用者决定排除）；抽检上限每档 8 条换算。

## 10. 失败处理

| 失败点 | 行为 |
|---|---|
| 输入不可解析 | status=input_error，仍写 result.json |
| 无行数据 | status=insufficient_evidence，骨架齐全 |
| 规则缺失/损坏 | 自动推导档继续 |
| 机检器自身异常 | gates.machine_verify=unreadable，如实登记不假装通过 |
| 任何异常路径 | 退出码恒 0，/app/output 不缺 result.json |

## 11. 复用建议

先跑 profile 看列名/单位分布 → 把字典与工单翻译进 rules-template.json（不改代码）→ run+check →
有预算再 evidence。换表只改 rules.json；脏值登记归档可作下次规则素材（examples/ 即最小样本）。

## 12. 版本与维护

Skill 版本 sciclean-r1；引擎版本写在 result.engine；规则模板版本在 rules-template.json 的 version；
变更记录见 worklog.md。引擎改动后跑 selftest 确认 5 步全 0。

## 13. 文件清单

| 文件 | 作用 |
|---|---|
| SKILL.md | Skill 本体：强制协议+五步流程+schema+异常表+限制（112 行） |
| scripts/clean_run.py | 清洗引擎（skeleton/profile/run/check/evidence/selftest，零依赖，退出码恒 0） |
| resources/rules-template.json | 规则模板（UC/SN/AF/DD/MM/FM 六类+字段字典+冲突策略） |
| resources/units-table.md | 单位换算表：SI 前缀、常见线性换算、不猜边界 |
| resources/result-schema.md | result.json 完整形态与机检复核式 |
| examples/example-case.json | 最小示例输入（合成聚合表：字典+工单+记录） |
| examples/example-rules.json | 配套规则（selftest 复用） |
| examples/example-result.json | 示例输出（真实跑结果，标注示意非正式答案） |
| README.md | 本文件 |
| worklog.md | 迭代记录（真实对照数字） |
