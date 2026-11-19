# exp-result-explain — 实验结果解释与异常分析 Skill

把一批实验读数解释成**五段可检查的结论**：结果趋势、异常点、可能原因、复核步骤、后续实验建议，并对齐研究假设（supported / partially_supported / not_supported / unassessable）。每条解释绑定逐字数据证据，异常-原因一一配对，复核步骤第二个人可执行。

## 0. 最小自检清单（本仓库实测记录）

```bash
# ① 结构与口径落骨架（退出码 0）
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
# ② 趋势/异常机械复算（退出码 0，all_match=True）
python3 scripts/trend_anomaly_check.py --result examples/example-result.json --case examples/example-case.json
# ③ 配对/回证/可执行性汇总（退出码 0）
python3 scripts/explain_rollup.py --result examples/example-result.json --rules /tmp/wk/judge_rules.json
# ④ 增益对照 + 9 类污染注入（退出码 0，caught 9/9）
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
# ⑤ 主校验器（退出码恒 0；判据看 verdict=PASS）
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --rules /tmp/wk/judge_rules.json --out /tmp/vc.json --emit-into
# ⑥ 契约守卫（退出码恒 0；verdict=PASS）
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/sg.json
```

2026-11-19 实测：六条命令退出码全部为 0；verify_check verdict=PASS（0 问题）；schema_guard verdict=PASS；trend_anomaly_check all_match=true。失败路径（result.json 缺失/损坏、case.json 缺失）同样实测退出码恒 0，报告内 verdict=FAIL。

## 1. 输入格式

平台挂载后自动读取（无需手工准备）：

| 文件 | 说明 |
|------|------|
| `/input/case.json` | 案例输入：`case_id`、`output_contract.fields`（契约字段名）、数据集（`datasets`/`series`/`traces`/`records` 等键，元素含 `dataset_id`、`title`、`description`、`values` 数值序列，序列元素可为数字或含 `value` 字段的字典）、研究假设（`hypotheses`，含 `hypothesis_id`/`text`，可选） |
| `/input/task.md` | 任务题面 |

**以实际文件为准，不依据标签假设内容。**

## 2. 输出格式（/app/output/result.json 顶层键）

- `case_id` / `status`（answered·partial·insufficient_evidence·input_error）/ `result`（业务主体）
- `claims`（证据链：每条含 claim_id/text/kind/source_id/location/evidence[]，引文逐字）
- `uncertainties`（unreported/unverifiable/conflicts/human_review/summary）
- `changelog`（步骤级变更记录）
- `self_check` / `gates` / `unbacked_numbers` / `unbacked_evidence` / `validator_verdict`（由 verify_check.py 回写）

## 3. result 内关键字段含义

| 字段 | 归属 | 含义 |
|------|------|------|
| `analysis_scope` | build_skeleton+Agent | 解释范围、假设引用、单位口径 |
| `checklist` | 同上 | 五分面清单（trend/anomaly/cause/recheck/followup） |
| `judge_rules` | 同上 | **事前声明**的判读口径：对齐规则、检测阈值、原因类别、配对/回证/可执行规则 |
| `analyses[]` | Agent | 每组序列：trend / anomalies / causes / rechecks / followups / alignment / appraisals |
| `trend_anomaly_check` | 仅 trend_anomaly_check.py | 从原始读数复算方向/离群/跳变/平台并与 claimed 对照 |
| `explain_summary` | 仅 explain_rollup.py | 配对完备性、无证据解释、可执行复核数、对齐一致性 |
| `coverage` / `pending_review` / `verdict` | build_skeleton+Agent | 覆盖统计、弃权登记、交付结论 |
| `gain_evidence` / `efficiency` | 仅 gain_probe.py | 正常 vs 退化消融实测差 + 污染注入抓捕 + 墙钟/字节 |

多脚本**禁写同一键**：上表"归属"列即唯一写者。

## 4. 判定阈值（默认口径，judge_rules.detection_thresholds 可事前改写）

| 阈值 | 默认 | 含义 |
|------|------|------|
| `outlier_z` | 3.0 | \|z\|>3.0 判离群（z 用样本 sd） |
| `jump_rel` | 0.5 | 相邻读数相对变化 >50% 判跳变 |
| `plateau_min_points` | 3 | 连续 ≥3 点判平台段 |
| `plateau_tol_rel` | 0.05 | 段内相邻相对变化 ≤5% |
| 方向 | — | rel=slope×(n-1)/\|mean\|；\|rel\|<0.05 记 flat |

## 5. 五段输出定义

1. **趋势**：direction / inflection_points / plateau / magnitude，附方法与逐字证据；
2. **异常点**：定位到对象（样本/批次/通道/孔位/时间点 + 索引）、anomaly_type(outlier/jump/plateau)、severity、threshold_used、偏离幅度；
3. **可能原因**：instrument/operation/sample/environment 四类，按证据强度排序，supporting+excluding 证据齐备，**相关≠因果必须写进 correlation_note**；
4. **复核步骤**：action+target_file+target_field/method+expected_outcome 四要素，缺一即判不可执行，"检查数据质量"类空话直接拒绝；
5. **后续实验建议**：绑定 cause_ids，给出具体改动与依据。

对齐判定四档：方向一致且无未决异常⇒supported；一致但有未决⇒partially_supported；相反/矛盾⇒not_supported；数据不足⇒unassessable（须登记 pending_review）。supported 与负面/弃权条目并存即校验 FAIL。

## 6. 调用方式（Agent 执行流）

Step 0 落骨架 → Step 1 声明 judge_rules（declared_at 落台账，此后禁改）→ Step 2 五段解释回填 → Step 3 机械复算 → Step 4 汇总+证据链 → Step 5 增益对照 → Step 6 自检（看 verdict 不看退出码）。全部命令见 SKILL.md「七步流程」。

## 7. 依赖与限制

- 零外部依赖：仅 Python 标准库（json/math/os/re/statistics 语义），命令一律 `python3`，不装 pip 包。
- 资源：6 个脚本 + 2 个示例文件 + 本 README + worklog + SKILL.md，共 11 个 UTF-8 文本文件（限额 50 个/2MB 内）。
- 平台运行：脚本挂载于 `/skills/weekly-skill/`，输入 `/input/`，产出 `/app/output/result.json`；所有脚本退出码恒 0，失败写进报告 verdict/problems。
- z 分数对小样本偏保守，可能漏报边缘离群（登记 pending_review 处理，不冒充 Grubbs/ISO 标准）。

## 8. 复用模板

- `judge_rules`（阈值/类别/规则）可直接作为其他解释类任务的口径模板；
- `checklist` 五分面清单与 `recheck` 四要素模板可直接复制到复核清单；
- `examples/example-case.json` 的数据组织方式（description 内植原文句子 + values 数值序列）可作为构题模板。

## 9. 典型案例

`examples/` 为**示意案例（数据与引文全部虚构，非正式答案）**：ds-bend-01（12 读数含 1 个 z=3.16 离群点，趋势 flat）、ds-temp-02（16 采样点含跳变+平台期，原因定级弃权）。跑通第 0 节六条命令即可复现全部指标。

## 10. 已知边界（诚实声明）

- 方向"flat"口径（|rel|<0.05）与平台期容差法是声明口径，非变点检验/拟合检验；
- 增益对照是本校验层正常 vs 退化两模式与污染注入，**不等于**平台基础 Agent 对照；白板对照由平台生成；
- 引文回证要求逐字命中 case.json 序列化文本，来源若为外部位图/扫描件则登记 unavailable，不臆造；
- `model_requests` 由 Agent 按实际请求数回填，示例中保持 null。

## 11. 自检失败怎么办

verify_check/schema_guard 报 FAIL 时：按 `problems` 列表逐条修复 → 覆盖写 result.json → 重跑直到 PASS。常见修复：补 evidence_quote（逐字）、补 cause 配对、把 vague 复核改写为四要素齐备、对齐判定降级、补 pending_review。修不了就如实登记 uncertainties 并将 status 置 partial——**绝不删键、绝不编数据、绝不中断交付**。
