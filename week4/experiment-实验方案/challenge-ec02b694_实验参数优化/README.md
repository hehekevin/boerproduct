# exp-param-domain — 实验参数优化建议：关键参数可行域 Skill（v2 精简版）

针对 Bohrium 产品赛第 4 期「实验方案设计」赛道（challenge-ec02b694）的
**实验参数优化建议**子题参赛 Skill。v2 采用「极简单点」策略，只做题面五个
突破方向中的**第 1 条：关键参数识别与可行域约束**，砍掉响应指标代理建模、
搜索策略、成本权衡、风险深化四个方向。

## 1. 用途

给定研究目标、约束与科研材料，从设备手册、材料规格、安全阈值与历史实验中抽出
每个关键参数的**上下限、步进与互斥关系**，形成可被判定的可行域。

只做三件事：
1. 抽 3–6 个关键参数，每个给 `name + current + range[下限,上限] + unit + basis + step`。
2. 登记耦合约束（含 none_declared 兜底），用受限 AST 求值器做真实算术校验。
3. 用脚本给出 honest verdict：当前方案是否落在可行域内。

## 2. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | 3.8+，只用标准库（json/os/re/sys/argparse/ast/platform），**零第三方依赖** |
| 脚本 | 3 个：build_skeleton.py / param_check.py / verify_check.py |
| 资源上限 | ≤50 文本文件、单文件 ≤500KB、总计 ≤2MB（本包 8 文件、<80KB）|

## 3. 五步流程

```bash
# Step 0 落骨架（必做，第一个动作）
python3 scripts/build_skeleton.py --case /input/case.json --input-root /input \
  --out /app/output/result.json --work-dir /app/work

# Step 1-2 Agent 填 result.parameters[]（3-6 个关键参数）+ result.constraints[]

# Step 3 数值校验（写 result.feasibility_check）
python3 scripts/param_check.py --result /app/output/result.json --emit-into

# Step 4 自检（退出码恒 0，看 verdict）
python3 scripts/verify_check.py --result /app/output/result.json --case /input/case.json \
  --out /app/work/verify_check.json --emit-into
```

## 4. 输入输出

- **输入**：`/input/case.json`、`task.md`（以实际文件为准，不依据标签假设内容）。
- **输出**：`/app/output/result.json`，含 output_contract 全字段 + 业务键
  `parameters / constraints / feasibility_check / risks / confirmations / completeness /
  run_status / verdict / gain_evidence`。
- **verdict**：`feasible | partially_feasible | infeasible | cannot_verify`。
- **status**：`answered | partial | insufficient_evidence | input_error`。

## 5. 最小调用示例（示意，非正式答案）

`examples/` 提供合成案例（虚构催化微反应器，4 参数 + 2 约束）：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/param_check.py --result examples/example-result.json --out /tmp/pc.json
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
```

示意输出关键片段（非正式答案）：
```json
{
  "case_id": "demo-paramdomain-001", "status": "answered",
  "result": {
    "parameters": [{"name": "反应温度", "current": 150, "range": [120, 175], "unit": "℃", "basis": "spec", "step": 5}],
    "constraints": [{"cid": "C-01", "params": ["反应温度"], "expression": "反应温度 <= 175", "severity": "hard"}],
    "verdict": "feasible", "feasibility_check": {"all_within_domain": true, "all_constraints_satisfied": true}
  }
}
```

## 6. 异常处理与限制

| 异常 | 处置 |
|------|------|
| 材料/规格/安全阈值缺失 | material_gaps 登记 + confirmations pending，不脑补 |
| 约束冲突 / 无可行解 | param_check violations 如实登记；verdict=infeasible + 转人工 |
| 校验脚本失败 | 退出码恒 0，看报告 verdict；FAIL 逐条修复后重跑 |

限制：仅做可行域约束单方向；算术校验基于登记的声明域/当前值，属前瞻性规划
口径，不冒充设备量程认定或安全认证。

## 7. 版本

v2（2026-11-22）精简重构：从 v1 的 6 脚本/150 行全方向包，收敛为 3 脚本/
113 行单方向包。参数规模封顶 6，脚本职责见 worklog.md。