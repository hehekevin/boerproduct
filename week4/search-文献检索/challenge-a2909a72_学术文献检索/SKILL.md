---
name: lit-search-pro
description: Academic literature search skill (multi-round query planning / keyword expansion / database combination / dedup / source traceability). Decomposes a research question into a multi-round query plan, mechanically expands keywords (synonyms, abbreviations, variants, related terms), records every database query attempt with status and result counts, clusters duplicate records via normalized title+DOI and keeps full source traceability (every paper carries source_db + matched_queries + relevance rationale), registers gaps (empty results, conflicts, missing metadata, access or rate-limit issues), and emits a 4-level coverage verdict with a claims evidence chain whose years and scores are verified verbatim against source snippets. Also runs a normal-vs-degraded mechanism ablation probe embedding real measured gain_evidence and efficiency counters into result.json. Use when the task asks to search open scholarly databases for literature around a research question with traceable candidates, screening evidence, dedup and gap disclosure.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 query_plan / keyword_expansion / queries_executed / databases_used / papers / dedup / coverage / gaps / steps / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **广度优先**：先覆盖全部查询轮次与全部候选文献（每步一个写盘动作），再做深挖；禁止在单条文献上耗尽预算导致其余项空白。
4. **不编造文献**：每条文献的元数据必须来自 case.json 材料或实际检索响应的逐字摘录；检索不到就登记 gaps，绝不补造标题、作者、年份或 DOI；元数据缺失逐条登记 papers[].metadata_missing。
5. **来源可追溯**：每条候选必须带 `source_db`（哪个库）+ `matched_queries`（哪次查询命中）+ `rationale`（为何相关）；三者缺一即不可追溯，verify_check 判 FAIL。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增处理，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：围绕一个科研问题，在开放学术数据库上完成「检索规划 → 关键词扩展 → 多库执行 → 去重 → 来源登记 → 遗漏分析」的结构化闭环。单篇论文精读、全文解析、写作润色、资料库整理不在范围；无网络时按 case.json 提供的检索响应材料执行同一流程。
关键词：规划好（多轮不漏方向）· 召回全（同义词/缩写都试）· 判得准（相关性有依据）· 查得到（每条可回溯）。
- 输入：`/input/case.json`（科研问题 + 检索响应材料 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–5 线性推进，禁止分支回环。

## 六步流程

### Step 0 — 自动落骨架与材料清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；扫描 /input 建材料清单（检索响应材料预填 `queries_executed[]` 计划位）；生成 `/app/work/query_plan.json` 工作模板。
- 脚本失败时手工兜底：读 case.json 抄 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 查询规划与关键词扩展（1 次脚本调用 + 1 次响应复核）
```bash
python3 /skills/weekly-skill/scripts/plan_queries.py --case /input/case.json \
  --result /app/output/result.json --work-dir /app/work
```
- 自动拆解科研问题为多轮查询计划（round1 核心术语 / round2 扩展术语 / round3 相关与上位术语 / round4 补漏与验证），并机械扩展关键词（复数、连字符变体、缩写展开、缩写反推、相关概念），写入 `result.query_plan[]` 与 `result.keyword_expansion[]`（键分工：仅此脚本写这两个键）。
- 人工复核：从 case.json 材料中确认专业术语、缩写（如 MPNN）、跨语言表达是否已被覆盖；漏的补进 keyword_expansion（kind 标 synonym/abbreviation/related_term/translation/variant），每个扩展带 source_basis（规则名或材料位置）。
- 数据库组合：按 case.scope.databases 或材料实际来源确定 `result.databases_used[]`（name/status=accessible|rate_limited|unavailable|not_tried/queries/results_count）。

### Step 2 — 检索执行与逐条登记（1-2 次响应）
- 逐轮执行 query_plan，把每次尝试登记进 `result.queries_executed[]`：`{query_id, round, query, database, result_count, status=executed|failed|skipped, notes}`；空结果也是执行记录，登记后同步写 gaps（kind=empty_result）。
- 对每条命中文献登记 `result.papers[]`：`{paper_id, title, authors, year, venue, doi, url, source_db, matched_queries[], relevance_score, rationale, duplicate_of, metadata_missing[]}`。
- **元数据逐字摘录**：title/year/doi 必须能在来源材料中逐字找到（claims[].evidence[].quote 存原文）；对不上就写 metadata_missing，不猜测。

### Step 3 — 去重聚类与覆盖统计（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/dedup_records.py --result /app/output/result.json \
  --work-dir /app/work
```
- 机械去重：标题归一化（大小写/标点/空白）+ DOI 归一化聚类，重复条目标 `duplicate_of`（保留元数据更全者为正本）。
- 写 `result.dedup`（criteria/clusters_found/removed_duplicates/dedup_rate）与 `result.coverage`（total_raw/total_unique/traceable_items/traceability_ratio/per_db_counts）（键分工：仅此脚本写这两个键）。
- 每次去重决定登记进 changelog；无法判定是否重复的（同名不同 DOI）不合并，登记 uncertainties.conflicts。

### Step 4 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑多遍：正常模式（全部机械校验开）与退化模式（--ablate 分别关闭回证/去重/追溯），把**真实数字**写进 `result.gain_evidence`：`runs[]`、`delta_normal_minus_degraded`、`mechanism_to_metric_map`（机制→指标映射）、`boundaries`（边界）、`failure_conditions`（失效条件）。
- 对照指标：来源可追溯率 / 去重漏检数 / 回证漏检数 / 需人工核对条目数 / 查询覆盖数 / 关键词扩展数 / 步骤数 / 追问轮次。数字全部来自实跑，**不得手填或臆造**。
- 同时写 `result.efficiency`（墙钟、字节、检查项数、文件数 + `reproduce` 命令）；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- `--inject-pollution` 在**副本**上注入污染（注入未标记重复文献、清空 matched_queries、篡改年份）做反例自测：正常模式须抓到，原 result.json 不被改动。
- 脚本跑不了时手工写 `gain_evidence` = `{available:false, reason:"…"}` 与 `efficiency` 同理，不得编数字。退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 5 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- 两个脚本退出码恒为 0；**判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- verify_check 通过后把三元组自检、闸门状态与 unbacked 清单回写进 result.json（键 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`），保留勿删。
- 自查三问：每条文献都能回溯到库+查询+依据吗？重复的标了吗、统计对得上吗？检索不到的都登记 gaps 了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["某数据库响应材料未随案例提供"],
    "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": "科研问题原文", "scope": {"years": "2019-2024", "databases": ["Crossref"]},
    "query_plan": [{"round": 1, "query": "graph neural network molecular property", "databases": ["Crossref"], "purpose": "核心术语首查", "status": "planned"}],
    "keyword_expansion": [{"term": "MPNN", "kind": "abbreviation", "source_basis": "material m1"}],
    "queries_executed": [{"query_id": "q1", "round": 1, "query": "…", "database": "Crossref", "result_count": 3, "status": "executed", "notes": ""}],
    "databases_used": [{"name": "Crossref", "status": "accessible", "queries": 3, "results_count": 5, "note": ""}],
    "papers": [{"paper_id": "p1", "title": "…", "authors": "…", "year": 2019, "venue": "…", "doi": "10.xxxx/yyy",
                "source_db": "Crossref", "matched_queries": ["q1"], "relevance_score": 0.9, "rationale": "为何相关",
                "duplicate_of": null, "metadata_missing": []}],
    "dedup": {"criteria": "归一化标题+归一化DOI", "clusters_found": 1, "removed_duplicates": 1, "dedup_rate": 0.2, "note": ""},
    "coverage": {"total_raw": 5, "total_unique": 4, "traceable_items": 5, "traceability_ratio": 1.0, "per_db_counts": {}},
    "gaps": [{"gap_id": "g1", "kind": "empty_result | conflict | missing_metadata | access_denied | rate_limited | suspected_miss",
              "description": "…", "follow_up": "…"}],
    "steps": [{"step": "step2", "action": "执行 round1 查询并登记", "command": "python3 /skills/weekly-skill/scripts/dedup_records.py --result /app/output/result.json", "output_ref": "queries_executed[0]", "status": "done"}],
    "run_status": {"state": "partial", "reason": "…", "manual_takeover": ["…"]},
    "verdict": "complete | partial | empty | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 .../gain_probe.py ..."}
  },
  "claims": [{"claim_id": "k1", "text": "来源摘录+本方判断+差异说明", "kind": "reported | inferred", "source_id": "材料或文献 id", "location": "papers[0] / m1", "evidence": [{"paragraph_id": "m1", "quote": "来源原文逐字摘录"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "result_readable", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. kind / status / verdict / run_status.state / gap kind / database status 枚举非法；papers 行缺 title 或 source_db。
2. 不可追溯：matched_queries 或 source_db 或 rationale 为空 → trace FAIL；traceability_ratio 与实际不符。
3. 去重不一致：duplicate_of 指向不存在的 paper_id / 指向自身 / 正本也标了 duplicate_of；dedup.removed_duplicates 与实际标记数不符；dedup_rate 与 removed/total_raw 不符。
4. coverage 不一致：total_raw ≠ papers 行数；total_unique ≠ 未标重复行数；per_db_counts 与 papers[].source_db 不符。
5. 数字逐字回证：papers[].year、relevance_score 及 dedup/coverage 计数须在 claims quote（来源侧）或 claim text（本方计算侧）中回证，未回证列入 unbacked_numbers 判 FAIL；**DOI/URL/ID 等标识符内嵌数字不参与回证（防误报），区间端点（如 2019-2024）逐端回证**。
6. 有命中文献但 claims 为空；papers 为空但 gaps 为空（空检索必须登记遗漏）；verdict=empty 但 papers 非空；verdict=complete 但 traceability_ratio≠1.0；verdict=cannot_verify 但 material_gaps 空。
7. query_plan / queries_executed 为空；steps 全无 command；environment 缺 python_version；gain_evidence/efficiency 缺失或闸门未 enforced 时 warn「下游不得宣称已核对」。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/plan_queries.py --case examples/example-case.json --result /tmp/skel.json --work-dir /tmp/wk
python3 scripts/dedup_records.py --result /tmp/skel.json --work-dir /tmp/wk
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 数据库响应材料缺失/不可访问 | 登记 material_gaps，databases_used 状态标 unavailable/not_tried，verdict 按实际降级 |
| 某次查询空结果 | queries_executed 照记 result_count=0，gaps 登记 empty_result，不补造文献 |
| 接口限流/权限不足 | gaps 登记 rate_limited/access_denied，databases_used 状态如实标，follow_up 写后续动作 |
| 元数据缺失 | papers[].metadata_missing 逐条登记；year 缺失则该行不参与回证计数 |
| 疑似重复但不确定 | 不合并，uncertainties.conflicts 登记，gaps 登记 conflict |
| 算力/时间不足 | 保留已完成轮次，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 无实时网络检索能力：检索执行依赖 case.json 提供的检索响应材料；无网络时流程照走，执行记录以材料为准，不虚构"已在线检索"。
- 关键词扩展是规则驱动的保守扩展（复数/连字符/常见缩写表/相关概念），不覆盖领域私有缩写；Agent 应结合材料人工补充并标注 source_basis。
- 相关性分数是规则+判断的参考排序，不是权威引用计数；排序依据写在 rationale，可复核。
- 增益对照是本校验层正常 vs 退化多模式对照，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按约定批量（每轮 3 条）折算，是估计量；原始计数 manual_review_items 一并落盘。
