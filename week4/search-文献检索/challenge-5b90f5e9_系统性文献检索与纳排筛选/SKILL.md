---
name: sysrev-search-screen
description: Systematic literature search & screening skill (PRISMA-style). Converts a research question (PICO) into a declared search protocol, pre-declares versioned inclusion/exclusion criteria BEFORE any judgment, mechanically deduplicates records (DOI exact / title normalized / fuzzy with human escalation), screens every record with decision+reason code dictionary (RC-EX-*/RC-PD-*) + criteria_ref + verbatim evidence quote, arbitrates dual-annotator disagreements without majority masking, recomputes the PRISMA funnel (identified→duplicates_removed→screened→included/excluded/pending) with closure checking, and re-runs normal-vs-degraded ablation to embed measured gain_evidence and efficiency into result.json. verify_check mechanically re-verifies criteria pre-declaration, reason-code validity, evidence back-referencing and funnel closure; all failure paths exit 0. Use when the task asks to run a reproducible screening flow over a finite record snapshot with auditable counts and reviewable per-record decisions.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 search_protocol / criteria / records / funnel / conflicts / pending_review / coverage / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全记录覆盖**：输入题录**每一条**都必须逐条判定（judged=true 或写明 pending_reason），禁止只处理前几条就收尾；缺摘要/缺 DOI/疑似重复的条目登记 missing_metadata 或 conflicts，不脑补、不跳过。
4. **不编造**：evidence_quote 必须逐字摘自该条目的实际摘要/原文并附位置；漏斗数字必须来自 flow_audit 实际复算；材料缺失就登记，不改证据凑结论；文不对题就照实标 exclude。
5. **标准事前声明**：纳排标准必须在**任何逐条判定之前**声明版本号与 declared_at（写入 /app/work/criteria_ledger.json 台账），之后禁止口头修改；确需修改必须新增版本并逐条回溯重判受影响记录（防标准漂移）。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定研究问题、纳排标准与题录快照（真实署名论文 + 少量合成重复导出/分歧夹具，夹具是**输入**不是期望答案），完成**检索协议声明、确定性去重、逐条纳排判定、双人分歧仲裁、漏斗计数审计、待复核登记**。不做实时数据库全域召回、不全文精读、不做数据提取与统计分析；检索无结果、标准冲突、元数据缺失照实登记，不补造文献。
关键词：标准先声明（版本化、防漂移）· 判得有据（理由码字典 + 逐字证据）· 数得闭合（漏斗逐级核对）· 分歧不掩盖（升级人工）。
- 输入：`/input/case.json`（研究问题 + 标准 + 题录 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–7 线性推进，禁止分支回环。

## 八步流程

### Step 0 — 自动落骨架与题录清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（records/papers/candidates 等）提取题录清单预填 `result.records[]`；生成 `/app/work/criteria_ledger.json` 标准台账模板。
- 脚本失败时手工兜底：读 case.json 抄题录清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 研究问题、检索协议与标准事前声明（1 次响应，判定前完成）
- 填 `result.research_question`（question/PICO/scope/time_range）与 `result.search_protocol`：检索式、数据库、字段、时间范围、语种限制、检索日期，并写明与纳入标准的逐条对应（criteria_mapping）。快照模式：不宣称实时全域召回。
- **事前声明标准**：`result.criteria` = `{version:"v1.0", declared_at, inclusion:[{criterion_id,text}], exclusion:[…(含理由码映射)]}`，同步登记进 /app/work/criteria_ledger.json。标准之间冲突时登记 `uncertainties.conflicts` 并声明优先序。**声明后禁止调整。**

### Step 2 — 机械去重（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/dedupe.py --result /app/output/result.json \
  --apply --report /app/work/dedupe_report.json
```
- DOI 归一化精确一致 / 标题归一化精确一致 → 直接合并（merge_basis=doi_exact|title_exact）；标题相似度 ≥0.90 → **escalated 交人工确认，不静默合并**（防"不同研究因标题相似被误合并"）。
- 保留规则（确定性）：published > 有 DOI > 标题长 > 序号小；合并依据写入 conflicts（kind=duplicate_versions）与 records[].duplicate_of/merge_basis。
- 归一化不用 str.isalpha（汉字 isalpha=True 会误伤），统一正则口径，中英文同一处理。

### Step 3 — 逐条纳排判定（1-2 次响应，广度优先）
对 `result.records[]` 中**每一条**题录，缺一不可：
- `decision` ∈ included/excluded/pending_review；included 必须 criteria_ref 引用 ≥1 条纳入标准 id；excluded 必须 reason_code 取自字典（RC-EX-*）且 criteria_ref 引用排除标准 id（RC-EX-DUPLICATE 除外）；pending_review 必须 reason_code 取 RC-PD-* 且写 pending_reason。
- 理由码字典见 `resources/reason_codes.json`（RC-EX-SCOPE/DESIGN/POPULATION/INTERVENTION/OUTCOME/LANGUAGE/TIME/PUBTYPE/DUPLICATE；RC-PD-NO-ABSTRACT/BORDERLINE/METADATA/DISAGREEMENT/FULLTEXT）。
- `evidence_quote` 逐字摘自该条摘要/原文 + `evidence_location`；`confidence` ∈ high/medium/low；`rationale` 写明命中哪条标准、依据哪段证据；仅有摘要、语种不符、对象部分重叠等边界情形按对应 RC-PD 码登记。

### Step 4 — 双人判定与分歧仲裁（1 次响应）
- 输入含标注者分歧夹具时：把双方意见记入 records[].annotation（annotator_a/b），登记 conflicts（kind=annotator_disagreement）；**实质性分歧不用平均/多数掩盖**——有明确判据依据则写仲裁结论（resolution=arbitrated + basis），判据不确定则 escalated 进 pending_review 由研究者最终确认。
- `result.pending_review[]`：每个 decision=pending_review 条目登记 `{record_id, reason, needed_action}`；escalated 冲突同样登记。**模型输出只是待复核建议，最终纳入由研究者确认。**

### Step 5 — 漏斗复算与闭合审计（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/flow_audit.py --result /app/output/result.json \
  --report /app/work/funnel_audit.json
```
- 机械复算 PRISMA 五级计数：identified → duplicates_removed → screened → included/excluded/pending_review，排除原因按 reason_code 分组（合计须 == excluded），closure=closed 才算闭合；存值与复算不符会被逐条记差异并覆盖为复算值，不静默改平。
- `result.steps[]` 审计日志逐步记录 in_count/out_count/operator/command。

### Step 6 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭标准声明核对 / 理由回证 / 漏斗闭合 / 待复核登记），把**真实数字**写进 `result.gain_evidence`：runs[]、delta_normal_minus_degraded、mechanism_to_metric_map、boundaries、failure_conditions。
- 五项对照指标：纳排违规漏检数 / 计数失据漏检数 / 证据缺失漏检数 / 待复核漏登记数 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- `--inject-pollution` 在**副本**上注入污染（纳入无依据 / 排除原因缺失 / 计数篡改 / 清空待复核 / 清空 claims）做反例自测：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence` = `{available:false, reason:"…"}` 与 `efficiency` 同理，不得编数字。退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 7 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：题录每一条都有判定或待复核吗？每个 included/excluded 都能回溯到标准 id 与逐字证据吗？漏斗五级计数与排除原因分布闭合吗？

## 输出 schema（result.json — 平台通用契约五字段 + 业务键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"question": "…", "pico": {"population": "…", "intervention": "…", "comparison": "…", "outcome": "…", "study_design": "…"}, "scope": "…", "time_range": "…"},
    "search_protocol": {"databases": [], "query_string": "…", "fields": [], "time_range": "…", "language_limits": "…", "search_date": "…", "criteria_mapping": "…"},
    "criteria": {"version": "v1.0", "declared_at": "判定前时点", "inclusion": [{"criterion_id": "IN-01", "text": "…"}], "exclusion": [{"criterion_id": "EX-01", "text": "…"}]},
    "records": [{"record_id": "R01", "source_ref": "records[0]", "title": "…", "year": 2024, "doi": "…", "source_db": "…", "venue_type": "published", "decision": "included", "reason_code": null, "criteria_ref": ["IN-01"], "evidence_quote": "逐字摘录", "evidence_location": "records[0].abstract", "confidence": "high", "rationale": "…", "duplicate_of": null, "merge_basis": null, "missing_metadata": [], "annotation": {"annotator_a": null, "annotator_b": null}, "pending_reason": null, "judged": true}],
    "funnel": {"identified": 7, "duplicates_removed": 1, "screened": 6, "excluded": 1, "included": 3, "pending_review": 2, "excluded_by_reason": {"RC-EX-DESIGN": 1}, "closure": "closed", "closure_note": "…"},
    "conflicts": [{"record_ids": ["R03", "R04"], "kind": "duplicate_versions | annotator_disagreement", "resolution": "merged | escalated | arbitrated", "arbitration": {"basis": "…", "decided_by": "…"}, "evidence": "…"}],
    "pending_review": [{"record_id": "R05", "reason": "…", "needed_action": "…"}],
    "coverage": {"total_records": 7, "judged_records": 7, "included": 3, "excluded": 1, "pending_review": 2, "duplicates_merged": 1, "ratio": 1.0},
    "steps": [{"step": "step2", "action": "…", "in_count": 7, "out_count": 6, "operator": "scripts/dedupe.py", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success | partial | unable_to_determine | refused", "reason": null, "manual_takeover": []},
    "verdict": "screened | partially_screened | not_screened | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "判定+理由码+证据", "kind": "reported | inferred", "source_id": "R01", "location": "records[0]", "evidence": [{"paragraph_id": "records[0].abstract", "quote": "摘要原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. decision / confidence / venue_type / verdict / run_status.state 枚举非法；reason_code 不在理由码字典。
2. included 无 criteria_ref 或引用不存在的纳入标准；excluded 无 EX 系理由码或引用不存在的排除标准；pending 无 PD 系理由码或 pending_reason 空。
3. criteria.version / declared_at 为空；标准台账存在多版本但判定引用版本 != 最终版本（标准漂移）。
4. 已判定条目 rationale 空；included/excluded 缺 evidence_quote 或 location；证据在 claims 无逐字回证。
5. 漏斗存值与复算不符；excluded_by_reason 分布与逐条复算不一致；closure != closed；coverage 汇总与实际条目不符；duplicate_of 未登记 conflicts。
6. pending 未登记进 pending_review（缺 reason/needed_action）；escalated 冲突未进待复核；steps 为空或无可执行 command。
7. 闸门（case_contract / criteria_ledger / flow_audit_output / dedupe_output）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，标题摘要 DOI 均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/dedupe.py --result examples/example-result.json --apply --report /tmp/dedupe.json
python3 scripts/flow_audit.py --result examples/example-result.json --report /tmp/funnel.json
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 题录清单为空 | records 空、funnel.identified=0、verdict=cannot_verify 或 not_screened，status 写明，绝不补造文献 |
| 无摘要 / 缺 DOI / 年份 | missing_metadata 登记 + 置信度降级；无法据题录判定则 pending（RC-PD-NO-ABSTRACT/METADATA）并登记待复核 |
| 标准互相冲突 | uncertainties.conflicts 登记双方 + 声明优先序；确需改标准则新增版本并回溯重判 |
| 预印本/重复导出 | dedupe 判 doi_exact/title_exact 直接合并（保留 published）；title_similar 升级人工，不静默合并 |
| 标注者分歧 | 实质性分歧不掩盖：有判据依据则仲裁（arbitrated），否则 escalated 进 pending_review |
| 大量待复核 | pending_review 逐条登记 reason+needed_action，coverage.pending_review 与漏斗一致 |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 已知限制
- 仅处理输入题录快照：不做实时数据库全域召回、不全文精读、不做系统综述后续阶段。
- 理由码字典是本技能设定的方法学约定（参考 PRISMA 常规排除原因），可按综述自行扩展并声明版本。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
