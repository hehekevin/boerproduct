---
name: exp-result-explain
description: Experimental result interpretation and anomaly analysis skill (trend reading / anomaly localization / evidence-ranked cause candidates / executable recheck steps / follow-up experiment suggestions). For each given result dataset it reads trend direction, inflection and plateau mechanically from raw readings (least-squares slope, z-score outliers, jump and plateau detection with declared thresholds, stdlib only), binds every anomaly to a concrete object (sample/batch/channel/well/time point) with threshold and deviation magnitude, builds cause-candidate lists ranked by evidence strength across instrument/operation/sample/environment categories each with supporting and excluding evidence plus a correlation-vs-causation note, registers recheck steps only when executable by a second person (target file + field + method + expected outcome, rejects vague wording like check-data-quality), maps results to hypothesis alignment with a mechanical consistency rule (supported/partially_supported/not_supported/unassessable) and downgrades over-aligned conclusions, and gives follow-up experiment changes tied to cause gaps. Explain_rollup mechanically checks anomaly-cause pairing, evidence back-binding and recheck executability; verify_check re-checks all groups reporting verdict-only (exit code always 0); gain_probe runs normal-vs-degraded ablation with pollution injection to embed measured gain_evidence and efficiency into result.json. Use when the task asks to interpret experimental results into trends, anomalies, causes, rechecks and next-round suggestions with evidence-bound conclusions.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 analyses / judge_rules / trend_anomaly_check / explain_summary / coverage / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **五分面逐条全覆盖**：每组分析的 appraisals 必须覆盖清单声明的**全部 domain**（trend / anomaly / cause / recheck / followup，缺面=FAIL）；每条 judged=true，或 unassessable 写 abstain_reason、not_applicable 写 na_reason。
4. **解释必须回证**：趋势、异常、原因、复核、对齐每条结论必须附 evidence_quote（逐字摘自 case.json 原文）+ evidence_location（series#位置 或 dataset_id#字段）；异常必须绑定具体对象（样本/批次/通道/孔位/时间点 + 索引/编号）；数据缺失就如实登记 unavailable，**绝不臆造数字、绝不把相关当因果**。
5. **口径事前声明**：judge_rules（alignment_rule / detection_thresholds / cause_categories / cause_rank_map / pairing_rule / evidence_rule / executable_rule / grade_map / category_map / penalty_map / grade_bands / speculation_verbs / abstain_rule / direction_rule）必须在**任何判读与分级之前**声明（declared_at 落 /app/work/judge_rules.json 台账），之后禁止调整。
6. **键归属纪律（多脚本禁写同一键）**：trend_anomaly_check 只归 trend_anomaly_check.py；explain_summary 只归 explain_rollup.py；self_check / gates / unbacked_numbers / unbacked_evidence / validator_verdict 只归 verify_check.py；gain_evidence / efficiency 只归 gain_probe.py；其余归 build_skeleton + Agent。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：对给定实验读数做**五段解释**——结果趋势（方向/拐点/平台期/幅度）、异常点（离群/跳变/平台期异常，定位到对象并给阈值与偏离幅度）、可能原因（instrument/operation/sample/environment 四类，按证据强度排序，区分相关与因果）、复核步骤（第二个人可执行的核查动作）、后续实验建议（针对原因候选与证据缺口）。判读只用标准库 statistics/math（最小二乘斜率、z 分数离群、相对跳变、连续平台段），阈值一律取自事前声明的 detection_thresholds。不做实验方案设计本身、不做样本量估算、不写论文；原始读数不可得时如实登记，弃权不罚分。
关键词：趋势读得准（斜率/拐点回原始读数）· 异常找得对（定位到对象+阈值+偏离幅度）· 原因排得出（支持证据+排除证据+相关≠因果）· 复核跑得动（文件/字段/方法/预期结果四要素）· 敢弃权（口径不明标 unassessable 并登记人工复核）。
- 输入：`/input/case.json`（数据集/读数序列 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖（不装 numpy/scipy）。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与序列清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（datasets/series/traces/records/results 等）提取读数序列清单预填 `result.analyses[]`；预填五分面清单与 judge_rules 模板；生成 /app/work/judge_rules.json 台账。
- 脚本失败时手工兜底：读 case.json 抄序列清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 解释范围与口径声明（1 次响应，判读前完成）
- 填 `result.analysis_scope`（question / hypothesis_refs / series_refs / unit_policy）。
- **事前声明 judge_rules**：detection_thresholds（outlier_z=3.0 / jump_rel=0.5 / plateau_min_points=3 / plateau_tol_rel=0.05）、alignment_rule、cause_categories 与 cause_rank_map、pairing_rule、evidence_rule、executable_rule、speculation_verbs、grade_map / category_map / penalty_map / grade_bands / abstain_rule / direction_rule，declared_at 必填并同步 /app/work/judge_rules.json。**声明后禁止调整。**

### Step 2 — 五段逐条解释与登记（1-3 次响应，广度优先）
对每组序列的**每条清单条目**，缺一不可：
- `judgment` ∈ supported / concerns / inadequate / unreported / not_applicable / unassessable；`grade` 与 `category` 必须等于 judge_rules 映射导出值（inadequate⇒method_error 方法误用、unreported⇒reporting_gap 报告不全——两者不得互换）；
- 趋势段：`trend` 填 direction / inflection_points / plateau / magnitude，写明区间、对照与方法；
- 异常段：`anomalies[]` 每条填 anomaly_id / dimension / object_ref / anomaly_type(outlier|jump|plateau) / severity / threshold_used / deviation_from_control / evidence_location；
- 原因段：`causes[]` 每条填 cause_id / anomaly_id / category(instrument|operation|sample|environment|unknown) / hypothesis / supporting_evidence / excluding_evidence / rank / correlation_note，按证据强度排序，**相关≠因果必须写明**；
- 复核段：`rechecks[]` 每条填 recheck_id / anomaly_id / action / target_file / target_field / method / expected_outcome / executable——四要素缺一即不可执行；
- 对齐判定：`alignment` 填 verdict ∈ supported / partially_supported / not_supported / unassessable + basis + hypothesis_ref + evidence_quote；**不得把 partially_supported 写成 supported**；
- 负面判定（concerns/inadequate/unreported）必填 `bias_direction`；每条 `rationale` 一句话。

### Step 3 — 趋势与异常机械复算（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/trend_anomaly_check.py --result /app/output/result.json \
  --case /input/case.json
```
- 从原始读数复算 n/mean/sd/最小二乘斜率/方向、z 分数离群、相对跳变、连续平台段，与 claimed 的 trend 方向和 anomalies 清单对照；缺失/非数值跳过并计数，绝不按 0 计入。写入 `result.trend_anomaly_check`（仅此键）。
- 原始读数不可得 ⇒ 该组记 unavailable，如实登记 material_gaps，不臆造。脚本失败时手工按同一公式复算并在 steps 注明，事后重跑核对。

### Step 4 — 配对/回证/可执行性机械汇总（1 次响应 + 1 次脚本调用）
```bash
python3 /skills/weekly-skill/scripts/explain_rollup.py --result /app/output/result.json
```
- 机械复算每组 pairing（异常-原因配对完备性）/ unbound_explanations（无证据解释）/ executable_rechecks / alignment_consistency / speculation_only / penalty_total / overall / direction，写入 `result.explain_summary`（仅此键）。无证据的原因猜测（仅 speculation_verbs 命中）必须降级并登记。
- **claims 证据链**：每组分析至少一条 `{claim_id, text, kind, source_id, location, evidence:[{paragraph_id, quote}]}`；数字未回证列入 unbacked_numbers 判 FAIL。
- `result.pending_review[]`：每个 unassessable 登记 `{analysis_id, checklist_id, reason, needed_action}`。
- `result.verdict`（verdict_basis 一句话）：`audited` 全部逐条判定；`partially_audited` 部分；`not_audited` 未产生判定；`cannot_verify` 材料缺口且 material_gaps 非空。`run_status.state` ∈ success|partial|unable_to_determine|refused，非 success 必须写 reason。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（对齐一致性/配对/回证/可执行复核四组校验全开）与退化模式（--ablate all：四组全关），把**真实数字**写进 `result.gain_evidence`。
- `--inject-pollution` 在**副本**上注入 9 类污染（异常删原因 / 解释删证据 / 对齐越级判 supported / 复核改空话 / claim 篡改数字 / 原因类别非法 / 清空 pending_review / 异常删对象绑定 / 编造引文）：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 同时写 `result.efficiency`（墙钟、字节、检查项数 + reproduce 命令）；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。跑不了时手工写 `gain_evidence={available:false, reason:…}`，不得编数字。**退化模式结果仅用于增益对照，不得当作交付自检结论。**

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --rules /app/work/judge_rules.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每条解释都能回到原始读数与来源文本吗？异常-原因配对与对齐判定都符合同一口径吗？复核步骤第二个人能照着跑吗？

## 输出 schema（result.json — 平台通用契约 + 本题业务键）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": null, "packages": "stdlib-only", "seed": null, "hardware_note": null},
    "analysis_scope": {"question": null, "hypothesis_refs": null, "series_refs": null, "unit_policy": null, "checklist_version": null},
    "checklist": {"version": "…", "domains": ["trend","anomaly","cause","recheck","followup"], "items": [{"checklist_id": "TR-01", "domain": "trend", "prompt": "…", "evidence_required": true}]},
    "judge_rules": {"version": "…", "declared_at": "…", "alignment_verdicts": ["supported","partially_supported","not_supported","unassessable"], "alignment_rule": "…", "detection_thresholds": {"outlier_z": 3.0, "jump_rel": 0.5, "plateau_min_points": 3, "plateau_tol_rel": 0.05}, "anomaly_types": ["outlier","jump","plateau"], "cause_categories": ["instrument","operation","sample","environment","unknown"], "cause_rank_map": {}, "grade_map": {}, "category_map": {}, "penalty_map": {}, "grade_bands": {"low": [0,1], "some_concerns": [2,4], "high": [5,9999]}, "speculation_verbs": ["可能是","推测","疑为"], "pairing_rule": "…", "evidence_rule": "…", "executable_rule": "…", "abstain_rule": "…", "direction_rule": "…"},
    "analyses": [{"analysis_id": "A01", "dataset_id": "ds-01", "title": "…", "design_type": "experimental", "source_ref": "datasets[0]", "hypothesis_ref": "H1", "trend": {"direction": "flat", "inflection_points": [], "plateau": null, "magnitude": "…", "method": "…", "evidence_quote": "…", "evidence_location": "…"}, "anomalies": [{"anomaly_id": "AN-01", "dimension": "时间点", "object_ref": "values[5]", "anomaly_type": "outlier", "severity": "z=3.16", "threshold_used": "outlier_z=3.0", "deviation_from_control": "…", "evidence_quote": "…", "evidence_location": "…"}], "causes": [{"cause_id": "C-01", "anomaly_id": "AN-01", "category": "instrument", "hypothesis": "…", "supporting_evidence": ["…"], "excluding_evidence": ["…"], "rank": 1, "correlation_note": "…"}], "rechecks": [{"recheck_id": "RC-01", "anomaly_id": "AN-01", "action": "…", "target_file": "…", "target_field": "…", "method": "…", "expected_outcome": "…", "executable": true}], "followups": [{"followup_id": "FU-01", "based_on_cause_ids": ["C-01"], "change": "…", "rationale": "…", "evidence_quote": "…", "evidence_location": "…"}], "alignment": {"verdict": "supported", "basis": "…", "hypothesis_ref": "H1", "evidence_quote": "…", "evidence_location": "…"}, "appraisals": [{"checklist_id": "TR-01", "domain": "trend", "judgment": "supported", "grade": "high", "category": "none", "bias_direction": "none", "evidence_quote": "逐字摘录", "evidence_location": "ds-01#description", "rationale": "…", "judged": true, "abstain_reason": null, "na_reason": null}], "judged": true}],
    "trend_anomaly_check": {"computed_by": "scripts/trend_anomaly_check.py", "thresholds_used": {}, "per_dataset": [{"analysis_id": "A01", "status": "ok", "recomputed": {}, "claimed": {}, "diffs": {}, "match": true, "missing_skipped": 0}], "all_match": true},
    "explain_summary": {"computed_by": "scripts/explain_rollup.py", "per_analysis": [{"analysis_id": "A01", "pairing_complete": true, "unbound_explanations": 0, "executable_rechecks": 1, "alignment_consistent": true, "speculation_only": 0, "penalty_total": 0, "overall": "high", "direction": "favors_conclusion"}], "totals": {}},
    "coverage": {"datasets_total": 2, "domains_required": 5, "items_total": 10, "judged_items": 10, "abstained": 0, "method_errors": 0, "reporting_gaps": 0, "interpretation_risks": 0, "not_applicable": 0, "ratio": 1.0},
    "conflicts": [], "pending_review": [],
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "audited | partially_audited | not_audited | cannot_verify", "verdict_basis": "一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "…", "kind": "inferred", "source_id": "A01", "location": "analyses[0]", "evidence": [{"paragraph_id": "ds-01#description", "quote": "原文原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "unbacked_evidence": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | invalid", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py，问题串带组标签）
1. [enum] alignment.verdict / anomaly_type / cause.category / judgment / grade / category / bias_direction / run_status.state 枚举非法。
2. [coverage] 五分面漏覆盖；judged=true 但缺完成要素（judgment 非法、弃权/不适用无说明）。
3. [alignment] 对齐口径一致：verdict 缺 basis/evidence_quote；supported 但存在 inadequate/unreported/unassessable 条目（口径矛盾）；unassessable 未登记 pending_review。
4. [pairing] anomaly 无 ≥1 条绑定 cause；cause 回指不存在的 anomaly_id；与 explain_summary 交叉核对。
5. [evidence] trend/anomalies/causes/rechecks/followups/alignment 缺 evidence_quote 或 location；引文无逐字回证或来源文本不存在；claims 数字未回证 → unbacked_numbers 判 FAIL。
6. [recheck] executable=true 但四要素（action/target_file/target_field或method/expected_outcome）缺一；"检查数据质量"类空话判不可执行。
7. [anomaly_check] 复算的 trend 方向 / 离群 / 跳变 / 平台与 claimed 不符（阈值取 detection_thresholds）。
8. [structure]/[contract]：steps 为空、coverage 汇总不符、verdict 与进度矛盾、缺 output_contract 字段；闸门非 enforced 时 warn——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，数据与引文均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/trend_anomaly_check.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/explain_rollup.py --result examples/example-result.json --rules /tmp/wk/judge_rules.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --rules /tmp/wk/judge_rules.json --out /tmp/vc.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/sg.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 原始读数不可得 / 字段非数值 | trend_anomaly_check 记 unavailable + material_gaps 登记，绝不臆造复算值 |
| 读数超量程/饱和、单位不一致 | judgment=unassessable + abstain_reason + 登记 pending_review，弃权不罚分 |
| 对照缺失 / 重复数不足 | anomaly.deviation_from_control 写明"无对照可比"，登记 uncertainties，不编偏离幅度 |
| 原因只有机理猜测无数据证据 | explain_summary.speculation_only 计数，rank 降为 weak，不得写成因果结论 |
| 复核写成"检查数据质量"类空话 | recheck.executable=false 并重写为四要素齐备的动作 |
| 复算与 claimed 不符 | 以复算为准修复 claimed，不改数据凑结论；修不了如实登记 uncertainties |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- detection_thresholds（outlier_z=3.0 / jump_rel=0.5 / plateau_tol_rel=0.05）是本技能事前声明并机械执行的保守默认（题面未给定时按保守量级），不冒充 Grubbs/ISO 等外部标准；z 分数对小样本偏保守，可能漏报边缘离群，命中争议时登记 pending_review。
- 方向判定按 |slope×span/mean|<0.05 记 flat，属声明口径而非拟合检验；平台期检测用连续相对容差法，非变点检验。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
