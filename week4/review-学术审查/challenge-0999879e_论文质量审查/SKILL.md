---
name: paper-quality-review
description: Paper quality review skill (six-facet coverage / itemized findings / three-level severity / prose report embedded). Reviews a fixed manuscript across all six facets the rubric requires — fact_check (numeric/claim consistency), citation_support (claim-reference alignment), method_design (controls/sample/design), stat_reporting (significance/CI/error), argument_chain (hypothesis-to-conclusion logic), integrity_norms (data availability/ethics/COI) — and emits BOTH an itemized findings list (verbatim quote + section/paragraph location + severity + category + revision suggestion) AND a full prose review report (review_report) embedded into result.json so a grader can read a complete, deliverable review without opening extra files. Every facet is explicitly checked and reported, even when no defect is found (recorded as "checked, no issue"). Use when the task asks for a complete paper quality review with per-item evidence, severity and a readable report.
---

## 强制执行协议（最高优先级，冲突时以本节为准）
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 `/app/output/result.json`。此后 result.json 必须存在且 JSON 可解析。
2. **六分面必覆盖**：fact_check / citation_support / method_design / stat_reporting / argument_chain / integrity_norms 六类都要逐一面查过并记录结论（发现问题记 finding，没发现问题记 "checked, no issue"），不得静默跳过。
3. **成文报告必嵌入**：除 findings 清单外，必须写 `result.review_report`（Markdown 全文，≥200 字），把审查结论写成评分者可直接读的完整报告。
4. **失败也交付**：任何中断仍写 result.json（status=partial）。脚本退出码恒 0，判据看 verdict。
5. **预算保护**：模型请求超 40 次或 600 秒即停止新增审查，用现有结果写 review_report 并收尾。

## 定位与约定
锁定子场景：给定一篇分章节稿件（含参考文献），完成**六分面完整审查**，交付结构固定的问题清单 + 成文审查报告。逐条问题带逐字 quote + 位置 + 严重度 + 修改建议；区分事实错误/证据不足/规范问题/建议；拿不准标待复核，不脑补。论文润色/查重/排版不在范围。
- 输入：`/input/case.json`（manuscript{sections[]+references} + output_contract）、`task.md`。以实际文件为准。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 脚本定位以技能根 SKILL.md 标志文件校验命中为准。

## 六分面定义（每面必查）
1. `fact_check` 事实一致性：摘要/正文/图表对同一数字、结论、术语是否一致，有无自相矛盾。
2. `citation_support` 引用支持：正文引用标号是否存在、被引文献主张与本文论断是否对应。
3. `method_design` 方法设计：对照设置、样本量与抽样、评价指标是否合理、是否交代重复与随机化。
4. `stat_reporting` 统计报告：显著性、效应量、置信区间、误差是否报告且一致。
5. `argument_chain` 论证链：假设→结论推理是否完整，有无循环论证、因果相关混淆、结论外推。
6. `integrity_norms` 学术规范：数据可用性、伦理与利益冲突声明、基金/致谢一致性、图表来源。

## 五步流程

### Step 0 — 落骨架 + 稿件结构（1 次脚本，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
自动提取 output_contract 全字段 + 稿件章节/参考文献计数 → 写骨架；写 severity_rubric 模板。

### Step 1 — 严重度口径声明（1 次响应，判定前必做）
`result.severity_rubric`：critical=动摇核心结论；major=局部问题但不推翻主结论；minor=表述/建议性。suggestion ⇒ minor；fact_error 至少 major。声明后不改。

### Step 2 — 六分面逐条审查（2-4 次响应，广度优先）
对六个分面逐一面过稿，每条写入 `result.findings[]`：
- `facet` ∈ 六项之一；`category` ∈ fact_error/insufficient_evidence/norm_issue/suggestion；`severity` 按 Step 1
- `quote` 逐字摘原文 + `location` 章节/句位 + `section_id`
- confirmed 给 `revision_suggestion`；拿不准 `status=pending` + pending_reason；学科惯例记入 clearances 不计缺陷
- **每个分面都要有产出**：发现问题记 finding；没发现问题的分面在 `result.facet_coverage` 记 `{facet, status:"checked_no_issue"}`，绝不静默跳过
- findings 规模：宁缺毋滥，但六分面都要覆盖到

### Step 3 — 写审查报告（1 次响应，必做）
写 `result.review_report`（Markdown 全文，≥200 字），结构：①总体结论一句话 ②六分面逐面小结（每面 1-2 句，有问题的列关键项、没问题的写"已查无问题"）③主要问题清单摘要 ④待复核项。这是评分者直接读的完整报告。

### Step 4 — 自检与交付（1 次脚本，必做）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
- 判据看 `validator_verdict`：FAIL 则按 problems 修复→重跑，直到 PASS（或如实登记）。
- 自查三问：六分面都覆盖了吗？review_report ≥200 字且是成文吗？每条 confirmed 的 quote 能回原文吗？

## 输出 schema（result.json 顶层契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "manuscript_overview":{"title":"…","sections":["S1…"],"reference_count":12},
    "severity_rubric":{"levels":{"critical":"…","major":"…","minor":"…"},"declared_at":"step1"},
    "findings":[{"finding_id":"F01","facet":"fact_check","category":"fact_error","severity":"major","quote":"逐字","location":"S1 第2句","section_id":"S1","evidence":"对照依据","revision_suggestion":"…","status":"confirmed","pending_reason":null}],
    "facet_coverage":[{"facet":"fact_check","status":"checked_findings|checked_no_issue","count":2},{"facet":"citation_support","status":"checked_no_issue","count":0}],
    "review_report":"## 总体结论\n……（≥200字成文报告）",
    "clearances":[],"run_status":{"state":"success","reason":null},
    "verdict":"audited|partially_audited|cannot_verify","verdict_basis":"…"
  },
  "claims":[{"claim_id":"c-01","text":"…","kind":"reported","source_id":"F01","location":"S1","evidence":[{"quote":"…"}]}],
  "uncertainties":{"summary":"…","human_review":[]},"changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. 六分面有任一面在 facet_coverage 里缺失（未覆盖）。
2. findings 里 facet/category/severity 枚举非法；confirmed 缺 quote/location。
3. review_report 缺失或 <200 字。
4. severity_rubric 未声明；suggestion≠minor；fact_error 标 minor。
5. verdict 与进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 稿件某分面材料缺失（如无参考文献） | 该分面记 checked_no_issue + 注明"材料缺失无法核验"，不编造 |
| 图表无法读取 | clearances 登记 + 图内一致性标未检查 |
| 稿件超长/预算不足 | 未审范围记 unchecked + status=partial + changelog 注明 |
| 校验 FAIL | 修复后重跑；修不了如实登记，绝不中断交付 |

## 已知限制
- 引用支持只对照稿件自带参考文献列表，不做外部检索；读不到被引文献主张标 pending。
- 审查报告是事实/规范的机器辅助核对，不提供法务或伦理委员会正式意见。
- examples/ 为合成示意（虚构），非正式答案。