---
name: exp-plan-compare
description: Experiment plan comparison and selection skill (unified scoring matrix / pre-declared five-dimension weights / per-dimension evidence back-references / mechanical weighted-total recompute / weight-perturbation sensitivity analysis / defensible choice with rejection registry). Registers organizer-provided candidate plans under one comparable field structure, declares a five-dimension rubric (scientific_value/feasibility/cost/duration/risk_control, sum=1.0) BEFORE any ranking, scores every plan×dimension cell with score+basis+evidence_ref back-chained to claims, mechanically recomputes fused scores and a deterministic tie-broken ranking via score_plan, runs a 40-variant weight-perturbation sensitivity grid with flip conditions, registers final choice reasons plus per-plan rejection reasons, then re-runs normal-vs-degraded ablation (gain_probe) to embed measured gain_evidence and efficiency into result.json. Use when the task asks to compare and select among candidate experiment plans with unified dimensions, weight pre-declaration, evidence-backed scores, total recompute, sensitivity analysis and defensible trade-offs.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 rubric / comparability / plan_versions / plan_ranking / sensitivity / final_choice / completeness / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **统一口径先行**：五维 rubric 权重（scientific_value/feasibility/cost/duration/risk_control，合计=1.0）与 tie_break/normalization 必须在**任何方案排序之前**声明（declared_at），声明后禁止调整；三个候选方案必须用同一字段结构逐维度填格，禁止各方案各用一套描述。
4. **不编造**：每格打分必须带 score+basis+evidence_ref，evidence_ref 指向 claims 中带非空 quote 的条目；方案分数必须来自 score_plan 实际输出；组织方材料没有的价格/排期/实测一律登记 material_gaps 与 confirmations（pending），不脑补报价与档期。
5. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增比较，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
6. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
7. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。
8. **选择要可辩护**：final_choice.chosen_id 必须等于机械排序第 1 名；每个落选方案都要登记非空 rejection_reason 与 tradeoff；overall_stable=false 时必须在 choice_reasons 写明翻转条件。

## 定位与约定
锁定子场景：给定研究目标、约束与组织方预置的多个候选方案（含前瞻性价格/排期/预约合同），完成**统一口径声明 → 逐维度打分与依据回证 → 加权总分机械复算 → 权重敏感性分析 → 最终选择与放弃理由登记**的完整比较链路。路线原始设计创新、文献综述、实际实验执行、安全伦理审批不在范围；材料缺失、约束冲突、依赖不可用照实登记，不补造报价或实测数据。
- 输入：`/input/case.json`（研究目标 + 约束 + 候选方案 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。脚本定位以 `/app/work/skill_marker.json` 标志文件校验为准（Step 0 落盘）。

## 七步流程

### Step 0 — 自动落骨架与要素清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段与研究目标/约束/候选方案 → 写骨架；生成 `/app/work/rubric.json` 口径模板与 `/app/work/skill_marker.json` 标志文件。
- 脚本失败时手工兜底：读 case.json 抄目标与字段名，手写骨架（键一个不缺）。

### Step 1 — 权重与口径事前声明（1 次响应）
- `result.rubric`：五维权重（合计=1.0）+ tie_break（fused_score 降序 → risk_control 降序 → plan_id 升序）+ normalization + declared_at，**在任何排序之前填写**，同步更新 /app/work/rubric.json 台账。**声明后禁止调整。**
- `result.comparability.dimensions[]`：五维逐条给 definition + scale + scoring_rule（如"总成本 ≤1000 元→1.0"），所有方案共用，禁止每方案一套算法。

### Step 2 — 逐方案逐维度打分与依据回证（1 次响应）
- `result.plan_versions[]`：登记组织方全部候选方案（plan_id/summary/source），每方案 `factors`（五维 0-1 数值）+ `factors_detail`（每维 score+basis+evidence_ref）。
- `claims[]`：每个 evidence_ref 建一条 `{claim_id, text, kind, source_id, location, evidence:[{paragraph_id, quote}]}`，quote 引用案例材料/文献/设备手册/预实验原文——**回证断裂会被校验器判 FAIL**。

### Step 3 — 选中方案执行要素与风险登记（1 次响应）
- 对拟选方案落可执行要素：`hypotheses`（hypothesis_id+testable）、`variables`（三组，每个变量 name+operational_definition+measurement+unit）、`controls`（每个对照写明 excludes_confound+basis）、`groups`+`power_basis.n_registry`（每组 n 登记功效依据）、`protocol`（参数逐个 value+unit+range+basis，duration_min+cost_yuan 可排期可报价）、`analysis_plan`（每个 hypothesis 被引用）、`risks`（failure_mode+judge_criterion+stop_loss+fallback）、`confirmations`（未确认一律 status=pending）。
- protocol 数值参数必须出现在 claims（空白归一化后子串匹配），否则进 unbacked_numbers 判 FAIL。
- 运行状态 `run_status` 与结论分级 `verdict`：`selected | partially_selected | not_selected | cannot_verify`（cannot_verify 须 material_gaps 非空）。

### Step 4 — 机械排序与敏感性分析（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/score_plan.py --result /app/output/result.json --k 1
```
- 机械复算各 plan_versions[].fused_score（保留 4 位小数），按平局规则产出 `result.plan_ranking`（ordered_ids/ties/top_k/k_value）与 rank；同分记入 ties 不静默破平。
- 自动做 40 变体权重扰动敏感性（每维 ±0.05/0.10/0.15/0.20，其余维度按比例归一）：写 `result.sensitivity`（variants/flip_conditions/overall_stable）。overall_stable=false 时把翻转条件写进 final_choice.choice_reasons。
- 脚本失败时手工兜底：按同一公式手算并在 steps 注明「手算」，事后仍须重跑脚本核对。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（六组校验全开）与退化模式（--ablate all：关闭权重声明/口径统一/依据回证/总分复算/敏感性/选择登记），真实数字写进 `result.gain_evidence`。
- `--inject-pollution` 在**副本**上注入污染（总分篡改/清空 claims/权重置 None/清空 sensitivity/清空 rejected）：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 脚本跑不了时手工写 `gain_evidence`={available:false, reason}，不得编数字。退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：五维口径与权重事前声明了吗？每格打分都有依据回证、总分能复算一致吗？最终选择与每个落选方案的理由都登记了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 业务键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": "…", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"question": "…", "scope": "…", "constraints": "…"},
    "rubric": {"weights": {"scientific_value": 0.3, "feasibility": 0.25, "cost": 0.15, "duration": 0.1, "risk_control": 0.2}, "tie_break": ["fused_score 降序", "risk_control 降序", "plan_id 升序"], "normalization": "…", "declared_at": "step1"},
    "comparability": {"dimensions": [{"dim": "…", "definition": "…", "scale": "0-1", "scoring_rule": "…"}], "unified_note": "…"},
    "plan_versions": [{"plan_id": "P1", "summary": "…", "source": "organizer-case", "factors": {"scientific_value": 0.85, "…": 0}, "factors_detail": {"scientific_value": {"score": 0.85, "basis": "…", "evidence_ref": "c-01"}}, "fused_score": 0.795, "rank": 1}],
    "plan_ranking": {"ordered_ids": ["P1"], "ties": [], "top_k": ["P1"], "k_value": 1},
    "sensitivity": {"available": true, "base_winner": "P1", "variants": [], "flip_conditions": [{"dim": "cost", "direction": "+", "min_flip_delta": 0.15, "winner_after": "P3"}], "overall_stable": true},
    "final_choice": {"chosen_id": "P1", "choice_reasons": ["…"], "expert_confirmation_needed": ["…"], "rejected": [{"plan_id": "P2", "rejection_reason": "…", "tradeoff": "…"}]},
    "hypotheses": [], "variables": {"independent": [], "dependent": [], "control": []},
    "controls": [], "groups": [], "power_basis": {"n_registry": []},
    "protocol": [], "measurements": [], "analysis_plan": [], "risks": [], "confirmations": [],
    "completeness": {"candidates_total": 3, "dimensions_declared": 5, "scored_cells": 15, "backed_cells": 15, "sensitivity_variants": 40, "rejected_registered": 2, "claims_total": 19, "ratio": 1.0},
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "selected | partially_selected | not_selected | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "打分依据+出处", "kind": "reported | inferred", "source_id": "P1", "location": "case.candidate_plans[P1]", "evidence": [{"paragraph_id": "candidate_plans.P1", "quote": "原文"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract | rubric_ledger | skill_scripts | plan_ranking_recompute | sensitivity_recompute", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py，--ablate 六组可关）
1. 权重声明：五维权重非法或合计≠1.0；declared_at 为空；与 rubric.json 台账不一致（声明后禁止调整）。
2. 口径统一：comparability 五维缺 definition；任一方案×维度缺 score(0-1)/basis/evidence_ref（一格缺失即 FAIL）。
3. 依据回证：evidence_ref 未指向带非空 quote 的 claim；protocol 数值参数未出现在 claims（unbacked_numbers 判 FAIL）；risks 缺判据或止损。
4. 总分复算：fused_score 与 rubric 权重复算不符；ordered_ids 与复算顺序不一致；可复算方案 <2。
5. 敏感性：缺失或 variants 为空；逐变体 winner 与独立复算不符；overall_stable/flip_conditions 与复算不符；overall_stable=false 但 choice_reasons 空。
6. 选择登记：chosen_id ≠ 排序第 1；choice_reasons 空；落选方案缺 rejection_reason；把选中方案登记为放弃。
7. 常开检查：completeness 汇总与实际条目不符、verdict 与进度矛盾、run_status/steps 违规、契约字段缺失、闸门（case_contract / rubric_ledger / skill_scripts / plan_ranking_recompute / sensitivity_recompute）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

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
| 候选方案/价格/排期材料缺失 | material_gaps 登记 + confirmations pending，打分格子留 range 待定，不脑补报价 |
| 约束冲突（预算 vs 载量目标 / 排期窗口） | uncertainties.conflicts 登记双方 + 声明取舍与被舍弃方案的代价 |
| 全部候选方案均不可行 | verdict=partially_selected 或 not_selected，逐方案登记不可行判据，绝不硬选 |
| 大量同分 | score_plan 把并列组记入 ties，按 tie_break 规则破平并在 ranking 可见 |
| 敏感性显示 winner 易翻转 | flip_conditions 落盘 + choice_reasons 写明翻转权重条件，不静默只报 winner |
| 算力/时间不足 | 保留已完成要素，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 7 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅处理输入范围内的方案比较与选择：不做路线原始设计创新、不执行实验、不替代安全与伦理审查。
- 维度打分依赖 scoring_rule 声明的归一口径；组织方未给价格/排期时按 material_gaps 登记，不冒充报价。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；追问轮次按每轮 3 条折算，非实测交互次数；平台白板对照由平台生成。
