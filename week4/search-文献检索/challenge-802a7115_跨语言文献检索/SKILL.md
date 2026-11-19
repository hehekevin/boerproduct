---
name: xling-lit-recall
description: Cross-language literature retrieval skill (evidence-backed term map / per-language query building / language & version identification / multi-language version merging / language coverage matrix / translation-ambiguity registry). Builds a terminology map with verbatim evidence (synonyms, abbreviations, transliterations, localized names), mechanically expands per-language query strings via build_queries.py, judges every candidate record's body language (script-based detection support via lang_detect.py using explicit Unicode ranges, never isalpha) and version (original/translation/abstract_only/bilingual), merges multi-language views of the same work into clusters keeping the original-language record canonical, keeps the per-language coverage matrix mechanically consistent with issued queries and judged records, registers translation ambiguities and pending items for human review, and re-scores a deterministic ranking on weights declared before sorting. verify_check.py re-runs termmap/cluster/coverage/pending/evidence checks; gain_probe.py runs a normal-vs-degraded ablation with measured counters; every failure path exits 0 with honest JSON verdicts. Use when the task asks to retrieve literature across languages, align terminology with original paper wording, deduplicate language versions, and keep every retrieval decision reviewable.
---
## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 term_map / queries / items / clusters / ambiguities / coverage / coverage_matrix / pending_review / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全记录覆盖**：候选集**每一条**记录（一个语种视 = 一条）都必须逐条判定语言/版本/相关性（judged=true 或写明 pending_reason），禁止只处理前几条就收尾；缺元数据、语种不确定、疑似重复照实登记，不脑补、不跳过。
4. **不编造**：term_map 每条映射必须附逐字证据（evidence_quote + 位置）；evidence_quote 必须逐字摘自案例实际材料；本方分数必须来自 score_rank 实际输出；术语对不上、语种判不准就登记，不改证据凑结论。
5. **口径事前声明**：rubric（三项权重 + 归一化规则 + 平局规则）必须在**任何排序之前**写定（declared_at），之后禁止调整；目标语种清单（research_question.target_languages）同样事前声明，不得事后增删凑覆盖率。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定研究问题、目标语种与候选记录集（同一研究的多语种视图：原文、出版方全文译本、仅英文摘要、精确重复等），完成**术语映射有据、逐语种检索式构建、语言/版本判定、跨语言版本归并、语言覆盖矩阵一致、翻译歧义待复核登记**。整篇翻译润色、数据库实时抓取、未经授权的跨境获取不在范围；检索无结果、术语无对应译法、语种识别不确定照实登记，不补造文献。
关键词：映射有据（每条术语映射带逐字证据）· 归并对（同一研究多语种版本并入簇、保留原文版为正本）· 覆盖一致（矩阵数字与检索式/记录机械对账）· 歧义登记（词面对应语义存疑的全部进待复核）。
- 输入：`/input/case.json`（研究问题 + 候选记录 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–7 线性推进，禁止分支回环；**中文处理禁用 isalpha**（汉字 isalpha()==True），一律用显式字符类或 \w。

## 八步流程

### Step 0 — 自动落骨架与候选清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键提取候选记录预填 `result.items[]`；生成 /app/work/rubric.json 打分口径模板。
- 脚本失败时手工兜底：读 case.json 抄候选清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 研究问题、目标语种、术语表与打分口径（1-2 次响应，排序前完成）
- 填 `result.research_question`（question/scope/**target_languages**/time_range）；目标语种清单事前声明，之后禁止增删。
- 填 `result.term_map[]`：每条 `{entry_id, source_term, source_lang, target_term, target_lang, variant_type∈synonym|abbreviation|transliteration|localized|variant_spelling, evidence_quote, evidence_location, confidence}`。**术语映射有据**：evidence_quote 逐字摘自案例材料（候选标题/摘要/正文），evidence_location 注明位置；同一词面多读法（缩写跨学科歧义、音译多解）同时登记进 `result.ambiguities[]`。
- **事前声明 rubric**：`result.rubric` = `{weights:{relevance,crosslang,recency}（合计=1.0）, tie_break, normalization, declared_at}`，同步写 /app/work/rubric.json。normalization 约定：relevance direct=1.0/indirect=0.5/irrelevant=0.0；crosslang 按 work_cluster 语言版本视数/2 封顶 0-1；recency 按 (year−起始年)/跨度 截断 0-1。**声明后禁止调整。**

### Step 2 — 逐语种检索式机械构建（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_queries.py --result /app/output/result.json
```
- 从 term_map 机械展开：每语种汇集全部术语（源词+目标词，去重）→ `"词1" OR "词2"`，写 `result.queries[]`（query_id/language/query_string/built_from 引用 entry_id）。术语映射为空时照实告警，不虚构检索式。

### Step 3 — 逐条判定：语言、版本、相关性（1-2 次响应，广度优先）
对 `result.items[]` 中**每一条**候选记录，缺一不可：
- `body_language`（ISO 码或 unknown/other）+ `language_evidence`（字形/刊名/署名依据，可调 `lang_detect.py` 辅助）；`version` ∈ original/translation/abstract_only/bilingual/unknown + `version_evidence`；
- `relevance` ∈ direct/indirect/irrelevant；`label` ∈ keep/pending/exclude：keep 必须命中 ≥1 条纳入标准（criteria_hit），exclude 必须命中 ≥1 条排除标准（excluded_by），pending 必须写 pending_reason；
- `evidence_quote` 逐字摘自该条实际材料 + `evidence_location`；`rationale` 写明命中哪条标准、术语是否与原文用词一致；
- **跨语言归并**：同一研究的多语种视图 → `work_cluster_id` + `duplicate_of` 指向保留的**原文版正本**，在 `result.clusters[]` 登记 `{cluster_id, member_ids, canonical_id, basis∈doi|title_translation|exact_duplicate, merge_evidence, resolution: merged|escalated}`；确认不了同一性则 escalated 进待复核。**精确重复（同 DOI 同题）必须被归并，不得重复计数。**
- **翻译歧义**：词面对应但语义存疑的高风险命中 → `result.ambiguities[]` 登记 `{ambiguity_id, surface_form, langs, readings, resolved_as, resolution∈resolved|needs_review, related_entries}`；needs_review 的必须进 pending_review。

### Step 4 — 机械排序（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/score_rank.py --result /app/output/result.json [--k 10]
```
- 按事前 rubric 权重机械复算 fused_score（保留 4 位小数）并按平局规则（fused_score 降序 → recency 降序 → item_id 升序）产出 `result.ranking` 与 items[].fused_score、items[].rank；同分并列组全部记入 ties。k 默认取 keep 条目数。
- keep/pending 条目填 factors（三项 0-1）；exclude 条目 factors 留空不参与排序。

### Step 5 — 覆盖矩阵、待复核与证据链（1 次响应）
- `result.coverage_matrix[]`：**每个目标语种一行** `{language, queries_issued, records_found, kept, pending, excluded, gap_note}`；数字必须与 result.queries、result.items 机械一致；某语种 queries_issued=0 或无结果必须写 gap_note，不静默漏语种。
- `result.coverage`（汇总）+ `result.pending_review[]`：每个 label=pending 条目与每个 needs_review 歧义、escalated 簇成员登记 `{item_id, reason, needed_action}`。
- **claims 证据链**：每个 keep/pending 条目在顶层 `claims[]` 各有一条 `{claim_id, text, kind, source_id, location, evidence:[{paragraph_id, quote}]}`；text 须含「语种/版本判定依据 + 术语对齐说明 + fused_score 数值」。**数字逐字回证**：fused_score 数字必须出现在 claim text/quote 里；标识符内嵌数字（如 V01 的 01）不作为回证命中，区间端点（如 0.91-0.95）保留；未回证数字列入 unbacked_numbers 并判 FAIL。
- 结论分级 `result.verdict`（verdict_basis 一句话写依据）：`retrieved` 全部逐条判定且覆盖完整；`partially_retrieved` 部分判定；`not_retrieved` 未产生有效判定；`cannot_verify` 材料缺口导致无法判定且 material_gaps 非空。`result.run_status` = `{state, reason, manual_takeover[]}`，非 success 必须写 reason。

### Step 6 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（五组机械校验全开）与退化模式（--ablate all：关闭术语映射校验/跨语言归并/覆盖矩阵/证据回证/待复核登记），把**真实数字**写进 `result.gain_evidence`（runs / delta_normal_minus_degraded / mechanism_to_metric_map / boundaries / failure_conditions）。
- 同时写 `result.efficiency`（墙钟、字节、检查项数、条目数 + reproduce 命令）；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- `--inject-pollution` 在**副本**上注入污染（术语映射删证据 / 清 duplicate_of / 篡改覆盖矩阵 / 清空待复核与 claims）做反例自测：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence`/`efficiency` = `{available:false, reason:"…"}`，不得编数字。退化模式结果仅用于增益对照，不得当作交付自检结论。

### Step 7 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：候选记录每一条都判了语种/版本/相关性吗？同一研究的多语种版本都归并进簇了吗？每个目标语种在覆盖矩阵有一行且数字对得上吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"question": "…", "scope": "…", "target_languages": ["en","pt","ja","zh"], "time_range": "…"},
    "criteria": {"inclusion": [{"criterion_id": "IN-01", "text": "…"}], "exclusion": [{"criterion_id": "EX-01", "text": "…"}]},
    "rubric": {"weights": {"relevance": 0.5, "crosslang": 0.3, "recency": 0.2}, "tie_break": ["fused_score 降序", "recency 降序", "item_id 升序"], "normalization": "…", "declared_at": "step1"},
    "term_map": [{"entry_id": "T01", "source_term": "细胞焦亡", "source_lang": "zh", "target_term": "pyroptosis", "target_lang": "en", "variant_type": "synonym", "evidence_quote": "逐字摘录", "evidence_location": "candidates[1].abstract", "confidence": "high"}],
    "queries": [{"query_id": "Q-en-01", "language": "en", "query_string": "\"pyroptosis\" OR \"…\"", "built_from": ["T01"], "status": "built"}],
    "items": [{"item_id": "V01", "source_ref": "candidates[0]", "title": "…", "title_lang": "pt", "body_language": "pt", "language_evidence": "…", "version": "original", "version_evidence": "…", "relevance": "direct", "label": "keep", "criteria_hit": ["IN-01"], "excluded_by": [], "evidence_quote": "逐字摘录", "evidence_location": "candidates[0].abstract", "confidence": "high", "rationale": "…", "factors": {"relevance": 1.0, "crosslang": 1.0, "recency": 0.8}, "fused_score": 0.96, "rank": 1, "work_cluster_id": "W1", "duplicate_of": null, "missing_metadata": [], "pending_reason": null, "judged": true}],
    "clusters": [{"cluster_id": "W1", "member_ids": ["V01","V02"], "canonical_id": "V01", "basis": "doi", "merge_evidence": "…", "resolution": "merged"}],
    "ambiguities": [{"ambiguity_id": "A01", "surface_form": "…", "langs": ["pt"], "readings": ["…"], "resolved_as": "…", "resolution": "needs_review", "related_entries": ["T03"]}],
    "coverage": {"total_candidates": 6, "judged_items": 6, "keep": 3, "pending": 1, "exclude": 2, "versions_merged": 2, "ratio": 1.0},
    "coverage_matrix": [{"language": "en", "queries_issued": 1, "records_found": 3, "kept": 1, "pending": 0, "excluded": 2, "gap_note": null}],
    "pending_review": [{"item_id": "V03", "reason": "…", "needed_action": "…"}],
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "retrieved | partially_retrieved | not_retrieved | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "语种/版本判定+术语对齐+分数", "kind": "reported | inferred", "source_id": "V01", "location": "items[0]", "evidence": [{"paragraph_id": "candidates[0].abstract", "quote": "原文原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. relevance / label / confidence / version / verdict / run_status.state 枚举非法；body_language 未登记（既非目标语种也不在覆盖矩阵）。
2. **术语映射无据**：term_map 条目缺 evidence_quote / 枚举非法 / queries.built_from 引用了不存在的 entry_id。
3. **归并不对**：duplicate_of 未在 clusters 登记 merged/escalated；簇正本与 duplicate_of 不一致；簇成员（非正本）未指回正本；同题同版疑似精确重复未归并；escalated 未进待复核。
4. **覆盖矩阵不一致**：矩阵行集合 ≠ 目标语种 ∪ 已判定记录语种；queries_issued ≠ 该语种检索式数；records_found / kept / pending / excluded 与 items 计数不符；目标语种无检索式又无 gap_note。
5. keep 无 criteria_hit；exclude 无 excluded_by；pending 无 pending_reason 或未登记进 pending_review；needs_review 歧义未进待复核；keep 无 evidence_quote；claims 无逐字回证；fused_score 数字无回证 → unbacked_numbers 判 FAIL。
6. coverage 汇总与实际条目不符；verdict 与判定进度矛盾；steps 为空或无可执行 command；rubric 未事前声明或权重合计≠1.0；fused_score 复算不符或 ranking.ordered_ids 与复算顺序不一致。
7. 闸门（case_contract / rubric_ledger / ranking_recompute / score_rank_output）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，标题摘要均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/build_queries.py --result examples/example-result.json
python3 scripts/score_rank.py --result examples/example-result.json --k 3 --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --rubric /tmp/wk/rubric.json --out /tmp/vc.json && python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 检索无结果 / 候选集为空 | items 空、coverage.total=0、verdict=cannot_verify 或 not_retrieved，绝不补造文献 |
| 术语无对应译法 | 不硬造映射；登记 uncertainties.unverifiable，目标语种检索式降级为核心词并写 gap_note |
| 语种识别不确定 | body_language=unknown + language_evidence 写明依据缺口，进 pending_review |
| 同一论文多语种版本 | duplicate_of + clusters 登记 merged（保留原文版正本）；确认不了同一性则 escalated 进待复核 |
| 词面对应语义存疑（误译风险） | ambiguities 登记 readings，needs_review 进 pending_review，必要时回译复核 |
| 翻译服务失败 / 限额 | 不重试烧预算；受影响语种在 coverage_matrix.gap_note 登记并标 run_status=partial |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |

## 已知限制
- 仅处理输入候选集内记录：不做数据库实时检索、不整篇翻译、不做未经授权的数据抓取；lang_detect.py 只做字形判定与停用词辅助猜测，区分不了同一字形的多门语言（如 pt/es），最终语种判定以 Agent 结合元数据为准。
- crosslang/recency 归一化口径按 rubric 声明的规则计算，口径是本技能设定（论文/平台未给定时按量级保守设定并写明），不冒充外部标准。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。追问轮次按每轮 3 条折算的估计量，原始计数一并落盘。
