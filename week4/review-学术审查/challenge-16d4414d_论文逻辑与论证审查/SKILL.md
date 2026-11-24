---
name: paper-logic-review
description: Paper logic and argumentation review skill (five-dimension coverage / itemized findings / three-level severity / prose report embedded). Reviews a manuscript across all five dimensions the rubric requires — claim_extraction (core claims and their qualifications), evidence_support (whether evidence exists and is strong enough), reasoning_chain (premise-to-conclusion gaps, implicit assumptions, causal-vs-correlational), section_coherence (intro promises vs method/result delivery, abstract-vs-body consistency, figure-text alignment), severity (explainable severity grading + actionable revision suggestions) — and emits BOTH an itemized findings list AND a full prose review report (review_report) embedded into result.json. Every dimension is explicitly checked and reported. Use when the task asks for a complete paper logic/argumentation review.
---

## 强制执行协议（最高优先级，冲突时以本节为准）
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 `/app/output/result.json`。此后 result.json 必须存在且可解析。
2. **五维度必覆盖**：claim_extraction / evidence_support / reasoning_chain / section_coherence / severity 五类都要逐面查过并记录，不得静默跳过。
3. **成文报告必嵌入**：除 findings 外，必须写 `result.review_report`（Markdown 全文，≥200 字）。
4. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
5. **预算保护**：模型请求超 40 次或 600 秒即停止，用现有结果写 review_report 收尾。

## 定位与约定
锁定子场景：给定一篇分章节稿件，完成**五维度完整逻辑审查**，交付结构固定的问题清单 + 成文报告。逐条问题带逐字 quote + 位置 + 严重度 + 修改建议；区分事实错误/证据不足/规范问题/建议。论文润色/查重/复算统计不在范围。
- 输入：`/input/case.json`（manuscript{sections[]+references} + output_contract）、`task.md`。以实际文件为准。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 脚本定位以技能根 SKILL.md 标志文件校验命中为准。

## 五维度定义（每维必查）
1. `claim_extraction` 论点与主张抽取：从摘要/引言/结果/讨论抽作者核心主张及限定条件，区分作者主张、引用他人观点、假设情形。
2. `evidence_support` 证据支撑核查：每条主张的支撑证据是否存在、是否来自本文实验或所引文献、是否足以支撑该强度表述；识别"结论超出数据""引用不支持观点"。
3. `reasoning_chain` 推理链完整性：前提→结论是否有跳跃、隐含假设未说明、替代解释未排除、相关与因果混用。
4. `section_coherence` 章节衔接一致性：引言承诺的问题是否在方法/结果交付、方法结果口径是否一致、摘要与正文结论是否一致、图表与正文描述是否对应。
5. `severity` 严重度与修改建议：给出可解释的严重度分级（是否影响主结论/是否可修正/是否影响可复现性），生成落到具体句子的修改建议。

## 五步流程

### Step 0 — 落骨架 + 稿件结构（1 次脚本，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
自动提取 output_contract 全字段 + 稿件章节/参考文献计数 → 写骨架 + 口径模板。

### Step 1 — 三口径事前声明（1 次响应，判定前必做）
- `evidence_scale`：证据 E3=对照/实验、E2=观察性相关、E1=个案/转述、E0=无实证；主张 C3=因果/普遍推广、C2=限定相关、C1=假说。规则 C3须E3、C2须≥E2。
- `severity_rubric`：critical=影响主结论；major=削弱可信度可修正；minor=局部表述。
- `issue_taxonomy`：no_evidence / insufficient_evidence / strength_mismatch / citation_unsupported / overgeneralization / reasoning_gap / incoherent。
- 声明后不改；写 /app/work/rubrics.json。

### Step 2 — 五维度逐面审查（2-4 次响应，广度优先）
- 先抽主张 `result.claims[]`：每案例 6-12 条核心主张，标 claim_strength + evidence_strength + judge
- 再逐维审：每条问题写 `result.findings[]`，`dimension` ∈ 五维之一，`issue_type` ∈ 七类之一，`severity` 按口径，`quote` 逐字 + `location` + `revision_suggestion`
- **每维都要产出**：有问题记 finding；没问题的维度在 `result.dimension_coverage` 记 `{dimension, status:"checked_no_issue"}`
- 无法确认 → pending；对照组/假设/转述 → suppressed（FP-01/02）

### Step 3 — 写审查报告（1 次响应，必做）
写 `result.review_report`（≥200 字）：①总体结论 ②五维度逐维小结 ③主要问题清单摘要 ④待复核项。

### Step 4 — 自检与交付（1 次脚本，必做）
```bash
python3 /skills/weekly-skill/scripts/evidence_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/evidence_check.json --emit-into
```
判据看 validator_verdict；FAIL 则修复→重跑，直到 PASS。

## 输出 schema（result.json 顶层契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "manuscript_overview":{"title":"…","sections":["S1…"],"reference_count":12},
    "evidence_scale":{"evidence_levels":{},"claim_levels":{},"rule":"…","declared_at":"step1"},
    "severity_rubric":{"levels":{"critical":"…","major":"…","minor":"…"},"declared_at":"step1"},
    "issue_taxonomy":{"types":{},"declared_at":"step1"},
    "claims":[{"claim_id":"c-01","text":"…","claim_strength":"C3","evidence_strength":"E2","judge":"overstated","location":"S5","quote":"…"}],
    "findings":[{"finding_id":"F01","dimension":"evidence_support","issue_type":"strength_mismatch","category":"insufficient_evidence","severity":"major","quote":"逐字","location":"S5 第1句","evidence":"…","revision_suggestion":"…","status":"confirmed","claim_id":"c-01"}],
    "dimension_coverage":[{"dimension":"claim_extraction","status":"checked_findings","count":1},{"dimension":"section_coherence","status":"checked_no_issue","count":0}],
    "review_report":"## 总体结论\n……（≥200字）",
    "suppressed":[],"pending_review":[],"clearances":[],
    "run_status":{"state":"success","reason":null},
    "verdict":"audited|partially_audited|cannot_verify","verdict_basis":"…"
  },
  "claims":[],
  "uncertainties":{"summary":"…"},"changelog":[]
}
```

## 校验器会抓的错（evidence_check.py）
1. 五维度有任一面在 dimension_coverage 缺失。
2. findings 里 dimension/issue_type/category/severity 枚举非法；confirmed 缺 quote/location。
3. review_report 缺失或 <200 字。
4. 三口径未声明；C3 配 E2 以下判 supported 违规；suggestion≠minor。
5. verdict 与进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 某维度材料缺失 | 该维记 checked_no_issue + 注明"材料缺失无法核验"，不编造 |
| 图表无法读取 | clearances 登记 + 图标一致性标未检查 |
| 稿件超长/预算不足 | unchecked 登记 + status=partial |
| 校验 FAIL | 修复后重跑；修不了如实登记，绝不中断交付 |

## 已知限制
- 只审输入稿件本身与自带参考文献，不做外部检索、不查重、不复算统计。
- 审查是事实/逻辑的机器辅助核对，不提供期刊官方意见。
- examples/ 为合成示意（虚构），非正式答案。