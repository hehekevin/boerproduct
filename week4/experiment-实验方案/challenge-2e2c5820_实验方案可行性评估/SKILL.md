---
name: plan-feasibility-check
description: Experiment plan feasibility review skill (focused on resource-and-condition verification). For each candidate plan, verifies the equipment/materials/samples it references against the provided resource inventory, classifying each referenced resource into four states (available / external / to-purchase / unavailable), with a source-based rationale. Produces a per-plan feasibility conclusion (feasible / conditionally_feasible / infeasible) with an explicit condition list. Only resource-condition verification is in scope; time estimation and full ethics-loan review are one-line notes. Use when the task asks to check whether an experiment plan is feasible under concrete resource constraints.
---
## 强制执行协议（最高优先级）
以下 4 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 `/app/output/result.json`。此后任何时刻 result.json 必须存在且 JSON 可解析。
2. **只核验资源条件**：判定是「资源上是否到位」，不评技术路线合理性。方案未写明的资源不默认满足，登记待确认。
3. **失败也交付**：任何中断仍写 result.json（status=partial）。所有脚本退出码恒 0，判据看 verdict。
4. **预算保护**：超 32 次请求或 450 秒停止新增核验，用现有结果定稿。

## 定位与约定
锁定子场景：给定 2 个候选方案 + 设备/材料/样本清单 + 预算/工期约束，完成「逐方案资源四态核验 → 可行性结论 + 条件清单」。只做资源条件核验，不逐条估算时间/人力、不展开伦理审批全流程（各一句话兜底）。材料缺失照实登记，不补造报价。
- 输入：`/input/case.json`（research_objective + constraints + resources{equipment/materials/samples} + plans[] + output_contract）、`task.md`。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 线性 3 步。脚本定位以 skill_marker.json 校验。

## 三步流程

### Step 0 — 落骨架
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 逐方案资源四态核验（核心，1-2 次响应）
对每个 plan，扫它 steps/parameters/reagents 里提到的设备、材料、样本，与 resources 清单比对：
- `status` ∈ `available`（清单有且可用）/ `external`（共享平台需预约）/ `to_purchase`（清单有但缺货需采购）/ `unavailable`（清单无且无替代）
- 每项给 `basis`（引用 resources 里对应条目原文）+ `source_ref`
- 方案引用但清单未提的资源 → 标 `unavailable` 或 `to_confirm`，不默认满足
- 每个 plan 给 `feasibility` ∈ `feasible`/`conditionally_feasible`/`infeasible` + `conditions[]`（可执行的条件清单，如"预约微流控芯片""采购二氯甲烷约5天"）+ 一句话结论依据

### Step 2 — 综合结论 + 自检
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
- `result.conclusion`：哪个方案更可行 + 关键阻塞项；`result.run_status` + `result.verdict` 如实。
- verify_check 判据看 validator_verdict；FAIL 则逐条修复重跑直到 PASS。

## 输出 schema（result.json 顶层 6 契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "research_objective":"…",
    "constraints":{"budget_note":"…","deadline_note":"…"},
    "plan_checks":[{"plan_id":"P1","resource_checks":[{"item":"…","kind":"equipment|material|sample","status":"available|external|to_purchase|unavailable","basis":"…","source_ref":"resources.equipment[0]"}],"feasibility":"conditionally_feasible","conditions":["…"]}],
    "conclusion":{"recommended_plan":"P1","blockers":["…"],"note":"…"},
    "run_status":{"state":"success","reason":null},
    "verdict":"reviewed|partially_reviewed|cannot_verify","verdict_basis":"…"
  },
  "claims":[{"claim_id":"c-01","text":"…","kind":"reported","source_id":"P1","location":"resources.equipment[0]","evidence":[{"quote":"…"}]}],
  "uncertainties":{"summary":"…","human_review":[]},
  "changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. plan_checks 未覆盖全部 plans；resource_checks 空且无 material_gaps 登记。
2. status 枚举非法；每项 basis/source_ref 缺失。
3. feasibility 枚举非法；infeasible/conditionally_feasible 无 conditions 或 blockers。
4. verdict 与核验进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 方案引用资源清单未提 | 标 to_confirm/unavailable，不默认满足 |
| 资源清单为空 | 全部标 to_confirm，verdict=cannot_verify |
| 预算/工期不清 | conditions 里注明"需确认预算/排期"，不脑补 |
| 校验失败 | 退出码恒 0，结论记 verdict |

## 已知限制
- 只核资源条件，不估时间人力、不展开伦理审批；报价/排期为组织方给定清单，不补造。
- examples/ 为合成示意（虚构）非正式答案。