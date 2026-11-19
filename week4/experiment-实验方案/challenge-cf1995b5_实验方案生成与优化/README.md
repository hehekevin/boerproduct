# exp-plan-design — 实验方案生成与优化 Skill（v1）

针对 Bohrium 产品赛第 4 周「实验方案生成与优化」赛道 (challenge-cf1995b5)
的参赛 Skill。锁定子场景：**研究目标 → 假设/变量表 → 对照与分组 → 功效依据 →
步骤参数 → 风险预案 → 分析对齐 → 候选方案机械比较**。

## 1. 用途与适用条件

给定研究目标、约束与科研材料（含组织方前瞻性资源/价格/预约合同），完成八件事：

1. **假设与变量表**：目标拆成可检验假设（hypothesis_id + testable）；独立/因/控制
   变量逐个给操作定义、测量方式、单位与量程——缺一被校验器判 FAIL。
2. **对照组设计**：空白/阳性/阴性/剂量梯度按需组合，每个对照写明**排除哪一类混杂**
   与设置依据；处理组+对照 ≥2 组并写明随机化方式。
3. **样本量/功效依据登记**：每组的 n 必须在 `power_basis.n_registry` 登记
   （检验方法/效应量/alpha/power/source），杜绝"拍脑袋的样本量"。
4. **步骤与参数**：每步绑定设备/试剂，参数逐个给 value+unit+range+basis
   （manual/pilot/literature/vendor），时长与预算使方案可排期可报价。
5. **风险与异常**：失败模式 + 判据 + 止损点 + 替代路径；安全/伦理/设备/专家确认项
   未确认的一律标 pending。
6. **分析计划-假设对齐**：每个假设被 ≥1 条 analysis_plan 引用，引用 id 必须存在，
   每个因变量有测量条目。
7. **候选方案机械比较**：≥2 个版本在事前声明的四因子 rubric 下由 score_plan 复算
   fused_score 并按确定性平局规则排序。
8. **证据链与自检**：数值参数逐字回证 claims；verify_check 五组机检 + schema_guard
   结构守卫 + gain_probe 消融对照全部退出码恒 0，判据只看报告 verdict。

**核心保证**：`verify_check.py` 独立机械复核变量表完备/对照设置/功效登记/分析对齐/
数字回证五组检查；`gain_probe.py` 用正常 vs 退化双跑实测机制增益并写入
`result.gain_evidence`。评分器不开附件即可通过 `self_check / gates /
unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 / 实验设计者 | 拿到研究目标要排期执行，需要变量-对照-参数-预算全套落盘 | 六类要素齐备、可被同行评审的方案 + 最优版本 |
| 研究助理 / 研究生 | 要向导师解释"为什么这样分组、n 为什么是 36" | 功效依据台账 + 对照排除混杂说明逐条可回溯 |
| 复核者 / 评审 | 检查方案是否覆盖假设变量对照参数风险，数字有没有出处 | 机械校验报告（self_check 三元组 + unbacked_numbers）|
| 教学 / 培训 | 演示"事前声明口径 + 机械复算 + 消融对照"的设计纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不做文献综述、不执行实验、不替代安全与伦理审批；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 上实测通过），只用标准库 |
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

# Step 1-4：Agent 填假设/变量表/对照/功效/步骤/风险/分析计划/claims（见 SKILL.md 八步流程）

# Step 5：候选方案机械比较（写 result.plan_ranking / fused_score / rank）
python3 /skills/weekly-skill/scripts/score_plan.py --result /app/output/result.json --k 1

# Step 6：增益对照 + 效率计数 + 污染反例（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 7：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

## 5. 输入与输出

- **输入**：`/input/case.json`（研究目标 + 约束 + 材料 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`research_question`、`rubric`、
    `hypotheses`、`variables`（三组）、`controls`、`groups`、`power_basis`、`protocol`、
    `measurements`、`analysis_plan`、`risks`、`confirmations`、`plan_versions`、
    `plan_ranking`、`completeness`、`steps`、`run_status`、`verdict`、`verdict_basis`、
    `gain_evidence`、`efficiency`
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`、`/app/work/schema_guard.json`、
  `/app/work/gain_evidence.json`、`/app/work/rubric.json`（口径台账）、
  `/app/work/skill_marker.json`（脚本标志）、`/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（材料批号与数据均为虚构）：1 条可检验假设 → 4 变量
（1 自变量 2 水平 / 1 因变量 / 2 控制变量）→ 4 组含空白+阴性对照 → 4 条功效登记 →
3 步骤全部参数带依据 → 2 条风险 → 分析计划对齐 H-01 → 3 个候选版本
（V1 fused=0.8 排第 1、V2 0.78、V3 0.72）。示意输出关键片段：

```json
{
  "case_id": "demo-expplan-001", "status": "answered",
  "result": {
    "variables": {"independent": [{"var_id": "IV-01", "unit": "μmol·m⁻²·s⁻¹", "level_count": 2}]},
    "controls": [{"control_id": "CTL-02", "type": "negative", "excludes_confound": "非光信号本底伸长"}],
    "power_basis": {"n_registry": [{"group_id": "G-01", "n": 36, "method": "effect_size=0.65, alpha=0.05, power=0.8"}]},
    "plan_ranking": {"ordered_ids": ["V1", "V2", "V3"], "k_value": 1},
    "verdict": "designed"
  }
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/score_plan.py --result examples/example-result.json --k 1 --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --marker /tmp/wk/skill_marker.json --rubric /tmp/wk/rubric.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --marker /tmp/wk/skill_marker.json --emit-into --inject-pollution
```

### 最小自检清单（本包全部实测通过，退出码均为 0）

| # | 自检项 | 实测结果 |
|---|--------|---------|
| 1 | build_skeleton 落骨架 + 标志文件 | exit 0，all_present=5/5 |
| 2 | verify_check 干净输入 | exit 0，verdict=PASS（28 检查项全 applied）|
| 3 | schema_guard 结构守卫 | exit 0，verdict=PASS |
| 4 | score_plan 排序 | exit 0，V1 0.8 > V2 0.78 > V3 0.72 |
| 5 | gain_probe 消融双跑 | exit 0，steps_count 30 vs 2（delta +28）|
| 6 | 污染反例副本 | exit 0，caught_by_normal_mode=true |
| 7 | SKILL.md 行数 | 150 行（≤150）|

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 数字全回证 | `unbacked_numbers` 为空数组 |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 六类要素齐 | hypotheses/variables/controls/groups/power_basis/protocol/risks/analysis_plan 全落键且 completeness 汇总与实际一致 |
| A6 | 对照可回溯 | 每个 control 写明 excludes_confound + basis；group_id 有效 |
| A7 | 功效有据 | 每个 groups[].n 在 n_registry 登记（n 一致、method+source 非空） |
| A8 | 分析对齐 | 每个 hypothesis_id 被 ≥1 条 analysis_plan 引用；因变量有测量条目 |
| A9 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A10 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（变量表 + 对照设置 + 功效依据 + 分析对齐 + 证据回证） | — |
| `degraded` | 枚举/结构/completeness 汇总/verdict 一致性 | **variables / controls / power / alignment / evidence 五组** |

实测对照（合成案例 + 注入 5 项污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 污染副本 problems | 11 | 2 | −9 |
| 变量表违规漏检 | 0 | 1 | +1 |
| 对照设置违规漏检 | 0 | 1 | +1 |
| 功效依据漏登记 | 0 | 4 | +4 |
| 分析对齐漏检 | 0 | 1 | +1 |
| 证据回证漏检 | 0 | 1 | +1 |
| steps_count（干净输入） | 30 | 2 | +28 |

注入的 5 项污染：清空 controls（无对照设计）、IV-01 清空 operational_definition、
清空 power_basis.n_registry、清空 analysis_plan、清空 claims。**同一校验器、同一污染
输入**：正常模式抓全（漏检 0，verdict=FAIL 11 处问题），退化模式 8 处客观违规漏掉
6 组中的 8 项、problems 从 11 掉到 2——这是机制增益最直接的证据。数字由探针独立
复算违规真值，与校验层分开实现；详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。
> 退化模式因常开检查（completeness 汇总/verdict 一致性）仍抓到 2 处，verdict 保持
> FAIL——漏检数是下界而非最坏情形，照实呈现。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 材料/设备/预算缺失 | material_gaps 登记 + confirmations pending，参数留 range 待定，不脑补 |
| 约束冲突（时间窗 vs 样本量） | uncertainties.conflicts 登记 + 声明取舍与代价 |
| 依赖不可用（试剂缺货/设备满） | risks 加 fallback；档期进 confirmations 待确认 |
| 无有效对照可行 | verdict=partially_designed + reason，绝不静默交无对照设计 |
| 大量同分 | 并列组记入 ties，按 tie_break 规则破平，不静默改分 |
| 算力/时间不足 | 保留已完成要素，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与 `problems`
列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：方案比较会不会换一批候选版本就不稳定？**
不会静默变。fused_score 是 rubric 事前权重的线性组合，平局按固定规则破（分数→
feasibility→version_id 字符串序），同输入重复运行顺序逐位一致；并列组全部在
`plan_ranking.ties` 可见。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。
SKILL.md 明确退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：功效分析的口径是谁定的？**
本技能在 power_basis.n_registry[].method 里逐条写明（检验方法/效应量/alpha/power），
source 注明来自预实验还是文献；预实验/文献未给定时按保守量级设定并写明，不冒充外部标准。

**Q：为什么每个变量必须有操作定义和单位？**
题面要求"变量的操作定义、测量方式、单位与取值范围"。缺操作定义的变量表会被
verify_check 判 FAIL——这正是防止"变量只有名字"退化的机械闸门。

**Q：confirmations 里 pending 是不是没做完？**
不是——它是题面要求的"标注需要专家确认的内容"。未确认的建议必须标 pending，
把人工注意力集中到真正需要确认的事项上，不把未经确认的建议写成可执行事实。

## 11. 适用范围与限制

- 仅处理输入范围内的方案生成与比较：不做文献综述、不执行实验、不替代安全与伦理审查。
- 功效口径按 n_registry 声明并逐条落盘，预实验/文献未给定时保守设定，不冒充外部标准。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘），`ablate` 参数可直接用作别处的"机制开关"对照实验 |
| `scripts/score_plan.py` 的确定性排序 | 权重事前声明 + 固定平局规则 + ties 登记，任何"稳定可解释排序"需求可直接照抄 |
| `power_basis.n_registry` 台账 | `{group_id, n, method, source}` 是通用的"数值依据登记"格式 |
| `controls` 检查 | `excludes_confound` 字段把"对照排除哪类混杂"变成可机检条目，任何实验设计场景可复用 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `skill_marker.json` 标志文件 | 脚本定位走标志文件校验，挂载路径变化时无需改代码 |
| `examples/` 合成案例 | 作为自测 fixture：复制一份删字段即得新的负例 |

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 八步流程 + schema + 校验说明，150 行） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/要素清单/rubric 模板/标志文件（退出码恒 0） | 是 |
| scripts/score_plan.py | 四因子机械打分 + 确定性排序 + 平局登记 | 是 |
| scripts/verify_check.py | 业务校验器（变量表/对照/功效/对齐/回证五组，--ablate 可关） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（虚构拟南芥光强实验） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节五条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/VAR_REQUIRED`
  与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
