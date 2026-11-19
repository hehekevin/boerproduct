# worklog — sysrev-review-synthesis（challenge-51977f9b）

作者：w8-res2 ｜ 日期：2026-11-19 ｜ 环境：Windows 11 / Git Bash / Python 3.13.14

## 1. 设计决策

题面要求 PRISMA 式全流程（协议注册→检索→筛选→质量评价→数据提取→综合），
机检点为**漏斗计数闭合、协议事前声明、提取项回证、结论强度分级一致**。第 4 期
既有参考包（challenge-5b90f5e9）覆盖了检索+筛选段，本包在其骨架上补齐下游三段，
并把四个机检点全部做成机械可校验：

| 机检点 | 实现机制 | 归属脚本 |
|--------|---------|---------|
| 漏斗计数闭合 | 五级计数复算 + excluded_by_reason 合计 + closure 判据 | flow_audit.py（沿用参考包，实测直接可用） |
| 协议事前声明 | review_registration + protocol_ledger 台账 + 版本漂移核对 | build_skeleton.py 落模板 + verify_check.py 核对 |
| 提取项回证 | 结构化三块（design/sample/effect）逐块 quote 归一化子串命中语料或 claims | extraction_guard.py（新增） |
| 强度分级一致 | 声明 strength == 按 supporting 数×质量×冲突数规则推导 | synthesis_check.py（新增）+ strength_rules.json |

质量评价一致性（quality 组）作为第 5 组消融开关一并纳入，防止"质量较高"式
一句话评价。理由码字典、去重、漏斗脚本直接复用参考包（同为 PRISMA 域，零改动
或极小改动），节省的预算投给三个新审计器。

## 2. 开发过程（真实时序）

1. 复制参考包 6 脚本 → 语合法检 → 保留 dedupe/flow_audit 原样，重写
   build_skeleton（+review_registration/quality_appraisal/extraction/synthesis
   四组骨架键 + protocol_ledger 模板）。
2. 新增 quality_audit.py / extraction_guard.py / synthesis_check.py 三个纯函数
   审计器（analyze_* 供 verify_check 复用，CLI 只读审计）。
3. verify_check.py 改造：四组 → 六组消融开关（protocol/screening/funnel/
   extraction/quality/synthesis），import 三个审计器，gate 更名 protocol_ledger。
4. gain_probe.py 改造：客观真值扩展到七类（+extraction/quality/synthesis，独立
   实现）；污染注入从 6 项扩到 14 项（+提取无据/强度篡改/等级篡改/清协议声明/
   清空白登记）；指标与 delta_keys 同步扩。
5. 合成示例 9 条虚构题录（他汀×认知域）：5 纳入/2 排除/1 重复合并/1 待复核，
   质量等级与提取 quote 均按"能被机械推导/命中"反推设计。

## 3. 实测对照数字（全部来自实跑，非手填）

**干净示例输入**（examples/，verify_check 81 条检查项）：

- normal：verdict=PASS；degraded（--ablate all）：verdict=PASS；七类漏检均 0。
- steps_count：normal 87 vs degraded 9，delta=+81。
- 两遍 analyze 耗时 0.0016s / 0.0007s（同机同输入）。

**污染副本**（14 项注入：included 清 criteria_ref+quote、excluded 清 reason、
funnel.included 篡改 +1、R09 清 pending_reason、清 pending_review、清 claims、
R01 提取块清 evidence、R03 overall_grade high→low、S-01 strength strong→weak、
清 gaps/gaps_note、清 registered_at、清 criteria.version 等）：

| 指标 | normal | degraded |
|------|--------|----------|
| verdict | FAIL（20 处问题） | PASS（0 处问题） |
| criteria 漏检 | 0 | 3 |
| funnel 漏检 | 0 | 2 |
| evidence 漏检 | 0 | 7 |
| pending 漏检 | 0 | 1 |
| extraction 漏检 | 0 | 3 |
| quality 漏检 | 0 | 1 |
| synthesis 漏检 | 0 | 1 |

正常模式 14 项污染全部捕获（七类漏检全 0）；退化模式 18 处客观违规全部漏掉且
verdict 从 FAIL 翻成 PASS。部分消融 `--ablate funnel,extraction,synthesis` 实测
47/81 检查项执行、机制独立生效。

修复记录：R09 pending 条目需 judged=true + rationale（与参考包口径一致）；
synthesis 的 gaps/bias/conflict_matrix 检查最初缺 self_check 三元组，导致增益
计数漏 1，补三元组并把 count_caught 前缀扩为 `synthesis.` 后对齐；污染注入补
第 14 项（质量等级篡改）使七组机制全部有对照差。

## 4. 诚实边界

- 增益对照是本校验层 normal vs degraded 两模式，**不等于**平台"基础 Agent vs
  参赛 Skill"白板对照；平台对照由平台生成。
- 退化模式仅关闭分组检查，枚举/coverage 等基础检查仍开，退化侧漏检数是下界。
- 违规真值由 gain_probe 独立复算，但与校验器共享"归一化子串回证"口径；若真实
  案例的来源文本分块方式不同（如 quote 跨字段拼接），extraction 回证可能误报——
  届时按 problems 逐条修复，不得关闭回证检查。
- 示例 claims/evidence 均为合成数据；正式结论只能来自平台案例实际运行。
- quality_missed 在未注入质量污染的历史版本曾恒为 0，当前版本已注入第 14 项
  污染覆盖该机制；若未来扩展污染集，需保持七类机制均有对照差。
- wall_clock 为本机耗时，仅同次对照参考；模型请求数不可由脚本采集，保持 null
  由 Agent 侧回填。

## 5. 遗留风险

- 真实案例 output_contract 字段名排布未知，build_skeleton 已做多键兼容
  （fields/required_fields/result.json/result/裸键），但极端排布可能需手工兜底。
- 案例若提供 PDF 全文而非题录摘要，extraction_guard 语料回证依赖 case.json 文本
  字段；PDF 场景需 Agent 先落文本再判定（SKILL.md 已注明"以实际文件为准"）。
- 协议台账漂移核对依赖 --ledger 路径正确挂载（默认 /app/work/protocol_ledger.json）。
