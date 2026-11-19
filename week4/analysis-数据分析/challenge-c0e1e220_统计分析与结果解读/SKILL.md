---
name: stat-analysis-audit
description: Statistical analysis and result interpretation audit skill (descriptive recompute / test-choice registration / effect-CI reporting check / strength grading / causal-word constraint). For each given dataset-analysis it audits six facets (data_quality / descriptive / test_choice / effect_ci / interpretation / causal_claim), re-computes every claimed statistic (n, mean, variance, stdev, quantiles, stdlib statistics/math only) from the raw values in case.json and back-checks every reported number against the claims chain, verifies the registered test (parametric/nonparametric, t/ANOVA/Mann-Whitney/Kruskal-Wallis/Welch/paired/correlation) against declared assumptions, mechanically derives claim_strength from design_type via a declared strength_map and downgrades overclaims (significant ≠ proven), forbids causal wording in observational designs (correlation ≠ causation, explicit verb list, no isalpha on CJK), separates method_error from reporting_gap, and registers abstentions (unassessable) with pending_review. Verify_check re-checks all seven groups; gain_probe runs normal-vs-degraded ablation with pollution injection to embed measured gain_evidence and efficiency into result.json. Use when the task asks to audit statistical analysis and result interpretation with recomputable numbers and strength-matched conclusions.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 analyses / claim_rules / stat_recompute / interpret_summary / coverage / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **六分面逐条全覆盖**：每组分析的 appraisals 必须覆盖清单声明的**全部 domain**（data_quality / descriptive / test_choice / effect_ci / interpretation / causal_claim，缺面=FAIL）；每条 judged=true，或 unassessable 写 abstain_reason、not_applicable 写 na_reason。
4. **数字必须回证**：claimed 统计量（n/mean/sd/分位数/p 值等）必须能在 claims 证据链与来源文本中找到出处；evidence_quote 逐字摘自 case.json 并附位置（dataset_id#章节）；数据缺失就复算 unavailable 如实登记，**绝不臆造数字、绝不把缺失当 0**。
5. **口径事前声明**：claim_rules（grade_map / category_map / penalty_map / thresholds / strength_map / causal_verbs / abstain_rule / direction_rule）必须在**任何复算与分级之前**声明（declared_at 落 /app/work/claim_rules.json 台账），之后禁止调整。
6. **键归属纪律（多脚本禁写同一键）**：stat_recompute 只归 stat_recompute.py；interpret_summary 只归 interpret_rollup.py；self_check / gates / unbacked_numbers / unbacked_evidence / validator_verdict 只归 verify_check.py；gain_evidence / efficiency 只归 gain_probe.py；其余归 build_skeleton + Agent。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：对给定科研数据与统计报告做**六分面审计**——缺失/重复/异常口径（data_quality）、描述统计复算（descriptive）、检验选择依据（test_choice）、效应量与置信区间（effect_ci）、解读强度分级（interpretation）、因果表述约束（causal_claim）。统计复算只用标准库 statistics/math（样本方差 n-1 口径、分位数线性插值），检验期望按组数/配对/正态性/方差齐性/设计类型机械推导。不做实验设计、不做样本量估算、不写论文；原始数据不可得时如实登记，弃权不罚分。
关键词：算得准（claimed 逐个回原始数据复算）· 选得对（检验与分布/设计匹配）· 强度稳（结论强度由设计机械导出、过强降级）· 分得清（方法误用≠没写）· 敢弃权（口径不明标 unassessable 并登记人工复核）。
- 输入：`/input/case.json`（数据集/记录 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖（不装 numpy/scipy）。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与数据集清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（datasets/records/data/tables 等）提取数据集清单预填 `result.analyses[]`；预填六分面清单与 claim_rules 模板；生成 /app/work/claim_rules.json 台账。
- 脚本失败时手工兜底：读 case.json 抄数据集清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 审计范围与口径声明（1 次响应，复算前完成）
- 填 `result.review_scope`（question / dataset_refs / unit_policy）。
- **事前声明 claim_rules**：strength_map（design_type→允许最高强度 experimental→causal、observational/correlational→associative、unknown→descriptive）、causal_verbs（因果动词词表）、grade_map / category_map / penalty_map / thresholds / abstain_rule / direction_rule，declared_at 必填并同步 /app/work/claim_rules.json。**声明后禁止调整。**

### Step 2 — 逐分面评价与登记（1-3 次响应，广度优先）
对每组分析的**每条清单条目**，缺一不可：
- `judgment` ∈ supported / concerns / inadequate / unreported / not_applicable / unassessable；`grade` 与 `category` 必须等于 claim_rules 映射导出值（inadequate⇒method_error 方法误用、unreported⇒reporting_gap 报告不全——两者不得互换）；
- 数据质量：缺失/重复/异常各自的处理口径（删了多少、怎么判）写进 `data_quality`，绝不把缺失当 0 或静默删行；
- 描述统计：claimed 值写进 `descriptive`（n_claimed/mean_claimed/sd_claimed/quantiles_claimed，含单位）；
- 检验登记：`test_registration` 登记家族（parametric/nonparametric）、名称、n_groups、paired、正态性/方差齐性假设与选择理由；
- 解读登记：`claim.text` + `claim_strength` ∈ causal/associative/descriptive/insufficient，**不得超过 strength_map[design_type]**（过强结论降级）；
- 负面判定（concerns/inadequate/unreported）必填 `bias_direction`；每条 `rationale` 一句话；evidence_quote 逐字摘自来源文本（unassessable 允许为空但须说明检索过程）。

### Step 3 — 统计量复算与检验期望（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/stat_recompute.py --result /app/output/result.json \
  --case /input/case.json
```
- 从原始数据复算 n/mean/variance/stdev/分位数，与 claimed 对照（相对容差 1e-6）；缺失/非数值跳过并计数，绝不按 0 计入；按假设推期望检验族与名称，与登记对照。写入 `result.stat_recompute`（仅此键）。
- 原始数据不可得 ⇒ 该组记 unavailable，如实登记 material_gaps，不臆造。脚本失败时手工按同一公式手算并在 steps 注明，事后重跑核对。

### Step 4 — 解读强度机械汇总与证据链（1 次响应 + 1 次脚本调用）
```bash
python3 /skills/weekly-skill/scripts/interpret_rollup.py --result /app/output/result.json
```
- 机械复算每组 strength_allowed / overclaim / causal_verbs_found / causal_ok / penalty_total / overall / direction，写入 `result.interpret_summary`（仅此键）。p=0.04 不得写成"证明有效"——统计显著≠证明有效，无效应量时结论强度必须降级。
- **claims 证据链**：每组分析至少一条 `{claim_id, text, kind, source_id=analysis_id, location, evidence:[{paragraph_id, quote}]}`；text 含 claimed 关键数字 + 强度结论；所有引文逐字进入 evidence，数字未回证列入 unbacked_numbers 判 FAIL。
- `result.pending_review[]`：每个 unassessable 登记 `{analysis_id, checklist_id, reason, needed_action}`。
- `result.verdict`（verdict_basis 一句话）：`audited` 全部逐条判定；`partially_audited` 部分；`not_audited` 未产生判定；`cannot_verify` 材料缺口且 material_gaps 非空。`run_status.state` ∈ success|partial|unable_to_determine|refused，非 success 必须写 reason。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（七组机械校验全开）与退化模式（--ablate all：关闭覆盖/分级/证据/缺陷/复算/因果/弃权），把**真实数字**写进 `result.gain_evidence`。
- `--inject-pollution` 在**副本**上注入 9 类污染（统计量篡改 / 结论强度夸大 / 编造引文 / 缺陷混淆 / 删条目 / 因果越界表述 / 解读汇总篡改 / 清空弃权 / 清空证据链）：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 同时写 `result.efficiency`（墙钟、字节、检查项数 + reproduce 命令）；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。跑不了时手工写 `gain_evidence={available:false, reason:…}`，不得编数字。**退化模式结果仅用于增益对照，不得当作交付自检结论。**

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每个 claimed 数字都能回到原始数据与来源文本吗？检验选择与解读强度都有事前口径依据吗？弃权与因果越界都如实登记了吗？

## 输出 schema（result.json — 平台通用契约 + 本题业务键）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": null, "packages": "stdlib-only", "seed": null, "hardware_note": null},
    "review_scope": {"question": null, "dataset_refs": null, "unit_policy": null, "checklist_version": null},
    "checklist": {"version": "…", "domains": ["data_quality","descriptive","test_choice","effect_ci","interpretation","causal_claim"], "items": [{"checklist_id": "DQ-01", "domain": "data_quality", "prompt": "…", "evidence_required": true}]},
    "claim_rules": {"version": "…", "declared_at": "…", "grade_map": {"supported": "high", "concerns": "medium", "inadequate": "low", "unreported": "uncertain", "unassessable": "uncertain", "not_applicable": null}, "category_map": {"inadequate": "method_error", "unreported": "reporting_gap", "concerns": "interpretation_risk", "…": "…"}, "penalty_map": {}, "thresholds": {"low": [0,1], "some_concerns": [2,4], "high": [5,9999]}, "strength_map": {"experimental": "causal", "observational": "associative", "…": "…"}, "causal_verbs": ["导致","证明","因果","…"], "abstain_rule": "…", "direction_rule": "…"},
    "analyses": [{"analysis_id": "A01", "dataset_id": "ds-exp-01", "title": "…", "design_type": "experimental", "source_ref": "datasets[0]", "data_quality": {}, "descriptive": {"variable": "yield", "unit": "kg/plot", "n_claimed": 12, "mean_claimed": 53.65833333333333, "sd_claimed": 4.740053381619881, "quantiles_claimed": {"p25": 50.25}}, "test_registration": {"test_id": "T01", "test_family": "parametric", "test_name": "welch t-test", "n_groups": 2, "paired": false, "assumptions": {"normality": "yes", "variance_equality": "no"}, "reason": "…"}, "claim": {"claim_id": "c-A01", "text": "…", "evidence_level": "…", "claim_strength": "causal"}, "appraisals": [{"checklist_id": "DQ-01", "domain": "data_quality", "judgment": "supported", "grade": "high", "category": "none", "bias_direction": "none", "evidence_quote": "逐字摘录", "evidence_location": "ds-exp-01#description", "rationale": "…", "judged": true, "abstain_reason": null, "na_reason": null}], "judged": true}],
    "stat_recompute": {"computed_by": "scripts/stat_recompute.py", "tolerance": 1e-06, "per_dataset": [{"analysis_id": "A01", "status": "ok", "recomputed": {}, "diffs": {}, "match": true, "test_check": {}, "missing_skipped": 0}], "all_match": true},
    "interpret_summary": {"computed_by": "scripts/interpret_rollup.py", "per_analysis": [{"analysis_id": "A01", "strength_allowed": "causal", "strength_claimed": "causal", "overclaim": false, "causal_verbs_found": [], "causal_ok": true, "penalty_total": 2, "overall": "medium", "direction": "favors_conclusion"}], "totals": {}},
    "coverage": {"datasets_total": 2, "domains_required": 6, "items_total": 12, "judged_items": 12, "abstained": 1, "method_errors": 0, "reporting_gaps": 2, "interpretation_risks": 1, "not_applicable": 0, "ratio": 1.0},
    "conflicts": [], "pending_review": [{"analysis_id": "A02", "checklist_id": "DQ-01", "reason": "…", "needed_action": "…"}],
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "audited | partially_audited | not_audited | cannot_verify", "verdict_basis": "一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "均值 53.66、p=0.04 …", "kind": "inferred", "source_id": "A01", "location": "analyses[0]", "evidence": [{"paragraph_id": "ds-exp-01#methods", "quote": "原文原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "unbacked_evidence": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | invalid", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py，问题串带组标签）
1. [enum] judgment/grade/category/bias_direction/design_type/claim_strength/run_status.state 枚举非法。
2. [coverage] 六分面漏覆盖；judged=true 但缺完成要素（judgment 非法、弃权/不适用无说明）。
3. [grading] grade 与 grade_map 不符；claim_strength 超过 strength_map[design_type]（过强结论不降级）；负面判定缺 bias_direction；penalty/overall/overclaim 复算与 interpret_summary 不符。
4. [evidence] supported/concerns/inadequate 缺 evidence_quote；引文无逐字回证或来源文本不存在；rationale 为空；claimed 数字未回证 → unbacked_numbers 判 FAIL。
5. [defect] category 与 category_map 不符；inadequate 归 reporting_gap 或 unreported 归 method_error（方法误用≠报告不全）。
6. [recompute] claimed 与 stat_recompute 复算不符（容差 1e-6）；stat_recompute 跑后 claimed 被改动（现场比对）；检验选择与假设失配。
7. [causal] 观察性/相关性设计 + 因果动词命中（相关≠因果）；与 interpret_summary.causal_ok 交叉核对。
8. [pending] unassessable 未登记 pending_review。另 [structure]/[contract]：steps 为空、coverage 汇总不符、verdict 与进度矛盾、缺 output_contract 字段；闸门非 enforced 时 warn——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，数据与引文均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/stat_recompute.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/interpret_rollup.py --result examples/example-result.json --rules /tmp/wk/claim_rules.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --rubric /tmp/wk/claim_rules.json --out /tmp/vc.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/sg.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 原始数据不可得 / 字段非数值 | stat_recompute 记 unavailable + material_gaps 登记，绝不臆造复算值 |
| 缺失/异常/重复口径不明 | judgment=unassessable + abstain_reason + 登记 pending_review，弃权不罚分 |
| 单位/口径不明（μg 还是 mg） | review_scope.unit_policy 写明不换算，unreported 登记并提示追问 |
| 正态性/方差齐性未检验 | test_choice 按 unreported 处理；期望检验按保守假设推导 |
| claim 含因果动词且为观察性设计 | causal 判 FAIL，结论强度降级到 associative 并登记 |
| 统计量与复算不符 | 以复算为准修复 claimed，不改数据凑结论；修不了如实登记 uncertainties |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- strength_map 与因果动词词表是本技能事前声明并机械执行的保守设定（题面未给定时按保守量级），不冒充 APA/CONSORT 等外部标准；子串匹配可能误报否定句式（"未导致"），命中时人工复核后如实登记。
- 复算口径固定为样本方差（n-1）与线性插值分位数；claimed 若为总体方差（n）口径会在 diffs 中显示，需按口径人工核对。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量；原始计数一并落盘。
