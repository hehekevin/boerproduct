# graphical-abstract-builder 使用说明

## 用途
从论文材料生成期刊风格单图图形摘要（标题区 + 要点区 + 中心概念示意 + 图例），或对已有图稿做 source-preserving 编辑。交付分层可编辑 SVG 源文件、PNG(300dpi)/PDF 导出件与全字段 result.json，全程可溯源。

## 文件清单
| 文件 | 作用 |
|---|---|
| `SKILL.md` | Skill 本体：强制协议 + 线性五步流程 + 异常处理 + 自检清单 |
| `scripts/render_svg.py` | SVG→PNG/PDF 渲染（内置渲染器回退链）+ PNG 像素校验 |
| `README.md` | 本文件 |

## 依赖与安装
- Python 3（仅标准库即可运行 render_svg.py 的像素校验与浏览器回退）。
- 可选渲染后端（按可用性自动选择，无需手工配置）：cairosvg → rsvg-convert → inkscape → chromium/chrome headless。
- 平台安装：Skill 目录装载于 `/skills/weekly-skill`；运行时脚本用 `find /skills /app -name render_svg.py` 动态定位（SKILL.md 协议第 3 条），不依赖固定路径。

## 调用方式（Agent 视角）
1. 读 `/input/case.json` → 逐键抄录 `output_contract` 与 `case_id`；定位工单（`ls -R /input` + case.json 内嵌字段）。
2. 立即写 `/app/output/result.json` 骨架（全键 + `status="partial"`）。
3. 从论文摘要/结论/图注提炼 content_map（每元素带出处），生成四图层 SVG（分批写入）。
4. `python <render_svg.py> work/ga.svg --outdir /app/output --png --pdf --dpi 300`，再 `--check` 校验像素。
5. 填全 result.json 并自检（键集合、case_id、字号下限、溯源、status 如实）。

## 输入 / 输出
- 输入：`/input/case.json`、task.md、论文材料（PDF/文本）、（若有）figure-workorder。
- 输出（`/app/output/`）：分层 SVG（可编辑源，文字全为 `<text>`）、`*.png`（300dpi，`--check` 通过）、`*.pdf`、`result.json`（键集合与 case.json 的 output_contract 完全一致）。

## 最小示意示例（仅为接口示意，非正式案例结果）
输入：一篇论文 PDF + 工单（画布 1200×600，新建图）。
示意输出：
```
/app/output/ga.svg          # layer-title / layer-points / layer-visual / layer-legend
/app/output/ga.png          # 300dpi，CHECK OK nonbg_ratio>0.01
/app/output/ga.pdf
/app/output/result.json     # {"case_id":"...","status":"complete","editable_source":...,
                            #  "export_artifact":[...],"content_map":[...],
                            #  "compliance_checks":[...],"exceptions":[]}
```
注：实际字段名以 case.json 的 `output_contract` 原样声明为准，上例键名不构成契约。

## 限制与失败处理
- 材料仅摘要可用 → 降级提炼，exceptions 登记 `abstract-only`。
- 渲染全链失败 → 保留 SVG、status=partial、登记 `render-failed`，仍写出全字段 result.json。
- 材料之外的数据（数值、实体、结论）一律不上图。
- 维护：修改渲染逻辑只动 `scripts/render_svg.py`；修改流程规则只动 `SKILL.md`；两文件行数分别控制在 200/130 行内以便审阅。
