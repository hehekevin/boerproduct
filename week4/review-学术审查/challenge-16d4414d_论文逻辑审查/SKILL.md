---
name: evidence-support-review
description: Paper evidence-support review skill (single-facet claim-extraction / evidence-existence check / evidence-strength matching / located findings / pending-review registry). Extracts core claims only from the abstract and results (5-10 per case), then judges each claim on two axes: whether supporting evidence exists at all, and whether that evidence is strong enough to bear the claim's stated strength. Identifies conclusions that outrun the data and citations that do not support the cited point, under a pre-declared two-sided strength scale (evidence E3-E0 vs claim C3-C1) and a five-type issue taxonomy (no_evidence / insufficient_evidence / strength_mismatch / citation_unsupported / overgeneralization). Suppresses false positives via pre-declared rules (control groups, explicitly-marked hypotheticals, others' opinions are NOT author defects). evidence_check mechanically audits every quote against the actual manuscript (whitespace-normalized verbatim match), taxonomy/severity enums, strength-scale declaration, per-claim judgement registration, and pending/suppressed registration. Use when the task asks to review a paper's logic and argumentation with per-item evidence and severity, with a focus on conclusions exceeding the evidence.
---

## 强制执行协议（最高优先级）
以下 4 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。
3. **退出码恒 0 判据看 verdict**：所有校验脚本退出码恒为 0，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
4. **预算过半即定稿**：模型请求已用超 32 次或运行超 450 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial；增益层 available=false）。
5. **不编造**：每条 finding 与主张的 quote 必须逐字摘自实际稿件原文并附句位；对照组、明确标注的假设情形、转述他人观点不得报成作者缺陷（FP-01/02）；无法确认标 pending 并登记，不凭空补结论。

## 定位与约定
锁定单方向子场景：**证据支撑核查**——从摘要与结果抽取作者核心主张，逐条判断"支撑证据是否存在 + 是否足以支撑该强度表述"，识别"结论超出数据"与"引用不支持观点"。论证链完整性、章节衔接一致性、严重度分级建议三方向**不在本技能范围**。
- 输入：`/input/case.json`（稿件 + 审查要求 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–4 线性推进。脚本定位以 `/app/work/skill_marker.json` 标志文件校验为准（Step 0 落盘）。

## 五步流程

### Step 0 — 自动落骨架与稿件结构（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动提取 output_contract 全部字段与稿件结构，写骨架 + 口径模板 `/app/work/rubrics.json`。
- 脚本失败时手工兜底：读 case.json 抄结构字段名，手写骨架（键一个不缺）。

### Step 1 — 三口径事前声明（1 次响应，判定前完成）
- **evidence_scale**：证据 E3=对照/实验/定量复现、E2=观察性相关或单点定量、E1=个案/转述/权威断言、E0=无实证；主张 C3=因果断言或普遍推广、C2=限定条件下的相关结论、C1=假说性表述。规则：C3 须 E3、C2 须 ≥E2、E0 不得支撑任何 confirmed 结论。
- **severity_rubric**：critical=直接影响主结论；major=削弱结论可信度但可修正；minor=局部表述。suggestion⇒minor，fact_error⇒critical/major。
- **issue_taxonomy** 五类：no_evidence=无实证支撑；insufficient_evidence=证据不足够撑该强度；strength_mismatch=结论强度超出证据等级（结论超出数据）；citation_unsupported=引用不支持所引观点；overgeneralization=超出样本/场景/时限。
- 三口径同步写 `/app/work/rubrics.json`，declared_at 必填，之后禁止调整。

### Step 2 — 抽主张 + 逐条核查（2-3 次响应）
- **只抽摘要+结果里的核心主张**，每案例 5-10 条写 `result.claims[]`：`{claim_id, text, kind∈reported|inferred, claim_strength(C1-C3), evidence_strength(E0-E3), judge∈supported|overstated|understated|pending, judge_basis, location, quote(逐字), finding_id}`。
- 逐条判断证据有无与强度是否够，读到"证据不足/结论过强/引用不支持"就记 `result.findings[]`，**宁少勿滥，不必逐句通读全文**，每案例 6-12 条封顶。每条 finding：`{finding_id, section_id, location, issue_type(五类), category∈fact_error|insufficient_evidence|norm_issue|suggestion, severity, quote(逐字), evidence(对照依据), revision_suggestion(可执行), status∈confirmed|pending|suppressed, pending_reason, suppressed_by, judged, claim_id}`。
- 无法确认 → pending + pending_reason + 登记 pending_review；对照/假设/转述 → suppressed + suppressed_by=FP-xx + 登记 suppressed。

### Step 3 — 机械校验与覆盖计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/evidence_check.py --result /app/output/result.json \
  --case /input/case.json --ledger /app/work/rubrics.json --out /app/work/evidence_check.json --emit-into
```
- 机械校验：定位回证（quote 逐字回证原文 + location 非空）、口径一致（三口径声明 + 枚举合法 + C3须E3）、登记一致（pending/suppressed 登记 + coverage 一致）；回写 self_check / gates / validator_verdict / coverage / unchecked。
- `result.verdict`：`audited`（覆盖齐、全部判定且 unchecked 空）/ `partially_audited` / `not_audited` / `cannot_verify`（material_gaps 非空）；`run_status` 非 success 必写 reason。

### Step 4 — 自检与交付（退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json → 重跑，直到 PASS（或确认无法修复并如实记录）。
- 增益层**预算 50% 即跳过**：`result.gain_evidence = {available:false, reason:…}`，不编数字。

## 输出 schema（result.json — 平台通用契约 + 本题业务键）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": "…", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "manuscript_overview": {"title": "…", "sections": [{"section_id": "S1", "name": "摘要", "source_ref": "…"}], "reference_count": 12},
    "evidence_scale": {"evidence_levels": {"E3": "…", "E2": "…", "E1": "…", "E0": "…"}, "claim_levels": {"C3": "…", "C2": "…", "C1": "…"}, "rule": "C3须E3；C2须≥E2；E0不得支撑confirmed结论", "declared_at": "step1"},
    "severity_rubric": {"levels": {"critical": "…", "major": "…", "minor": "…"}, "declared_at": "step1"},
    "issue_taxonomy": {"types": {"no_evidence": "…", "insufficient_evidence": "…", "strength_mismatch": "…", "citation_unsupported": "…", "overgeneralization": "…"}, "declared_at": "step1"},
    "suppression_rules": [{"rule_id": "FP-01", "text": "对照组/明确标注假设情形不是自相矛盾"}, {"rule_id": "FP-02", "text": "转述他人观点不算作者缺陷"}],
    "claims": [{"claim_id": "c-01", "text": "…", "kind": "reported", "claim_strength": "C3", "evidence_strength": "E2", "judge": "overstated", "judge_basis": "…", "location": "S5 第1句", "quote": "逐字", "finding_id": "F01"}],
    "findings": [{"finding_id": "F01", "section_id": "S5", "location": "S5 第1句", "issue_type": "strength_mismatch", "category": "insufficient_evidence", "severity": "major", "quote": "逐字", "evidence": "对照依据", "revision_suggestion": "…", "status": "confirmed", "pending_reason": null, "suppressed_by": null, "judged": true, "claim_id": "c-01"}],
    "suppressed": [], "pending_review": [{"finding_id": "F08", "reason": "…", "needed_action": "…"}],
    "clearances": [], "coverage": {"total_sections": 5, "sections_with_findings": 2, "total_findings": 8, "judged": 8, "confirmed": 7, "pending": 1, "suppressed": 0, "issue_type_counts": {}, "category_counts": {}, "severity_counts": {}, "per_section": {}, "manuscript_stats": {}, "note": "evidence_check.py 回填"},
    "unchecked": [], "steps": [], "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "audited | partially_audited | not_audited | cannot_verify", "verdict_basis": "…",
    "gain_evidence": {"available": false, "reason": "预算过半跳过增益层，如实记录"},
    "efficiency": {"wall_clock_seconds_total": null, "checker_runs": null, "reproduce": "python3 …"}
  },
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}],
  "validator_verdict": "PASS | FAIL"
}
```

## 校验器会抓的错（evidence_check.py 三组 + 常开）
1. **定位可回证**：confirmed 的 finding 与每条 claim 的 quote 空白归一化后须逐字出现在稿件原文，且 location 非空；引文不在原文 = 定位失据判 FAIL。
2. **口径一致**：三口径判定前声明；issue_type/severity/category/claim_strength/evidence_strength/judge 枚举合法；suggestion⇒minor、fact_error⇒critical/major；C3 配 E2 以下判 supported = 违规。
3. **登记一致**：pending⇒pending_review（reason+needed_action）；suppressed⇒suppressed[]（rule_id 在规则表内）；judge=overstated 或 E0 的主张须有对应 confirmed 发现；strength_mismatch 发现须有 claim_id；coverage 与实际 findings 一致。
4. 常开：枚举合法性、verdict/run_status/steps 一致性、契约字段、闸门（case_contract/rubrics_ledger/coverage_output 非 enforced 时 warn「没跑 ≠ 通过」）。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，材料与数据均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/evidence_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk/rubrics.json --out /tmp/ec.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 稿件解析失败 / 输入不可读 | material_gaps 登记 + verdict=cannot_verify，绝不编造审查结论 |
| 图表无法读取 | clearances 登记 `artifact:*` 豁免 + material_gaps 注明 |
| 参考文献缺失/全文未获取 | 引用支持标 pending + 登记 pending_review（含 needed_action） |
| 对照组/假设情形/转述观点 | 按 suppression_rules（FP-01/02）标 suppressed 并登记，不报成作者自相矛盾 |
| 稿件超长/预算不足 | 保留已审部分，unchecked 登记未审范围，status=partial |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |

## 已知限制
- 只审查输入稿件本身与其自带参考文献：不做外部检索、不查重、不润色、不复算统计。
- 锁定证据支撑核查单方向：不做论证链完整性、章节衔接一致性、严重度分级建议三方向。
- 三口径（证据标尺/严重度/问题类型）是本技能事前声明的设定，不冒充期刊官方标准。
- 引文回证是"逐字出现于稿件原文"的机械下界；主张抽取与强度定级靠语义判断，机械校验只保证回证、枚举与登记一致。
- 增益层在预算过半即降级为 available=false，不编造对照数字；平台白板对照由平台生成。