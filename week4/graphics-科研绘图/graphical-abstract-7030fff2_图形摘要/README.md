# graphical-abstract-builder 使用说明

## 用途
从论文材料生成期刊风格单图图形摘要（标题区 + 要点区 + 中心概念示意 + 图例，阅读顺序按"背景→方法→结果→结论"分区），或对已有图稿做 source-preserving 编辑。交付分层可编辑 SVG 源文件、PNG(300dpi)/PDF 导出件与全字段 result.json；机检对账（三元组 + 闸门状态）由脚本生成并原样内嵌，全程可溯源、可复跑。

## 文件清单
| 文件 | 作用 |
|---|---|
| `SKILL.md` | Skill 本体：7 条强制协议 + 线性五步流程 + 异常处理 + 自检清单 |
| `scripts/render_svg.py` | SVG→PNG/PDF 渲染（内置渲染器回退链）+ PNG 像素校验 |
| `scripts/svg_audit.py` | SVG 机检对账：画布/字号下限/纯 text 元素/图层/视觉动线分区/溢出扫描/编辑 diff，逐项产出 `{item, template_value, applied, match}` 三元组 + `gate` 显式状态（enforced/skipped_not_provided/not_found/unreadable），fail 冒泡退出码 |
| `README.md` | 本文件 |

## 依赖与安装
- Python 3（render_svg.py 与 svg_audit.py 均纯标准库，零第三方依赖）。
- 可选渲染后端（按可用性自动选择，无需手工配置）：cairosvg → rsvg-convert → inkscape → chromium/chrome headless。
- 平台安装：Skill 目录装载于 `/skills/weekly-skill`；运行时脚本用 `find /skills /app -name '<脚本名>'` 动态定位（SKILL.md 协议第 4 条），不依赖固定路径。

## 调用方式（Agent 视角）
1. 读 `/input/case.json` → 逐键抄录 `output_contract` 与 `case_id`；定位工单（`ls -R /input` + case.json 内嵌字段）。
2. 立即写 `/app/output/result.json` 骨架（全键 + `status="partial"`），此后每次回写前做 JSON 自检。
3. 从论文摘要/结论/图注提炼 `content_map` + `evidence_map`（每元素带 ≤40 字逐字 quote 与 location；数字必须逐字回证），生成四图层 + `data-zone` 分区的 SVG（分批写入）。
4. 渲染导出：`python3 render_svg.py work/ga.svg --outdir /app/output --png --pdf --dpi 300`，再 `--check` 校验像素。
5. 机检对账：`python3 svg_audit.py work/ga.svg --canvas 1200x600 --zones background,method,result,conclusion [--baseline 原稿.svg] --out svg_audit.json`；`match:false` 必须修图重跑；`svg_audit.json` **原样内嵌** result.json。
6. 填全 result.json 并自检（键集合、case_id、numeric_unbacked 为空、gates 无未解释 skipped、status 如实四级）。

## 输入 / 输出
- 输入：`/input/case.json`、task.md、论文材料（PDF/文本）、（若有）figure-workorder。
- 输出（`/app/output/`）：分层 SVG（可编辑源，文字全为 `<text>`，`data-zone` 分区标注）、`*.png`（300dpi，`--check` 通过）、`*.pdf`、`result.json`（键集合与 case.json 的 output_contract 完全一致；内嵌 svg_audit 三元组、evidence_map、visual_flow 分区登记、编辑 diff）。

## 最小示意示例（仅为接口示意，非正式案例结果）
```bash
python3 scripts/svg_audit.py work/ga.svg --canvas 1200x600 \
    --zones background,method,result,conclusion --out work/svg_audit.json
# → {"checks":{"canvas":{"match":true,...},"font_floor":{"violations":[],"match":true,...},
#    "overflow":{"suspects":[],"match":true,...},"edit_diff":{"gate":"skipped_not_provided",...}},
#    "summary":{"fail":0,"gates":{...}}}   # 退出码 0
```
注：实际 result.json 字段名以 case.json 的 `output_contract` 原样声明为准，上例键名不构成契约。

## 本地双测证据（作者机，Python 3.13）
- 正例（合规 SVG）：`AUDIT fail=0`，退出码 0，闸门 canvas/font_floor/text_edit/layers/visual_flow/overflow=enforced，edit_diff=skipped_not_provided。
- 反例（注入脏数据：画布 1000≠1200、12px 字号、`<image>` 标签、缺 2 个图层、缺 data-zone、溢出文字）：9 项 fail 全部命中，退出码 1（fail 冒泡）。
- 编辑 diff：对正例删除元素 p2 后以 `--baseline` 复检 → `removed:['p2']` 被抓、preserved=10、退出码 1。

## 限制与失败处理
- 材料仅摘要可用 → 降级提炼，exceptions 登记 `abstract-only`。
- 渲染全链失败 → 保留 SVG、status=partial、登记 `render-failed`，仍写出全字段 result.json（本机双测即触发该路径：无渲染后端时回退链如实失败，不伪造 PNG）。
- 材料之外的数据（数值、实体、结论）一律不上图；unbacked 数字逐条列出。
- 维护：修改渲染逻辑只动 `scripts/render_svg.py`；修改机检规则只动 `scripts/svg_audit.py`；修改流程规则只动 `SKILL.md`；三文件行数分别控制在 200/280/150 行内以便审阅。


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
