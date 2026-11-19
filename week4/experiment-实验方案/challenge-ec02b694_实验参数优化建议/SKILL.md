---
name: exp-param-optimize
description: Experiment parameter optimization advisory skill (parameter-response mapping / current-value basis audit registry manual-pilot-literature / direction-magnitude-expected-gain suggestions / coupling-constraint registration with safe arithmetic evaluation / search-method selection OFAT-grid-RSM with stop criteria). Turns a research goal into a checkable advisory chain: response metrics with measurement protocols, a parameter-response map where every relation carries evidence, a current-value audit where every parameter declares unit/finite domain/basis (manual|pilot|literature|vendor)/source_ref, optimization suggestions each with direction (up/down/hold/set_to), magnitude or suggested_value, quantified expected_gain (baseline/projected/delta consistency-checked) and basis, coupling constraints (domain bounds, time-machine budgets, thermal/safety thresholds) evaluated by a restricted-AST arithmetic checker under both current and suggested value maps, and a search strategy (method/initial_points/stop_criteria/budget) mechanically compared across ≥2 candidate strategies under a pre-declared four-factor rubric with deterministic tie-breaks. Verify_check mechanically re-checks the five groups, re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency counters, and back-chains every business number into the claims evidence chain. Use when the task asks for experiment parameter optimization advice: which parameters matter, what value each should take, within what feasible range, which response metric to watch, which search strategy to run and at what cost.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 response_metrics / parameter_response_map / parameters / optimization_suggestions / coupling_constraints / search_strategy / strategy_versions / strategy_ranking / feasibility_check / risks / confirmations / completeness / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **五要素全覆盖**：参数-响应关系、当前值审计、优化建议、寻优方法、耦合约束——每一类都要落到对应键；缺材料/缺设备/缺预算就登记 material_gaps 与 confirmations，不脑补规格与报价。
4. **不编造**：当前值依据必须逐字写来源类别（manual/pilot/literature/vendor）与可查出处；当前值/建议值/预期收益数字必须出现在 claims 证据链中；预期收益必须量化（baseline/projected/delta），形容词不算收益；策略分数必须来自 score_strategy 实际输出；对不上就登记，不改证据凑结论。
5. **口径事前声明**：rubric（四因子权重 + 归一化规则 + 平局规则）必须在**任何策略排序之前**写定（declared_at），之后禁止调整；耦合约束的 source 必须可查（设备手册/材料规格/安全阈值/机时合同），不得事后改标准凑结果。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增设计，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定研究目标、约束与科研材料（含组织方前瞻性资源/价格/预约合同、有限参数域），完成**响应指标-参数响应图-当前值审计-优化建议-耦合约束-寻优方法-策略比较**的参数优化建议链。底层数据库接入、文献综述、实际实验执行、安全与伦理审批不在范围；材料缺失、约束冲突、依赖不可用照实登记，不补造设备报价或实测数据。所有算术校验基于登记的声明域/当前值/建议值，属前瞻性规划口径。
- 输入：`/input/case.json`（研究目标 + 约束 + 材料 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–7 线性推进，禁止分支回环。脚本定位以 `/app/work/skill_marker.json` 标志文件校验为准（Step 0 落盘）。

## 八步流程

### Step 0 — 自动落骨架与要素清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段与研究目标/约束/材料 → 写骨架；生成 `/app/work/rubric.json` 口径模板与 `/app/work/skill_marker.json` 脚本标志文件。
- 脚本失败时手工兜底：读 case.json 抄目标与字段名，手写骨架（键一个不缺）。

### Step 1 — 响应指标与参数-响应关系图（1 次响应）
- `result.response_metrics[]`：每个指标给 metric_id + name + unit + **measurement（口径/仪器/平行次数）** + acceptable_variation。
- `result.parameter_response_map[]`：每条 param_id + metric_id + relation（increasing/decreasing/unimodal/coupled…）+ **evidence（文献图表/预实验编号）**——引用的 param_id/metric_id 必须存在，缺 evidence 判 FAIL。
- **事前声明 rubric**：四因子权重（information_gain/cost_efficiency/robustness/risk_coverage，合计=1.0）+ tie_break + normalization + declared_at，同步写 /app/work/rubric.json。**声明后禁止调整。**

### Step 2 — 当前参数取值审计（1 次响应）
- `result.parameters[]`：每个参数 param_id + name + unit + **domain{min,max,step}（有限参数域）** + current_value（数值）+ **basis ∈ manual/pilot/literature/vendor** + source_ref（可查出处）——登记依据的取值才可进入后续优化，缺 basis 判 FAIL。

### Step 3 — 优化建议与耦合约束（1 次响应）
- `result.optimization_suggestions[]`：每条 sugg_id + param_id + direction（up/down/hold/set_to）+ magnitude 或 suggested_value + **expected_gain{metric_ref, baseline, projected, delta}（delta=projected−baseline，量化）** + basis + rationale + risk_note。
- `result.coupling_constraints[]`：每条 cid + params（引用存在的参数）+ **expression（算术表达式，支持当前值/建议值两套映射求值）** + source + severity（hard/soft）；确无耦合也须登记 kind=none_declared 条目并给 source，不脑补约束。
- `result.risks[]`：失败模式 + judge_criterion + stop_loss + fallback；`result.confirmations[]`：安全/EHS/设备档期/专家确认项，**未确认的写 status=pending，不写成可执行事实**。

### Step 4 — 寻优方法与证据链（1 次响应）
- `result.search_strategy`：method（ofat/grid/rsm/bayesian/sequential/staged_screening）+ rationale + initial_points + **stop_criteria（收敛/停止判据可复核）** + budget_note（机时/耗材口径）；method=grid 须给 grid_resolution。
- `claims[]`：每个当前值/建议值/预期收益数字建一条 `{claim_id, text, kind, source_id, location, evidence:[{paragraph_id, quote}]}`；**数值逐字回证**：数字必须出现在 claim text/quote 中（空白归一化后子串匹配），未回证数字列入 unbacked_numbers 判 FAIL。
- 运行状态 `result.run_status` 与结论分级 `result.verdict`（optimized/partially_optimized/not_optimized/cannot_verify，cannot_verify 须 material_gaps 非空）。

### Step 5 — 数值校验与策略机械比较（2 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/param_check.py --result /app/output/result.json --emit-into
python3 /skills/weekly-skill/scripts/score_strategy.py --result /app/output/result.json --k 1
```
- param_check：受限 AST 求值器（白名单四则/比较/and-or，函数调用与属性拒绝）校验当前值与建议执行值是否落声明域、逐条约束在两套映射下是否成立；越界/不成立/不可求值记 violations——**建议越界却不提示正是本题主抓的失败模式**。
- score_strategy：按事前 rubric 权重复算各 strategy_versions[].fused_score（4 位小数），按平局规则（fused_score 降序 → cost_efficiency 降序 → version_id 升序）产出 result.strategy_ranking 与 rank；并列记入 ties。至少给 2 个候选策略（如 staged_screening vs grid）并写明 changes。
- 脚本失败时手工兜底：按同一公式手算并在 steps 注明「手算」，事后仍须重跑脚本核对。

### Step 6 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（五组机械校验全开）与退化模式（--ablate all：关闭审计/建议/耦合/寻优/回证），把**真实数字**写进 `result.gain_evidence`：runs[]、delta_normal_minus_degraded、mechanism_to_metric_map、boundaries、failure_conditions。
- `--inject-pollution` 在**副本**上注入污染（清空当前值 basis / 建议依据 / 收益量化 / 耦合约束 / claims）做反例自测：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 脚本跑不了时**手工**写 gain_evidence = {available:false, reason} 与 efficiency 同理，不得编数字。退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 7 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每个当前值都有依据登记吗？每条建议都有方向、依据、量化的预期收益和风险注记吗？每条耦合约束都能被 param_check 真实算术求值、每个数字都有 claims 回证吗？

## 输出 schema（result.json — 平台通用契约五字段 + 业务键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": "…", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"question": "…", "scope": "…", "constraints": "…"},
    "rubric": {"weights": {"information_gain": 0.4, "cost_efficiency": 0.3, "robustness": 0.2, "risk_coverage": 0.1}, "tie_break": ["fused_score 降序", "cost_efficiency 降序", "version_id 升序"], "normalization": "…", "declared_at": "step1"},
    "response_metrics": [{"metric_id": "M-01", "name": "…", "unit": "…", "measurement": "口径/仪器/平行次数", "acceptable_variation": "…"}],
    "parameter_response_map": [{"map_id": "MAP-01", "param_id": "P-01", "metric_id": "M-01", "relation": "unimodal", "evidence": "文献图表/预实验编号"}],
    "parameters": [{"param_id": "P-01", "name": "…", "unit": "…", "domain": {"min": 120, "max": 180, "step": 5}, "current_value": 150, "basis": "literature", "source_ref": "可查出处"}],
    "optimization_suggestions": [{"sugg_id": "S-01", "param_id": "P-01", "direction": "set_to", "suggested_value": 165, "magnitude": null, "expected_gain": {"metric_ref": "M-01", "baseline": 78.5, "projected": 84.2, "delta": 5.7, "unit": "百分点"}, "basis": "literature", "rationale": "…", "risk_note": "…"}],
    "coupling_constraints": [{"cid": "C-01", "params": ["P-01", "P-02"], "expression": "P-01 * P-02 <= 2500", "source": "设备手册/安全阈值/机时合同", "severity": "hard"}],
    "search_strategy": {"method": "staged_screening", "rationale": "…", "initial_points": "…", "grid_resolution": null, "stop_criteria": "…", "budget_note": "…"},
    "strategy_versions": [{"version_id": "V1", "summary": "…", "factors": {"information_gain": 0.9, "cost_efficiency": 0.75, "robustness": 0.8, "risk_coverage": 0.8}, "fused_score": 0.825, "rank": 1, "changes": "…"}],
    "strategy_ranking": {"ordered_ids": ["V1"], "ties": [], "top_k": ["V1"], "k_value": 1},
    "feasibility_check": {"tool": "scripts/param_check.py", "checked_count": 7, "violations": [], "warnings": [], "all_within_domain": true, "all_constraints_satisfied": true},
    "risks": [{"risk_id": "R-01", "failure_mode": "…", "judge_criterion": "…", "stop_loss": "…", "fallback": "…"}],
    "confirmations": [{"item": "…", "kind": "safety | ethics | equipment | expert", "status": "pending | confirmed"}],
    "completeness": {"parameters_total": 4, "metrics_total": 2, "map_entries": 4, "suggestions_total": 4, "constraints_total": 3, "risks_total": 2, "strategy_versions": 3},
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "optimized | partially_optimized | not_optimized | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "当前值+建议+依据+收益", "kind": "reported | inferred", "source_id": "lit-doe-2019", "location": "optimization_suggestions[S-01]", "evidence": [{"paragraph_id": "lit-doe-2019 表3", "quote": "原文"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py，--ablate 审计/建议/耦合/寻优/回证五组可关）
1. 当前值审计不全：parameters 为 0；任一参数缺 name/unit/basis/source_ref/当前值数值或 domain(min/max)；basis 不在 manual/pilot/literature/vendor 枚举。
2. 建议不完备：optimization_suggestions=0；param_id 引用不存在；basis/rationale 空；expected_gain 缺 metric_ref/baseline/projected/delta 或 delta≠projected−baseline（收益虚标即 FAIL）；set_to 无数值。
3. 耦合约束缺陷：coupling_constraints=0（确无耦合须登记 none_declared+source）；params 引用不存在的参数；expression/source 空；severity 枚举非法。
4. 寻优方法缺陷：method 缺失或不在枚举；rationale/stop_criteria/budget_note/initial_points 空（停止判据说不清即 FAIL）；method=grid 缺 grid_resolution。
5. 依据/风险/回证：parameter_response_map 空、条目缺 relation/evidence 或引用无效；响应指标缺测量口径；risks 缺判据或止损；当前值/建议值/projected 数字未出现在 claims（unbacked_numbers 判 FAIL）。
6. 策略排序：fused_score 与 rubric 权重复算不符；ordered_ids 与复算顺序不一致；rubric 未事前声明或权重合计≠1.0。
7. 常开检查：枚举合法性、completeness 汇总与实际条目不符、verdict 与要素进度矛盾、run_status/steps 违规、契约字段缺失、闸门（case_contract / rubric_ledger / skill_scripts / strategy_ranking_recompute / param_feasibility_check）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，材料与数据均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/param_check.py --result examples/example-result.json --out /tmp/pc.json
python3 scripts/score_strategy.py --result examples/example-result.json --k 1 --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --marker /tmp/wk/skill_marker.json --rubric /tmp/wk/rubric.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --marker /tmp/wk/skill_marker.json --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 材料/设备/预算信息缺失 | material_gaps 登记 + confirmations 写 pending，参数域留待定，不脑补规格报价 |
| 约束冲突（目标值与耐温/安全阈值/机时冲突） | param_check violations 如实登记；放宽 soft 约束须在 uncertainties.conflicts 登记双方与代价，绝不静默放宽 hard 约束 |
| 无可行解 | verdict=partially_optimized/not_optimized + reason，risks[R].fallback 给转人工路径 |
| 数据缺失（响应关系无出处） | relation 留待定 + evidence 登记缺口，不补造文献 |
| 指标互相矛盾（转化率↑但副产物↑） | parameter_response_map 分列两条关系 + suggestions 风险注记联动监控 + trade-off 写入 rationale |
| 大量同分 | score_strategy 把并列组记入 ties，按 tie_break 规则破平并在 ranking 可见 |
| 算力/时间不足 | 保留已完成要素，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅处理输入范围内的参数优化建议：不做文献综述、不执行实验、不替代安全与伦理审查；不冒充设备量程认定或安全认证。
- 预期收益为前瞻性折算口径（依据登记的来源推算并写明），不是实测承诺；预测不确定度写入 uncertainties.unverifiable。
- 参数域/约束取自输入登记与声明出处；输入未给时不臆造，登记 material_gaps。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；追问轮次按每轮 3 条折算，非实测交互次数。
