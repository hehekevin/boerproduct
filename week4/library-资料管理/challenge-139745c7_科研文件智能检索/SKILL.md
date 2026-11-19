---
name: sci-file-retrieval
description: Scientific research file intelligent retrieval skill (retrieval-plan declaration / full-coverage per-file judgment / verbatim in-file evidence quotes / re-computable relevance ranking / empty-result and restricted-file registries). For each natural-language request it declares a retrieval plan (keywords, synonyms, metadata filters, content terms, requirement mapping and pre-declared three-factor weights), judges every query-file pair as hit/pending/no_hit with matched terms traced to the declared vocabulary, quotes verbatim in-file evidence with location, re-computes a deterministic fused ranking per query, and registers zero-hit queries and permission-restricted or text-less files for follow-up. Verify_check mechanically re-scores rankings, back-checks every quote against the file content in case.json and the claims chain, and re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency counters into result.json. Use when the task asks to locate relevant research files across a file library from natural-language needs, with traceable, independently re-verifiable hits and honest failure registries.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 hits / ranking / coverage / restricted_files / no_result_queries / pending_review / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全记录覆盖**：每个 (query, file) 判定对都必须逐条判定（judged=true 或写明 pending_reason），禁止只报前几条命中就收尾；无文本层/受限/缺失的文件登记 pending 或 restricted_files，不脑补、不跳过。
4. **不编造**：evidence_quote 必须逐字摘自该文件在 case.json 中的实际内容并附位置；matched_terms 必须来自 query_plan 声明词表；本方分数必须来自 score_rank 实际输出；对不上就登记，不改证据凑结论。
5. **口径事前声明**：query_plan（每个需求的 keywords/synonyms/metadata_filters/content_terms + requirement_mapping + 三因子权重，合计=1.0）必须在**任何排序之前**写定（declared_at），之后禁止调整；过滤条件是硬约束，条件无法满足时如实报告而不是放宽。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定资料库（文件清单 + 内容摘要/元数据，通常为真实文件 + 少量受限/无文本层/版本副本夹具）与自然语言检索需求，完成**检索式构建、逐文件命中判定、逐字证据引用、可复算相关性排序、空结果与受限登记**。开放网络文献检索、全文精读、存储权限建设不在范围；检索无结果、权限受限、扫描件无文本层照实登记，不补造文件。
关键词：找得准（检索式与需求映射有据）· 排得稳（权重事前声明、平局有规则）· 引得实（证据逐字出自原文）· 登记全（空结果/受限/待定不静默）。
- 输入：`/input/case.json`（资料库 + 检索需求 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。词表匹配用子串/集合运算，**不用 str.isalpha 分词**（汉字会被误判）。

## 七步流程

### Step 0 — 自动落骨架与资料库/需求清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（files/documents/library/queries/questions 等，含一层嵌套）提取资料库清单与检索需求；预填 `result.hits[]`（每个 query×file 对，默认 pending）；生成 `/app/work/query_plan.json` 检索式台账模板。
- 脚本失败时手工兜底：读 case.json 抄文件清单与需求清单，手写骨架（键一个不缺）。

### Step 1 — 检索式构建与打分口径（1 次响应，排序前完成）
- **逐需求声明检索式**：`result.query_plan.per_query[]` = `{query_id, keywords, synonyms, metadata_filters, content_terms, requirement_mapping}`；requirement_mapping 一句话写明词面锚点/内容词/过滤条件如何覆盖需求；声明的 metadata_filters 是硬约束。
- **事前声明权重**：`result.query_plan.scoring` = `{weights:{term_match, metadata_match, content_match}（合计=1.0）, tie_break, normalization, declared_at}`，同步写 /app/work/query_plan.json。**声明后禁止调整。**

### Step 2 — 逐对判定（1-2 次响应，广度优先）
对 `result.hits[]` 中**每一条** (query, file) 对，缺一不可：
- `label` ∈ hit/pending/no_hit：hit 必须有 `matched_terms`（每项都在该需求声明词表内）+ `evidence_quote`（逐字摘自该文件 case.json 内容）+ `evidence_location`（章节/字段/行）；声明了 metadata_filters 时必须 `filters_applied` 非空且为声明子集；no_hit 必须写 `no_match_reason`；pending 必须写 `pending_reason`（无文本层/权限受限/内容缺失）。
- `relevance` ∈ high/medium/low；`confidence` ∈ high/medium/low；`rationale` 一句话写明命中依据。
- `factors` = {term_match, metadata_match, content_match}（0-1，仅 hit 填）。
- **版本/重复**：改名副本、修订版 → 旧版 hit 的 `duplicate_of` 指向新版 hit_id，在 `result.conflicts[]` 登记 `{item_ids, kind: version_superseded|duplicate, resolution: merged|escalated, evidence}`；escalated 的必须同时进 pending_review。
- **受限文件**：restricted=true 或无读取权限 → 照实 pending + 登记 `result.restricted_files[]`（含 reason 与 needed_action），不脑补内容。

### Step 3 — 机械排序（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/score_rank.py --result /app/output/result.json [--k 10]
```
- 按事前权重机械复算 fused_score（保留 4 位小数），按查询产出 `result.ranking.per_query[]`（ordered_hits / ties / top_k / k_value）与 hits[].fused_score、hits[].rank（查询内名次）；平局规则（fused_score 降序 → content_match 降序 → hit_id 升序），同分并列组全部记入 ties。
- no_hit/pending 条目不参与排序。脚本失败时手工兜底：按同一公式手算并在 steps 注明「手算」，事后仍须重跑脚本核对。

### Step 4 — 证据链与登记（1 次响应）
- **claims 证据链**：每个 hit/pending 条目在 `claims[]` 各有一条 `{claim_id, text, kind: reported|inferred, source_id=hit_id, location, evidence:[{paragraph_id, quote}]}`；text 须含「命中依据 + 原文证据说明 + fused_score 数值」。**数字逐字回证**：evidence_quote 必须出现在对应 quote 里、fused_score 数字必须出现在 claim text/quote 里（空白归一化后子串匹配），未回证数字列入 unbacked_numbers 并判 FAIL。
- `result.no_result_queries[]`：**每个零命中查询**登记 `{query_id, reason, suggestion}`（空结果登记，绝不放宽条件凑命中）。
- `result.coverage`：total_pairs / judged_pairs / hit / pending / no_hit / ratio / per_query，与实际条目一致。
- 结论分级 `result.verdict`（verdict_basis 一句话写依据）：`searched` 全部逐条判定且覆盖完整；`partially_searched` 部分判定；`not_searched` 未产生有效判定；`cannot_verify` 材料缺口导致无法判定且 material_gaps 非空。
- 运行状态 `result.run_status` = `{state, reason, manual_takeover[]}`，`state` ∈ success|partial|unable_to_determine|refused；非 success 必须写 reason 与人工接管位置。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭检索式一致性 / 排序复算 / 证据回证 / 登记完备），把**真实数字**写进 `result.gain_evidence`：`runs[]`、`delta_normal_minus_degraded`、`mechanism_to_metric_map`、`boundaries`、`failure_conditions`。
- 五项对照指标：检索式无据漏检数 / 排序失据漏检数 / 证据缺失漏检数 / 登记漏报数 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- 同时写 `result.efficiency`（墙钟、字节、检查项数、判定对数、人工条目、追问轮次 + `reproduce` 复现命令）；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- `--inject-pollution` 在**副本**上注入污染（hit 无词表依据 / 篡改分数 / 清空登记 / 清空 claims）做反例自测：正常模式须抓到（`caught_by_normal_mode=true`），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence` = `{available:false, reason:"…"}` 与 `efficiency` = `{available:false, reason:"…"}`，不得编数字。
- 退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每个 (query, file) 对都有判定或待复核吗？每个 hit 都能回溯到词表与原文逐字证据吗？空结果、受限、待定都登记了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "library": {"root": "…", "total_files": 8, "files": [{"file_id": "F01", "source_ref": "files[0]", "title": "…", "content_available": true, "metadata": {}, "restricted": false, "restricted_reason": null}]},
    "queries": [{"query_id": "Q01", "question": "自然语言需求", "source_ref": "queries[0]"}],
    "query_plan": {"scoring": {"weights": {"term_match": 0.4, "metadata_match": 0.2, "content_match": 0.4}, "tie_break": ["fused_score 降序", "content_match 降序", "hit_id 升序"], "normalization": "…", "declared_at": "step1"}, "declared_at": "step1", "per_query": [{"query_id": "Q01", "keywords": ["…"], "synonyms": ["…"], "metadata_filters": ["project:proj-A"], "content_terms": ["…"], "requirement_mapping": "…"}]},
    "hits": [{"hit_id": "H001", "query_id": "Q01", "file_id": "F01", "file_ref": "files[0]", "label": "hit", "relevance": "high", "matched_terms": ["…"], "filters_applied": ["project:proj-A"], "evidence_quote": "逐字摘录", "evidence_location": "章节/字段", "confidence": "high", "rationale": "…", "factors": {"term_match": 1.0, "metadata_match": 1.0, "content_match": 1.0}, "fused_score": 1.0, "rank": 1, "duplicate_of": null, "restricted": false, "pending_reason": null, "no_match_reason": null, "judged": true}],
    "ranking": {"per_query": [{"query_id": "Q01", "ordered_hits": ["H001"], "ties": [], "top_k": ["H001"], "k_value": 1}], "weights": {}, "tie_break": [], "declared_at": "step1"},
    "coverage": {"total_pairs": 24, "judged_pairs": 24, "hit": 8, "pending": 6, "no_hit": 10, "ratio": 1.0, "per_query": {"Q01": {"total": 8, "hit": 4, "pending": 2, "no_hit": 2}}},
    "restricted_files": [{"file_id": "F06", "reason": "权限受限", "needed_action": "申请授权后补检"}],
    "no_result_queries": [{"query_id": "Q03", "reason": "…", "suggestion": "…"}],
    "pending_review": [{"hit_id": "H005", "reason": "…", "needed_action": "…"}],
    "conflicts": [{"item_ids": ["H003", "H004"], "kind": "version_superseded", "resolution": "merged", "evidence": "…"}],
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "searched | partially_searched | not_searched | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "命中依据+证据+分数", "kind": "reported | inferred", "source_id": "H001", "location": "hits[0]", "evidence": [{"paragraph_id": "files[0].content", "quote": "文件内容原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. label / relevance / confidence / run_status.state / verdict 枚举非法。
2. hit 无 matched_terms 或词表外用词（检索式无据）；hit 无 evidence_quote；声明过滤未执行或越界；no_hit 无 no_match_reason；pending 无 pending_reason；查询未声明检索式。
3. fused_score 与事前权重机械复算不符；ordered_hits 与复算顺序不一致；查询内名次不连续；权重合计≠1.0 或 declared_at 为空。
4. 已判定条目 rationale 为空；hit 的 evidence_quote 未在 case.json 该文件内容中逐字找到；hit/pending 证据在 claims 无逐字回证；fused_score 数字无回证 → unbacked_numbers 判 FAIL。
5. pending 未登记进 pending_review；零命中查询未登记 no_result_queries（空结果漏登记）；受限文件未登记 restricted_files；duplicate_of 未在 conflicts 登记；escalated 未进待复核。
6. coverage 汇总与实际条目不符；verdict 与判定进度矛盾；steps 为空或无可执行 command。
7. 闸门（case_contract / query_plan_ledger / case_content_verbatim / ranking_recompute / score_rank_output）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，文件内容均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/score_rank.py --result examples/example-result.json --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --query-plan /tmp/wk/query_plan.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 检索无结果 | 该查询全部 no_hit，登记 no_result_queries（含 reason/suggestion），绝不放宽条件凑命中 |
| 文件无内容/无文本层扫描件 | pending + 登记 pending_review（needed_action=OCR 后补检），不猜内容 |
| 文件权限受限 | pending + 登记 restricted_files（含 reason），绝不脑补受限内容 |
| 重名/修订版/副本 | duplicate_of 指向最新版 + conflicts 登记 merged；无法确认同一性则 escalated 进待复核 |
| 过滤条件无法满足 | 照实报告（no_hit + reason），不放宽声明过的硬约束 |
| 大量同分 | score_rank 把并列组记入 ties，按 tie_break 规则破平并在 ranking 可见 |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅处理输入资料库内文件：不做开放网络检索、不全文精读、不做存储权限建设。
- term_match/metadata_match/content_match 的归一化口径是本技能在 query_plan 事前声明的设定（论文/平台未给定时按量级保守设定并写明），不冒充外部标准。
- case.json 未提供文件内容时，逐字回证退化为 claims 链回证（gate 记 not_found 并如实标注）。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
