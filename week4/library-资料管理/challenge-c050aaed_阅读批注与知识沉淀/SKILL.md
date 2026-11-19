---
name: read-note-harvest
description: Reading annotation and knowledge sedimentation skill (annotation extraction / position back-evidence / type-vocabulary consistency / three-element knowledge cards / theme induction / to-verify registry / retrieval entry). Declares a four-type annotation vocabulary (question/supplement/challenge/association) BEFORE any annotation is judged, then judges every annotation with a verbatim source quote plus page/section locator, back-checks each quote through a claims evidence chain, sediments annotations into knowledge cards with all three elements (point/evidence/source, card quotes must derive verbatim from cited annotations), induces cross-annotation themes grounded in >=2 existing annotations with explicit basis, registers every needs_verify item into a to_verify registry, builds a deterministic retrieval index with ASCII-word/CJK-bigram tokenization (no isalpha trap), and embeds measured normal-vs-degraded gain_evidence plus efficiency counters into result.json. Verify_check mechanically re-checks location back-evidence, type drift, card completeness, theme grounding and to_verify registration; gain_probe runs the same validator twice (normal vs ablated) on the same input and injects pollution into a copy to prove detection gain. Use when the task asks to turn scattered reading annotations into traceable, searchable, reviewable knowledge.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 annotations / cards / themes / to_verify / annotation_vocab / coverage / retrieval / theme_stats / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全记录覆盖**：输入材料中**每一条**批注都必须逐条判定（judged=true 或写明材料缺口），禁止只处理前几条就收尾；缺定位/疑似重复/OCR 可疑的条目登记 missing_metadata 或 conflicts，不脑补、不跳过。
4. **不编造**：quote 必须逐字摘自该批注实际指向的原文并附位置；卡片摘录必须逐字来自所引批注；对不上就登记，不改证据凑结论。
5. **口径事前声明**：annotation_vocab 四类型（question/supplement/challenge/association）必须在**任何批注判定之前**写定（declared_at），之后禁止调整；ann_type 必须命中口径，不得事后改口径凑结果。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定科研材料与其上的散落批注（高亮/划线/页边/手写/剪藏），完成**逐条批注定位与回证、四类型标注、知识卡片三要素沉淀、跨批注主题归纳、待查证登记、检索入口**。PDF 解析库接入、全文精读判断、文献检索、目录治理与长期归档不在范围；材料缺失、OCR 不可信、重复下载照实登记，不补造内容。
关键词：定得准（locator+quote 逐字回证）· 分得清（四类型口径事前声明）· 沉得住（卡片三要素一个不缺）· 连得稳（归纳有依据、控制过度连接）· 查得到（检索入口+召回不足处置）。
- 输入：`/input/case.json`（材料 + 批注线索 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与批注清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（annotations/notes/highlights/materials 等）提取批注与材料清单预填 `result.annotations[]`；扫描输入目录逐文件记 sha256；生成 `/app/work/type_vocab.json` 类型口径模板。
- 脚本失败时手工兜底：读 case.json 抄清单与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 材料盘点与类型口径声明（1 次响应，判定前完成）
- 填 `result.source_materials`（逐材料 sha256/kind/version_of）与 `result.research_question`。
- **事前声明 `result.annotation_vocab`**：四类型逐条给 type_id + 定义 + 判定规则，declared_at 必填，同步写 /app/work/type_vocab.json。**声明后禁止调整。**重复下载/多版本材料在 source_materials.version_of 登记。

### Step 2 — 逐条批注判定（1-2 次响应，广度优先）
对 `result.annotations[]` 中**每一条**批注，缺一不可：
- `locator`（页/节/段，须与实际材料一致）+ `anchor_kind` ∈ highlight/underline/margin/handwritten/webclip/ocr/text_selection/unknown；
- `ann_type` 必须命中 Step 1 口径；`confidence` ∈ high/medium/low；
- `quote` 逐字摘自原文 + `quote_location`；并在 `claims[]` 建证据链 `{source_id=ann_id, evidence:[{paragraph_id, quote}]}`——**quote 必须在 claims 中逐字回证，无回证判 FAIL**；
- 疑点未决 `needs_verify=true`；重复下载/版本串味 `duplicate_of` 指向保留条目，并在 `result.conflicts[]` 登记 merged（保留正式版本）或 escalated（进 to_verify）；`missing_metadata[]` 登记缺失项。

### Step 3 — 检索索引与主题统计（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/index_search.py --result /app/output/result.json --query "<材料核心术语>"
```
- 机械生成 `result.retrieval`（卡片+已判定批注的确定性索引，ASCII 词 + CJK 二元组切词，**不用 isalpha 避开汉字陷阱**；命中 0 条时 low_recall_note 给出召回不足处置）与 `result.theme_stats`（每主题批注数/类型分布/卡片数）。同输入重复运行逐位一致。
- 脚本失败时手工兜底：按同一规则手写索引并在 steps 注明，事后重跑脚本核对。

### Step 4 — 卡片沉淀、主题归纳与待查证登记（1 次响应）
- `result.cards[]`：**每张卡片三要素一个不缺**——point（要点）/ evidence（引用批注 ann_id + 摘录，摘录须逐字来自所引批注的 quote）/ source（原文定位）；theme_ids 关联主题。
- `result.themes[]`：member_anns ≥2 且全部真实存在，basis 写明归纳依据（禁止单词重合即连接）；每个 needs_verify=true 的批注逐条登记 `result.to_verify[]`（含 question + needed_action）。
- `result.coverage`：total_annotations / extracted / judged / by_type / cards_total / themes_total / to_verify_total / ratio，与实际条目一致。
- `result.verdict`（verdict_basis 一句话）：`extracted` 全部判定且回证齐备；`partially_extracted` 部分判定；`not_extracted` 未产生有效判定；`cannot_verify` 材料缺口导致无法判定且 material_gaps 非空。
- `result.run_status` = `{state, reason, manual_takeover[]}`，state ∈ success|partial|unable_to_determine|refused；非 success 必须写 reason。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（五组机械校验全开）与退化模式（--ablate all：关闭位置回证/类型口径/卡片三要素/归纳依据/待查证登记），把**真实数字**写进 `result.gain_evidence`：`runs[]`、`delta_normal_minus_degraded`、`mechanism_to_metric_map`、`boundaries`、`failure_conditions`。
- 六项对照指标：位置回证漏检数 / 类型漂移漏检数 / 三要素缺失漏检数 / 归纳无依据漏检数 / 待查证漏登记数 / 需人工核对条目数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**。
- `--inject-pollution` 在**副本**上注入污染（清空 locator/quote + 越界类型 + 清空卡片 source/证据改指向幽灵批注 + 清空归纳 + 清空 to_verify + 清空 claims）做反例自测：正常模式须抓到（`caught_by_normal_mode=true`），原 result.json 不被改动。
- 脚本跑不了时**手工**写 `gain_evidence` = `{available:false, reason:"…"}` 与 `efficiency` 同理，不得编数字。
- 退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每条批注都能回到原文的页与位置吗？每张卡片的论断都指得到支撑它的批注与原文片段吗？疑点与重复文件都登记了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"question": "…", "scope": "…", "time_range": null},
    "source_materials": [{"material_id": "M01", "source_ref": "materials[0]", "title": "…", "sha256": "…", "kind": "pdf|text_excerpt|…", "version_of": null, "access_note": null}],
    "input_files": [{"path": "…", "sha256": "…"}],
    "annotation_vocab": {"types": [{"type_id": "question", "label": "疑问", "definition": "…", "rule": "…"}], "declared_at": "step1", "note": "…"},
    "annotations": [{"ann_id": "A01", "source_ref": "materials[0]", "locator": "p.2 §3 para1", "anchor_kind": "highlight", "ann_type": "question", "quote": "逐字摘录", "quote_location": "materials[0].excerpts[0]", "note_text": "…", "confidence": "medium", "duplicate_of": null, "missing_metadata": [], "needs_verify": true, "judged": true}],
    "cards": [{"card_id": "C01", "point": "要点", "evidence": [{"ann_id": "A01", "quote": "逐字来自所引批注"}], "source": "原文定位", "theme_ids": ["T01"]}],
    "themes": [{"theme_id": "T01", "label": "…", "basis": "归纳依据", "member_anns": ["A01", "A02"], "member_cards": ["C01"]}],
    "to_verify": [{"item_id": "V01", "question": "…", "related_anns": ["A01"], "needed_action": "…", "status": "open"}],
    "coverage": {"total_annotations": 5, "extracted": 5, "judged": 5, "by_type": {"question": 1}, "cards_total": 2, "themes_total": 2, "to_verify_total": 2, "ratio": 1.0},
    "conflicts": [{"item_ids": ["A04", "A05"], "kind": "duplicate_download", "resolution": "merged", "evidence": "…"}],
    "retrieval": {"index_size": 7, "entries": [], "tokenize_note": "…", "recall_policy": "…", "query_demo": {"query": "…", "hits_total": 1, "top_k": [], "k_value": 5, "low_recall_note": null}},
    "theme_stats": [{"theme_id": "T01", "label": "…", "ann_count": 2, "type_distribution": {}, "card_count": 1}],
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "extracted | partially_extracted | not_extracted | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "…", "kind": "reported | inferred", "source_id": "A01", "location": "result.annotations[0]", "evidence": [{"paragraph_id": "materials[0].excerpts[0]", "quote": "原文逐字摘录"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. confidence / anchor_kind / run_status.state 枚举非法。
2. 已判定批注 locator 为空；quote 在 claims 无逐字回证（位置不可回证）。
3. ann_type 不在事前声明口径内；vocab 未声明或 declared_at 为空（类型口径漂移）。
4. 卡片三要素缺一；卡片 evidence 引用不存在的批注；卡片摘录与所引批注 quote 不符（脱离原文）。
5. 主题 member_anns <2 或含不存在批注或 basis 为空（归纳无依据/过度连接）。
6. needs_verify=true 未登记 to_verify（缺 question/needed_action）；duplicate_of 未在 conflicts 登记。
7. coverage 汇总与实际条目不符；verdict 与判定进度矛盾；steps 为空或无可执行 command。
8. 闸门（case_contract / vocab_ledger）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，材料与批注均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/index_search.py --result examples/example-result.json --query "memory" --k 3 --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --vocab /tmp/wk/type_vocab.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 材料目录为空 / 无批注线索 | annotations 空、coverage.total=0、verdict=cannot_verify 或 not_extracted，绝不补造内容 |
| OCR 置信度低 / 无文本层扫描件 | anchor_kind=ocr + missing_metadata 登记 + 置信度降级；无法定位则 needs_verify 登记 |
| 重复下载 / 多版本批注分裂 | duplicate_of + conflicts 登记 merged（保留正式版本）；无法确认同一性则 escalated 进 to_verify |
| 批注类型难判 | 按 vocab 判定规则就近归类并在 note_text 注明依据；确实无法归类则 confidence=low 并 needs_verify |
| 加密或损坏文件 | 登记 material_gaps，status 如实降级，不假装已读取 |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅处理输入材料内的批注：不做 PDF 解析库接入、不全文精读、不文献检索、不目录治理。
- 四类型口径与切词规则是本技能设定并事前声明，不冒充外部标准；扫描件坐标校正依赖平台 ocr-tool，本技能只登记不修正。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
