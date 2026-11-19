# repro-verify — 论文复现与方法验证 Skill（v5）

针对 Bohrium 产品赛第 3 周「文献阅读」赛道「论文复现与方法验证」(challenge-da62e8d4)
的参赛 Skill。锁定子场景：**参数/代码/指标验算与差异归因**。

## 1. 用途与适用条件

给定论文材料与包内候选数值方法（代码/脚本），完成六件事：

1. **参数复原**：每个关键参数标注 `paper_explicit` / `code_inferred` / `self_set`
   三类来源与出处；正文/附录/代码冲突时登记双方取值，论文明确值优先。
2. **事前容差声明**：每个指标先写定容差（metric / tolerance / basis / declared_at），
   验算前完成，事后禁止调整——这是"对得上"的前置条件，不是事后凑数。
3. **实际运行**：逐个候选方法用复原参数实际执行，`ran` + `run_log`，或
   `ran=false` + `failure_stage`（parse|import|run|output）+ `failure_reason`，
   不跳过、不伪造成功。
4. **指标对照**：`paper_value` 逐字摘自论文（附位置），`computed_value` 来自实际输出，
   `within_tolerance` 由校验器按事前容差**机械复算**，不得手填。
5. **差异归因**：超容差项逐条归因到 environment / data / implementation /
   paper_underspecification，evidence 指到具体位置。
6. **结论分级**：reproduced / partially_reproduced / not_reproduced / cannot_verify
   四级，附 `verdict_basis`；另出 `run_status`（success/partial/unable_to_determine/refused）。

**核心保证**：每个可复算数字（参数值、paper_value、computed_value、归因 delta）在
`claims[]` 有对应证据链（论文逐字摘录 + 本方计算值 + 差异说明），且数字逐字回证
（论文侧数字出现在 claim quote、本方计算值出现在 claim text，空白归一化后子串
匹配，未回证数字列入 `unbacked_numbers` 并判 FAIL）；verify_check 把每条检查的
三元组 `{item, template_value, applied, match}`、闸门状态（enforced /
skipped_not_provided / not_found / unreadable，未 enforced 时注明「下游不得宣称
已核对」）与 unbacked 清单回写进 result.json（键 `self_check` / `gates` /
`unbacked_numbers` / `validator_verdict`），评分器不开附件即可核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 论文复现者（科研/算法工程师） | 拿到论文正文 + 作者代码仓，要把论文表格数字跑出来对账 | 参数表（带来源分类）、事前容差、指标对照表、差异归因清单、可复算结论 |
| 审稿人 / 复现性评审 | 判断"论文结果对不上"是环境、数据、实现还是论文描述不足 | 四级结论 + 逐条归因（evidence 指到具体位置）+ 缺口登记 |
| 数值方法维护者 | 自己的实现与论文指标有偏差，要定位差在哪 | metric_checks 中 paper/computed 双列 + 归因 follow_up 建议 |
| 教学 / 培训 | 演示"事前声明容差 + 机械复算"的复现纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不拉外部仓库、不申请外部数据、不装 pip 依赖；不能替代原作者全量复现
（合成试验 ≠ 原作者复现，结论只针对包内候选方法与论文声明的一致性）。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 与 3.12 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 200 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 材料清单 + 容差模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 5：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json

# Step 6：增益对照 + 效率计数（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```

## 5. 输入与输出

- **输入**：`/input/case.json`（论文材料 + 候选方法清单 + output_contract）、
  包内方法文件、`task.md`。**以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`parameters`、`candidates`、
    `metric_checks`、`attributions`、`steps`、`declared_tolerances`、
    `recomputability`、`run_status`、`verdict`、`verdict_basis`、
    `gain_evidence`、`efficiency`
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`（校验报告）、
  `/app/work/schema_guard.json`（结构报告）、`/app/work/gain_evidence.json`
  （增益对照证据）、`/app/work/declared_tolerances.json`（容差声明台账）、
  `/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例：论文声明 RMSE=0.031，两候选方法分别复算得 0.0312（容差内）
与 0.0497（超容差，归因到实现差异）。示意输出关键片段：

```json
{
  "case_id": "demo-repro-001", "status": "answered",
  "result": {
    "parameters": [{"parameter": "拟合阶数", "value": 2, "source_class": "paper_explicit",
                     "source_location": "§2", "recomputable": true}],
    "candidates": [{"candidate_id": "candidate-A", "ran": true, "run_log": "RMSE=0.0312"}],
    "metric_checks": [{"metric": "RMSE", "candidate_id": "candidate-A",
                        "paper_value": 0.031, "computed_value": 0.0312,
                        "tolerance": "±10%", "within_tolerance": true}],
    "attributions": [{"metric": "RMSE(candidate-B)", "delta": 0.0187,
                       "attribution": "implementation",
                       "evidence": "method_b.py 使用一阶多项式，与论文 §2 声明的阶数不一致"}],
    "declared_tolerances": [{"metric": "RMSE", "tolerance": "±10%",
                              "basis": "论文未给容差，按指标量级保守声明", "declared_at": "step1"}],
    "verdict": "partially_reproduced"
  },
  "claims": [{"claim_id": "k-01", "kind": "inferred", "location": "metric_checks[0]",
               "evidence": [{"paragraph_id": "§2", "quote": "RMSE 0.031"}]}]
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题 12 个业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 数字全回证 | `unbacked_numbers` 为空数组 |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 候选全覆盖 | 每个候选都有 ran=true+run_log 或 ran=false+failure_stage+failure_reason |
| A6 | 容差事前 | `declared_tolerances` 非空，每条有 basis；与 `metric_checks[].tolerance` 一致 |
| A7 | 步骤可重跑 | `steps[]` 非空，至少一条含可执行 `command` |
| A8 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 + 失效条件 |
| A9 | 效率可复算 | `efficiency` 含自动采集计数与 `reproduce` 命令；`model_requests` 缺失时为 null |
| A10 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（含逐字回证 + 容差复算） | — |
| `degraded` | 枚举/结构/失败阶段/归因/claims 覆盖 | **逐字回证**（value_backed / numbers_backed / delta_backed）+ **容差复算**（tolerance_recompute） |

逐项对照五项指标（全部实测，不臆造）：
`recomputable_ratio`（可复算数值占比）、`tolerance_missed`（容差违规漏检数）、
`manual_review_items`（需人工核对条目数）、`steps_count`（步骤数）、
`clarification_rounds`（追问轮次，公式 `ceil(manual_review_items/3)` 随记录落盘）。

每项指标都写明**机制 → 指标映射**（`mechanism_to_metric_map`）、**边界**
（`boundaries`）与**失效条件**（`failure_conditions`）。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 仓库/原始数据不可访问 | material_gaps 登记，对应项 recomputable=false 写明缺什么，verdict=cannot_verify |
| 依赖冲突/缺失 | failure_stage=import，failure_reason + stderr 摘要入 run_log，尝试 stdlib 替代 |
| 算力/时间不足 | 保留已跑部分，status=partial，changelog 注明截断位置 |
| 评价脚本缺失 | 自行实现等价计算，口径差异登记 uncertainties.unreported |
| 结果对不上 | 逐条写归因（evidence 指到具体位置），不掩盖、不调容差 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| 运行中断 | 仍写 result.json（status=partial），注明中断点与已完成部分 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与
`problems` 列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器
自身故障打断。SKILL.md 协议第 7 条明确"自检只判 verdict"。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**（normal=0 漏检 → degraded 检出更少），
它的作用是量化"关闭这些机制会漏掉多少"，作为增益证据。SKILL.md 明确：
退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：`gain_evidence` 里的数字是真实的吗？**
是。两遍都由 `verify_check.analyze()` 在同一份输入上实跑产出；
`tolerance_missed` 的真值由探针独立复算 |paper−computed| 与容差比较得出，
与校验层分开算。污染反例只在副本上注入，原 result.json 不被改动。

**Q：为什么 `steps_count` 正常模式反而更大？**
正常模式执行更多检查项，所以步骤数更高——这正是"步骤少不等于质量高"的证据，
`mechanism_to_metric_map` 里对该指标标了 `higher_is_better: null`。

**Q：能不能只跑部分候选方法省时间？**
不能。协议第 3 条"广度优先"要求覆盖全部候选与全部关键指标；跳过候选会被
`verify_check` 记为 FAIL（未运行候选却有 computed_value）。

**Q：`recomputable:false` 是不是偷懒？**
不是——它表示"材料不足以复算"，必须同时写 `missing_for_recompute`（缺什么），
这正是题面"缺失项显式登记而不是默默跳过"的要求。

**Q：容差可以事后调吗？**
不可以。`declared_tolerances` 必须在验算前写定；`verify_check` 会核对
`metric_checks[].tolerance` 与声明是否一致，不一致即 FAIL。

## 11. 适用范围与限制

- 仅验算包内候选方法：不拉外部仓库、不申请外部数据、不装 pip 依赖（stdlib-only）。
- 合成试验 ≠ 原作者复现：结论仅针对候选方法与论文声明的一致性，不冒充全量复现。
- 容差未在论文给出时按指标量级保守声明（declared_tolerances 注明"本技能声明"）。
- 论文口径缺失时如实登记 uncertainties，不自创口径冒充论文口径。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数；
  原始计数 `manual_review_items` 一并落盘，可换批量重算。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，
  缺失保持 null，不得臆造。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘、不读环境），可直接 `import` 到别的校验器里；`ablate` 参数可复用为别处的"机制开关"对照实验 |
| `scripts/gain_probe.py` 的双模式对照 | 换掉 `analyze` 即可测任何校验器的机制增益；指标公式全部写在 `mechanism_to_metric_map` 里，可照抄改造 |
| `declared_tolerances` 台账格式 | `{metric, tolerance, basis, declared_at}` 是通用的"事前声明"台账，数值型评测类 Skill 都能用 |
| `steps[]` 复现步骤格式 | `{step, action, command, output_ref, status}` 适合任何"他人可重跑"型交付 |
| `run_status` 四态 | success/partial/unable_to_determine/refused + reason + manual_takeover，通用且诚实 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` 可直接抄到别的 Skill |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改数字即得新的负例 |

**建议的复用顺序**：先抄 `verify_check.py` 的 `analyze()` 骨架（拿到三元组 + 闸门 + 回证），
再抄 `gain_probe.py` 的双模式对照（拿到可验证的增益证据），最后按自己的业务 schema
改 `RESULT_REQUIRED` 列表。

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 六步流程 + schema + 校验说明 + 速查表） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 自动落骨架/材料清单/容差模板（三级容错，退出码恒 0） | 是 |
| scripts/verify_check.py | 业务逻辑校验器（容差复算/claims 覆盖/recomputable/回证/闸门/三元组） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例自测 | 是（含指标公式） |
| examples/example-case.json | 合成输入示例 | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明（用途/依赖/安装/输入输出/验收/FAQ/限制/异常/复用/维护） | — |
| worklog.md | 开发记录、五维差距清单与双测证据 | — |

## 14. 版本与维护

版本 **v5**（2026-11-17）。依赖：Python 3.8+ 标准库，无第三方依赖。

| 版本 | 增量 |
|------|------|
| v5 | ① 题面对齐：result 新增 `steps` / `declared_tolerances` / `recomputability` / `run_status` 四组字段（对应题面输出要求表的"复现步骤 / 数值容差 / 可复算性 / 运行状态"）；② 全部校验脚本**失败路径退出码恒 0**，verdict 照实记录在报告与 `validator_verdict`，禁止中断交付；③ 新增 `gain_probe.py`：正常 vs 退化双模式实跑，把真实数字写入 `result.gain_evidence`（五项指标 + 机制→指标映射 + 边界 + 失效条件）与 `result.efficiency`；④ verify_check 新增 6 组检查（事前容差一致性 / 复现步骤 / 可复算性汇总 / 运行状态 / 失败阶段枚举 / 归因 delta 回证）；⑤ README 补齐生态贡献全套（依赖版本/安装运行/输入输出/目标用户场景/验收/FAQ/限制/失败处理/复用建议/版本维护）；⑥ SKILL.md 144 行（≤150 硬约束） |
| v4 | 协议补齐 7 条；verify_check 新增 self_check 三元组 / unbacked 数字逐字回证 / gates 闸门枚举并回写 result.json；parse_tol 兼容带注释容差串；SKILL.md 压缩至 133 行 |
| v3 | 恢复 examples 双文件自测链路；新增 build_skeleton.py 与 claims 证据链、recomputable 标注 |
| v2/v1 | 见 worklog 存档（v1=65、v2=61→v3 修复回归） |

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第四节四条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED` 与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。

---

# 存档：v4 及更早记录

见 `worklog.md`（含 v3 重做记录、v1→v2 降分回归原因分析）。
