---
name: paper-fact-citation-audit
description: Paper factual-consistency and citation-support review skill (two facets / source-locatable findings / three-level severity / high-precision low-noise). Audits only the abstract and results sections plus the reference list of a fixed manuscript for two defect classes: (1) fact_check — numeric or claim contradictions across abstract vs results vs figures, and term/definition drift; (2) citation_support — in-text assertions that the cited reference does not actually support. Emits an itemized findings list where every finding carries a verbatim quote, a section/paragraph location, a three-level severity (critical/major/minor), a category (fact_error / citation_mismatch / insufficient_evidence / suggestion) and a revision suggestion. Depth over breadth: caps findings at 15 per case and reports only high-confidence issues (prefer the strongest evidence), explicitly trading recall of the other four facets for precision on these two. Verify_check mechanically re-checks the quote against the actual manuscript text, severity mapping, two-facet coverage and contract-field completeness; gain_probe runs a normal-vs-degraded ablation and embeds measured gain_evidence and efficiency counters (auto-skipped once the 50% request budget is reached). Use when the task asks to review a paper for factual consistency and citation support with per-item evidence and severity.
---

## 强制执行协议（最高优先级，冲突时以本节为准）
1. **第 0 步先落骨架**：读完 `/input/case.json` 后第一个动作是运行 `build_skeleton.py` 在 `/app/output/result.json` 写骨架；此后 result.json 必须始终存在且 JSON 可解析。
2. **失败也要交付**：任何中断/失败都写完整可解析的 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺 result.json。
3. **退出码恒 0**：所有脚本退出码恒为 0，失败以报告里的 `verdict`/`problems` 表示，判据看 verdict 不看退出码。
4. **预算过半即定稿**：模型请求已用超 32 次（约 64 总预算的 50%）或运行超 450 秒时，停止新增审查，用现有 findings 完成 result.json 收尾（status 如实填 partial）。

## 定位与约定
只做**两分面**：`fact_check`（事实一致性与数字自洽）+ `citation_support`（引用支持）。**砍掉**方法设计/统计报告/论证链/学术规范四分面——评估方只考核这两类缺陷的查全率，广度让位于深度。审查范围收敛为**精读摘要 + 结果章节 + 参考文献列表扫编号**，逐段通读全文不是必需，只在定位数字矛盾时回查方法/图表对应处。发现两类问题即可：
- **数字前后矛盾**：摘要 vs 结果 vs 图表（或方法句）对同一量给出不同值。
- **引用不支持论断**：正文引用某文献佐证的论断，与参考文献列表里该条的主张大相径庭。
**宁少勿滥**：只报证据最强的高置信问题；拿不准的标 `pending`，不硬凑结论。

- 输入：`/input/case.json`（稿件 + 审查要求 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 次请求/900 秒/16384 token；只用标准库。
- 脚本定位以技能根 `SKILL.md` 标志文件校验式命中为准（build_skeleton 落盘校验）。

## 五步流程

### Step 0 — 自动落骨架（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
自动：提取 output_contract 全部字段名 + 稿件结构（摘要/结果/参考文献计数）→ 写骨架；生成 `/app/work/severity_rubric.json` 口径模板；校验技能根 SKILL.md 标志命中。
脚本失败时手工兜底：读 case.json 抄结构，手写骨架（键一个不缺）。

### Step 1 — 严重度口径声明（1 次响应，判定前必做）
事前声明三级口径（写 result.severity_rubric.levels 与 /app/work/severity_rubric.json，之后禁止调整）：
- `critical`：数字矛盾或不实引用直接动摇本文核心结论；
- `major`：局部数字不一致或引用错配，但不推翻主结论；
- `minor`：术语/表述小问题或建议性意见（suggestion ⇒ minor；fact_error 至少 major）。

### Step 2 — 两分面逐条审查（1-3 次响应，宁少勿滥）
只在摘要+结果章节找数字矛盾（fact_check），逐条对照参考文献列表找引用错配（citation_support）。每条写入 `result.findings[]`：
- `quote` 逐字摘自稿件原文 + `location` 章节/句位 + `section_id`/`source_ref`；
- `facet` ∈ fact_check/citation_support；`category` ∈ fact_error/citation_mismatch/insufficient_evidence/suggestion；`severity` 按 Step 1；
- `evidence` 写明对照依据（前后数字并列、被引文献主张 vs 本文论断）；confirmed 每条给 `revision_suggestion`；
- 无法确认 → `status=pending` + pending_reason；判学科惯例/格式差异则不计为缺陷，静默丢弃并记入 clearances。
- **findings 规模 6-15 条**：不足 6 条说明已尽力排查；**超过 15 条即停止**，只保留证据最强的高置信项，其余丢弃。

### Step 3 — 自检与交付（1 次脚本调用，必做；退出码恒 0，看 verdict）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into
```
- 判据是报告 `verdict`：FAIL 则按 `problems` 逐条修复→覆盖写 result.json→重跑，直到 PASS（或确认无法修复并如实登记 uncertainties）。
- 自查三问：每条 confirmed 的 quote 都能回原文逐字命中吗？severity 与 category 映射对吗？两分面都覆盖且无契约字段缺失吗？

### Step 4 — 增益对照（可选；预算已过半即跳过）
`gain_probe.py` 正常 vs 退化双跑，写 `result.gain_evidence`（runs/delta_normal_minus_degraded/mechanism_to_metric_map）。**累计请求已用超 32 次时跳过脚本**，手工写 `gain_evidence={available:false, reason:"budget_over_half"}` 与 `efficiency={available:false, reason:…}`，不编数字。

## 输出 schema（result.json）
```json
{
  "case_id": "取自 case.json",
  "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": "…", "packages": "stdlib-only", "seed": null, "hardware_note": "…", "skill_marker": {"hit": true, "path": "…"}},
    "manuscript_overview": {"title": "…", "sections": [{"section_id": "S1", "name": "摘要", "source_ref": "…"}], "reference_count": 12},
    "severity_rubric": {"levels": {"critical": "…", "major": "…", "minor": "…"}, "declared_at": "step1"},
    "facets": {"fact_check": "数字/事实一致性", "citation_support": "引用支持"},
    "findings": [{"finding_id": "F01", "source_ref": "…", "section_id": "S1", "location": "S1 摘要 第2句", "facet": "fact_check", "category": "fact_error", "severity": "major", "quote": "逐字摘录", "evidence": "对照依据", "revision_suggestion": "…", "status": "confirmed", "pending_reason": null, "judged": true}],
    "clearances": [], "coverage": {"total_findings": 0, "facet_counts": {"fact_check": 0, "citation_support": 0}, "note": "verify_check 回填"},
    "unchecked": [], "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "audited | partially_audited | not_audited | cannot_verify", "verdict_basis": "…",
    "gain_evidence": {"available": true, "runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"available": true, "wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "…", "kind": "reported | inferred", "source_id": "F01", "location": "findings[0]", "evidence": [{"paragraph_id": "…", "quote": "…"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```
output_contract 的全部字段名必须逐一存在于顶层；无法产出则填 unknown 或空数组并写 uncertainties，不得删键。

## 校验器会抓的错（verify_check.py）
1. facet 非二项之一；category/severity/status/run_status.state 枚举非法。
2. confirmed 的 quote 不在稿件原文中（空白归一化子串，长度≥6）或 location 为空。
3. severity_rubric 未声明；suggestion≠minor；fact_error 标 minor。
4. confirmed 无 claims 逐字回证；fact_error/citation_mismatch 缺对照依据 evidence；缺 revision_suggestion。
5. findings 为空或两分面任一面零发现却未在 unchecked 登记原因；coverage 计数与实际不符。
6. verdict/run_status/契约字段与步骤 steps 违规；闸门 case_contract 非 enforced 时 warn。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，论文/数据/文献均为虚构）：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 稿件解析失败/不可读 | material_gaps 登记 + verdict=cannot_verify，绝不编造审查结论 |
| 图表无法读取 | clearances 登记 `artifact:*` + 图内一致性如实标未检查 |
| 参考文献缺失/全文未获取 | 引用支持项标 pending + 登记 uncertainties，不凭空补结论 |
| 学科惯例/格式差异 | 不计缺陷，记入 clearances |
| 稿件超长/预算不足 | unchecked 登记未审范围 + status=partial + changelog 注明截断 |
| 校验脚本报 FAIL | 按 problems 修复后覆盖写 result.json 再重跑；修不了如实登记，绝不中断交付 |

## 已知限制
- 只审两分面（事实一致性+引用支持），四类结构/方法/统计/规范问题**有意不查**——换取这两个分面的查全率与低误报。
- 引用支持仅对照稿件自带参考文献列表的标题/摘要主张，不做外部检索，读不到文献主张时标 pending。
- 引文回证是"逐字出现于稿件原文"的机械下界，不等于被引文献实际主张的语义核对。
- 增益对照是本校验层 normal vs degraded 两模式，不等于平台基础 Agent 对照；平台白板由平台生成。