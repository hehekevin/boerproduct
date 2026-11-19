# worklog — challenge-8354c69a（exp-result-explain 制作记录）

日期：2026-11-19。本题：实验结果解释与异常分析（experiment 实验方案设计赛道收官题）。
交付：保底版（五段解释 + 机械复算 + 四项机检）+ 增益层（消融双跑 + 污染注入 + 生态文档）。

## 一、改动文件清单（相对空目录，全部新建）

| 文件 | 说明 |
|------|------|
| `SKILL.md` | 148 行（限额 150），含合法 YAML frontmatter（name/description） |
| `scripts/build_skeleton.py` | Step 0 落骨架：提取 output_contract 全字段与序列清单，预填五分面清单与 judge_rules 模板 |
| `scripts/trend_anomaly_check.py` | Step 3 机械复算：最小二乘方向 / z 离群 / 相对跳变 / 连续平台段，与 claimed 对照 |
| `scripts/explain_rollup.py` | Step 4 机械汇总：配对完备性 / 回证 / 可执行复核 / 对齐一致性 / speculation_only |
| `scripts/gain_probe.py` | Step 5 增益对照：正常 vs 退化双跑（清洁 + 污染副本各两遍）+ 9 类污染注入 |
| `scripts/verify_check.py` | Step 6 主校验器八组：enum/coverage/alignment/pairing/evidence/recheck/anomaly_check/structure |
| `scripts/schema_guard.py` | 契约守卫：output_contract 全字段 + 业务 schema 结构校验 |
| `examples/example-case.json` | 示意案例（虚构，标注非正式答案） |
| `examples/example-result.json` | 示意输出（由脚本真实跑出后固化） |
| `README.md` | 生态十项 + 最小自检清单（实测记录） |

合规数字：脚本 6/8，文件 11/50，总体积约 148KB / 2MB，零外部依赖，命令一律 python3，无 symlink。

## 二、真实对照数字（2026-11-19 本机实测，Python 3.13.14）

示例链路六命令退出码全部 0：

| 指标 | 数值 |
|------|------|
| trend_anomaly_check.all_match | true（方向 flat/increasing、离群 values[5]、跳变 values[7]、平台 [7,15] 全部与复算一致） |
| explain_summary.totals | pairing_complete=2/2，unbound_total=0，executable_rechecks=2，alignment_inconsistent=0，speculation_only=0 |
| gain：清洁输入 normal vs degraded(--ablate all) | 0 vs 0 问题（清洁数据两组都过，delta=0，如实记录） |
| gain：污染副本 normal vs degraded | **9 vs 1** 问题；delta_polluted = total **8**（alignment +1，pairing +2，evidence +3，recheck +2；enum 恒开不计入消融差） |
| 污染注入抓捕 | **9/9** caught_by_normal_mode=true（异常删原因、解释删证据、对齐越级、复核空话、篡改数字、类别非法、清空 pending_review、删对象绑定、编造引文） |
| verify_check | verdict=PASS（0 问题），unbacked_numbers=[]，unbacked_evidence=[] |
| schema_guard | verdict=PASS |
| efficiency | wall_clock=0.0037s，checker_runs=4，result_bytes≈31.9KB |

失败路径实测（全部退出码 0，verdict 照实写 FAIL/降级，不中断）：
- result.json 缺失 / 非 JSON：verify_check、schema_guard、gain_probe、explain_rollup、trend_anomaly_check 全部 exit 0；
- case.json 缺失：build_skeleton、trend_anomaly_check exit 0，trend_anomaly_check 将各组记 unavailable 并提示登记 material_gaps。

## 三、设计要点与硬约束对照

1. SKILL.md 148 行 ≤150；frontmatter 仅 name/description，YAML 合法。
2. 挂载 `/skills/weekly-skill`；输入 `/input/case.json`+task.md；产出 `/app/output/result.json`（含 case_id 与 output_contract 全字段，schema_guard 强校验）。
3. 所有失败路径 exit 0（语义值 verdict 返回在报告 JSON 内）——已逐脚本实测。
4. 不预置正式答案：examples 数据与引文全部虚构并标注"示意"。
5. 定位标志：每个脚本校验 `../SKILL.md` 同包存在（marker_hit），未命中打 WARN 不中断。
6. 多脚本禁写同一键：trend_anomaly_check / explain_summary / self_check·gates·unbacked_*·validator_verdict / gain_evidence·efficiency 各归唯一写者（SKILL.md 协议第 6 条 + README §3）。
7. 防 isalpha 汉字陷阱：全部词表匹配用子串 `in` 与正则 `\d`，未使用 `.isalpha()`；数字回证容差 max(0.5%×参照值, 0.5%×声称值)。
8. 口径事前声明：judge_rules（含 detection_thresholds / alignment_rule / pairing_rule / evidence_rule / executable_rule）declared_at 落 `/app/work/judge_rules.json` 台账，声明后禁改。

## 四、诚实边界（不夸大）

- 清洁输入上正常/退化两模式问题数均为 0，增益差主要体现在污染副本（8）与注入抓捕（9/9）；这是校验层对照，**不等于**平台基础 Agent 对照，白板对照由平台生成。
- 方向 flat 口径（|slope×span/mean|<0.05）与平台期容差法是声明口径，非变点检验；z 分数小样本偏保守。
- 对齐判定"机械一致性"只校验 supported 与负面/弃权条目不并存、unassessable 必登记，方向语义（如 H2 的"仅切换点升温"）仍依赖 Agent 判读，机检不做语义级对齐。
- 引文回证基于 case.json 序列化文本的逐字匹配；扫描件/外部位图来源登记 unavailable，不做 OCR 臆造。
- 增益探针的 enum 组恒开，不计入消融差（消融只关 alignment/pairing/evidence/recheck 四组）。
- 风险：真实平台案例的序列字段名若不在 VALUE_KEYS 常见键内，Step 3 会记 unavailable——脚本已打印提示键清单，Agent 需按提示人工映射后重跑。

## 五、自检结论

最小自检清单（README §0）六命令实测全过；校验器双跑 FAIL 差与污染反例注入均落地在 result.gain_evidence；无未修复 FAIL。剩余风险已在上节如实登记。
