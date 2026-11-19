---
name: sci-db-query-analyze
description: Scientific-database query and analysis skill (structured query construction / question-query mapping / in-memory query execution with logging / aggregate mechanical recompute with group conservation / empty-result and boundary registration). Builds each analysis question into structured queries (filters / group_by / aggregations, cross-table two-step key passing), executes them against the case.json dataset snapshot by in-memory filtering (no real DB connection), leaves a full issued+executed query log, independently recomputes every aggregate (count/avg/sum) and enforces group conservation (group count sum == total rows), registers empty results, missing values, duplicate rows and coding-field semantics into a boundary registry instead of silently dropping them. Verify_check re-checks five groups (mapping / recompute / boundary / log / conservation) and re-runs normal-vs-degraded ablation via gain_probe to embed measured gain_evidence and efficiency counters into result.json. Use when the task asks to query a research dataset, aggregate numbers, explain field semantics and deliver reproducible, auditable query results.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py` 在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 queries / query_results / recompute / boundary_registry / query_log / coverage / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **每问必有映射查询**：query_scope 中每个要回答的问题至少一条 query 有 question_id 回指；过滤列/分组列/聚合列必须存在于该数据集实际字段（张冠李戴即 FAIL）；编码型字段按 field_dictionary 语义过滤，不得当数值直接聚合。
4. **不编造数字**：query_results 的每个聚合值必须由 stat_recompute.py 独立复算一致；分组查询必须组计数和==总行数（守恒）；复算不一致以原始数据为准修复查询，不改数据凑结论。
5. **空结果必须登记**：row_count==0、缺失值被过滤剔除、重复记录、数据集未找到一律写入 boundary_registry（含 ref/kind/note），绝不静默丢弃；确认不了的进 pending_review。
6. **键归属纪律（多脚本禁写同一键）**：queries/query_results/query_log/boundary_registry 只归 query_engine.py（kind 以 manual_ 开头的手工登记会被保留）；recompute 只归 stat_recompute.py；self_check / gates / unbacked_numbers / unbacked_evidence / validator_verdict 只归 verify_check.py；gain_evidence / efficiency 只归 gain_probe.py；其余归 build_skeleton + Agent。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
技能标志 `sci-db-query-analyze-v1`（脚本据此校验与 SKILL.md 同包部署）。
锁定子场景：给定数据快照（case.json 内数据集，如表格 rows 或 SQLite 导出行）与分析问题，把问题编译成**结构化查询**（filters/group_by/aggregations + issued_sql_like 留痕），在内存中过滤聚合执行（**不连接真实数据库**），产出可独立复算的结果集、查询日志、字段语义解释与边界登记。不做库表写入、不做 SQL 方言适配、不下载外部数据；快照之外的口径一律登记不臆断。
关键词：问得清（每问映射到查询）· 查得实（过滤列真实存在）· 算得准（聚合独立复算+分组守恒）· 留得全（issued+executed 日志）· 敢报缺（空结果/缺失/重复进边界登记）。
- 输入：`/input/case.json`（数据集 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。
- **标识符判定禁用 isalpha()**（汉字 isalpha()==True 会误放行）：query_id/dataset_id/列名一律用显式字符集校验（见 build_skeleton.IDENT_RE，允许 ASCII 与汉字、禁空白与控制字符）。

## 七步流程

### Step 0 — 自动落骨架与数据集清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（datasets/tables/snapshots/data）提取数据集清单与行数，从 questions/tasks 提取问题清单预填 query_scope；生成 /app/work/query_scope.json 口径台账（filter_ops/agg_fns/缺失值令牌/空结果规则）。
- 脚本失败时手工兜底：读 case.json 抄数据集与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 字段语义与查询口径（1 次响应，执行前完成）
- 填 `result.field_dictionary`：每个用到的字段 {dataset_id, column, dtype, meaning, unit_or_encoding}；**编码型字段**（如状态码）必须写清编码表并注明"不得当数值聚合"。
- query_scope.query_convention 已由骨架声明（filter_ops 12 种 / agg_fns 6 种 / 缺失令牌 / 空结果规则）；声明后禁止调整。

### Step 2 — 构建结构化查询（1-2 次响应，每问至少一条）
在 `result.queries[]` 写：{query_id, question_id, dataset_id, filters[], group_by[], aggregations[], issued_sql_like}。
- filters op ∈ eq/ne/gt/gte/lt/lte/in/nin/contains/between/isnull/notnull；aggregations fn ∈ count/sum/avg/min/max/nunique，column="*" 表示整行计数。
- **跨表两步**：先在维表过滤取键（如 nunique/列表），再以 in 过滤事实表聚合——显式传键控制一对多膨胀， issued_sql_like 注明键来源。
- 预期空结果/边界探针查询也照常定义，靠 boundary_registry 兜底。
- 注意：数值列含缺失值时 query_engine 自动剔除缺失行并在 boundary 登记（missing_values），均值口径按"剔除后"计算，如需其它口径在此步写明。

### Step 3 — 执行查询并留痕（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/query_engine.py --result /app/output/result.json --case /input/case.json
```
- 内存过滤执行每条查询，写 query_results（row_count/groups/aggregates/empty/status）+ query_log（issued+executed+时间戳）+ 自动 boundary 登记；数据集未找到、非法 op/fn 记 status=error 不中断。
- 脚本失败时手工兜底：按同口径手工过滤计数，并在 steps 注明「手算」，事后重跑脚本核对。

### Step 4 — 独立复算与证据链（1 次脚本调用 + 1 次响应）
```bash
python3 /skills/weekly-skill/scripts/stat_recompute.py --result /app/output/result.json --case /input/case.json
```
- **独立实现**（不 import query_engine）复算 row_count/各聚合值/分组守恒（组计数和==总行数、组 sum 和==总体 sum），写 result.recompute（仅此键）。
- **claims 证据链**：每个问题至少一条 {claim_id, text, kind=computed, source_id=query_id, location, evidence:[{paragraph_id, quote}]}；text 含关键数字；数字须有 recompute 检查回证（否则 unbacked_numbers 判 FAIL）；evidence 引文逐字来自 case.json（否则 unbacked_evidence 判 FAIL）。
- 结论分级 `result.verdict`：`answered` 全部问题有结论（含空结果登记）；`partially_answered` 部分；`not_appraised` 未执行；`cannot_verify` 数据集缺失。运行状态 `result.run_status` = {state, reason, manual_takeover[]}。
- coverage 自动回填：questions_total/queries_total/answered_questions/empty_results/boundary_registered/ratio。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- **同一校验器（verify_check.analyze）双跑**：normal（mapping/recompute/boundary/log/conservation 五组全开）vs degraded（--ablate all 关闭五组），真实漏检差写入 result.gain_evidence。
- `--inject-pollution` 在**副本**上注入 8 类污染（聚合值篡改/行数篡改/组计数篡改/过滤条件遗漏/删日志/删边界登记/删复算/悬空映射）：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 同时写 result.efficiency（墙钟、checker_runs、steps_count + reproduce 命令）；model_requests 由 Agent 按实际请求数回填，缺失保持 null。
- 脚本跑不了时**手工**写 gain_evidence={available:false, reason}，不得编数字。退化模式结果仅用于增益对照，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- FAIL 则按 problems 逐条修复 → 覆盖写 result.json → 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每个问题的查询都映射回问题且列名真实存在吗？每个聚合数字都能独立复算并守恒吗？空结果、缺失值、重复记录都登记了吗？

## 输出 schema（result.json — 平台通用契约 + 本题业务键）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": null, "packages": "stdlib-only", "seed": null, "hardware_note": null},
    "query_scope": {"questions": [{"question_id": "Q01", "text": "…", "intent": "…"}], "snapshot_note": "…", "query_convention": {"filter_ops": ["eq","…"], "agg_fns": ["count","…"], "missing_tokens": ["na","…"], "empty_result_rule": "…"}},
    "field_dictionary": [{"dataset_id": "…", "column": "status", "dtype": "integer-code", "meaning": "…", "unit_or_encoding": "编码型，不得当数值聚合"}],
    "queries": [{"query_id": "QA-01", "question_id": "Q01", "dataset_id": "…", "filters": [{"column": "…", "op": "eq", "value": "…"}], "group_by": [], "aggregations": [{"fn": "count", "column": "*", "alias": "n"}], "issued_sql_like": "SELECT …", "status": "pending"}],
    "query_results": [{"query_id": "QA-01", "row_count": 12, "groups": [{"key": {}, "count": 0}], "aggregates": {"n": 0}, "empty": false, "status": "ok", "notes": []}],
    "recompute": {"computed_by": "stat_recompute.py", "checks": [{"query_id": "QA-01", "kind": "row_count|aggregate|group_conservation_*", "ok": true, "detail": "…"}], "all_ok": true},
    "boundary_registry": [{"ref": "QA-04", "kind": "empty_result|missing_values|manual_duplicate_rows|dataset_not_found", "note": "…"}],
    "query_log": [{"seq": 1, "ts": "…", "query_id": "QA-01", "action": "issued|executed", "detail": {}}],
    "coverage": {"questions_total": 0, "queries_total": 0, "answered_questions": 0, "empty_results": 0, "boundary_registered": 0, "ratio": 0.0},
    "pending_review": [], "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success|partial|unable_to_determine|refused", "reason": null, "manual_takeover": []},
    "verdict": "answered | partially_answered | not_appraised | cannot_verify", "verdict_basis": "一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "model_requests": null, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "…数字…", "kind": "computed", "source_id": "QA-01", "location": "query_results[QA-01]", "evidence": [{"paragraph_id": "…", "quote": "case.json 原文原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "unbacked_evidence": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | invalid", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py，问题串带组标签）
1. [mapping] 查询缺 question_id 或 question_id 悬空；过滤/分组/聚合列不在数据集实际字段（张冠李戴）；查询定义与 query_log.issued 记录不一致（执行后被改写/条件遗漏）；无任何成功查询。
2. [recompute] recompute 段缺失或 computed_by 非 stat_recompute.py；任一复算检查 ok=false（行数/聚合/守恒不一致）。
3. [boundary] 空结果查询未登记 boundary_registry（静默丢弃）；全空且无任何登记记录。
4. [log] query_log 为空；日志 seq 重复；查询缺 issued 或 executed；缺时间戳。
5. [conservation] 分组查询组计数和 ≠ row_count（行数膨胀/丢失，与 stat_recompute 分开实现互查）。
6. [structure]/[contract] steps 为空、coverage.queries_total 与实际不符、verdict 与进度矛盾、缺 output_contract 字段；闸门（case_contract/query_execution/recompute_output）非 enforced 时 warn——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，数据为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/query_engine.py --result /tmp/skel.json --case examples/example-case.json
python3 scripts/stat_recompute.py --result /tmp/skel.json --case examples/example-case.json
python3 scripts/gain_probe.py --result /tmp/skel.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result /tmp/skel.json --case examples/example-case.json --out /tmp/wk/vc.json --emit-into
python3 scripts/schema_guard.py --result /tmp/skel.json --case examples/example-case.json --out /tmp/wk/sg.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 数据集未找到 / 键名不识别 | status=error + boundary 登记 dataset_not_found；手工核对键名后重跑，绝不假设字段 |
| 查询结果 0 行 | boundary 登记 empty_result，verdict 如实降级，不补造数字 |
| 数值列含缺失/重复记录 | 缺失行剔除并登记 missing_values；重复登记 manual_duplicate_rows 待人工确认，不静默去重 |
| 编码型字段被要求聚合 | 按 field_dictionary 语义转义过滤，claims 注明口径，不做数值聚合 |
| 复算不一致 | 以原始数据为准修复查询/结果，不改数据凑结论；修不了登记 uncertainties |
| 非数值混入数值列 | 该行剔除并登记，聚合只计可解析值 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 只对 case.json 提供的数据快照做内存查询模拟，不连接真实数据库、不做 SQL 方言适配；快照之外的表/字段一律登记不臆断。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 增益探针的污染注入只覆盖 8 类客观违规，不能证明全部正确性；数值正确性以 stat_recompute 独立复算为准。
