---
name: paper-review-audit
description: Paper quality review skill (six-facet audit / located findings / severity grading / false-positive suppression / pending-review registry). Audits a fixed manuscript across six facets (fact_check, citation_support, method_design, stat_reporting, argument_chain, integrity_norms) and emits an itemized, source-locatable findings list: every finding carries a verbatim quote, a section/paragraph location, a severity (critical/major/minor) graded under a rubric declared before any judgment, a category (fact_error / insufficient_evidence / norm_issue / suggestion) and a revision suggestion. Suppresses false positives via pre-declared rules (discipline writing conventions, journal format differences, author trade-offs are NOT defects), registers unverifiable items as pending review instead of inventing conclusions, and records material gaps honestly. Coverage_audit mechanically audits six-facet and section coverage; verify_check back-checks every quote against the actual manuscript text, severity mapping, claims evidence chain and pending/suppressed registries; gain_probe re-runs normal-vs-degraded ablation on the same input and embeds measured gain_evidence and efficiency counters into result.json. Use when the task asks to review a paper for quality, citations, facts, methods, statistics, logic or norms with per-item evidence and severity.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 findings / suppressed / pending_review / clearances / coverage / unchecked / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **六分面全覆盖**：事实核验、引用支持、方法设计、统计报告、论证链、学术规范六个分面逐一过稿，与稿件相关的分面缺一不可；零发现分面须在 unchecked/clearances 登记原因，禁止静默跳过。
4. **不编造**：每条 finding 的 quote 必须逐字摘自实际稿件原文并附位置（原文不在稿件中的引文 = 定位失据）；被引文献主张读不到就标 pending，不凭空补结论；无法读的图表登记 material_gaps。
5. **口径事前声明**：severity_rubric 三级口径（critical/major/minor 判据）与误报抑制规则（FP-xx）必须在**任何逐条判定之前**写定（declared_at），之后禁止调整；判定必须可映射回口径。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定一篇固定稿件（论文/科研材料）与审查要求，完成**六分面逐条问题清单（原文位置 + 严重度 + 修改建议）、四类区分（事实错误/证据不足/规范问题/建议）、误报抑制、待复核登记**。论文润色改写、语言翻译、查重比对、投稿排版等事务性工作不在范围；稿件解析失败、图表不可读、参考文献缺失照实登记，不脑补。
关键词：查得全（六分面 + 章节双覆盖）· 定得准（逐条可回原文）· 分得清（四类 × 三级口径）· 压得住（学科惯例不算缺陷）· 交得实（待复核与缺口全登记）。
- 输入：`/input/case.json`（稿件 + 审查要求 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与稿件结构清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（manuscript/paper/document 等）提取章节结构预填 `result.manuscript_overview`；生成 `/app/work/severity_rubric.json` 口径模板；校验挂载标志文件（技能根 SKILL.md）。
- 脚本失败时手工兜底：读 case.json 抄稿件结构与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 严重度口径与误报抑制规则（1 次响应，判定前完成）
- **事前声明 severity_rubric**：`result.severity_rubric.levels` = {critical/major/minor 各一句话判据}，declared_at 必填，同步写 /app/work/severity_rubric.json。机械映射：suggestion ⇒ minor；fact_error ⇒ critical/major。**声明后禁止调整。**
- **事前声明 suppression_rules**：FP-01 学科写作惯例（作者自陈局限、惯用转承语）、FP-02 期刊格式差异、FP-03 作者有意取舍；判"不算缺陷"必须引用 rule_id。

### Step 2 — 六分面逐条审查（2-4 次响应，广度优先）
对六个分面逐一过稿，每条发现写入 `result.findings[]`，缺一不可：
- `quote` 逐字摘自稿件原文 + `location` 注明章节/句位 + `section_id`/`source_ref`；
- `facet` ∈ fact_check/citation_support/method_design/stat_reporting/argument_chain/integrity_norms；`category` ∈ fact_error/insufficient_evidence/norm_issue/suggestion；`severity` 按 Step 1 口径；
- `evidence` 写明判断依据（引用主张与论断对照、数据前后对照等）；fact_error 必须给对照依据；每条 confirmed 给 `revision_suggestion`；
- 无法确认 → `status=pending` + pending_reason；判为学科惯例/格式差异 → `status=suppressed` + suppressed_by=FP-xx（仍登记，不静默丢弃）。

### Step 3 — 六项覆盖机械审计（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/coverage_audit.py --result /app/output/result.json \
  --case /input/case.json --input-root /input --emit-into
```
- 机械计数六分面/类别/严重度/章节覆盖，回写 `result.coverage` 与 `result.unchecked`；零发现分面或章节且未登记 clearances 豁免 → 进 unchecked（verdict 不得为 audited）。
- 脚本失败时手工兜底：手算各分面计数并写 steps 注明「手算」。

### Step 4 — 待复核登记与证据链（1 次响应）
- `result.pending_review[]`：**每个 status=pending 发现**登记 `{finding_id, reason, needed_action}`；
- `result.suppressed[]`：每个 suppressed 发现登记 `{finding_id, rule_id, reason}`；`result.clearances[]`：已查无问题或材料不可读的显式豁免（如 `artifact:图2`）；
- `claims[]`：每条 confirmed 发现一条 `{claim_id, text, kind: reported|inferred, source_id=finding_id, location, evidence:[{paragraph_id, quote}]}`，quote 与 finding.quote 逐字一致（空白归一化后须逐字回证于稿件原文）；
- 结论分级 `result.verdict`：`audited`（六分面全覆盖且全部判定且 unchecked 空）/ `partially_audited` / `not_audited` / `cannot_verify`（material_gaps 非空）；运行状态 `result.run_status` 非 success 必须写 reason。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭定位回证/严重度口径/证据链/待复核登记），把**真实数字**写进 `result.gain_evidence`：runs、delta_normal_minus_degraded、mechanism_to_metric_map、boundaries、failure_conditions。
- 五项对照指标：定位失据漏检 / 分级口径违规漏检 / 证据缺失漏检 / 待复核漏登记 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- 同时写 `result.efficiency`；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- `--inject-pollution` 在**副本**上注入污染（清空引文定位/清空对照依据/清空待复核/清空证据链）做反例自测：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence = {available:false, reason:…}`；退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --ledger /app/work/severity_rubric.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：六分面每面都查过或有豁免登记吗？每条 confirmed 的引文都能回原文逐字命中吗？待定与被抑制的发现都登记了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "manuscript_overview": {"title": "…", "sections": [{"section_id": "S1", "name": "摘要", "source_ref": "manuscript.sections[0]"}], "reference_count": 12},
    "severity_rubric": {"levels": {"critical": "…", "major": "…", "minor": "…"}, "declared_at": "step1", "note": "…"},
    "suppression_rules": [{"rule_id": "FP-01", "text": "学科写作惯例不算缺陷"}],
    "facets": {"fact_check": "…", "citation_support": "…", "method_design": "…", "stat_reporting": "…", "argument_chain": "…", "integrity_norms": "…"},
    "findings": [{"finding_id": "F01", "source_ref": "manuscript.sections[0].text", "section_id": "S1", "location": "S1 摘要 第2句", "facet": "fact_check", "category": "fact_error", "severity": "critical", "quote": "逐字摘录", "evidence": "对照依据", "revision_suggestion": "…", "status": "confirmed", "pending_reason": null, "suppressed_by": null, "judged": true}],
    "suppressed": [{"finding_id": "F09", "rule_id": "FP-01", "reason": "…"}],
    "pending_review": [{"finding_id": "F08", "reason": "…", "needed_action": "…"}],
    "clearances": [{"scope": "artifact:图2", "reason": "扫描件无法读取"}],
    "coverage": {"total_sections": 5, "sections_with_findings": 5, "total_findings": 9, "judged": 9, "confirmed": 7, "pending": 1, "suppressed": 1, "facet_counts": {}, "category_counts": {}, "severity_counts": {}, "per_section": {}},
    "unchecked": [], "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "audited | partially_audited | not_audited | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "…", "kind": "reported | inferred", "source_id": "F01", "location": "findings[0]", "evidence": [{"paragraph_id": "manuscript.sections[0].text", "quote": "稿件原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. facet / category / severity / status / run_status.state 枚举非法。
2. confirmed 的 quote 不在稿件原文中或 location 为空（定位可回证失败）。
3. severity_rubric 未事前声明；suggestion≠minor；fact_error 标 minor（分级口径违规）。
4. confirmed 无 claims 逐字回证；fact_error 无对照依据；已判定无 revision_suggestion。
5. pending 未登记 pending_review（缺 reason/needed_action）；suppressed 未登记 suppressed[] 或 rule_id 不在事前规则表。
6. coverage 汇总/facet_counts 与实际不符；零发现分面未登记；unchecked 非空却判 audited；verdict 与判定进度矛盾；steps 为空或无可执行 command。
7. 闸门（case_contract / severity_ledger / coverage_audit_output）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，论文/数据/文献均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/coverage_audit.py --result examples/example-result.json --case examples/example-case.json --input-root examples --emit-into
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk/severity_rubric.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 稿件解析失败 / 输入不可读 | material_gaps 登记、status=input_error 或 insufficient_evidence、verdict=cannot_verify，绝不编造审查结论 |
| 图表无法读取 | clearances 登记 `artifact:*` 豁免 + material_gaps 注明，图内一致性如实标未检查 |
| 参考文献缺失/全文未获取 | 引用支持性标 pending + 登记 pending_review（含 needed_action），不凭空补结论 |
| 学科惯例/格式差异 | 按 suppression_rules（FP-xx）标 suppressed 并登记，不判缺陷也不静默丢弃 |
| 稿件超长/预算不足 | 保留已审部分，unchecked 登记未审范围，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅审查输入稿件本身与其自带参考文献：不做外部检索、不查重、不润色改写。
- 严重度口径与误报抑制规则是本技能事前声明的设定（题面未给定时按量级保守设定并写明），不冒充期刊官方标准。
- 引文回证是"逐字出现于稿件原文"的机械校验，不能替代被引文献实际主张的语义核对（读不到文献时标 pending）。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
