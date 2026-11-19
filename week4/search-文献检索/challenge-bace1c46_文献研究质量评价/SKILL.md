---
name: lit-quality-appraise
description: Literature methodology quality appraisal skill (checklist-driven itemized appraisal / evidence anchoring / mechanical grade rollup / design-flaw vs reporting-gap separation). Judges each given paper item-by-item against a pre-declared methodology checklist (design / sample / control / blinding / statistics / other), quotes verbatim evidence with a located position for every judgment, maps each judgment to a fixed grade (high/medium/low/uncertain) via declared grade_map, separates design flaws from reporting gaps via declared category_map, abstains (unassessable) with registration when evidence is insufficient, and mechanically rolls up per-paper penalty totals, risk-of-bias bands and bias direction via grade_rollup. Verify_check re-checks domain coverage, re-derives every grade from the declared map, back-checks every quote against the claims chain and the actual source text, re-computes the rollup, and re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency counters into result.json. Use when the task asks to appraise research methodology quality item-by-item with traceable evidence and reproducible grades.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 papers / checklist / grading_rules / risk_summary / pending_review / coverage / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **清单逐条全覆盖**：每篇文献的 appraisals 必须覆盖量表声明的**全部 domain**（缺维度=FAIL）；每条 judged=true，或 unassessable 写 abstain_reason、not_applicable 写 na_reason；不跳条、不脑补。
4. **不编造证据**：evidence_quote 必须逐字摘自 case.json 实际来源文本并附位置（doc_id#章节）；校验器会把每条引文与来源文本逐字比对，转述或编造即 FAIL；判不了就 unassessable 弃权并登记，不补一个"看起来合理"的判断。
5. **口径事前声明**：grading_rules（grade_map / category_map / penalty_map / thresholds / abstain_rule / direction_rule）必须在**任何复算之前**声明（declared_at 落 /app/work/grading_rules.json 台账），之后禁止调整；每条 grade 与 category 必须能由 judgment 经声明映射机械导出。
6. **键归属纪律（多脚本禁写同一键）**：risk_summary 只归 grade_rollup.py；self_check / gates / unbacked_numbers / unbacked_evidence / validator_verdict 只归 verify_check.py；gain_evidence / efficiency 只归 gain_probe.py；其余归 build_skeleton + Agent。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定若干篇文献（含全文/摘要的分节文本），按**方法学质量清单**逐条评价——研究设计 / 样本 / 对照 / 盲法 / 统计 / 其他（伦理与资助），每条给逐字证据 + 定位 + 分级（高/中/低/不确定），区分**设计缺陷**与**报告不全**，按事前规则机械汇总偏倚风险等级与方向。不做同行评审、事实核验、临床/政策决策，不做数据库检索与全文下载；全文不可得、仅有摘要、证据缺失照实登记，弃权不罚分。
关键词：判得全（清单维度一个不缺）· 钉得死（每条判断回到原文可定位句子）· 级得稳（分级由声明映射机械导出、汇总可复算）· 分得清（设计缺陷≠报告不全）· 敢弃权（证据不足标 uncertain 并登记人工复核）。
- 输入：`/input/case.json`（文献分节文本 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与文献清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（papers/documents/articles 等）提取文献清单预填 `result.papers[]`；预填默认量表与分级口径模板；生成 /app/work/grading_rules.json 台账。
- 脚本失败时手工兜底：读 case.json 抄文献清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 评价范围、量表与分级口径（1 次响应，复算前完成）
- 填 `result.review_scope`（question / paper_types / checklist_version）与 `result.checklist`：按文献类型裁剪量表条目（默认 6 domain：design/sample/control/blinding/statistics/other），每条 checklist_id + domain + prompt。
- **事前声明 grading_rules**：grade_map（judgment→grade）、category_map（judgment→design_flaw/reporting_gap/none）、penalty_map（judgment→罚分）、thresholds（penalty_total 分档）、abstain_rule、direction_rule，declared_at 必填并同步 /app/work/grading_rules.json。**声明后禁止调整。**

### Step 2 — 逐条评价（1-3 次响应，广度优先）
对每篇文献的**每条量表条目**，缺一不可：
- `judgment` ∈ adequate / concerns / inadequate / unreported / not_applicable / unassessable；`grade` 必须等于 grade_map[judgment]；`category` 必须等于 category_map[judgment]（inadequate⇒设计缺陷、unreported⇒报告不全——两者不得互换）；
- `evidence_quote` 逐字摘自来源文本 + `evidence_location`（doc_id#章节/段落，注明页码或图表号如有）；unreported/unassessable 允许引文为空但须在 location 说明检索过程（如「全文无盲法表述」）；
- 负面判定（concerns/inadequate/unreported）必填 `bias_direction` ∈ favors_conclusion / against_conclusion / unclear；unassessable 写 abstain_reason 并进 Step 4 待复核；not_applicable 写 na_reason；
- 每条 `rationale` 一句话写明判断依据哪段证据。

### Step 3 — 机械汇总复算（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/grade_rollup.py --result /app/output/result.json
```
- 按事前规则机械复算每篇 penalty_total、risk_of_bias（分档+abstain_rule）、direction（direction_rule），写入 `result.risk_summary`（仅此键）；结果与 claims 中逐篇结论数字必须一致。
- 脚本失败时手工兜底：按同一公式手算并在 steps 注明「手算」，事后仍须重跑脚本核对。

### Step 4 — 弃权登记与证据链（1 次响应）
- `result.pending_review[]`：**每个 unassessable 条目**登记 `{paper_id, checklist_id, reason, needed_action}`。
- `result.coverage`：papers_total / items_total / judged_items / abstained / design_flaws / reporting_gaps 等，与实际条目一致。
- **claims 证据链**：每篇文献至少一条 `{claim_id, text, kind, source_id=paper_id, location, evidence:[{paragraph_id, quote}]}`；text 含「penalty_total 数字 + risk_of_bias + direction + 关键判断」；所有引文逐字进入对应 evidence，penalty_total 数字未回证列入 unbacked_numbers 判 FAIL。
- 结论分级 `result.verdict`（verdict_basis 一句话）：`appraised` 全部逐条判定；`partially_appraised` 部分；`not_appraised` 未产生判定；`cannot_verify` 材料缺口且 material_gaps 非空。
- 运行状态 `result.run_status` = `{state, reason, manual_takeover[]}`，state ∈ success|partial|unable_to_determine|refused；非 success 必须写 reason。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（五组机械校验全开）与退化模式（--ablate all：关闭清单覆盖 / 分级一致 / 证据回证 / 缺陷区分 / 弃权登记），把**真实数字**写进 `result.gain_evidence`：runs、delta_normal_minus_degraded、mechanism_to_metric_map、boundaries、failure_conditions。
- 违规客观真值由探针独立复算（与校验层分开实现）；`--inject-pollution` 在**副本**上注入污染（缺陷混淆 / 分级漂移 / 编造引文 / 删条目 / 篡改汇总 / 清空待复核 / 清空 claims）：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 同时写 `result.efficiency`（墙钟、字节、检查项数、篇目数、人工条目、追问轮次 + reproduce 命令）；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- 脚本跑不了时**手工**写 `gain_evidence` = `{available:false, reason:"…"}`，不得编数字。退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每篇文献的量表维度全覆盖了吗？每条判断都能逐字回到原文与声明映射吗？弃权与报告不全都如实区分并登记了吗？

## 输出 schema（result.json — 平台通用契约 + 本题业务键）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": null, "packages": "stdlib-only", "seed": null, "hardware_note": null},
    "review_scope": {"question": null, "paper_types": null, "checklist_version": null},
    "checklist": {"version": "…", "domains": ["design","sample","control","blinding","statistics","other"], "items": [{"checklist_id": "DS-01", "domain": "design", "prompt": "…", "evidence_required": true}]},
    "grading_rules": {"version": "…", "declared_at": "…", "grade_map": {"adequate": "high", "concerns": "medium", "inadequate": "low", "unreported": "uncertain", "unassessable": "uncertain", "not_applicable": null}, "category_map": {"concerns": "design_flaw", "inadequate": "design_flaw", "unreported": "reporting_gap", "…": "…"}, "penalty_map": {}, "thresholds": {"low": [0,1], "some_concerns": [2,4], "high": [5,9999]}, "abstain_rule": "…", "direction_rule": "…"},
    "papers": [{"paper_id": "Q01", "doc_id": "doc-q01", "title": "…", "paper_type": "rct", "source_ref": "papers[0]", "judged": true, "appraisals": [{"checklist_id": "DS-01", "domain": "design", "judgment": "concerns", "grade": "medium", "category": "design_flaw", "bias_direction": "against_conclusion", "evidence_quote": "逐字摘录", "evidence_location": "doc-q01#methods", "rationale": "…", "judged": true, "abstain_reason": null, "na_reason": null}]}],
    "risk_summary": {"computed_by": "grade_rollup.py", "per_paper": [{"paper_id": "Q01", "penalty_total": 5, "risk_of_bias": "high", "direction": "against_conclusion", "abstained": 0, "design_flaws": 2, "reporting_gaps": 1, "grade_counts": {}}], "totals": {}},
    "coverage": {"papers_total": 2, "domains_required": 6, "items_total": 12, "judged_items": 12, "abstained": 1, "design_flaws": 3, "reporting_gaps": 1, "not_applicable": 1, "ratio": 1.0},
    "conflicts": [], "pending_review": [{"paper_id": "Q02", "checklist_id": "OT-01", "reason": "…", "needed_action": "…"}],
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "appraised | partially_appraised | not_appraised | cannot_verify", "verdict_basis": "一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "penalty_total=5 …", "kind": "inferred", "source_id": "Q01", "location": "papers[0]", "evidence": [{"paragraph_id": "doc-q01#methods", "quote": "原文原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "unbacked_evidence": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | invalid", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py，问题串带组标签）
1. [enum] judgment/grade/category/bias_direction/paper_type/run_status.state 枚举非法。
2. [coverage] 量表 domain 漏覆盖；judged=true 但缺完成要素（judgment 非法、弃权/不适用无说明）。
3. [grading] grade 与 grade_map[judgment] 不符（口径漂移）；负面判定缺 bias_direction；汇总复算与 risk_summary 不符；penalty 数字无回证 → unbacked_numbers 判 FAIL。
4. [evidence] judgment=adequate/concerns/inadequate 但 evidence_quote 为空；引文在 claims 无逐字回证或在 case.json 来源文本中不存在 → unbacked_evidence 判 FAIL；rationale 为空。
5. [defect] category 与 category_map[judgment] 不符；inadequate 归 reporting_gap 或 unreported 归 design_flaw（两类混淆）。
6. [pending] unassessable 未登记 pending_review（缺 reason/needed_action）。
7. [structure]/[contract] steps 为空、coverage 汇总不符、verdict 与判定进度矛盾、缺 output_contract 字段；闸门（case_contract / rules_ledger / grade_rollup / rollup_output）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，标题摘要均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/grade_rollup.py --result examples/example-result.json --rules /tmp/wk/grading_rules.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --rubric /tmp/wk/grading_rules.json --out /tmp/vc.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/sg.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 全文不可得 / 仅有摘要 | material_gaps 登记；评价范围如实缩小，verdict 写 partially_appraised 或 cannot_verify，绝不补造全文 |
| 关键证据缺失 | judgment=unassessable + abstain_reason + 登记 pending_review；弃权不罚分，不臆断 |
| 图表不可解析 | 在该条 evidence_location 注明不可解析及原因，按可用文本评价并在 uncertainties 登记 |
| 维度不适用（如队列无盲法） | judgment=not_applicable + na_reason，grade 置 null，不参与罚分 |
| 语言/预印本状态特殊 | paper_type 如实标注，量表条目按类型裁剪并在 review_scope 写明 |
| 汇总与引文对不上 | 以 grade_rollup 与来源文本为准修复评价，不改证据凑结论；修不了如实登记 uncertainties |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 量表与分级口径是本技能事前声明并机械执行的设定（题面未给定时按保守量级设定并写明），不冒充 Cochrane/JBI 等外部标准；条目裁剪在 review_scope 写明。
- 仅评价输入提供的文本：不做同行评审、不核验事实真伪、不支撑临床或政策决策。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
