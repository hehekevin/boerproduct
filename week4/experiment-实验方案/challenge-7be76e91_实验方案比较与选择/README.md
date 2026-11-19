# exp-plan-compare — 实验方案比较与选择 Skill（v1）

针对 Bohrium 第 4 期「实验方案比较与选择」赛道 (challenge-7be76e91) 的参赛 Skill。
锁定子场景：**候选方案统一口径登记 → 五维权重事前声明 → 逐维度打分与依据回证 →
加权总分机械复算 → 权重敏感性分析 → 最终选择与放弃理由登记**。

## 1. 用途与适用条件

给定研究目标、约束与组织方预置的候选方案（含前瞻性价格/排期/预约合同），完成六件事：

1. **口径事前声明**：五维权重（scientific_value / feasibility / cost / duration /
   risk_control，合计=1.0）+ tie_break + normalization 在**任何排序之前**声明并落
   `/app/work/rubric.json` 台账，声明后禁止调整——杜绝"先看结果再定权重"。
2. **统一比较矩阵**：所有候选方案用同一字段结构逐维度填格
   （score + basis + evidence_ref），缺一格即被校验器判 FAIL——杜绝"三方案三套结构"。
3. **依据回证**：每个打分格的 evidence_ref 必须指向 claims 中带非空 quote 的条目；
   选中方案 protocol 数值参数逐字回证（空白归一化子串匹配）。
4. **机械复算排序**：fused_score = Σ w_i × score_i（保留 4 位小数）由 score_plan.py
   复算回写，平局按固定规则破（分数 → risk_control → plan_id）并记入 ties。
5. **敏感性分析**：40 个权重扰动变体（每维 ±0.05/0.10/0.15/0.20，其余维度按比例
   归一）逐个复算 winner，落盘 flip_conditions（winner 翻转的最小扰动）与
   overall_stable；易翻转时必须在选择理由中写明翻转条件。
6. **可辩护选择**：chosen_id 必须等于机械排序第 1 名；每个落选方案登记非空
   rejection_reason + tradeoff；安全/设备/专家确认项未确认一律 pending。

**核心保证**：`verify_check.py` 独立机械复核权重声明/口径统一/依据回证/总分复算/
敏感性可复算/选择登记六组检查；`gain_probe.py` 用正常 vs 退化双跑实测机制增益并
写入 `result.gain_evidence`。评分器不开附件即可通过 `self_check / gates /
unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 / 课题组长 | 三五条可行路线要定一条，还要向评委/导师解释为什么 | 统一口径比较矩阵 + 敏感性说明 + 可辩护选择登记 |
| 研究助理 / 研究生 | 排期与预算有限，需要"本实验室现在可做"而非"理论上可行" | 设备档期/成本口径逐条回证的打分台账 |
| 复核者 / 评审 | 检查比较是否公平、分数有没有出处、选择是否站得住 | 机械校验报告（self_check 三元组 + unbacked_numbers）|
| 教学 / 培训 | 演示"事前声明口径 + 机械复算 + 消融对照"的设计纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不做路线原始设计创新、不执行实验、不替代安全与伦理审批；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13.14 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 100 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。脚本定位走标志文件：Step 0 会在
`/app/work/skill_marker.json` 落盘脚本存在性校验结果，后续校验器据此命中。

```bash
# Step 0：自动落骨架 + 要素清单 + rubric 模板 + 脚本标志文件（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-3：Agent 声明口径/逐维打分回证/落选中方案执行要素（见 SKILL.md 七步流程）

# Step 4：机械排序 + 40 变体敏感性分析（写 plan_ranking / sensitivity / fused_score / rank）
python3 /skills/weekly-skill/scripts/score_plan.py --result /app/output/result.json --k 1

# Step 5：增益对照 + 效率计数 + 污染反例（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 6：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

## 5. 输入与输出

- **输入**：`/input/case.json`（研究目标 + 约束 + 候选方案 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`research_question`、`rubric`、
    `comparability`、`plan_versions`、`plan_ranking`、`sensitivity`、`final_choice`、
    `hypotheses`、`variables`（三组）、`controls`、`groups`、`power_basis`、`protocol`、
    `measurements`、`analysis_plan`、`risks`、`confirmations`、`completeness`、
    `steps`、`run_status`、`verdict`、`verdict_basis`、`gain_evidence`、`efficiency`
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`、`/app/work/schema_guard.json`、
  `/app/work/gain_evidence.json`、`/app/work/rubric.json`（口径台账）、
  `/app/work/skill_marker.json`（脚本标志）、`/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（材料价格与数据均为虚构）：3 个候选方案（水热交联 /
溶胶-凝胶 / 机械球磨）× 5 维统一打分 → 15 格全部 basis+evidence_ref 回证 19 条
claims → fused_score 机械复算 P1=0.795 > P3=0.7775 > P2=0.64 → 40 变体敏感性
（5 个翻转方向，P1 在基线权重下稳健）→ 选择 P1、P2/P3 弃选理由登记。示意输出关键片段：

```json
{
  "case_id": "demo-plancompare-001", "status": "answered",
  "result": {
    "plan_ranking": {"ordered_ids": ["P1", "P3", "P2"], "k_value": 1},
    "sensitivity": {"base_winner": "P1", "overall_stable": false,
                    "flip_conditions": [{"dim": "cost", "direction": "+", "min_flip_delta": 0.15, "winner_after": "P3"}]},
    "final_choice": {"chosen_id": "P1", "rejected": [{"plan_id": "P3", "rejection_reason": "载量上限 0.25 mmol/g 低于达标线 0.40"}]},
    "verdict": "selected"
  },
  "validator_verdict": "PASS"
}
```

### 最小自检清单（本包全部实测通过，退出码均为 0，2026-11-19 实测）

| # | 自检项 | 实测结果 |
|---|--------|---------|
| 1 | build_skeleton 落骨架 + 标志文件 | exit 0，all_present=5/5，契约字段 6 个 |
| 2 | verify_check 干净输入 | exit 0，verdict=PASS（16 检查项） |
| 3 | verify_check --ablate all | exit 0，verdict=PASS（0 检查项，无关闭副作用） |
| 4 | schema_guard 结构守卫 | exit 0，verdict=PASS |
| 5 | score_plan 排序复算 | exit 0，P1 0.795 > P3 0.7775 > P2 0.64（与手算逐位一致） |
| 6 | score_plan 敏感性 | exit 0，40 变体 / 5 条翻转条件 / overall_stable=false |
| 7 | gain_probe 消融双跑 | exit 0，steps_count 23 vs 7（delta +16） |
| 8 | 污染反例副本 | exit 0，caught_by_normal_mode=true（正常 18 处 vs 退化 1 处） |
| 9 | SKILL.md 行数 | 138 行（≤150），frontmatter 合法 |

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） |
| A2 | 权重事前声明 | `verify_check` 组 A：五维权重合法合计=1.0、declared_at 非空、与台账一致 |
| A3 | 口径统一 | `verify_check` 组 B：五维 definition 齐备，方案×维度 15 格全部 score+basis+evidence_ref |
| A4 | 依据回证 | `verify_check` 组 C：evidence_ref 全部指向带 quote 的 claim，`unbacked_numbers` 为空 |
| A5 | 总分复算一致 | `verify_check` 组 D：fused_score 与 ordered_ids 机械复算逐位一致 |
| A6 | 敏感性存在且可复算 | `verify_check` 组 E：variants 逐变体 winner 与独立复算一致 |
| A7 | 选择可辩护 | `verify_check` 组 F：chosen_id=第 1 名、全部落选方案有放弃理由 |
| A8 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A9 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |
| A10 | 闸门诚实 | `gates[]` 五项 state ∈ 四态枚举；非 enforced 必有 note |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部六组（rubric + comparability + evidence + ranking + sensitivity + choice） | — |
| `degraded` | 枚举/结构/completeness 汇总/verdict 一致性 | **上述六组** |

实测对照（合成案例 + 注入 5 项污染的副本，2026-11-19 实跑，Python 3.13.14）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入 problems | 0 | 0 | 0（干净输入本无违规，见边界说明） |
| steps_count（干净输入） | 23 | 7 | +16 |
| 污染副本 problems | 18 | 1 | −17 |
| 污染副本 rubric_missed | 0 | 1 | +1 |
| 污染副本 evidence_missed | 0 | 2 | +2 |

注入的 5 项污染：fused_score 篡改 +0.1234（总分与复算不一致）、清空 claims（打分
依据回证全部断裂）、rubric.weights.risk_control 置 None（权重声明破坏）、清空
sensitivity（敏感性缺失）、清空 rejected（放弃理由缺失）。**同一校验器、同一污染
输入**：正常模式抓到 18 处问题（verdict=FAIL），退化模式只余 1 处（常开
completeness 汇总检查抓到）——权重声明、依据回证、敏感性、放弃理由四类机检在
退化模式下完全失明，这是机制增益最直接的证据。数字由探针独立复算违规真值，
与校验层分开实现；详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。
> 干净输入上六组违规本就为 0，故 missed 指标 delta=0 表示"该指标在本输入上无
> 区分度"而非"机制无用"——增益证据以污染副本对照为准，照实呈现。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 候选方案/价格/排期缺失 | material_gaps 登记 + confirmations pending，打分格子留待定，不脑补 |
| 约束冲突（预算 vs 载量目标） | uncertainties.conflicts 登记 + 声明取舍与被舍弃方案的代价 |
| 全部候选不可行 | verdict=partially_selected/not_selected，逐方案登记不可行判据，绝不硬选 |
| 大量同分 | 并列组记入 ties，按 tie_break 规则破平，不静默改分 |
| 敏感性显示易翻转 | flip_conditions 落盘 + choice_reasons 写明翻转条件，不静默只报 winner |
| 算力/时间不足 | 保留已完成要素，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与 `problems`
列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：权重是谁定的？会不会先看方案再凑权重？**
权重由 Agent 在 Step 1（任何排序之前）声明并同步落 `/app/work/rubric.json` 台账；
verify_check 组 A 会逐项对照 result.rubric 与台账，声明后调整会被判 FAIL。declared_at
记录声明时点，评分器可直接核对。

**Q：换一批候选方案排序还稳定吗？**
fused_score 是 rubric 事前权重的线性组合，平局按固定规则破（分数 → risk_control →
plan_id 字符串序），同输入重复运行顺序逐位一致；并列组全部在 `plan_ranking.ties` 可见。

**Q：敏感性分析是手写的吗？**
不是。score_plan.py 对五维权重做 ±0.05/0.10/0.15/0.20 的机械扰动（其余维度按比例
归一，共 40 变体），逐变体复算 winner；verify_check 组 E 独立重算全部变体逐一对照，
任何一处 winner 不符即 FAIL。overall_stable=false 是正常输出，不是错误——它强制
Agent 在选择理由里写清"权重怎么变会改选谁"。

**Q：打分依据回证是怎么检查的？**
每个打分格的 evidence_ref 必须是 claims 里真实存在的 claim_id，且该 claim 带非空
quote（引用案例材料/设备手册/文献/预实验原文）；选中方案 protocol 的数值参数还须
逐字出现在 claim 文本/引文中（空白归一化后子串匹配），否则进 unbacked_numbers 判 FAIL。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。
SKILL.md 明确退化模式结果仅用于增益对照，不得当作交付自检结论。

## 11. 适用范围与限制

- 仅处理输入范围内的方案比较与选择：不做路线原始设计创新、不执行实验、不替代安全与伦理审查。
- 维度打分依赖 comparability 声明的归一口径；组织方未给价格/排期时按 material_gaps 登记，不冒充报价。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/score_plan.py` 的 `compute_sensitivity()` | 权重扰动网格 + flip_conditions 是通用的"结论稳健性"量化器，任何加权决策场景可直接导入复算 |
| `scripts/score_plan.py` 的确定性排序 | 权重事前声明 + 固定平局规则 + ties 登记，任何"稳定可解释排序"需求可直接照抄 |
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘），`ablate` 参数可直接用作别处的"机制开关"对照实验 |
| `factors_detail` 打分格 | `{score, basis, evidence_ref}` 是通用的"逐项判断挂证据"格式 |
| `final_choice.rejected` 台账 | `{plan_id, rejection_reason, tradeoff}` 把"弃选理由"变成可机检条目 |
| 闸门五态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `skill_marker.json` 标志文件 | 脚本定位走标志文件校验，挂载路径变化时无需改代码 |
| `examples/` 合成案例 | 作为自测 fixture：复制一份删字段即得新的负例 |

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明，138 行） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/要素清单/rubric 模板/标志文件（退出码恒 0） | 是 |
| scripts/score_plan.py | 五维机械打分 + 确定性排序 + 平局登记 + 40 变体敏感性 | 是（含 `compute_sensitivity()` API） |
| scripts/verify_check.py | 业务校验器（权重/口径/回证/复算/敏感性/选择六组，--ablate 可关） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（虚构酶固定化载体选型） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节五条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED` 与 SKILL.md 的 schema 段。
- 改动五维权重键名时同步 `score_plan.py` 的 `WEIGHT_KEYS`、`schema_guard.py`、
  `verify_check.py`（二者从 score_plan 导入）与 SKILL.md。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
