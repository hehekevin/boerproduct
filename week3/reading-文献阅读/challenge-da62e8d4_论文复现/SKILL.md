---
name: repro-verify
description: Paper reproduction and method verification skill (parameter/code/metric verification with difference attribution). Runs bundled candidate numerical methods, restores parameters by source class (paper_explicit / code_inferred / self_set) with conflict logging, pre-declares numeric tolerances before any computation, compares metrics against those tolerances with mechanical recomputation, attributes every gap (environment/data/implementation/paper_underspecification), and emits a 4-level reproducibility verdict. Every recomputable number carries a claims evidence chain with verbatim back-verification; non-recomputable items must declare missing_for_recompute. Also runs a normal-vs-degraded ablation probe that embeds real measured gain_evidence and efficiency counters into result.json. Use when the task asks to verify parameters, code and metrics of supplied numerical methods against a paper with tolerance-based comparison and difference attribution.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 steps / declared_tolerances / recomputability / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **广度优先**：先覆盖全部候选方法与全部关键指标（每步一个写盘动作），再做深挖；禁止在单一候选/指标上耗尽预算导致其余项空白。
4. **不编造**：论文值逐字摘录并附位置；本方计算值必须来自实际运行输出；对不上就写归因，不调容差凑数；不可复算的项填 `recomputable:false` 并写明缺什么材料。
5. **容差事前声明**：`declared_tolerances` 必须在**任何验算之前**写定（metric / tolerance / basis / declared_at），事后不得调整；每个 metric_checks 的 tolerance 须与声明一致。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增处理，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定论文材料与包内候选数值方法（代码/脚本），核对参数与指标的原始来源、在实际运行环境跑通验算、用**事前容差**判定一致、把差异**逐条归因**、给出四级复现结论。原作者代码、物理实验、全量数据集复现不在范围；缺什么登记什么，不脑补。
关键词：找得齐（缺口显式登记）· 跑得对（参数按论文复原）· 对得上（事前容差内）· 讲得清（归因有证据）。
- 输入：`/input/case.json`（论文材料 + 候选方法清单 + output_contract）、包内方法文件、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 六步流程

### Step 0 — 自动落骨架与材料清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；扫描 /input 建材料清单（候选方法预填 `candidates[]`，ran=false）；生成 `/app/work/declared_tolerances.json` 容差模板。
- 脚本失败时手工兜底：读 case.json 抄 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 参数复原与事前容差（1 次响应）
构建 `result.parameters[]`，每行 `{parameter, value, source_class, source_location, conflict, recomputable, missing_for_recompute}`：
- `source_class` ∈ `paper_explicit`（论文明确）| `code_inferred`（代码推断）| `self_set`（自行设定，source_location 写明理由）。冲突时记双方位置与取值，**论文明确值优先**。
- `recomputable:false` 必须写 `missing_for_recompute`（缺论文哪段/哪个仓库/哪个数据）。
- 环境快照 `result.environment`：`{python_version, packages, seed, hardware_note}`，照实记录。
- **事前容差声明**：填 `result.declared_tolerances[]` = `{metric, tolerance, basis, declared_at}`，并在 `/app/work/declared_tolerances.json` 同步。**必须在任何验算之前完成，禁止事后调容差。**
- **复现步骤**：填 `result.steps[]` = `{step, action, command, output_ref, status}`，写明他人可照此重跑的顺序与命令；至少一条给出可执行 `command`。

### Step 2 — 候选方法实际运行（1-2 次响应）
对 `result.candidates[]` 中**每个候选方法**，缺一不可：
- 读入口说明/代码确认调用方式 → 用 Step 1 复原参数**实际执行** → 捕获 stdout/stderr 摘要。
- `ran=true` 填 `run_log`（含关键输出指标值）；跑不了填 `ran=false` + `failure_stage`（parse|import|run|output）+ `failure_reason`。**不得跳过任一候选，不得伪造成功。**

### Step 3 — 指标对照与差异归因（1 次响应）
构建 `result.metric_checks[]`，每行 `{metric, candidate_id, paper_value, computed_value, tolerance, within_tolerance, notes, recomputable, missing_for_recompute}`：
- `paper_value` 从论文表/图/正文**逐字**提取（附位置）；`computed_value` 从 Step 2 实际输出提取。两者只填一个=错。`within_tolerance` 按 |paper−computed| ≤ tol **复算**，不得手填。
- `tolerance` 串必须与 `declared_tolerances` 中同 metric 的声明一致；口径（均值/方差/样本数）以论文为准；口径不明登记 `uncertainties.unreported`；`recomputable:false` 的指标行写明 `missing_for_recompute`，不编数值。
- **合成试验结果 ≠ 原作者复现结果**，notes 注明试验性质。
- 对每个超容差项写 `result.attributions[]` `{metric, delta, attribution, evidence, follow_up}`，`attribution` ∈ `environment|data|implementation|paper_underspecification`，`evidence` 必须指明具体位置（哪个环境差异/哪行代码/哪个数据切片/论文哪段缺失），不写"可能吧"。
- 汇总 `result.recomputability` = `{total_items, recomputable_items, non_recomputable_items, ratio}`（total_items = parameters 行数 + metric_checks 行数）。

### Step 4 — claims 证据链（1 次响应）
**每个可复算数字（parameters[].value、metric_checks[].paper_value/computed_value、attributions[].delta）在 claims[] 中各有一条对应条目**：
- `text` = 论文逐字摘录 + 本方计算值 + 差异说明（三者齐备）；`kind` ∈ `reported`（转述论文）| `inferred`（本方计算）；`source_id` = 材料或候选 id；`location` = §x.y / Table n / 代码文件:行 / metric_checks[i]；`evidence[]` = `[{paragraph_id, quote}]`，quote 是论文原文逐字摘录。
- **数字逐字回证**：论文侧数字必须出现在对应 quote 里（空白归一化后子串匹配），本方计算值必须出现在 claim text 里；verify_check 把未回证数字列入 `unbacked_numbers` 并判 FAIL。

结论分级 `result.verdict`（`verdict_basis` 一句话写依据）：`reproduced` 全部关键指标在事前容差内；`partially_reproduced` 部分在容差内；`not_reproduced` 关键指标超容差且 attributions 非空；`cannot_verify` 材料缺口导致无法验算且 material_gaps 非空。
运行状态 `result.run_status` = `{state, reason, manual_takeover[]}`，`state` ∈ `success|partial|unable_to_determine|refused`；非 success 必须写 reason 与人工接管位置（题面"运行状态"字段）。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（全部机械校验开）与退化模式（关闭逐字回证 + 容差复算），把**真实数字**写进 `result.gain_evidence`：`runs[]`（两遍逐项指标）、`delta_normal_minus_degraded`、`mechanism_to_metric_map`（机制→指标映射）、`boundaries`（边界）、`failure_conditions`（失效条件）。
- 五项对照指标：可复算数值占比 / 容差违规漏检数 / 需人工核对条目数 / 步骤数 / 追问轮次。数字全部来自实跑，**不得手填或臆造**。
- 同时写 `result.efficiency`：自动可采集计数（墙钟、字节、检查项数、文件数、人工条目、追问轮次）+ `reproduce` 复现命令；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- `--inject-pollution` 在**副本**上注入污染做反例自测：正常模式须抓到污染项（`caught_by_normal_mode=true`），原 result.json 不被改动。
- 脚本跑不了时（如环境缺脚本）：**手工**写 `gain_evidence` = `{available:false, reason:"…"}` 与 `efficiency` = `{available:false, reason:"…"}`，不得编数字。
- 退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- 两个脚本退出码恒为 0；**判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- verify_check 通过后把每条检查的三元组 `{item, template_value, applied, match}`、闸门状态与 unbacked 清单回写进 result.json（键 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`），保留勿删。
- 自查三问：每个可复算数字都有 claims 回证吗？不可复算项写明缺什么了吗？两候选都有运行记录或失败记录吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["原作者仓库未随包提供"],
    "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "parameters": [{"parameter": "poly_degree", "value": 2, "source_class": "paper_explicit", "source_location": "§2 第3段", "conflict": null, "recomputable": true, "missing_for_recompute": null}],
    "candidates": [{"candidate_id": "A", "entry": "method_a.py::fit", "ran": true, "run_log": "RMSE=0.0312", "failure_stage": null, "failure_reason": null}],
    "metric_checks": [{"metric": "RMSE", "candidate_id": "A", "paper_value": 0.031, "computed_value": 0.0312, "tolerance": "±10%", "within_tolerance": true, "notes": "同口径；合成试验", "recomputable": true, "missing_for_recompute": null}],
    "attributions": [{"metric": "RMSE(B)", "delta": 0.0187, "attribution": "implementation", "evidence": "method_b.py:12 用一阶多项式，论文 §2 声明 degree=2", "follow_up": "改二阶后重跑"}],
    "steps": [{"step": "step2", "action": "用复原参数运行候选方法", "command": "python3 method_a.py --degree 2", "output_ref": "candidates[0].run_log", "status": "done"}],
    "declared_tolerances": [{"metric": "RMSE", "tolerance": "±10%", "basis": "论文未给，按量级保守声明", "declared_at": "step1"}],
    "recomputability": {"total_items": 4, "recomputable_items": 3, "non_recomputable_items": 1, "ratio": 0.75},
    "run_status": {"state": "partial", "reason": "原始数据未提供，全量复现无法判定", "manual_takeover": ["取得作者运行配置"]},
    "verdict": "reproduced | partially_reproduced | not_reproduced | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 .../gain_probe.py ..."}
  },
  "claims": [{"claim_id": "k1", "text": "论文摘录+本方计算值+差异说明", "kind": "reported | inferred", "source_id": "…", "location": "…", "evidence": [{"paragraph_id": "§2", "quote": "论文原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "result_readable", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. source_class / attribution / verdict / run_status.state / failure_stage 枚举非法；self_set 无理由。
2. metric_checks 的 paper_value/computed_value 只填一个；缺事前容差或与 declared_tolerances 不一致；within_tolerance=true 但复算超容差。
3. 候选 ran=false 无 failure_stage / failure_reason / 枚举非法；未运行的候选却有 computed_value。
4. verdict=not_reproduced 但 attributions 空；verdict=cannot_verify 但 material_gaps 空。
5. 有可复算数字但 claims 为空；recomputable=false 的行没写 missing_for_recompute；recomputability 汇总与实际条目数不符。
6. 论文侧数字无 quote 回证 / 本方计算值无 claim text 回证 → unbacked 计入 FAIL。
7. environment 缺 python_version；steps 为空或全无 command。闸门状态非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**），可本地自测整条链路：
```bash
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 仓库/原始数据不可访问 | 登记 material_gaps，对应项 recomputable=false 写明缺什么，verdict=cannot_verify |
| 依赖冲突/缺失 | failure_stage=import，failure_reason+stderr 摘要写 run_log，尝试 stdlib 替代 |
| 算力/时间不足 | 保留已跑部分，status=partial，changelog 注明截断位置 |
| 评价脚本缺失 | 自行实现等价计算，口径差异登记 uncertainties.unreported |
| 结果对不上 | 逐条写归因（evidence 指到具体位置），不掩盖、不调容差 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅验算包内候选方法：不拉外部仓库、不申请外部数据、不装 pip 依赖（stdlib-only）。
- 合成试验 ≠ 原作者复现：结论仅针对候选方法与论文声明的一致性，不冒充全量复现；容差未在论文给出时按指标量级保守声明（declared_tolerances 注明"本技能声明"），论文口径缺失时如实登记 uncertainties，不自创口径。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
