---
name: num-consistency-audit
description: Result-reporting number-consistency audit skill (single facet). Mechanically extracts every number (sample n, p-value, effect size, confidence interval, percentage, test statistic, df) from the manuscript body, tables and figure captions via regex \d (never isalpha), then cross-checks them for self-contradiction: sample-size sums across groups/sections, percentage totals vs 100, p-value vs significance wording, CI vs null, and the same statistic reported with conflicting values in different places. The model only adjudicates which occurrence is the typo; it does not close-read the whole text. Emits number_audits[] (source + value + consistent + conflict targets) and findings[] (verbatim quote + location + severity + revision), graded under a pre-declared severity rubric, with verdict and honest run_status. Suppresses non-numeric facets (design/variable/stat-method choice/power estimation) as out of scope. Use when the task asks to audit result reporting for numeric consistency with per-item evidence and severity.
---

## 强制执行协议（最高优先级）
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一动作是运行 `build_skeleton.py` 在 /app/output/result.json 写入骨架；之后任意时刻 result.json 必须存在且可解析，每次更新都整体覆盖。
2. **只做数字一致性**：本题锁定「结果报告审查——数字一致性」一个方向；研究设计/变量定义/统计方法匹配/样本量估算 4 个方向**砍掉**，判为 out_of_scope 记入 unchecked，不逐句读全文。
3. **机械提取、模型只判笔误**：所有数字由脚本用正则 `\d` 机械提取，跨位置交叉比对；模型只负责在「同一统计量出现多个冲突值」时判定哪个是笔误，不做语义层面的全文精读。
4. **失败也交付 + 退出码恒 0**：任何脚本失败仍写 result.json（如实填 status/verdict）；脚本退出码恒 0，判据只看报告内的 `verdict` 与 `problems`。
5. **预算保护**：模型请求超 48 次或运行超 700 秒即用现有中间结果收尾（status=partial）；增益层预算过半即降级为 available=false。

## 定位与约定
锁定子场景：给定一篇稿件（论文/科研材料），核对正文/表格/图注/摘要之间的 样本量、p 值、效应量、置信区间、百分比、统计量、自由度 是否自相矛盾，产出可逐条回原位的审查单。文献综述、翻译、润色、投稿决策不在范围；图表/参考文献不可读照实登记，不脑补。
- 输入：`/input/case.json`（稿件 + output_contract）、`task.md`；工作区 `/app/work`；最终产物 `/app/output/result.json`。预算 64 请求 / 900 秒 / 单响应 16384 token；零外部依赖，只用 python3 标准库。

## 五步流程

### Step 0 — 落骨架（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
自动提取 output_contract 全字段名 + 稿件全文/章节结构，写骨架，生成 `/app/work/skill_marker.json`（挂载标志，脚本定位校验用）。脚本失败时手工兜底抄字段名写骨架。

### Step 1 — 事前声明严重度口径（1 次响应，判定前完成）
- critical=摘要与正文/图表间的样本量或主要结局效应量/CI/p 值冲突，直接推翻主要结论；
- major=次要结局、百分比、统计量/自由度不一致，影响可信度但不必然推翻结论；
- minor=百分比四舍五入差、表述不一致但不改变结论。
declared_at 必填，写 `/app/work/severity_rubric.json`，声明后禁止调整。unchecked 记 out_of_scope 的四个方向。

### Step 2 — 数字提取与交叉比对（1 次脚本调用，核心）
```bash
python3 /skills/weekly-skill/scripts/number_audit.py --result /app/output/result.json \
  --case /input/case.json --input-root /input --emit-into
```
脚本正则 `\d` 机械提取全文/表格/图注里的六类数字 → 写 `result.number_audits[]`（每个数字：audit_id + kind + value + type_tag + source + location + raw + consistent + conflicts_with + note）→ 交叉比对规则：
- 样本量 n：分组 n 求和 vs 报告总数；摘要 n vs 方法 n；
- 百分比：各类百分比之和 vs 100；
- p 值与显著性表述：p<0.05 却写"不显著"（或反之）；
- CI 与 null：CI 是否跨 0/1 却声称显著；
- 同一统计量（r/t/df/CI/效应量）在多位置出现不同值 → 记 conflicts_with。
产出的不一致写入 `result.findings[]`（finding_id + quote 逐字 + location + severity + evidence 引用冲突的 audit_id + revision_suggestion + status）。模型在本步后只补「哪个值是笔误」的判定。

### Step 3 — 校验与守卫（2 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json
```
verify_check 判据是报告 `verdict`（PASS/FAIL）：findings 定位可回证、severity 合口径、number_audits 与 findings 双向一致、verdict/run_status 合理；FAIL 就逐条修复后重跑，直到 PASS 或如实登记。schema_guard 校验契约字段 + 业务 schema 不缺键。

### Step 4 — 增益降级与收尾
预算过半或时间不足：`result.gain_evidence = {"available": false, ...}`、`efficiency` 照实填；填写 `verdict`（audited=全数字比对完成且 unchecked 空 / partially_audited / not_audited / cannot_verify）、`verdict_basis`、`run_status`、`changelog`。自检四问：六类数字都提取了吗？每条 finding 都有 conflict_ids 回链吗？冲突处都有逐字 quote 吗？out_of_scope 方向登记了吗？

## 输出 schema（result.json）
```json
{
  "case_id": "取自 case.json", "status": "answered|partial|insufficient_evidence|input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": "…", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "manuscript_overview": {"title": "…", "sections": [{"section_id": "S1", "name": "…", "chars": 200}], "full_text_chars": 2000, "reference_count": 2},
    "severity_rubric": {"levels": {"critical": "…", "major": "…", "minor": "…"}, "declared_at": "step1"},
    "number_audits": [{"audit_id": "N01", "kind": "sample_size|p_value|effect_size|confidence_interval|percentage|statistic|df", "value": 48, "type_tag": "n=48", "source": "manuscript.sections[0].text", "location": "摘要", "raw": "共纳入本科生 48 名", "consistent": false, "conflicts_with": ["N05"], "note": "…"}],
    "findings": [{"finding_id": "F01", "kind": "number_conflict", "quote": "逐字摘录", "location": "摘要第1句", "severity": "critical", "evidence": "N01(n=48) 与 N05(共纳入36) 冲突", "revision_suggestion": "…", "status": "confirmed", "conflict_ids": ["N01", "N05"]}],
    "conflict_summary": {"conflicts_total": 1, "by_kind": {}, "by_severity": {}},
    "unchecked": [{"scope": "facet:research_design", "reason": "out_of_scope：本题只做数字一致性"}],
    "run_status": {"state": "success|partial|unable_to_determine|refused", "reason": null, "manual_takeover": []},
    "verdict": "audited|partially_audited|not_audited|cannot_verify", "verdict_basis": "…",
    "gain_evidence": {"available": false, "reason": "…"}, "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "…", "kind": "reported", "source_id": "F01", "location": "findings[0].quote", "evidence": [{"paragraph_id": "manuscript.sections[0].text", "quote": "稿件原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [], "unbacked_numbers": [], "validator_verdict": "PASS|FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced|skipped_not_provided|not_found|unreadable", "note": ""}]
}
```

## 最小调用示例
`examples/` 有合成示意案例（非正式答案，数字矛盾为演示故意构造）：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/number_audit.py --result /tmp/skel.json --case examples/example-case.json --input-root examples --emit-into
python3 scripts/verify_check.py --result /tmp/skel.json --case examples/example-case.json --emit-into
python3 scripts/schema_guard.py --result /tmp/skel.json --case examples/example-case.json
```

## 异常处置与限制
| 场景 | 处置 |
|------|------|
| 稿件解析失败/不可读 | material_gaps 登记，status=input_error/insufficient_evidence，verdict=cannot_verify，不编造 |
| 图表无法解析 | material_gaps 注明，相关条目标 pending（注明无法比对） |
| 数字参数不全无法比对 | note 记 indeterminate，不算矛盾、不臆造补值 |
| 预算/时间不足 | 保留已比对部分，status=partial，changelog 注明截断点 |
- 只做稿件内部数字自洽性核对，不验证原始数据真伪；不覆盖研究设计/变量/统计方法选择/样本量估算四方向（记 unchecked）。
- 数值提取一律正则 `\d`，不用 isalpha 判汉字，避免误切中文数字。
- 增益层预算过半降级为 available=false；平台白板对照由平台生成。