---
name: sci-code-exec
description: Scientific code generation and execution skill (requirement-to-code coverage mapping / cleaning rules declared upfront / execution tracing with command-version-seed-exit / independent numeric recompute / anomaly registry without silent fixes). Turns a scientific data analysis requirement into runnable stdlib-only scripts, executes them with full reproducible traces (command, python version, seed, exit code, log path), independently recomputes every declared statistic from the raw data under the declared cleaning rules, maps every requirement to a code artifact, and registers missing/duplicate/outlier anomalies instead of silently fixing them. Verify_check mechanically audits coverage, traces, recompute and anomaly handling; gain_probe runs normal-vs-degraded ablation plus pollution injection to embed measured gain_evidence and efficiency into result.json. Use when the task asks to generate, run and verify scientific analysis code with reviewable evidence.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 requirements / code_artifacts / coverage_map / cleaning_rules / stats / recompute / anomalies / steps / execution_traces / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **需求-代码全覆盖**：题目要求（requirements[]）每条都必须有 coverage_map 条目映射到 code_artifacts 中的产物；uncovered/partial 必须写 note 并登记 pending_review，不得漏映射、不得宣称覆盖了没写的代码。
4. **口径事前声明**：cleaning_rules（缺失/去重/过滤/截断/填补规则）必须在**任何计算之前**声明（declared_at 落 /app/work/cleaning_rules.json 台账），之后禁止调整；每条 stats 的 rule_refs 必须指向已声明规则；异常值处理方式必须与声明一致。
5. **数字必须可复算**：每条 stats 都由 recompute.py 从原始数据按声明规则**独立复算**；复算不符（mismatches 非空）即 FAIL——修数据或改口径凑数都不允许，只能修代码重跑；stat 数值未在 claims 回证列入 unbacked_numbers。
6. **键归属纪律（多脚本禁写同一键）**：execution_traces 只归 run_trace.py；recompute 只归 recompute.py；self_check / gates / unbacked_numbers / unbacked_evidence / validator_verdict 只归 verify_check.py；gain_evidence / efficiency 只归 gain_probe.py；其余归 build_skeleton + Agent。
7. **自检只判 verdict**：所有脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json；执行失败照实记 exit_code 与日志，换代码重试前先定位原因。

## 定位与约定
锁定子场景：给定数据字典 + 科研数据（内联 CSV / CSV 文件 / SQLite）+ 分析要求，完成**分析代码生成 → 带留痕执行 → 数值独立复算 → 需求覆盖映射 → 异常登记**五件事。不做实验方案设计、机理解释、论文写作；不预装第三方库（只用标准库）；数据或字段缺失照实登记，不脑补数值。
关键词：映射得全（每条需求落到代码）· 留痕留得住（命令/版本/种子/退出码/日志）· 数字算得回（独立复算与声明一致）· 异常说得出（登记不静默）· 失败交得出（任何路径 exit 0 + result.json 在）。
- 输入：`/input/case.json`（数据字典 + 数据集 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`（生成脚本与日志放这里）；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；命令一律 `python3`。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与数据清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；识别数据集（csv_inline / file / sqlite）与数据字典预填；生成 /app/work/cleaning_rules.json 口径模板。
- 脚本失败时手工兜底：读 case.json 抄数据集与字段，手写骨架（键一个不缺）。

### Step 1 — 口径声明（1 次响应，任何计算之前完成）
- 填 `result.task_scope`、`result.data_dictionary`（逐字段：名称/类型/单位/缺失标记）。
- **事前声明 cleaning_rules**：每条 {rule_id, action∈dropna/dedup/filter/clip/impute, target_field, params, rationale}，declared_at 必填并同步 /app/work/cleaning_rules.json。**声明后禁止调整**；执行顺序按 rule_id 顺序。

### Step 2 — 生成代码并带留痕执行（1-3 次响应 + 每次运行 1 次脚本调用）
- 生成的分析脚本写到 /app/work（自包含：标准库、路径参数化、不写死本机路径），登记进 `result.code_artifacts`。
- 每次运行必须经 run_trace.py 留痕（写 `result.execution_traces`，仅此键）：
```bash
python3 /skills/weekly-skill/scripts/run_trace.py --script /app/work/analysis_01.py \
  --result /app/output/result.json --work-dir /app/work --timeout 120
```
- exit_code≠0 时先读日志定位原因再改代码重跑（trace 保留失败记录），不得换代码盲试；把命令、版本、退出码同步到 `result.steps`。
- 随机过程必须设种子并写入 `result.environment.seed`。

### Step 3 — 数值独立复算（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/recompute.py --case /input/case.json \
  --input-root /input --result /app/output/result.json --emit-into
```
- 按声明规则从**原始数据**独立复算每条 stats（写 `result.recompute`，仅此键）；mismatches 非空时修代码重跑，**不得改数凑数**；数据不可读时 verdict=UNABLE 并登记 material_gaps。

### Step 4 — 覆盖映射、异常登记与证据链（1 次响应）
- `result.coverage_map[]`：每条 requirement 一条 {req_id, artifact_id, step_ref, evidence_location, status∈covered/partial/uncovered, note}；uncovered/partial 登记 pending_review。
- `result.anomalies[]`：缺失/重复/异常值/类型不符/查询为空逐一登记 {anomaly_id, kind, handling, rule_ref, rows_affected, evidence_location}——处理方式必须与 cleaning_rules 一致，**不得静默修改或掩盖**。
- `result.steps[]` 与 `claims[]`：每条 stat 至少一条 claim 回证数字；verdict（completed/partial_completed/not_completed/cannot_verify）与覆盖进度一致；run_status 非 success 必须写 reason。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭覆盖映射/执行留痕/复算核验/异常登记），把**真实数字**写进 `result.gain_evidence` 与 `result.efficiency`。
- `--inject-pollution` 在**副本**上注入污染（删覆盖映射/改数值/去退出码/伪造规则引用/清环境版本等）：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence` = `{available:false, reason:"…"}`，不得编数字。退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每条需求都映射到真实代码了吗？每次执行的命令/版本/退出码/日志都留痕了吗？每个数值都能从原始数据独立复算回来吗？

## 输出 schema（result.json — 平台通用契约 + 本题业务键）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": null, "packages": "stdlib-only", "seed": null, "hardware_note": null},
    "task_scope": {"question": null, "dataset_names": [], "analysis_kind": null},
    "data_dictionary": {"version": "…", "fields": [{"name": "score", "dtype": "float", "unit": "score-unit", "missing_marker": "", "notes": ""}]},
    "cleaning_rules": {"version": "…", "declared_at": null, "rules": [{"rule_id": "CR-01", "action": "dropna", "target_field": "score", "params": {}, "rationale": "…"}]},
    "requirements": [{"req_id": "R1", "text": "…", "source": "task.md"}],
    "code_artifacts": [{"artifact_id": "A1", "path": "/app/work/analysis_01.py", "purpose": "…", "entry": "main()"}],
    "coverage_map": [{"req_id": "R1", "artifact_id": "A1", "step_ref": "steps[1]", "evidence_location": "analysis_01.py#dropna", "status": "covered", "note": ""}],
    "steps": [{"step": "step2-run-1", "action": "…", "command": "python3 /app/work/analysis_01.py", "exit_code": 0, "log_ref": "/app/work/logs/run_001.log", "python_version": "3.x", "seed": null, "status": "done"}],
    "execution_traces": [{"trace_id": "run_001", "command": "python3 …", "exit_code": 0, "log_ref": "…", "wall_seconds": 0.1, "started_at": "…", "python_version": "…"}],
    "stats": [{"stat_id": "S1", "name": "n_after_clean", "type": "count", "params": {}, "value": 4, "rule_refs": ["CR-01"], "source_field": null, "n_rows": 4, "source": "exp_a"}],
    "recompute": {"computed_by": "recompute.py", "data_sources": [], "per_stat": [{"stat_id": "S1", "declared_value": 4, "recomputed_value": 4, "abs_diff": 0.0, "tolerance": 1e-06, "matched": true}], "mismatches": [], "verdict": "PASS", "note": ""},
    "anomalies": [{"anomaly_id": "AN-01", "kind": "missing", "handling": "dropped", "rule_ref": "CR-01", "rows_affected": 1, "evidence_location": "exp_a 行 2", "note": ""}],
    "coverage": {"requirements_total": 0, "covered": 0, "partial": 0, "uncovered": 0, "stats_total": 0, "stats_recomputed": 0, "recompute_pass": false, "anomalies_registered": 0, "ratio": null},
    "conflicts": [], "pending_review": [{"req_id": "R5", "reason": "…", "needed_action": "…"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "completed | partial_completed | not_completed | cannot_verify", "verdict_basis": "一句话",
    "gain_evidence": {}, "efficiency": {}
  },
  "claims": [{"claim_id": "c-01", "text": "S1 n_after_clean=4 …", "kind": "computed", "source_id": "S1", "location": "stats[0]", "evidence": [{"log_id": "run_001", "quote": "n_after_clean=4"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "unbacked_evidence": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | invalid", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py，问题串带组标签）
1. [enum] status/verdict/run_status.state/anomaly.kind/anomaly.handling/coverage_map.status/stat.type 枚举非法。
2. [coverage] requirement 缺 coverage_map 条目；artifact_id 不在 code_artifacts；uncovered/partial 未登记 pending_review 或缺 note；code_artifacts 为空。
3. [trace] 命令不是 python3 开头；steps 有命令但缺 exit_code 或 log_ref；environment.python_version 为空；有命令步骤但 execution_traces 为空（执行未留痕）。
4. [anomaly] handling∈dropped/imputed/clipped/filtered 但 rule_ref 不在已声明 cleaning_rules；stats.rule_refs 引用不存在的规则。
5. [recompute] stat 未被复算（recompute.per_stat 缺条目）；declared_value 与 stats 值不符；recompute.verdict≠PASS；stat 数值在 claims 无回证 → unbacked_numbers 判 FAIL。
6. [structure] steps 为空或无可执行命令；coverage 汇总与实际不符；verdict 与覆盖进度/复算结果矛盾；缺 output_contract 字段；闸门（case_contract / rules_ledger / recompute / traces）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，数据与结论均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/run_trace.py --script examples/demo_analysis.py --result /tmp/skel.json --work-dir /tmp/wk
python3 scripts/recompute.py --case examples/example-case.json --input-root examples --result /tmp/skel.json --emit-into
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --rubric /tmp/wk/cleaning_rules.json --out /tmp/vc.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/sg.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 数据文件缺失 / SQLite 打不开 | material_gaps 登记，verdict=cannot_verify，绝不编造数据 |
| 缺列 / 类型不符 | anomaly 登记（kind=type_mismatch），按声明规则处理或降级，不静默改列名 |
| 脚本运行失败 | run_trace 留存 exit_code 与日志 → 读日志定位 → 修复重跑；失败记录保留不删除 |
| 依赖不可用 | 只用标准库；确实需要第三方时登记 material_gaps 并给出降级路径，不现场 pip install |
| 数值溢出 / 除零 | 在生成代码内防御（分母保护、范围检查），异常按 overflow 登记 |
| 查询为空 / 结果为空集 | 空 result 如实返回 0 行并登记 empty_query，不拿上一轮结果顶替 |
| 复算与声明不符 | 修代码重跑直到一致；修不了就 mismatches 照实报告 + verdict 降级，不改数凑数 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- cleaning_rules 的具体动作阈值是本技能事前声明并机械执行的设定（题面未给定时按保守口径设定并写明），不冒充外部统计规范。
- recompute.py 只覆盖 count/count_missing/mean/sum/min/max/group_mean/group_count 八类基础统计与五种清洗规则；更复杂的模型类结果由生成的分析脚本自行留痕 + claims 回证。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- efficiency.model_requests 由 Agent 按实际请求数回填，缺失保持 null。
