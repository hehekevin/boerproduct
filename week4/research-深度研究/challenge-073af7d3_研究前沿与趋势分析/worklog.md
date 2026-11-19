# worklog — challenge-073af7d3「研究前沿与趋势分析」Skill 包制作记录

日期：2026-11-19（窗口截止 11-25 21:00）
作者：w8-res4
输出：`bohrium-week4-final/challenge-073af7d3/submission/`（SKILL.md + README.md + worklog.md + scripts/×5 + examples/×2）

## 一、做了什么
按题面四类可检查产物（时间趋势 / 主题演化 / 代表作 / 研究空白）设计 `trend-frontier-analyst`：
- **口径事前声明**：clustering_policy（关键词簇+归一化+匹配顺序）、trend_policy（观测窗口/增速公式/分级阈值）、extrapolation（外推边界）全部 declared_at=step1，同步 /app/work/trend_policy.json 台账。
- **趋势判定可复算**：trend_engine.py 机械落定 yearly_counts / growth_rate / stage；verify_check.py 独立复算逐项对照（growth 容差 1e-3），分级不一致直接 FAIL。
- **主题-证据绑定**：每主题 claims 回证，代表作 evidence_quote 逐字出现 + growth_rate 数字回证（空白归一化子串匹配），未回证数字入 unbacked_numbers 判 FAIL。
- **空白不冒充**：gaps.status=identified 须有 search_scope + 逐条带 quote 的 exclusion_evidence；否则必须标 not_verified + reason。
- **防汉字陷阱**：标题归一化用正则 `[^\w]+` 折叠（\w 含 CJK），全链无 isalpha。

## 二、文件清单（9 个，约 90KB，远低于 2MB/50 文件限制）
| 文件 | 说明 |
|---|---|
| SKILL.md | 145 行（≤150 达标），合法 YAML frontmatter（name/description） |
| scripts/build_skeleton.py | Step 0 骨架 + trend_policy 口径模板，三级容错 |
| scripts/trend_engine.py | 机械引擎：主题分配/年度计数/增速/分级/coverage/外推边界 |
| scripts/verify_check.py | 四组可消融校验（consistency/trend/evidence/registry）+ 闸门 |
| scripts/schema_guard.py | 结构守卫（契约字段 + items/topics/gaps/policy 子字段） |
| scripts/gain_probe.py | 消融双跑 + 污染反例注入（副本）+ 效率计数 |
| examples/example-case.json | 合成案例：19 条虚构文献、3 簇、2016-2026 |
| examples/example-result.json | 示意输出（标注非正式答案），全链路实测 PASS |

## 三、真实对照数字（全部来自实跑，未手填）
合成案例 19 条记录：T1 忆阻器件 6 篇 growth=-0.4 → **declining**；T2 脉冲神经网络 7 篇 growth=2.0 → **emerging**；T3 存内计算 5 篇 growth=-0.2 → **mature**；R19 无簇关键词 → unassigned + pending_review。coverage：total=19 judged=19 core=17 related=1 irrelevant=1 unassigned=1 topics_count=3 ratio=1.0。

| 实测项 | 结果 |
|---|---|
| build_skeleton（examples 输入） | exit 0；contract 字段 6 个；记录 19 条预填 |
| trend_engine | exit 0；3 topics 按上表机械落定 |
| verify_check（正常模式） | exit 0；**PASS，62 检查项全部 applied** |
| schema_guard | exit 0；PASS，结构完整 |
| gain_probe（消融双跑，同一输入） | exit 0；normal PASS / degraded PASS；steps_count **69 vs 7（delta 62）**；漏检全 0（干净输入无违规，符合预期） |
| gain_probe（污染反例，副本注入 5 项） | 正常模式 **FAIL 26 处**全抓到（caught_by_normal_mode=true）；退化模式 **PASS 0 处**（漏检下界，符合预期）；missed_detection_delta：trend_missed +1、evidence_missed +5、problems -26 |
| 失败路径（4 脚本 × 不存在文件） | exit 0 全部实测通过，FAIL 写报告不中断 |
| verify_check --ablate all | exit 0，PASS（0 组检查，仅基础枚举/结构仍开） |

## 四、硬约束自检（逐条）
1. SKILL.md 145 行 ≤150 ✓；frontmatter 仅 name/description，YAML 合法 ✓
2. 脚本 5 个 ≤8 ✓；文件 9 个 ≤50 ✓；总大小 <100KB <2MB ✓；零外部依赖（纯标准库）✓；命令一律 python3 ✓
3. 挂载路径 /skills/weekly-skill ✓；输入 /input/case.json + task.md ✓；产出 /app/output/result.json（含 case_id 与 output_contract 全字段，build_skeleton 自动补齐 contract 字段）✓
4. 所有失败路径 exit 0（4 个脚本实测）✓；verdict 照实写 JSON，语义值返回非退出码 ✓
5. 不预置正式答案：examples 标注「示意，非正式答案」，标题/摘要/年份/引用数均虚构 ✓
6. 定位标志：description 明确「Use when the task asks to analyze research frontiers and trends…」，触发词与题面对齐 ✓
7. 多脚本键归属分离（verify 只写 self_check/gates/unbacked_numbers/validator_verdict；gain 只写 gain_evidence/efficiency；engine 只写 topics/coverage/extrapolation）✓；无 isalpha ✓

## 五、诚实边界与剩余风险
- 增益对照是本校验层 normal vs degraded 两模式，不是平台基础 Agent 对照；platform 白板对照由平台生成。
- 关键词规则聚类的先验性：簇词表是本技能设定，术语漂移覆盖不足时按未归属处理（合成案例已演示该路径），真实案例若主题术语跨度大，可能出现较多 unassigned 待复核条目——这是登记而非失败，但会拉低一次通过率。
- growth_rate 是两端均值对比，不识别拐点年份；题面「区分离散波动与真实拐点」需要人工结合 yearly_counts 判断，本技能只提供可复算分布，未做变点检测。
- 污染反例的退化模式 PASS 0 处属预期（四组检查全关），证明增益来自机械校验层本身；但 26 处 FAIL 中多数来自清空 claims 的连锁效应，单项污染的检出贡献未逐一拆分。
- 效率计数 wall_clock 受机器负载影响，仅同次对照参考；model_requests 由 Agent 侧回填，脚本侧保持 null 不臆造。
- 正式案例的 records 键名/字段名未知，build_skeleton 已按 9 种常见键兜底 + WARN 提示人工核对，但极端命名仍需 Agent 手工预填。
