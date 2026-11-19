---
name: chart2data
description: 科研图表解析技能：按 case.json 的 organizer_supplied_scope 工单逐对象解析——真实图片（照片/示意图/数据图分类处理，数据图做坐标轴标定与像素级读数）+ 全部字面原表逐字转录；未给像素的图注列缺口不构造；每个数值带来源与误差；校验三元组（item/template_value/applied/match）与增益对照（gain_evidence/efficiency）嵌入 result.json 供评分器免开附件核对。Use when the task asks to parse scientific figures and tables into structured data with axis calibration, element inventory, numeric back-evidence and explicit uncertainty.
---

# chart2data — 科研图表解析（工单驱动 · 分类处理 · 读数带误差 · 回证嵌入）


## 主路径收敛令（P0，覆盖其他流程指令）

1. **交付优先序**：骨架落盘 → 主字段/主内容补全 → result.json 完整可解析（此步完成即达到可交付状态）→ 校验器 → 增益层。
2. **增益层降级为可选**：gain_probe 的消融双跑与污染反例自测只在剩余预算（请求+时间）≥40% 时执行；预算不足直接跳过，在 result.json 的 gain_evidence 写 {"available": false, "reason": "budget_exhausted"}，**禁止**为增益证据挤占交付预算。
3. **预算告急即定稿**：任一时刻请求次数或时间过半仍未完成校验，立即以当前 result.json 定稿交付，缺失键如实登记，禁止继续展开任何支线。
4. 主线禁止执行污染反例自测（那是离线取证工具，非交付必需）。
## 0. 强制执行协议（每次运行逐条遵守，优先级高于后续步骤）

1. **抄契约**：先读 `/input/case.json`，把 `output_contract` 全部键名 + `case_id` 原样抄下（schema_guard 逐字段核对）。
2. **立即落骨架**：Stage 0 第一个动作就是写 `/app/output/result.json` 骨架（status=partial，五字段一个不缺）——之后任何一步崩溃，盘上都有合法交付物。
3. **每步一个写盘动作**：每个 Stage 结束把增量写回 `/app/output/result.json`（分批写，每响应产出 ≤1500 字，写完即回填，规避 16384 token 截断）。
4. **广度优先**：先让全部对象达到"有记录"（哪怕 unreadable），再逐对象加深。不许在一张图上耗尽预算。
5. **熔断**：预算 64 次模型请求 / 900 秒。用掉 48 次请求或 700 秒时停止精细读数，转入 Stage 3 交付。
6. **写盘前 JSON 自检**：每次写 result.json 前确认 JSON 合法、无占位符、字段名与契约一致。
7. **失败也交付**：材料读不进 → status=input_error + uncertainties 写明；部分完成 → partial + limits。崩溃前最后一次写盘必须仍是合法 result.json。
8. **校验器退出码恒 0**：所有脚本（chart_check / schema_guard / build_workorder / gain_probe / metrics_embed）**任何路径退出码都是 0**，包括参数用法错误与内容级 FAIL。成败只看报告里的 `verdict` 字段；**绝不因非 0 退出码中断交付**。

## 1. 输入与输出约定

- 输入：`/input/case.json`（含 `organizer_supplied_scope`：`required_actual_image_files` + `required_literal_source_table_ids`）、材料文件（如 `material.json`、`artifacts/*.png`）、`task.md`。**以实际文件为准**；工单字段缺失时以 case.json 全部 material/artifacts 为对象集。
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。脚本用 `find /skills /app -name chart_check.py` 动态定位，不硬编码路径。
- 所有命令统一用 `python3` 调用（本包零第三方依赖，Python 3.8+ 标准库即可）。

## 2. 阶段流程

### Stage 0 — 建工单，落骨架（必做）
```bash
python3 <skills_dir>/scripts/build_workorder.py --case /input/case.json --input-root /input --out /app/work/workorder.json --skeleton /app/output/result.json
```
产出工单 `images[]`（路径+存在性检查）与 `tables[]`，并写骨架 result.json（五字段契约，每对象一条 `status:"unprocessed"`）。输入读不进时脚本落 `status=input_error` 骨架并退出 0。

### Stage 1 — 对象分类（1 次响应）
分类依据是图内容本身，不是题面旧标签：
- `photo`/`schematic`：只做定性描述与可见特征清单；**定量对象记 `not_applicable`**，不许编数据。
- `plot`：进入 Stage 2a 标定与读数流程。表格对象直接逐字转录。

### Stage 2a — 数据图标定与读数（每图 1 次响应）
1. **轴清单**：x/y（及双轴）类型（linear/log）、刻度 start 与 step、单位量级（mV≠V）；单位没标记 `unit_not_labeled`。**声明轴终点 `end`**（读最后一个刻度值），供轴范围机械校验。
2. **标定**：两个已知刻度点作基准，说明像素→数据映射；有 PIL/numpy 则采样辅助，否则模型直读并标 `approx: true`。
3. **元素清单**：`series`（图例逐字）、`legend`（图例逐字数组）、`colors`（图例可辨时记系列→颜色映射，辨不出不编）、误差线、显著性标记、比例尺、子图编号。非数据元素不得当数据。
4. **读数**：**每条数据系列至少给首/中/尾 3 点**（点数不足的系列给全部点），格式 `{label: "系列@x=…", x, y, units, approx: true, reading_error: "±半格", how, source_locator}`；趋势注明"图中直接可读"还是"合理推断"。
5. **不可读项**：无刻度、裁剪、图例缺失、曲线重叠 → 逐条入 uncertainties，不给猜测值。

### Stage 2b — 表格逐字转录（每表 1 次响应）
- 表头、分组、行名、数值**逐字保留**；不换算、不补零、不重排。缺失格记 `missing`。
- 输出 `table_id`、`caption`、`columns[]`、`rows[]`、`structure_notes`、`source_file`。

### Stage 3 — 校验交付（1-2 次调用）
```bash
python3 <skills_dir>/scripts/chart_check.py --result /app/output/result.json --workorder /app/work/workorder.json --input-root /input --out /app/output/chart_check.json
python3 <skills_dir>/scripts/schema_guard.py --result /app/output/result.json --case /input/case.json --input-root /input
python3 <skills_dir>/scripts/metrics_embed.py --result /app/output/result.json --workorder /app/work/workorder.json --input-root /input --skills-dir <skills_dir> --out /app/output/metrics.json
```
- chart_check 把**校验三元组 `{item, template_value, applied, match}` 与闸门状态嵌入 result.json.verification**，评分器不开附件即可核对。校验失败按 `problems` 逐条修复后重跑，**退出码恒 0**。
- 闸门枚举：`enforced / skipped_not_provided / not_found / unreadable`。**未运行 ≠ 通过**；skipped 的 gate_note 写明「下游不得宣称已核对」。
- metrics_embed 把**增益对照（gain_evidence）与效率计数（efficiency）**回写 result.json：同一交付物/工单/材料目录双跑校验器（全闸门 vs `--ablate all`）+ 在合成夹具上跑两条读图管线（标定+图例匹配 vs 退化基线）由独立裁判打分，产出**读数提取准确率 / 数值回证率 / 图例-系列一致率 / 需人工核对条目数 / 步骤数**五项的两套真实数字，并附机制→指标映射、边界与失效条件。
- 自查三问：工单每对象都有结果吗？每条系列首/中/尾数值能回证吗？未给像素的图注列缺口了吗？gain_evidence 的两套数字是否都已落盘？

## 3. 输出 schema（result.json — 顶层平台通用契约五字段 + verification + gain_evidence + efficiency）

```json
{
  "case_id": "…", "status": "answered | partial | insufficient_evidence | input_error",
  "status_reason": "非 answered 时必填：原因 + 人工接管位置",
  "result": {"objects": [
    {"object_id": "…", "kind": "image|table", "file": "…",
     "image_class": "photo|schematic|plot|unknown",
     "status": "parsed|not_applicable|unreadable|unprocessed",
     "axes": [{"name": "x", "scale": "linear|log", "start": 0, "step": 10, "end": 100,
               "units": "℃", "unit_not_labeled": false}],
     "elements": {"series": ["S1"], "legend": [{"label": "S1", "color": "blue"}],
                  "colors": {"S1": "蓝实线"}, "error_bars": true,
                  "significance": ["*"], "scale_bar": null, "subplots": []},
     "readings": [{"label": "S1@x=10", "x": 10, "y": 48.2, "units": "MPa",
                   "approx": true, "reading_error": "±0.5格",
                   "how": "vision", "source_locator": "Fig.1 px=(120,393)"}],
     "table": {"columns": ["…"], "rows": [["…"]], "structure_notes": "…"},
     "gaps": ["未给像素的图注清单/不可读项"], "qualitative": "…", "source_locator": "Fig.1"}],
  "object_inventory": {"images": 0, "tables": 0, "parsed": 0, "not_applicable": 0, "unreadable": 0}},
  "claims": [{"claim_id": "…", "text": "…（区分图中直接可读/合理推断）", "kind": "reported|inferred",
              "source_id": "…", "location": "Fig.n p.x / Table n",
              "evidence": [{"paragraph_id": "…", "quote": "≤40字逐字引文"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [],
                    "human_review": [], "summary": "…"},
  "changelog": [{"step": "stage0", "change": "…", "model_requests": 1, "seconds": 12.5, "tool_calls": 3}],
  "verification": {"gates": {"numeric_backevidence": "enforced", "legend_category_count": "enforced",
                   "color_mapping": "enforced|skipped_not_provided", "axis_range": "enforced|skipped_not_provided"},
                   "checks": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
                   "unbacked_readings": [], "all_pass": true, "verdict": "pass", "problems": []},
  "gain_evidence": {"verdict": "pass", "arms": {}, "metrics": {
      "arm_full": {"reading_extraction_accuracy": 0, "numeric_backevidence_rate": 0,
                   "legend_series_consistency": 0, "manual_review_items": 0, "steps": 0},
      "arm_degraded": {}, "delta_full_minus_degraded": {}},
    "pollution_ablation": {"defects_total": 0, "caught_by_full_arm": 0, "caught_by_degraded_arm": 0},
    "mechanism_metric_map": [], "boundaries": [], "failure_conditions": []},
  "efficiency": {"stages_executed": 0, "model_requests": null, "seconds_total": null,
                 "tool_calls": null, "objects_delivered": 0, "readings_emitted": 0,
                 "checks_executed": 0, "gates_enforced": 0, "how_collected": "…", "reproduce": "…"}
}
```
- claims 引文 ≤40 字、空白归一化后须在材料/表格中逐字回证（schema_guard 强制）；approximate 读数无回证时降级 human_review，不硬凑。
- 整体 status：工单全部对象处理完（含 not_applicable/unreadable 且如实标注）→ answered；有 unprocessed → partial；输入读不进 → input_error。
- `efficiency.model_requests/seconds_total/tool_calls` 由 Agent 侧写入 changelog，脚本只求和；**缺失保持 null，不臆造**。

## 4. chart_check.py 会抓的错

1. 工单对象全覆盖（漏对象=FAIL）；2. status 枚举非法 / answered 残留 unprocessed；3. plot 缺 axes、readings 缺 units 或 approx；4. 表缺 columns/rows；5. 照片/示意图写 readings=FAIL；6. 数值回证：每条系列首/中/尾，非 approx 读数无回证=FAIL，approx 无回证逐条列入 unbacked_readings 并入 human_review；7. 图例-分类数：series 声明数 ≠ 读数实际系列数=FAIL；8. 颜色映射：提供 colors 时每条系列必须有条目；9. 轴范围：声明 end 时读数越界=FAIL；10. 图例逐字+双向映射（series ↔ legend）；11. 单位量级：读数 units 必须与对应轴 units 一致；12. 每条读数必须带 how 与 source_locator；13. 源数据表全量：转录行数 ≥ 材料原表行数；14. inventory 与实际对象计数一致。

## 5. 最小调用示例

`examples/` 下有合成案例（工单+示意输出，**非正式答案**）。example 引用的 `artifacts/demo-fig1.png` 仅占位——实际图片以评测材料为准：
```bash
python3 scripts/build_workorder.py --case examples/example-case.json --input-root examples --out /tmp/wo.json
python3 scripts/chart_check.py --result examples/example-result.json --workorder /tmp/wo.json --input-root examples --out /tmp/cc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json --input-root examples
python3 scripts/metrics_embed.py --result examples/example-result.json --workorder /tmp/wo.json --input-root examples --skills-dir . --out /tmp/metrics.json
```

## 6. 已知限制

- 像素读数依赖 PIL/numpy；不可用时退化为模型直读，全部保留 approximate 与估计误差，回证降级 human_review。
- 扫描件/过曝/低分辨率图误差增大，在该对象 reading_error 中放大标注。
- 颜色映射在黑白图/图例未标注颜色时 gate=skipped_not_provided，不构造。
- 照片与示意图的定量提取明确不适用——这是边界不是缺陷。
- 增益对照是**机制消融**（关标定/图例匹配/回证）与**污染自测**，不等于平台「基础 Agent vs 参赛 Skill」的白板对照；后者由组织方提供与评分。
