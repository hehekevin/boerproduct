---
name: kbqa-cite
description: Research knowledge-base QA skill (multi-file retrieval / sentence-level source citation / miss registration / question decomposition). Inventories KB entries (FAQ/doc/note/files) with a content ledger, mechanically decomposes every case question into subquestions, runs a deterministic CJK-bigram+token retrieval probe over entries, then answers each subquestion sentence-by-sentence where every answer sentence carries a source entry id, a verbatim quote and a quote location that verify_check back-checks against the entry text ledger and the claims evidence chain (including number back-backing). Questions with no basis in the KB are honestly answered as insufficient (status=miss) with miss_reason and a gap list (missing_topic/needed_action); partial answers must declare gaps. verify_check also enforces decomposition coverage, coverage-count consistency, miss registration, no-source-sentence detection and verdict consistency, all exit-0. gain_probe runs normal-vs-degraded ablation on the same input and a pollution-injection self-test to embed measured gain_evidence and efficiency into result.json. Use when the task asks to answer questions over a research knowledge base with per-sentence traceable citations and honest insufficiency reporting.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 knowledge_base / questions / answers / gaps / retrieval / coverage / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **全问题覆盖**：case.json 里**每一个**问题都必须拆解并逐子问题作答（status=answered/partial/miss 三选一），禁止只答前几个就收尾；条目不可读、字段缺失登记 material_gaps 或 missing_metadata，不脑补、不跳过。
4. **不编造**：每条答案句的 quote 必须逐字摘自 source_entry 指向条目的实际正文并附 quote_location；检索未命中就照实标 miss 并登记缺口，不改证据凑结论；知识库没有依据就敢说"没有"并说明缺什么。
5. **句句带来源**：answered/partial 的每个答案句都必须有 source_entry（真实存在的条目 id）+ 非空 quote + quote_location，并在 claims 证据链中逐字回证；无来源句一律不许出现在答案里。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增子问题作答，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定科研知识库条目集（FAQ/文档/笔记/文件，可能含重复副本与历史版本）与一组问题，完成**问题拆解、机械检索、逐问逐句带来源作答、未命中登记与缺口清单**。底层数据库搭建、全文翻译、跨库实时检索不在范围；文件不可读、目录为空、版本冲突、证据互相矛盾照实登记，不补造资料。
关键词：答得准（句句可回链）· 拆得全（逐问拆解不漏答）· 缺得诚实（未命中如实说不足并给缺口清单）· 复核得了（他人可按引用回原文核对）。
- 输入：`/input/case.json`（知识库条目 + 问题 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容；先读实际条目再作答。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- **键归属（多脚本禁写同一键）**：build_skeleton 写骨架与 /app/work/entries.json 台账；kb_index 只写 /app/work/retrieval.json（不碰 result.json）；verify_check 只写 self_check / gates / unbacked_numbers / validator_verdict；gain_probe 只写 result.gain_evidence / result.efficiency；业务键（questions/answers/gaps 等）归 Agent。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与知识库盘点（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；从 case.json 常见键（kb_entries/entries/documents/notes/faqs/files 等）提取知识库条目预填 `result.knowledge_base.entries`；提取问题清单预填 `result.questions`；扫描输入目录，把**每个可读条目正文**写进 `/app/work/entries.json` 内容台账（后续引用回证的真值来源）。
- 脚本失败时手工兜底：读 case.json 抄条目清单、问题清单与 output_contract 字段名，手写骨架（键一个不缺），条目正文手工抄入台账。

### Step 1 — 问题拆解与作答口径（1 次响应，检索前完成）
- `result.questions[]`：每个 case 问题拆成 1-N 个原子子问题（sub_id=Q1-1…），`decomposed=true`；事实性问题与比较性问题分开拆，不得合并作答。
- 口径声明：引用粒度=句子级；每句一来源；多来源分句陈述；confidence ∈ high/medium/low 按证据直接程度定。**拆解后禁止再改 sub_id 口径。**

### Step 2 — 机械检索（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/kb_index.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work
```
- 对每个子问题在条目上做确定性词面重叠打分（中文 2-gram + 英文/数字词，idf 加权），产出 `/app/work/retrieval.json`：top-k 候选条目与分数、top1 低于阈值记 miss_candidate。
- **词面命中≠语义相关**：候选条目必须逐条读原文核对；miss_candidate 必须人工核实，不得静默忽略。脚本失败时手工按关键词逐条目检索并在 steps 注明。

### Step 3 — 逐问逐句作答（2-4 次响应，广度优先）
对 `result.answers[]` 中**每个子问题**，缺一不可：
- `status` ∈ answered/partial/miss；answered/partial 的每条 `sentences[]` = `{sentence_id, text, source_entry, quote, quote_location, confidence}`：
  - `quote` **逐字**摘自 source_entry 条目正文（verify_check 对照 entries.json 台账做空白归一化子串匹配，对不上即 FAIL）；`quote_location` 写明位置（条目/段落/FAQ 问号/字段）。
  - 句中数字（≥2 位或小数）必须能在来源条目正文中找到（unbacked_numbers 机制）。
  - 推断性表述标 kind=inferred 的 claim 并注明推断依据；不得把推断写成原文。
- **版本与重复**：引用当前参数用现行版本条目；历史版本只用于差异说明；同主题多副本在 `knowledge_base.duplicates` 或 `conflicts[]` 登记并声明以哪份为准。
- **证据冲突**：两个条目对同一事实说法不一 → `conflicts[]` 登记 {entries, kind: evidence_conflict, resolution: recorded|escalated, evidence}，答案句注明分歧，escalated 进 uncertainties.human_review。
- `claims[]`：每条答案句对应一条 claim `{claim_id, text(=句子原文), kind, source_id, location, evidence:[{paragraph_id, quote}]}`——这是机检回证的通道，漏一条即 FAIL。

### Step 4 — 未命中登记与缺口清单（1 次响应）
- `status=miss` 的子问题：答案里**如实说"知识库没有依据"**，写 `miss_reason`（检索了什么、为何判定无依据），并登记 `result.gaps[]` = `{sub_id, missing_topic, needed_action, kind}`（kind ∈ no_hit/insufficient_evidence/unreadable/conflict/permission/empty_kb/other）。
- `status=partial`：至少 1 个带来源句子 + 显式声明缺口（gaps 或 miss_reason），**不把未完成写成完成**。
- `result.coverage`：total_questions/decomposed/total_subquestions/answered/partial/miss/uncovered_subquestions/ratio(=answered/total_subquestions)，与实际条目一致。
- 结论分级 `result.verdict`（verdict_basis 一句话写依据）：`answered` 全部子问题已答且无 miss；`partially_answered` 有 answered 且存在 miss/partial；`not_answered` 全部 miss 或零作答；`cannot_verify` 材料缺口导致无法判定且 material_gaps 非空。
- 运行状态 `result.run_status` = `{state, reason, manual_takeover[]}`，state ∈ success|partial|unable_to_determine|refused；非 success 必须写 reason 与人工接管位置。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（四组机械校验全开）与退化模式（--ablate all：关闭答案句-来源对齐 / 问题拆解覆盖 / 检索未命中登记 / claims 证据链回证），把**真实数字**写进 `result.gain_evidence`：`runs[]`、`delta_normal_minus_degraded`、`mechanism_to_metric_map`、`boundaries`、`failure_conditions`。
- 五项对照指标：对齐违规漏检数 / 覆盖违规漏检数 / 未命中漏登记数 / claims 回证缺失漏检数 / 需人工核对子问题数（另有 steps_count 与追问轮次折算）。数字全部来自实跑，**不得手填或臆造**；干净输入 delta=0 属正常（解释规则随证据落盘），污染副本上的对照差在 pollution_selftest 里。
- `--inject-pollution` 在**副本**上注入污染（无来源句+编造答案 / 清 miss_reason / 清 gaps / 清 claims）做反例自测：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 同时写 `result.efficiency`（墙钟、字节、条目数、人工条目、追问轮次 + `reproduce` 复现命令）；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- 脚本跑不了时**手工**写 `gain_evidence` = `{available:false, reason:"…"}`，不得编数字。退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- **判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency / self_check 等已回写键）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：case 的每个问题都拆解且每个子问题都有答案或缺口登记吗？每条答案句都能回链到具体条目正文的具体位置吗？知识不足的地方敢说"没有"并给缺口清单了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": ["…"], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "knowledge_base": {"entries": [{"entry_id": "E01", "source_ref": "kb_entries[0]", "title": "…", "kind": "doc|faq|note|file|unknown", "version": "", "path": "", "readable": true, "chars": null, "missing_metadata": []}], "total_entries": 5, "duplicates": []},
    "questions": [{"question_id": "Q1", "question": "…", "decomposed": true, "subquestions": [{"sub_id": "Q1-1", "sub_question": "…"}]}],
    "answers": [{"sub_id": "Q1-1", "question_id": "Q1", "sub_question": "…", "status": "answered|partial|miss", "confidence": "high", "sentences": [{"sentence_id": "Q1-1-s1", "text": "答案句", "source_entry": "E01", "quote": "逐字引文", "quote_location": "E01 正文第 1 步", "confidence": "high"}], "miss_reason": null}],
    "gaps": [{"sub_id": "Q3-1", "missing_topic": "…", "needed_action": "…", "kind": "no_hit"}],
    "retrieval": {"queries": 5, "topk": 3, "miss_registered": 1, "index_tool": "scripts/kb_index.py"},
    "coverage": {"total_questions": 3, "decomposed": 3, "total_subquestions": 5, "answered": 4, "partial": 0, "miss": 1, "uncovered_subquestions": 0, "ratio": 0.8},
    "conflicts": [{"entries": ["E01", "E02"], "kind": "version_succession|evidence_conflict", "resolution": "recorded|escalated", "evidence": "…"}],
    "steps": [{"step": "step0", "action": "…", "command": "python3 …", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success", "reason": null, "manual_takeover": []},
    "verdict": "answered | partially_answered | not_answered | cannot_verify", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "答案句原文", "kind": "reported | inferred", "source_id": "E01", "location": "answers[0].sentences[0]", "evidence": [{"paragraph_id": "E01#正文", "quote": "条目原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract|entries_manifest|retrieval_index", "state": "enforced | skipped_not_provided | not_found", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. answers[].status / confidence / verdict / run_status.state 枚举非法。
2. answered/partial 的句子 source_entry 为空（无来源句）、指向不存在的条目、quote 为空、quote 未逐字回证条目正文台账（空白归一化匹配）；answered/partial 零句子。
3. case 问题未出现在 result.questions 或未拆解出子问题；子问题无 answers 条目；coverage 各计数与 ratio 与实际不符。
4. status=miss 缺 miss_reason 或未登记 gaps（须含 missing_topic/needed_action）；status=partial 无句子或未声明缺口。
5. 答案句在 claims 证据链无逐字回证（text 与 quote 双回证）；句中数字未回证条目正文 → unbacked_numbers 判 FAIL。
6. verdict 与作答进度矛盾（answered 却有 miss、not_answered 却有 answered 等）；steps 为空或无可执行 command。
7. 闸门（case_contract / entries_manifest / retrieval_index）非 enforced 时 warn + note「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，条目与问题均为虚构），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/kb_index.py --result /tmp/skel.json --case examples/example-case.json --work-dir /tmp/wk
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 知识库为空 / 条目全不可读 | entries 空、material_gaps 登记、verdict=cannot_verify 或 not_answered，绝不补造条目 |
| 问题在知识库无依据 | status=miss + miss_reason + gaps 登记 missing_topic/needed_action，如实说"没有" |
| 引文对不上 / 怀疑编造 | 以 entries.json 台账为准逐字重抄 quote；对不上就不引用，降级为 miss/partial |
| 条目重复 / 历史版本 | duplicates 或 conflicts 登记并声明以哪份为准；当前参数只引现行版本 |
| 证据互相矛盾 | conflicts 登记双方原文，答案注明分歧；escalated 进 uncertainties.human_review |
| 文件不可读 / 权限受限 | readable=false + missing_metadata，kind 填 unreadable/permission，不猜内容 |
| 算力/时间不足 | 保留已答部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅处理输入知识库内条目：不做外部数据库实时检索、不做全文翻译与语义精读；词面检索是召回策略，语义相关性由 Agent 逐条核对。
- 引用回证依赖 build_skeleton 产出的条目正文台账；台账缺失时回证降级为 claims 链内回证（闸门 entries_manifest 可见），须在交付说明中注明。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
