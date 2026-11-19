---
name: research-stat-audit
description: Research-method & statistics audit skill (five-facet audit / located findings / statistical recomputation / defect-vs-underreporting distinction / severity rubric / pending-review registry). Audits a fixed manuscript across six facets (research_design, variable_definition, stat_method, sample_power, result_reporting, norms_consistency) and emits an itemized, source-locatable review sheet — every finding carries a verbatim quote, a section/sentence location, a severity graded under a rubric declared before any judgment, a category (fact_error / insufficient_evidence / norm_issue / suggestion), and a defect_class that separates method_defect (the authors did it wrong) from reporting_gap (the authors did not report it). Mechanically recomputes reported statistics via stat_recompute.py (r→t→p, p-boundary vs normal-approx, CI width vs 2*z*SE, CI vs null vs claimed significance, df vs n per design, group-size sums) and records each claim as consistent/inconsistent/indeterminate in result.stat_recompute. Suppresses false positives via pre-declared rules, registers unverifiable items as pending review instead of inventing conclusions, and records material gaps honestly. coverage_audit mechanically audits facet×section coverage; verify_check back-checks every quote against the manuscript, severity mapping, defect-class mapping, recorded-vs-independent stat recomputation and claims chain; gain_probe re-runs normal-vs-degraded ablation on the same input and embeds measured gain_evidence and efficiency into result.json. Use when the task asks to review research design, variable definitions, statistical methods, sample size or results reporting with per-item evidence, severity and statistical recomputation.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 findings / suppressed / pending_review / clearances / stat_recompute / coverage / unchecked / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **六分面全覆盖**：研究设计、变量定义、统计方法、样本量与效能、结果报告、规范与一致性六个分面逐一过稿，缺一不可；零发现分面须在 unchecked/clearances 登记原因，禁止静默跳过。
4. **不编造**：每条 finding 的 quote 必须逐字摘自实际稿件原文并附位置（原文不在稿件中的引文 = 定位失据）；读不到的图表/文献标 pending 并登记，不凭空补结论；输入是真实论文全文，不依据任何标签假设内容。
5. **口径事前声明**：severity_rubric 三级口径与误报抑制规则（FP-xx）必须在任何逐条判定之前写定（declared_at），之后禁止调整；判定必须可映射回口径。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本退出码恒为 0，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定一篇固定稿件（论文/科研材料）与审查要求，完成**六分面逐条问题清单（原文位置 + 严重度 + 修改建议）、统计量复算、缺陷/报告不全区分、四类区分、误报抑制、待复核登记**。文献检索与综述、全文翻译、语言润色、投稿决策不在范围；稿件解析失败、图表不可读、参考文献缺失照实登记，不脑补。
- 输入：`/input/case.json`（稿件 + 审查要求 + output_contract）、`task.md`，以实际文件为准；工作区 `/app/work`，最终产物 `/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–7 线性推进，禁止分支回环。

## 八步流程

### Step 0 — 自动落骨架与稿件结构清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键提取章节结构预填 `result.manuscript_overview`；生成 `/app/work/severity_rubric.json` 口径模板；校验挂载标志文件（技能根 SKILL.md）。
- 脚本失败时手工兜底：读 case.json 抄稿件结构与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 严重度口径与误报抑制规则（1 次响应，判定前完成）
- **事前声明 severity_rubric**：critical=统计结论错误或数据矛盾直接推翻主要结论（p 值与复算矛盾、CI/SE/df 组合不自洽、无对照基础断言显著）；major=方法/报告缺陷影响可信度但不必然推翻（随机化/盲法细节缺失、多重比较未校正、样本量无依据、关键统计量缺失）；minor=规范与表述问题不改变结论。declared_at 必填，同步写 /app/work/severity_rubric.json。机械映射：suggestion ⇒ minor；fact_error ⇒ critical/major。**声明后禁止调整。**
- **事前声明 suppression_rules**：FP-01 学科写作惯例（作者自陈局限）、FP-02 期刊格式差异、FP-03 作者有意取舍、FP-04 超出方法/统计范围的意见；判"不算缺陷"必须引用 rule_id。

### Step 2 — 六分面逐条审查（2-4 次响应，广度优先）
对六个分面逐一过稿，每条发现写入 `result.findings[]`，缺一不可：
- `quote` 逐字摘自稿件原文 + `location` 注明章节/句位 + `section_id`/`source_ref`；
- `facet` ∈ research_design/variable_definition/stat_method/sample_power/result_reporting/norms_consistency；`category` ∈ fact_error/insufficient_evidence/norm_issue/suggestion；`severity` 按 Step 1 口径；
- **`defect_class` 必填**（本题核心区分）：`method_defect`（作者做错了：数值矛盾、该校正未校正、检验误用）/ `reporting_gap`（作者没报告：随机化细节、样本量依据、效应量、CI、校正方法缺失）/ `cannot_classify`（材料不足）/ `not_applicable`（suggestion 类）。机械映射：fact_error ⇒ method_defect；reporting_gap ⇒ category ∈ insufficient_evidence/norm_issue；suggestion ⇒ not_applicable；
- **统计量断言附 `stat_claim`**：稿件报告的统计量组合摘录为 `{"type": r_to_t|t_to_p|ci_from_se|ci_vs_null|df_vs_n|group_shares, "params": {...}, "claimed": {...}}`（如 r 与 n、t 与 p、CI 与 SE、df 与样本量、各组 n 与总数），供 Step 4 复算；
- 涉及统计结论的判断写明对照依据（复算值、正文前后数值对照、规范要求）；每条 confirmed 给 `revision_suggestion`；无法确认 → status=pending；判为学科惯例/格式差异 → status=suppressed + FP-xx（仍登记）。

### Step 3 — 六分面覆盖机械审计（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/coverage_audit.py --result /app/output/result.json \
  --case /input/case.json --input-root /input --emit-into
```
- 机械计数六分面/类别/严重度/章节覆盖，回写 `result.coverage` 与 `result.unchecked`；零发现分面或章节且未登记 clearances 豁免 → 进 unchecked（verdict 不得为 audited）。

### Step 4 — 统计量数值复算（1 次脚本调用，凡有 stat_claim 必做）
```bash
python3 /skills/weekly-skill/scripts/stat_recompute.py --result /app/output/result.json --emit-into
```
- 对每条 stat_claim 独立复算并把结果写进 `result.stat_recompute.checks[]`（computed + consistent 三值 + detail）；consistent=false 是**缺陷证据**（如 r=0.32,n=48 复算 p≈0.022 ≠ p<0.001；df 超过 n-1；CI 宽 ≠ 2*z*SE），据实写入对应 finding 的 evidence；
- 复算口径：p 值正态近似（标准库无 t 分布分位数；df<30 容差 0.015），CI 相对容差 5%；参数不全判 indeterminate，不算矛盾，不臆造补值。

### Step 5 — 待复核登记与证据链（1 次响应）
- `result.pending_review[]`：每个 status=pending 发现登记 `{finding_id, reason, needed_action}`；`result.suppressed[]`：每个 suppressed 发现登记 `{finding_id, rule_id, reason}`；`result.clearances[]`：已查无问题或材料不可读的显式豁免（如 `facet:variable_definition`、`artifact:图2`）；
- `claims[]`：每条 confirmed 发现一条 `{claim_id, text, kind, source_id=finding_id, location, evidence:[{paragraph_id, quote}]}`，quote 与 finding.quote 逐字一致；
- `result.verdict`：audited（全覆盖且全判定且 unchecked 空）/ partially_audited / not_audited / cannot_verify（material_gaps 非空）；`run_status` 非 success 必写 reason。

### Step 6 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（六组机械校验全开）与退化模式（--ablate all：关闭定位回证/分级口径/证据链/待复核/**统计复算一致**/**缺陷区分**），把真实数字写进 `result.gain_evidence`：runs、delta_normal_minus_degraded、mechanism_to_metric_map、boundaries、failure_conditions；
- 七项对照指标：定位失据/分级口径/证据缺失/待复核/统计复算篡改/缺陷区分违规漏检 + 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，不得手填；
- `--inject-pollution` 在**副本**上注入污染（清空定位/篡改严重度/清空待复核/清空证据链/**把 CI 与 SE、df 与样本量矛盾的复算记录翻转为「一致」**）：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动；
- 脚本跑不了时手工写 `gain_evidence = {available:false, reason:…}`；退化模式结果仅用于增益对照，不得当作交付自检结论。

### Step 7 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --ledger /app/work/severity_rubric.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- 判据是报告 `verdict`：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：六分面每面都查过或有豁免登记吗？每条 confirmed 的引文都能回原文逐字命中吗？方法缺陷和报告不全分清了吗、统计断言都复算了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "manuscript_overview": {"title": "…", "sections": [{"section_id": "S1", "name": "引言", "source_ref": "manuscript.sections[0]"}], "reference_count": 12},
    "severity_rubric": {"levels": {"critical": "…", "major": "…", "minor": "…"}, "declared_at": "step1", "note": "…"},
    "suppression_rules": [{"rule_id": "FP-01", "text": "…"}],
    "facets": {"research_design": "…", "variable_definition": "…", "stat_method": "…", "sample_power": "…", "result_reporting": "…", "norms_consistency": "…"},
    "findings": [{"finding_id": "F01", "source_ref": "manuscript.sections[0].text", "section_id": "S1", "location": "S1 第2句", "facet": "stat_method", "category": "fact_error", "severity": "critical", "quote": "逐字摘录", "evidence": "对照依据（含复算值）", "revision_suggestion": "…", "status": "confirmed", "defect_class": "method_defect", "stat_claim": {"type": "r_to_t", "params": {}, "claimed": {}}, "pending_reason": null, "suppressed_by": null, "judged": true}],
    "suppressed": [{"finding_id": "F09", "rule_id": "FP-01", "reason": "…"}],
    "pending_review": [{"finding_id": "F08", "reason": "…", "needed_action": "…"}],
    "clearances": [{"scope": "facet:variable_definition", "reason": "…"}],
    "stat_recompute": {"tool": "scripts/stat_recompute.py", "checks": [{"finding_id": "F01", "type": "r_to_t", "computed": {}, "consistent": true, "detail": "…"}], "counts": {"claims_total": 0, "consistent": 0, "inconsistent": 0, "indeterminate": 0}, "approx_note": "…"},
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

## 校验器会抓的错（verify_check.py 六组）
1. 枚举非法：facet / category / severity / status / defect_class / run_status.state。
2. 定位失据：confirmed 的 quote 不在稿件原文中或 location 为空。
3. 分级口径：severity_rubric 未事前声明；suggestion≠minor；fact_error 标 minor。
4. 证据链：confirmed 无 claims 逐字回证；fact_error 无对照依据；已判定无 revision_suggestion；pending 未登记 pending_review；suppressed 未登记或 rule_id 不在事前规则表。
5. **统计复算**：stat_claim 无复算记录；复算记录的 consistent 与独立复算不一致（复算结果被篡改即 FAIL）。
6. **缺陷区分**：fact_error 标 reporting_gap；reporting_gap 配了 fact_error/suggestion；confirmed 非 suggestion 缺 method_defect/reporting_gap。另：coverage 与实际不符、零发现分面未登记、unchecked 非空却判 audited、steps 为空、闸门非 enforced 时 warn「下游不得宣称已核对」。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，论文/数据/统计量均为虚构且为演示复算故意构造），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/coverage_audit.py --result examples/example-result.json --case examples/example-case.json --input-root examples --emit-into
python3 scripts/stat_recompute.py --result examples/example-result.json --emit-into
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk/severity_rubric.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 稿件解析失败 / 输入不可读 | material_gaps 登记、status=input_error 或 insufficient_evidence、verdict=cannot_verify，绝不编造审查结论 |
| 图表无法读取 | clearances 登记 `artifact:*` 豁免 + material_gaps 注明；涉及图表的条目标 pending 并登记 pending_review |
| 统计量参数不全 / 无法复算 | stat_recompute 判 indeterminate 并注明，不算矛盾、不臆造补值；对应条目按证据不足处理 |
| 参考文献缺失/全文未获取 | 相关条目标 pending + 登记 pending_review（含 needed_action），不凭空补结论 |
| 学科惯例/格式差异 | 按 suppression_rules（FP-xx）标 suppressed 并登记，不判缺陷也不静默丢弃 |
| 稿件超长/预算不足 | 保留已审部分，unchecked 登记未审范围，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅审查输入稿件本身与其自带参考文献：不做外部检索、不查重、不润色改写。
- 统计复算只用稿件报告值做一致性核验（内部自洽性），无法验证原始数据真伪；p 值为正态近似（df<30 容差 0.015）、CI 容差 5%，边界值可能判 indeterminate。
- 严重度口径与误报抑制规则是本技能事前声明的设定，不冒充期刊官方标准。
- 缺陷/报告不全的区分基于稿件文本可观测证据，语义边界情形（如"报告了但报错"）以 fact_error 优先并写明依据。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量；model_requests 由 Agent 侧回填，缺失保持 null。
