# pathway-figure-skill 使用说明

把一份真实机制材料变成**可回溯、可编辑、可导出**的生物通路图。所有实体与关系只来自输入材料，方向经逐条核对，不编造任何名字或调控方向。

## 文件清单

| 文件 | 作用 |
|---|---|
| `SKILL.md` | Skill 本体：强制执行协议 + 线性五步流程 + 异常处理 + 自检清单 |
| `scripts/render_svg.py` | SVG 渲染导出与像素校验（多渲染器回退，零第三方依赖也能跑） |
| `templates/relation-checklist-template.md` | 通路关系核对表模板（步骤3 的逐条比对记录载体） |

## 依赖与安装

- Python 3.8+（仅标准库）。
- 渲染器按优先级自动探测：`cairosvg`(pip 可选) → `rsvg-convert` → `inkscape` → chromium/chrome headless。任一可用即可导出 PNG+PDF；全缺失时 SVG 仍可交付，导出缺口登记在 `exceptions`。
- 无需其他配置，路径均相对运行目录。

## 调用步骤（最小流程）

1. 读 `/input/case.json`，抄 `case_id` 与 `output_contract` 全键；读工单与来源材料。
2. 立即写 `/app/output/result.json` 骨架（全键 + `status:"partial"`）。
3. 按 `templates/relation-checklist-template.md` 逐条抽取实体与相互作用，填证据（来源位置+原文摘录），执行方向核对。
4. 写分层 SVG → 导出：
   ```bash
   python scripts/render_svg.py figure.svg --outdir /app/output --png --pdf --dpi 300
   python scripts/render_svg.py /app/output/figure.png --check
   ```
5. 填全 result.json（content_map / compliance_checks / exceptions / status），做 JSON 自检。

## 输入输出

- **输入**：`case.json`（含 case_id、output_contract）、task.md、来源材料（论文正文/图注/数据文件）、可选 `artifacts/figure-workorder.json` 编辑工单。
- **输出**：`/app/output/` 下 `figure.svg`（分层可编辑源文件）、`figure.png`(300dpi)、`figure.pdf`、`result.json`（含 content_map 证据链与 compliance_checks 核对记录）。

## 最小示意示例（标注：以下为示意，非正式案例结果）

输入材料一句原文：「EGF 激活 EGFR，EGFR 磷酸化 STAT3；STAT3 促进 MYC 转录，而 SOCS3 抑制 STAT3 通路。」

核对表产出（节选）：

| 原文 | 类型 | 方向 |
|---|---|---|
| EGF 激活 EGFR | 激活 | EGF → EGFR |
| EGFR 磷酸化 STAT3 | 磷酸化 | EGFR -P→ STAT3 |
| STAT3 促进 MYC 转录 | 转录调控 | STAT3 → MYC |
| SOCS3 抑制 STAT3 | 抑制 | SOCS3 ⊣ STAT3 |

示意 SVG 结构（节选，完整图由流程生成）：

```xml
<g id="compartment-extracellular"><text>ECF zone</text>
  <g id="entity-EGF"><text>EGF</text></g></g>
<g id="compartment-membrane">
  <g id="entity-EGFR"><text>EGFR</text></g></g>
<g id="compartment-cytoplasm">
  <g id="entity-SOCS3"><text>SOCS3</text></g>
  <g id="edge-EGFR-activates-STAT3"><path marker-end="url(#arrow)"/><text>P</text></g>
  <g id="edge-SOCS3-inhibits-STAT3"><line marker-end="url(#tbar)"/></g></g>
<g id="compartment-nucleus">
  <g id="entity-MYC"><text>MYC</text></g></g>
<g id="legend"><!-- → 激活 / ⊣ 抑制 / -P→ 磷酸化 --></g>
```

导出后 `--check` 返回 `CHECK OK {"width":..., "nonbg_ratio":>0.01}` 即像素校验通过。

## 适用范围与限制

- 适用：受体/激酶/转录因子类线性、分支、反馈环通路；新建图与 source-preserving 编辑两类工单。
- 不负责：数值统计结论、实验方案、论文版式美化（相邻课题承担）。
- 限制：材料未提及的实体/关系一律不画；方向模糊时取最保守画法并登记 exceptions；不产出预制作答。

## 维护

- 关系语义约定、SVG 分层 id 规范集中定义在 SKILL.md，修改只需改该文件。
- render_svg.py 为独立工具，可被其他绘图任务复用。
