---
name: topic-novelty-audit
description: Research topic selection and novelty assessment skill (structured topic decomposition / novelty cross-check against known works / feasibility element audit / pre-declared grading rubric / risk & alternative registry). Structures each candidate topic into problem/hypothesis/method/expected-contribution, checks every novelty claim item-by-item against the provided known-work list with verbatim quotes and overlap verdicts (covered/partial/none/uncertain, duplicates flagged), audits data/method/resource/time feasibility elements with status and basis, grades innovation levels under a rubric declared BEFORE any grading (weights sum to 1.0, fixed tie-break), and registers risks, alternative routes and human-review items. Verify_check mechanically recomputes scores and ranking, back-checks every quote and score through the claims evidence chain, and re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency counters into result.json. Use when the task asks to evaluate research topic proposals for novelty and feasibility with every judgment traceable.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 proposals / novelty 校验 / rubric / ranking / human_review / coverage / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全记录覆盖**：候选选题**每一条**都必须逐条结构化与评估（judged=true 或写明 pending_reason），禁止只处理前几条就收尾；缺要素/缺已知文献/疑似重复照实登记，不脑补。
4. **不编造**：novelty_claims 的 evidence_quote 必须逐字摘自实际已知文献条目并附位置；分级与分数必须来自声明的口径与 novelty_rank 实际输出；"检索不到"绝不写成"尚无人研究"——对照不到就标 uncertain 并登记待复核。
5. **口径事前声明**：rubric（分级规则 grade_rules + 三项权重 + 归一化 + 平局规则）必须在**任何分级/排序之前**写定（declared_at），之后禁止调整；判定必须引用声明条目，不得事后改口径凑结果。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增评估，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定候选选题清单与已知工作清单（真实署名文献/项目 + 少量合成重复夹具），完成**选题四要素结构化、新颖性逐条对照、可行性要素核查、创新性分级与排序、风险与替代路线登记**。底层数据库实时检索、全文精读、代写标书不在范围；已知工作对不上、证据互相冲突、要素缺失照实登记，不补造文献。
关键词：拆得清（四要素可检验）· 对得准（与已知工作逐条划界）· 级得稳（口径事前声明）· 证得实（评估逐条回证）· 兜得住（风险与替代路线全登记）。
- 输入：`/input/case.json`（研究方向 + 候选选题 proposals + 已知工作 known_works + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与选题清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（proposals/topics/candidates 提选题，known_works/references/papers 提已知工作）预填 `result.proposals[]` 与 `/app/work/known_works.json`；生成 `/app/work/rubric.json` 分级口径模板。
- 脚本失败时手工兜底：读 case.json 抄选题与已知工作清单及 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 研究方向与分级口径（1 次响应，分级前完成）
- 填 `result.research_context`（direction/scope/constraints）与 `result.criteria`（新颖性对照的纳入/排除口径，逐条编号 IN-01…/EX-01…，说明什么样的工作算"与选题撞车"）。
- **事前声明 rubric**：`result.rubric` = `{grade_rules:[{grade, rule}...]（breakthrough/strong/incremental/not_novel/uncertain 五级）, weights:{novelty,feasibility,evidence}（合计=1.0）, tie_break, normalization, declared_at}`，同步写 /app/work/rubric.json。**声明后禁止调整。**

### Step 2 — 选题结构化与新颖性逐条对照（1-2 次响应，广度优先）
对 `result.proposals[]` 中**每一条**候选选题，缺一不可：
- **四要素结构化** `structure`：`problem`（研究对象+关键变量+比较基线）、`hypothesis`（可证伪表述）、`method`（技术路线）、`expected_contribution`（预期贡献）；要素写不出就登记 `missing_elements[]`，不硬凑。
- **新颖性对照** `novelty_claims[]`：把创新陈述拆条（`kind` ∈ method/data/scene/theory），**每条**与 known_works 逐条对照：`closest_work_id` + `overlap` ∈ none/partial/covered/uncertain + `evidence_quote` 逐字摘自该已知工作条目 + `evidence_location` 注明位置。overlap=covered 的选题标 `novelty_grade=not_novel` 并登记 `duplicate_of`；对照不到（known_works 覆盖不足）标 uncertain，**不许下"尚无人研究"的结论**。
- **可行性核查** `feasibility`：data/method/resource/time 四要素各填 `{status ∈ sufficient/partial/missing/assumption, basis}`；basis 须指明来源（材料字段或明确标 assumption）。
- `confidence` ∈ high/medium/low；`rationale` 一句话写明分级依据与证据位置；创新性分级 `novelty_grade` 必须对应 rubric 声明的 grade_rules 条目。**重复/冲突**：选题间重复或与已知工作重复 → `duplicate_of` + `result.conflicts[]` 登记 `{item_ids, kind, resolution: flagged|escalated, evidence}`；escalated 必须同时进 human_review。

### Step 3 — 机械分级打分与排序（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/novelty_rank.py --result /app/output/result.json [--k 5]
```
- 按事前 rubric 权重机械复算 fused_score（保留 4 位小数）并按平局规则（fused_score 降序 → novelty 因子降序 → proposal_id 升序）产出 `result.ranking`（ordered_ids / ties / top_k / k_value）与 proposals[].fused_score、rank；同分并列组全部记入 ties。
- 已评估条目填 factors（novelty/feasibility/evidence 三项 0-1）；未评估条目不参与排序。k 默认取已评估条目数。
- 脚本失败时手工兜底：按同一公式手算并在 steps 注明「手算」，事后仍须重跑脚本核对。

### Step 4 — 登记与证据链（1 次响应）
- `result.human_review[]`：grade=uncertain、missing_elements 非空、feasibility 有 missing/assumption、冲突升级条目**逐条**登记 `{proposal_id, reason, needed_action}`。
- **风险与替代路线 + 覆盖汇总**：每条已评估选题在 `risks[]` 登记 `{risk_id, proposal_id, description, mitigation}`，有替代路线的登记 `alternatives[]` `{alt_id, proposal_id, route, reason}`（确无风险的写明「未识别到」而不是留空）；`result.coverage`：total_proposals / judged / structure_complete / novelty_covered / feasibility_flagged / ratio，与实际条目一致。
- **claims 证据链**：每条已评估选题在 `claims[]` 各有一条 `{claim_id, text, kind: reported|inferred, source_id=proposal_id, location, evidence:[{paragraph_id, quote}]}`；text 须含「分级 + 关键对照结论 + fused_score 数值」。**数字与引文逐字回证**：novelty_claims 的 evidence_quote 必须出现在对应 claim 的 quote 里、fused_score 数字必须出现在 claim text/quote 里（空白归一化后子串匹配），未回证列入 unbacked_numbers 并判 FAIL。
- 结论分级 `result.verdict`（verdict_basis 一句话）：`assessed` 全部逐条评估且覆盖完整；`partially_assessed` 部分评估；`not_assessed` 未产生有效评估；`cannot_verify` 材料缺口导致无法判定且 material_gaps 非空。
- 运行状态 `result.run_status` = `{state ∈ success|partial|unable_to_determine|refused, reason, manual_takeover[]}`，非 success 必须写 reason。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭要素覆盖 / 口径与复算 / 评估回证 / 登记检查），把**真实数字**写进 `result.gain_evidence`：`runs[]`、`delta_normal_minus_degraded`、`mechanism_to_metric_map`、`boundaries`、`failure_conditions`。
- 五项对照指标：要素违规漏检数 / 口径与复算漏检数 / 回证缺失漏检数 / 登记漏项数 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- 同时写 `result.efficiency`（墙钟、字节、检查项数、条目数、人工条目、追问轮次 + `reproduce` 复现命令）；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- `--inject-pollution` 在**副本**上注入污染（要素缺失未登记 / covered 却标 breakthrough / 口径声明清空 / 清空 human_review / 清空 claims）做反例自测：正常模式须抓到（`caught_by_normal_mode=true`），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence` = `{available:false, reason:"…"}` 与 `efficiency` = `{available:false, reason:"…"}`，不得编数字；退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每条选题都结构化且要素齐备或登记缺失了吗？每条创新陈述都能回溯到已知工作条目与逐字证据吗？uncertain、缺要素、可行性缺口与冲突升级都登记进 human_review 了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_context": {"direction": "…", "scope": "…", "constraints": "…"},
    "criteria": {"inclusion": [{"criterion_id": "IN-01", "text": "…"}], "exclusion": [{"criterion_id": "EX-01", "text": "…"}]},
    "rubric": {"grade_rules": [{"grade": "breakthrough", "rule": "≥1 条 method/theory 创新陈述 overlap=none 且要素齐全"}],
               "weights": {"novelty": 0.5, "feasibility": 0.3, "evidence": 0.2}, "tie_break": ["fused_score 降序", "novelty 因子降序", "proposal_id 升序"], "normalization": "…", "declared_at": "step1"},
    "proposals": [{"proposal_id": "T01", "source_ref": "proposals[0]", "title": "…",
      "structure": {"problem": "…", "hypothesis": "…", "method": "…", "expected_contribution": "…"}, "missing_elements": [],
      "novelty_claims": [{"claim_id": "T01-N1", "text": "…", "kind": "method", "closest_work_id": "W02", "overlap": "partial", "evidence_quote": "逐字摘录", "evidence_location": "known_works[1].abstract"}],
      "novelty_grade": "breakthrough | strong | incremental | not_novel | uncertain",
      "feasibility": {"data": {"status": "sufficient", "basis": "…"}, "method": {"status": "partial", "basis": "…"}, "resource": {"status": "assumption", "basis": "…"}, "time": {"status": "sufficient", "basis": "…"}}, "feasibility_verdict": "feasible | conditional | infeasible | uncertain",
      "duplicate_of": null, "confidence": "high", "rationale": "…", "factors": {"novelty": 0.9, "feasibility": 0.7, "evidence": 0.85}, "fused_score": 0.83, "rank": 1, "missing_metadata": [], "pending_reason": null, "judged": true}],
    "ranking": {"ordered_ids": ["T01"], "ties": [], "top_k": ["T01"], "k_value": 1},
    "coverage": {"total_proposals": 4, "judged": 4, "structure_complete": 3, "novelty_covered": 1, "feasibility_flagged": 2, "ratio": 1.0},
    "conflicts": [{"item_ids": ["T02", "W02"], "kind": "covered_by_prior_work", "resolution": "flagged", "evidence": "…"}],
    "human_review": [{"proposal_id": "T03", "reason": "…", "needed_action": "…"}],
    "risks": [{"risk_id": "R01", "proposal_id": "T01", "description": "…", "mitigation": "…"}],
    "alternatives": [{"alt_id": "A01", "proposal_id": "T01", "route": "…", "reason": "…"}],
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "assessed | partially_assessed | not_assessed | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "分级+对照结论+分数", "kind": "reported | inferred", "source_id": "T01", "location": "proposals[0]", "evidence": [{"paragraph_id": "known_works[1].abstract", "quote": "已知工作原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. novelty_grade / overlap / kind / feasibility.status / feasibility_verdict / confidence / verdict / run_status.state 枚举非法。
2. 要素覆盖：judged 选题四要素有空且未登记 missing_elements；feasibility 四要素缺项或 status 为空；分级但要素不全未登记。
3. 口径与复算：rubric 未事前声明（declared_at 空 / grade_rules 空 / 权重合计≠1.0）；fused_score 复算不符；ranking.ordered_ids 与复算顺序不一致；rank 名次不连续；overlap=covered 却分级 not not_novel；breakthrough/strong 却无 overlap=none 陈述。
4. 评估回证：judged 无 rationale；novelty_claims 的 evidence_quote 为空或未在 claims 逐字回证；fused_score 数字无回证 → unbacked_numbers 判 FAIL；overlap=none/uncertain 却无 closest_work_id 或 evidence。
5. 登记：grade=uncertain、missing_elements 非空、feasibility missing/assumption、duplicate_of/escalated 未进 human_review；duplicate_of 未在 conflicts 登记；coverage 汇总与实际条目不符；verdict 与评估进度矛盾；steps 为空或无可执行 command。
6. 闸门（case_contract / rubric_ledger / ranking_recompute / novelty_rank_output）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，选题与已知工作均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/novelty_rank.py --result examples/example-result.json --k 3 --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --rubric /tmp/wk/rubric.json --out /tmp/vc.json && python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 已知工作清单缺失 / 对照不到 | novelty_claims 标 uncertain、分级降为 uncertain、登记 human_review，绝不写"尚无人研究" |
| 选题要素写不出 | missing_elements 登记具体缺项 + 置信度降级 + human_review，不硬凑可检验表述 |
| 可行性前提无来源 | status=assumption 且 basis 写明"假设"，登记 human_review；结论改 conditional |
| 证据互相冲突 | uncertainties.conflicts 登记双方 + 声明采用的优先序，不混用两套口径 |
| 选题重复 / 与已知工作重复 | duplicate_of + conflicts 登记 flagged（标 not_novel）；无法确认则 escalated 进 human_review |
| 重度同分 | novelty_rank 把并列组记入 ties，按 tie_break 规则破平并在 ranking 可见，不静默改分 |
| 算力/时间不足或运行中断 | 保留已评估部分写 result.json，status=partial，changelog 注明截断/中断位置（协议第 8 条） |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 重跑；修不了就如实登记 uncertainties，绝不中断交付 |

## 已知限制
- 仅对照输入 known_works 清单内的工作：不做实时数据库检索、不全文精读；"新颖"仅指"在给定清单范围内未见覆盖"，外部新颖性不作断言。
- novelty/feasibility/evidence 三因子与五级分级口径按 rubric 事前声明，口径是本技能设定（论文/平台未给定时按量级保守设定并写明），不冒充外部标准。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
