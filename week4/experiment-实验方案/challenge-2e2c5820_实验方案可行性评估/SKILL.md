---
name: feas-review
description: Experiment plan feasibility review skill (seven-constraint coverage / pre-declared grading rubric / evidence-backed judgments / risk-mitigation pairing / pending registry). Reviews versioned experiment plans across seven constraint dimensions (assumptions & variables, controls, equipment & materials, time cost, parameter ranges, risks & exceptions, ethics & safety), grading every check item as feasible/conditional/infeasible/unverifiable against a rubric declared before any judgment, with verbatim evidence quotes — never treating "not written in the plan" as "satisfied". Mechanically sums per-step time estimates (equipment occupancy + labor + waiting) into per-plan totals with an explainable, reproducible formula, pairs every identified risk with a concrete mitigation or an explicit human-escalation node, and registers every unverifiable item and pending confirmation for human review. Verify_check mechanically re-computes dimension coverage, grading consistency, evidence back-checks and risk-mitigation pairing, and re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency counters into result.json. Use when the task asks to assess whether an experiment plan is executable under equipment, material, time, sample, ethics and safety constraints, and to produce a reviewable, re-runnable feasibility verdict.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 check_items / time_estimate / coverage / risks / confirmations / pending_review / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全记录覆盖**：每个方案 × 七类约束（D1 假设与变量 / D2 对照组 / D3 设备材料 / D4 时间成本 / D5 参数范围 / D6 风险与异常 / D7 伦理与安全）都必须逐项判定（judged=true 或写明 pending_reason），禁止只判前几个维度就收尾；方案没写的内容判 unverifiable 并登记，**不得默认为已满足**。
4. **不编造**：evidence_quote 必须逐字摘自方案文本/条件清单/资源清单实际内容并附位置；时间合计必须来自 estimate_time 实际输出；对不上就登记，不改证据凑结论；设备/审批状态不明的照实标 unverifiable。
5. **口径事前声明**：grading_rubric（feasible / conditional / infeasible / unverifiable 四级边界 + evidence_rule）必须在**任何分级判定之前**写定（declared_at），之后禁止调整；「有条件可行」必须写清条件清单，不得事后改口径凑结论。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定研究目标、约束与 1-3 个版本化候选实验方案 + 资源/条件清单（设备、耗材、样本、审批状态），完成**七类约束逐项审查、四级可行性分级、可解释时间估算、风险-缓解配对、待复核登记**。实验执行、数据分析、文献综述、论文写作不在范围；材料缺页、参数缺失、审批状态不明照实登记，不补造条件。
关键词：判得实（没写 ≠ 满足，逐条回证）· 级得稳（四级口径事前声明）· 算得清（时间三分量机械累加、公式落盘）· 配得全（风险必有缓解或转人工节点）。
- 输入：`/input/case.json`（研究目标 + 约束 + 方案 + 资源清单 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与检查项槽位（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（plans/proposals/schemes 等）提取候选方案，按方案 × 七类约束预填 `result.check_items[]` 槽位；生成 `/app/work/grading_rubric.json` 分级口径模板。
- 脚本失败时手工兜底：读 case.json 抄方案清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 审查范围与分级口径（1 次响应，判定前完成）
- 填 `result.review_scope`（objective / constraints / plan_ids）与 `result.grading_rubric`：四级边界逐级写清（feasible=条件明确支持且附证据；conditional=可行但须列出前置条件；infeasible=与条件/文本直接冲突或关键要素缺失无替代路径；unverifiable=方案未写或状态不明，**无法核实 ≠ 不满足**），同步写 /app/work/grading_rubric.json。**声明后禁止调整。**

### Step 2 — 逐项判定与时间行拆解（1-3 次响应，广度优先）
对 `result.check_items[]` 中**每一项**（每方案 × 7 维度），缺一不可：
- `status` ∈ feasible/conditional/infeasible/unverifiable，判定必须引用 Step 1 口径；
- feasible/infeasible 必须附 `evidence_quote`（逐字摘自方案或资源清单）+ `evidence_location` + `rationale`；conditional 必须填 `conditions[]`（每条可执行）；unverifiable 必须写 `pending_reason` 并登记进 pending_review；
- `basis_type` ∈ plan/resource/sop/assumption，注明依据来自方案文本、条件清单还是本方假设；
- 时间行：按方案步骤把 `result.time_estimate.rows[]` 填成 `{plan_id, step_id, equipment_h, labor_h, wait_h}`（设备占用 + 人工 + 等待，等待不占设备但占排期）；缺耗时的步骤登记 material_gaps。

### Step 3 — 机械时间汇总（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/estimate_time.py --result /app/output/result.json
```
- 机械累加每行 total_h=equipment_h+labor_h+wait_h 与每方案 totals（保留 2 位），回写 `result.time_estimate`；无隐含系数，公式随记录落盘。
- 脚本失败时手工兜底：按同一公式手算并在 steps 注明「手算」，事后仍须重跑脚本核对。

### Step 4 — 风险配对、确认项与证据链（1 次响应）
- `result.risks[]`：每条风险 `{risk_id, plan_id, dimension, description, severity∈high/medium/low, trigger, mitigation:{action,owner,trigger_condition}, escalation_to_human}`；**无缓解措施的风险必须 escalation_to_human=true 并登记进 pending_review**（转人工节点）。
- `result.confirmations[]`：安全/伦理/设备可用性/专家确认项逐条登记 `{topic, needed_action}`；**不把未经确认的建议写成可执行事实**。
- **claims 证据链**：每个 feasible/conditional/infeasible 判定在 `claims[]` 各有一条 `{claim_id, text, kind, source_id=check_id, location, evidence:[{paragraph_id, quote}]}`；时间合计数字必须出现在 claim text/quote 里（空白归一化后子串匹配），未回证数字列入 unbacked_numbers 并判 FAIL。
- 结论分级 `result.verdict`（verdict_basis 一句话写依据）：`fully_reviewed` 全部逐项判定；`partially_reviewed` 部分判定；`not_reviewed` 未产生有效判定；`cannot_verify` 材料缺口导致无法判定且 material_gaps 非空。
- 运行状态 `result.run_status` = `{state, reason, manual_takeover[]}`，`state` ∈ success|partial|unable_to_determine|refused；非 success 必须写 reason 与人工接管位置。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭维度覆盖/口径一致/依据回证/风险配对），把**真实数字**写进 `result.gain_evidence`：`runs[]`、`delta_normal_minus_degraded`、`mechanism_to_metric_map`、`boundaries`、`failure_conditions`。
- 五项对照指标：维度覆盖漏检数 / 口径失据漏检数 / 依据缺失漏检数 / 风险漏配对数 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- 同时写 `result.efficiency`（墙钟、字节、检查项数、需人工条目、追问轮次 + `reproduce` 复现命令）；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- `--inject-pollution` 在**副本**上注入污染（判断无据 / 有条件无清单 / 有风险无缓解 / 待复核清空 / 证据链清空）做反例自测：正常模式须抓到（`caught_by_normal_mode=true`），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence` = `{available:false, reason:"…"}` 与 `efficiency` = `{available:false, reason:"…"}`，不得编数字。
- 退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每个方案 × 七维度都有判定或待复核吗？每个 feasible/conditional 都能回溯到逐字证据与条件清单吗？无缓解的风险都转人工登记了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "review_scope": {"objective": "…", "constraints": ["…"], "plan_ids": ["PL-A"]},
    "grading_rubric": {"levels": {"feasible": "…", "conditional": "…", "infeasible": "…", "unverifiable": "…"}, "evidence_rule": "…", "declared_at": "step1"},
    "dimensions": [{"dimension_id": "D1", "name": "assumptions_variables", "label": "假设与变量"}],
    "plans": [{"plan_id": "PL-A", "title": "…", "source_ref": "plans[0]"}],
    "check_items": [{"check_id": "PL-A-D1", "plan_id": "PL-A", "dimension": "D1", "item_text": "…", "status": "feasible", "conditions": [], "basis_type": "plan", "evidence_quote": "逐字摘录", "evidence_location": "plans[0].hypothesis", "rationale": "…", "confidence": "high", "pending_reason": null, "judged": true}],
    "time_estimate": {"rows": [{"plan_id": "PL-A", "step_id": "S1", "equipment_h": 0.5, "labor_h": 0.5, "wait_h": 0.0, "total_h": 1.0}], "totals": {"PL-A": 6.0}, "note": "…", "computed_by": "estimate_time.py"},
    "coverage": {"total_checks": 14, "judged": 14, "per_dimension": {"D1": 2}, "per_status": {"feasible": 7, "conditional": 3, "infeasible": 1, "unverifiable": 3}, "missing_dimensions": [], "ratio": 1.0},
    "risks": [{"risk_id": "R1", "plan_id": "PL-A", "dimension": "D3", "description": "…", "severity": "high", "trigger": "…", "mitigation": {"action": "…", "owner": "…", "trigger_condition": "…"}, "escalation_to_human": false, "evidence_location": "…"}],
    "confirmations": [{"confirm_id": "CF1", "plan_id": "PL-A", "topic": "…", "status": "pending_confirmation", "needed_action": "…"}],
    "pending_review": [{"item_id": "PL-A-D7", "reason": "…", "needed_action": "…"}],
    "conflicts": [], "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "fully_reviewed | partially_reviewed | not_reviewed | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "判定依据+证据说明（含时间数字）", "kind": "reported | inferred", "source_id": "PL-A-D1", "location": "check_items[0]", "evidence": [{"paragraph_id": "plans[0].hypothesis", "quote": "方案原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. check_items.dimension / status / confidence、risks.severity、risks.dimension、verdict、run_status.state 枚举非法。
2. 判 feasible 无逐字证据（**方案没写 ≠ 方案满足**）；判 conditional 未列条件；判 infeasible 无 rationale；判 unverifiable 无 pending_reason 或未登记进 pending_review。
3. 维度覆盖缺口（某方案缺某维度判定）未登记进 coverage.missing_dimensions；grading_rubric 未事前声明或 evidence_rule 为空；coverage.per_status / per_dimension / total_checks 与实际不符。
4. time_estimate.totals 与 rows 机械复算不符；已判定条目 rationale 为空；feasible/conditional/infeasible 的证据在 claims 无逐字回证；时间合计数字无回证 → unbacked_numbers 判 FAIL。
5. 风险无 mitigation.action 且未转人工（escalation_to_human=true 须登记 pending_review）；确认项缺 topic/needed_action。
6. verdict 与判定进度矛盾；steps 为空或无可执行 command。
7. 闸门（case_contract / grading_ledger / estimate_output）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，方案/设备/审批状态均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/estimate_time.py --result examples/example-result.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --rubric /tmp/wk/grading_rubric.json --out /tmp/vc.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 无候选方案 / 方案为空 | check_items 空、coverage.total=0、verdict=cannot_verify 或 not_reviewed，status 写明，绝不补造方案 |
| 方案缺页 / 参数缺失 / 审批状态不明 | 该项判 unverifiable + 登记 pending_review + material_gaps，置信度不虚高；未写 ≠ 满足 |
| 设备信息互相矛盾 | uncertainties.conflicts 登记双方 + 声明采用的优先序，不混用两套口径 |
| 时间无法拆解（步骤缺耗时） | 已知行照常汇总，缺行登记 material_gaps，对应维度判 conditional |
| 大量 unverifiable | 逐条登记 pending_review（含 needed_action），verdict 照实降级，不凑 fully_reviewed |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅审查输入方案文本与条件清单：不做实验执行、不代查采购系统/审批系统实时状态、不出伦理结论（伦理项只登记待确认）。
- 时间估算是 rows 三分量机械累加（设备占用+人工+等待），口径是本技能设定并落盘，不冒充平台标准；数值依赖 Agent 读方案的拆解质量。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
