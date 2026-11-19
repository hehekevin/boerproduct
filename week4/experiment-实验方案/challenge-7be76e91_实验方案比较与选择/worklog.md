# worklog — exp-plan-compare（challenge-7be76e91）

开发记录与真实对照数字。所有数字均来自 2026-11-19 本机实跑
（Windows 11 / Git Bash / Python 3.13.14，仅标准库），非手填。

## 1. 开发时间线

1. 读题面 `task.md`，锁定机检四点：权重事前声明、打分依据回证、总分复算一致、
   敏感性分析存在；外加"最终选择理由与放弃理由登记"。
2. 以第 4 期已交付包（challenge-cf1995b5，exp-plan-design）为骨架参考，把
   "方案生成"域改写为"方案比较与选择"域：五维权重（scientific_value /
   feasibility / cost / duration / risk_control）替换原四因子；plan_versions
   语义改为组织方预置候选方案的登记与打分；新增 comparability（统一口径）、
   sensitivity（机械敏感性）、final_choice（选择+放弃登记）三个业务块。
3. 5 个脚本全部重写/适配，键归属约定不变（多脚本禁写同一键）：
   - build_skeleton.py → 骨架 + rubric.json 模板 + skill_marker.json
   - score_plan.py → plan_ranking / sensitivity / fused_score / rank
   - verify_check.py → self_check / gates / unbacked_numbers / validator_verdict
   - schema_guard.py → 只读结构守卫，不改内容
   - gain_probe.py → gain_evidence / efficiency

## 2. 实测对照数字（合成案例 demo-plancompare-001）

### 2.1 排序复算（score_plan.py，与手算逐位一致）

| plan | scientific_value | feasibility | cost | duration | risk_control | fused_score | rank |
|------|-----|-----|-----|-----|-----|---------|------|
| P1 水热交联法 | 0.85 | 0.80 | 0.70 | 0.75 | 0.80 | **0.7950** | 1 |
| P3 机械球磨法 | 0.70 | 0.90 | 0.85 | 0.85 | 0.65 | 0.7775 | 2 |
| P2 溶胶-凝胶法 | 0.80 | 0.60 | 0.50 | 0.55 | 0.60 | 0.6400 | 3 |

权重：0.30 / 0.25 / 0.15 / 0.10 / 0.20（合计 1.0，declared_at=step1）。

### 2.2 敏感性分析（score_plan.py 机械扰动，40 变体）

- base_winner = P1；**overall_stable = false**（如实呈现，不粉饰）
- 翻转条件 5 条（winner 全部翻向 P3）：scientific_value−0.15、feasibility+0.20、
  cost+0.15、duration+0.20、risk_control−0.15
- 示例 choice_reasons 已按实测写明"若更看重成本与周期应改选 P3"
- verify_check 组 E 独立重算 40 变体逐一对照 → PASS

### 2.3 校验器与污染反例（gain_probe.py 同输入双跑 + 副本注入）

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入 problems | 0 | 0 | 0 |
| 干净输入 steps_count | 23 | 7 | +16 |
| 污染副本 problems | 18 | 1 | −17 |
| 污染副本 rubric_missed | 0 | 1 | +1 |
| 污染副本 evidence_missed | 0 | 2 | +2 |
| 污染副本 ranking/sensitivity/choice_missed | 0 | 0 | 0（见 §4 边界 3） |

注入 5 项污染：fused_score 篡改 +0.1234、清空 claims、risk_control 权重置 None、
清空 sensitivity、清空 rejected。caught_by_normal_mode = **true**。

### 2.4 自检清单（全部实测 exit 0）

| # | 命令 | 结果 |
|---|------|------|
| 1 | build_skeleton（example-case → .selftest/skel.json） | exit 0，all_present=5/5，契约字段 6 个 |
| 2 | verify_check（normal，--emit-into） | exit 0，PASS，16 检查项 |
| 3 | verify_check（--ablate all） | exit 0，PASS，0 检查项 |
| 4 | schema_guard | exit 0，PASS |
| 5 | score_plan（--k 1） | exit 0，排序/敏感性回写（见 §2.1/§2.2） |
| 6 | gain_probe（--emit-into --inject-pollution） | exit 0，caught=true |
| 7 | SKILL.md 行数 | 138 行（≤150），frontmatter 合法 |

## 3. 开发中发现并修复的问题

1. **ledger 台账 None 崩溃**：rubric.json 模板权重为 None 时，
   `abs(float(led_w.get(k, -1)) - weights[k])` 抛 TypeError → 改为仅在台账五键
   全为数值时才比对，模板态跳过比对（闸门仍记 enforced）。
2. **ablate=all 的关闭副作用**：comparability 组关闭后 cells_total=0，导致常开
   completeness 汇总比对误报 scored_cells/backed_cells 不符 → 改为该组关闭时
   两键不参与汇总比对（§2.4 第 3 行即修复后的实测）。
3. **ablate=choice 时变量未定义**：`chosen` 原在组 F 内定义，verdict 一致性段
   （常开）在组关闭时会 NameError → 提取到分析函数入口统一获取。
4. **weights 为 None 时 scored_pairs KeyError**：组 D/F 原用
   `scored_pairs(versions, weights or {})`，空 dict 触发 `weights[k]` KeyError →
   改为 weights 缺失时跳过该组（权重违规已由组 A 判 FAIL）。
5. **示例 choice_reasons 数字与实跑不符**：手估翻转条件为 3 条（cost+0.20 /
   duration+0.20 / scientific_value−0.20），实跑为 5 条且阈值不同 → 按实测更正。

## 4. 诚实边界

1. 增益对照是本校验层"正常 vs 退化"两模式对照，**不等于**平台"基础 Agent vs
   参赛 Skill"白板对照；平台对照由平台生成，本包不冒充。
2. 干净输入上六组违规本就为 0，missed 指标 delta=0 表示"该指标在本输入上无
   区分度"，不是"机制无用"；增益证据以污染副本对照（18 vs 1）为准。
3. 污染副本上 ranking/sensitivity/choice 三组 missed=0：总分篡改/敏感性清空/
   放弃理由清空在**正常模式全部被抓**（计入 problems 18 处），退化模式下这三项
   由常开 completeness 汇总比对部分兜住（剩余 1 处），故 missed 差值未显现在
   这三组——真实漏检情况以 problem_sample 明细为准，未做修饰。
4. 追问轮次（clarification_rounds）按每轮 3 条折算的估计量，非实测交互次数。
5. 敏感性扰动网格（±0.05/0.10/0.15/0.20，其余维度按比例归一）是约定口径，不是
   对评审方权重的猜测；flip_conditions 只覆盖网格内可检出的翻转。
6. 文献载量等数值在合成案例中标注为虚构；真实案例上此类数值必须逐条回证
   claims（quote 引原文），无法回证的进 unbacked_numbers 判 FAIL。
7. 模型请求数（efficiency.model_requests）不可由脚本采集，保持 null，由 Agent
   侧按实际请求次数回填，不臆造。

## 5. 交付清单

- SKILL.md（138 行，frontmatter 合法）
- scripts/：build_skeleton.py / score_plan.py / verify_check.py / schema_guard.py / gain_probe.py（5 个，≤8 上限内）
- examples/：example-case.json / example-result.json（合成，标注示意）
- README.md（生态说明 + 实测自检清单）/ worklog.md（本文件）
- 文件数 9 个、总大小 <100 KB（≤50 文件 / ≤2MB 上限内）；零外部依赖；命令一律 python3
