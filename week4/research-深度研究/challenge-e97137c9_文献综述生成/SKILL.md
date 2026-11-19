---
name: lit-review-bind
description: Literature review generation skill (theme grouping from the corpus / paragraph-source binding / verbatim quote back-check / dispute-vs-consensus table / coverage with omission registry). Groups screened papers into corpus-grounded themes (timeline and method lanes declared before drafting), binds every paragraph to real paper_ids, mechanically back-checks every claim quote verbatim against the source text in case.json, registers contradictory findings side-by-side with strength labels (established/suggestive/disputed) so conclusions never exceed what sources support, and recomputes citation coverage while registering every uncited paper. Verify_check enforces all four machine-check points (paragraph-source binding, verbatim quote evidence, dispute registration, coverage) and re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency into result.json. Use when the task asks to draft a literature review where every assertion must trace back to a specific source and disagreements must stay visible.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 themes / outline / evidence_table / disputes / omissions / coverage / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全记录覆盖**：输入文献**每一条**都必须逐条判定（judged=true 或写明 pending_reason）；每篇纳入（keep）文献必须归属 ≥1 个主题或登记 omissions——综述只准丢文献于登记处，不准静默丢。
4. **不编造**：claims[].evidence[].quote 必须逐字摘自该文献在 case.json 的实际正文/摘要并附位置；本方覆盖数字必须来自 theme_group 实际重算；对不上就登记，不改证据凑结论。
5. **大纲事前声明**：主题分组/时间脉络/方法论脉络必须在**草稿写作之前**写定（declared_at 记入 /app/work/outline.json 台账），之后只允许补充新文献、不允许推翻已绑定证据；综述结论不超出文献支持范围。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增段落，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定研究问题、纳排标准与文献集，完成**筛选 → 主题归纳 → 证据组织与回链 → 带引用草稿**四步，并把分歧与共识并列呈现。底层数据库检索、单篇精读、全文翻译、润色与投稿选刊不在范围；缺全文/元数据不全/结论冲突照实登记，不补造文献。
关键词：分得准（主题从文献长出来）· 绑得住（段落必带来源）· 查得回（引用逐字回证）· 不抹平（分歧对照、强度分级）· 漏登记（覆盖可核、遗漏入册）。
- 输入：`/input/case.json`（研究问题 + 标准 + 文献 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与文献清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（papers/literature/references 等）提取文献清单预填 `result.items[]`；生成 `/app/work/outline.json` 大纲台账模板。
- 脚本失败时手工兜底：读 case.json 抄文献清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 研究问题与纳排标准（1 次响应）
- 填 `result.research_question`（question/scope/time_range）与 `result.criteria`：纳入/排除标准逐条编号（IN-01…/EX-01…）；标准冲突或口径不明登记 `uncertainties.conflicts` 并声明优先序。

### Step 2 — 逐条筛选与主题归纳（1-2 次响应，写作前完成）
对 `result.items[]` **每一条**文献：`label` ∈ keep/pending/exclude（keep 命中 ≥1 条纳入标准，exclude 命中 ≥1 条排除标准，pending 写 pending_reason 并登记 pending_review）；缺元数据填 missing_metadata；重复报道 `duplicate_of` + conflicts 登记。
再归纳 `result.themes[]`：每主题 `{theme_id, title, basis, paper_ids, boundary, dispute_ids}`——**basis 必须写明该主题从哪些文献的什么分歧/方法/对象中长出来**，禁止套「背景/方法/挑战/展望」通用框架；同一文献可跨主题（跨主题会记入 overlap 供复核）。同时写 `/app/work/outline.json`（declared_at + 主题顺序 + 时间脉络/方法论脉络备注）。

### Step 3 — 草稿生成与段落-来源绑定（1-2 次响应）
- 写 `result.outline.sections[]`：每段 `{para_id, text, claim_ids, source_ids}`——**非空段落 source_ids 必须非空**，且只能引用输入文献集内的 paper_id。
- 每条实质论断在顶层 `claims[]` 登记：`{claim_id, text, strength, source_ids, para_ref, dispute_id, evidence:[{paragraph_id, quote}]}`。strength ∈ **established（≥2 来源）/ suggestive（提示性）/ disputed（须指向 dispute_id）**——结论强度不得超出文献支持范围。
- `result.evidence_table[]`：`{row_id, paper_id, quote(逐字), location, claim_id, strength}`，使草稿写作能反向查到证据行。

### Step 4 — 分歧对照与覆盖核对（1 次脚本调用 + 1 次响应）
```bash
python3 /skills/weekly-skill/scripts/dispute_table.py --result /app/output/result.json --emit-into
python3 /skills/weekly-skill/scripts/theme_group.py --result /app/output/result.json --case /input/case.json --emit-into
```
- `dispute_table.py` 机械核对分歧登记与强度不越界并回写顶层 `dispute_audit`；同一问题结论相反的文献在 `result.disputes[]` **双方并列**（各立场附 paper_ids + 逐字 quote，双方文献不得重叠），共识条目写 consensus_text + 支撑文献。
- `theme_group.py` 机械重算 `result.coverage`（键归属该脚本）并回写：total/included/cited_in_outline/uncited/ratio；**未入大纲的 keep 文献必须在 omissions[] 登记原因**，否则判 FAIL。
- `result.verdict`：`drafted`（全链完成）/ `partially_drafted` / `not_drafted` / `cannot_verify`（材料缺口且 material_gaps 非空）；`run_status` 照实。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭段落绑定 / 逐字回证 / 分歧对照 / 覆盖检查），把**真实数字**写进 `result.gain_evidence`。
- 五项对照指标：无来源论断漏检数 / 编造引用漏检数 / 分歧漏检数 / 覆盖遗漏漏检数 / 需人工核对条目数。数字全部来自实跑，**不得手填或臆造**。
- `--inject-pollution` 在**副本**上注入污染（无来源论断 / 编造引用 / 清空 omissions / 拆散分歧对照）：正常模式须抓到（`caught_by_normal_mode=true`），原 result.json 不被改动。
- 同时写 `result.efficiency`（墙钟、字节、检查项数、条目数 + reproduce 命令）；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- 退化模式结果**仅用于增益对照**，不得当作交付自检结论；脚本跑不了时手工写 `available:false` + 原因。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每条文献都有判定且每篇纳入都进了主题或遗漏登记吗？每个非空段落都绑定了真实来源、每条引用都逐字回证了吗？分歧是否双方并列、结论强度是否未越界？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "…", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"question": "…", "scope": "…", "time_range": "…"},
    "criteria": {"inclusion": [{"criterion_id": "IN-01", "text": "…"}], "exclusion": [{"criterion_id": "EX-01", "text": "…"}]},
    "items": [{"paper_id": "R01", "source_ref": "papers[0]", "title": "…", "label": "keep", "criteria_hit": ["IN-01"], "excluded_by": [], "theme_ids": ["T1"], "duplicate_of": null, "missing_metadata": [], "pending_reason": null, "judged": true}],
    "themes": [{"theme_id": "T1", "title": "…", "basis": "主题从哪些文献长出来", "paper_ids": ["R01"], "boundary": "…", "dispute_ids": ["D-01"]}],
    "outline": {"order": ["T1"], "sections": [{"section_id": "S1", "theme_id": "T1", "heading": "…", "timeline_note": "…", "method_note": "…", "paragraphs": [{"para_id": "P-01", "text": "…", "claim_ids": ["c-01"], "source_ids": ["R01"]}]}]},
    "evidence_table": [{"row_id": "E-01", "paper_id": "R01", "quote": "逐字摘录", "location": "papers[0].abstract", "claim_id": "c-01", "strength": "established"}],
    "disputes": [{"dispute_id": "D-01", "question": "…", "status": "disputed|consensus|unresolved", "positions": [{"side": "positive", "paper_ids": ["R01"], "quote": "…"}], "consensus_text": "…", "note": "…"}],
    "omissions": [{"paper_id": "R02", "reason": "未入大纲的原因", "needed_action": "…"}],
    "coverage": {"total_papers": 6, "included_papers": 4, "cited_in_outline": 4, "uncited": 0, "omissions_registered": 0, "ratio": 1.0},
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success|partial|unable_to_determine|refused", "reason": null, "manual_takeover": []},
    "verdict": "drafted | partially_drafted | not_drafted | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "…", "strength": "established|suggestive|disputed", "source_ids": ["R01"], "para_ref": "sections[0].paragraphs[0]", "dispute_id": null, "evidence": [{"paragraph_id": "R01", "quote": "逐字摘录"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_quotes": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py 汇总四组）
1. 非空段落无 source_ids；来源不在输入文献集（来源越界）；claim_ids 断链。
2. claim 无来源（无来源论断）；evidence.quote 未在来源正文逐字命中 → unbacked_quotes 判 FAIL（编造引用拦截）；回证底本缺失登记 unverifiable_text。
3. disputed 无对立双方/双方文献重叠/缺逐字 quote；consensus 缺支撑文献或表述；established 来源 <2（结论超出支持范围）；disputed claim 的 dispute_id 断链。
4. keep 未归属主题且未登记 omissions；uncited 未登记；coverage 手填与机械重算不符；主题缺 basis/title/paper_ids。
5. label/pending_reason/verdict/run_status 枚举非法；verdict 与 claims 进度矛盾；steps 为空或无可执行 command。
6. 闸门（case_contract / outline_ledger / outline_written）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，标题摘要均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/draft_bind.py --result examples/example-result.json --case examples/example-case.json --out /tmp/db.json
python3 scripts/dispute_table.py --result examples/example-result.json --out /tmp/dt.json
python3 scripts/theme_group.py --result examples/example-result.json --case examples/example-case.json --out /tmp/tg.json
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 检索无结果 / 文献集为空 | items 空、coverage.total=0、verdict=cannot_verify 或 not_drafted，绝不补造文献 |
| 缺全文/元数据不全 | missing_metadata 登记 + 该条 pending 并进 pending_review；不脑补 |
| case 未提供正文 | 逐字回证以 evidence_table 摘录为底本并登记 unverifiable_text，如实降级 |
| 结论互相冲突 | disputes[] 双方并列 + uncertainties.conflicts 登记；claims 标 disputed 并指向 dispute_id |
| 文献不入大纲 | omissions[] 登记原因（如：低相关、待人工），coverage 留痕，不静默丢弃 |
| 算力/时间不足 | 保留已完成段落，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅处理输入文献集内材料：不做实时检索、不全文精读、不做单篇事实审查（相邻课题输入）。
- established 的「≥2 来源」是本技能的保守口径（题面未给定阈值时按可核验性保守设定并写明），不冒充外部标准。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
