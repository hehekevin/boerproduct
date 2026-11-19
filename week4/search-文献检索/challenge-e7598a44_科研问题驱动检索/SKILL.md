---
name: quest-search
description: Research-question-driven literature search skill (question decomposition, query planning, term expansion, relevance screening, gap registration). Decomposes a research question into retrievable subquestions with dimensions, builds an ordered query plan with dependencies and term expansions, declares stop criteria BEFORE searching, screens every candidate with traceable source and explicit relevance basis, registers gaps (no_result/conflict/metadata_missing/permission), and emits reproducible steps. Bundled validators mechanically check subquestion coverage, relevance evidence and gap registration; a normal-vs-degraded ablation probe embeds real measured gain_evidence and efficiency counters into result.json. Use when the task asks to plan searches for a complex research question, screen literature against subquestions, and keep the screening basis auditable.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 subquestions / query_plan / search_rounds / candidates / gaps / stop_criteria / steps / reproducibility / run_status / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **广度优先**：先覆盖全部子问题与全部候选（每步一个写盘动作），再做深挖；禁止在单一子问题上耗尽预算导致其余项空白。
4. **不编造**：相关性依据逐字摘自案例材料并附位置；未命中的检索照实登记，不补造文献、不虚构元数据；材料里没有的就是没有，登记进 gaps 或 material_gaps。
5. **停止条件事前声明**：`stop_criteria.declared_before` 必须在**任何检索之前**写定（并同步 /app/work/stop_criteria.json），事后不得放宽；停止时对照事前规则写 stop_reason。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增检索，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定科研问题与案例内文献记录集（fixture 快照，无联网数据库），完成「问题拆解 → 查询规划 → 执行检索 → 相关性判定 → 缺口登记」的结构化可复跑流程。单篇精读、全文翻译、开放式科研问答不在范围；缺什么登记什么，不脑补。
关键词：拆得开（子问题可检索）· 查得顺（依赖与顺序有理）· 判得有据（相关性逐条给依据）· 讲得清（过程可复现）。
- 输入：`/input/case.json`（科研问题 + 文献记录集 + output_contract）与 `task.md`。**以实际文件为准，不依据标签假设内容；正式案例可能含合成重复/冲突记录，按输入事实处理并如实标注。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- **脚本定位**：一律用固定路径 `/skills/weekly-skill/scripts/<脚本名>`；使用前先确认标志文件 `/skills/weekly-skill/scripts/.package-marker.json` 存在且 `package=quest-search`（或跑 `python3 /skills/weekly-skill/scripts/verify_check.py --selftest`）。**禁止 `find | head -1` 式定位（会串包）。**
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与材料清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；扫描 /input 与 case 内嵌记录集建材料清单；生成 `/app/work/stop_criteria.json` 停止条件声明模板。
- 脚本失败时手工兜底：读 case.json 抄 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 问题拆解与查询规划（1 次响应）
- `result.research_question`：把问题填进 object / mechanism / method / time_range / comparison / evidence_requirements 六维 + `scope`（检索范围）；材料未给明的维度填 unknown 并登记 uncertainties。
- `result.subquestions[]`：每行 `{subq_id, text, dimension, query_ids, status}`——子问题必须**可检索**（能落成查询式），覆盖机制、方法、时间范围、比较关系、证据要求等维度。
- `result.query_plan[]`：每行 `{query_id, subq_id, phase, depends_on, query_string, term_expansions, rationale}`——为子问题安排检索顺序与依赖（前置/并行）；每条查询做同义词/缩写/上下位术语扩展，控制发散。
- **停止条件事前声明**：写 `result.stop_criteria` 与 `/app/work/stop_criteria.json`：`{declared_before, applied, stop_reason, marginal_rule, rationale}`。**必须在检索前完成。**

### Step 2 — 执行检索与多轮记录（1-2 次响应）
在案例记录集（fixture）上按 query_plan 逐条执行：
- `result.search_rounds[]`：每轮 `{round, queries_executed, findings, adjustment}`——上轮结果如何调整下轮查询（补缺口、验证冲突）。
- 命中数、轮次等计数照实记录；无结果的查询照实登记（gaps kind=no_result），不重试凑数。

### Step 3 — 候选筛选与相关性判定（1-2 次响应）
`result.candidates[]` 每行：`{candidate_id, title, source, location, metadata, subq_ids, relevance_score, relevance_basis, included, exclusion_reason}`：
- `source`/`location` 指到案例材料具体位置（可追溯）；`relevance_basis` 逐字摘录材料原句 + 说明与哪个子问题相关；`included=false` 必须写 `exclusion_reason`。
- `result.gaps[]`：每行 `{gap_id, subq_id, kind, description, follow_up}`，`kind` ∈ `no_result | conflict | metadata_missing | permission | other`——无结果、证据冲突、元数据缺失、权限不足逐条登记，不默默跳过。
- 汇总 `result.reproducibility` = `{total_subquestions, query_covered, evidence_covered, uncovered, ratio}`（covered=有查询且有候选关联或缺口登记）。

### Step 4 — claims 证据链与结论（1 次响应）
**每个 relevance_score 数字在 claims[] 中有一条对应条目**：`{claim_id, text, kind, source_id, location, evidence:[{paragraph_id, quote}]}`，quote 是材料原文逐字摘录；评分数字必须出现在 claim text 里（空白归一化子串匹配，未回证列入 `unbacked_numbers` 并判 FAIL）。
- 结论分级 `result.verdict`（`verdict_basis` 一句话写依据）：`search_completed` 全部子问题 covered；`partial_coverage` 部分子问题缺证据（basis 写明缺哪些）；`cannot_verify` 材料缺口导致无法检索且 material_gaps/gaps 非空；`refused` 输入不可用。
- 运行状态 `result.run_status` = `{state, reason, manual_takeover[]}`，`state` ∈ `success|partial|unable_to_determine|refused`；非 success 必须写 reason 与人工接管位置。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（子问题覆盖 + 相关性判定 + 缺口登记校验全开）与退化模式（--ablate all 关闭三类校验），把**真实数字**写进 `result.gain_evidence`：`runs[]`、`delta_normal_minus_degraded`、`mechanism_to_metric_map`（机制→指标映射）、`boundaries`、`failure_conditions`。
- 五项对照指标：子问题覆盖机器判定占比 / 相关性依据缺失漏检数 / 需人工核对条目数 / 步骤数 / 追问轮次。数字全部来自实跑，**不得手填或臆造**。
- 同时写 `result.efficiency`：自动计数（墙钟、字节、检查项数）+ `reproduce` 复现命令；`model_requests` 由 Agent 按实际请求数回填，缺失保持 null。
- `--inject-pollution` 在**副本**上注入污染做反例自测：正常模式须抓到污染项（`caught_by_normal_mode=true`），原 result.json 不被改动。
- 脚本跑不了时：**手工**写 `gain_evidence`/`efficiency` = `{available:false, reason:"…"}`，不得编数字。退化模式结果**仅用于增益对照**，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- 两个脚本退出码恒为 0；**判据是报告 `verdict`**：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency）→ 重跑，直到 PASS（或确认无法修复并如实记录）。
- verify_check 通过后把每条检查的三元组 `{item, template_value, applied, match}`、闸门状态与 unbacked 清单回写进 result.json（键 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`），保留勿删。
- 自查三问：每个子问题都有查询覆盖或缺口登记吗？每条候选都有可追溯来源与相关性依据吗？停止理由对照的是事前声明吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "research_question": {"object": "…", "mechanism": "…", "method": "…", "time_range": "…", "comparison": "…", "evidence_requirements": "…", "scope": "…"},
    "subquestions": [{"subq_id": "sq1", "text": "…", "dimension": "mechanism", "query_ids": ["q1"], "status": "covered"}],
    "query_plan": [{"query_id": "q1", "subq_id": "sq1", "phase": 1, "depends_on": [], "query_string": "…", "term_expansions": ["…"], "rationale": "…"}],
    "search_rounds": [{"round": 1, "queries_executed": 3, "findings": "…", "adjustment": "…"}],
    "candidates": [{"candidate_id": "R1", "title": "…", "source": "records[0]", "location": "records[0].abstract_excerpt", "metadata": {"year": 2019}, "subq_ids": ["sq1"], "relevance_score": 0.92, "relevance_basis": "摘要逐字：…", "included": true, "exclusion_reason": null}],
    "gaps": [{"gap_id": "g1", "subq_id": "sq3", "kind": "conflict", "description": "…", "follow_up": "…"}],
    "stop_criteria": {"declared_before": "step1", "applied": true, "stop_reason": "…", "marginal_rule": "…", "rationale": "…"},
    "steps": [{"step": "step1", "action": "…", "command": "python3 …", "output_ref": "result.subquestions", "status": "done"}],
    "reproducibility": {"total_subquestions": 3, "query_covered": 3, "evidence_covered": 3, "uncovered": 0, "ratio": 1.0},
    "run_status": {"state": "success", "reason": "…", "manual_takeover": []},
    "verdict": "search_completed | partial_coverage | cannot_verify | refused", "verdict_basis": "分级依据一句话",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …/gain_probe.py …"}
  },
  "claims": [{"claim_id": "k1", "text": "材料摘录+评分+依据说明", "kind": "reported | inferred", "source_id": "R1", "location": "candidates[0]", "evidence": [{"paragraph_id": "records[0]", "quote": "材料原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "result_readable", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. gap kind / verdict / run_status.state 枚举非法；status 非约定枚举只 warn。
2. 子问题未挂到 query_plan 中存在的 query_id（query_coverage）；reproducibility 计数与实际覆盖不一致。
3. query_plan 的 query_string 空、依赖指向不存在的 query_id；全部查询无术语扩展只 warn。
4. 候选缺 source/location（不可追溯）、缺关联子问题、缺 relevance_basis；included=false 无 exclusion_reason。
5. relevance_score 数字无 claim text 回证 → unbacked 计入 FAIL；有数字但 claims 为空。
6. stop_criteria 无事前声明 declared_before 或无实质规则；steps 为空或全无 command。
7. verdict=search_completed 但 uncovered>0；verdict=cannot_verify 但 material_gaps 与 gaps 均空。
8. environment 缺 python_version；gain_evidence/efficiency 缺失或 available=false 无 reason。闸门非 enforced 时 warn「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式案例答案**），可本地自测整条链路：
```bash
python3 scripts/verify_check.py --selftest
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
cp examples/example-result.json /tmp/demo.json && python3 scripts/gain_probe.py --result /tmp/demo.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 记录集/材料不可访问 | 登记 material_gaps，verdict=cannot_verify，绝不编造候选 |
| 某查询无结果 | gaps kind=no_result 登记 + follow_up，不重试凑数 |
| 证据互相冲突 | gaps kind=conflict 双方摘录并注明，登记 human_review |
| 元数据缺失/权限不足 | gaps kind=metadata_missing / permission，included 按现有证据判定并写明 |
| 术语严重歧义 | 在 term_expansions 与 uncertainties 登记歧义项，查询串用上位概念兜底 |
| 预算不足 | 保留已覆盖子问题，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅在案例提供的记录集（finite snapshot）上检索：不联网、不访问外部数据库、不装 pip 依赖（stdlib-only）；不宣称全域召回。
- 合成重复/冲突记录是输入 fixture，不是期望答案；按输入事实筛查并如实标注。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- relevance_score 是本技能基于材料原文的判定分数，非人工标注金标准；冲突时登记 human_review。
