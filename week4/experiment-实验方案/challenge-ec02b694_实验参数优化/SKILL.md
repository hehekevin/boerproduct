---
name: exp-param-optimize
description: Experiment parameter optimization skill (four-aspect coverage / feasible domain / response metric / search strategy / cost-time tradeoff / prose plan embedded). Produces a complete, executable parameter optimization plan: (1) key parameters with feasible domain [lower, upper] + step + basis from equipment manual/material spec/safety threshold; (2) response metric with definition, unit, measurement method and acceptable fluctuation; (3) a search strategy (grid/sequential/Bayesian/staged) with initial points and per-round additions; (4) cost-time budget tradeoff across machine-hours, consumables and throughput. Emits BOTH a structured parameter table AND a full prose plan (plan_report) embedded into result.json. All four aspects are explicitly covered. Use when the task asks for a complete parameter optimization plan under concrete equipment/material/cost constraints.
---

## 强制执行协议（最高优先级，冲突时以本节为准）
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 result.json。此后 result.json 必须存在且可解析。
2. **四方面必覆盖**：关键参数可行域 / 响应指标 / 搜索策略 / 成本时间权衡 四方面都要产出，不得静默跳过。
3. **成文方案必嵌入**：除结构化字段外，必须写 `result.plan_report`（Markdown 全文，≥200 字），把完整可执行方案写成评分者可读的成文。
4. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
5. **预算保护**：模型请求超 40 次或 600 秒即停止，用现有结果写 plan_report 收尾。

## 定位与约定
锁定子场景：给定研究目标 + 材料（设备/规格/安全阈值）+ 前瞻性机时/耗材合同，完成**四方面完整参数优化方案**。逐参数给可行域（上下限+步进+依据+出处）；响应指标给口径/单位/测量/可接受波动；搜索策略给初始点+每轮补点+调整规则；成本权衡给机时/耗材/样品数/通量的取舍。材料缺失、约束冲突照实登记，不补造。
- 输入：`/input/case.json`（research_question + materials + prospective_contracts + output_contract）、`task.md`。以实际文件为准。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 脚本定位以 skill_marker.json 校验。

## 四方面定义（每方面必查）
1. `parameters` 关键参数与可行域：3-6 个关键参数，每个 name/current/range[lower,upper]/unit/basis(manual|spec|literature)/step/source_ref。
2. `response_metric` 响应指标：口径定义 + 单位 + 测量方法 + 可接受波动范围 + 预测方式（历史拟合/代理模型/经验规则）+ 不确定度披露。
3. `search_strategy` 搜索策略：网格/序贯/贝叶斯/分阶段筛选择一 + 初始点怎么选 + 每轮补哪些点 + 如何用上一轮结果调整。
4. `cost_tradeoff` 成本时间权衡：机时/耗材/样品数/通量纳入目标 + 成本受限时牺牲多少响应指标可接受 + 多目标取舍规则。

## 五步流程

### Step 0 — 落骨架（1 次脚本，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 四方面逐项产出（2-4 次响应，广度优先）
- `result.parameters[]`：3-6 个关键参数，每个带 name/current/range/unit/basis/step/source_ref，range 有出处可回查。
- `result.response_metric`：口径+单位+测量+可接受波动+预测方式+不确定度。
- `result.search_strategy`：类型+初始点+每轮补点+调整规则。
- `result.cost_tradeoff`：机时/耗材/样品数/通量 + 成本受限时的取舍规则。
- `result.constraints[]`：耦合约束（温度 vs 材料耐温等），确无也记 none_declared。

### Step 2 — 数值校验（1 次脚本，必做）
```bash
python3 /skills/weekly-skill/scripts/param_check.py --result /app/output/result.json --emit-into
```
核对 current 是否落 range、约束表达式是否成立，越界记 violations，写 result.feasibility_check。

### Step 3 — 写成文方案（1 次响应，必做）
写 `result.plan_report`（≥200 字）：①研究目标 ②关键参数与可行域 ③响应指标 ④搜索策略 ⑤成本权衡 ⑥风险与待确认项。这是评分者直接读的完整方案。

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
    "research_question":{"question":"…","scope":"…","constraints":"…"},
    "parameters":[{"name":"反应温度","current":150,"range":[120,175],"unit":"℃","basis":"spec","step":5,"source_ref":"设备手册 SOP-12 附录A"}],
    "response_metric":{"definition":"包封率","unit":"%","measurement":"HPLC 定量","acceptable_fluctuation":"±5%","prediction":"经验规则+文献","uncertainty":"…"},
    "search_strategy":{"type":"staged_screening","initial_points":"…","per_round_additions":"…","adjustment_rule":"…"},
    "cost_tradeoff":{"machine_hours":"2h/次","consumables":"100元/次","sample_count":"…","throughput":"…","tradeoff_rule":"…"},
    "constraints":[{"cid":"C-01","params":["反应温度"],"expression":"反应温度 <= 175","source":"PEEK 耐温175℃","severity":"hard"}],
    "feasibility_check":{},
    "plan_report":"## 方案\n……（≥200字成文）",
    "risks":[],"confirmations":[],
    "run_status":{"state":"success","reason":null},
    "verdict":"feasible|partially_feasible|infeasible|cannot_verify","verdict_basis":"…"
  },
  "claims":[],"uncertainties":{"summary":"…"},"changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. parameters 数不在 [3,6]；任一参数缺 name/current/range/unit/basis/step 或 current 未落 range。
2. response_metric / search_strategy / cost_tradeoff 任一方面缺失。
3. plan_report 缺失或 <200 字。
4. 约束 params 引用不存在参数；current 数值未在 claims 回证。
5. verdict 与进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 材料/规格缺失 | material_gaps 登记 + confirmations pending，不脑补 |
| 约束冲突（温度 vs 耐温） | violations 如实记 + verdict=infeasible + 转人工 |
| 无可行解 | verdict=infeasible + reason + fallback |
| 校验 FAIL | 修复后重跑；修不了如实登记，绝不中断交付 |

## 已知限制
- 可行域/约束取自输入登记与声明出处；算术校验属前瞻性规划口径，不冒充实测数据。
- 搜索策略与成本权衡是方法学建议，不声称真实实验执行结果。
- examples/ 为合成示意（虚构），非正式答案。