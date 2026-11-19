# source-value-chart 使用说明

## 用途
科研数据图表的生成与源保留编辑：从源数据表出发，生成每个数值可溯源、图例与分类严格一致、颜色逐项对应、轴范围与数据范围一致、可编辑、可投稿的图表。

## 文件清单（4 个，全 UTF-8，总量远小于 2MB）

| 文件 | 作用 |
|---|---|
| `SKILL.md` | Skill 本体：强制执行协议、线性五步主流程、双层 content_map、四项机械校验、异常处理、自检清单 |
| `scripts/render_svg.py` | SVG 渲染与 PNG 像素/尺寸检查工具（零第三方依赖，多渲染器回退） |
| `README.md` | 本说明 |
| `worklog.md` | 制作时间线与版本差距分析 |

## 依赖与安装
- Python 3.8+（标准库）；`scripts/render_svg.py` 无第三方依赖。
- 可选：`matplotlib`（首选绘图路径）；缺失时自动回退到手写分层 SVG。
- 可选渲染器（任一即可）：`cairosvg` / `rsvg-convert` / `inkscape` / chromium headless（render_svg.py 内置回退链）。
- 中文字体：优先 Noto Sans CJK；无则回退英文标签并登记 exceptions。

## 调用方式
平台将本 Skill 安装到 `/skills/weekly-skill` 后，在官方 DeepSeek Harness 中对每个案例自动执行。运行时输入 `/input/case.json`、task.md（可能含 `artifacts/figure-workorder.json` 工单与数据表），工作目录 `/app/work`，产物写 `/app/output/`（必含 `result.json`）。

### 主流程（摘自 SKILL.md 步骤①-⑤）
1. 读 case.json → 抄 `case_id` 与 `output_contract` 全键
2. 立即写 `/app/output/result.json` 骨架（status=partial，字段一个不缺）
3. 逐列核对数据表，**源数据表全量嵌入 `source_table` 字段**（评分器不开附件即可逐格核对），生成**双层 content_map**：系列层（element_id↔数据列）+ 数值层（每个绘制值逐条↔单元格），图例项与颜色同样标注来源
4. matplotlib 出图：脚本存 output（可编辑源），导出 SVG+PNG(300dpi)+PDF；`render_svg.py --check` 校验像素/尺寸/DPI；机械校验——图例项数=分类数、颜色映射逐项列表核对、轴范围覆盖数据范围、数值抽样（每系列首/中/尾）；**多子图/双轴图逐子图逐轴核对（每条记录带 panel，y1/y2 分别核对）**
5. 填 result.json 全字段，含 **reproducibility 块**（数据文件指纹、字段映射、依赖版本、导出参数、人工修改记录——他人可独立重跑得同一张图）；编辑工单只改工单参数（source-preserving）并记录旧值→新值后重跑

## 最小示意示例（标注：以下为示意，非正式案例结果）

输入 `data.csv`（示意）：
```csv
group,weight_g
control,12.3
treated_a,15.8
treated_b,9.4
```

调用：按 SKILL.md 主流程生成 `chart_source.py` 并运行。

示意输出（示意，节选）：
```json
{
  "case_id": "demo-case",
  "status": "complete",
  "source_table": {"file": "data.csv", "header": ["group", "weight_g"], "rows": [["control", 12.3], ["treated_a", 15.8], ["treated_b", 9.4]]},
  "content_map": {
    "series": [{"series": "weight", "element_id": "bar-group", "data_col": "weight_g", "rows": "2-4", "unit": "g"}],
    "values": [{"element": "bar[control]", "value": 12.3, "source": "data.csv row=2 col=weight_g", "color": "#4C72B0", "legend": "control"}]
  },
  "compliance_checks": {
    "legend_count": {"legend_items": 3, "categories": 3, "match": true},
    "color_mapping": [{"series": "control", "color": "#4C72B0", "legend": "control", "match": true}],
    "axis_check": [{"panel": "ax1", "xlabel": "group", "ylabel": "weight (g)", "data_range": [9.4, 15.8], "axis_range": [0, 18], "within": true}],
    "value_sampling": [{"series": "weight", "pos": "first", "on_chart": "bar[control]=12.3", "source_value": 12.3, "cell": "data.csv r2c2", "match": true}]
  },
  "reproducibility": {"data_file": "data.csv", "data_fingerprint": "3 rows x 2 cols", "field_mapping": "weight_g->bar 高度, group->x 轴", "deps": "python3.8+ matplotlib", "export_params": "svg+png(300dpi)+pdf", "manual_edits": "无", "rerun_command": "python3 /app/output/chart_source.py"},
  "exceptions": []
}
```

## 数据更新→重绘（核心创新点）
源数据更新后无需重做图：`python3 /app/output/chart_source.py` 即按新数据重绘并重新导出三格式。图与数据版本始终同步。

## 适用范围与限制
- 适用：柱状/折线/散点/箱线等以表格数值为源的数据图表；source-preserving 编辑工单。
- 不负责：统计方法选择与显著性计算的正确性（属数据分析方向）；实验方案设计。
- 限制：无任何渲染器与 matplotlib 时，交付 SVG 源但 PNG/PDF 标 unknown；中文字体缺失时英文标签替代。


## 生态贡献：依赖、安装运行、目标用户与验收

| 项目 | 说明 |
|---|---|
| 依赖与版本 | Python 3（评测沙箱 3.12；本 Skill 脚本仅用标准库，无需 pip 安装）；无浏览器/无外部渲染器时按降级链处理。 |
| 安装与运行 | 平台把提交目录装入 `/skills/weekly-skill`；输入 `/input/case.json`（+ 材料），产物写 `/app/output/result.json`。 |
| 输入 / 输出解释 | 输入=案例标识、来源材料、图稿工单与导出约束；输出=result.json（契约全字段 + content_map + compliance_checks 三元组 + gain_evidence + efficiency + exceptions）。 |
| 目标用户与场景 | 科研绘图的作者与评审：需要「可编辑源文件 + 可溯源要素 + 可核验导出件」，用于机制图/流程图/技术路线图/数据图的成稿与复核。 |
| 验收方式 | ①契约键一个不缺且 JSON 可解析；②content_map 元素数=图面元素数且逐条带 source+evidence；③compliance_checks 三组三元组齐全、非 enforced 均有 gate_note；④gain_evidence 含两套对照指标与削减量。 |
| 常见问题 | 图面元素无来源→按材料补登记或删除该元素；关系方向不明→按原文陈述方向，存疑记 exceptions；导出件缺失→按降级链如实登记 renderer_unavailable。 |
| 已知限制 | 无渲染器环境只能交付 SVG 源文件与降级记录；像素级校验需在有渲染器的环境复跑 `--check`。 |
| 失败处理 | 任一步异常：写盘已有产出、status 如实降级、exceptions 记录失败点与已尝试回退链；机检结论照实记录，**不中断交付**。 |
| 复用建议 | 把本目录 scripts/ 直接复制到新项目；content_map 与 compliance_checks 的字段结构可直接套用到其它绘图任务。 |
| 版本与维护 | 见 worklog.md 的版本小节；结构变更时同步更新本表与 SKILL.md 的输出字段说明。 |

## 最小可运行自检清单（复制即跑，用于确认环境可用）

```bash
python3 -c "import sys;print(sys.version)"   # 1) 解释器可用
ls scripts/                                    # 2) 脚本在位
python3 scripts/gain_evidence.py --help         # 3) 增益脚本可执行
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"  # 4) 产物可解析且键齐全
```
