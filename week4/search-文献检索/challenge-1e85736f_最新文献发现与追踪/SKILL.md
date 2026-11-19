---
name: lit-track-incremental
description: Latest-literature discovery and tracking skill (time-window increment / dedup keys / version chains / recency ranking / source registry). Declares window/watermark/dedup-policy/weights up front, then mechanically recomputes stable dedup keys (doi > arxiv_id > normalized title, CJK-safe), window membership (UTC-declared start/end, delayed-index backfill vs stale repeats), version chains that merge preprint-to-published across DOI/arXiv keys via title linking, and a recomputable recency ranking (track_score desc -> published_date desc -> item_id asc). Every push/hold item carries verbatim evidence back-linked through claims; retractions are registered but never pushed as new literature. Verify_check mechanically re-scores and re-orders, back-checks every dedup key, score digit and quote, and re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency counters into result.json. Use when the task asks to identify genuinely new literature per time window, suppress duplicates and retraction misreports, and keep every incremental decision replayable.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 items / ranking / window / watermark / dedup_policy / version_chains / source_registry / pending_review / coverage / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全记录覆盖**：本次窗口抓到的**每一条**记录都必须逐条判定（judged=true 或写明 pending_reason），禁止只处理前几条就收尾；缺日期/缺 DOI/疑似重复/撤稿嫌疑的条目登记 missing_metadata 或 conflicts，不脑补、不跳过。
4. **不编造**：evidence_quote 必须逐字摘自该条目的实际摘要/元数据并附位置；事件判定与 track_score 必须来自 track_engine 实际输出；对不上就登记，不改证据凑结论；文不对题就照实标 irrelevant/exclude。
5. **口径事前声明**：window（起止+时区）、watermark（上次快照+水位）、dedup_policy（归一化+优先级）、rubric（三项权重+平局规则）必须在**任何判定与排序之前**写定（declared_at）并同步 /app/work/track_policy.json，之后禁止调整；不得事后改窗口凑结果。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定主题、时间窗、上次快照（水位）与本次抓到的记录集（真实署名文献 + 少量合成重复/撤稿/回补夹具），完成**增量识别、去重合并、版本链跟踪、时效排序与来源登记**。数据库实时接入、全文精读、自动写综述不在范围；来源无响应、字段缺失、时区错位照实登记，不补造文献。
关键词：判得新（新增/更新/回补/重复/撤稿有据）· 并得对（去重键稳定、跨键版本链可回溯）· 排得稳（时效排序机械可复算、平局有规则）· 登得全（来源清单、窗口、水位全量落盘，增量可回放）。
- 输入：`/input/case.json`（主题 + 窗口/快照线索 + 记录集 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与记录清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（records/papers/candidates 等）提取本次记录预填 `result.items[]`；提取上次快照键；生成 `/app/work/track_policy.json` 口径模板。
- 脚本失败时手工兜底：读 case.json 抄记录清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 窗口、水位、去重键与权重口径（1 次响应，判定前完成）
- 填 `result.research_question`（topic/scope/sources）与 `result.window`（start/end/timezone，ISO 8601）、`result.watermark`（上次快照引用 + watermark_date + window_index）。
- **事前声明口径**：`result.dedup_policy`（title_normalization=casefold+去标点空白，\w 含 CJK，**禁用 isalpha 判字**；id_precedence=doi>arxiv_id>title_norm）与 `result.rubric`（weights:{relevance,recency,confidence} 合计=1.0、tie_break、normalization、declared_at），同步写 /app/work/track_policy.json。**声明后禁止调整。**
- 标准（纳入 IN-01…/排除 EX-01…）逐条编号；标准冲突登记 uncertainties.conflicts 并声明优先序。

### Step 2 — 逐条判定（1-2 次响应，广度优先）
对 `result.items[]` 中**每一条**记录，缺一不可：
- `relevance` ∈ direct/indirect/irrelevant；`published_date`/`indexed_date`/`doi`/`arxiv_id`/`version_tag` 按实际元数据回填；`venue_type` ∈ preprint/published/unknown；
- `label` ∈ push/hold/exclude：push 只给**窗内新增/版本更新/延迟入库补回**且 relevance=direct 且有证据的条目；hold 必须写 pending_reason 并登记 pending_review；exclude 必须写 excluded_by（命中 EX-id）；
- `evidence_quote` 逐字摘录 + `evidence_location`；`confidence` ∈ high/medium/low；缺日期等字段缺失填 `missing_metadata[]`；
- **事件不抢脚本的活**：event/dedup_key/in_window/track_score/rank 由 Step 3 引擎机械落定，Agent 只在引擎记 WARN（如日期缺失）时人工判定并写明依据；
- 撤稿/勘误条目**不得 push**（更正走人工通道）；跨主题混合记录在 rationale 注明所属主题。

### Step 3 — 机械引擎（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/track_engine.py --result /app/output/result.json \
  --case /input/case.json
```
- 机械落定四件事：①去重键（doi>arxiv>title_norm，\w 含 CJK）；②时间窗判定与 backfill/out_of_window 区分（indexed_date ≥ 窗口起点=延迟入库补回，否则=窗外旧条目）；③版本链（同 dedup_key **或同 title_norm** 归并，覆盖预印本→正式版跨 DOI/arXiv 键场景；独立撤稿建单成员链）；④时效排序（rubric 权重复算 track_score，平局 track_score 降序→published_date 降序→item_id 升序），写 ranking/track_score/rank/version_chains。
- 脚本失败时手工兜底：按同一公式手算并在 steps 注明「手算」，事后仍须重跑脚本核对。

### Step 4 — 待复核登记与证据链（1 次响应）
- `result.pending_review[]`：**每个 label=hold 条目**登记 `{item_id, reason, needed_action}`；冲突升级条目同样登记。
- `result.version_chains`/`result.conflicts`：重复/版本合并登记 merged；无法确认同一性则 escalated 进待复核。`result.source_registry[]`：每个来源登记 {source_id, name, query, retrieved_at, count_returned, status}，来源异常照实记 failed/partial。
- **claims 证据链**：每个 push/hold 条目在 `claims[]` 各有一条 `{claim_id, text, kind, source_id=item_id, location, evidence:[{paragraph_id, quote}]}`；text 须含「事件判定 + 摘要证据说明 + track_score 数值」。**数字逐字回证**：evidence_quote 必须出现在对应 quote 里、track_score 数字必须出现在 claim text/quote 里（空白归一化后子串匹配），未回证数字列入 unbacked_numbers 并判 FAIL。
- 结论分级 `result.verdict`（verdict_basis 一句话）：`tracked` 全部逐条判定；`partially_tracked` 部分判定；`not_tracked` 无有效判定；`cannot_verify` 材料缺口且 material_gaps 非空。
- `result.run_status` = `{state, reason, manual_takeover[]}`，state ∈ success|partial|unable_to_determine|refused；非 success 必须写 reason。
- `result.coverage`：total/in_window/judged/push/hold/exclude/new/version_update/duplicates_merged/backfilled/retracted/out_of_window/ratio，与实际条目一致。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭事件-标签一致性/时效排序复算/证据回证/登记完整性），把**真实数字**写进 `result.gain_evidence`：`runs[]`、`delta_normal_minus_degraded`、`mechanism_to_metric_map`、`boundaries`、`failure_conditions`。
- 五项对照指标：事件-标签违规漏检数 / 排序失据漏检数 / 证据缺失漏检数 / 登记漏项数 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- `--inject-pollution` 在**副本**上注入污染（push 无证据 / 篡改分数 / 清空待复核 / 清空 claims / 抹掉 related_to）做反例自测：正常模式须抓到（`caught_by_normal_mode=true`），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence`/`efficiency` = `{available:false, reason:"…"}`，不得编数字。
- 退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每条记录都有判定或待复核吗？每个 push/exclude 都能回溯到事件依据、标准 id 与摘要证据吗？重复与撤稿都登记进 conflicts/version_chains 了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 本题业务键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"topic": "…", "scope": "…", "sources": ["…"]},
    "window": {"start": "2026-05-01", "end": "2026-05-31", "timezone": "UTC", "boundary_rule": "start <= published_date <= end"},
    "watermark": {"previous_snapshot_ref": "…", "watermark_date": "…", "window_index": 3, "declared_at": "step1"},
    "dedup_policy": {"title_normalization": "casefold+去标点空白(\\w 含 CJK)", "id_precedence": "doi > arxiv_id > title_norm", "version_link_rule": "同键或同 title_norm 按发表日升序", "declared_at": "step1"},
    "rubric": {"weights": {"relevance": 0.5, "recency": 0.3, "confidence": 0.2}, "tie_break": ["track_score 降序", "published_date 降序", "item_id 升序"], "normalization": "…", "declared_at": "step1"},
    "items": [{"item_id": "R01", "source_ref": "records[0]", "title": "…", "published_date": "…", "indexed_date": "…", "venue_type": "published", "version_tag": null, "doi": "…", "arxiv_id": null, "dedup_key": "doi:…", "in_window": true, "event": "new", "related_to": null, "relevance": "direct", "label": "push", "excluded_by": [], "evidence_quote": "逐字摘录", "evidence_location": "records[0].abstract", "confidence": "high", "rationale": "…", "factors": {"relevance": 1.0, "recency": 0.35, "confidence": 0.9}, "track_score": 0.79, "rank": 1, "missing_metadata": [], "pending_reason": null, "judged": true}],
    "ranking": {"ordered_ids": ["R01"], "ties": [], "top_k": ["R01"], "k_value": 1, "tie_break": ["…"], "window": {"start": "…", "end": "…"}},
    "coverage": {"total": 8, "in_window": 5, "judged": 8, "push": 2, "hold": 4, "exclude": 2, "new": 2, "version_update": 1, "duplicates_merged": 1, "backfilled": 1, "retracted": 1, "out_of_window": 1, "ratio": 1.0},
    "version_chains": [{"chain_id": "vc-01", "dedup_key": "…", "alt_keys": ["…"], "member_ids": ["R02", "R03"], "members": [{"item_id": "R02", "published_date": "…", "venue_type": "preprint", "version_tag": "v1"}], "kind": "multi_version", "canonical": "R02", "resolution": "merged", "evidence": "title_norm 相同跨键归并，按发表日升序"}],
    "source_registry": [{"source_id": "S1", "name": "crossref-feed", "query": "…", "retrieved_at": "…", "count_returned": 5, "status": "ok"}],
    "conflicts": [{"item_ids": ["R02", "R03"], "kind": "preprint_published", "resolution": "merged", "evidence": "…"}], "pending_review": [{"item_id": "R05", "reason": "…", "needed_action": "…"}],
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}], "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "tracked | partially_tracked | not_tracked | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "事件判定+证据+分数", "kind": "reported | inferred", "source_id": "R01", "location": "items[0]", "evidence": [{"paragraph_id": "records[0].abstract", "quote": "摘要原句"}]}], "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}], "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. relevance / label / event / confidence / venue_type / verdict / run_status.state 枚举非法。
2. push 非 new/version_update/backfill 事件、push 窗外条目、push 非 direct、push 无证据；out_of_window 不标 exclude；duplicate 无 related_to；retraction 标 push；hold 无 pending_reason；exclude 无 excluded_by；irrelevant 标 push。
3. window 声明非法（start>end / 非 ISO / timezone 空）；rubric 未事前声明或权重合计≠1.0；track_score 与 rubric 权重机械复算不符；ordered_ids 与复算顺序不一致；rank 名次不连续。
4. dedup_key 与机械重算不符（归一化规则不可复算）；已判定条目 rationale 为空；push/hold 的证据在 claims 无逐字回证；track_score 数字无回证 → unbacked_numbers 判 FAIL。
5. hold 未登记进 pending_review；related_to 未在 conflicts 登记 merged/escalated；escalated 未进待复核；version_update/retraction 未进 version_chains；source_registry 为空或缺 source_ref。
6. coverage 汇总与实际条目不符；verdict 与判定进度矛盾；steps 为空或无可执行 command。
7. 闸门（case_contract / policy_ledger / ranking_recompute / track_engine_output）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，标题摘要 DOI 均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/track_engine.py --result examples/example-result.json --case examples/example-case.json --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --policy /tmp/wk/track_policy.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 来源无响应 / 记录集为空 | items 空、coverage.total=0、verdict=cannot_verify 或 not_tracked，source_registry 记 failed，绝不补造文献 |
| published_date / DOI 缺失 | missing_metadata 登记 + 置信度降级；无法判窗内新增则 hold 并登记待复核 |
| 时区错位 / 窗口边界争议 | window.timezone 必须显式声明；边界条目（恰为起止日）一律按 start<=date<=end 判入并在 rationale 注明 |
| 预印本→正式版（DOI 与 arXiv 并存） | 引擎按 title_norm 跨键归并成版本链，正式版 version_update、预印本按提醒抑制规则 hold 待确认 |
| 同文多源转载 / 重复投喂 | dedup_key 相同即合并（duplicate），related_to 指向保留条目，conflicts 登记 merged |
| 撤稿 / 勘误 | event=retraction，登记 version_chains，绝不 push；走人工更正通道 |
| 延迟入库（旧文献本期才被索引） | event=backfill 可推送；非延迟入库的窗外旧条目 out_of_window 必须排除 |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅处理输入记录集内文献：不做数据库实时检索、不全文精读、不负责授权外的定时抓取。
- 去重以标题归一化 + 标识优先级为准：改题换封面（同一论文换标题再投）无法机械归并，只能靠 escalated 待复核兜底；该边界已在 gain_evidence.failure_conditions 声明。
- recency/confidence 因子按 rubric 声明的归一化口径计算，口径是本技能设定（论文/平台未给定时按量级保守设定并写明），不冒充外部标准。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
