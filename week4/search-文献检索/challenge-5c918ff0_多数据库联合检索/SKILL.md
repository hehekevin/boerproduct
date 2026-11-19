---
name: multi-db-merge
description: Multi-database scholarly retrieval skill (cross-database query adaptation, field normalization, dedup, merge, conflict registry, coverage matrix). Runs a bundled deterministic engine: adapts each query to per-database syntax (never copies one query verbatim to every database), normalizes DOI/title/authors/year/venue across databases with CJK-aware tokenization, merges duplicates by exact DOI plus title/author/year fuzzy matching under a pre-declared policy, registers field conflicts per record instead of silently overwriting, and emits a database x field coverage matrix with single-source records and failure gaps. Every merged record keeps a db->query->raw response->field-source trace chain. Also runs a normal-vs-degraded ablation probe that embeds real measured gain_evidence and efficiency counters into result.json. Use when the task asks to jointly search multiple scholarly databases and deliver a deduplicated, traceable, coverage-explained merged record set.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 databases / raw_hits / dedup_policy / merged_records / dedup_decisions / conflicts / coverage_matrix / dedup_metrics / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **广度优先**：先覆盖任务要求的全部库与全部关键字段（每步一个写盘动作），再做深挖；禁止在单库上耗尽预算导致其余库空白。
4. **以实际文件为准**：不依据库标签/文件名假设响应内容；材料用 `build_skeleton.py` 的内容签名扫描命中。不补造文献：库没返回就是没返回，缺口登记不脑补。
5. **策略事前声明**：`dedup_policy`（标题相似度阈值/年份容差/作者比对/字段优先级）必须在**任何去重匹配之前**写定 basis 与 declared_at，事后不得调参凑结果。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增处理，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定各库响应材料，完成「库注册→检索式适配→合并去重→冲突登记→覆盖矩阵」五段结构化流程，交付一份不重复、字段可用、来源可追溯的联合记录集。绕过服务限制、单库全文阅读、未经授权的数据汇总不在范围。
关键词：查得对（按库适配不机械复制）· 并得净（去重可解释）· 冲突留痕（不静默吞掉）· 溯源有链（库—查询—原始响应—字段来源）。
- 输入：`/input/case.json`（研究问题 + 各库响应材料 + output_contract）、`task.md`。**以实际文件为准。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库。
- 按 Step 0–6 线性推进；脚本分工固定，禁写同一键：build_skeleton 落骨架，dedup_core --apply 只写 merged_records/dedup_decisions/conflicts/coverage_matrix/dedup_metrics 五键，verify_check 只写 self_check/unbacked_numbers/gates/validator_verdict，gain_probe 只写 gain_evidence/efficiency。

## 七步流程

### Step 0 — 自动落骨架与材料清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；对 /input 全部 JSON 做**内容签名扫描**（FIELD_ALIASES + 库签名，不依据文件名），预填 `raw_hits[]`（hit_id 按扫描顺序 H001 起，**此后不得重排**）与 `databases[]` 草稿；生成 /app/work/dedup_policy.json 策略模板。
- 脚本失败时手工兜底：读 case.json 抄 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 库注册、检索式适配与策略声明（1 次响应）
- 完善 `result.databases[]`：每库 `{db_id, db_name, status(queried|failed|limited|skipped), fields_profile, queries[]}`；每条查询 `{query_id, original_query, adapted_query, adaptation_notes, status, raw_count, returned_count, failure_stage(connect|auth|rate_limit|syntax|parse), failure_reason}`。
- **检索式必须按库适配**：各库语法、字段能力、字段名不同，禁止把同一条查询机械复制到所有库（校验器逐条比对 adapted≠original）。
- 填 `raw_hits[]` 每行的 db_id / query_id / raw_ref（指向原始响应片段位置），来源链三要素缺一不可。
- **事前策略声明**：填 `result.dedup_policy` = `{title_similarity_threshold, year_tolerance, require_author_overlap, field_priority, basis, declared_at}`，与 /app/work/dedup_policy.json 同步。**必须在匹配之前完成。**

### Step 2 — 机械去重合并管线（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/dedup_core.py --result /app/output/result.json --apply
```
- 机械执行：字段归一（DOI 去前缀转小写、标题 CJK 逐字分词、作者词元、年份截取）→ DOI 精确匹配 + 标题 Jaccard≥阈值 且年份/作者过关的模糊匹配（并查集划分）→ 按字段优先级合并 → 冲突登记 → 覆盖矩阵 → 写 5 个业务键。
- 引擎自含 CJK 分词回归自测（防 isalpha 汉字陷阱）。跑不了时按 schema 手工填写全部五键，并在 uncertainties 注明"引擎不可用，人工执行"。

### Step 3 — 相关性判断与缺口登记（1-2 次响应）
- 为每条 `merged_records[]` 补 `relevance_basis`（与研究问题的相关性依据）；超出检索范围的记录标注保留原因，不静默丢弃。
- 检查 `conflicts[]`：每处字段冲突 `{record_id, field, values, resolution, basis}`，resolution 按库优先级并保留其余取值备查；`coverage_matrix` 补 not_applicable/失败库说明；`dedup_metrics` 计数与 `attributions[]`（db_unavailable/syntax_mismatch/dedup_ambiguity/metadata_conflict/coverage_gap）如实填写。

### Step 4 — claims 证据链（1 次响应）
- 合并计数（raw_hits_total/merged_records_total/duplicates_merged/single_source_records）、title_fuzzy 相似度在 `claims[].text` 回证；每条合并记录年份在 `claims[].evidence[].quote`（原始响应逐字片段）回证。verify_check 把未回证数字列入 unbacked_numbers 并判 FAIL。
- 结论分级 `result.verdict`：`merged` 全部可得库完成适配查询、划分与引擎一致、冲突全登记；`partially_merged` 部分完成；`not_merged` 关键划分不一致或库大面积失败且 attributions 非空；`cannot_verify` 材料缺口导致无法处理且 material_gaps 非空。运行状态 `run_status` = success/partial/unable_to_determine/refused，非 success 写 reason 与 manual_takeover。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（归一+模糊去重+冲突检测全开）与退化模式（--ablate all 全关），真实数字写进 `result.gain_evidence`：runs[]、delta_normal_minus_degraded、mechanism_to_metric_map、boundaries、failure_conditions。五项指标：机器判定数值位占比 / 引擎-交付一致率 / 去重漏检 / 冲突漏检 / 人工核对条目（+步骤数、追问轮次）。
- `--inject-pollution` 在副本注入静默拆分/删冲突/断来源链等污染：正常模式须抓到（caught_by_normal_mode=true），原文件不动。
- 脚本跑不了时手工写 `gain_evidence` = `{available:false, reason:…}`，不得编数字。退化结果仅用于增益对照，不得当交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- FAIL 则按 problems 逐条修复 → 覆盖写 result.json（保留 gain_evidence/efficiency）→ 重跑。通过后 self_check/gates/unbacked/validator_verdict 已回写，保留勿删。
- 自查三问：每条命中都有库—查询—原始响应链吗？重复判定与冲突都能解释吗？没覆盖的库和字段说清楚了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 业务字段 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": "3.x", "packages": "stdlib-only"},
    "databases": [{"db_id": "crossref", "status": "queried", "queries": [{"query_id": "q1", "original_query": "...", "adapted_query": "...", "status": "queried", "failure_stage": null, "failure_reason": null}]}],
    "raw_hits": [{"hit_id": "H001", "db_id": "crossref", "query_id": "q1", "raw_ref": "文件 :: 路径", "doi": "...", "title": "...", "authors": [], "year": 2021, "venue": "..."}],
    "dedup_policy": {"title_similarity_threshold": 0.82, "year_tolerance": 1, "require_author_overlap": true, "field_priority": [], "basis": "...", "declared_at": "step1"},
    "merged_records": [{"record_id": "R001", "sources": [{"hit_id": "H001", "db_id": "crossref"}], "year": 2021, "relevance_basis": "...", "conflicts": [], "arbitration": null}],
    "dedup_decisions": [{"pair": ["H001", "H002"], "method": "doi_exact|title_fuzzy|manual", "similarity": 1.0, "reason": "..."}],
    "conflicts": [{"record_id": "R001", "field": "year", "values": {}, "resolution": "...", "basis": "..."}],
    "coverage_matrix": {"crossref": {"doi": "covered|missing", "...": "..."}},
    "dedup_metrics": {"raw_hits_total": 0, "merged_records_total": 0, "duplicates_merged": 0, "single_source_records": 0},
    "attributions": [{"attribution": "db_unavailable|syntax_mismatch|dedup_ambiguity|metadata_conflict|coverage_gap", "evidence": "..."}],
    "steps": [{"step": "step1", "action": "...", "command": "...", "output_ref": "...", "status": "done"}],
    "run_status": {"state": "success|partial|unable_to_determine|refused", "reason": "...", "manual_takeover": []},
    "verdict": "merged | partially_merged | not_merged | cannot_verify", "verdict_basis": "一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 ..."}
  },
  "claims": [{"claim_id": "k1", "text": "...", "kind": "reported|inferred", "source_id": "...", "location": "...", "evidence": [{"paragraph_id": "...", "quote": "原始响应逐字片段"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "..."},
  "changelog": [], "self_check": [{"item": "...", "template_value": "...", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "result_readable", "state": "enforced|skipped_not_provided|not_found|unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. adapted_query 为空或与 original 相同（机械复制）；查询状态/失败阶段枚举非法；failed 无 failure_reason。
2. raw_hits 来源链断裂（db_id 不在注册表 / query_id 不在该库 / raw_ref 空）。
3. dedup_policy 缺失、无 basis/declared_at、阈值非法；title_fuzzy 声称相似度与引擎复算差超 ±0.05。
4. raw_hit 重复归入多条记录或未归入任何记录；合并划分与引擎复算不一致（人工仲裁 arbitration=manual 的记录除外，保留仲裁入口）。
5. 引擎检出冲突未登记；覆盖矩阵与引擎复算不一致；dedup_metrics 计数与引擎复算不符。
6. 计数/相似度无 claim text 回证、年份无 quote 回证 → unbacked 计入 FAIL；verdict=not_merged 无 attributions / cannot_verify 无 material_gaps。
7. environment 缺 python_version；steps 为空或全无 command；闸门非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**），可本地自测整条链路：
```bash
python3 scripts/dedup_core.py --result examples/example-result.json   # 引擎 CJK/DOI 自测
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 某库响应缺失/限流/超时 | 查询 status=failed + failure_stage + failure_reason，coverage_matrix 标注缺口，attributions 记 db_unavailable，verdict 照实 |
| 字段缺失或语义不等价 | field_sources 记实际来源库；缺失与 unknown 区分；系统性缺失字段写入 uncertainties |
| 去重拿不准（阈值边缘） | dedup_decisions method=manual + reason，merged_records 标 arbitration=manual，保留人工仲裁入口 |
| 响应格式异常/编码错误 | raw_hits 照常登记 + raw_ref 指向原始片段，冲突/缺口登记，不脑补字段 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 检索在组织方提供的本地响应材料上进行：不发起真实网络请求、不绕过服务限制、不装 pip 依赖（stdlib-only）。
- 去重策略阈值是本技能事前声明（案例未给时按保守值设定并注明）；人工仲裁记录机器不复算。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
