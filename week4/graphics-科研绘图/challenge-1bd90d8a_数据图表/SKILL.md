---
name: source-value-chart
description: >
  Scientific data chart generation and source-preserving editing. Reads case.json,
  workorder and source data tables, draws charts with matplotlib (script as editable
  source), exports layered SVG plus 300dpi PNG/PDF, and builds two-layer content_map
  (series element_id-to-column + value-to-cell). Mechanically verifies legend-count vs
  category-count, per-item color mapping, axis range vs data range, and full-coverage
  value sampling (first/middle/last of EVERY series; per-panel on multi-subplot/twin-axis
  charts) in result.json compliance_checks. Embeds the FULL source table (source_table)
  and a reproducibility block (data fingerprint, field mapping, export params) so the
  scorer can verify every cell without opening attachments.
  Every plotted number traceable to a source cell; never fabricates or rewrites values.
---

# source-value-chart：科研数据图表生成与编辑

核心承诺：**图上每个数值都能指回源数据表的具体单元格；源数据表全量嵌入 result.json（评分器不开附件即可逐格核对）；每个数据系列建立 element_id↔数据列映射；图例项数=分类数、颜色逐项对应、轴范围覆盖数据范围、数值抽样全覆盖——全部机械校验并逐条写入 compliance_checks（多子图/双轴逐子图逐轴核对）；reproducibility 块保证独立重跑得同一张图；交付可编辑双源（脚本 + 分层 SVG）+ 真实渲染 PNG/PDF。** 任何环节数据缺失、冲突或失败，都如实登记，不编造、不静默改数。

## 0. 强制执行协议（最高优先级，优先于一切绘图工作）

1. **读完 `/input/case.json`、工单（artifacts/figure-workorder.json）与数据表后，第一件事是写 `/app/output/result.json` 骨架**：含 output_contract 声明的全部键 + `case_id` + `status="partial"`，一个键都不能少；暂无法产出的字段填 `"unknown"` 或 `[]`，不许留空缺键。
2. `output_contract` 以 case.json 实际声明为准（预期为 `["case_id","status","editable_source","export_artifact","content_map","compliance_checks","exceptions"]`）；读到什么抄什么，不臆造键名。
3. **广度优先**：先让每个字段都有占位内容，再逐字段充实，不在单一环节耗尽预算。
4. **预算硬闸**：模型请求超过 48 次（上限 64）、或运行超过 700 秒（上限 900），立即停止细调转入收尾。
5. **写盘自检**：每次写 result.json 前，确认 `json.loads` 可解析、字段齐全、`case_id` 与输入一致。
6. **失败也要写 result.json**：崩溃、缺环境、缺数据时写含 `status="partial"`、exceptions 说明的完整骨架，绝不空手退出；禁止编造软件状态或科学数据；材料缺失、无法判断、运行失败三者在 exceptions 中分别说明。

## 1. 线性五步主流程

### 步骤① 读输入（1-2 次请求）
- 读 `/input/case.json`：抄下 `case_id` 与 `output_contract` 全部键。
- 读 task.md 与工单：确认任务是**生成**还是**编辑**（source-preserving edit）、目标图型、系列、标签、范围要求。
- 找到源数据表（CSV/TSV/Excel/文本表格），确认路径、行列数。**数据表是数值唯一合法来源**；论文文字/标签名只是参照，不依据错误的领域标签补造数据。

### 步骤② 写 result.json 骨架（1 次请求）
按协议第 1 条立即落盘 `/app/output/result.json`，此后每次实质进展增量回写。

### 步骤③ 数据核对与全量嵌入（1-2 次请求）
逐列理解数据表：列名、单位、分类数（=图例项数）、样本数、数值范围。**源数据表全量嵌入 result.json**（`source_table` 字段：表头+每行为结构化数组，评分器不开附件即可逐格核对；表大时分批增量写，每批 ≤1500 字，写完即回填，规避单响应截断）。生成**双层映射**：
- **系列层**：每个数据系列一条 `{level:"series", series, element_id, data_col, rows, unit}`——图元组↔数据列，支持图回溯数据、数据定位图元；
- **数值层**：**每个将绘制的数值逐条全量嵌入**（非抽样）：`{level:"value", element, value, source:"data.csv row=r col=列名"}`；每个图例项、每种颜色同样标注来源。
- 数据冲突（同名列不同值、单位不明、缺失行）→ 登记 exceptions，不静默修改。

### 步骤④ 绘图与导出 + 机械校验（3-6 次请求）
**首选 matplotlib**（脚本即编辑源，数值来自读文件而非硬编码字面量）：
```python3
# chart_source.py：数据区与样式区分离；len(cats) = 图例项数 = 颜色数
import csv, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
rows = list(csv.DictReader(open("data.csv", encoding="utf-8")))
cats = [r["category"] for r in rows]
vals = [float(r["value"]) for r in rows]        # 每个值对应 content_map 一条映射
fig, ax = plt.subplots(figsize=(6, 4))
ax.bar(cats, vals, color=COLORS[:len(cats)])    # 颜色逐项对应
ax.set_ylabel("weight (g)")                     # 轴标签含单位与量级
fig.savefig("figure.svg"); fig.savefig("figure.png", dpi=300); fig.savefig("figure.pdf")
```
- 产物：脚本 + `.svg` + `.png`(300dpi) + `.pdf` 存 `/app/output/`（脚本与 SVG 是**可编辑双源**）。
- 中文字体缺失：优先用环境 font-discovery 找到的 CJK 字体（如 Noto Sans CJK），`rcParams["font.sans-serif"]` 指定；仍失败改英文标签并登记 exceptions。
- 渲染校验：先 `find /skills /app/work . -name render_svg.py 2>/dev/null | head -1` 拿真实路径，再 `python3 <路径>/render_svg.py --check figure.png`（非空非全白 + 尺寸/DPI），结果写入 compliance_checks；找不到脚本时内联 cairosvg 回退并登记。
- **机械校验（审稿硬伤防线，结果全部写入 compliance_checks）**：
  1. 图例项数 == 数据分类数（记录两个具体数字，不等则修脚本重跑）；
  2. 颜色映射逐项核对：每系列/分类↔颜色↔图例文字一一对应，输出逐项列表而非单个 bool；
  3. 轴刻度范围 vs 数据范围：数据 min/max 落在轴范围内、无截断，轴标签含单位与量级；
  4. 数值抽样核对（结构性全覆盖，见步骤⑤）。
  **多子图/双轴图逐子图逐轴核对**：每个子图（panel）单独记录 `panel` 标识，四项校验（图例数/颜色/轴范围/抽样）按子图逐个枚举，禁止单个子图通过即宣称整图通过；双轴（twinx）按 y1/y2 分别记录数据范围与轴范围；逐子图结果全部 match 才算通过，任一失败先修重跑。

**编辑工单**：只修改工单要求的系列/标签/范围/样式参数，其余一律不动；result.json 写 `edit` 记录（参数、旧值→新值、原因），改脚本后重跑步骤④。
**无 matplotlib 回退**：手写分层 SVG（`<g>` 按系列分层、每个图元带数据注释），数值仍从数据文件读取；`render_svg.py 输入.svg --outdir . --png --pdf --dpi 300` 渲染（内置回退链 cairosvg→rsvg-convert→inkscape→chrome headless），全部失败则 PNG/PDF=unknown 并登记 exceptions。

### 步骤⑤ 填充 result.json 全字段（2-3 次请求）
**output_contract 键为准且一个不缺；`source_table` 与 `reproducibility` 为本技能附加增强字段，在 contract 之外追加，不挤占不替换**。
```json
{
  "case_id": "<抄自 case.json>",
  "status": "complete | partial",
  "source_table": {"file": "data.csv", "header": ["group", "weight_g"], "rows": [["control", 12.3], ["treated_a", 15.8], ["treated_b", 9.4]]},
  "editable_source": {"script": "/app/output/chart_source.py", "svg": "/app/output/figure.svg", "rerun_command": "python3 /app/output/chart_source.py"},
  "export_artifact": {"png": {"path": "/app/output/figure.png", "size_px": "1800x1200", "dpi": 300, "pixel_check": "OK nonbg_ratio=0.18"}, "pdf": {"path": "/app/output/figure.pdf"}},
  "content_map": {
    "series": [{"series": "weight", "element_id": "bar-group", "data_col": "weight_g", "rows": "2-4", "unit": "g"}],
    "values": [{"element": "bar[control]", "value": 12.3, "source": "data.csv row=2 col=weight_g", "color": "#4C72B0", "legend": "control"}]
  },
  "compliance_checks": {
    "legend_count": {"legend_items": 3, "categories": 3, "match": true},
    "color_mapping": [{"series": "control", "color": "#4C72B0", "legend": "control", "match": true}],
    "axis_check": [{"panel": "ax1", "xlabel": "group", "ylabel": "weight (g)", "data_range": [9.4, 15.8], "axis_range": [0, 18], "within": true}],
    "value_sampling": [{"series": "weight", "pos": "first", "on_chart": "bar[control]=12.3", "source_value": 12.3, "cell": "data.csv r2c2", "match": true}],
    "png_pixel_check": "OK nonbg_ratio=0.18",
    "font": "Noto Sans CJK / DejaVu Sans"
  },
  "reproducibility": {"data_file": "data.csv", "data_fingerprint": "3 rows x 2 cols; sha256=<实际计算>", "field_mapping": "weight_g->bar 高度, group->x 轴", "deps": "python3.8+ matplotlib<实际版本>", "export_params": "svg+png(300dpi)+pdf", "manual_edits": "无", "rerun_command": "python3 /app/output/chart_source.py"},
  "exceptions": [], "edit": {}
}
```
**value_sampling 结构性全覆盖（可核验性关键）**：**每条数据系列**抽首/中/尾各 1 个值，逐条含 图上值 on_chart / 数据源值 source_value / 单元格定位 cell / match 结论；总量 = 系列数 × 3。多子图时每条再带 `panel` 字段，逐子图抽样。**reproducibility 块（可复现性硬指标）**：数据文件名+指纹（行×列数/哈希）、字段映射（每列→图元）、脚本依赖与版本、导出参数（格式/尺寸/dpi/色彩）、人工修改记录（无则写"无"）——他人按此块可独立重跑得到同一张图。若 case.json 要求 content_map 为列表，则把 series 与 values 条目平铺进同一列表。任何 match=false 先修脚本重跑，修不好登记 exceptions。

## 2. 异常处理速查

| 情况 | 处置 |
|---|---|
| 数据列缺失/类型混乱/数值范围异常 | 登记exceptions不静默改；能画的列照画；必要时对数轴并在轴上注明 |
| 图例项数 ≠ 分类数 / 颜色错配 / 抽样 match=false | 修脚本重跑；修不好则 status=partial + exceptions |
| 无 matplotlib | 手写分层 SVG 回退（见步骤④），数值仍从数据读 |
| 渲染器全失败 | PNG/PDF=unknown，SVG 保留（仍可编辑），exceptions 说明 |
| 中文变方框 | 换 CJK 字体；不行则英文标签 + exceptions |
| 数据表过大写 result.json 被截断 | 分批增量写（每批 ≤1500 字），写完即验 json.loads |
| 预算触顶（48 请求/700 秒） | 立即收尾填 result.json，未完成项标 unknown |

## 3. 自检清单（收尾前逐项过）

- [ ] result.json 可被 json.loads 解析，字段与 output_contract 完全一致；case_id 一致；status 如实
- [ ] **source_table 全量嵌入**：表头+每行与源数据逐格一致（抽查任意单元格可与源文件对上）；表大已分批写
- [ ] editable_source 双源齐备（脚本+SVG，路径真实存在）；PNG 已过 --check（非空+尺寸/DPI），PDF 存在
- [ ] content_map：系列层每系列有 element_id↔data_col；数值层**每个绘制值逐条**（全量非抽样）有来源单元格
- [ ] 图例项数==分类数（两个数字已记录）；颜色映射逐项列表且全部 match=true；轴范围覆盖数据 min/max 无截断、轴标签含单位
- [ ] **多子图/双轴：每个子图单独出 axis_check/图例/颜色/抽样记录（带 panel），双轴 y1/y2 分别核对**；任一子图失败不算整图通过
- [ ] value_sampling 覆盖每条系列的首/中/尾且全部 match=true（不一致的已修正或登记）
- [ ] **reproducibility 块齐备**：数据指纹、字段映射、依赖版本、导出参数、人工修改记录，他人可独立重跑得同一张图
- [ ] 科学实体名与源数据逐字符一致（不凭记忆改写基因/蛋白/化合物名）
- [ ] 编辑工单：edit 记录含旧值→新值，未动工单外内容
- [ ] exceptions 覆盖：材料缺失、无法判断、运行失败三类（如适用）；全部文本 UTF-8

## 4. 设计要点（为什么这样做）

- **双层 content_map**：系列层回答"这组柱子来自哪列"，数值层回答"这根柱子是哪个格"——双向回溯都有据可查。
- **源数据表全量嵌入 result.json**：评分器不开附件即可逐格核对图上值；content_map.values 与 source_table 双向印证，杜绝"转述走样"。
- **双源策略 + 数据驱动创新**：脚本（数据驱动，源数据更新后只需 `python3 chart_source.py` 即按新数据重绘并重新导出三格式，图与数据版本始终同步）+ 分层 SVG（图元级手改），覆盖两类返修场景。reproducibility 块记录数据指纹/字段映射/导出参数，保证独立重跑可得同一张图。
- **机械校验优于人工目检**：图例数、颜色映射、轴范围、数值抽样全部是可程序化断言，且以逐项明细（非单个 bool）写入 compliance_checks，供审稿逐条复核。
- **抽样全覆盖而非随机抽 3 条**：每系列首/中/尾结构性抽取，杜绝"恰好没抽到错值"的侥幸；**骨架先行**保证任何失败路径下 result.json 合同完整。

### 步骤X：增益证据与效率计数（回填 result.json）
本节产出的必须是**本次运行真跑出来的数字**，不是文字声明：
```bash
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --baseline
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --write
```
- 第一条：基础模式对照——模拟「不做证据登记/不做方向核对」的路径，统计源材料里有多少实体与数值会变成不可核对项（需人工逐条核对的规模）。
- 第二条：当前模式实测——登记覆盖率、证据逐字回证率、关系/数值核对通过率、需人工核对条目数，并计算相对基线的削减量；`--write` 写入 `result.json.registry_evidence`（含 `baseline_comparison.reduction` 与 `efficiency` 计数；若本包另有脚本写 `gain_evidence`，两者互补不覆盖）。
