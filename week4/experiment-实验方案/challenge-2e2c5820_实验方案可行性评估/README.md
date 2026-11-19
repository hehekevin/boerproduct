# feas-review — 实验方案可行性审查 Skill（v1）

针对 Bohrium 产品赛第 4 周「实验方案设计」赛道「实验方案可行性评估」(challenge-2e2c5820)
的参赛 Skill。锁定子场景：**七类约束逐项审查 + 四级可行性分级 + 可解释时间估算 + 风险-缓解配对 + 待复核登记**。

## 1. 用途与适用条件

给定研究目标、约束、1-3 个版本化候选实验方案与资源/条件清单（设备、耗材、样本、审批状态），完成六件事：

1. **七类约束逐项审查**：假设与变量（D1）/ 对照组（D2）/ 设备材料（D3）/ 时间成本（D4）/
   参数范围（D5）/ 风险与异常（D6）/ 伦理与安全（D7），每个方案 × 每个维度一项判定，
   维度缺口必须登记——对应题面「检查项体系」突破方向。
2. **四级可行性分级**：`feasible / conditional / infeasible / unverifiable`，口径
   **在任何判定之前事前声明**（grading_rubric，含 evidence_rule），声明后禁止调整；
   conditional 必须写清条件清单（「有条件可行」要能执行）。
3. **「没写 ≠ 满足」机械闸门**：判 feasible 必须附方案/清单逐字证据；方案未写、状态不明
   一律判 unverifiable 并登记待复核——这正是基础 Agent 的典型失分点。
4. **可解释时间估算**：按步骤拆成 `equipment_h + labor_h + wait_h` 三分量（等待不占设备
   但占排期），`estimate_time.py` 机械累加出每方案合计，无隐含系数、公式随记录落盘，
   合计数字必须在 claims 中回证——对应题面「时间成本靠感觉给数」的痛点。
5. **风险-缓解配对**：每条风险（severity 分级 + 触发条件）必须有可执行缓解措施，或显式
   `escalation_to_human=true` 并登记转人工节点；安全/伦理/专家确认项单独登记，
   **不把未经确认写成可执行事实**。
6. **待复核登记**：每个 unverifiable 条目与每条转人工风险都进 `pending_review[]`
   （含 reason 与 needed_action），人工复核入口一个不漏。

**核心保证**：`verify_check.py` 机械复算维度覆盖、口径一致性、时间合计与证据回证，
把无回证的判断与数字列入 `unbacked_numbers` 判 FAIL；`gain_probe.py` 用正常 vs 退化
双跑实测机制增益并写入 `result.gain_evidence`。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 课题组 PI / 方案作者 | 送审前自查：方案纸面通得过，但设备/排期/审批到底能不能开工 | 每维度四级分级 + 条件清单 + 缺口登记 |
| 内部评审人 | 拿到审查结论后要独立复核"凭什么判可行" | evidence_quote 逐字回证 + 时间合计机械复算 + 口径事前声明 |
| 实验负责人 / 安全员 | 只需要处理真正悬而未决的事 | pending_review 清单 + 转人工节点 + 确认项（伦理/BSL/EHS） |
| 教学 / 培训 | 演示"口径事前声明 + 没写默认不满足 + 风险必配缓解"的审查纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不做实验执行、不代查采购/审批系统实时状态、不出伦理结论（只登记待确认）；
缺什么登记什么，不脑补。

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
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 方案清单 + 检查项槽位 + 分级口径模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 声明分级口径，逐项判定 7 维度并拆解时间行（见 SKILL.md 七步流程）

# Step 3：机械汇总时间成本（写 result.time_estimate）
python3 /skills/weekly-skill/scripts/estimate_time.py --result /app/output/result.json

# Step 5：增益对照 + 效率计数（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 6：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

## 5. 输入与输出

- **输入**：`/input/case.json`（研究目标 + 约束 + 方案 + 资源清单 + output_contract）、
  `task.md`。**以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`review_scope`、`grading_rubric`、
    `dimensions`（七类约束定义）、`plans[]`、`check_items[]`（逐项判定）、`time_estimate`、
    `coverage`、`risks[]`、`confirmations[]`、`pending_review`、`steps`、`run_status`、
    `verdict`、`verdict_basis`、`gain_evidence`、`efficiency`
- **分级体系**：`status`（feasible/conditional/infeasible/unverifiable）× `severity`
  （high/medium/low）× `confidence`（high/medium/low）；判定条件与边界见 SKILL.md
  「Step 1」与 `grading_rubric` 事前声明。
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`（校验报告）、`/app/work/schema_guard.json`
  （结构报告）、`/app/work/gain_evidence.json`（增益对照证据）、
  `/app/work/grading_rubric.json`（分级口径台账）、`/app/work/gain_probe_polluted.json`
  （污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（方案/设备/审批状态均为虚构）：2 个候选方案（PL-A 微流控法 /
PL-B 复乳法）× 7 维度共 14 项检查项 → 7 feasible / 3 conditional / 1 infeasible
（PL-B 无对照组）/ 3 unverifiable（审批与异常处置未写）；2 方案时间合计 PL-A 6.0h /
PL-B 4.0h（超声耗时缺失登记缺口）；4 条风险全部配缓解或转人工（R4 废液处置转 EHS）。
示意输出关键片段：

```json
{
  "case_id": "demo-feasreview-001", "status": "answered",
  "result": {
    "grading_rubric": {"levels": {"feasible": "…", "unverifiable": "无法核实 ≠ 不满足…"}},
    "check_items": [{"check_id": "PL-A-D3", "status": "conditional",
                      "conditions": ["提前 5 天向共享平台预约微流控芯片并获得确认", "…"],
                      "evidence_quote": "共享平台托管，需提前预约（虚构）"}],
    "time_estimate": {"totals": {"PL-A": 6.0, "PL-B": 4.0}},
    "risks": [{"risk_id": "R4", "mitigation": {}, "escalation_to_human": true}],
    "verdict": "fully_reviewed"
  },
  "claims": [{"claim_id": "c-03", "source_id": "PL-A-D3",
               "evidence": [{"paragraph_id": "resources.equipment[0].status", "quote": "共享平台托管，需提前预约（虚构）"}]}]
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/estimate_time.py --result examples/example-result.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --rubric /tmp/wk/grading_rubric.json --out /tmp/vc.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 7. 验收标准（最小自检清单 — 全部实测通过，见 worklog.md）

| 编号 | 验收项 | 判定方式 | 实测 |
|------|--------|---------|------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） | PASS |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 | PASS（49 检查项全 applied） |
| A3 | 数字全回证 | `unbacked_numbers` 为空数组 | `[]` |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note | 3 闸门全 enforced |
| A5 | 全记录覆盖 | 每方案 × 7 维度逐项判定，coverage 与实际一致 | 14/14，ratio 1.0 |
| A6 | 没写 ≠ 满足 | feasible 必有逐字证据；unverifiable 必登记待复核 | 校验器抓 21 处污染违规含此两类 |
| A7 | 时间可复算 | totals 与 rows 机械累加一致；篡改 totals 判 FAIL | 篡改 6.0→99.0 被抓 |
| A8 | 风险全配对 | 每条风险有 mitigation.action 或 escalation+登记 | 4/4 |
| A9 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑 + delta + 机制映射 + 边界 | 2 runs |
| A10 | 污染被抓 | `pollution_selftest.caught_by_normal_mode == true` | true（6 项注入全抓） |
| A11 | 失败路径 exit 0 | 5 个脚本对缺失/损坏输入全部返回退出码 0 | 实测 5/5 |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（维度覆盖 + 口径一致 + 依据回证 + 风险配对） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **coverage / grading / evidence / risks 四组** |

实测对照（合成案例 + 注入 6 项污染的副本，2026-11-19 实跑，Python 3.13.14）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入 verdict / problems | PASS / 0 | PASS / 0 | — |
| 干净输入四类漏检 | 0 | 0 | 0（无违规可漏） |
| steps_count（校验项+流程步） | 55 | 6 | +49 |
| 污染副本 verdict | FAIL（21 处问题） | PASS（0 处） | −21 |
| 污染副本维度覆盖漏检 | 0 | 5 | +5 |
| 污染副本依据回证漏检 | 0 | 11 | +11 |
| 污染副本风险漏配对 | 0 | 2 | +2 |

注入的 6 项污染：PL-A-D1 判 feasible 清空证据（判断无据）/ PL-A-D3 判 conditional 清空
条件 / R1 清空缓解（有风险无缓解）/ PL-A-D7 清空 pending_reason / 清空 pending_review /
清空 claims。**同一校验器、同一污染输入**：正常模式抓全（漏检 0，21 处违规），
退化模式 18 处客观违规全部漏掉且 verdict 从 FAIL 翻成 PASS——机制增益最直接的证据。
另有单点测试：篡改 time_estimate.totals（PL-A 6.0→99.0），正常模式判 FAIL 并精确命中
「与 rows 复算不符（期望 6.0，实际 99.0）」，退化模式漏检。数字由探针独立复算违规真值，
与校验层分开实现；详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 无候选方案 / 方案为空 | check_items 空、coverage.total=0、verdict=cannot_verify 或 not_reviewed，绝不补造方案 |
| 方案缺页 / 参数缺失 / 审批状态不明 | 判 unverifiable + 登记 pending_review + material_gaps；未写 ≠ 满足 |
| 设备信息互相矛盾 | uncertainties.conflicts 登记双方 + 声明采用的优先序 |
| 时间无法拆解 | 已知行照常汇总，缺行登记 material_gaps，对应维度判 conditional |
| 大量 unverifiable | 逐条登记（含 needed_action），verdict 照实降级，不凑 fully_reviewed |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与 `problems`
列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断（5 个脚本
对缺失输入的退出码已逐一实测）。

**Q：为什么判 feasible 必须附逐字证据？**
题面明确要求审查"是否把『方案没写』误当成『方案满足』"。没有证据的 feasible 会被
verify_check 判 FAIL，这正是防"纸面合理即通过"的机械闸门。

**Q：unverifiable 是不是偷懒？**
不是——方案确实没写审批状态时，判"满足"是编造，判"不满足"是冤枉。unverifiable 必须
写 pending_reason 并登记 pending_review（含 needed_action），把人工注意力集中到真正
要去找 PI/安全员确认的条目上。

**Q：时间估算是拍脑袋吗？**
不是。每个方案按步骤拆成设备占用/人工/等待三个分量，estimate_time.py 机械累加（等待
不占设备但占排期），无隐含系数；合计数字必须在 claims 中回证，篡改会被复算抓出。
口径是本技能设定并落盘，不冒充平台标准。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。SKILL.md
明确退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：同一份方案重复运行结论会漂吗？**
判定由口径（事前声明）+ 逐字证据驱动，时间合计是确定性累加，平局无随机性；同输入
重复运行结果逐位一致。

## 11. 适用范围与限制

- 仅审查输入方案文本与条件清单：不做实验执行、不代查采购/审批系统实时状态、不出伦理结论。
- 时间估算口径（三分量累加）是本技能设定并落盘，不冒充外部标准。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘），`ablate` 参数可直接用作别处的"机制开关"对照实验 |
| `grading_rubric` 台账格式 | `{levels, evidence_rule, declared_at}` 是通用的"事前口径声明"台账 |
| `time_estimate` 三分量累加 | `equipment_h + labor_h + wait_h` 任何"可解释工时/耗时估算"需求可直接照抄 |
| `pending_review` 登记 | `{item_id, reason, needed_action}` 通用的人工复核入口格式 |
| 风险-缓解配对 | `{severity, trigger, mitigation, escalation_to_human}` 通用的风险登记格式 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改状态即得新的负例 |

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明，145 行） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/方案清单/检查项槽位/口径模板（退出码恒 0） | 是 |
| scripts/estimate_time.py | 时间三分量机械累加 + totals 回写 | 是 |
| scripts/verify_check.py | 业务校验器（维度覆盖/口径一致/依据回证/风险配对） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（2 个虚构方案 + 资源清单） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节五条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/CHECK_REQUIRED`
  与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
