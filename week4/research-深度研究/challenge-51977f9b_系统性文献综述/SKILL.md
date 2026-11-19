---
name: sysrev-review-synthesis
description: Systematic literature review skill (PRISMA-style full pipeline). Registers a review protocol (question/PICO + search string + versioned inclusion/exclusion criteria) BEFORE any judgment in a protocol ledger, mechanically deduplicates records (DOI/title exact merge, fuzzy escalation), screens every record with decision+reason-code dictionary+criteria_ref+verbatim evidence, appraises quality of each included study on a declared scale whose overall grade is mechanically derived from dimension judgments, extracts structured data (study_design/sample/effect with per-block verbatim back-referencing to source text), synthesizes graded conclusions whose strength (strong/moderate/weak/insufficient) must equal a rule-derived level from supporting-record quality and conflicts, recomputes the PRISMA funnel with closure checking, and runs normal-vs-degraded ablation plus pollution selftest to embed measured gain_evidence. All validators exit 0 and report verdict in JSON. Use when the task asks for a reproducible systematic-review flow with auditable counts, structured extraction back-evidence and consistent conclusion strength grading.
---
## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 review_registration / search_protocol / criteria / records / funnel / quality_appraisal / extraction / synthesis / pending_review / coverage / steps / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全流程逐条覆盖**：输入题录每一条都必须逐条判定；纳入研究每一条都必须质量评价+结构化提取；综合结论每一条都必须强度分级；缺什么登记什么，不跳过、不脑补。
4. **不编造**：evidence_quote 与提取项 evidence.quote 必须逐字摘自实际材料并附位置；漏斗数字来自 flow_audit 复算；质量等级由量表推导；强度由规则推导；材料缺失就登记，文不对题就照实 exclude。
5. **协议事前声明**：综述协议（研究问题/检索式/纳排标准）必须在任何判定之前注册版本号与 registered_at（写入 /app/work/protocol_ledger.json 台账）；之后禁止口头修改，确需修改必须新增版本并逐条回溯重判（防协议漂移）。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定研究问题与题录快照（真实署名论文 + 少量合成重复导出/夹具，夹具是**输入**不是期望答案），完成**协议注册 → 检索式声明 → 逐条筛选 → 质量评价 → 结构化提取 → 分级综合**六段 PRISMA 式流程。不做实时数据库全域召回、不全文精读翻译、不论文写作润色、不替代学术事实核验；检索无结果、标准冲突、材料缺失照实登记，不补造文献。
关键词：协议先注册（版本化防漂移）· 判得有据（理由码 + 逐字证据）· 评得一致（量表推导等级）· 提得有源（结构化逐字回证）· 综得守界（强度分级规则化）· 数得闭合（漏斗逐级核对）。
- 输入：`/input/case.json`（研究问题 + 题录 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用 Python 标准库。
- 按 Step 0–8 线性推进，禁止分支回环。

## 九步流程

### Step 0 — 自动落骨架与题录清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全字段 → 写骨架；从 case.json 常见键提取题录清单预填 `result.records[]`；生成 `/app/work/protocol_ledger.json` 协议注册台账模板。
- 脚本失败时手工兜底：抄题录清单与 output_contract 字段名手写骨架（键一个不缺）。

### Step 1 — 协议注册与检索式/标准事前声明（1 次响应，判定前完成）
- 填 `result.review_registration`（review_id/registered_at/protocol_version）并登记台账；填 `result.research_question`（PICO）与 `result.search_protocol`（检索式、数据库、字段、时间范围、语种、检索日期、criteria_mapping）；声明 `result.criteria`（版本 v1.0 + declared_at + 逐条编号纳排标准）。**声明后禁止调整。**标准冲突时登记 uncertainties.conflicts 并声明优先序。

### Step 2 — 机械去重（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/dedupe.py --result /app/output/result.json \
  --apply --report /app/work/dedupe_report.json
```
- DOI/标题归一化精确一致 → 直接合并（merge_basis=doi_exact|title_exact）；标题相似 ≥0.90 → **escalated 交人工**；保留规则 published>有 DOI>标题长>序号小；归一化统一正则口径（不用 isalpha，防汉字误判）。

### Step 3 — 逐条纳排判定（1-2 次响应，广度优先）
对 `result.records[]` 每一条：decision ∈ included/excluded/pending_review；included 必须 criteria_ref 引用纳入标准 id；excluded 必须 RC-EX-* 理由码 + 排除标准 id（RC-EX-DUPLICATE 除外）；pending 必须 RC-PD-* + pending_reason；每条已判定记录给 rationale + confidence + evidence_quote（逐字）+ evidence_location。理由码字典见 `resources/reason_codes.json`。

### Step 4 — 质量评价（1-2 次响应 + 1 次脚本，必做）
- 用 `resources/quality_scales.json` 量表（Q1-Q6，判定 yes/partly/no/unclear）对**每条纳入（非重复）记录**逐维度评价并附 evidence_location；`overall_grade` 必须等于量表推导（yes=1/partly=0.5/no=0，均分 ≥0.8→high、≥0.5→moderate、<0.5→low），并写 grade_basis。
```bash
python3 /skills/weekly-skill/scripts/quality_audit.py --result /app/output/result.json --out /app/work/quality_audit.json
```

### Step 5 — 结构化数据提取（1-2 次响应 + 1 次脚本，必做）
- 对每条纳入记录填 `result.extraction.items[]`：study_design / sample（size+units）/ effect（measure+value+ci+direction）三块，**每块 evidence.quote 逐字摘自该记录实际材料** + location；缺值写 extraction_notes 说明。
```bash
python3 /skills/weekly-skill/scripts/extraction_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/extraction_audit.json
```

### Step 6 — 证据综合与强度分级（1-2 次响应 + 1 次脚本，必做）
- 填 `result.synthesis`：conclusions[]（text/strength/strength_basis/supporting_records/conflicting_records）、conflict_matrix、gaps、bias_registry。strength ∈ strong/moderate/weak/insufficient，**必须等于规则推导**（`resources/strength_rules.json`：strong=≥3 支持+无冲突+支持质量∈{high,moderate}；moderate=≥2 支持+冲突≤1；weak=≥1 支持；insufficient=0 支持）。
```bash
python3 /skills/weekly-skill/scripts/synthesis_check.py --result /app/output/result.json --out /app/work/synthesis_check.json
```

### Step 7 — 漏斗复算与闭合审计（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/flow_audit.py --result /app/output/result.json \
  --report /app/work/funnel_audit.json
```
- 机械复算 PRISMA 五级计数（identified→duplicates_removed→screened→included/excluded/pending_review），excluded_by_reason 合计==excluded，closure=closed 才闭合；差异逐条记录并覆盖为复算值。

### Step 8 — 增益对照与双重自检（2 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --ledger /app/work/protocol_ledger.json --out /app/work/verify_check.json --emit-into
```
- gain_probe 同一输入跑 normal（七组校验全开）与 degraded（--ablate all）两遍，把实测差写进 result.gain_evidence + efficiency；`--inject-pollution` 在副本注入 14 项污染（漏斗篡改/提取无据/强度篡改/等级篡改/清协议声明等）做反例自测。退化结果仅用于增益对照，不得当交付自检。
- verify_check 判据是报告 `verdict`：FAIL 则按 problems 逐条修复 → 覆盖写 result.json → 重跑直到 PASS。

## 输出 schema（result.json 顶层五键 + result 业务键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": "…", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"question": "…", "pico": {"population": "…", "intervention": "…", "comparison": "…", "outcome": "…", "study_design": "…"}, "scope": "…", "time_range": "…"},
    "review_registration": {"review_id": "…", "registered_at": "判定前时点", "question_final": "…", "protocol_version": "v1.0"}, "search_protocol": {"databases": [], "query_string": "…", "fields": [], "time_range": "…", "language_limits": "…", "search_date": "…", "criteria_mapping": "…"},
    "criteria": {"version": "v1.0", "declared_at": "判定前时点", "inclusion": [{"criterion_id": "IN-01", "text": "…"}], "exclusion": [{"criterion_id": "EX-01", "text": "…"}]},
    "records": [{"record_id": "R01", "source_ref": "records[0]", "title": "…", "year": 2024, "doi": "…", "source_db": "…", "venue_type": "published", "decision": "included", "reason_code": null, "criteria_ref": ["IN-01"], "evidence_quote": "逐字摘录", "evidence_location": "records[0].abstract", "confidence": "high", "rationale": "…", "duplicate_of": null, "merge_basis": null, "missing_metadata": [], "annotation": {"annotator_a": null, "annotator_b": null}, "pending_reason": null, "judged": true}],
    "funnel": {"identified": 9, "duplicates_removed": 1, "screened": 8, "excluded": 2, "included": 5, "pending_review": 1, "excluded_by_reason": {}, "closure": "closed", "closure_note": "…"},
    "conflicts": [{"record_ids": [], "kind": "duplicate_versions | annotator_disagreement", "resolution": "merged | escalated | arbitrated", "arbitration": {"basis": "…", "decided_by": "…"}, "evidence": "…"}],
    "pending_review": [{"record_id": "R09", "reason": "…", "needed_action": "…"}],
    "quality_appraisal": {"scale": {"id": "QAS-GEN-1", "version": "v1.0", "dimensions": [{"dim_id": "Q1", "text": "…"}]}, "assessments": [{"record_id": "R01", "dimensions": [{"dim_id": "Q1", "judgment": "yes", "evidence_location": "…"}], "overall_grade": "high", "grade_basis": "均分 0.83 → high", "notes": null}], "coverage_note": "…"},
    "extraction": {"schema_note": "…", "items": [{"record_id": "R01", "study_design": {"value": "…", "evidence": {"quote": "逐字", "location": "…"}}, "sample": {"size": 48, "units": "participants", "population": "…", "evidence": {"quote": "逐字", "location": "…"}}, "effect": {"measure": "SMD", "value": 0.62, "ci": [0.21, 1.03], "direction": "…", "evidence": {"quote": "逐字", "location": "…"}}, "outcomes": [], "extraction_notes": null}]},
    "synthesis": {"conclusions": [{"conclusion_id": "S-01", "text": "…", "strength": "strong", "strength_basis": "…", "supporting_records": ["R01"], "conflicting_records": [], "location": "synthesis.conclusions[0]"}], "conflict_matrix": [{"conclusion_id": "S-01", "record_ids": [], "description": "…", "handling": "…"}], "gaps": [{"gap_id": "G-01", "description": "…", "related_conclusions": [], "evidence": "…"}], "bias_registry": [{"record_ids": [], "bias_type": "…", "description": "…", "influence": "…"}], "gaps_note": null, "bias_note": null},
    "coverage": {"total_records": 9, "judged_records": 9, "included": 5, "excluded": 2, "pending_review": 1, "duplicates_merged": 1, "ratio": 1.0},
    "steps": [{"step": "step2", "action": "…", "in_count": 9, "out_count": 8, "operator": "scripts/dedupe.py", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success | partial | unable_to_determine | refused", "reason": null, "manual_takeover": []},
    "verdict": "screened | partially_screened | not_screened | cannot_verify", "verdict_basis": "一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "…", "kind": "reported | inferred", "source_id": "R01", "location": "records[0]", "evidence": [{"paragraph_id": "records[0].abstract", "quote": "摘要原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL", "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py 六组，可 --ablate 分组消融）
1. **protocol**：criteria.version/declared_at 为空；review_registration 缺 registered_at/protocol_version；判定引用版本 != 协议台账最终版本（协议漂移）。
2. **screening**：decision/confidence/venue_type/verdict/run_status.state 枚举非法；reason_code 不在字典；included 无 criteria_ref 或引用不存在标准；excluded 无 EX 码或引用不存在标准；pending 无 PD 码/pending_reason 空；rationale 空；included/excluded 缺逐字证据或 claims 无回证；pending 未登记；escalated 冲突未进待复核。
3. **funnel**：漏斗存值与复算不符；excluded_by_reason 分布不一致；closure != closed；coverage 汇总不符；duplicate_of 未登记 conflicts。
4. **extraction**：纳入记录缺提取项；缺 study_design/sample/effect 块；块缺 evidence.quote/location；quote 在来源语料与 claims 均无逐字回证；缺值未在 extraction_notes 说明；提取项指向非 included 记录。
5. **quality**：纳入记录缺评价；维度 id/judgment 非法；overall_grade != 量表推导；缺 grade_basis。
6. **synthesis**：strength 非法或 != 规则推导；supporting/conflicting 引用不存在或非 included 记录；缺 strength_basis；gaps/bias_registry/conflict_matrix 缺登记且无 note。
另：steps 为空或无可执行 command、verdict 与判定进度矛盾、缺 output_contract 字段——始终开启。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，标题摘要 DOI 均为虚构，9 条题录 → 5 纳入/2 排除/1 重复合并/1 待复核，3 条结论 strong/weak/insufficient）：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/dedupe.py --result examples/example-result.json --apply --report /tmp/dedupe.json
python3 scripts/quality_audit.py --result examples/example-result.json --out /tmp/quality.json
python3 scripts/extraction_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/extraction.json
python3 scripts/synthesis_check.py --result examples/example-result.json --out /tmp/synthesis.json
python3 scripts/flow_audit.py --result examples/example-result.json --report /tmp/funnel.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 题录清单为空 | records 空、funnel.identified=0、verdict=cannot_verify 或 not_screened，绝不补造文献 |
| 无摘要/缺 DOI | missing_metadata 登记 + 置信度降级；无法判定则 pending（RC-PD-NO-ABSTRACT/METADATA）并登记待复核 |
| 标准互相冲突 | uncertainties.conflicts 登记 + 声明优先序；改协议必须新增版本并回溯重判 |
| 纳入证据互相矛盾 | conflict_matrix 登记 + 按质量等级与强度规则降级结论，不静默取舍 |
| 全文不可得/提取缺值 | extraction_notes 说明 + material_gaps 登记，不脑补效应量 |
| 预印本/重复导出 | doi_exact/title_exact 直接合并（保留 published）；title_similar 升级人工 |
| 算力/时间不足 | 保留已完成部分，status=partial，changelog 注明截断位置 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 已知限制
- 仅处理输入题录快照：不做实时数据库全域召回、不全文精读、不做元分析与统计合并。
- 量表与强度规则是本技能的方法学约定，可按综述替换并声明新版本（resources/*.json）。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量；模型请求数由 Agent 侧回填，缺失保持 null。
