---
name: lit-classify
description: Literature and research-material auto-classification skill (multi-level taxonomy declared upfront / per-item classified with verbatim evidence quotes / multi-label tagging / boundary-case pending registry / same-key-same-class consistency). Builds a subject/type/year multi-level taxonomy before any assignment, classifies every file into a taxonomy node with confidence and a verbatim quote from the source text, attaches multi-dimensional tags, flags boundary cases (multi-domain, missing metadata, duplicates, unreadable) for human review, and mechanically recomputes same-key consistency (same DOI or same normalized title+year must land in the same class unless a merged/escalated conflict is registered). Verify_check re-checks taxonomy membership, quote back-verification against case.json source text, same-key consistency and pending registration; gain_probe runs normal-vs-degraded ablation on the same input and embeds measured gain_evidence plus efficiency counters into result.json. Use when the task asks to organize a mixed research-material folder into a reviewable classification with per-item rationale, duplicates distinguished, and every boundary case registered.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 items / consistency / coverage / pending_review / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全记录覆盖**：资料库**每一条**文件都必须逐条判定（judged=true 或写明 pending_reason），禁止只处理前几条就收尾；缺元数据/扫描件/疑似重复的条目登记 boundary 或 conflicts，不脑补、不跳过。
4. **不编造**：evidence_quote 必须逐字摘自该条目在 case.json 中的原文（标题/摘要/关键词）并附位置；主类目必须来自体系 node_id，不得凭空造类目；对不上就登记，不改证据凑结论。
5. **体系事前声明**：taxonomy（dimensions.nodes 含 node_id/path/keywords + 多标签策略 + 边界策略）必须在**任何分类判定之前**写定（declared_at），之后禁止调整；判定必须引用体系中 node_id，不得事后改体系凑结果。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定混杂的科研资料集合（期刊论文/预印本/会议论文/数据集/扫描件等），完成**多级分类体系构建、逐条归类判定（含置信度）、多标签、依据引用原文、重复与边界情形登记、同键同类一致性校验**。单篇精读、全文翻译、检索发现不在范围；材料缺失、无法判断、运行失败照实分别说明。
关键词：归得对（逐条可回溯原文）· 分得稳（体系事前声明、同键同类）· 讲得清（逐条理由 + 置信度）· 漏得少（边界全登记、重复必处置）。
- 输入：`/input/case.json`（分类目标 + 资料清单 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与资料清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（files/documents/records 等）提取资料清单预填 `result.items[]`（含可用元数据字段）；生成 `/app/work/taxonomy.json` 分类体系模板。
- 脚本失败时手工兜底：读 case.json 抄资料清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 分类目标与多级体系（1 次响应，分类前完成）
- 填 `result.classification_goal`（question/scope/corpus_note）与 `result.taxonomy`：维度按学科主题/文献类型/年份段等组织，每维 `dim_id/name/nodes[]`，节点含 `node_id/path/keywords`（关键词为机械归类线索）；同步写 /app/work/taxonomy.json。**声明后禁止调整。**
- 同时写定 `multi_label_policy`（主类目唯一、类型/年份按元数据多标签）与 `boundary_policy`（multi_domain/missing_fields/duplicate/unreadable 四类边界必须登记）。

### Step 2 — 机械归类与同键分组（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/classify_engine.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work
```
- 按体系关键词对每条原文做命中计数，产出建议路径/命中数/分差/置信度建议（写入 `items[].mechanical`，**仅供采纳或复核，不冒充最终判定**）；按 DOI → 归一化标题+年份 → source_ref 生成 `key_signature` 并分组，回写 `result.consistency.key_groups`。
- 中文按原文子串匹配（不用 isalpha 判字）；脚本失败时手工兜底并在 steps 注明，事后仍须重跑核对。

### Step 3 — 逐条判定（1-2 次响应，广度优先）
对 `result.items[]` 中**每一条**，缺一不可：
- `primary_path` ∈ 体系 node_id（主类目唯一）；`tags[]` 多标签（类型/年份段等维度，均须命中体系 node_id）；
- `confidence` ∈ high/medium/low（机械分差 ≥2 → high，=1 → medium，同分或无命中 → low，可依原文证据上调并说明）；
- `evidence_quote` 逐字摘自该条目原文 + `evidence_location` 注明位置；`rationale` 一句话写明命中哪个节点、依据哪段原文；
- `boundary` ∈ multi_domain/ambiguous/missing_fields/duplicate/unreadable 或 null；重复条目 `conflicts[]` 登记 `{item_ids, kind, resolution: merged|escalated, evidence}`（保留正式版/哈希一致版，绝不删除原文件记录）；escalated 必须同时进 pending_review；
- 元数据缺失照实登记 `material_gaps`，不得补造作者/年份/DOI。

### Step 4 — 待复核登记与证据链（1 次响应）
- `result.pending_review[]`：**每个 judged=false 条目**与**每个边界条目**（multi_domain/ambiguous/missing_fields/unreadable）登记 `{item_id, reason, needed_action}`。
- `result.coverage`：total_items / judged_items / classified / pending / boundary_flagged / multi_label_count / ratio，与实际条目一致。
- **claims 证据链**：每条已归类条目在 `claims[]` 有 `{claim_id, text, kind, source_id=item_id, location, evidence:[{paragraph_id, quote}]}`；text 须含「命中节点 + 原文依据 + 置信度」；**逐字回证**：evidence_quote 必须在 case.json 该条目原文与 claim quote 中出现（空白归一化后子串匹配），未回证列入 unbacked_numbers 判 FAIL。
- 结论分级 `result.verdict`：`classified` 全部逐条判定；`partially_classified` 部分判定；`not_classified` 未产生有效判定；`cannot_verify` 材料缺口导致无法判定且 material_gaps 非空。运行状态 `result.run_status` ∈ success|partial|unable_to_determine|refused，非 success 必须写 reason 与 manual_takeover。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭体系命中 / 引用回证 / 同键同类 / 边界登记），把**真实数字**写进 `result.gain_evidence`：`runs[]`、`delta_normal_minus_degraded`、`mechanism_to_metric_map`、`boundaries`、`failure_conditions`。
- 五项对照指标：体系外路径漏检数 / 引用回证缺失漏检数 / 同键同类漏检数 / 待复核漏登记数 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- 同时写 `result.efficiency`（墙钟、字节、检查项数、条目数、人工条目、追问轮次 + `reproduce` 复现命令）；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- `--inject-pollution` 在**副本**上注入污染（体系外路径 / 依据缺失 / 同键不同判 / 清空待复核 / 清空处置记录）做反例自测：正常模式须抓到（`caught_by_normal_mode=true`），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence` = `{available:false, reason:"…"}` 与 `efficiency` = `{available:false, reason:"…"}`，不得编数字。退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每条文件都有判定或待复核吗？每个归类的依据都能回溯到体系 node_id 与原文逐字引用吗？边界与冲突升级都登记进 pending_review 了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "classification_goal": {"question": "…", "scope": "…", "corpus_note": "…"},
    "taxonomy": {"declared_at": "step1", "dimensions": [{"dim_id": "D1", "name": "学科主题", "nodes": [{"node_id": "T-01", "path": "机器学习/深度学习", "keywords": ["deep learning"]}]}], "multi_label_policy": "…", "boundary_policy": "…"},
    "items": [{"item_id": "F01", "source_ref": "files[0]", "title": "…", "fields": {"year": 2022, "doc_type": "journal_article", "doi": "…"}, "primary_path": "T-01", "tags": ["T-01", "T-10"], "confidence": "high", "rationale": "…", "evidence_quote": "逐字摘录", "evidence_location": "files[0].abstract", "key_signature": "doi:…", "mechanical": {"suggested_path": "T-01", "keyword_hits": 3, "margin": 3, "confidence_suggestion": "high"}, "boundary": null, "pending_reason": null, "judged": true}],
    "consistency": {"key_groups": [{"key": "doi:…", "item_ids": ["F01", "F02"], "suggested_paths": ["T-01"], "same": true, "rule": "doi > 标题+年份 > source_ref"}], "note": "…"},
    "coverage": {"total_items": 8, "judged_items": 7, "classified": 7, "pending": 1, "boundary_flagged": 2, "multi_label_count": 7, "ratio": 0.875},
    "conflicts": [{"item_ids": ["F01", "F02"], "kind": "preprint_vs_published", "resolution": "merged", "evidence": "…"}],
    "pending_review": [{"item_id": "F04", "reason": "…", "needed_action": "…"}],
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "classified | partially_classified | not_classified | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "命中节点+原文依据+置信度", "kind": "reported | inferred", "source_id": "F01", "location": "items[0]", "evidence": [{"paragraph_id": "files[0].abstract", "quote": "原文原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. confidence / boundary / run_status.state / verdict 枚举非法。
2. taxonomy 未事前声明（declared_at 空或 dimensions.nodes 无 node_id）；primary_path 或 tags 含体系外 node_id（凭空造类目）。
3. 已判定条目 rationale 为空；primary_path 非空但 evidence_quote 缺失、或未在 case.json 该条目原文逐字回证、或 claims 证据链无对应条目 → unbacked_numbers 判 FAIL。
4. 同键条目（key_signature 相同）primary_path 不一致且 conflicts 未登记 merged/escalated；escalated 未进 pending_review。
5. judged=false 或边界条目（multi_domain/ambiguous/missing_fields/unreadable）未登记进 pending_review（缺 reason/needed_action）。
6. coverage 汇总与实际条目不符；verdict 与判定进度矛盾；steps 为空或无可执行 command。
7. 闸门（case_contract / taxonomy_ledger / consistency_recompute / classification_output）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，标题摘要 DOI 均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/classify_engine.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --taxonomy /tmp/wk/taxonomy.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 资料清单为空 | items 空、coverage.total=0、verdict=cannot_verify 或 not_classified，status 写明，绝不补造文件 |
| 扫描件无文本层 / 加密 PDF / 乱码 | boundary=unreadable 或 missing_fields + pending_review 登记 needed_action（OCR/人工录入），不脑补元数据 |
| 跨主题/多标签模糊 | 主类目暂取分差较大者并降置信度，boundary=multi_domain + 待复核登记 |
| 同名不同版本/重复下载 | key_signature 同键 + conflicts 登记 merged（保留正式版）或 escalated；绝不静默覆盖或删除 |
| 分类标准冲突或体系不完备 | uncertainties.conflicts 登记双方 + 声明采用口径；体系不得事后增删节点凑结果 |
| 大批量超预算 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅处理输入清单内资料：不做实时检索、不全文精读、不做单篇深度解读。
- 机械归类关键词命中是建议值（items[].mechanical），最终判定须由 Agent 引用原文证据复核；建议与最终不一致时以 rationale 说明为准。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
