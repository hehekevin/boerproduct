---
name: deep-research-loop
description: Deep-research evidence-synthesis skill (pre-declared research plan / iterative retrieve-synthesize-gap loop with full trace / strength-tagged conclusions aligned to sources / divergent views side-by-side / open-questions registry). Declares a sub-question plan (dependency DAG, evidence needs, search queries, stop rules, convergence criteria) BEFORE any retrieval, runs traceable rounds (queries_run, sources_found, synthesis_note, artifacts_ref), tags every conclusion with strength (strong needs >=2 independent quoted sources; material_fact must link sources; unverified carries none), back-checks every quote verbatim through the claims chain, presents conflicting views side-by-side without picking a side, and registers every unanswered/partial sub-question into open_questions with needed_action. Verify_check mechanically re-audits plan declaration, round traceability, conclusion-evidence alignment and registry completeness, re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency into result.json. Use when the task asks to decompose a research question, run multi-step retrieval-synthesis iterations, synthesize evidence with per-claim provenance, and keep the whole path replayable.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 plan / iterations / findings / divergent_views / open_questions / coverage / strength_summary / plan_audit / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **计划全覆盖**：plan 中**每个**子问题必须有结论（finding）或登记进 open_questions，禁止只处理前几个就收尾；以实际输入文件为准，不依据领域标签假设内容、不补造文献。
4. **不编造**：来源 quote 必须逐字摘自实际输入并附位置；每个结论的 source_id 必须出现在某轮 `sources_found` 中（检索留痕可回放）；对不上就登记 open_questions，不改证据凑结论。
5. **计划事前声明**：plan（子问题+依赖+证据需求+检索式+停止规则+收敛判据）必须在**任何检索迭代之前**写定（declared_at）并通过 plan_audit；声明后禁止调整，不得事后改计划凑结果。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增迭代，用现有中间结果完成 result.json 并收尾（status 如实填 partial，末轮 next_action= budget_stop）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定研究问题与研究来源集合（真实署名文献/记录 + 可能混入的冲突夹具），完成**计划拆解、逐轮检索-综合-缺口迭代留痕、带强度标注的证据综合、分歧并陈、未决问题登记**。数据库实时接入、单篇全文精读、文献元数据审查不在范围；检索无结果、来源冲突、材料缺失照实登记，不脑补。
关键词：拆得开（子问题可独立检索、依赖成 DAG）· 走得留痕（每轮检索式/来源/综合/缺口可回放）· 对得上（结论-证据逐字回链、强度与来源数一致）· 交得清（分歧并陈、未决问题可执行）。
- 输入：`/input/case.json`（研究问题 + 材料/来源 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–7 线性推进，禁止分支回环。

## 八步流程

### Step 0 — 自动落骨架与来源清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（sub_questions/sources/records 等共 5+10 组键）提取建议子问题与来源预填 `result.plan.sub_questions`；生成 `/app/work/plan.json` 计划声明模板。
- 脚本失败时手工兜底：读 case.json 抄子问题/来源与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 研究计划事前声明并审计（1 次响应 + 1 次脚本，任何迭代之前）
- 填 `result.plan`：每个子问题 `{sq_id, text, depends_on[], evidence_needs, search_queries[], stop_rule}`；依赖必须成 DAG（有向无环）；`convergence` 声明收敛判据与最大轮数；同步 /app/work/plan.json。**声明后禁止调整。**
```bash
python3 /skills/weekly-skill/scripts/plan_audit.py --result /app/output/result.json --work-dir /app/work
```
- 审计通过（state=declared）才进入 Step 2；失败按 problems 修 plan 后重跑。

### Step 2 — 逐轮检索-综合-缺口迭代（1-3 次响应，广度优先）
每轮向 `result.iterations[]` 追加一条（round_id 必须 R1、R2…顺序编号），字段缺一不可：
- `sq_ids_targeted` ⊆ 计划子问题集合；`queries_run` 本轮实际检索式；`sources_found` 命中来源 id；
- `synthesis_note` 本轮综合一句话；`gaps_found` 本轮发现的证据缺口；`next_action` ∈ continue/converged/budget_stop/blocked；`artifacts_ref` 本轮中间产物路径；`status` ∈ done/failed_with_record/skipped。
- 工具失败与检索为空照实记录（status=failed_with_record + note），不重试到死；预算触顶按协议第 6 条。

### Step 3 — 结论、分歧与未决问题（1 次响应）
- `result.findings[]`：每条 `{finding_id, text, kind, strength, sq_ids[], sources[], confidence_basis}`。
  - `kind` ∈ material_fact（材料事实，必须有来源）/ inference（合理推断，须写明推断基础）/ uncertain（无法确定）；
  - `strength` ∈ strong（≥2 个独立来源带 quote+location 且方向一致）/ moderate（1 个带引文来源）/ weak（间接/冲突/单一弱设计）/ unverified（无来源，sources 必须为空）；
  - 每条带来源结论在 `claims[]` 有对应条目（source_id=finding_id，evidence 逐字收录全部来源引文）。
- `result.divergent_views[]`：冲突研究结论**双方并陈**（每个 view 有 claim+source_ids），不做静默取舍；`handling` ∈ presented_side_by_side/weighed/unresolved；unresolved 必须填 `open_question_ref`。
- `result.open_questions[]`：无中等以上强度结论的子问题**逐条登记** `{oq_id, question, related_sq_ids, reason, needed_action}`——研究空白必须写明来自哪个检索缺口（引用 gaps_found），不写套话。
- `result.verdict`（verdict_basis 一句话写依据）：`synthesized` 全部子问题 answered；`partially_synthesized` 部分 answered；`not_synthesized` 无有效结论；`cannot_verify` 材料缺口导致无法判定且 material_gaps 非空。

### Step 4 — 覆盖面与强度机械汇总（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/coverage_calc.py --result /app/output/result.json --work-dir /app/work
```
- 机械汇总 `result.coverage`（answered/partially_answered/unanswered/ratio）与 `result.strength_summary`（四档计数）；verify_check 会独立复算对照，手改数字必被抓。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭计划声明/迭代留痕/证据对齐/未决登记），把**真实数字**写进 `result.gain_evidence`：`runs[]`、`delta_normal_minus_degraded`、`mechanism_to_metric_map`、`boundaries`、`failure_conditions`。
- 五项对照指标：计划违规漏检 / 留痕漏检 / 证据对齐漏检 / 未决漏登记 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- `--inject-pollution` 在**副本**上注入 5 项污染（strong 清来源/清 claims/清 open_questions/清 declared_at/清 queries_run）：正常模式须抓到（`caught_by_normal_mode=true`），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence` = `{available:false, reason:"…"}`，不得编数字。
- 退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每个子问题都有结论或登记未决吗？每条结论都能回链到具体来源引文与某轮检索吗？分歧双方并陈了吗？
- 收尾：`result.run_status` = `{state ∈ success|partial|unable_to_determine|refused, reason, manual_takeover[]}`，非 success 必写 reason；`changelog` 记录全部阶段动作。

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "…", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"question": "…", "scope": "…", "time_range": "…"},
    "plan": {"declared_at": "step1", "sub_questions": [{"sq_id": "SQ-01", "text": "…", "depends_on": [], "evidence_needs": "…", "search_queries": ["…"], "stop_rule": "…"}],
             "convergence": {"rule": "…", "criteria": ["…"]}},
    "iterations": [{"round_id": "R1", "sq_ids_targeted": ["SQ-01"], "action": "…", "queries_run": ["…"], "sources_found": ["S01"], "synthesis_note": "…", "gaps_found": [], "next_action": "continue", "artifacts_ref": "iterations/R1.md", "status": "done"}],
    "findings": [{"finding_id": "F1", "text": "…", "kind": "material_fact", "strength": "strong", "sq_ids": ["SQ-01"],
                  "sources": [{"source_id": "S01", "location": "sources[0].content", "quote": "逐字引文"}], "confidence_basis": "…"}],
    "divergent_views": [{"topic_id": "V1", "topic": "…", "views": [{"side": "…", "claim": "…", "source_ids": ["S04"]}], "handling": "unresolved", "open_question_ref": "OQ-01"}],
    "open_questions": [{"oq_id": "OQ-01", "question": "…", "related_sq_ids": ["SQ-03"], "reason": "来自哪个检索缺口", "needed_action": "…"}],
    "coverage": {"sub_questions_total": 3, "answered": 2, "partially_answered": 1, "unanswered": 0, "answered_ratio": 0.6667},
    "strength_summary": {"strong": 1, "moderate": 1, "weak": 2, "unverified": 0, "total": 4},
    "plan_audit": {"state": "declared", "declared_at": "…", "digest": "sha256前16位", "problems": []},
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "synthesized | partially_synthesized | not_synthesized | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "结论+强度+来源说明", "kind": "reported | inferred", "source_id": "F1", "location": "result.findings[0]", "evidence": [{"paragraph_id": "sources[0].content", "quote": "逐字引文"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py 四组消融开关 plan/trace/evidence/registry）
1. strength / kind / handling / status / verdict / run_status.state 枚举非法。
2. **plan 组**：declared_at 或 convergence.rule 为空；sq_id 重复；evidence_needs/search_queries 缺失；depends_on 引用不存在或成环；findings/iterations 的 sq_ids 越出计划集合；依赖未满足先出结论；plan_audit.state≠declared。
3. **trace 组**：iterations 为空；round_id 不按 R1..Rn 顺序；queries_run/synthesis_note/artifacts_ref/sq_ids_targeted 缺失；结论来源不在任何轮 sources_found（检索留痕缺口）；末轮 next_action 未记录。
4. **evidence 组**：strong 带 quote 来源 <2；moderate 无带引文来源；unverified 却带来源；material_fact 无来源；结论引文在 claims 无逐字回证（空白归一化子串匹配）→ unbacked_numbers 判 FAIL；分歧未双方并陈。
5. **registry 组**：unanswered/partially 子问题未登记 open_questions；open_questions 缺 reason/needed_action；unresolved 分歧未指向有效 open_question_ref。
6. coverage / strength_summary 与实际不符；verdict 与进度矛盾；steps 为空或无可执行 command。
7. 闸门（case_contract / plan_ledger / iteration_replay / findings_chain）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，研究问题与来源均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/plan_audit.py --result examples/example-result.json --work-dir /tmp/wk
python3 scripts/coverage_calc.py --result examples/example-result.json --work-dir /tmp/wk
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/sg.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 检索无结果 / 来源集合为空 | findings 空、coverage.total=0、verdict=cannot_verify 或 not_synthesized，status 写明，绝不补造来源 |
| 来源互相冲突 | 双方并陈进 divergent_views（各带 claim+source_ids）；unresolved 则登记 open_questions，不取一方 |
| 计划与材料对不上（子问题无法检索） | 不改已锁定计划：照实执行可执行部分，缺口登记 open_questions + material_gaps |
| 工具报错/限流/解析失败 | 该轮 status=failed_with_record，gaps_found 写明失败点；连续失败 next_action=blocked 并人工接管 |
| 强度无法定级 | 按下限标 weak/unverified，never 高估；unverified 必须 sources=[] |
| 算力/时间不足 | 保留已完成轮次，status=partial，末轮 next_action=budget_stop，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅处理输入来源集合内材料：不做数据库实时检索、不全文精读、不做元数据方法学审查。
- strength 判级口径（strong=≥2 独立带引文来源方向一致等）是本技能事前设定的机械规则，不冒充外部标准；方向一致性由 Agent 判定，校验器只核对来源数量与引文回证。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照（平台白板由平台生成）；追问轮次按每轮 3 条折算的估计量，原始计数一并落盘。
