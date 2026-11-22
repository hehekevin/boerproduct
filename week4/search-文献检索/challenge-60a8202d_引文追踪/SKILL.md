---
name: cite-trace
description: Single-direction citation tracing skill. From one seed paper, run 1-2 layers of backward tracing (seed references -> method/dataset provenance) and forward tracing (citing works -> improvements/critiques/applications), keep at most 5 most-relevant papers per layer with direction, layer and a one-sentence link rationale per item, then stop. Every traced paper carries a source_ref back to the input material. Emits result.json with case_id, all output_contract fields, seed, trace_results, trace_summary, verdict and run_status; a mechanical verify_check returns exit code 0 and reports PASS/FAIL in verdict. Use when the task asks to trace citations forward/backward from a seed paper and keep the screening rationale for every result.
---

## 强制执行协议（最高优先级，4 条铁纪律）
1. **第 0 步先落骨架**：读完 /input/case.json 与 task.md 后，第一个动作是运行 `build_skeleton.py` 在 /app/output/result.json 写入骨架；此后 result.json 任何时刻都必须存在且可解析。
2. **失败也要交付**：中断/失败时仍写 result.json（status=partial，写明中断点与已完成部分），绝不让 /app/output 缺 result.json。
3. **退出码恒 0 看 verdict**：所有校验脚本退出码恒为 0，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems`，FAIL 就逐条修复后覆盖写再重跑。
4. **预算过半即定稿**：模型请求已用 ≥32 次或运行 ≥450 秒时，停止新增扩展，用现有结果收尾（verdict 如实填），增益层直接 `gain_evidence.available=false`。

## 定位与约定
锁定子场景：**只做种子论文的前向/后向追踪**。沿种子参考文献（后向 backward）找方法与数据出处，沿施引文献（前向 forward）找后续改进与批评，处理层级扩展与停止判断。本 Skill **不做**关联文献发现、引用网络、路径解释、去重合并四件事。
关键词：找得到（双向覆盖）· 说得清（每条可回指 source_ref）· 停得住（2 层、每层 ≤5 篇）。
- 输入：`/input/case.json`（种子 + 引文材料 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒；只用标准库，不装 pip 依赖。
- 脚本定位以 `/app/work/skill_marker.json` 标志文件为准（Step 0 落盘）。

## 五步流程

### Step 0 — 自动落骨架（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
自动提取 case_id、output_contract 全字段、种子文献信息、扫描 /input 建材料清单，写骨架与 `skill_marker.json`。脚本失败则手工兜底：读 case.json 抄字段名手写骨架。

### Step 1 — 种子定位与停止规则声明（1 次响应）
- 复核 `result.seed`（seed_id/title/year/doi 逐字来自 case.json，source_ref 写定位来源）。
- 事前声明停止规则并写入 `result.trace_summary.stop_rule`：**只做 1–2 层，每层按相关性选最重要的 3–5 篇（≤5），到第 2 层或每层满 5 篇即停止**；`per_layer_cap=5`。声明后禁止事后调高。

### Step 2 — 前后向追踪（1–2 次响应）
构建 `result.trace_results[]`，每个方向都执行，总数 10–20 封顶：
- **backward**：种子引用了谁。`direction:"backward"`，`layer` 从 1 起；relation 标注 `method_origin / dataset_origin / prior_work / other`。
- **forward**：谁引用了种子。`direction:"forward"`，relation 标注 `improvement / critique / application / other`；区分"用它/改它/质疑它"。
- 每条给 `related_basis`（与种子关联依据**一句话**，写清方向+层级+关系）与 `source_ref`（输入文件具体位置，可回指）。拿不准的边 `pending=true` 写 `pending_reason`。
- 第 2 层扩展：以第 1 层新节点为起点继续追踪，同样每层 ≤5 篇；无前向记录时 forward 留空但要在 material_gaps / trace_summary 登记原因，**不补造**。

### Step 3 — 汇总与运行状态（1 次响应）
- 回填 `result.trace_summary`：`backward_count`/`forward_count`/`backward_layers`/`forward_layers` 各项**必须等于** trace_results 对应条数与最大层级（机器复算）。
- `result.run_status`：state ∈ success/partial/unable_to_determine/refused，非 success 写 reason。

### Step 4 — 自检与交付（校验脚本退出码恒 0，看 verdict）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- FAIL 则按 problems 逐条修复 → 覆盖写 result.json（保留 verify_check 回写的 self_check/gates/unbacked_numbers/validator_verdict）→ 重跑直到 PASS（或确认无法修复并如实记录）。
- verdict 分级：`traced`（双向覆盖、计数一致）| `partial_trace`（有空方向或 pending 未清）| `insufficient_records`（材料不足）| `unverifiable`（材料缺口，material_gaps 必须非空）。
- 增益层：预算 <50% 时可用 `--ablate all` 双跑写 gain_evidence；预算 ≥50% 直接 `gain_evidence.available=false`、`efficiency.available=false`，不编数字。

## 输出 schema（result.json — output_contract 全字段 + 最小业务键）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": "…", "packages": "stdlib-only", "note": "照实"},
    "seed": {"seed_id": "S0", "title": "…", "year": 2024, "doi": "…", "source_ref": "case.json:seed", "note": "…"},
    "trace_results": [
      {"trace_id": "t1", "paper_id": "B1", "title": "…", "year": 2019, "doi": "…",
       "direction": "backward | forward", "layer": 1, "relation": "method_origin | dataset_origin | prior_work | improvement | critique | application | other",
       "related_basis": "与种子关联依据一句话", "source_ref": "records.references[0]",
       "pending": false, "pending_reason": null}
    ],
    "trace_summary": {"backward_layers": 1, "forward_layers": 1, "backward_count": 3, "forward_count": 5,
                      "max_layer": 2, "per_layer_cap": 5, "seed_forward_available": true,
                      "stop_rule": "控制在2层、每层≤5篇即停止", "coverage_note": "…"},
    "run_status": {"state": "success | partial | unable_to_determine | refused", "reason": null, "manual_takeover": []},
    "verdict": "traced | partial_trace | insufficient_records | unverifiable", "verdict_basis": "一句话依据",
    "gain_evidence": {"available": false, "reason": "…"}, "efficiency": {"available": false, "reason": "…"}
  },
  "claims": [{"claim_id": "k1", "text": "…", "kind": "reported | inferred", "source_id": "…", "evidence": [{"quote": "材料原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [], "unbacked_numbers": [], "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "result_readable", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. 结构：case_id 空、result 非对象、seed 空（title 与 doi 都无）、trace_results 非数组或为空。
2. 单条违规：trace_id 缺失/重复；direction 枚举非法；layer 非 ≥1 整数；related_basis 或 source_ref 空；pending=true 却无 pending_reason。
3. 计数不符：trace_summary.backward_count/forward_count 与实际方向条数不一致；layers 与最大层级不一致；stop_rule 或缺 per_layer_cap。
4. 状态违规：run_status.state 枚举非法；state≠success 却无 reason；verdict 枚举非法。
5. 闸门：gates state 非 enforced 时 warn「下游不得宣称已核对」——没跑 ≠ 通过。

## 最小调用示例
`examples/` 为合成案例（**非正式答案**），本地自测：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 数据源无前向引用记录 | forward 留空 + seed_forward_available=false + material_gaps 登记，verdict=partial_trace |
| 种子未在材料中明示 | 按题面定位并登记 uncertainties.conflicts，不猜；定位失败 status=insufficient_evidence |
| 缺 DOI / 元数据冲突 | 边 pending=true 写 pending_reason，不补造文献 |
| 算力/时间不足 | 按 stop_rule 收尾，verdict=partial_trace，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按铁纪律第 2 条写 result.json，status=partial |

## 已知限制
- 仅追踪输入材料内的引用关系：不调外部引文接口、不抓数据（stdlib-only）；材料没给的引用边登记缺口，不联网补。
- 只做前后向追踪一个方向：不输出关联发现/引用网络/路径解释/去重合并。
- 增益对照未单独成脚本：预算 <50% 时以 verify_check 正常/退化双跑量化，≥50% 时 available=false。