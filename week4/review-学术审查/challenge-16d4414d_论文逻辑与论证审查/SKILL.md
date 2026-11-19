---
name: argchain-review
description: Paper logic & argumentation review skill (argument-chain tracing / typed logic defects / conclusion-evidence strength matching / located findings / pending-review registry). Traces each argument chain node by node (hypothesis, premise, reasoning, conclusion) with verbatim quotes and sentence-level locations; identifies and types logic defects under a taxonomy declared before any judgment (broken_chain, circular_reasoning, correlation_causation, over_extrapolation, strength_mismatch, missing_rebuttal); checks conclusion-evidence strength matching against a pre-declared two-sided scale (evidence E3-E0 vs claim C3-C1, verdict registered as supported/overstated/pending per claim); verifies rebuttal and limitation coverage; suppresses false positives via pre-declared rules (control groups, explicitly marked hypotheticals, cited opinions of others are NOT author self-contradiction); chains_audit mechanically audits chain node completeness (every chain needs a premise and a conclusion, node quotes must be back-evidenced) and six-facet/section coverage; verify_check back-checks every quote against the actual manuscript, taxonomy and severity mapping, chain node completeness, strength-match registration and pending/suppressed registries; gain_probe re-runs normal-vs-degraded ablation on the same input and embeds measured gain_evidence and efficiency counters into result.json. Use when the task asks to review a paper's logic and argumentation: broken reasoning, circular arguments, correlation presented as causation, conclusions exceeding the evidence, missing rebuttals or limitations, with per-item evidence and severity.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 argument_chains / findings / strength_matches / suppressed / pending_review / coverage / unchecked / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **三个口径判定前声明**：severity_rubric 三级判据、issue_taxonomy 六类问题定义、strength_scale 双侧强度标尺，必须在**任何逐条判定之前**写定（declared_at），同步落 /app/work/rubrics.json，声明后禁止调整；判定必须可映射回口径。
4. **不编造**：每条 finding 与链节点的 quote 必须逐字摘自实际稿件原文并附句位；作者有意设置的对照组、明确标注的假设情形、转述他人观点不得报成作者自相矛盾（FP-01/02/03 事前声明）；无法确认标 pending 并登记，不凭空补结论。
5. **论证链逐环定位**：每条主论证链（argument_chains[]）节点角色 ∈ hypothesis/premise/reasoning/conclusion，链节点完备性由 chain_audit.py 机械审计——缺前提或缺结论的链必须落 unchecked。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定一篇固定稿件与审查要求，完成**论证链逐环追踪（假设→前提→推理→结论，逐节点定位）+ 六类逻辑问题清单（断链/循环论证/因果相关混淆/外推超界/强度不匹配/反驳缺失，原文位置 + 严重度 + 可执行建议）+ 结论-证据强度匹配判定登记 + 反驳与局限性覆盖检查**。文字润色、查重、文献格式、统计复算、投稿策略不在范围；稿件解析失败、图表不可读、参考文献缺失照实登记，不脑补。
关键词：追得全（链节点逐环定位）· 分得清（六类口径一致）· 配得准（强度双侧标尺）· 压得住（假设/对照/转述不误报）· 交得实（待复核与缺口全登记）。
- 输入：`/input/case.json`（稿件 + 审查要求 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与稿件结构清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键提取章节结构预填 `result.manuscript_overview`；生成 /app/work/rubrics.json（三级口径 + 六类问题 + 强度标尺三合一模板）；校验技能标志文件（技能根 SKILL.md）。
- 脚本失败时手工兜底：读 case.json 抄稿件结构与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 三个口径事前声明（1 次响应，判定前完成）
- **severity_rubric**：critical=断链/因果冒充等直接影响主结论的缺陷；major=外推超界、强度不匹配等削弱结论但可修正；minor=局部表述或覆盖建议。suggestion ⇒ minor。
- **issue_taxonomy** 六类定义（每条发现 issue_type 必居其一）：broken_chain=前提与结论之间缺必要推理环节或隐含假设未交代；circular_reasoning=结论（或其等价改写）被用作前提；correlation_causation=仅相关/观察证据却做因果表述；over_extrapolation=超出样本、场景或时限的推广；strength_mismatch=结论强度超出证据等级；missing_rebuttal=对明显替代解释或已知反例无讨论且未声明局限。
- **strength_scale**：证据侧 E3=对照/实验/定量复现，E2=观察性相关或单点定量，E1=个案/转述/权威断言，E0=无实证；主张侧 C3=因果断言或普遍推广，C2=限定条件下的相关结论，C1=假说性表述。匹配规则：C3 须 E3；C2 须 ≥E2；E0 不得支撑任何 confirmed 结论。三个口径同步写入 rubrics.json，declared_at 必填，之后禁止调整。

### Step 2 — 论证链追踪 + 六类逐条审查（2-4 次响应，广度优先）
- **先抽链**：对每条主论证建 `result.argument_chains[]`：`{chain_id, name, nodes:[{node_id, role ∈ hypothesis/premise/reasoning/conclusion, quote 逐字, section_id, location}]}`；假设情形、对照设置、转述观点按 FP-01/02/03 不入作者自己的链。
- **再逐条发现**写入 `result.findings[]`：`issue_type` 六类之一 + `facet` ∈ argument_chain/strength_match/rebuttal_coverage/cross_section + `category` ∈ fact_error/insufficient_evidence/norm_issue/suggestion + severity 按 Step 1；`quote` 逐字 + `location` 句位 + `chain_ref`（命中的链节点）；`evidence` 写明判断依据（前提-结论对照、证据等级-结论强度对照）；每条 confirmed 给可执行 `revision_suggestion`（说清补什么证据/改哪句/把哪个结论强度降下来）。
- 无法确认 → `status=pending` + pending_reason；判为学科惯例/有意取舍 → `status=suppressed` + suppressed_by=FP-xx（仍登记，不静默丢弃）。

### Step 3 — 链完备与覆盖机械审计（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/chain_audit.py --result /app/output/result.json \
  --case /input/case.json --input-root /input --emit-into
```
- 机械审计两件事：① 每条链节点完备性（缺 premise / 缺 conclusion / 节点 quote 过短）→ `result.chain_audit`；② 六分面/类别/严重度/章节覆盖计数 → `result.coverage`；零发现分面或章节且未登记 clearances → 进 unchecked（verdict 不得为 audited）。脚本失败时手工兜底并写 steps 注明「手算」。

### Step 4 — 强度匹配登记与待复核（1 次响应）
- **强度匹配判定登记**：对稿件每条核心结论建 `result.strength_matches[]`：`{match_id, finding_id 或 null, claim_quote, claim_strength(C1-C3), evidence_strength(E0-E3), verdict ∈ supported/overstated/understated/pending, basis}`；overstated 必须对应一条 strength_mismatch 发现。
- `result.pending_review[]`：每个 pending 发现登记 `{finding_id, reason, needed_action}`；`result.suppressed[]`：`{finding_id, rule_id, reason}`；`result.clearances[]`：已查无问题或材料不可读的显式豁免（如 `artifact:图2`）。
- `claims[]`：每条 confirmed 发现一条 `{claim_id, text, kind: reported|inferred, source_id=finding_id, evidence:[{paragraph_id, quote}]}`，quote 与 finding.quote 逐字一致（空白归一化后须回证于稿件原文）。
- `result.verdict`：`audited`（覆盖齐、全部判定且 unchecked 空）/ `partially_audited` / `not_audited` / `cannot_verify`（material_gaps 非空）；`run_status` 非 success 必写 reason。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（五组机械校验全开）与退化模式（--ablate all：关闭定位回证/分类口径/强度匹配/链完备/待复核登记），把**真实数字**写进 `result.gain_evidence`：runs、delta_normal_minus_degraded、mechanism_to_metric_map、boundaries、failure_conditions。
- 对照指标：定位失据漏检 / 分类口径违规漏检 / 强度登记缺失漏检 / 链完备违规漏检 / 待复核漏登记 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**；同时写 `result.efficiency`（model_requests 由 Agent 回填，缺失保持 null）。
- `--inject-pollution` 在**副本**上注入污染（清空引文定位/篡改问题类型/清空强度登记/删链节点/清空待复核）做反例自测：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。跑不了时手工写 `gain_evidence={available:false, reason:…}`；退化模式结果仅用于增益对照，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --ledger /app/work/rubrics.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每条 confirmed 的引文都能回原文逐字命中吗？每条 issue_type 都能映射回事前口径吗？每条核心结论都登记了强度匹配判定吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "manuscript_overview": {"title": "…", "sections": [{"section_id": "S1", "name": "摘要", "source_ref": "manuscript.sections[0]"}], "reference_count": 12},
    "severity_rubric": {"levels": {"critical": "…", "major": "…", "minor": "…"}, "declared_at": "step1", "note": "…"},
    "issue_taxonomy": {"types": {"broken_chain": "…", "circular_reasoning": "…", "correlation_causation": "…", "over_extrapolation": "…", "strength_mismatch": "…", "missing_rebuttal": "…"}, "declared_at": "step1"},
    "strength_scale": {"evidence_levels": {"E3": "…", "E2": "…", "E1": "…", "E0": "…"}, "claim_levels": {"C3": "…", "C2": "…", "C1": "…"}, "rule": "C3须E3；C2须≥E2；E0不得支撑confirmed结论", "declared_at": "step1"},
    "suppression_rules": [{"rule_id": "FP-01", "text": "作者有意设置的对照组/明确标注的假设情形不是自相矛盾"}],
    "facets": {"argument_chain": "…", "strength_match": "…", "rebuttal_coverage": "…", "cross_section": "…", "fact_check": "…", "integrity_norms": "…"},
    "argument_chains": [{"chain_id": "C1", "name": "主论证", "nodes": [{"node_id": "C1-N1", "role": "premise", "quote": "逐字摘录", "section_id": "S3", "location": "S3 第2句"}]}],
    "findings": [{"finding_id": "F01", "source_ref": "manuscript.sections[4].text", "section_id": "S5", "location": "S5 第1句", "facet": "strength_match", "issue_type": "correlation_causation", "category": "fact_error", "severity": "critical", "quote": "逐字摘录", "chain_ref": "C1-N3", "evidence": "对照依据", "revision_suggestion": "…", "status": "confirmed", "pending_reason": null, "suppressed_by": null, "judged": true}],
    "strength_matches": [{"match_id": "M01", "finding_id": "F01", "claim_quote": "…", "claim_strength": "C3", "evidence_strength": "E2", "verdict": "overstated", "basis": "…"}],
    "suppressed": [{"finding_id": "F09", "rule_id": "FP-01", "reason": "…"}],
    "pending_review": [{"finding_id": "F08", "reason": "…", "needed_action": "…"}],
    "clearances": [{"scope": "artifact:图2", "reason": "扫描件无法读取"}],
    "coverage": {"total_sections": 5, "sections_with_findings": 4, "total_findings": 9, "judged": 9, "confirmed": 7, "pending": 1, "suppressed": 1, "facet_counts": {}, "issue_type_counts": {}, "category_counts": {}, "severity_counts": {}, "per_section": {}},
    "unchecked": [], "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "audited | partially_audited | not_audited | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "…", "kind": "reported | inferred", "source_id": "F01", "location": "findings[0]", "evidence": [{"paragraph_id": "manuscript.sections[4].text", "quote": "稿件原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py 五组）
1. **定位可回证**：confirmed 的 quote 不在稿件原文中或 location 为空；链节点 quote 不在原文中。
2. **分类口径一致**：issue_taxonomy 未事前声明；issue_type 不在六类枚举；severity 枚举非法；suggestion≠minor；fact_error 标 minor。
3. **强度匹配登记**：strength_scale 未事前声明；核心结论缺 strength_matches 登记；verdict=overstated 却无对应发现；C3 配 E2 以下未标 overstated。
4. **链节点完备**：链缺 premise 或缺 conclusion；finding.chain_ref 指向不存在的节点。
5. **登记与一致性**：pending 未登记（缺 reason/needed_action）；suppressed 的 rule_id 不在事前规则表；coverage 与实际不符；零发现分面未登记；unchecked 非空却判 audited；steps 为空；闸门非 enforced 时 warn——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，论文/数据/文献均为虚构，已标注示意），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/chain_audit.py --result examples/example-result.json --case examples/example-case.json --input-root examples --emit-into
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk/rubrics.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 稿件解析失败 / 输入不可读 | material_gaps 登记、status=input_error 或 insufficient_evidence、verdict=cannot_verify，绝不编造审查结论 |
| 图表无法读取 | clearances 登记 `artifact:*` 豁免 + material_gaps 注明，图内一致性如实标未检查 |
| 参考文献缺失/全文未获取 | 引用支持性标 pending + 登记 pending_review（含 needed_action），不凭空补结论 |
| 对照组/假设情形/转述观点 | 按 suppression_rules（FP-01/02/03）标 suppressed 并登记，不报成作者自相矛盾 |
| 稿件超长/预算不足 | 保留已审部分，unchecked 登记未审范围，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅审查输入稿件本身与其自带参考文献：不做外部检索、不查重、不润色改写。
- 三个口径（严重度/问题类型/强度标尺）是本技能事前声明的设定（题面未给定时按量级保守设定并写明），不冒充期刊官方标准。
- 引文回证是"逐字出现于稿件原文"的机械校验；论证链抽取靠语义判断，机械审计只保证节点完备与引文可回证，不保证链的语义无遗漏。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
