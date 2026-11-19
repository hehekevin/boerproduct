# worklog — multi-step-analysis-chain（agent-6aefb2fd，analysis 赛道）

日期：2026-11-19 ｜ 执行：w7-ana6 ｜ 状态：保底版 + 增益层完成，全链路实测通过

## 交付物
- `SKILL.md`（140 行，YAML frontmatter 合法）
- `scripts/` 5 个：build_skeleton / pipeline_run / verify_check / schema_guard / gain_probe
- `examples/` 2 个：example-case.json + example-result.json（合成示意，标注非正式答案）
- `README.md`（生态十项 + 最小自检清单）、本 worklog
- 包体：14 个文件 / 224KB（约束 ≤50 文件 / <2MB）；零外部依赖（AST 扫描确认仅标准库 + 包内互导）

## 真实对照数字（2026-11-19 本机实测，非估计）

### 全链路五脚本（examples 合成案例，退出码全部实测为 0）
| 脚本 | verdict | 关键读数 |
|------|---------|----------|
| build_skeleton | —（落盘） | marker_hit=True，contract 6 字段，1 表 12 行 |
| pipeline_run | PASS | acyclic=True；计划 5 步 / 留痕 5 条 / 完成 5 |
| gain_probe | 正常 PASS / 退化 PASS | 见下两节 |
| verify_check | PASS（0 problems） | 中间校验 total=10 passed=9 pass_rate=0.9 |
| schema_guard | PASS（0 problems） | 顶层 11 键 + contract 全字段；键归属一致 |

### 消融双跑（同一输入，正常 vs --ablate all）
- steps_count：normal=10 vs degraded=5，**delta=5**（关闭五组机械检查后执行计数减半，换来漏检面扩大）
- graph/trace/middle/evidence/fallback_missed：本干净样例上 normal=0、degraded=0，delta=0——干净输入上无违规可漏，属**真实无区分度**，不是缺失测量；区分度由污染副本双跑提供（见下）。
- manual_review_items / clarification_rounds：normal=0，degraded=0。

### 污染反例双跑（副本注入 5 项，原文件不动）
- 注入：S1 反向依赖 S5（成环）、删 S5 留痕、middle_checks 篡改 999/999、claims 编造引文+无回证数字 98.7/99.9、清空 fallbacks。
- **同一校验器双跑 FAIL 差：normal FAIL（14 problems） vs degraded PASS（0 problems）**，caught_by_normal_mode=true。
- 漏检差（degraded−normal）：graph=1、trace=1、middle=3、evidence=5、fallback=1——五组机制逐项有区分度。
- 抽样捕获：`[graph] 步骤图存在环（S1..S5）`、`[middle] total=999 与复算 8 不符`、`[evidence] c-01 引文无逐字回证`。

## 关键设计决策
1. 环检测双实现互核：verify_check 用 Kahn 拓扑，gain_probe 独立用 DFS 三色标记——口径一致时漏检数才可信。
2. 键归属矩阵机械检查（schema_guard）：dag/trace_audit→pipeline_run，middle_checks/self_check/gates/unbacked_*/validator_verdict→verify_check，gain_evidence/efficiency→gain_probe，杜绝多脚本写同一键互相覆盖。
3. step_id 校验用显式 ASCII 白名单（STEP_ID_RE），注释明确禁用 str.isalpha——该函数对汉字返回 True，「步骤一」会被误判为合法标识符。
4. 数字回证：claim 正文每个数字必须出现在引文或 source_id 步骤产物 JSON 中，否则 unbacked_numbers 判 FAIL——对应机检「结论-证据对齐」。
5. 所有失败路径 exit 0：参数解析失败/文件缺失/异常均打印并 return 0，语义照实写 verdict。

## 诚实边界
- 消融对照对象是本校验层正常 vs 退化两模式，**不是**平台基础 Agent vs 参赛 Agent 的白板对照；后者由平台生成。
- 干净输入上五类漏检指标 delta=0 是真实结果（无违规可漏）；增益的量化证据来自污染副本（14/0 FAIL 差）与 steps_count（10/5）。
- 退化模式仍保留枚举/contract 基础检查，漏检数是下界而非最坏情形。
- wall_clock_seconds 受机器负载影响，仅同次对照可参考；clarification_rounds 是按每轮 3 条折算的估计量。
- model_requests 保持 null（脚本无法采集），须由 Agent 按实际请求数回填，不臆造。
- 示例案例的统计为小样本示意（n=5/3/3），只演示链路不构成统计结论。

## 剩余风险
- verify_check 与台账（/app/work/analysis_plan.json）的一致性比对依赖 JSON 键序一致（norm 后字符串比对）；Agent 手改 plan 键序会触发 [plan] 不一致 FAIL——属保守失败，修复方式是重跑脚本回填而非手改。
- 污染注入依赖 result 结构可定位（plan.steps 首步、claims[0]）；极端退化骨架下注入项会减少，plan 里如实记录「无可注入位置」。
- 平台侧 /skills/weekly-skill 挂载路径与 /input、/app 目录假设已按 Runtime contract 写死，若平台路径变更需同步 SKILL.md 三处命令模板。
