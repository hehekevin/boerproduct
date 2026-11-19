---
name: lit-screen-rank
description: Literature screening and intelligent ranking skill (relevance tiering / criteria-based labeling / multi-factor ordering / pending-review registry). Judges each candidate paper against pre-declared inclusion/exclusion criteria with per-item rationale and abstract quotes, labels keep/pending/exclude, fuses relevance/quality/recency factors into a deterministic explainable ranking (pre-declared weights, recorded ties, top-k), merges preprint/published duplicates with conflict records, and registers every pending item for human review. Verify_check mechanically re-scores and re-orders, back-checks every quote and fused_score through the claims evidence chain, and re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency counters into result.json. Use when the task asks to screen a candidate literature set against research questions and criteria, rank papers by traceable multi-factor scores, and keep every decision reviewable.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 items / ranking / rubric / pending_review / coverage / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全记录覆盖**：候选集**每一条**文献都必须逐条判定（judged=true 或写明 pending_reason），禁止只处理前几条就收尾；缺摘要/缺年份/疑似重复的条目登记 missing_metadata 或 conflicts，不脑补、不跳过。
4. **不编造**：evidence_quote 必须逐字摘自该条目的实际摘要/原文并附位置；本方分数必须来自 score_rank 实际输出；对不上就登记，不改证据凑结论；文不对题就照实标 irrelevant/exclude。
5. **口径事前声明**：rubric（三项权重 + 归一化规则 + 平局规则）必须在**任何排序之前**写定（declared_at），之后禁止调整；纳排标准逐条给 criterion_id，判定必须引用 id，不得事后改标准凑结果。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定研究问题、纳排标准与候选文献集（通常为真实署名论文 + 少量合成重复/冲突夹具），完成**逐条相关性判断、三层标签、可解释多因子排序、待复核登记**。底层数据库接入、全文精读、系统综述全流程不在范围；检索无结果、标注标准互相冲突、元数据缺失照实登记，不补造文献。
关键词：判得准（纳排逐条可回溯）· 排得稳（权重事前声明、平局有规则）· 讲得清（逐条理由 + 摘要证据 + 置信度）· 漏得少（待定全登记、重复必合并）。
- 输入：`/input/case.json`（研究问题 + 标准 + 候选文献 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与候选清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（papers/candidates/items 等）提取候选清单预填 `result.items[]`；生成 `/app/work/rubric.json` 打分口径模板。
- 脚本失败时手工兜底：读 case.json 抄候选清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 研究问题、纳排标准与打分口径（1 次响应，排序前完成）
- 填 `result.research_question`（question/scope/time_range）与 `result.criteria`：纳入/排除标准逐条编号（IN-01…/EX-01…），标准之间冲突或口径不明时登记 `uncertainties.conflicts` 并声明采用哪条优先，不得 silently 混用。
- **事前声明 rubric**：`result.rubric` = `{weights:{relevance,quality,recency}（合计=1.0）, tie_break, normalization, declared_at}`，同步写 /app/work/rubric.json。normalization 约定：relevance direct=1.0/indirect=0.5/irrelevant=0.0；quality 按设计类型与样本量 0-1；recency 按 (year−起始年)/跨度 截断 0-1。**声明后禁止调整。**

### Step 2 — 逐条判定（1-2 次响应，广度优先）
对 `result.items[]` 中**每一条**候选文献，缺一不可：
- `relevance` ∈ direct/indirect/irrelevant（依据研究问题、对象、方法、人群、时间范围）；
- `label` ∈ keep/pending/exclude：keep 必须命中 ≥1 条纳入标准（criteria_hit 填 id）；exclude 必须命中 ≥1 条排除标准（excluded_by 填 id）；pending 必须写 pending_reason；
- `evidence_quote` 逐字摘自该条摘要/原文 + `evidence_location` 注明位置；`confidence` ∈ high/medium/low；`rationale` 一句话写明命中哪条标准、依据哪段证据；
- `venue_type` ∈ preprint/published/unknown；缺摘要/缺年份/字段缺失填 `missing_metadata[]`；
- **冲突处理**：预印本与正式版本、同一研究多篇报道 → `duplicate_of` 指向保留条目，在 `result.conflicts[]` 登记 `{item_ids, kind, resolution: merged|escalated, evidence}`；escalated 的必须同时进 pending_review。**跨主题混合候选集按研究问题分主题时，在 rationale 注明所属主题，不改变排序规则。**

### Step 3 — 机械排序（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/score_rank.py --result /app/output/result.json [--k 10]
```
- 按事前 rubric 权重机械复算 fused_score（保留 4 位小数）并按平局规则（fused_score 降序 → recency 降序 → item_id 升序）产出 `result.ranking`（ordered_ids / ties / top_k / k_value）与 items[].fused_score、items[].rank；同分并列组全部记入 ties。k 默认取 keep 条目数，可由任务要求覆盖。
- keep/pending 条目填 factors（三项 0-1）；exclude 条目 factors 留空不参与排序。
- 脚本失败时手工兜底：按同一公式手算并在 steps 注明「手算」，事后仍须重跑脚本核对。

### Step 4 — 待复核登记与证据链（1 次响应）
- `result.pending_review[]`：**每个 label=pending 条目**登记 `{item_id, reason, needed_action}`；冲突升级条目同样登记。
- `result.coverage`：total_candidates / judged_items / keep / pending / exclude / duplicates_merged / ratio（judged/total），与实际条目一致。
- **claims 证据链**：每个 keep/pending 条目在 `claims[]` 各有一条 `{claim_id, text, kind: reported|inferred, source_id=item_id, location, evidence:[{paragraph_id, quote}]}`；text 须含「纳排命中 + 摘要证据说明 + fused_score 数值」。**数字逐字回证**：evidence_quote 必须出现在对应 quote 里、fused_score 数字必须出现在 claim text/quote 里（空白归一化后子串匹配），未回证数字列入 unbacked_numbers 并判 FAIL。
- 结论分级 `result.verdict`（verdict_basis 一句话写依据）：`screened` 全部逐条判定且覆盖完整；`partially_screened` 部分判定；`not_screened` 未产生有效判定；`cannot_verify` 材料缺口导致无法判定且 material_gaps 非空。
- 运行状态 `result.run_status` = `{state, reason, manual_takeover[]}`，`state` ∈ success|partial|unable_to_determine|refused；非 success 必须写 reason 与人工接管位置。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭纳排一致性 / 排序复算 / 证据回证 / 待复核登记），把**真实数字**写进 `result.gain_evidence`：`runs[]`、`delta_normal_minus_degraded`、`mechanism_to_metric_map`、`boundaries`、`failure_conditions`。
- 五项对照指标：纳排违规漏检数 / 排序失据漏检数 / 证据缺失漏检数 / 待复核漏登记数 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- 同时写 `result.efficiency`（墙钟、字节、检查项数、条目数、人工条目、追问轮次 + `reproduce` 复现命令）；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- `--inject-pollution` 在**副本**上注入污染（keep 无依据 / 篡改分数 / 清空待复核 / 清空 claims）做反例自测：正常模式须抓到（`caught_by_normal_mode=true`），原 result.json 不被改动。
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
- 自查三问：候选集每一条都有判定或待复核吗？每个 keep/exclude 都能回溯到纳排 id 与摘要证据吗？待定与冲突升级都登记进 pending_review 了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"question": "…", "scope": "…", "time_range": "…"},
    "criteria": {"inclusion": [{"criterion_id": "IN-01", "text": "…"}], "exclusion": [{"criterion_id": "EX-01", "text": "…"}]},
    "rubric": {"weights": {"relevance": 0.5, "quality": 0.3, "recency": 0.2}, "tie_break": ["fused_score 降序", "recency 降序", "item_id 升序"], "normalization": "…", "declared_at": "step1"},
    "items": [{"item_id": "P01", "source_ref": "candidates[0]", "title": "…", "venue_type": "published", "relevance": "direct", "label": "keep", "criteria_hit": ["IN-01"], "excluded_by": [], "evidence_quote": "逐字摘录", "evidence_location": "candidates[0].abstract", "confidence": "high", "rationale": "…", "factors": {"relevance": 1.0, "quality": 0.9, "recency": 0.7}, "fused_score": 0.91, "rank": 1, "duplicate_of": null, "missing_metadata": [], "pending_reason": null, "judged": true}],
    "ranking": {"ordered_ids": ["P01"], "ties": [], "top_k": ["P01"], "k_value": 1},
    "coverage": {"total_candidates": 6, "judged_items": 6, "keep": 2, "pending": 1, "exclude": 3, "duplicates_merged": 1, "ratio": 1.0},
    "conflicts": [{"item_ids": ["P02", "P03"], "kind": "duplicate_versions", "resolution": "merged", "evidence": "…"}],
    "pending_review": [{"item_id": "P04", "reason": "…", "needed_action": "…"}],
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "screened | partially_screened | not_screened | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "纳排命中+证据+分数", "kind": "reported | inferred", "source_id": "P01", "location": "items[0]", "evidence": [{"paragraph_id": "candidates[0].abstract", "quote": "摘要原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. relevance / label / confidence / venue_type / verdict / run_status.state 枚举非法。
2. keep 无 criteria_hit；exclude 无 excluded_by；pending 无 pending_reason；irrelevant 标 keep；direct 标 exclude 且未登记 duplicate_of（跨级矛盾）。
3. fused_score 与 rubric 权重机械复算不符；ranking.ordered_ids 与复算顺序不一致；rank 名次不连续；rubric 未事前声明或权重合计≠1.0。
4. 已判定条目 rationale 为空；keep 无 evidence_quote；keep/pending 的证据在 claims 无逐字回证；fused_score 数字无回证 → unbacked_numbers 判 FAIL。
5. pending 未登记进 pending_review；duplicate_of 未在 conflicts 登记 merged/escalated；escalated 未进待复核。
6. coverage 汇总与实际条目不符；verdict 与判定进度矛盾；steps 为空或无可执行 command。
7. 闸门（case_contract / rubric_ledger / ranking_recompute / score_rank_output）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，标题摘要均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/score_rank.py --result examples/example-result.json --k 3 --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --rubric /tmp/wk/rubric.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 检索无结果 / 候选集为空 | items 空、coverage.total=0、verdict=cannot_verify 或 not_screened，status 写明，绝不补造文献 |
| 摘要/年份/元数据缺失 | missing_metadata 登记 + 置信度降级；关键信息缺失则 pending 并登记待复核 |
| 标注标准互相冲突 | uncertainties.conflicts 登记双方 + 声明采用的优先序，不混用两套口径 |
| 预印本/重复/多篇报道 | duplicate_of + conflicts 登记 merged（保留正式发表版本）；无法确认同一性则 escalated 进待复核 |
| 大量同分 | score_rank 把并列组记入 ties，按 tie_break 规则破平并在 ranking 可见，不静默改分 |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅处理输入候选集内文献：不做数据库实时检索、不全文精读、不做系统综述纳排全流程。
- quality/recency 因子按 rubric 声明的归一化口径计算，口径是本技能设定（论文/平台未给定时按量级保守设定并写明），不冒充外部标准。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
