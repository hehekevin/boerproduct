# chart2data — 科研图表解析 Skill（v6）

面向 Bohrium 产品赛第 3 周「文献阅读」赛道「科研图表解析」(challenge-f35e4ca5) 的参赛 Skill。
锁定子场景：**单张科研图片 + 全部字面原表 → 带单位/精度/误差与回证路径的结构化数据**。

## 1. 用途与适用条件

给定 `case.json` 工单（`organizer_supplied_scope.required_actual_image_files` +
`required_literal_source_table_ids`），逐对象完成：

1. **对象分类**：按图内容本身判 `photo` / `schematic` / `plot`（不信题面旧标签）。
   照片与示意图只做定性特征清单，**定量提取记 `not_applicable`**——这是边界不是缺陷。
2. **坐标轴标定**：轴类型（linear/log）、刻度 start/step/**end**、单位量级（mV≠V）；
   两个已知刻度点建立像素→数据映射，轴终点缺失时明确标 `unit_not_labeled` / 不构造。
3. **元素还原**：图例逐字、series、颜色映射、误差线、显著性标记、比例尺、子图编号——
   **非数据元素不得当数据**。
4. **带误差读数**：每条数据系列至少首/中/尾 3 点，每点带 `units`、`approx`、
   `reading_error`、`how`、`source_locator`（可回指原图像素/图号）。
5. **原表逐字转录**：表头、分组、行名、数值逐字保留，不换算、不补零、不重排；
   缺失格记 `missing`；行数与材料原表核对（少行 = FAIL）。
6. **回证与闸门**：每条系列首/中/尾的数值必须在材料/引文 blob 中逐字命中；
   非 approx 无回证 = FAIL，approx 无回证逐条降级 `human_review`。
7. **显式边界**：未给像素的图注列缺口、无法判断项、冲突项分别登记在
   `uncertainties.{unreported, unverifiable, conflicts, human_review}`。

**核心保证**：校验三元组 `{item, template_value, applied, match}`、闸门四态、
增益对照与效率计数全部**嵌入 result.json**，评分器不开附件即可核对；
所有脚本**任何路径退出码恒 0**，校验失败只改 `verdict` 不中断交付。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研读者 / 论文作者 | 手里有一张论文图，想把曲线数值变成可复现的 CSV | 结构化读数（带单位+误差+像素定位）+ 图例-系列对应表 |
| 数据复现者 | 论文正文说「S1 在 60 ℃ 达 51.0 MPa」，图上读数对不上 | 数值回证率与 unbacked 清单，明确哪些是「材料里写着」哪些是「看着像」 |
| 图表解析工具开发者 | 需要一个坐标标定 + 图例匹配的可复用模块 | `gain_probe.py` 的纯标准库 PNG 编解码 + 标定 + 独立裁判 |
| 多模态 Agent 开发者 | 想给 Agent 加「读图必带证据」的硬约束 | 14 条机械闸门 + 闸门四态 + 校验三元组，可直接抄 |
| 教学 / 培训 | 演示「读数必须可回证」的科研诚信纪律 | 正例（examples/）+ 反例（污染自测）双跑对照 |

**不适用**：不做物质成分判定（光谱图只给峰位/峰强，不推断化合物）；不做统计推断
（不给 p 值、不做假设检验）；不解析非 PNG 格式的像素管线；不替代作者的原始数据。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 实测通过），**只用标准库** |
| 第三方依赖 | **零**（`json`/`os`/`re`/`sys`/`argparse`/`struct`/`zlib`/`math`/`subprocess`/`tempfile`/`shutil`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 可选加速 | 有 PIL/numpy 时像素读数更准；**没有也照跑**（退化为模型直读 + `approx: true`） |
| 磁盘 | 整包 < 200 KB（上限契约：≤50 文本文件 / 单文件 ≤500 KB / 总计 ≤2 MB） |
| 网络 | **不需要**（无 CDN、无 pip、无外部数据下载） |

## 4. 安装与运行

**安装**：把 `submission/` 挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需安装步骤、无依赖解析、无需联网。脚本路径请用
`find /skills /app -name chart_check.py` 动态定位，不硬编码。

```bash
# Step 0：自动落工单 + result.json 骨架（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_workorder.py --case /input/case.json \
  --input-root /input --out /app/work/workorder.json --skeleton /app/output/result.json

# Step 3：三重自检 + 增益/效率回写（退出码恒 0；判据是报告里的 verdict 字段）
python3 /skills/weekly-skill/scripts/chart_check.py --result /app/output/result.json \
  --workorder /app/work/workorder.json --input-root /input --out /app/output/chart_check.json
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --input-root /input
python3 /skills/weekly-skill/scripts/metrics_embed.py --result /app/output/result.json \
  --workorder /app/work/workorder.json --input-root /input \
  --skills-dir /skills/weekly-skill --out /app/output/metrics.json

# 可选：单独看增益对照的两套数字（像素级双臂 + 污染自测）
python3 /skills/weekly-skill/scripts/gain_probe.py --selftest \
  --out /app/output/gain_probe.json --workdir /app/work
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --workorder /app/work/workorder.json --input-root /input --pollute \
  --out /app/output/gain_probe_delivery.json
```

## 5. 输入与输出

- **输入**：`/input/case.json`（工单 + `output_contract` + 材料引用）、材料文件
  （`material.json`、`artifacts/*.png`）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `status_reason` / `result` / `claims` / `uncertainties` /
    `changelog` / `verification` / `gain_evidence` / `efficiency`
  - `result.objects[]`：每个对象一条，含 `object_id`/`kind`/`image_class`/`status`/`axes`/
    `elements`/`readings`/`table`/`gaps`/`qualitative`/`source_locator`
  - `verification`：闸门四态 + 校验三元组 + `unbacked_readings` + `all_pass`
  - `gain_evidence`：五项指标的两套数字 + 污染对照 + 机制→指标映射 + 边界 + 失效条件
  - `efficiency`：自动采集的效率计数 + `reproduce` 命令
- **status**：`answered`（工单全部对象处理完，含如实标注的 not_applicable/unreadable）|
  `partial`（有 unprocessed 或部分完成）| `insufficient_evidence`（关键材料缺失）|
  `input_error`（输入不可读）。
- **工作区产物**：`/app/work/workorder.json`（工单）、`/app/output/chart_check.json`、
  `/app/output/metrics.json`、`/app/output/gain_probe*.json`。

### 字段口径速查

| 字段 | 含义 | 口径 |
|------|------|------|
| `readings[].approx` | 该读数是否为目测/近似值 | 像素标定得到且有刻度锚点可写 false，否则 true |
| `readings[].reading_error` | 误差区间 | 如 `±0.5格`（半格 / 步长）；扫描件需放大标注 |
| `readings[].how` | 读数方式 | `pixel_calibrated_sampling` / `vision` / `table_lookup` |
| `readings[].source_locator` | 回指原图位置 | `Fig.1 px=(120,393)` 或 `Table 2 row 5` |
| `axes[].end` | 轴终点值 | 读最后一个刻度；不声明则 `axis_range` gate = skipped_not_provided |
| `gates` 四态 | 闸门执行情况 | `enforced`（真跑了）/ `skipped_not_provided`（材料未提供）/ `not_found` / `unreadable`；**未运行 ≠ 通过** |
| `unbacked_readings` | 无逐字回证的近似读数 | 每条带 object/series/position/values，并自动进 `human_review` |
| `efficiency.model_requests` | 模型请求数 | Agent 侧写入 changelog，脚本只求和；**缺失为 null，不臆造** |

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供**合成**案例：一张占位图引用 + 一张 3 行原表
（示意读数 `S1@x=10 → 48.2 MPa`、`S2@x=20 → 4.4 %`）。示意输出关键片段：

```json
{
  "case_id": "demo-chart-001", "status": "answered",
  "result": {
    "objects": [
      {"object_id": "demo-fig1", "kind": "image", "image_class": "plot", "status": "parsed",
       "axes": [{"name": "x", "scale": "linear", "start": 0, "step": 10, "end": 20,
                 "units": "min", "unit_not_labeled": false},
                {"name": "y", "scale": "linear", "start": 0, "step": 10, "end": 60,
                 "units": "MPa", "unit_not_labeled": false}],
       "elements": {"series": ["S1", "S2"],
                    "legend": [{"label": "S1", "color": "blue"}, {"label": "S2", "color": "red"}],
                    "colors": {"S1": "蓝实线", "S2": "红虚线"},
                    "error_bars": true, "significance": ["*"], "scale_bar": null, "subplots": []},
       "readings": [{"label": "S1@x=10", "x": 10, "y": 48.2, "units": "MPa",
                     "approx": true, "reading_error": "±0.5格", "how": "vision",
                     "source_locator": "Fig.1 px=(120,393)"}]},
      {"object_id": "DEMO-P001", "kind": "table", "status": "parsed",
       "table": {"columns": ["Specimen", "Ultimate strength (MPa)", "Elongation (%)"],
                 "rows": [["A-1", "48.2 ± 1.3", "3.1"], ["B-2", "55.7 ± 2.0", "4.4"]],
                 "structure_notes": "示意材料（非正式案例）"}}
    ],
    "object_inventory": {"images": 1, "tables": 1, "parsed": 2,
                         "not_applicable": 0, "unreadable": 0}},
  "claims": [{"claim_id": "k-01", "kind": "reported", "source_id": "DEMO-P001",
              "location": "Table 1 row A-1",
              "text": "S1 系列在 x=10 处 y=48.2 MPa（图中直接可读）",
              "evidence": [{"paragraph_id": "notes", "quote": "S1 系列在 x=10 处 y=48.2 MPa"}]}],
  "verification": {"gates": {"numeric_backevidence": "enforced"},
                   "checks": [{"item": "demo-fig1.legend_category_count",
                               "template_value": 2, "applied": true, "match": true}],
                   "unbacked_readings": [], "all_pass": true},
  "gain_evidence": {"verdict": "pass",
                    "metrics": {"arm_full": {"reading_extraction_accuracy": 1.0,
                                             "numeric_backevidence_rate": 0.6667,
                                             "legend_series_consistency": 1.0,
                                             "manual_review_items": 2, "steps": 9},
                                "arm_degraded": {"reading_extraction_accuracy": 0.1667,
                                                 "numeric_backevidence_rate": 0.0,
                                                 "legend_series_consistency": 0.0,
                                                 "manual_review_items": 6, "steps": 7}}},
  "efficiency": {"stages_executed": 2, "model_requests": 2, "checks_executed": 14}
}
```

### 最小可运行自检清单（复制即可跑，全绿才算交付合格）

```bash
cd submission
mkdir -p /tmp/w4/out /tmp/w4/work
# ① 工单 + 骨架
python3 scripts/build_workorder.py --case examples/example-case.json --input-root examples \
  --out /tmp/w4/work/workorder.json --skeleton /tmp/w4/out/skeleton.json
# ② 结构守卫（预期 verdict=pass，退出码 0）
python3 scripts/schema_guard.py --result examples/example-result.json \
  --case examples/example-case.json --input-root examples
# ③ 业务闸门（预期 verdict=pass，退出码 0）
python3 scripts/chart_check.py --result examples/example-result.json \
  --workorder /tmp/w4/work/workorder.json --input-root examples --out /tmp/w4/out/cc.json
# ④ 增益对照 + 效率回写（预期 verdict=pass，退出码 0；写入 result.json）
#    —— 用副本跑，避免改动随包发布的 examples/example-result.json
cp examples/example-result.json /tmp/w4/out/result.json
python3 scripts/metrics_embed.py --result /tmp/w4/out/result.json \
  --workorder /tmp/w4/work/workorder.json --input-root examples --skills-dir . \
  --out /tmp/w4/out/metrics.json
# ⑤ 像素级双臂对照（预期 verdict=pass，五项指标两套数字）
python3 scripts/gain_probe.py --selftest --out /tmp/w4/out/gain_probe.json --workdir /tmp/w4/work
```

> 注：`chart_check` / `metrics_embed` 会把 `verification` / `gain_evidence` / `efficiency`
> 回写进被校验的 result.json。**正式运行**中这一步是有意为之（评分器要读这些字段）；
> **自检**中建议先 `cp` 到临时副本再跑第 ④ 步，以免改动随包发布的示例文件。
> `chart_check` 会自动把 result.json 自身排除在「材料证据 blob」之外
> （`--skip-blob`），因此不存在「自己写的数字回证自己」的自证循环。

自检通过判据（逐条查 `result.json`）：
① `result.status` ∈ 四态且 `result.objects[]` 覆盖工单全部对象；
② `verification.all_pass == true` 且 `verification.gates` 每项 ∈ 四态；
③ `verification.checks[]` 每条含 `item`/`template_value`/`applied`/`match`；
④ `gain_evidence.metrics.arm_full` 与 `arm_degraded` 两套五项数字均已落盘；
⑤ `gain_evidence.pollution_ablation.caught_by_full_arm > caught_by_degraded_arm`；
⑥ `efficiency.how_collected` 与 `efficiency.reproduce` 非空。

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=pass`（output_contract 全字段 + 五字段通用契约） |
| A2 | 对象全覆盖 | 工单 `images[]`/`tables[]` 每个 object_id 在 `result.objects[]` 有记录 |
| A3 | 状态诚实 | 无 unprocessed 残留；有 unreadable 必须在 `uncertainties` 登记 |
| A4 | 闸门四态 | `verification.gates` 每项 ∈ {enforced, skipped_not_provided, not_found, unreadable} |
| A5 | 读数合规 | 每条读数带 `units` + `approx` + `how` + `source_locator`；plot 缺 axes = FAIL |
| A6 | 数值回证 | `verification.unbacked_readings` 中每条已进 `uncertainties.human_review` |
| A7 | 表全量 | 材料原表行数 ≤ 转录行数（表头 + 数据行） |
| A8 | 照片边界 | photo/schematic 对象 `readings` 为空 |
| A9 | 增益有据 | `gain_evidence.metrics` 含 arm_full / arm_degraded 两套五项数字 + 映射 + 边界 + 失效条件 |
| A10 | 污染可检出 | `pollution_ablation.caught_by_full_arm` ≥ `caught_by_degraded_arm` 且 `defects_total > 0` |
| A11 | 效率可复算 | `efficiency` 含 `how_collected` + `reproduce`；缺失计数为 null |
| A12 | 零中断 | 全部脚本在缺文件 / 坏 JSON / 脏数据 / 参数错误下退出码均为 0 |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` + `metrics_embed.py` 产出**四层对照**，全部数字来自本次运行实跑：

| 层 | 对照方式 | 产出 |
|----|---------|------|
| ① 像素级双臂 | 同一张合成 PNG 上跑两条读图管线：`full`（探测轴线与刻度→像素↔数据标定 + 图例↔系列语义匹配 + 单位传递 + 来源定位）vs `degraded`（整图边界线性假设 + 只按色相团命名系列 + 不传单位 + 不写定位），由**独立裁判**（第三份代码，不与两条管线共享实现）打分 | 读数提取准确率 / 数值回证率 / 图例-系列一致率 / 需人工核对条目数 / 步骤数 |
| ② 闸门消融 | 同一交付物 + 工单 + 材料目录双跑 `chart_check.py`：`--ablate none`（全闸门）vs `--ablate all`（全关） | defects_caught / checks_applied 差 |
| ③ 污染自测 | 在交付物**副本**上注入 8 条已知缺陷（每条对应一条闸门），再跑两臂 | 检出条数 / 漏检条数（full 应全检出，degraded 应漏 2 条） |
| ④ 效率计数 | changelog 求和 + 对象/读数计数 + 实际执行的 checks/gates 数 | stages / requests / seconds / tool_calls / objects / readings |

机制→指标映射表写在 `gain_evidence.mechanism_metric_map`，每条含 `mechanism` / `metric` /
`why` / `degraded_arm`；边界写在 `boundaries`；失效条件写在 `failure_conditions`。

> **重要边界**：①是**机制消融**（关掉标定/图例匹配/回证），**不等于**平台
> 「基础 Agent vs 参赛 Skill」的白板对照；②③④是本校验层的自证对照。
> 像素级数字来自**合成自检夹具**（真值已知才能算准确率），只证明机制可复现，
> **不得当作正式案例成绩**。平台基线对照由组织方生成与评分，本记录不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| `case.json` 缺失/坏 JSON | `build_workorder` 落 `status=input_error` 骨架 + `status_reason` 写明人工接管位置，**退出码 0** |
| 工单声明的图片文件不存在 | `images[].exists=false`；该对象记 `unreadable` + `gaps` 说明，**不构造内容** |
| 工单里的表 id 在材料中找不到 | `tables[].found=false`；对象记缺口，**不凭 id 猜表内容** |
| 图无刻度 / 图被裁剪 | 标定退化为 `axis_extent_fallback`；读数标 `approx: true`、放大 `reading_error`，进 `human_review` |
| 图例缺失或黑白图 | `legend_series_map` / `color_mapping` gate = `skipped_not_provided` + gate_note「下游不得宣称已核对」 |
| 曲线重叠 / 过曝 / 低分辨率 | 颜色团合并多曲线 → 系列数少于真实数 → 全部标 `approx` 并降级人工复核 |
| 单位未标注 | `unit_not_labeled: true`；**不猜量级**（不把 mV 当 V） |
| PNG 非 8bit / 带隔行 / 调色板 | 纯标准库解码器不支持 → 跳过像素管线，记录诊断，**不静默产出错误读数** |
| 材料未写出对应表值 | 回证率必然低——这是**材料的诚实缺口**不是解析失败，记 `uncertainties.unreported`，不硬凑数值 |
| 校验脚本报 FAIL | 按 `problems` 逐条修复后覆盖写 result.json 再重跑；**退出码恒 0**，修不了就如实登记 uncertainties |
| 预算/时间耗尽 | 保留已产出部分，`status=partial`，changelog 注明截断位置 |
| **任何脚本任何路径失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求「失败也要交付」。脚本把结论写进报告的 `verdict`（pass/fail）与
`problems` 列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障
（包括参数用法错误）打断。SKILL.md 协议第 8 条明确「只看 verdict」。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**（full 检出 8/8 → degraded 检出 6/8），
它的作用是量化「关闭这些机制会漏掉多少」，作为增益证据。退化臂结果仅用于
增益对照，**不得当作交付自检结论**。

**Q：`gain_evidence` 里的数字是真实的吗？**
是。像素级五项指标由 `gain_probe.judge()`（独立裁判）在本次运行实跑产出；
污染对照的缺陷由脚本在**副本**上注入，原 `result.json` 不被改动。
平台基础 Agent 对照由组织方提供，本记录不冒充。

**Q：为什么 full 臂的步骤数反而更多？**
full 臂多做了刻度探测、标定、图例匹配与单位传递，步骤数更高是**机制更重的证据**，
不是低效。`metrics.direction` 显式标注每个指标的方向（`steps` 标 `lower_is_better`，
但两臂差异应结合 `manual_review_items` 一起读）。

**Q：读数一定要精确到小数点后两位吗？**
不。`approx: true` + `reading_error: "±0.5格"` + `source_locator` 三件套齐了，
就是合格的「带误差的结构化读数」。**编造小数位比少写精度更糟**。

**Q：照片能不能也做定量提取？**
不能。photo/schematic 的 `readings` 非空 = FAIL。这是刻意的边界：
凭空给显微照片编一个「直径 23.4 µm」比留空更危险。

**Q：能不能跳过没把握的对象不写？**
不能。协议第 4 条「广度优先」要求全部工单对象都有记录——写 `unreadable` + `gaps`
也算记录。漏对象 = FAIL。

**Q：`efficiency.model_requests` 为什么可能是 null？**
脚本只能对 changelog 里的计数求和，模型请求数由 Agent 侧写入。没有就是 null，
**不臆造**。这是诚实口径。

## 11. 适用范围与限制

- 纯 stdlib；PNG 像素管线只支持 8bit 非隔行（灰度/RGB/带 alpha），
  其余格式跳过像素管线并记录诊断。
- 目测读数（无 PIL/numpy）受限于模型视觉能力，误差靠 `reading_error` 标注表达，
  不保证亚格精度。
- 只做**读数与结构化**，不做科学结论的因果推断、不做物质鉴定、不做统计检验。
- 不解析多图 PDF 的跨页子图自动配对（子图编号靠人工/模型在 `elements.subplots` 标注）。
- 增益对照是**机制消融 + 污染自测**，不等于平台基础 Agent 对照（见第 8 节边界）。
- 合成夹具数字只证明机制可复现，**不代表正式案例成绩**。
- 颜色映射在黑白图/图例未标色时不可用（gate = skipped_not_provided），不构造。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/gain_probe.py` 的 PNG 编解码 | 纯标准库 `png_write`/`png_read`（含 5 种 filter 还原），可直接搬到任何「零依赖读图」场景 |
| `find_axes()` + `calibrate()` | 纯像素启发式：最长暗线找轴、轴外像素聚簇找刻度、线性映射建标定。换成自己的图型只需改 `_data_grid` |
| `judge()` 独立裁判 | 「用第三份代码给被测代码打分」的模式可整套抄到任何评测 Skill |
| `inject_defects()` 污染自测 | 缺陷→闸门一一对应的注入器，改几行即可测自己的校验器 |
| 闸门四态 + 校验三元组 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}`，任何「Agent 自检」类 Skill 都能用 |
| `_LenientParser` 模式 | 让 argparse 用法错误也退出 0，杜绝「校验器自己把流水线打断了」 |
| `elements.legend` + `elements.colors` 结构 | 图例逐字 + 颜色映射分列存放，双向映射校验 |
| `examples/` 合成案例 | 复制一份改数字即得新的负例；`fixture-chart.json` 改动即得新的自检真值 |

**建议的复用顺序**：先抄 `chart_check.py` 的检查骨架（14 条闸门 + 三元组 + 闸门四态），
再抄 `gain_probe.py` 的双臂对照与独立裁判，最后按自己的业务 schema 改
`elements` / `readings` / `table` 三个字段定义。

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 四阶段流程 + schema + 校验说明 + 限制） | 是（加载入口） |
| scripts/build_workorder.py | Stage 0 工单构建 + 骨架落盘（输入不可读时落 input_error 骨架，退出码恒 0） | 是 |
| scripts/chart_check.py | 14 条业务闸门 + 三元组 + 闸门四态 + `--ablate` 消融开关 | 是（含 `--ablate` 对照实验） |
| scripts/schema_guard.py | output_contract + 五字段通用契约 + claims 引文 ≤40 字逐字回证 | 是（通用） |
| scripts/gain_probe.py | 纯标准库 PNG 编解码 + 像素标定 + 双臂读图 + 独立裁判 + 污染注入自测 | 是（含 `judge()`/`inject_defects()` API） |
| scripts/metrics_embed.py | 把 gain_evidence（五项两套数字）+ efficiency 回写 result.json | 是 |
| examples/example-case.json | 合成输入示例（工单结构） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| examples/material.json | 合成材料（含示意原表与回证句） | 是（fixture） |
| examples/fixture-chart.json | 合成自检夹具（含 truth/evidence_pairs，供像素级裁判算准确率） | 是（fixture） |
| README.md | 本说明（用途/依赖/安装/输入输出/验收/FAQ/限制/异常/复用/维护） | — |
| worklog.md | 开发记录、五维差距清单与双测证据 | — |

## 14. 版本与维护

版本 **v6**（2026-11-17）。依赖：Python 3.8+ 标准库，零第三方依赖。

| 版本 | 增量 |
|------|------|
| v6 | ① 增益对照补齐：`gain_probe.py` 新增 `inject_defects()` 污染注入 + `run_pollution_probe()`，实测 full 臂检出 8/8、degraded 臂 6/8；② `metrics_embed.py` 把**五项指标两套真实数字**（读数提取准确率 / 数值回证率 / 图例-系列一致率 / 需人工核对条目数 / 步骤数）与污染对照写入 `result.json.gain_evidence`，效率计数写入 `result.json.efficiency`；③ **全部脚本任何路径退出码恒 0**（含参数用法错误——新增 `_LenientParser`），`build_workorder` 输入不可读时落 `status=input_error` 骨架；④ README 补齐生态贡献全套（依赖版本/安装运行/输入输出/目标用户场景/验收/FAQ/限制/失败处理/复用建议/版本维护）+「最小可运行自检清单」；⑤ SKILL.md 126 行（≤150 硬约束），命令统一 `python3`，新增协议第 8 条「校验器退出码恒 0」 |
| v5 | 83 公式增强：置顶 8 条协议、校验三元组嵌入 verification、数值回证、闸门四态、claims 引文逐字回证 |
| v4 | 工单驱动 build_workorder、photo/schematic 禁 readings、表格逐字转录、approximate + 误差标注、status 四级诚实 |

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节自检清单 + 污染反例，确认 verdict=pass。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的必填字段清单与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注「示意/非正式案例」。
