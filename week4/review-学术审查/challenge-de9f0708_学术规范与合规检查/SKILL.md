---
name: paper-compliance-audit
description: Academic norms & compliance audit skill (declaration-existence mechanical scan / three-class findings / format-rule binding / located evidence / ablation gain probe). Audits a fixed manuscript across eight compliance facets (data_availability, ethics, conflict_of_interest, author_contributions, funding, copyright_license, reference_format, duplicate_publication) and emits an itemized, source-locatable findings list. Every finding carries a verbatim quote, a section location, one of exactly three classes (norm_missing 规范缺失 / norm_violation 规范不合规 / substantive_issue 实质性学术问题) with a severity graded under a rubric declared before any judgment, a rule_id bound to pre-declared format rules (FR-xx) as the checkable basis, and a revision suggestion. decl_audit.py mechanically scans required declarations (data availability, ethics, COI, contributions, funding, license) with bilingual keywords and records detected/evidence; missing mechanical detections must be covered by a norm_missing finding or an explicit clearance. False positives are suppressed via pre-declared FP rules (discipline conventions, journal format differences are NOT defects) with registry entries, not silent drops; unverifiable items (e.g. prior-publication comparison) are registered pending instead of invented. verify_check back-checks every quote against the actual manuscript, the three-class severity mapping, rule binding, declaration consistency, claims chain and pending/suppressed registries; gain_probe re-runs normal-vs-degraded ablation on the same input and embeds measured gain_evidence and efficiency into result.json. Use when the task asks to check a paper for required declarations, ethics/funding/COI/Copyright compliance, reference format norms or duplicate-publication signs with per-item evidence and basis.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 findings / declaration_audit / format_rules / suppressed / pending_review / clearances / coverage / unchecked / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **八分面全覆盖**：数据可用性、伦理与知情同意、利益冲突、作者贡献、基金资助、版权与许可、参考文献格式、重复发表与一稿多投八个分面逐一过稿；零发现分面须在 unchecked/clearances 登记原因，禁止静默跳过。
4. **三类分开呈现**：每条发现 category 三选一——`norm_missing`（规范缺失：必备声明/信息不存在）/ `norm_violation`（规范不合规：存在但不符合格式规则，须绑定 rule_id）/ `substantive_issue`（实质性学术问题：重复发表、数据复用等实质诚信问题）；不得混写为泛泛的"规范问题"。
5. **依据事前声明、位置逐字回证**：format_rules（FR-xx）与三类×严重度口径必须在**任何逐条判定之前**写定（declared_at），之后禁止调整；每条 finding 的 quote 必须逐字摘自实际稿件原文并附位置；判"不合规"必须引用事前规则条款，不编造期刊要求。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定一篇固定稿件（论文/科研材料）与合规审查要求，完成**八分面逐条合规清单（原文位置 + 三类区分 + 严重度 + 修改建议）+ 必备声明存在性机检 + 格式规则事前声明与依据绑定 + 误报抑制 + 待复核登记**。论文润色改写、语言翻译、查重库比对、投稿排版、法务/伦理委员会正式意见不在范围；稿件解析失败、图表不可读、声明在投稿系统等外部位置照实登记，不脑补。
关键词：查得全（八分面 + 章节双覆盖）· 定得准（逐条可回原文）· 分得清（三类 × 三级口径）· 绑得住（判"不合规"必引事前规则）· 压得住（学科惯例不算缺陷）· 交得实（待复核与缺口全登记）。
- 输入：`/input/case.json`（稿件 + 审查要求 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与稿件结构清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；预填八分面、format_rules（FR-01~08）、declaration_checklist、三类×严重度口径模板；生成 `/app/work/compliance_rubric.json` 口径台账；校验挂载标志文件（技能根 SKILL.md）。
- 脚本失败时手工兜底：读 case.json 抄稿件结构与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 三类口径与规则事前声明（1 次响应，判定前完成）
- **事前声明 compliance_rubric**：`categories`（三类定义）+ `severity_levels`（critical/major/minor 判据）+ `declared_at` 必填，同步写 /app/work/compliance_rubric.json。机械映射：substantive_issue⇒critical/major；norm_missing/norm_violation⇒major/minor。**声明后禁止调整。**
- **核对 format_rules**：FR-01~08 为默认规则（数据可用性/伦理批件号/利益冲突存在性/作者贡献/基金编号/第三方材料许可/参考文献要素/重复发表声明）；题面或目标期刊要求不同时按实际改写并注明来源，改写后同样判定前冻结。判"不算缺陷"引用 FP-01（学科写作惯例）/FP-02（期刊格式差异）/FP-03（作者取舍）。

### Step 2 — 八分面逐条审查（2-4 次响应，广度优先）
对八个分面逐一过稿，每条发现写入 `result.findings[]`：
- `quote` 逐字摘自稿件原文 + `location` 注明章节/句位 + `section_id`/`source_ref`；
- `facet` ∈ 八分面；`category` 三选一；`severity` 按 Step 1 口径；norm_missing/norm_violation 必须给 `rule_id`（FR-xx）；substantive_issue 必须给对照依据 `evidence`；
- 每条 confirmed 给 `revision_suggestion`；无法确认（如重复发表需外部比对、声明在投稿系统）→ `status=pending` + pending_reason + 登记待复核；判为学科惯例/格式差异 → `status=suppressed` + suppressed_by=FP-xx（仍登记，不静默丢弃）。

### Step 3 — 声明存在性机检与覆盖审计（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/decl_audit.py --result /app/output/result.json \
  --case /input/case.json --input-root /input --emit-into
```
- 机械扫描六项必备声明（数据可用性/伦理/利益冲突/作者贡献/基金资助/版权许可），按中英关键词表记录 detected/matched_keywords/sections → `result.declaration_audit`；同时机械计数八分面/三类/严重度/章节覆盖 → `result.coverage` 与 `result.unchecked`。
- **单向对账（verify_check 强制）**：detected=false 的声明必须有一条对应 norm_missing 发现或 clearances/material_gaps 豁免；detected=true 不强制有发现（关键词可能误命中，由语义判断）。零发现分面/章节未登记豁免 → 进 unchecked（verdict 不得为 audited）。
- 脚本失败时手工兜底：手读全文核对六项声明并手算覆盖计数，steps 注明「手算」。

### Step 4 — 待复核登记与证据链（1 次响应）
- `result.pending_review[]`：每个 status=pending 发现登记 `{finding_id, reason, needed_action}`；`result.suppressed[]`：每个 suppressed 发现登记 `{finding_id, rule_id, reason}`；`result.clearances[]`：已查无问题或材料不可读的显式豁免（如 `facet:ethics`、`section:S2`、`decl:copyright_license`）；
- `claims[]`：每条 confirmed 发现一条 `{claim_id, text, kind, source_id=finding_id, location, evidence:[{paragraph_id, quote}]}`，quote 与 finding.quote 逐字一致（空白归一化后须逐字回证于稿件原文）；
- 结论分级 `result.verdict`：`audited`（八分面全覆盖且全部判定且 unchecked 空）/ `partially_audited` / `not_audited` / `cannot_verify`（material_gaps 非空）；运行状态 `result.run_status` 非 success 必须写 reason。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（五组机械校验全开）与退化模式（--ablate all：关闭定位回证/三类口径/规则绑定与声明机检/证据链/待复核登记），把**真实数字**写进 `result.gain_evidence`：runs、delta_normal_minus_degraded、mechanism_to_metric_map、boundaries、failure_conditions。
- 六项对照指标：定位失据漏检 / 三类口径违规漏检 / 依据绑定与声明机检漏检 / 证据缺失漏检 / 待复核漏登记 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- 同时写 `result.efficiency`；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- `--inject-pollution` 在**副本**上注入污染（清空引文定位/抬升 severity 违反三类映射/清空 rule_id/清空待复核/清空证据链）做反例自测：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence = {available:false, reason:…}`；退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --ledger /app/work/compliance_rubric.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：八分面每面都查过或有豁免登记吗？每条判"不合规/缺失"的都引了事前规则、每条 confirmed 的引文都能回原文逐字命中吗？待定与被抑制的发现都登记了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "manuscript_overview": {"title": "…", "sections": [{"section_id": "S1", "name": "摘要", "source_ref": "manuscript.sections[0]"}], "reference_count": 12},
    "compliance_rubric": {"categories": {"norm_missing": "…", "norm_violation": "…", "substantive_issue": "…"}, "severity_levels": {"critical": "…", "major": "…", "minor": "…"}, "mapping": "substantive_issue⇒critical/major；norm_missing/norm_violation⇒major/minor", "declared_at": "step1"},
    "format_rules": [{"rule_id": "FR-01", "scope": "data_availability", "text": "数据可用性声明必须存在…"}],
    "suppression_rules": [{"rule_id": "FP-01", "text": "学科写作惯例不算缺陷"}],
    "facets": {"data_availability": "…", "ethics": "…", "conflict_of_interest": "…", "author_contributions": "…", "funding": "…", "copyright_license": "…", "reference_format": "…", "duplicate_publication": "…"},
    "declaration_checklist": [{"decl_id": "data_availability", "name": "数据可用性声明"}],
    "declaration_audit": {"items": [{"decl_id": "…", "name": "…", "detected": false, "matched_keywords": [], "sections": []}], "note": "机检证据非判定"},
    "findings": [{"finding_id": "F01", "source_ref": "manuscript.sections[0].text", "section_id": "S1", "location": "S1 摘要 第2句", "facet": "data_availability", "category": "norm_missing", "severity": "major", "quote": "逐字摘录", "evidence": "对照依据/规则说明", "rule_id": "FR-01", "revision_suggestion": "…", "status": "confirmed", "pending_reason": null, "suppressed_by": null, "judged": true}],
    "suppressed": [{"finding_id": "F09", "rule_id": "FP-01", "reason": "…"}],
    "pending_review": [{"finding_id": "F08", "reason": "…", "needed_action": "…"}],
    "clearances": [{"scope": "facet:ethics", "reason": "…"}],
    "coverage": {"total_sections": 6, "sections_with_findings": 5, "total_findings": 9, "judged": 9, "confirmed": 7, "pending": 1, "suppressed": 1, "facet_counts": {}, "category_counts": {}, "severity_counts": {}, "per_section": {}},
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
1. facet（八分面）/ category（三类）/ severity / status / run_status.state 枚举非法。
2. confirmed 的 quote 不在稿件原文中或 location 为空（定位可回证失败）。
3. compliance_rubric 未事前声明；三类×严重度映射违规（substantive_issue 标 minor、norm_missing/norm_violation 标 critical 等）。
4. norm_missing/norm_violation 无 rule_id 或 rule_id 不在事前 format_rules；substantive_issue 无对照依据。
5. 机检 detected=false 的声明无对应 norm_missing 发现且无豁免登记（机检与结论脱钩）。
6. confirmed 无 claims 逐字回证或缺 revision_suggestion；pending 未登记 pending_review；suppressed 未登记或 FP rule_id 不在事前规则表。
7. coverage 汇总/facet_counts 与实际不符；零发现分面未登记；unchecked 非空却判 audited；verdict 与判定进度矛盾；steps 为空或无可执行 command。
8. 闸门（case_contract / rubric_ledger / decl_audit_output / coverage_audit_output）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，论文/数据/文献均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/decl_audit.py --result examples/example-result.json --case examples/example-case.json --input-root examples --emit-into
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk/compliance_rubric.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 稿件解析失败 / 输入不可读 | material_gaps 登记、status=input_error 或 insufficient_evidence、verdict=cannot_verify，绝不编造合规结论 |
| 声明在投稿系统/单独文件而非正文 | 机检 detected=false 时按材料实际情况登记 clearances（scope=decl:xxx）或 material_gaps，不凭空判缺也不脑补存在 |
| 图表无法读取/许可标注不可解析 | clearances 登记 artifact:* 豁免 + material_gaps 注明；版权状态不明标 pending，不猜许可类型 |
| 重复发表/一稿多投疑似 | 本技能无外部检索与查重能力：稿件内部可确认的（如会议版未引用未声明）判 substantive_issue，需外部比对的标 pending + needed_action |
| 目标期刊要求缺失/题面未给规则 | 按 format_rules 默认条目保守审查并在 rubric note 写明依据自设，不冒充期刊官方标准 |
| 稿件超长/预算不足 | 保留已审部分，unchecked 登记未审范围，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅审查输入稿件本身与其自带材料：不做外部检索、不查重库比对、不润色改写、不代投。
- format_rules 默认条目是本技能事前声明的通用规范设定（题面或期刊指南给出时按实际改写并冻结），不冒充期刊官方标准。
- 声明存在性机检基于关键词表，只能证明"稿件文本中未出现相关表述"，不能证明声明不在投稿系统或单独文件——机检证据与语义判定分层，机检缺失须有发现或豁免对账。
- 重复发表比对只能基于稿件内部线索（会议版提及/文字高度复用），外部比对需求标 pending。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
