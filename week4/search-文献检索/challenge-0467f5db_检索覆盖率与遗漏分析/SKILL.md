---
name: cov-gap-audit
description: Search coverage and missed-literature analysis skill (reference-set freezing / mechanical hit matching / coverage accounting / miss registry with query-level attribution / supplementary-search marginal-gain audit). Freezes the known-reference set as the coverage denominator (never defined by the search results themselves), mechanically matches each reference item against retrieved records via normalized DOI/PMID or title, computes coverage/miss rates with per-item hit status, registers every miss with an actionable category (synonym gap / field narrow / time window / source gap / identifier anomaly) attributed to a concrete query, field and source, audits supplementary searches for real marginal gain (empty new-hits with claimed effectiveness = spinning), and back-traces every rate number through the claims evidence chain. Verify_check mechanically recomputes the denominator and rates, re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency counters into result.json. Use when the task asks to audit how much of a known literature set a search strategy actually found, explain each miss, and verify that supplementary searches really reduce misses.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 reference_set / coverage / miss_registry / supplementary / review / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **分母不许来自检索结果**：coverage 的分母只能是冻结参考集中 ref_status=included 的条目（unavailable/retracted 登记但不入分母）；参考集未冻结（frozen=true + frozen_at）之前不得宣称覆盖率；**绝不以检索结果反推应检文献**。
4. **遗漏逐条登记**：每条 hit_status=miss 的文献必须恰有一条 miss_registry 登记，category ∈ 六类枚举，attribution 落到具体 query_id/field/source_db/reason 且 query_id 必须存在于查询清单——"数据库覆盖不足"式泛泛归因会被判 FAIL；未命中不得当作不相关划掉。
5. **不编造**：evidence_quote 必须逐字摘自实际命中记录/输入并附位置；coverage_rate / miss_rate / post_coverage_rate 数字必须能在 claims 证据链中逐字回证；补检声称有效但新增命中为 0（补检空转）会被判 FAIL；检索无结果就照实写，绝不补造文献。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定研究问题、检索目标与**已知关键文献集合**（参考集，可能夹带撤稿/重复/标识异常条目），完成**覆盖测量、漏检分类登记、补充检索校验与闭环复核**。底层数据库实时接入、全文精读、系统综述正式纳排不在范围；来源超时、元数据缺失、标识冲突照实登记，不补造文献。
关键词：分母冻结（覆盖率口径一致、可独立复算）· 逐条判定（每条已知文献有 hit/miss 状态与证据）· 漏检可归因（落到查询式/字段/来源/时间窗）· 补检不空转（新增命中可验证、停止规则明示）。
- 输入：`/input/case.json`（研究问题 + 参考集 + 查询/检索记录 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与分母台账（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（reference_set/known_set、queries、retrieved_records 等）提取参考集/查询/检索记录预填；生成 `/app/work/coverage_ledger.json` 分母冻结台账。
- 脚本失败时手工兜底：读 case.json 抄参考集与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 冻结参考集与口径声明（1 次响应，覆盖率计算前完成）
- 逐条核对参考集：标识符去重、ref_status 标 included/unavailable/retracted（撤稿、无法获取全文属不可用记录），写明 inclusion_reason；然后置 `reference_set.frozen=true`、`frozen_at`，同步 /app/work/coverage_ledger.json。**冻结后禁止增删参考条目**；补充检索只可能把 miss 变 hit，不改变分母。
- 填 `result.research_question`（question/scope/time_range）与 `result.queries[]`（query_id/query_string/fields/source_db/time_window，缺什么登记什么）；命中判定规则在 coverage.match_rule 声明（标识符精确 → 标题归一化精确 → 人工裁决）。

### Step 2 — 机械命中判定与覆盖率计算（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/coverage_calc.py --result /app/output/result.json --case /input/case.json
```
- 按声明规则逐条比对：DOI/PMID 归一化精确 → matched_by=identifier；标题归一化精确 → matched_by=title；对机械结果有异议可改判 `matched_by=manual`（必须附 evidence_quote 与理由）后用 `--keep-manual` 重跑核对。
- 回写 `result.coverage`（total_reference/included/unavailable/judged/hit/miss/extra_records/coverage_rate/miss_rate）与 items[].hit_status/matched_*/；extra_records = 检索结果中与参考集无关的记录数——检索数量多 ≠ 覆盖好。
- 脚本失败时手工兜底：手写逐条判定与 coverage 汇总并在 steps 注明「手算」。

### Step 3 — 漏检登记与归因审计（1-2 次响应 + 1 次脚本调用）
- 对**每条 miss** 在 `result.miss_registry[]` 登记：`category` ∈ synonym_gap（查询词未覆盖同义表达）/ field_narrow（检索字段限制过窄）/ time_window（时间窗截断）/ source_gap（来源库未收录）/ identifier_anomaly（记录标识异常）/ other（须写明原因）；`attribution` = {query_id, field, source_db, reason} 四项全部非空且 query_id 必须存在于查询清单；`needed_action` 写明补检动作。
- ```bash
  python3 /skills/weekly-skill/scripts/miss_audit.py --result /app/output/result.json --case /input/case.json
  ```
  回写 miss_registry.audit 校验标记；verdict=FAIL 就按 problems 逐条修复。

### Step 4 — 补充检索与边际收益校验（1-2 次响应 + 1 次脚本调用）
- 按遗漏类别设计新查询/新来源（登记 query_id/based_on_category/query_string/source_db/new_hits/rationale）；残余遗漏逐条写 explanation；写明 stop_rule（何时停止补检）。
- ```bash
  python3 /skills/weekly-skill/scripts/supp_check.py --result /app/output/result.json --case /input/case.json
  ```
  机械复算 new_hits_total/marginal_gain/post_coverage_rate；**声称 effective=true 但新增命中为 0 = 补检空转，判 FAIL**；query_string 与原查询实质相同也会被判空转预警。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭分母口径 / 遗漏登记完备 / 补检真实收益 / 证据回证），把**真实数字**写进 `result.gain_evidence`：`runs[]`、`delta_normal_minus_degraded`、`mechanism_to_metric_map`、`boundaries`、`failure_conditions`。
- 五项对照指标：分母/口径违规漏检数 / 遗漏登记漏检数 / 补检空转漏检数 / 证据缺失漏检数 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- `--inject-pollution` 在**副本**上注入领域化污染（篡改覆盖率=1.0 / 清空遗漏登记 / 归因清空 / 补检空转 / 清空 claims）做反例自测：正常模式须抓到（`caught_by_normal_mode=true`），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence` = `{available:false, reason:"…"}` 与 `efficiency` 同理，不得编数字。
- 退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- `review[]`：对命中判定与归因做人工抽检（sampled/agreement_rate），残余遗漏规模与原因写进 residual_explanation。
- 自查三问：分母是冻结参考集吗？每条漏检都能指认到查询式/字段/来源吗？补检的新增命中与残余遗漏都核过账吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"question": "…", "scope": "…", "time_range": "…"},
    "reference_set": {"frozen": true, "frozen_at": "…", "source": "…", "denominator_rule": "分母=included 条目", "items": [{"ref_id": "K01", "source_ref": "…", "title": "…", "identifiers": {"doi": "…", "pmid": "…"}, "ref_status": "included|unavailable|retracted|pending", "inclusion_reason": "…"}]},
    "queries": [{"query_id": "Q1", "query_string": "…", "fields": "…", "source_db": "…", "time_window": "…"}],
    "items": [{"ref_id": "K01", "source_ref": "…", "title": "…", "ref_status": "included", "hit_status": "hit|miss|null", "matched_by": "identifier|title|manual|null", "matched_query_id": "Q1", "matched_record_ref": "retrieved_records[0]", "evidence_quote": "逐字摘录", "evidence_location": "…", "rationale": "…", "judged": true}],
    "retrieved_summary": {"records_seen": 4, "source_key": "retrieved_records"},
    "coverage": {"denominator_basis": "frozen_reference_set", "match_rule": "…", "total_reference": 6, "included": 5, "unavailable": 1, "judged": 6, "hit": 3, "miss": 2, "extra_records": 1, "coverage_rate": 0.6, "miss_rate": 0.4},
    "miss_registry": [{"ref_id": "K04", "category": "synonym_gap", "attribution": {"query_id": "Q1", "field": "title/abstract", "source_db": "EuropePMC", "reason": "…"}, "evidence": "…", "needed_action": "…", "audit": {"registered": true, "category_valid": true, "attribution_complete": true, "query_id_exists": true}}],
    "supplementary": {"queries": [{"query_id": "Q3", "based_on_category": "synonym_gap", "query_string": "…", "source_db": "…", "time_window": "…", "new_hits": ["K04"], "rationale": "…"}], "new_hits_total": 1, "marginal_gain": 1, "effective": true, "effective_actual": true, "post_coverage_rate": 0.8, "post_miss_rate": 0.2, "stop_rule": "…", "residual_misses": [{"ref_id": "K06", "explanation": "…"}]},
    "review": {"sampled": ["K01"], "agreement_rate": 1.0, "residual_explanation": ["…"]},
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "covered_audited | partially_audited | not_audited | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "命中/遗漏判定+证据+覆盖率数字", "kind": "reported | inferred", "source_id": "K01", "location": "items[0]", "evidence": [{"paragraph_id": "retrieved_records[0].title", "quote": "原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. ref_status / hit_status / matched_by / verdict / run_status.state 枚举非法。
2. 分母口径：参考集未冻结、frozen_at 空、denominator_basis 非法、total_reference/included/unavailable/hit/miss 与逐条复算不符、coverage_rate≠hit/included、rate=1.0 但存在 miss；不可用记录却计入命中。
3. 遗漏登记：miss 未登记/重复登记/错登记；category 非法；attribution 四项任一为空；query_id 不存在于查询清单（归因泛泛）；needed_action 为空。
4. 补检空转：effective=true 但新增命中为 0；new_hits 含非 miss 条目；query_string 与原查询实质相同；post_coverage_rate 复算不符；残余遗漏缺解释；stop_rule 为空。
5. 证据回证：hit 条目 rationale/evidence_quote 为空或 claims 无逐字回证；coverage_rate / miss_rate / post_coverage_rate 数字未出现在任何 claim text/quote → unbacked_numbers 判 FAIL（显式数字字符类定界，DOI 内嵌数字已排除）。
6. coverage.judged 汇总不符；verdict 与判定进度矛盾；steps 为空或无可执行 command。
7. 闸门（case_contract / coverage_ledger / coverage_output / supp_output）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，标题/DOI 均虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/coverage_calc.py --result /tmp/skel.json --case examples/example-case.json
python3 scripts/miss_audit.py --result examples/example-result.json --case examples/example-case.json --dry-run
python3 scripts/supp_check.py --result examples/example-result.json --case examples/example-case.json --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk/coverage_ledger.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 检索无结果 / 检索记录为空 | hit=0、coverage_rate=0.0（分母仍为冻结参考集）、verdict=not_audited 或 partially_audited，绝不以结果定义分母、绝不补造文献 |
| 参考集条目撤稿/无法获取/标识异常 | ref_status=unavailable/retracted，登记不入分母；identifier_anomaly 遗漏归因写明异常细节 |
| 参考集含重复记录 | 去重后再冻结（frozen 前），duplicates 记入 material_gaps 或 uncertainties，分母以去重后条目计 |
| 来源超时 / 元数据缺失 | material_gaps 登记 + status=partial；漏检归因写明证据缺失部分，不猜测原因 |
| 两条记录同名疑似同一文献 | 机械匹配按标题归一化精确判命中；存疑改 matched_by=manual 并附证据，必要时登记 human_review |
| 补检换同义词重跑无新增 | supp_check 判空转 FAIL；如实登记 effective=false，不得报告遗漏下降 |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL / 运行中断 | 按 problems 逐条修复；修不了就如实登记 uncertainties；按协议第 8 条写 result.json，绝不中断交付 |

## 已知限制
- 仅处理输入参考集与检索记录内的文献：不做数据库实时接入、不全文精读、不做系统综述正式纳排流程。
- 机械匹配只覆盖标识符精确与标题归一化精确两种规则；标题改动大且无标识符的漏配需人工裁决（matched_by=manual）。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
