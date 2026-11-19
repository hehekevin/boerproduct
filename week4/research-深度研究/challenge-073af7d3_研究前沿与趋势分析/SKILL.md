---
name: trend-frontier-analyst
description: Research-frontier trend analysis skill (topic clustering / yearly trend recomputation / emerging-vs-mature-vs-declining grading / evidence-bound hot topics / extrapolation boundary registry). Declares clustering keyword-clusters, observation window and grading thresholds up front, then mechanically assigns every record to a topic (CJK-safe normalization, no isalpha), recomputes per-topic yearly counts, growth_rate=(late_avg-early_avg)/early_avg and stages from the declared thresholds, binds every trend conclusion to verbatim representative evidence via claims, and registers an extrapolation boundary (no extrapolation by default). Research gaps are only claimed as identified when backed by itemized exclusion evidence, never by "nothing retrieved". Verify_check mechanically re-derives topic assignment, yearly counts, growth rates and stages, back-checks every growth number and quote, and re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency counters into result.json. Use when the task asks to analyze research frontiers and trends with replayable, evidence-bound conclusions.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 items / topics / gaps / clustering_policy / trend_policy / extrapolation / coverage / source_registry / pending_review / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全记录覆盖**：输入中的**每一条**文献记录都必须逐条判定（judged=true 或写明 pending_reason），禁止只处理前几条就收尾；缺年份/缺引用数/关键词歧义的条目登记 missing_metadata 或 pending_review，不脑补、不跳过。
4. **不编造**：evidence_quote 必须逐字摘自该条目的实际摘要/标题并附位置；年度计数、growth_rate、stage 必须来自 trend_engine 实际输出；对不上就登记，不改证据凑结论。
5. **口径事前声明**：clustering_policy（关键词簇+归一化+匹配顺序）、trend_policy（观测窗口 start_year/end_year、增速公式、emerging/declining 阈值）、extrapolation 边界必须在**任何判定与分级之前**写定（declared_at）并同步 /app/work/trend_policy.json，之后禁止调整；不得事后改窗口或阈值凑结果。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定研究问题与固定记录集（真实文献 + 可能的歧义/缺字段夹具），完成**主题聚类、年度趋势复算、新兴/成熟/衰退分级、热点证据绑定、研究空白识别与外推边界登记**。数据库实时检索、全文精读、引文网络自动抓取不在范围；检索为空、年份缺失、主题歧义照实登记，不补造文献。
关键词：归得对（主题归属机械可复算）· 算得准（年度计数与增速回证数字）· 分得稳（分级只看事前阈值）· 绑得住（每个趋势结论绑定逐字证据）· 不越界（空白须有排除证据，趋势不外推）。
- 输入：`/input/case.json`（研究问题 + 记录集 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与记录清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（records/papers/documents 等）提取记录预填 `result.items[]`；生成 `/app/work/trend_policy.json` 口径模板。
- 脚本失败时手工兜底：读 case.json 抄记录清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 聚类口径、观测窗口与分级阈值（1 次响应，判定前完成）
- 填 `result.research_question`（topic/scope/inclusion_criteria/exclusion_criteria）与 `result.trend_policy.window`（start_year/end_year）。
- **事前声明口径**：`result.clustering_policy`（method=keyword_rule；归一化=casefold+非字母数字折叠为空格，\w 含 CJK，**禁用 isalpha 判字**；match_order=簇声明顺序首个命中；clusters[].keywords 按主题语义写全，覆盖术语变体）；`result.trend_policy`（split_rule=growth_rate=(late_avg-early_avg)/early_avg；thresholds：emerging_min_growth=0.5、declining_max_growth=-0.34，可按窗口长短调整但须先声明）；同步 /app/work/trend_policy.json。**声明后禁止调整。**
- `result.extrapolation` 登记外推边界（默认 allowed=false，仅报告窗口内趋势）。

### Step 2 — 逐条判定（1-2 次响应，广度优先）
对 `result.items[]` 中**每一条**记录，缺一不可：
- `topic_id`/`matched_keyword`：按簇关键词命中填写；不含任何关键词 → topic_id=null + pending_reason + 登记 pending_review；
- `relevance` ∈ core/related/irrelevant；`year`/`published_date`/`citation_count`/`venue_type` 按实际元数据回填；
- `evidence_quote` 逐字摘录 + `evidence_location`；`confidence` ∈ high/medium/low；缺字段登记 `missing_metadata[]`；
- **数字不抢脚本的活**：yearly_counts/growth_rate/stage/coverage 由 Step 3 引擎机械落定，Agent 只在引擎记 WARN 时人工判定并写明依据；
- 引用数不参与趋势判定（只作代表作辅助线索）；术语换了说法但簇词表未覆盖的条目按未归属处理，不硬塞主题。

### Step 3 — 机械趋势引擎（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/trend_engine.py --result /app/output/result.json
```
- 机械落定四件事：①主题归属复算（与 Step 2 填写对照）；②每主题 `yearly_counts`（按 window 切片）；③`growth_rate`（early=[S..mid]、late=[mid+1..E]，mid=(S+E)//2）与 `stage`（只看事前阈值：>=0.5 emerging / <=-0.34 declining / 其间 mature；0 条目主题 no_evidence）；④`coverage` 与 `extrapolation` 回写。
- 脚本失败时手工兜底：按同一公式手算并在 steps 注明「手算」，事后仍须重跑脚本核对。

### Step 4 — 证据绑定与空白主张（1 次响应）
- **claims 证据链**：每个主题在 `claims[]` 一条 `{claim_id, text, kind, source_id=topic_id, evidence:[{paragraph_id, quote}]}`；text 须含「年度计数 + 早期/近期均值 + growth_rate 数值 + stage + 代表作 id」；代表作的 evidence_quote 须逐字出现在该 claim 的 evidence quote 里。**数字逐字回证**：growth_rate 数字必须出现在 claim text/quote 中（空白归一化后子串匹配），未回证列入 unbacked_numbers 判 FAIL。
- **gaps 空白主张**：status=identified 须有 `search_scope` 与逐条带 quote 的 `exclusion_evidence`（被反复提出未解决/方法失效/证据冲突未决）；没有排除证据就填 status=not_verified + reason，**绝不把"没检索到"当研究空白**。
- 结论分级 `result.verdict`（verdict_basis 一句话）：`analyzed` 全部判定；`partially_analyzed` 部分判定；`not_analyzed` 无有效判定；`cannot_verify` 材料缺口且 material_gaps 非空。
- `result.run_status` = `{state, reason, manual_takeover[]}`，state ∈ success|partial|unable_to_determine|refused；非 success 必须写 reason。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭主题归属一致性/趋势判定复算/证据回证/登记完整性），把**真实数字**写进 `result.gain_evidence`：runs[]、delta_normal_minus_degraded、mechanism_to_metric_map、boundaries、failure_conditions。
- 五项对照指标：主题归属违规漏检数 / 趋势判定漏检数 / 证据缺失漏检数 / 登记漏项数 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- `--inject-pollution` 在**副本**上注入污染（篡改 growth_rate / 错标 stage / 清空证据 / 拆除空白排除证据 / 清空 claims）做反例自测：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence`/`efficiency` = `{available:false, reason:"…"}`，不得编数字。退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每条记录都有判定或待复核吗？每个主题的计数/增速/分级都能按事前口径复算并回证吗？每个空白都有排除证据或如实标 not_verified 吗？

## 输出 schema（result.json — 平台通用契约五字段 + 本题业务键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"topic": "…", "scope": "…", "sources": ["…"], "inclusion_criteria": ["IN-01 …"], "exclusion_criteria": ["EX-01 …"]},
    "clustering_policy": {"method": "keyword_rule", "title_normalization": "casefold+非字母数字折叠(\\w 含 CJK，不用 isalpha)", "match_order": "簇声明顺序首个命中", "clusters": [{"topic_id": "T1", "label": "…", "keywords": ["…"], "representative_seed": ["R01"]}], "declared_at": "step1"},
    "trend_policy": {"year_field": "year", "window": {"start_year": 2016, "end_year": 2026}, "split_rule": "mid=(S+E)//2；growth=(late_avg-early_avg)/early_avg", "thresholds": {"emerging_min_growth": 0.5, "declining_max_growth": -0.34}, "citation_note": "引用数仅辅助", "declared_at": "step1"},
    "extrapolation": {"allowed": false, "rule": "仅报告窗口内趋势，不外推", "registered_at": "step3"},
    "items": [{"item_id": "R01", "source_ref": "records[0]", "title": "…", "published_date": "…", "year": 2016, "venue_type": "published", "citation_count": 210, "topic_id": "T1", "matched_keyword": "memristor", "relevance": "core", "evidence_quote": "逐字摘录", "evidence_location": "records[0].abstract", "confidence": "high", "rationale": "…", "missing_metadata": [], "pending_reason": null, "judged": true}],
    "topics": [{"topic_id": "T1", "label": "…", "keywords": ["…"], "item_ids": ["R01"], "total_count": 6, "yearly_counts": {"2016": 1}, "early_avg": 0.67, "late_avg": 0.4, "growth_rate": -0.4, "stage": "declining", "stage_basis": "阈值复算依据", "representative_ids": ["R01", "R05"]}],
    "gaps": [{"gap_id": "G-01", "claim": "…", "kind": "repeated_unresolved", "search_scope": "…", "exclusion_evidence": [{"source_ref": "records[6]", "quote": "…"}], "status": "identified | not_verified"}],
    "coverage": {"total": 19, "judged": 19, "core": 17, "related": 1, "irrelevant": 1, "unassigned": 1, "topics_count": 3, "ratio": 1.0},
    "source_registry": [{"source_id": "S1", "name": "…", "query": "…", "retrieved_at": "…", "count_returned": 19, "status": "ok"}],
    "pending_review": [{"item_id": "R19", "reason": "…", "needed_action": "…"}],
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}], "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "analyzed | partially_analyzed | not_analyzed | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-T1", "text": "主题计数+均值+growth_rate+stage+代表作", "kind": "reported | inferred", "source_id": "T1", "location": "topics", "evidence": [{"paragraph_id": "records[0].abstract", "quote": "摘要原句"}]}], "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}], "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. relevance / confidence / venue_type / stage / gap.status / verdict / run_status.state 枚举非法。
2. topic_id 与按事前关键词簇机械重算不符；matched_keyword 不在簇词表；irrelevant 却有 topic_id；judged 未归属却无 pending_reason 或未登记 pending_review；代表作不在主题成员内或缺逐字证据。
3. clustering_policy / trend_policy 未事前声明（declared_at 空、簇为空、window 非法）；yearly_counts / early_avg / late_avg / growth_rate / stage 与 items+window+阈值复算不符（growth 容差 1e-3）——**分级不一致直接 FAIL**。
4. judged 条目 rationale 为空；core/related 缺 evidence_quote/location；主题无 claims 回证；代表作 quote 未逐字回证；growth_rate 数字未回证 → unbacked_numbers 判 FAIL；identified 空白缺 search_scope 或排除证据。
5. source_registry 为空或缺 source_ref；coverage 汇总与实际条目不符；extrapolation 未登记外推边界；verdict 与判定进度矛盾；steps 为空或无可执行 command。
6. 闸门（case_contract / policy_ledger / trend_engine_output）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，标题/摘要/年份/引用数均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/trend_engine.py --result examples/example-result.json
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --policy /tmp/wk/trend_policy.json --out /tmp/vc.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 记录集为空 / 材料缺失 | items 空、coverage.total=0、verdict=cannot_verify，source_registry 记 failed，绝不补造文献 |
| year / published_date 缺失 | missing_metadata 登记 + 置信度降级；无法定年则不进 yearly_counts 并登记待复核 |
| 关键词歧义 / 术语漂移 | 簇词表未覆盖 → topic_id=null + pending_reason + pending_review，不硬塞主题；同名异义在 rationale 注明 |
| 关键词横跨多簇 | 按 match_order 首个命中即归属，rationale 注明次选簇 |
| 引用数缺失 / 引用刷高 | 趋势判定只看发文量口径，引用数仅辅助，缺失不阻塞 |
| 窗口边界条目（恰为起止年） | 按 start_year<=year<=end_year 判入并在 rationale 注明 |
| 证据互相冲突 | 登记 uncertainties.conflicts，结论只写证据支撑的部分，其余进待复核 |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅处理输入记录集内文献：不做数据库实时检索、不全文精读、不抓引文网络；共引/耦合等需要引文图谱的聚类方法不在范围，聚类按声明关键词规则机械执行。
- 簇词表是本技能的先验设定而非文献库官方分类：术语漂移依赖词表覆盖度，覆盖不足的条目按未归属登记待复核；该边界已在 gain_evidence.boundaries 声明。
- growth_rate 是窗口两端均值对比，不识别拐点年份；离散波动与真实拐点的区分须人工结合 yearly_counts 判断，本技能只提供可复算的年度分布。
- 阈值 0.5/-0.34 是本技能的保守设定（窗口 8-12 年时量级合理），非外部标准；调整须在 Step 1 事前声明。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
