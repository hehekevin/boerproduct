---
name: cite-fact-review
description: Citation and factual verification review skill (six-aspect coverage / itemized findings / three-level severity / prose report embedded). Reviews a manuscript across all six aspects the rubric requires — citation_support (whether cited refs actually support each cited claim), fact_source_reliability (source type and reliability grading), evidence_location (verbatim quote + section/sentence location), numeric_stat_consistency (numbers consistent across abstract/body/figures), argument_chain (premise-to-conclusion gaps), integrity_norms (academic norm compliance) — and emits BOTH an itemized findings list AND a full prose review report (review_report) embedded into result.json. Every aspect is explicitly checked. Use when the task asks for a complete citation and factual verification review.
---

## 强制执行协议（最高优先级，冲突时以本节为准）
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 result.json。此后 result.json 必须存在且可解析。
2. **六方面必覆盖**：citation_support / fact_source_reliability / evidence_location / numeric_stat_consistency / argument_chain / integrity_norms 六类都要逐面查过并记录，不得静默跳过。
3. **成文报告必嵌入**：除 findings 外，必须写 `result.review_report`（Markdown 全文，≥200 字）。
4. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
5. **预算保护**：模型请求超 40 次或 600 秒即停止，用现有结果写 review_report 收尾。

## 定位与约定
锁定子场景：给定一篇稿件（含参考文献），完成**六方面完整引用与事实核验**。逐条问题带逐字 quote + 位置 + 严重度 + 修改建议；区分事实错误/证据不足/规范问题/建议；拿不准标待复核，不脑补。外部检索/查重/润色不在范围。
- 输入：`/input/case.json`（manuscript{sections[]+references} + output_contract）、`task.md`。以实际文件为准。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 脚本定位以 skill_marker.json 校验。

## 六方面定义（每面必查）
1. `citation_support` 引用支持：正文引用标号是否存在、被引文献主张与本文论断是否对应（完整/部分/不支持/无法判定）。
2. `fact_source_reliability` 事实来源可靠性：事实论断的来源类型（一手实验/二手转述/权威数据）与可靠性分级。
3. `evidence_location` 证据定位：每条论断能否回到原文具体章节/句位，quote 逐字可回证。
4. `numeric_stat_consistency` 数值与统计一致性：摘要/正文/图表对同一数字、p 值、效应量是否一致。
5. `argument_chain` 论证链完整性：前提→结论是否跳跃、相关因果混用、结论外推。
6. `integrity_norms` 学术规范：基金/致谢一致性、利益冲突、数据可用性声明。

## 五步流程

### Step 0 — 落骨架（1 次脚本，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 严重度口径声明（1 次响应，判定前必做）
critical=动摇核心结论；major=局部问题可修正；minor=表述/建议。

### Step 2 — 六方面逐面审查（2-4 次响应，广度优先）
- 先跑 citation_scan 机械提取带引用标号句：
```bash
python3 /skills/weekly-skill/scripts/citation_scan.py --result /app/output/result.json --case /input/case.json --emit-into
```
- 再逐面审，每条问题写 `result.findings[]`：`aspect` ∈ 六面之一 + `quote` 逐字 + `location` + `severity` + `evidence` + `revision_suggestion`
- **每面都要产出**：有问题记 finding；没问题的面在 `result.aspect_coverage` 记 `{aspect, status:"checked_no_issue"}`
- 读不到被引原文 → 标 cannot_determine，不脑补

### Step 3 — 写审查报告（1 次响应，必做）
写 `result.review_report`（≥200 字）：①总体结论 ②六方面逐面小结 ③主要问题清单 ④待复核项。

### Step 4 — 自检与交付（1 次脚本，必做）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
判据看 validator_verdict；FAIL 则修复→重跑直到 PASS。

## 输出 schema（result.json 顶层契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "manuscript_overview":{"title":"…","sections":["S1…"],"reference_count":4},
    "severity_rubric":{"levels":{"critical":"…","major":"…","minor":"…"},"declared_at":"step1"},
    "citation_scan":{},
    "findings":[{"finding_id":"F01","aspect":"citation_support","category":"insufficient_evidence","severity":"major","quote":"逐字","location":"S2 第2句","evidence":"…","revision_suggestion":"…","status":"confirmed"}],
    "aspect_coverage":[{"aspect":"citation_support","status":"checked_findings","count":2},{"aspect":"fact_source_reliability","status":"checked_no_issue","count":0}],
    "review_report":"## 总体结论\n……（≥200字）",
    "run_status":{"state":"success","reason":null},
    "verdict":"audited|partially_audited|cannot_verify","verdict_basis":"…"
  },
  "claims":[],"uncertainties":{"summary":"…"},"changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. 六方面有任一面在 aspect_coverage 缺失。
2. findings 里 aspect/category/severity 枚举非法；confirmed 缺 quote/location。
3. review_report 缺失或 <200 字。
4. severity_rubric 未声明；suggestion≠minor；fact_error 标 minor。
5. verdict 与进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 某方面材料缺失（如无参考文献） | 该面记 checked_no_issue + 注明"材料缺失无法核验" |
| 被引文献读不到 | 标 cannot_determine，不脑补 |
| 图表无法读取 | 登记 + 相关条目标 pending |
| 校验 FAIL | 修复后重跑；修不了如实登记，绝不中断交付 |

## 已知限制
- 只审稿件内部引用/事实/数字自洽，不做外部检索、不查重、不复算统计。
- 引用支持对照稿件自带参考文献列表，读不到被引原文标 cannot_determine。
- examples/ 为合成示意（虚构），非正式答案。