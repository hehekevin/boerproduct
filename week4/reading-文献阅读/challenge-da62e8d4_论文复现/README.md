# repro-verify — 论文复现与方法验证 Skill（v3）

针对 Bohrium 产品赛第 3 周「文献阅读」赛道「论文复现与方法验证」(challenge-da62e8d4)
的参赛 Skill。锁定子场景：**参数/代码/指标验算与差异归因**。

## 用途

给定论文材料与包内候选数值方法（代码/脚本），完成：

1. **参数复原**：每个关键参数标注 `paper_explicit` / `code_inferred` / `self_set`
   三类来源与出处；正文/附录/代码冲突时登记双方取值，论文明确值优先。
2. **实际运行**：逐个候选方法用复原参数实际执行，`ran` + `run_log` 或
   `failure_stage`（parse/import/run/output），不跳过、不伪造成功。
3. **指标对照**：`paper_value` 逐字摘自论文（附位置），`computed_value` 来自实际输出，
   用**事前声明**的容差（`declared_tolerances.json`，验算前写定、禁止事后调）复算
   `within_tolerance`。
4. **差异归因**：超容差项逐条归因到 environment / data / implementation /
   paper_underspecification，evidence 指到具体位置。
5. **结论分级**：reproduced / partially_reproduced / not_reproduced / cannot_verify
   四级，附 `verdict_basis`。

核心保证：每个可复算数字（参数值、paper_value、computed_value、delta）在
`claims[]` 有对应证据链（论文逐字摘录 + 本方计算值 + 差异说明）；
不可复算项标 `recomputable:false` 并写明缺什么材料；合成试验 ≠ 原作者复现，
缺失原始数据/仓库显式登记到 `material_gaps`。

## 调用方式

Agent 加载 `SKILL.md` 后按其中五步流程执行（Step 0 落骨架 → Step 1 参数与容差 →
Step 2 运行候选 → Step 3 对照归因 → Step 4 claims 与结论 → Step 5 自检交付）。
关键脚本（评测环境路径为 `/skills/weekly-skill/scripts/`，本地自测用相对路径）：

```bash
# Step 0：自动落骨架 + 材料清单 + 容差模板
python /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 5：双重自检
python /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json
python /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json --case /input/case.json
```

## 输入与输出

- 输入：`/input/case.json`（论文材料 + 候选方法清单 + output_contract）、包内方法文件、
  `task.md`。
- 输出：`/app/output/result.json`（顶层五字段契约：case_id / status / result / claims /
  uncertainties + changelog；result 内含 material_gaps、environment、parameters、
  candidates、metric_checks、attributions、verdict、verdict_basis）。
- status：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。

## 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例：论文声明 RMSE=0.031，两候选方法分别复算得 0.0312（容差内）
与 0.0497（超容差，归因到实现差异）。示意输出关键片段：

```json
{
  "case_id": "demo-repro-001", "status": "answered",
  "result": {
    "parameters": [{"parameter": "拟合阶数", "value": 2, "source_class": "paper_explicit",
                     "source_location": "§2", "recomputable": true}],
    "candidates": [{"candidate_id": "candidate-A", "ran": true, "run_log": "RMSE=0.0312"}],
    "metric_checks": [{"metric": "RMSE", "candidate_id": "candidate-A",
                        "paper_value": 0.031, "computed_value": 0.0312,
                        "tolerance": "±10%（事前声明）", "within_tolerance": true}],
    "attributions": [{"metric": "RMSE(candidate-B)", "delta": "+60%",
                       "attribution": "implementation",
                       "evidence": "method_b.py:12 用一阶多项式，论文 §2 声明 degree=2"}],
    "verdict": "partially_reproduced"
  },
  "claims": [{"claim_id": "k-01", "kind": "inferred", "location": "metric_checks[0]",
               "evidence": [{"paragraph_id": "§2", "quote": "RMSE 0.031"}]}]
}
```

本地自测整条链路：

```bash
python scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 适用范围与限制

- 仅验算包内候选方法：不拉外部仓库、不申请外部数据、不装 pip 依赖（stdlib-only）。
- 合成试验 ≠ 原作者复现：结论仅针对候选方法与论文声明的一致性，不冒充全量复现。
- 容差未在论文给出时按指标量级保守声明（declared_tolerances.json 注明"本技能声明"）。
- 论文口径（统计方式/样本数）缺失时登记 uncertainties.unreported，不自创口径。

## 异常处理

| 异常 | 处置 |
|------|------|
| 仓库/原始数据不可访问 | material_gaps 登记，对应项 recomputable=false 写明缺什么，verdict=cannot_verify |
| 依赖冲突/缺失 | failure_stage=import，stderr 摘要入 run_log，尝试 stdlib 替代 |
| 算力/时间不足 | 保留已跑部分，status=partial，changelog 注明截断位置 |
| 评价脚本缺失 | 自行实现等价计算，口径差异登记 uncertainties |
| 运行中断 | 仍写 result.json（status=partial），注明中断点 |

## 自查方法

交付前必跑两个校验脚本（见上），verify_check 抓业务逻辑错（枚举/容差复算/归因完备/
claims 覆盖），schema_guard 抓结构错（output_contract 字段缺失）。非 0 退出码逐条修复。

## 资源清单与维护

| 文件 | 作用 |
|------|------|
| SKILL.md | 技能本体（强制协议 + 五步流程 + schema + 校验说明） |
| scripts/build_skeleton.py | Step 0 自动落骨架/材料清单/容差模板（三级容错） |
| scripts/verify_check.py | 业务逻辑校验器（容差复算/claims 覆盖/recomputable） |
| scripts/schema_guard.py | output_contract 结构守卫 |
| examples/example-case.json | 合成输入示例 |
| examples/example-result.json | 示意输出（非正式答案） |
| README.md | 本说明 |
| worklog.md | 开发记录与版本回归分析 |

版本 v3（2026-11-13）。依赖：Python 3.8+ 标准库，无第三方依赖。
