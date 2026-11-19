---
name: patent-search-verify
description: Patent and technical literature search skill (number normalization / family merging / legal status registry / cross-citation backback / pending review). Normalizes publication/grant/application numbers (country code + digits + kind code) and re-derives each stored norm from its raw number, merges simple-family members by normalized priority or application number with declared scope, registers legal status with source/query date/lag note and green-yellow-red licensing tiers per source, back-backs every evidence quote and norm_number through the claims evidence chain, and registers pending items for human review. Verify_check mechanically recomputes families and screening order, checks number-label consistency, registry completeness and quote backback, and re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency counters into result.json. Use when the task asks to search and screen patents/papers with traceable numbers, family relations, legal status and citations.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 items / family_groups / legal_status_registry / cross_registry / screening / coverage / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全记录覆盖**：候选集**每一条**（专利或论文）都必须逐条判定（judged=true 或写明 pending_reason），禁止只处理前几条就收尾；缺号码/缺优先权/OCR 边界保留的条目登记 missing_metadata，不脑补、不跳过。
4. **不编造**：evidence_quote 必须逐字摘自该条目的实际著录项/摘录/原文并附位置；号码、族关系、法律状态必须来自实际输入材料与登记来源，对不上就登记，不改证据凑结论；只有二手聚合站数据时必须标注 red 分级、不得冒充官方著录项。
5. **口径事前声明**：族归并口径（simple/extended）、筛选破平规则、授权分级策略必须在**任何筛选之前**写入 /app/work/ledger.json 与 result（declared_at），之后禁止调整；纳排标准逐条给 criterion_id，判定必须引用 id。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定检索问题、纳排标准与候选条目集（专利 + 技术文献，含少量同族/镜像/OCR 截断夹具），完成**号码规范化、专利族归并、法律状态登记、论文-专利交叉引用回证、技术要点摘录与待复核登记**。付费库实时抓取、绕过付费墙、侵权判定、自由实施分析、专利价值评估不在范围；检索无结果、字段缺失、权限不足照实登记，不补造文献。
关键词：号得规范（norm 可复算）· 族得有据（同键归并、口径声明）· 状态可查（来源+查询日期+滞后说明）· 引证可回（逐字回证）· 授权分明（绿黄红分级）。
- 输入：`/input/case.json`（检索问题 + 标准 + 候选条目 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与候选清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（patents/papers/candidates 等）提取候选清单预填 `result.items[]`（kind/raw_number/priority/application_number 预填）；生成 `/app/work/ledger.json` 口径台账模板。
- 脚本失败时手工兜底：读 case.json 抄候选清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 检索问题、纳排标准与口径台账（1 次响应，筛选前完成）
- 填 `result.research_question` 与 `result.criteria`（IN-01…/EX-01…），标准冲突时登记 `uncertainties.conflicts` 并声明优先序。
- **事前声明口径**：`/app/work/ledger.json` = `{declared_at, family_scope_default: simple|extended, screening_tie_break, licensing_policy}`；同步在 result.steps 记录声明动作。**声明后禁止调整。**
- 登记 `result.sources[]`：每个实际使用的数据源一条 `{source_id, name, version, query_date, licensing: green|yellow|red, display_scope}`；红=仅登记存在性，黄=仅登记元数据，绿=可摘录展示。

### Step 2 — 逐条判定（1-2 次响应，广度优先）
对 `result.items[]` 中**每一条**候选，缺一不可：
- `relevance` ∈ direct/indirect/irrelevant；`label` ∈ keep/pending/exclude：keep 必须命中 ≥1 条纳入标准（criteria_hit 填 id）；exclude 必须命中 ≥1 条排除标准（excluded_by）；pending 必须写 pending_reason；
- `evidence_quote` 逐字摘录 + `evidence_location` 注明位置；`confidence` ∈ high/medium/low；`rationale` 一句话写明命中哪条标准；
- **专利条目**：`raw_number` 保留原样；OCR 截断/字段缺失填 `missing_metadata[]`（如 ["priority"]）；`legal_status` = `{status, effective_date, source, query_date, lag_note}`，status 是登记转述而非官方实时结论，source 必须是 sources[] 里已登记的 id；
- **技术要点**：`tech_points[]` 逐条 `{point_id, quote, location}`，quote 逐字摘录；
- **交叉引用**：论文引专利/专利引论文填 `cross_refs[]` = `{ref_kind, target_id, evidence_quote, location}`，target_id 必须指向 items 里真实存在的条目，引证句逐字摘录；
- **重复/镜像**：同号转载记录 → `duplicate_of` 指向保留条目 + `conflicts[]` 登记 merged；无法确认同一性则 escalated 进待复核。

### Step 3 — 号码规范化 + 族归并 + 筛选排序（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/norm_family.py --result /app/output/result.json
```
- 机械归一号码（国家码+数字+种类码；norm 必须等于 raw 的归一结果）、按声明口径用规范化优先权号（缺省申请号）归并族组 `result.family_groups[]`（family_id/key/key_kind/member_ids/scope/evidence），无族键条目 family_id=null 不臆造族关系；按 relevance 层级→confidence→item_id 产出确定性 `result.screening`。
- 脚本失败时手工兜底：按同一规则手算并在 steps 注明「手算」，事后仍须重跑脚本核对。

### Step 4 — 登记与证据链（1 次响应）
- `result.pending_review[]`：每个 label=pending 条目登记 `{item_id, reason, needed_action}`；escalated 冲突同样登记。
- `result.legal_status_registry[]` / `result.cross_registry[]`：与条目级 legal_status / cross_refs 一致（同源登记，不写矛盾状态）。
- `result.coverage`：total_candidates / judged_items / keep / pending / exclude / families_merged / duplicates_merged / ratio，与实际条目一致。
- **claims 证据链**：每个 keep/pending 条目在 `claims[]` 各有一条 `{claim_id, text, kind, source_id, location, evidence:[{paragraph_id, quote}]}`；text 须含「纳排命中 + 证据说明 + norm_number」。**号码逐字回证**：evidence_quote 必须逐字出现在对应 quote 里、norm_number 必须出现在 claim text/quote 里（空白归一化后子串匹配），未回证号码列入 unbacked_numbers 并判 FAIL。
- `result.verdict`（verdict_basis 一句话）：`screened` 全部逐条判定；`partially_screened` 部分；`not_screened` 无有效判定；`cannot_verify` 材料缺口且 material_gaps 非空。
- `result.run_status` = `{state, reason, manual_takeover[]}`，state ∈ success|partial|unable_to_determine|refused。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭号码与标签一致性 / 族归并复算 / 证据回证 / 登记完备性），把**真实数字**写进 `result.gain_evidence`。
- 四项对照指标：号码/标签违规漏检数 / 族归并失据漏检数 / 证据回证漏检数 / 登记缺失漏检数（另有 manual_review_items、steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- `--inject-pollution` 在**副本**上注入污染（keep 无依据 / 篡改 norm_number / 幽灵族 / 清空待复核 / 清空 claims）做反例自测：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 脚本跑不了时手工写 `gain_evidence` = `{available:false, reason:"…"}`，不得编数字。
- 退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每一条都有判定或待复核吗？每个 keep/交叉引用/法律状态都能回溯到标准 id、来源与逐字证据吗？pending 与 escalated 都登记进 pending_review 了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"question": "…", "scope": "…", "time_range": "…"},
    "criteria": {"inclusion": [{"criterion_id": "IN-01", "text": "…"}], "exclusion": [{"criterion_id": "EX-01", "text": "…"}]},
    "sources": [{"source_id": "src-1", "name": "…", "version": "…", "query_date": "…", "licensing": "green|yellow|red", "display_scope": "…"}],
    "items": [{"item_id": "P01", "kind": "patent", "raw_number": "US 2020/0123456 A1", "norm_number": "US20200123456A1", "priority_numbers": ["US 16/123,456"], "relevance": "direct", "label": "keep", "criteria_hit": ["IN-01"], "excluded_by": [], "evidence_quote": "逐字摘录", "confidence": "high", "rationale": "…", "family_id": "F-US16123456", "legal_status": {"status": "…", "source": "src-1", "query_date": "…", "lag_note": "…"}, "cross_refs": [{"ref_kind": "npl_cites_patent", "target_id": "P05", "evidence_quote": "…"}], "tech_points": [{"point_id": "tp-01", "quote": "…", "location": "…"}], "duplicate_of": null, "missing_metadata": [], "pending_reason": null, "judged": true}],
    "family_groups": [{"family_id": "F-US16123456", "key": "US16123456", "key_kind": "priority", "member_ids": ["P01", "P02"], "scope": "simple", "evidence": "…"}],
    "legal_status_registry": [{"item_id": "P01", "status": "…", "source": "src-1", "query_date": "…", "lag_note": "…"}],
    "cross_registry": [{"from_id": "P05", "to_id": "P01", "ref_kind": "npl_cites_patent", "evidence": "…", "location": "…"}],
    "screening": {"ordered_ids": ["P01"], "ties": [], "rule": "relevance 层级→confidence→item_id"},
    "coverage": {"total_candidates": 6, "judged_items": 6, "keep": 3, "pending": 1, "exclude": 2, "families_merged": 1, "duplicates_merged": 1, "ratio": 1.0},
    "conflicts": [{"item_ids": ["P01", "P03"], "kind": "duplicate_publication", "resolution": "merged", "evidence": "…"}],
    "pending_review": [{"item_id": "P04", "reason": "…", "needed_action": "…"}],
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "screened | partially_screened | not_screened | cannot_verify", "verdict_basis": "…",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "…", "kind": "reported | inferred", "source_id": "P01", "location": "items[0]", "evidence": [{"paragraph_id": "candidates[0].abstract", "quote": "…"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. kind / relevance / label / confidence / licensing / family_scope 枚举非法。
2. 专利条目无 raw_number、norm_number 不符合规范形式或与 raw 归一结果不一致；keep 无 criteria_hit；exclude 无 excluded_by；pending 无 pending_reason；irrelevant 标 keep；direct 标 exclude 且未登记 duplicate_of（跨级矛盾）。
3. 族归并复算不符：family_groups 成员不存在、有族键条目未归组或多组、同键成员被拆组；screening.ordered_ids 与机械复算顺序不一致。
4. 已判定条目 rationale 为空；keep 无 evidence_quote；keep/pending 的证据与 norm_number 在 claims 无逐字回证 → unbacked_numbers 判 FAIL；cross_refs 引证无逐字回证。
5. pending 未登记进 pending_review；duplicate_of 未在 conflicts 登记；escalated 未进待复核；keep 专利 legal_status 缺 status/source/query_date；source 未在 sources[] 登记授权分级；cross_refs 目标不存在。
6. coverage 汇总与实际条目不符；verdict 与判定进度矛盾；steps 为空或无可执行 command。
7. 闸门（case_contract / ledger_record / engine_output）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，号码/著录项/摘录均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/norm_family.py --result examples/example-result.json --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk/ledger.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 检索无结果 / 候选集为空 | items 空、coverage.total=0、verdict=cannot_verify 或 not_screened，绝不补造文献 |
| 号码缺失/OCR 截断/字段缺失 | missing_metadata 登记 + 置信度降级；族归属不明则 pending 并登记待复核 |
| 只有二手聚合站数据 | sources[] 登记 red 分级，结论标注「非官方著录项」，不冒充登记依据 |
| 法律状态冲突/状态过期 | legal_status.lag_note 写明查询日期与滞后；冲突登记 uncertainties.conflicts，不混用两套口径 |
| 同号转载/镜像记录 | duplicate_of + conflicts 登记 merged（保留原始登记条目）；无法确认则 escalated 进待复核 |
| 算力不足/运行中断 | 保留已判定部分，status=partial，changelog 注明截断位置，仍写 result.json |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |

## 已知限制
- 仅处理输入候选集内条目：不做付费库实时检索、不绕过付费墙、不抓受限库原文。
- 族归并按声明口径的族键机械归并；简单族与扩展族的语义差异以 ledger 声明为准，不冒充官方 INPADOC 口径。
- 法律状态是登记快照转述（来源+查询日期+滞后说明），不是官方实时核验结论。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
