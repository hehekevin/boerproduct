---
name: cite-trace
description: Citation tracing and related literature discovery skill (bidirectional reference tracing, related-work association, dedup and identity merging, all source-verifiable). Locks one seed paper, declares tracing/association/dedup rules up front, runs backward tracing (seed references to method and data provenance) and forward tracing (citing works to improvements and critiques) layer by layer, discovers parallel works via co-citation, bibliographic coupling, author, dataset or topic signals with a reason and confidence per item, merges preprint/conference/journal variants while keeping merge evidence, registers citation cycles and orphan nodes, and explains seed-to-target citation paths hop by hop. Emits a mechanical self-check plus a real normal-vs-degraded ablation gain probe with efficiency counters into result.json. Use when the task asks to trace citations from a seed paper, find related literature with justified association, merge duplicate paper identities, and keep every citation edge source-verifiable.
---

## 强制执行协议（最高优先级）
以下 8 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **字段一个不缺**：result.json 必须含 output_contract 全部键 + 本文 schema 全部键（含 nodes / traces / related / merges / tracking_coverage / pending_review / declared_rules / gain_evidence / efficiency）；无法产出时保留键、填 unknown 或空数组，原因写入 uncertainties，不得删键、不得编造。
3. **广度优先**：先双向各扫一层覆盖全部直接邻居，再做多层扩展与深挖；禁止在单一方向或单条文献上耗尽预算导致另一方向空白。
4. **不编造**：每条引用边必须有可回指的 source_ref（输入文件具体位置）；标题/年份/DOI 逐字摘录并进 claims 回证；找不到来源的边标 pending=true 并写明缺什么，不补造文献。
5. **规则事前声明**：`declared_rules`（关联置信度阈值 / 剪枝停止判据 / 去重键优先级）必须在**任何追踪之前**写定并同步 /app/work/declared_rules.json，事后不得调整。
6. **预算保护**：模型请求已用超 48 次或运行超 700 秒时，停止新增扩展，用现有中间结果完成 result.json 并收尾（verdict 如实填 partial_coverage）。
7. **自检只判 verdict**：所有校验脚本**退出码恒为 0**，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表——FAIL 就逐条修复后覆盖写 result.json 再重跑，自检不过不交付。
8. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 定位与约定
锁定子场景：给定种子文献与包内/输入目录的引文材料（引用记录、参考文献表、被引列表），完成双向追踪、关联发现、身份合并、路径解释四件事，并把每条结论的来源登记到可复核的程度。普通关键词检索、全文阅读、引文内容理解、未经授权的数据抓取不在范围；缺什么登记什么，不脑补。
关键词：找得到（双向覆盖）· 说得清（每条边可回指）· 并得对（合并有证据）· 查得到（待复核显式登记）。
- 输入：`/input/case.json`（种子 + 引文材料 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 按 Step 0–6 线性推进，禁止分支回环。

## 七步流程

### Step 0 — 自动落骨架与材料清单（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 → 写骨架；定位种子文献预填 `seed`/`nodes`；扫描 /input 建引文材料清单；生成 `/app/work/declared_rules.json` 规则声明模板。
- 脚本失败时手工兜底：读 case.json 抄 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 种子定位与规则事前声明（1 次响应）
- 复核骨架预填的种子（title/year/doi 逐字来自 case.json，不确定就登记）；登记 `nodes[]`：每个出现的文献一行 `{node_id, title, year, doi, roles, source_ref}`，node_id 全局唯一，种子 roles 含 `seed`。
- 事前声明 `declared_rules[]` = `{rule, threshold, basis, declared_at}`，至少 4 条：`related_confidence`（high/medium/low 判据）、`pruning_stop`（扩展层数与截断规则）、`dedup_keys`（去重键优先级）、`direction_coverage`（空方向处置）。**先声明后追踪，禁止事后调规则。**
- 中文标题归一化禁止用 isalpha 类启发式（汉字 isalpha()==True 会误判）；统一走校验器的 norm_title 口径（去空白标点+小写，CJK 原样保留）。

### Step 2 — 双向追踪（1-2 次响应）
构建 `result.traces`，两个方向**都不得留空**：
- `backward[]`：种子引用了谁。每条 `{edge_id, direction:"backward", from_id, to_id, layer, relation, context_clue, source_ref, pending, pending_reason}`；relation 标注语境（method_origin/dataset_origin/prior_work/…）。
- `forward[]`：谁引用了种子。`direction:"forward"`，from_id=施引者；relation 标注 improvement/critique/application/…，区分"用它/改它/质疑它"。
- 多层扩展：layer 递增；逐层按 `pruning_stop` 规则剪枝。数据源无前向记录（新预印本常见）时：forward 留空 + `tracking_coverage.seed_forward_available=false` + material_gaps 登记，**不补造**。
- 每条边必须有 source_ref；拿不准的边 pending=true 写 pending_reason。

### Step 3 — 关联发现、网络与路径（1-2 次响应）
- `related[]`：不直接引用种子的平行工作。每条 `{related_id, node_id, signals, reason, confidence, confidence_basis, edge_ids, source_ref}`；signals ∈ co_citation/bib_coupling/author/dataset/task/topic；**高置信必须有可回指证据**（edge_ids 或 source_ref）。高被引≠高相关，主题相似≠方法相关——reason 写清信号来源。
- `network`：foundational（奠基）/ bridge（桥接）/ recent_hot（近期热点）节点 + `cycles[]`（引用环：nodes≥2 + evidence）+ `orphans[]`（孤立节点：写明 reason）。
- `paths[]`：种子到远端文献的引用链。每条 `{path_id, target_id, reachable, hops(逐跳引用已登记的 edge_id), hop_count, direct, trust, note}`；hops 必须逐跳可回指，区分直接引用与间接可达；只有关联信号无引用链的写 reachable=false。

### Step 4 — 去重合并与显式登记（1 次响应）
- `merges[]`：同一工作的多形态（预印本/会议版/期刊版/增补版）合并。每条 `{merge_id, kept_id, merged_ids, keys(doi/title_norm/authors_sig/year), evidence, conflict}`；**evidence 必须非空**（标题主体一致+作者一致+DOI 版本对等），键冲突时不合并、只登记 pending。
- 同 DOI/同标题归一化后撞车但无合并记录 → 校验器 FAIL；同名不同文（标题同、内容不同）不合并，登记 uncertainties.conflicts。
- `pending_review[]`：所有 pending 条目登记 `{item_id, kind(edge/merge/related/path/node), reason, what_to_check}`；空方向也要登记原因（material_gaps / pending_review / coverage_note 三处之一）。
- 汇总 `tracking_coverage`：各计数**必须等于**对应列表长度（机器复算），另填 backward_layers_max / forward_layers_max / seed_forward_available。

### Step 5 — 增益对照与效率计数（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
```
- 同一份输入跑两遍：正常模式（全部机械校验开）与退化模式（`--ablate reasons|dedup|direction|all`，默认 all），把**真实数字**写进 `result.gain_evidence`：`runs[]`、`delta_normal_minus_degraded`、`mechanism_to_metric_map`、`boundaries`、`failure_conditions`；另写 `result.efficiency`（墙钟/字节数/检查项数/复现命令；model_requests 由 Agent 按实际回填，缺失保持 null）。
- 五项对照指标：来源可回指边占比 / 客观违规漏检数 / 需人工复核条目数 / 步骤数 / 追问轮次。数字全部来自实跑，**不得手填或臆造**。
- `--inject-pollution` 在**副本**上注入 5 类污染做反例自测：正常模式须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
- 脚本跑不了时：**手工**写 `gain_evidence` = `{available:false, reason:"…"}` 与 `efficiency` 同理，不得编数字。退化模式结果仅用于增益对照，不得当作交付自检结论。

### Step 6 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json（保留 gain_evidence / efficiency）→ 重跑，直到 PASS（或确认无法修复并如实记录）。verify_check 回写的 self_check/gates/unbacked/validator_verdict 四键保留勿删。
- 结论分级 `result.verdict`：`complete`（双向覆盖且计数一致）| `partial_coverage`（有空方向或待复核未清）| `insufficient_records`（材料不足）| `cannot_verify`（材料缺口，material_gaps 必须非空）。运行状态 `run_status`：success/partial/unable_to_determine/refused + reason + manual_takeover。
- 自查三问：每条边都有 source_ref 吗？每个高置信关联都有证据吗？空方向和 pending 都登记了吗？

## 输出 schema（result.json — 平台通用契约五字段 + 自检四键 + 增益证据）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": "3.12.x", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "seed": {"seed_id": "S0", "title": "…", "year": 2024, "doi": "…", "identity_keys": [], "variants": [], "source_ref": "case.json:seed"},
    "nodes": [{"node_id": "S0", "title": "…", "year": 2024, "doi": "…", "roles": ["seed"], "source_ref": "…"}],
    "traces": {"backward": [{"edge_id": "be1", "direction": "backward", "from_id": "S0", "to_id": "B1", "layer": 1, "relation": "method_origin", "context_clue": "…", "source_ref": "records.references[0]", "pending": false, "pending_reason": null}],
               "forward": [{"edge_id": "fe1", "direction": "forward", "from_id": "F1", "to_id": "S0", "layer": 1, "relation": "improvement", "source_ref": "…", "pending": false, "pending_reason": null}]},
    "related": [{"related_id": "r1", "node_id": "P1", "signals": ["bib_coupling"], "reason": "…", "confidence": "high", "confidence_basis": "…", "edge_ids": [], "source_ref": "…"}],
    "clusters": [{"cluster_id": "c1", "axis": "method", "members": [], "note": "…"}],
    "network": {"foundational": [], "bridge": [], "recent_hot": [],
                "cycles": [{"cycle_id": "cy1", "nodes": [], "evidence": "…"}],
                "orphans": [{"node_id": "O1", "reason": "…"}]},
    "paths": [{"path_id": "p1", "target_id": "F3", "reachable": true, "hops": ["fe1"], "hop_count": 1, "direct": true, "trust": "direct", "note": "…"}],
    "merges": [{"merge_id": "mg1", "kept_id": "S0", "merged_ids": ["S0x"], "keys": {"doi": "…", "title_norm": "…"}, "evidence": ["…"], "conflict": null, "pending": false, "pending_reason": null}],
    "declared_rules": [{"rule": "related_confidence", "threshold": "…", "basis": "…", "declared_at": "step1"}],
    "tracking_coverage": {"backward_layers_max": 1, "forward_layers_max": 1, "backward_edges": 3, "forward_edges": 5, "related_items": 2, "clusters": 1, "paths": 3, "merges": 2, "cycles_registered": 1, "orphans_registered": 1, "seed_forward_available": true, "coverage_note": "…"},
    "pending_review": [{"item_id": "be2", "kind": "edge", "reason": "…", "what_to_check": "…"}],
    "steps": [{"step": "step2", "action": "…", "command": "…", "output_ref": "…", "status": "done"}],
    "run_status": {"state": "success | partial | unable_to_determine | refused", "reason": "…", "manual_takeover": []},
    "verdict": "complete | partial_coverage | insufficient_records | cannot_verify", "verdict_basis": "一句话依据",
    "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
    "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 2, "reproduce": "python3 …/gain_probe.py …"}
  },
  "claims": [{"claim_id": "k1", "text": "摘录+结论说明", "kind": "reported | inferred", "source_id": "…", "location": "…", "evidence": [{"paragraph_id": "…", "quote": "材料原句逐字摘录"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [], "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "result_readable", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. direction/signal/confidence/verdict/run_status.state/kind 枚举非法；declared_rules 缺 rule/threshold/basis/declared_at。
2. 引用边缺 edge_id（或重复）、缺 source_ref（来源不可回指）、端点未登记 nodes（悬空）；pending 边缺 pending_reason 或未进 pending_review。
3. 关联条目缺 reason/confidence_basis；confidence=high 却无 edge_ids 或 source_ref 证据。
4. merge 缺 evidence 或 keys；kept/merged 未登记；同 DOI / 同标题归一化撞车且无合并记录、也不在 seed.variants 声明 → dedup 冲突 FAIL。
5. tracking_coverage 各计数与列表长度不符；后向/前向为空却未登记原因；path 的 hops 引用不存在的边、hop_count≠len(hops)、direct 与 hop_count==1 矛盾；环缺证据、孤立节点缺 reason。
6. 节点标题/年份在 claims quote 无逐字回证、覆盖计数在 claim text 无回证 → unbacked 计入 FAIL；有可回证内容但 claims 为空 → FAIL。标题回证用 norm_title 口径（CJK 保留，不踩 isalpha 陷阱）。
7. environment 缺 python_version；steps 为空或全无 command。闸门状态非 enforced 时 warn「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**），可本地自测整条链路：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```
（verify_check/gain_probe 会把自检三元组与增益证据回写进 --result 指向的文件，对示意文件属预期更新；键所有权：self_check 等四键归 verify_check，gain_evidence/efficiency 归 gain_probe，互不重叠。）

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 数据源无前向引用记录（新预印本） | forward 留空 + seed_forward_available=false + material_gaps 登记，verdict=partial_coverage |
| 种子未在材料中明示 | 按题面任务描述定位，登记 uncertainties.conflicts 与定位依据，不猜 |
| 同名不同文 / 同文不同名 | 去重键冲突不合并：同名不同文登记 conflicts；同文不同名走 merges 留证据 |
| 引用环 / 孤立节点 | network.cycles（nodes≥2+evidence）/ network.orphans（reason）显式登记 |
| 缺 DOI / 元数据冲突 | 边标 pending=true 写 pending_reason，进 pending_review 给 what_to_check |
| 算力/时间不足 | 按 pruning_stop 收尾，verdict=partial_coverage，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 8 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅追踪输入材料内的引用关系：不调外部引文接口、不抓未经授权数据、不装 pip 依赖（stdlib-only）；材料没给的引用边一律登记缺口，不联网补。
- 关联发现受材料覆盖度限制：共被引/耦合信号只能在已有引用图上计算；无前向记录的种子不冒充前向覆盖。
- 增益对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 追问轮次是按约定批量（每轮 3 条）折算的估计量，原始计数 manual_review_items 一并落盘可重算。
