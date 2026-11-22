---
name: repro-verify
description: 论文复现与方法验证技能（参数/代码/指标验算与差异归因子场景）：对包内候选数值方法实际运行，参数按"论文明确/代码推断/自行设定"三类复原并登记冲突，指标用事前声明容差对照，差异逐条归因（环境/数据/实现/论文描述不足），四级复现结论；每个可复算数字带 claims 证据链，不可复算项写明缺什么材料。合成试验≠原作者复现，缺失原始数据/仓库显式登记。Use when the task asks to verify parameters, code and metrics of supplied numerical methods against a paper with tolerance-based comparison, difference attribution, and a reproducibility verdict.
---

## 强制执行协议（最高优先级）

以下 6 条优先级高于本文档其余内容；与任何步骤冲突时以本节为准。

1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行
   `build_skeleton.py`（见 Step 0）在 /app/output/result.json 写入骨架；此后任何时刻
   result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：最终 result.json 必须含 output_contract 全部键 + 本文 schema 全部键。
   无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **不编造**：论文值逐字摘录并附位置；本方计算值必须来自实际运行输出；对不上就写归因，
   不调容差凑数。不可复算的项填 `recomputable:false` 并写明缺什么材料。
4. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增处理，用现有中间结果
   完成 result.json 并收尾（status 如实填 partial）。
5. **交付前自检**：跑 verify_check.py + schema_guard.py，非 0 退出码逐条修复后重跑；
   自检不过不交付。
6. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成
   部分），绝不让 /app/output 缺少 result.json。

## 定位

锁定子场景：给定论文材料与包内候选数值方法（代码/脚本），核对参数与指标的原始来源、
在实际运行环境跑通验算、用**事前容差**判定一致、把差异**逐条归因**、给出四级复现结论。
原作者代码、物理实验、全量数据集复现不在范围；缺什么登记什么，不脑补。
关键词：找得齐（缺口显式登记）· 跑得对（参数按论文复原）· 对得上（事前容差内）·
讲得清（归因有证据）。

## 输入与输出约定

- 输入：`/input/case.json`（论文材料 + 候选方法清单 + output_contract）、包内方法文件、
  `task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。
- 预算：64 次模型请求 / 900 秒 / 单响应 16384 token。只用标准库，不装 pip 依赖。
- 按 Step 0–5 线性推进，禁止分支回环。

## 五步流程

### Step 0 — 自动落骨架与材料清单（1 次脚本调用，必做）
```bash
python /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 脚本自动：提取 output_contract 全部字段 → 写骨架 result.json；扫描 /input 建材料清单
  （检测到的候选方法文件预填 `candidates[]`，ran=false 待运行）；生成
  `/app/work/declared_tolerances.json` 容差声明模板。
- 脚本失败时手工兜底：读 case.json 抄 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 参数复原与事前容差（1 次响应）
构建 `result.parameters[]`，每行：`{parameter, value, source_class, source_location,
conflict, recomputable, missing_for_recompute}`。
- `source_class` ∈ `paper_explicit`（论文明确给出）| `code_inferred`（从代码默认值/实现
  推断）| `self_set`（自行设定，必须在 source_location 写明理由）。
- 正文/附录/代码默认值冲突：`conflict` 记双方位置与取值；**论文明确值优先**，取值依据
  写入 source_location。
- `recomputable:false` 的参数（如原始数据缺失无法复原）必须写 `missing_for_recompute`
  （缺论文哪段/哪个仓库/哪个数据文件）。
- 环境快照 `result.environment`：`{python_version, packages, seed, hardware_note}`——
  照实记录实际环境（仅标准库写 `stdlib-only`），不编造。
- **容差事前声明**：填写 `/app/work/declared_tolerances.json`（每指标 ±X% 或 ±Y +
  声明依据：论文口径 / 指标量级保守设定）。**声明必须在任何验算之前完成，禁止事后调容差。**

### Step 2 — 候选方法实际运行（1-2 次响应）
对 `result.candidates[]` 中**每个候选方法**，缺一不可：
- 读入口说明/代码确认调用方式 → 用 Step 1 复原参数**实际执行** → 捕获 stdout/stderr 摘要
- `ran=true` 填 `run_log`（含关键输出指标值）；跑不了填 `ran=false` + `failure_stage`
  （parse|import|run|output）+ 错误摘要。**不得跳过任一候选，不得伪造成功。**

### Step 3 — 指标对照与差异归因（1 次响应）
构建 `result.metric_checks[]`，每行：`{metric, candidate_id, paper_value, computed_value,
tolerance, within_tolerance, notes, recomputable, missing_for_recompute}`。
- `paper_value` 从论文表/图/正文**逐字**提取（附位置）；`computed_value` 从 Step 2 实际
  输出提取。两者只填一个=错。
- `tolerance` 取事前声明值；`within_tolerance` 按 |paper−computed| ≤ tol **复算**，不得手填。
- 指标口径（均值/方差/样本数）以论文为准；口径不明登记 `uncertainties.unreported`。
- `recomputable:false` 的指标行（paper_value 都拿不到/无数据可跑）写明
  `missing_for_recompute`，不编数值。
- **合成试验结果 ≠ 原作者复现结果**，notes 注明试验性质。

对每个超容差/不一致项写 `result.attributions[]`：`{metric, delta, attribution, evidence,
follow_up}`。
- `attribution` ∈ `environment` | `data` | `implementation` | `paper_underspecification`。
- `evidence` 必须指明具体位置（哪个环境差异/哪行代码/哪个数据切片/论文哪段缺失），
  不写"可能吧"。

### Step 4 — claims 证据链（1 次响应）
**每个可复算数字（parameters[].value、metric_checks[].paper_value/computed_value、
attributions[].delta）在 claims[] 中各有一条对应条目**：
- `text` = 论文逐字摘录 + 本方计算值 + 差异说明（三者齐备）；
- `kind` ∈ `reported`（转述论文）| `inferred`（本方计算/推断）；
- `source_id` = 材料或候选 id；`location` = §x.y / Table n / 代码文件:行 / metric_checks[i]；
- `evidence[]` = `[{paragraph_id, quote}]`，quote 是论文原文逐字摘录。

结论分级 `result.verdict`（`verdict_basis` 一句话写依据）：
| verdict | 条件 |
|---------|------|
| `reproduced` | 全部关键指标在事前容差内 |
| `partially_reproduced` | 部分在容差内 |
| `not_reproduced` | 关键指标超容差，attributions 非空 |
| `cannot_verify` | 材料缺口导致无法验算，material_gaps 非空 |

### Step 5 — 自检与交付
```bash
python /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json
python /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json --case /input/case.json
```
- 非 0 退出码 → 逐条修复 → 覆盖写 result.json → 重跑校验。
- 自查三问：每个可复算数字都有 claims 吗？不可复算项写明缺什么了吗？
  两候选都有运行记录或失败记录吗？

## 输出 schema（result.json — 顶层平台通用契约五字段）

```json
{
  "case_id": "取自 case.json",
  "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["原作者仓库未随包提供", "原始数据未随包提供"],
    "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "parameters": [{"parameter": "poly_degree", "value": 2, "source_class": "paper_explicit",
                     "source_location": "§2 第3段", "conflict": null,
                     "recomputable": true, "missing_for_recompute": null}],
    "candidates": [{"candidate_id": "A", "entry": "method_a.py::fit", "ran": true,
                     "run_log": "RMSE=0.0312", "failure_stage": null}],
    "metric_checks": [{"metric": "RMSE", "candidate_id": "A", "paper_value": 0.031,
                        "computed_value": 0.0312, "tolerance": "±10%（事前声明）",
                        "within_tolerance": true, "notes": "同口径，样本数一致",
                        "recomputable": true, "missing_for_recompute": null}],
    "attributions": [{"metric": "RMSE(B)", "delta": "+60%", "attribution": "implementation",
                       "evidence": "method_b.py:12 用一阶多项式，论文 §2 声明 degree=2",
                       "follow_up": "改二阶后重跑"}],
    "verdict": "reproduced | partially_reproduced | not_reproduced | cannot_verify",
    "verdict_basis": "分级依据一句话"
  },
  "claims": [{"claim_id": "k1", "text": "论文摘录+本方计算值+差异说明", "kind": "reported | inferred",
               "source_id": "…", "location": "…", "evidence": [{"paragraph_id": "§2", "quote": "论文原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": []
}
```

## 校验器会抓的错（verify_check.py）

1. source_class / attribution / verdict 枚举非法；self_set 无理由。
2. metric_checks 的 paper_value/computed_value 只填一个；缺事前容差；within_tolerance=true
   但复算超容差。
3. 候选 ran=false 却有 computed_value；ran=false 无 failure_stage。
4. verdict=not_reproduced 但 attributions 空；verdict=cannot_verify 但 material_gaps 空。
5. 有可复算数字但 claims 为空；recomputable=false 的行没写 missing_for_recompute。
6. environment 缺 python_version。

## 最小调用示例

`examples/` 有合成案例与示意输出（**非正式答案**），可本地自测整条链路：
```bash
python scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
```

## 异常处置

| 异常场景 | 处置 |
|---------|------|
| 仓库/原始数据不可访问 | 登记 material_gaps，对应项 recomputable=false 写明缺什么，verdict=cannot_verify |
| 依赖冲突/缺失 | failure_stage=import，stderr 摘要写 run_log，尝试 stdlib 替代 |
| 算力/时间不足 | 保留已跑部分，status=partial，changelog 注明截断位置 |
| 评价脚本缺失 | 自行实现等价计算，口径差异登记 uncertainties.unreported |
| 结果对不上 | 逐条写归因（evidence 指到具体位置），不掩盖、不调容差 |
| 运行中断 | 按协议第 6 条写 result.json，status=partial，注明中断点 |

## 已知限制

- 仅验算包内候选方法：不拉外部仓库、不申请外部数据、不装 pip 依赖（stdlib-only）。
- 合成试验 ≠ 原作者复现：结论仅针对候选方法与论文声明的一致性，不冒充全量复现。
- 容差未在论文给出时按指标量级保守声明（declared_tolerances.json 注明"本技能声明"）。
- 论文口径缺失时如实登记 uncertainties，不自创口径冒充论文口径。
