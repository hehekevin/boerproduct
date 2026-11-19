---
name: exp-plan-design
description: Experiment plan generation and optimization skill (hypothesis-to-variable tables / control design / power-based sample size registry / analysis-plan alignment). Turns a research goal into a checkable hypothesis, an operational variable table (independent/dependent/control with operational definition, measurement method, unit and range), a control design that names the confound each control excludes, step protocols bound to equipment/reagents/parameter ranges/time cost, failure modes with judge criteria and stop-loss, and an analysis plan aligned to every hypothesis. Score_plan mechanically compares versioned candidate plans under a pre-declared four-factor rubric with deterministic tie-breaks. Verify_check mechanically re-checks variable completeness, control design, sample-size/power justification registration, hypothesis-analysis alignment and numeric back-evidence through the claims chain, then re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency counters into result.json. Use when the task asks to design, compare, optimize or explain an experiment plan with variables, controls, parameters, risks and justifications.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 hypotheses / variables / controls / groups / power_basis / protocol / analysis_plan / risks / confirmations / plan_versions / plan_ranking / completeness / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **六类要素全覆盖**：假设与变量、对照组、设备材料、时间成本、参数范围、风险和异常——每一类都要落到对应键；缺材料/缺设备/缺预算就登记 material_gaps 与 confirmations，不脑补规格与报价。
4. **不编造**：参数依据必须逐字写来源类别（manual/pilot/literature/vendor）与可查出处；数值参数必须出现在 claims 证据链中；方案分数必须来自 score_plan 实际输出；对不上就登记，不改证据凑结论。
5. **口径事前声明**：rubric（四因子权重 + 归一化规则 + 平局规则）必须在**任何方案排序之前**写定（declared_at），之后禁止调整；假设逐条给 hypothesis_id，分析计划判定必须引用 id，不得事后改标准凑结果。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增设计，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定研究目标、约束与科研材料（含组织方的前瞻性资源/价格/预约合同），完成**假设-变量表-对照-分组-功效依据-步骤参数-风险预案-分析对齐**的完整方案生成与候选方案机械比较。底层数据库接入、文献综述、实际实验执行、安全与伦理审批不在范围；材料缺失、约束冲突、依赖不可用照实登记，不补造设备报价或实测数据。
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

### Step 1 — 假设与变量表（1 次响应）
- `result.research_question`（question/scope/constraints）与 `result.hypotheses[]`：目标拆成可检验假设（hypothesis_id + text + testable=true）。
- `result.variables`：independent / dependent / control 三组，**每个变量**必须给 `name + operational_definition + measurement + unit`（缺一会被校验器判 FAIL）；量程与水平数写进 range/level_count。
- **事前声明 rubric**：四因子权重（completeness/feasibility/risk_coverage/cost_efficiency，合计=1.0）+ tie_break + normalization + declared_at，同步写 /app/work/rubric.json。**声明后禁止调整。**

### Step 2 — 对照、分组与功效依据（1 次响应）
- `result.controls[]`：空白/阳性/阴性/剂量梯度按需组合，**每个对照必须写明 excludes_confound（排除哪一类混杂）与 basis（设置依据）**；type ∈ blank/positive/negative/dose_gradient/vehicle/sham。
- `result.groups[]`：处理组 + 对照（groups≥2），n 为正整数，randomization 写明随机化方式。
- `result.power_basis.n_registry[]`：**每个组的 n 都要登记**功效依据（method 含检验方法/效应量/alpha/power，source 写预实验或文献），n 与 groups 一致——未登记判 FAIL。

### Step 3 — 步骤、参数与时间成本（1 次响应）
- `result.protocol[]`：每步绑定 equipment/reagents，参数逐个给 `value + unit + range + basis`（basis ∈ manual/pilot/literature/vendor）；duration_min 与 cost_yuan 使方案可排期可报价。
- `result.measurements[]`：每个因变量一条（dv_ref + instrument + precision + timing）。
- `result.risks[]`：失败模式（污染/无信号/重复性差/样本不足等）+ judge_criterion + stop_loss + fallback；`result.confirmations[]`：安全/伦理/设备可用性/专家确认项，**未确认的写 status=pending，不写成可执行事实**。

### Step 4 — 分析计划对齐与证据链（1 次响应）
- `result.analysis_plan[]`：**每个 hypothesis_id 必须被 ≥1 条引用**（dv_ref/test/alpha 齐备），引用的 id 必须存在——分析计划与假设不对齐判 FAIL。
- `claims[]`：protocol 关键参数与方案结论各建一条 `{claim_id, text, kind, source_id, location, evidence:[{paragraph_id, quote}]}`；**数值逐字回证**：protocol 数值参数必须出现在某条 claim text/quote 中（空白归一化后子串匹配），未回证数字列入 unbacked_numbers 判 FAIL。
- 运行状态 `result.run_status` = {state ∈ success|partial|unable_to_determine|refused, reason, manual_takeover[]}；非 success 必须写 reason。
- 结论分级 `result.verdict`：`designed` 要素齐备可执行；`partially_designed` 部分完成；`not_designed` 未产出有效设计；`cannot_verify` 材料缺口导致无法判定（material_gaps 非空）。

### Step 5 — 候选方案机械比较（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/score_plan.py --result /app/output/result.json [--k 1]
```
- 按事前 rubric 权重机械复算各 plan_versions[].fused_score（保留 4 位小数），按平局规则（fused_score 降序 → feasibility 降序 → version_id 升序）产出 `result.plan_ranking`（ordered_ids / ties / top_k / k_value）与 rank；同分并列记入 ties。至少给 2 个候选版本（完整版 + 至少 1 个取舍变体）并写明 changes。
- 脚本失败时手工兜底：按同一公式手算并在 steps 注明「手算」，事后仍须重跑脚本核对。

### Step 6 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（五组机械校验全开）与退化模式（--ablate all：关闭变量表/对照设置/功效依据/分析对齐/证据回证），把**真实数字**写进 `result.gain_evidence`：runs[]、delta_normal_minus_degraded、mechanism_to_metric_map、boundaries、failure_conditions。
- 六项对照指标：变量表违规漏检 / 对照违规漏检 / 功效漏登记 / 对齐漏检 / 回证漏检 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- `--inject-pollution` 在**副本**上注入污染（无对照设计 / 变量缺操作定义 / 清空功效登记 / 清空分析计划 / 清空 claims）做反例自测：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence` = {available:false, reason} 与 `efficiency` = {available:false, reason}，不得编数字。退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 7 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：六类要素都落到键了吗？每个组都有功效依据、每个对照都写明排除混杂吗？每个假设都被分析计划引用、每个数值参数都有 claims 回证吗？

## 输出 schema（result.json — 平台通用契约五字段 + 业务键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": "…", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"question": "…", "scope": "…", "constraints": "…"},
    "rubric": {"weights": {"completeness": 0.4, "feasibility": 0.3, "risk_coverage": 0.2, "cost_efficiency": 0.1}, "tie_break": ["fused_score 降序", "feasibility 降序", "version_id 升序"], "normalization": "…", "declared_at": "step1"},
    "hypotheses": [{"hypothesis_id": "H-01", "text": "…", "testable": true}],
    "variables": {"independent": [{"var_id": "IV-01", "name": "…", "operational_definition": "…", "measurement": "…", "unit": "…", "range": "…", "level_count": 2}], "dependent": [{"…同上…"}], "control": [{"…同上…"}]},
    "controls": [{"control_id": "CTL-01", "type": "blank", "group_id": "G-03", "excludes_confound": "排除哪类混杂", "basis": "依据"}],
    "groups": [{"group_id": "G-01", "name": "处理组", "treatment": "…", "n": 36, "randomization": "…"}],
    "power_basis": {"n_registry": [{"group_id": "G-01", "n": 36, "method": "效应量/alpha/power", "source": "预实验或文献"}]},
    "protocol": [{"step_id": "S1", "action": "…", "equipment": "…", "reagents": "…", "params": [{"name": "…", "value": 300, "unit": "…", "range": "…", "basis": "literature"}], "duration_min": 45, "cost_yuan": 120}],
    "measurements": [{"metric_id": "M-01", "dv_ref": "DV-01", "instrument": "…", "unit": "…", "precision": "…", "timing": "…"}],
    "analysis_plan": [{"analysis_id": "A-01", "hypothesis_id": "H-01", "dv_ref": "DV-01", "test": "…", "alpha": 0.05, "tool": "…"}],
    "risks": [{"risk_id": "R-01", "failure_mode": "…", "judge_criterion": "…", "stop_loss": "…", "fallback": "…"}],
    "confirmations": [{"item": "…", "kind": "safety | ethics | equipment | expert", "status": "pending | confirmed"}],
    "plan_versions": [{"version_id": "V1", "summary": "…", "factors": {"completeness": 0.9, "feasibility": 0.8, "risk_coverage": 0.7, "cost_efficiency": 0.6}, "fused_score": 0.8, "rank": 1, "changes": "…"}],
    "plan_ranking": {"ordered_ids": ["V1"], "ties": [], "top_k": ["V1"], "k_value": 1},
    "completeness": {"hypotheses_total": 1, "variables_defined": 4, "controls_count": 2, "groups_total": 4, "protocol_steps": 3, "analysis_entries": 1, "aligned_hypotheses": 1, "ratio": 1.0},
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "designed | partially_designed | not_designed | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "参数+依据+结论", "kind": "reported | inferred", "source_id": "H-01", "location": "protocol[S2]", "evidence": [{"paragraph_id": "protocol[S2].params", "quote": "原文"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py，--ablate 变量表/对照/功效/对齐/回证五组可关）
1. 变量表不完备：独立/因变量或控制变量为 0；任一变量缺操作定义、测量方式或单位；假设 text 空或 testable≠true。
2. 对照设置违规：groups<2 或 controls=0；control 的 group_id 不在 groups；excludes_confound 或 basis 空；type 枚举非法。
3. 功效依据缺失：任一组的 n 未在 n_registry 登记，或登记的 n/method/source 与 groups 不符；alpha/power 不在 (0,1)。
4. 对齐违规：假设未被任何 analysis_plan 引用；引用不存在的 hypothesis_id/dv_ref；test 空；因变量无测量条目。
5. 依据/风险/回证：protocol 空、参数缺 basis、risks 缺判据或止损、数值参数未出现在 claims（unbacked_numbers 判 FAIL）、claims 为空但存在数值参数。
6. 方案排序：fused_score 与 rubric 权重复算不符；ordered_ids 与复算顺序不一致；rubric 未事前声明或权重合计≠1.0。
7. 常开检查：枚举合法性、completeness 汇总与实际条目不符、verdict 与要素进度矛盾、run_status/steps 违规、契约字段缺失、闸门（case_contract / rubric_ledger / skill_scripts / plan_ranking_recompute）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，材料与数据均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/score_plan.py --result examples/example-result.json --k 1 --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --marker /tmp/wk/skill_marker.json --rubric /tmp/wk/rubric.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --marker /tmp/wk/skill_marker.json --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 材料/设备/预算信息缺失 | material_gaps 登记 + confirmations 写 pending，参数留 range 待定，不脑补规格报价 |
| 约束冲突（时间窗 vs 样本量/预算） | uncertainties.conflicts 登记双方 + 声明取舍（如减组不减重复），给出被舍弃方案的代价 |
| 依赖不可用（试剂缺货/设备排期满） | risks 增加 fallback 路径；设备档期写进 confirmations 待确认 |
| 无有效对照可行（伦理/材料限制） | verdict=partially_designed，controls 空 + reason 写明，绝不静默交无对照设计 |
| 大量同分 | score_plan 把并列组记入 ties，按 tie_break 规则破平并在 ranking 可见 |
| 算力/时间不足 | 保留已完成要素，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅处理输入范围内的方案生成与比较：不做文献综述、不执行实验、不替代安全与伦理审查。
- 功效分析按 n_registry 声明的口径计算（预实验/文献未给定时按保守量级设定并写明），不冒充外部标准。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；追问轮次按每轮 3 条折算，非实测交互次数；平台白板对照由平台生成。
