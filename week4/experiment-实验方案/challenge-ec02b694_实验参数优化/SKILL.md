---
name: exp-param-domain
description: Key-parameter feasible-domain advisory skill for experiment parameter optimization (identify 3-6 key parameters / extract per-parameter lower-upper bound, step and basis from equipment manual / material spec / safety threshold / literature / verify current values fall inside declared feasible ranges / register coupling constraints with safe arithmetic evaluation). Turns a research goal into a checkable feasible-domain table: each key parameter declares name + current value + unit + feasible range [lower, upper] + basis (manual|spec|literature) + step suggestion, plus coupling constraints (evaluated by a restricted-AST arithmetic checker) and an honest verdict on whether the current plan is executable. Use when the task asks for parameter optimization advice: which parameters matter, what range each may float in, what bounds the equipment/material/safety impose, and whether suggested values stay within those bounds.
---

## 强制执行协议（最高优先级）
以下 7 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析。
2. **字段一个不缺**：result.json 必须含 output_contract 全部字段 + 本文 schema 全部键（parameters / constraints / feasibility_check / risks / confirmations / completeness / run_status / gain_evidence）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **只做可行域约束一个方向**：只抽 3–6 个关键参数，每个给 name + current + range[下限,上限] + unit + basis（manual|spec|literature）+ step；不追求穷尽，不做响应指标代理建模/搜索策略/成本权衡/风险深化，那些只在异常时一句兜底。参数规模封顶 6。
4. **不编造**：range 上下限与 basis 必须能从输入材料/规格/安全阈值/文献逐字回查到出处；材料缺失就登记 material_gaps，不脑补规格。
5. **数值可回证**：每个 current 数字必须出现在 claims 证据链中（空白归一化后子串匹配），未回证数字列入 unbacked_numbers 判 FAIL。
6. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑。
7. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定研究目标、约束与科研材料（含组织方前瞻性资源/价格/预约合同、有限参数域），完成**关键参数识别与可行域约束**——从设备手册、材料规格、安全阈值与历史实验中抽出每个关键参数的上下限、步进与互斥关系，形成可被判定的可行域。响应指标代理建模、搜索策略、成本权衡、风险深化不在本题主线范围；材料缺失、约束冲突、依赖不可用照实登记，不补造规格或报价。所有算术校验基于登记的声明域/当前值，属前瞻性规划口径。
- 输入：`/input/case.json`（研究目标 + 约束 + 材料 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒；只用标准库，不装 pip 依赖。
- 按 Step 0–4 线性推进。脚本定位以 `/app/work/skill_marker.json` 标志文件为准（Step 0 落盘）。

## 五步流程

### Step 0 — 自动落骨架（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动提取 output_contract 字段名与研究目标/材料/约束 → 写骨架；落 skill_marker.json。
- 脚本失败时手工兜底：抄目标与字段名，手写骨架（键一个不缺）。

### Step 1 — 关键参数识别与可行域（1–2 次响应）
- `result.parameters[]`：**只抽 3–6 个关键参数**（对研究目标影响最大且材料/规格/安全阈值能给出上下限的参数）。每个给 `name`（参数名，可中文）+ `current`（当前值，数值）+ `range`（[下限,上限] 数值对）+ `unit` + `basis`（manual|spec|literature，设备手册=spec、材料规格=spec、安全阈值=spec、历史实验=literature/modification记录=manual）+ `step`（步进建议，可为 null）。
- 每个 range 的来源逐字写进 `source_ref`（如「设备手册 SOP-12 附录A」），保证可复核。

### Step 2 — 耦合约束登记（1 次响应）
- `result.constraints[]`：耦合约束（如目标温度与材料耐温的互斥、机时/耗材联合上限）。每条给 `cid` + `params`（引用存在的参数 name）+ `expression`（算术表达式，如 `反应温度 <= 175` 或 `P-01 * P-02 <= 2500`）+ `source` + `severity`（hard|soft）。**确无耦合也须登记一条 `kind=none_declared` + source**，不脑补约束。

### Step 3 — 数值校验（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/param_check.py --result /app/output/result.json --emit-into
```
- 受限 AST 求值器（白名单四则/比较/and-or，函数调用与属性访问拒绝）核对：current 是否落 range、每条约束表达式在当前值映射下是否成立；越界/不成立/不可求值记 violations——**建议值越界却不提示正是本题主抓的失败模式**。
- 写 `result.feasibility_check`。脚本失败时手工兜底，事后重跑核对。

### Step 4 — 自检与交付（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
- 判据是报告 `verdict`：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json → 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：关键参数 3–6 个且每个都有 name/current/range/unit/basis/step 吗？每个 range 都有可查出处、每个 current 都落在 range 内吗？约束都能被 param_check 真实算术求值吗？

## 输出 schema（result.json — 平台通用契约五字段 + 业务键）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": "…", "packages": "stdlib-only", "hardware_note": "照实"},
    "research_question": {"question": "…", "scope": "…", "constraints": "…"},
    "parameters": [
      {"name": "反应温度", "current": 150, "range": [120, 175], "unit": "℃",
       "basis": "spec", "source_ref": "设备手册 SOP-12 附录A", "step": 5}
    ],
    "constraints": [
      {"cid": "C-01", "params": ["反应温度"], "expression": "反应温度 <= 175",
       "source": "PEEK 密封件耐温 175℃（材料规格）", "severity": "hard"}
    ],
    "feasibility_check": {"tool": "scripts/param_check.py", "parameters_checked": 4, "constraints_declared": 1,
      "all_within_domain": true, "all_constraints_satisfied": true, "violations": [], "warnings": [],
      "verdict": "PASS", "summary": "…"},
    "risks": [{"risk_id": "R-01", "failure_mode": "约束冲突或无可行解", "judge_criterion": "…", "stop_loss": "…", "fallback": "转人工"}],
    "confirmations": [{"item": "…", "kind": "safety | equipment | expert", "status": "pending | confirmed"}],
    "completeness": {"parameters_total": 4, "constraints_total": 1},
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "feasible | partially_feasible | infeasible | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"available": false, "reason": "精简策略：预算保护降级，跳过正常/退化双重增益对照"}
  },
  "claims": [{"claim_id": "c-01", "text": "参数+当前值+依据", "kind": "reported", "source_id": "…",
              "location": "parameters[0]", "evidence": [{"paragraph_id": "…", "quote": "…"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [], "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. 关键参数数量不在 [3, 6]；任一参数缺 name/current/range/unit/basis/step，或 current 未落 range，或 basis 不在 manual/spec/literature 枚举。
2. 耦合约束未登记（确认无耦合须 none_declared+source）；params 引用不存在的参数；expression/source 空。
3. current 数值未出现在 claims text/quote（unbacked_numbers 判 FAIL）。
4. completeness 汇总与实际条目不符；verdict 与要素进度矛盾；run_status/steps 违规；契约字段缺失。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，材料与数据均为虚构）：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/param_check.py --result examples/example-result.json --out /tmp/pc.json
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 材料/规格/安全阈值缺失 | material_gaps 登记 + confirmations 写 pending，range 留待定，不脑补 |
| 约束冲突（目标温度 vs 材料耐温） | param_check violations 如实登记；verdict=infeasible + risks 转人工，不静默放宽 hard 约束 |
| 无可行解 | verdict=infeasible/partially_feasible + reason + fallback 转人工 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就登记 uncertainties |
| 运行中断 | 按协议第 7 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅做「关键参数识别与可行域约束」单方向：不做响应指标代理建模、搜索策略、成本权衡与风险深化（题面五方向取第一方向）。
- 可行域/约束取自输入登记与声明出处，输入未给时不臆造；不冒充设备量程认定或安全认证。
- 算术校验基于登记的声明域/当前值，属前瞻性规划口径，不代表实测实验室数据。