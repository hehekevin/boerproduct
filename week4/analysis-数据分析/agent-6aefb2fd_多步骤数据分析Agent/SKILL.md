---
name: multi-step-analysis-chain
description: Multi-step scientific data analysis skill (declared step-graph orchestration / per-step trace with replay / mid-product schema+recompute validation / failure fallback registration / conclusion-evidence alignment). Declares an acyclic step graph (import/field-check, cleaning, statistics, visualization, report) before execution, records a replayable trace (command/inputs/outputs/artifacts/checks) for every step, validates each mid-product with schema and numeric recomputation and rolls up a middle-check pass rate, registers failed/degraded/skipped steps as fallbacks or pending review instead of silently dropping them, and aligns every claim number and quote back to step artifacts or the actual source data. Verify_check re-derives DAG acyclicity (Kahn, cross-checked against a second DFS implementation in gain_probe), recomputes the pass rate, back-checks claim quotes verbatim and claim numbers against step outputs, and re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency counters into result.json. Use when the task asks for cleaning, statistics, visualization or reporting over fixed research tables with auditable, replayable evidence.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 plan / steps / fallbacks / middle_checks / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **先声明步骤图，再执行**：result.plan（每步 step_id/name/depends_on/inputs/outputs/checkpoint，declared_at 必填）必须在**任何步骤执行之前**声明并同步 /app/work/analysis_plan.json 台账，之后禁止调整；步骤图必须依赖无环（S1→S2→S3→S4/S5 模板可按题裁剪，但依赖关系必须真实）。
4. **逐步留痕，不可回放不算完成**：每个计划步骤在 result.steps 有且仅有一条留痕（step_id/status/command/inputs/outputs 必填，artifacts 存中间产物）；status ∈ done|failed|degraded|skipped；留痕顺序必须与拓扑序一致，依赖步骤未完成不得执行后续步骤。
5. **中间产物必须校验**：每个步骤的 checks 至少含一条 schema 校验 + 一条数值复算（recompute），失败项 passed=false 并触发 Step 4 降级；middle_checks 通过率由 verify_check 独立复算，不得手改凑数。
6. **键归属纪律（多脚本禁写同一键）**：dag / trace_audit 只归 pipeline_run.py；middle_checks / self_check / gates / unbacked_numbers / unbacked_evidence / validator_verdict 只归 verify_check.py；gain_evidence / efficiency 只归 gain_probe.py；其余归 build_skeleton + Agent。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定科研数据表 + 一句分析需求（含数据字典），按**声明的步骤图**做多步骤编排——导入与字段核对 → 清洗（缺失/异常/重复）→ 统计检验 → 可视化 → 报告生成，每步留痕可回放、中间产物过校验、失败步骤降级登记、最终结论与各步证据链对齐。不做数据库检索、不装 pip 依赖、不做超出题面的建模。
关键词：图无环（步骤图先声明、依赖可复算）· 步留痕（command/inputs/outputs 齐全可回放）· 中间验（schema+数值复算双闸）· 败登记（降级/跳过不静默）· 证对齐（正文数字可回算、引文逐字回证）。
- 输入：`/input/case.json`（数据表 + 数据字典 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与步骤图模板（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（tables/datasets/data 等）提取数据表清单预填 task_scope；预填五段步骤图模板；生成 /app/work/analysis_plan.json 台账。
- 脚本失败时手工兜底：读 case.json 抄表清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 任务边界与步骤图声明（1 次响应，执行前完成）
- 填 `result.task_scope`（question / table_ids / plan_version）与 `result.plan`：按题面裁剪五段模板（可增删步骤，但每步必须有 inputs/outputs/checkpoint 且依赖真实），declared_at 必填并同步台账。**声明后禁止调整。**
- step_id 只允许 ASCII 大写字母+数字（如 S1、S2）；**禁止用 str.isalpha 校验标识符**（该函数对汉字返回 True，「步骤一」会被误判合法）。

### Step 2 — 逐步执行与留痕（2-4 次响应，广度优先）
按拓扑序执行，每步一条留痕：
- `status` ∈ done|failed|degraded|skipped；command 写实际执行的命令或动作；inputs/outputs 写本步实际读写的产物；
- `artifacts` 落中间产物（schema_report / clean_summary+clean_log / stats_result / figure_spec / report_markdown）：清洗必须行数守恒（原始=保留+剔除+填补）并逐条登记规则；统计必须写前提校验与选择依据；
- 每步 `checks[]` 至少一条 schema + 一条 recompute（关键数值复算，如组均值、行数、差值），passed 如实填。

### Step 3 — 留痕审计与步骤图复核（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/pipeline_run.py --result /app/output/result.json \
  --plan /app/work/analysis_plan.json --out /app/work/pipeline_run.json
```
- 机械复核：依赖无环（Kahn 拓扑）、依赖引用完备、每计划步骤有留痕、留痕顺序合拓扑；写入 `result.dag` 与 `result.trace_audit`（仅此两键）。
- 脚本失败时手工兜底：手绘依赖表核对无环，事后仍须重跑脚本核对。

### Step 4 — 失败降级登记（1 次响应）
- failed/degraded 步骤必须登记 `result.fallbacks[]`（step_id + failure_mode + degraded_action + registered=true）；skipped 步骤登记 `result.pending_review[]`（reason + needed_action）。
- 降级原则：能降级就降级（如图形渲染失败→输出 figure_spec 数据规格并注明），绝不让单步失败拖垮全链，也绝不静默跳过。
- 运行状态 `result.run_status` = {state, reason, manual_takeover[]}；结论分级 `result.verdict`（verdict_basis 一句话）：answered 全链完成 / partially_answered 部分 / cannot_verify 材料缺口。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（五组机械校验全开）与退化模式（--ablate all：关闭步骤图完备/留痕回放/中间校验/证据对齐/降级登记），把**真实数字**写进 `result.gain_evidence`：runs、delta_normal_minus_degraded、mechanism_to_metric_map、boundaries、failure_conditions。
- 违规客观真值由探针独立复算（环检测为 DFS 第二实现，与校验层分开）；`--inject-pollution` 在**副本**上注入污染（注入环/删留痕/篡改通过率/编造引文与数字/清空降级登记）：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 同时写 `result.efficiency`（墙钟、字节、检查项数、留痕数 + reproduce 命令）；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- 脚本跑不了时**手工**写 `gain_evidence` = {available:false, reason:"…"}，不得编数字。退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --plan /app/work/analysis_plan.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每个计划步骤都有可回放留痕吗？中间校验通过率是复算出来的吗？每条结论的数字和引文都能回到步骤产物或原始数据吗？

## 输出 schema（result.json — 平台通用契约 + 本题业务键）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": null, "packages": "stdlib-only", "seed": null, "hardware_note": null},
    "task_scope": {"question": null, "table_ids": [], "plan_version": "analysis-plan-v1"},
    "plan": {"version": "…", "declared_at": "…", "steps": [{"step_id": "S1", "name": "导入与字段核对", "depends_on": [], "inputs": ["raw_table"], "outputs": ["schema_report"], "checkpoint": "…"}]},
    "dag": {"nodes": [], "edges": [], "acyclic": true, "order": [], "computed_by": "pipeline_run.py", "trace_stats": {}},
    "steps": [{"step_id": "S1", "status": "done", "command": "…", "inputs": [], "outputs": [], "artifacts": {}, "checks": [{"check_id": "S1-SCHEMA-01", "kind": "schema|recompute", "passed": true, "detail": "…"}]}],
    "fallbacks": [{"step_id": "S4", "failure_mode": "…", "degraded_action": "…", "registered": true}],
    "middle_checks": {"total": 10, "passed": 9, "failed": 1, "pass_rate": 0.9, "computed_by": "verify_check.py"},
    "artifacts": {"clean_summary": {}, "stats_result": {}, "figure_spec": {}, "report_markdown": {}},
    "conflicts": [], "pending_review": [{"step_id": "S4", "reason": "…", "needed_action": "…"}],
    "trace_audit": {"computed_by": "pipeline_run.py", "problems": [], "stats": {}},
    "run_status": {"state": "success|partial|unable_to_determine|refused", "reason": null, "manual_takeover": []},
    "verdict": "answered | partially_answered | not_answered | cannot_verify", "verdict_basis": "一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "结论句（含数字）", "kind": "grounded|inferred", "source_id": "S2", "location": "result.steps[S2].artifacts…", "evidence": [{"paragraph_id": "case 内定位", "quote": "逐字摘录"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "unbacked_evidence": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | invalid", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py，问题串带组标签）
1. [contract] 缺 output_contract 字段；case_id 与 case.json 不一致；status 枚举非法。
2. [plan] plan 未声明 / declared_at 为空 / 与台账不一致；步骤图有环或依赖引用悬空（独立复算）。
3. [trace] 计划步骤无留痕；留痕缺要素（command/inputs/outputs）；status 枚举非法；依赖未完成即执行；留痕顺序违背拓扑序。
4. [middle] 校验条目 kind 非法（须 schema|recompute）；有留痕但零中间校验；middle_checks 与复算不符。
5. [evidence] claims 为空；引文在 case.json 与步骤产物中均不存在（逐字比对）；claim 正文数字无回证 → unbacked_numbers / unbacked_evidence 判 FAIL。
6. [fallback]/[pending] failed/degraded 未登记 fallbacks（缺 degraded_action/failure_mode）；skipped 未登记 pending_review。
7. [structure]/[enum]/[owner] 步骤图基本形非法（step_id 须 ASCII，禁 isalpha）；verdict/run_status 枚举非法；键 computed_by 与归属矩阵不符——闸门（case_contract / plan_ledger / dag_acyclic / middle_checks）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，数据与结论均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/out/result.json --work-dir /tmp/wk
python3 scripts/pipeline_run.py --result examples/example-result.json --plan /tmp/wk/analysis_plan.json --out /tmp/wk/pipeline_run.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --plan /tmp/wk/analysis_plan.json --out /tmp/wk/vc.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/wk/sg.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 表缺失/列缺失/空表 | material_gaps 登记；相关步骤 status=skipped + pending_review，verdict 如实降级，绝不补造数据 |
| 编码错误/类型不符 | 在该步 checks 里 schema 校验 passed=false，按可读部分降级处理并在 clean_log 登记 |
| 清洗规则冲突 | 以 task.md 题面口径优先，conflicts 登记，不得静默改口径 |
| 统计前提不满足 | stats_result 写明前提校验结果与替代方法选择依据，不硬套检验 |
| 图形渲染失败/无图形栈 | S 降级输出 figure_spec 数据规格，fallbacks 登记，报告注明图形未实际生成 |
| 步骤图与实际执行对不上 | 以实际留痕为准修复 plan 或补执行，绝不删留痕凑拓扑序 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 五段步骤图模板是本技能事前声明并机械执行的编排口径，题面另有要求时按题裁剪并在 task_scope 写明；不冒充完整科研工作流平台。
- 仅处理输入提供的数据表：不做数据库检索、不联网取数、不装第三方依赖，图形产物受运行环境限制时以数据规格降级交付。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
