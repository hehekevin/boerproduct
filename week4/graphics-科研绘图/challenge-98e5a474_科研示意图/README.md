# scientific-schematic-generator

科研示意图生成与编辑 Skill：从来源材料生成或编辑分层可编辑 SVG 示意图，并导出 PNG(300dpi)/PDF，全部图面元素可溯源。

## 文件清单

| 文件 | 作用 |
|---|---|
| `SKILL.md` | Skill 本体：强制执行协议 + 线性五步主流程 + 异常处理 + 自检清单 |
| `scripts/render_svg.py` | SVG 渲染导出工具：多渲染器回退（cairosvg → rsvg-convert → inkscape → chromium headless）+ PNG 像素校验，仅用 Python 标准库 |

## 依赖与安装

- Python 3.x（仅标准库即可运行 `render_svg.py`；若环境已装 `cairosvg` 则自动优先使用）。
- 无需其他安装步骤，无字体依赖（SVG 使用通用字体栈 `Helvetica, Arial, sans-serif`，缺失时浏览器/渲染器自动回退）。

## 调用方式

平台把本 Skill 安装至 `/skills/weekly-skill` 后，由 Harness 在每个固定案例上执行：

1. 输入：`/input/case.json`、`task.md`、绘图工单与来源材料（文本/表格/PDF）。
2. 工作目录 `/app/work`；最终产物写入 `/app/output/`，包括 `result.json`（含 `output_contract` 全部字段与 `case_id`）、分层 SVG 源文件、PNG/PDF 导出件。

## 最小调用示例（示意输出，非正式案例结果）

```bash
# 渲染导出（新建或编辑后的 SVG）
python3 scripts/render_svg.py work/figure.svg --outdir /app/output --png --pdf --dpi 300
# PNG OK: /app/output/figure.png {"width": 1654, "height": 2339, "sampled": 10000, "nonbg_ratio": 0.184}
# PDF OK: /app/output/figure.pdf

# 像素校验（非空图、尺寸>0）
python3 scripts/render_svg.py /app/output/figure.png --check
# CHECK OK {"width": 1654, "height": 2339, ...}
```

`result.json` 示意结构（字段以案例 `output_contract` 实际声明为准）：

```json
{
  "case_id": "<与 case.json 一致>",
  "status": "complete",
  "editable_source": {"path": "/app/output/figure.svg", "layers": "g-stage/g-entity/g-rel/g-legend", "edit_record": []},
  "export_artifact": {"png": "/app/output/figure.png", "pdf": "/app/output/figure.pdf", "dpi": 300,
    "render_evidence": "PNG OK: /app/output/figure.png {'width': 1654, ...}\nCHECK OK {'width': 1654, ...}"},
  "content_map": [{"element_id": "g-entity-A", "type": "entity", "label": "...", "source": "materials.pdf p.3", "evidence": "原文摘录≤30字"}],
  "compliance_checks": {
    "relation_checks": {"gate": "enforced", "items": [
      {"item": "A抑制B", "template_value": "A inhibits B (materials.pdf p.3)", "applied": "T型阻断端 A⊣B", "match": true}]},
    "entity_checks": {"gate": "enforced", "items": [
      {"item": "g-entity-A", "template_value": "Protein A", "applied": "Protein A", "match": true}]},
    "export_checks": {"gate": "enforced", "items": [
      {"item": "dpi", "template_value": "300", "applied": "300", "match": true}]}
  },
  "exceptions": []
}
```

闸门 `gate` 状态只取 `enforced / skipped_not_provided / not_found / unreadable`；非 `enforced` 必须加 `warn:true` 与 `gate_note:"下游不得宣称已核对"`。

## 适用边界

- 适用：科研流程图、结构关系图、机制通路图、概念示意图的生成与编辑（含对现有 SVG 的 source-preserving 修改）。
- 不适用：统计图表的数值计算与统计方法选择、海报/封面版式设计、艺术插画、论文正文写作。

## 异常处理摘要

渲染器全部不可用时仍交付分层 SVG 作为可编辑源文件，`export_artifact` 标记 `unavailable`，`exceptions` 记录已尝试的回退链；来源缺失/矛盾时缺失实体不画、矛盾双证据登记；`status` 始终如实（`complete`/`partial`/`failed`），任何情况下 `result.json` 都会落盘。


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
