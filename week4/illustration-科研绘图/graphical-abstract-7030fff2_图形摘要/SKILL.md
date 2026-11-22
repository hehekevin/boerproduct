---
name: graphical-abstract-builder
description: >
  Build journal-style Graphical Abstracts (single-figure "question→method→
  result→conclusion" summaries) from provided source materials, or perform
  source-preserving edits on an existing figure. Produces a layered, fully
  text-editable SVG plus real PNG (300dpi) + PDF exports with pixel checks,
  and a result.json whose keys are copied verbatim from the case's
  output_contract. Every element in content_map is traceable to the source
  (abstract sentence / conclusion / figure number); fabrication is forbidden.
---

# Graphical Abstract Builder（图形摘要构建 Skill）

把论文材料变成一张期刊风格的单图图形摘要，或按工单对已有图稿做保源编辑。核心纪律：**图中每个实体、数值、结论都必须能追到来源材料原文；追不到就不画。**

## 强制执行协议（最高优先级，覆盖一切其他规则）

1. **先抄契约再动手**：读完 `/input/case.json` 后，**逐键原样抄录** `output_contract` 声明的全部字段键名（不增不减不排序）与真实 `case_id`。字段名一律以 case.json 实际内容为准，禁止凭本文件示例臆造。
2. **立即落骨架**：抄完契约立刻写 `/app/output/result.json` 骨架：全部契约键 + `status="partial"`，暂无法产出的字段填 `"unknown"` 或 `[]`。此后每次实质进展增量回写；任何时候 result.json 都是可解析的合法 JSON。
3. **路径不臆测**：工单与脚本位置不固定——先 `ls -R /input` 并检查 case.json 内嵌字段定位工单；用 `find /skills /app -name render_svg.py 2>/dev/null | head -1` 动态定位渲染脚本（找到什么用什么，禁止写死任何作者本地路径）。
4. **分批写长文件**：SVG 与 result.json 都先写骨架、再逐层/逐字段充实，单次写入不超过 200 行，避免超长输出被截断产生半截文件。
5. **预算熔断**：模型请求超过 48 次（上限 64）或运行超过 700 秒（上限 900）立即停止新步骤收尾；**任何失败（渲染失败、材料缺失、熔断）都必须写出含全字段与 exceptions 的 result.json**，`status` 如实取 `complete`/`partial`/`failed`。

## 线性五步主流程

### 步骤① 读输入，抄契约
- 读 `/input/case.json`：抄 `case_id` + `output_contract` 全键（原样）。
- 定位并读工单（如 `artifacts/figure-workorder.json`，可能内嵌于 case.json）：画布尺寸/比例、目标格式、是**新建图**还是**编辑工单**（source-preserving edit）、组织方修订注记（如 `graphical_abstract`、主生物来源对应 figure03）。
- 读论文材料（PDF/文本）：重点读**摘要、结论、主图图号与图注**。以实际文件内容为准，不依据标签臆测。记录题名、材料清单、缺失项（供步骤⑤登记）。

### 步骤② 落 result.json 骨架
按协议第 2 条立即写盘。写前自检：JSON 可解析、契约键一个不缺、case_id 一致。

### 步骤③ 提炼信息，生成 content_map（禁止编造）
- **一句话核心结论**：取自摘要或结论原句，作标题区副标题。
- **3–4 个关键要点**：每条 ≤12 词，按"问题→方法→核心结果→结论"排序，逐条标注出处（摘要第 N 句 / 结论段 / Figure N）。
- **一个中心视觉概念**：把方法/机制简化为流程示意（实体用论文明确写出的名字；箭头方向以原文因果为准；只用论文描述过的实体与关系）。
- 生成 `content_map`：每个要点/视觉元素一条记录 `{element, text, source, svg_layer}`；**content_map 找不到出处的内容一律不上图**。

### 步骤④ 写分层 SVG 并真实渲染
在 `/app/work` 写 SVG（先骨架后逐层充实，见协议第 4 条），四个图层（各为带语义 id 的 `<g>`）：
1. `layer-title`：论文短标题，大字号（1200 宽画布下 ≥34px）。
2. `layer-points`：3–4 个短句要点 + 编号图标。
3. `layer-visual`（约占 55% 面积）：中心概念示意——圆角矩形/圆形实体 + `marker` 箭头，流向左→右或上→下，不交叉。
4. `layer-legend`：图例说明图面用到的每种颜色/箭头含义。

硬性规则：文字全部用 `<text>` 元素（不转曲、不栅格化）；要点字号 ≥20px、图内标注 ≥16px；外边距 ≥40px；文字不溢出边界；同一含义只用一种颜色，避免纯红绿对。

**渲染**（脚本路径按协议第 3 条动态定位）：
```bash
python <render_svg.py> work/ga.svg --outdir /app/output --png --pdf --dpi 300
python <render_svg.py> /app/output/ga.png --check
```
`CHECK OK`（非空、非全白）才算通过。渲染是单点步骤，**失败不回滚**：按脚本内置回退链自动降级；全失败则保留 SVG 源文件，exceptions 登记 `render-failed`，status=partial，照常进步骤⑤。

**编辑工单**：在原 SVG 上只改工单要求的元素（文字/颜色/位置），**保留其余 id、图层结构与未涉及元素**；在 content_map 追加 `{edit: 元素, change: 改动, basis: 材料依据}` 记录；导出同样走渲染校验。

### 步骤⑤ 填 result.json 并自检
- `editable_source`：SVG 路径 + 图层 id 清单。
- `export_artifact`：PNG/PDF 路径 + 实际尺寸/dpi + `--check` 结果。
- `content_map`：步骤③产物（含编辑工单的 edit 记录）。
- `compliance_checks`：逐项登记——画布符合工单/默认 1200×600(2:1)；字号下限达标；每个要点可溯源；图中每个数字/结论在材料中能找到原句；文字全为 text 元素；渲染校验结果。
- `exceptions`：材料缺失、降级、渲染回退、熔断等逐条如实登记。
- `status`：如实。最后按协议第 2 条做 JSON/键集合/case_id 自检。

## 异常处理

| 情形 | 处置 |
|---|---|
| 仅摘要可用 | 降级：要点只从摘要提炼，登记 `abstract-only` |
| 工单缺失/画布未指定 | 按 1200×600(2:1) 执行，登记 `workorder-missing` |
| 渲染全链失败 | 交付 SVG + 登记 `render-failed` + status=partial，继续填 result.json |
| PNG 校验不过 | 检查 viewBox/透明背景，修正重渲；两次失败登记 exception |
| 文字溢出 | 缩短文案（不破 16px 下限）或拆两行 |
| 实体歧义 | 用原文明确表述；无法确定则不上图并登记 |
| 字体缺失 | font-family 用通用栈 `Arial, Helvetica, sans-serif` |

## 自检清单（交稿前逐项过）

- [ ] result.json 可解析，键集合与 output_contract 完全一致，case_id 一致
- [ ] 画布与工单一致；标题 ≥34px / 要点 ≥20px / 标注 ≥16px
- [ ] content_map 每条有出处；图中无编造数据
- [ ] 文字全为 `<text>`；SVG 分层且 id 语义化；图例覆盖全部颜色/箭头
- [ ] PNG(300dpi) `--check` 为 CHECK OK；PDF 已导出
- [ ] status 与 exceptions 如实；编辑工单有 edit 记录

## 使用方式

1. 平台把本 Skill 装入 `/skills/weekly-skill`，Harness 在每个固定案例上执行：输入 `/input/case.json` + task.md + 材料与工单；工作目录 `/app/work`；产物写 `/app/output/`。
2. 依赖：Python 3 标准库即可运行 render_svg.py；有 cairosvg/rsvg-convert/inkscape/chromium 时自动优先使用。详见 README.md。
3. 限制：不负责论文正文写作与统计分析；材料之外的数据一律不上图。
