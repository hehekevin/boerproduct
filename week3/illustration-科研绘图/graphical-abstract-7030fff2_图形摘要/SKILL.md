---
name: graphical-abstract-builder
description: >
  Build journal-style Graphical Abstracts (single-figure "question→method→
  result→conclusion" summaries) from provided source materials, or perform
  source-preserving edits on an existing figure. Produces a layered, fully
  text-editable SVG plus real PNG (300dpi) + PDF exports with pixel checks,
  and a result.json whose keys are copied verbatim from the case's
  output_contract. Machine-generated audit (canvas/font-floor/overflow/
  layer/zone/edit-diff triples) is embedded verbatim; every element and
  number is traceable to a verbatim source quote. Fabrication is forbidden.
---

# Graphical Abstract Builder（图形摘要构建 Skill）

把论文材料变成一张期刊风格单图图形摘要，或按工单对已有图稿做保源编辑。核心纪律：**图中每个实体、数值、结论都必须能逐字追到来源材料原文；追不到就不画。** 评分只看三件事：内容与来源对得上、机检对账可复跑、源文件可编辑可导出——三者全部由脚本产出数据，不经模型转述。

## 强制执行协议（最高优先级，覆盖一切其他规则）

1. **先抄契约再动手**：读完 `/input/case.json` 后，**逐键原样抄录** `output_contract` 全部字段键名（不增不减不排序）与真实 `case_id`。字段名以 case.json 实际内容为准，禁止凭本文件示例臆造。
2. **立即落骨架**：抄完契约立刻写 `/app/output/result.json` 骨架：全部契约键 + `status="partial"`，暂无法产出的字段填 `"unknown"` 或 `[]`。此后每步一个写盘动作增量回写；任何时候 result.json 都是可解析的合法 JSON。
3. **广度优先**：先跑通"读材料→SVG→渲染→audit→result.json"全链路拿到可评产物，再回头精修。禁止单个面板打磨到完美才继续。
4. **路径不臆测**：先 `ls -R /input` 并检查 case.json 内嵌字段定位工单与材料；用 `find /skills /app -name '<脚本名>' 2>/dev/null | head -1` 动态定位 render_svg.py 与 svg_audit.py（找到什么用什么，禁止写死任何作者本地路径）。
5. **分批写长文件**：SVG 与 result.json 都先写骨架、再逐层/逐字段充实，单次写入 ≤200 行（长文本每段 ≤1500 字），避免 16384 token 截断产生半截文件。
6. **写盘前 JSON 自检**：每次回写 result.json 前 `python3 -c "import json;d=json.load(open('/app/output/result.json'));print(len(d))"`，写完复核字段数未减少、可解析。
7. **预算熔断与失败也交付**：模型请求 >48 次（上限 64）或运行 >700 秒（上限 900）立即停止新步骤收尾；**任何失败（渲染失败、材料缺失、熔断）都必须写出含全字段与 exceptions 的 result.json**，status 如实四级。

## 线性五步主流程

### 步骤① 读输入，抄契约
- 读 `/input/case.json`：抄 `case_id` + `output_contract` 全键（原样）。
- 定位并读工单（如 `artifacts/figure-workorder.json`，可能内嵌 case.json）：画布尺寸/比例、目标格式、是**新建图**还是**编辑工单**（source-preserving edit）、组织方修订注记（如 `graphical_abstract`、主生物来源对应 figure03）。
- 读论文材料（PDF/文本）：重点读**摘要、结论、主图图号与图注**。以实际文件内容为准，不依据标签臆测。记录题名、材料清单、缺失项（供步骤⑤登记）。

### 步骤② 落 result.json 骨架
按协议第 2 条立即写盘，写后按协议第 6 条自检。

### 步骤③ 提炼信息：content_map + evidence_map（禁止编造）
- **一句话核心结论**：取自摘要或结论原句，作标题区副标题。
- **3–4 个关键要点**：每条 ≤12 词，按"问题→方法→核心结果→结论"排序。
- **一个中心视觉概念**：方法/机制简化为流程示意（实体用论文明确写出的名字；箭头方向以原文因果为准；只用论文描述过的实体与关系）。
- 产出两份映射，全部内嵌 result.json：
  - `content_map`：每要点/视觉元素一条 `{element, text, source, svg_layer}`；**找不到出处的内容一律不上图**。
  - `evidence_map`：每条 `{kind(claim|number|entity), evidence(≤40字逐字摘录), source_id(abstract|conclusion|figN|workorder), location(第N句/段/Figure N)}`；**数字类 claim 的数字必须逐字出现在 evidence 里**（空白归一化后子串匹配）。图中出现的每个数字都必须能回证到某条 evidence；**unbacked 数字逐条列出 → 改图补证或删数字，不许改 quote 迁就图**。材料不足标 uncertainty，不硬凑。

### 步骤④ 写分层 SVG → 真实渲染 → 机检对账
在 `/app/work` 写 SVG（先骨架后逐层充实），四个图层（各为带语义 id 的 `<g>`）+ 视觉动线分区：
1. `layer-title`：论文短标题（1200 宽画布 ≥34px），`data-zone="background"`。
2. `layer-points`：3–4 个短句要点 + 编号图标。
3. `layer-visual`（约占 55% 面积）：中心概念示意——圆角矩形/圆形实体 + `marker` 箭头，流向左→右或上→下，不交叉。
4. `layer-legend`：图例说明图面用到的每种颜色/箭头含义。

**视觉动线分区登记**：阅读顺序"背景→方法→结果→结论"用 `data-zone` 属性结构化标注（如 layer-points 的要点分组 `data-zone="background|method|result|conclusion"`），供 svg_audit 逐区核对并内嵌 result.json。

硬性规则：文字全部用 `<text>` 元素（不转曲、不栅格化、无 `<image>`）；要点字号 ≥20px、图内标注 ≥16px、标题 ≥34px；外边距 ≥40px；文字不溢出边界；同一含义只用一种颜色，避免纯红绿对；font-family 用通用栈。

**渲染**（脚本按协议第 4 条动态定位；渲染是单点步骤，失败不回滚）：
```bash
python3 <render_svg.py> work/ga.svg --outdir /app/output --png --pdf --dpi 300
python3 <render_svg.py> /app/output/ga.png --check   # CHECK OK（非空、非全白）才算通过
```
全失败则保留 SVG 源文件，exceptions 登记 `render-failed`，status=partial，照常进步骤⑤。

**机检对账**（结果文件**原样内嵌** result.json，禁止手写替代）：
```bash
# 新建图（zones 取步骤③实际分区名）：
python3 <svg_audit.py> work/ga.svg --canvas 1200x600 \
    --zones background,method,result,conclusion --out /app/work/svg_audit.json
# 编辑工单（额外传原稿产出 source-preserving diff）：
python3 <svg_audit.py> work/ga.svg --canvas 1200x600 --baseline <原稿.svg> \
    --zones ... --out /app/work/svg_audit.json
```
audit 每项输出 `{item, template_value, applied, match}` 三元组 + `gate` 显式状态（`enforced`=已执行 / `skipped_not_provided`=参数未提供未执行，须带 gate_note「下游不得宣称已核对」 / `not_found` / `unreadable`）。**任何 `match:false` 必须修图重跑**（缩文案不破字号下限、拆行、改分区标注）；修不了写 uncertainty 说明。`summary.fail>0` 照实写入报告并嵌入 result.json（退出码恒 0，不许伪装通过也不许中断交付）。

**编辑工单**：在原 SVG 上只改工单要求的元素（文字/颜色/位置），**保留其余 id、图层结构与未涉及元素**；机检用 `--baseline` 生成 `edit_diff`（preserved/modified/removed/added 逐条），`removed` 非空即 fail；content_map 追加 `{edit: 元素, change: 改动, basis: 材料依据}` 记录；导出同样走渲染校验。

### 步骤⑤ 填 result.json 并自检
- `editable_source`：SVG 路径 + 图层 id 清单 + data-zone 分区登记。
- `export_artifact`：PNG/PDF 路径 + 实际尺寸/dpi + `--check` 结果。
- `content_map` / `evidence_map`：步骤③产物（含编辑工单 edit 记录）；**numeric_unbacked 列表（须为空或已登记 uncertainty）**。
- `svg_audit`：`svg_audit.json` 全量原样内嵌（含全部三元组与 gates）。
- `compliance_checks`：渲染校验结果、画布符合工单/默认 1200×600(2:1)、字号下限达标（引用 audit 数据，不手写）。
- `exceptions`：材料缺失、降级、渲染回退、熔断、闸门未执行等逐条如实登记。
- `status` 四级如实：complete=全链路通过；partial=某阶段失败但有可评产物（写明哪步）；failed=无可用产物（仍写全字段）；blocked=材料缺失无法开始。最后按协议第 6 条做 JSON/键集合/case_id 自检。

### 步骤X：增益证据与效率计数（回填 result.json）
本节产出的必须是**本次运行真跑出来的数字**，不是文字声明：
```bash
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --baseline
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --write
```
- 第一条：基础模式对照——模拟「不做证据登记/不做方向核对」的路径，统计源材料里有多少实体与数值会变成不可核对项（需人工逐条核对的规模）。
- 第二条：当前模式实测——登记覆盖率、证据逐字回证率、关系方向核对通过率、需人工核对条目数，并计算相对基线的削减量；`--write` 写入 `result.json.registry_evidence`（含 `baseline_comparison.reduction` 与 `efficiency` 计数；若本包另有脚本写 `gain_evidence`，两者互补不覆盖）。
- 评分器不开附件即可核对：两套指标、削减比例、计数来源都写在 result.json 里。

## 异常处理

| 情形 | 处置 |
|---|---|
| 仅摘要可用 | 降级：要点只从摘要提炼，登记 `abstract-only` |
| 工单缺失/画布未指定 | 按 1200×600(2:1) 执行，登记 `workorder-missing` |
| 渲染全链失败 | 交付 SVG + 登记 `render-failed` + status=partial，继续填 result.json |
| PNG 校验不过 | 检查 viewBox/透明背景，修正重渲；两次失败登记 exception |
| 文字溢出（audit overflow match:false） | 缩短文案（不破 16px 下限）或拆两行，重跑 audit |
| 实体歧义 | 用原文明确表述；无法确定则不上图并登记 uncertainty |
| 字体缺失 | font-family 用通用栈 `Arial, Helvetica, sans-serif` |
| 材料无法判断 / 运行失败 | 三者分开写进 exceptions；status 如实降级，不编造运行状态 |

## 自检清单（交稿前逐项过）

- [ ] result.json 可解析，键集合与 output_contract 完全一致，case_id 一致
- [ ] svg_audit 全量内嵌；enforced 项 match 全 true；未执行项有 gate_note
- [ ] evidence_map 覆盖全部要点与图中数字；numeric_unbacked 为空或已登记
- [ ] data-zone 分区已标注且 audit 核对通过；content_map 每条有出处
- [ ] 文字全为 `<text>`；SVG 分层且 id 语义化；图例覆盖全部颜色/箭头
- [ ] 渲染成功：PNG(300dpi) `--check` 为 CHECK OK 且 PDF 已导出；渲染器不可用：已如实登记 renderer_unavailable 且 SVG 完整交付
- [ ] 编辑工单 edit_diff removed=0 且有 edit 记录
- [ ] status/exceptions/uncertainty 如实
