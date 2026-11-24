---
name: plan-feasibility-review
description: Experiment plan feasibility review skill (five-aspect coverage / itemized findings / prose plan embedded). Reviews each candidate plan across five aspects — checklist_system (checkable device/material/time/sample/ethics items), resource_verification (resource vs existing inventory four states), time_sample_estimate (step-wise time and sample feasibility), risk_anomaly (failure modes and fallback), ethics_safety (animal/human/reagent approval path) — and emits BOTH an itemized findings list AND a full prose plan report (plan_report) embedded into result.json. Every aspect is explicitly checked.
---

## 强制执行协议（最高优先级，冲突时以本节为准）
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 result.json。此后 result.json 必须存在且可解析。
2. **五方面必覆盖**：checklist_system / resource_verification / time_sample_estimate / risk_anomaly / ethics_safety 都要逐面查过并记录，不得静默跳过。
3. **成文方案必嵌入**：除 findings 外，必须写 `result.plan_report`（Markdown 全文，≥200 字）。
4. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
5. **预算保护**：模型请求超 40 次或 600 秒即停止，用现有结果写 plan_report 收尾。

## 定位与约定
锁定子场景：给定研究目标 + 约束 + 资源清单 + 候选方案，完成**五方面完整可行性评估**。逐条问题带逐字 quote + 位置 + 严重度 + 修改建议；区分已具备/可外协/需采购/不具备；材料缺失照实登记。
- 输入：`/input/case.json`（research_objective + constraints + resources + plans + output_contract）、`task.md`。以实际文件为准。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 脚本定位以 skill_marker.json 校验。

## 五方面定义（每面必查）
1. `checklist_system` 检查项体系：把设备/材料/时间/样本/伦理/参数/风险拆成可勾选、可判定的检查项。
2. `resource_verification` 资源与条件核验：方案引用的设备/材料/样本与现有条件清单比对，判定已具备/可外协/需采购/不具备。
3. `time_sample_estimate` 时间与样本估算：按步骤拆设备占用/人工/等待周期，核对样本来源、数量、保存条件与审批进度。
4. `risk_anomaly` 风险与异常处置：识别设备故障/材料批次/样本不足/参数越界，给出降级路径与转人工节点。
5. `ethics_safety` 伦理与安全合规：动物/人体/危险试剂/个人数据对应哪级审批、哪些材料、多久。

## 五步流程

### Step 0 — 落骨架（1 次脚本，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 严重度口径声明（1 次响应，判定前必做）
critical=动摇主结论；major=局部问题可修正；minor=表述/建议。写 result.severity_rubric。

### Step 2 — 五方面逐面产出（2-4 次响应，广度优先）
逐面处理，每条问题写 `result.findings[]`：`aspect` ∈ 五面之一 + `quote` 逐字 + `location` + `severity` + `evidence` + `revision_suggestion`。**每面都要产出**：有问题记 finding；没问题的面在 `result.aspect_coverage` 记 `{aspect, status:"checked_no_issue"}`。

### Step 3 — 写成文方案（1 次响应，必做）
写 `result.plan_report`（≥200 字）：①研究目标 ②五方面逐面小结 ③可行性结论 ④待确认项。

### Step 4 — 自检与交付（1 次脚本，必做）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
判据看 validator_verdict；FAIL 则修复→重跑直到 PASS。

## 输出 schema（result.json 顶层契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "severity_rubric":{"levels":{"critical":"…","major":"…","minor":"…"},"declared_at":"step1"},
    "findings":[{"finding_id":"F01","aspect":"resource_verification","category":"insufficient_evidence","severity":"major","quote":"逐字","location":"…","evidence":"…","revision_suggestion":"…","status":"confirmed"}],
    "aspect_coverage":[{"aspect":"resource_verification","status":"checked_findings","count":1}],
    "plan_report":"## 总体结论\n……（≥200字）",
    "run_status":{"state":"success","reason":null},
    "verdict":"feasible|partially_feasible|infeasible|cannot_verify","verdict_basis":"…"
  },
  "claims":[],"uncertainties":{"summary":"…"},"changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. 五方面有任一面在 aspect_coverage 缺失。
2. findings 里 aspect/category/severity 枚举非法；confirmed 缺 quote/location。
3. plan_report 缺失或 <200 字。
4. severity_rubric 未声明；suggestion≠minor；fact_error 标 minor。
5. verdict 与进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 某方面材料缺失 | 该面记 checked_no_issue + 注明"材料缺失无法核验"，不编造 |
| 约束冲突 | 如实记 + verdict=infeasible + 转人工 |
| 无可行解 | verdict=infeasible + reason + fallback |
| 校验 FAIL | 修复后重跑；修不了如实登记，绝不中断交付 |

## 已知限制
- 只审资源/时间/样本/风险/伦理条件，不执行实验；报价为给定清单，不补造。
- examples/ 为合成示意（虚构），非正式答案。
