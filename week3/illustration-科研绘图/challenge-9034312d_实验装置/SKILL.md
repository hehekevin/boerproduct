---
name: apparatus-route-figure
description: >
  Source-bound scientific figure skill for experimental apparatus diagrams
  (components, flow/optical/electrical connections, labeled parts) and
  technical route maps (stages, parallel branches, milestones). Extracts an
  element-id-traceable component-connection / stage structure from case
  materials, renders layered editable SVG, exports PNG(300dpi)+PDF via
  render_svg.py with pixel checks, and writes result.json honoring the
  output_contract. Every part, connection and stage carries element_id,
  source location and verbatim evidence; no invented parts or directions.
---

# 实验装置与技术路线图 Skill（apparatus-route-figure）

用途：把案例材料中的装置/工艺/研究计划描述，变成**可溯源、可编辑、可复跑**的装置图或技术路线图。铁律三条：①每个部件/连接/阶段都带 element_id 且能在来源中找到出处；②连接方向与来源一致，不明的画虚线并登记；③永远先写 result.json 骨架，再逐步充实。

## 第0节 强制执行协议（最高优先级，覆盖后续所有步骤）

1. **先骨架后完善**：读完 /input/case.json、工单（artifacts/figure-workorder.json，若存在）和来源材料后，**立即**在 /app/output/result.json 写入骨架：`output_contract` 声明的**全部键**逐一列出，值为 `unknown`/`[]`，外加 `"case_id"`（与 case.json 一致）与 `"status":"partial"`。字段一个不缺。
2. **广度优先**：先让六类要素（科学实体/空间关系/数据编码/图例标注/可编辑源文件/导出格式）各自有最小可用产出，再深化单项。禁止在单个部件绘制上耗尽预算。
3. **预算护栏**：累计模型请求 >48 次或运行 >700 秒，立即停止新增工作，转入收尾：填全 result.json、标记 status、登记 exceptions。
4. **写盘自检**：每次写 result.json 前确认：JSON 可被 `json.loads` 解析；含 output_contract 全部键；`case_id` 与 case.json 一致。任一不满足则修复后再写。
5. **失败也要交卷**：任何一步崩溃仍写 result.json：已完成部分如实填写，未完成字段填 `unknown`/`[]`，exceptions 写明失败环节，status 如实。空 result.json 比崩溃更不可接受。

## 第1节 线性5步主流程

### 步骤① 读取输入，抄定契约
- 读 /input/case.json：抄下 `case_id` 与 `output_contract` 的**全部键名**（以实际声明为准，不预设）。
- 读 task.md 与工单（若有）：判断是**新建图**还是**编辑既有图（source-preserving edit）**。
- 读来源材料（方法段落/装置清单/工艺说明/研究计划，PDF/文本/markdown）：提取文本，按**文件+页码/行号**记录位置。

### 步骤② 写 result.json 骨架
按第0节第1条立即落盘。此后每完成一块就回填对应字段，保持随时中断都是合法交付。

### 步骤③ 结构抽取（核心中间表示）
先抽结构再画图。部件名/阶段名一律用**来源原文**，不改写、不缩写、不意译。

**装置图**——
- 部件清单：每项含 `名称`（来源原文）、`参数`（来源给的规格；未给记 `未给出`）、`相对位置`（来源方位词）、`来源位置`（文件+页/行）。
- 连接关系：每条含 `起点部件`、`终点部件`、`介质`（物料/气/液/光/电/信息，用来源用词）、`线型依据`（来源明示=实线箭头；未明示但可合理推断=虚线+登记 exceptions）、`来源位置`。

**技术路线图**——
- 阶段清单：每项含 `阶段名`（来源原文）、`顺序号`（正文出现顺序）、`并行/分支`（仅来源明示的"同时/另/若…则"）、`判据`（无判据不画菱形）、`里程碑`、`来源位置`。编号与正文顺序逐条对照，禁止重排。

**content_map（可核验性核心，宁多勿漏）**：每个部件/连接/阶段一条记录，字段固定为：
`{"element_id": "part-01-反应器 / edge-03 / stage-02"（与 SVG 内 id 一一对应）, "text": 名称或"A→B(介质)", "source": "文件+页/行", "evidence": "≤30字逐字摘录（原文，含部件名/方向词）"}`
凡 content_map 中找不到证据条目的元素，一律不画。

### 步骤④ 写 SVG 并渲染导出
写**分层可编辑 SVG**（/app/output/），规范：
- 结构：`<g id="layer-parts|layer-links|layer-labels|layer-legend|layer-frame">`；每个部件 `<g id="part-01-反应器">`、每条连接 `<path id="edge-03">`、每个阶段 `<g id="stage-02-验证">`——id 与 content_map 的 element_id 一一对应。
- 装置图布局：按来源方位分区（浅色底框）；连接线用带 `marker-end` 的 `<path>`，旁标介质（如"载气 →"）；回流虚线弧；废液出口断头终端并标注。
- 技术路线图布局：泳道或阶段框+判断菱形（仅来源有判据）+并行分支；箭头与来源流程一致；框内标编号。
- 图例：图面用到的每种线型/颜色/箭头必须在 `<g id="legend">` 有对应条目，双向一一对应。
- 文字防溢出（机械检查）：宽度估算 = 中文字符数×字号 + ASCII 字符数×0.55×字号；超出框宽即换行或缩短，禁止溢出框外。
- 字体：`font-family="Noto Sans CJK SC, SimHei, sans-serif"`。
- 渲染：先动态定位脚本 `find /skills /app/work . -name render_svg.py 2>/dev/null | head -1`（不假设路径；找不到/渲染器不可用时如实登记 renderer_unavailable（**不要内联导入 cairosvg**，评测沙箱无此库）），再 `python3 "$SCRIPT" out/figure.svg --outdir out --png --pdf --dpi 300`，再 `python3 "$SCRIPT" out/figure.png --check`。两次输出逐字记入 render_evidence。
- **机检**：`find /skills /app/work . -name svg_verify.py 2>/dev/null | head -1` 定位后运行 `python3 "$VERIFY" out/figure.svg --map content_map.json --out out/verify_report.json`：机械检查分层（layer-* ≥4类）、语义 id 唯一、文字均为 `<text>`、legend 非空、content_map ↔ SVG id 双向一致；报告整份嵌入 result.json，退出码非零则 fail 冒泡到 status。
- **渲染证据嵌入**：把 `--check` 输出的 `width/height/nonbg_ratio` 与 PDF 字节数写成 `render_evidence: {png_width, png_height, nonbg_ratio, pdf_bytes, checker}` 嵌入 result.json（不许只写"渲染通过"）。
- 编辑工单：source-preserving edit（只改工单指定元素，保留其余图层与 id），再运行 `python3 "$VERIFY" out/figure_edited.svg --diff out/figure_original.svg --out out/edit_diff.json` 得到逐元素 diff（每个语义 id 一条 changed/before/after，未触碰元素 changed=false 即保留证据），**整份 edit_diff 嵌入 result.json**，并写 edit 记录（改了什么、依据哪条来源）。

### 步骤⑤ 填全 result.json 并自检
- 填全 output_contract 全部字段 + `content_map`（步骤③产出）+ `compliance_checks` + `exceptions` + `status`（如实）。
- compliance_checks 至少含五项**逐条记录**（写明每条比对结果，不许只写"已核对"）：
  ①**部件核对**：逐项"content_map.element_id ↔ 来源原文"，数量与名称一致。
  ②**连接方向核对表**：每条连接写成三列「原文句子 → 判定方向 A→B → 图上 edge-id 指向」，逐条比对。"A通入B"=A→B；虚线推断项也列入并标注；无一反向。
  ③**阶段顺序核对**：阶段编号↔正文出现顺序逐条对照。
  ④**图例完整性**：图面每种线型/颜色/箭头 ↔ legend 条目双向核对。
  ⑤**溢出与渲染**：各标注框宽度估算通过；PNG --check 通过（非全白、≥800px）；PDF >1KB；render_evidence 数值（宽/高/nonbg_ratio/PDF字节数）逐项嵌入。
  ⑥**分层可编辑性机检**：svg_verify.py 的 verify_report 五项逐条结果整份嵌入；编辑工单另嵌 edit_diff（逐元素 changed/before/after）。
- exceptions 登记：参数缺失、推断连接（虚线）、渲染回退、字体缺失等，每条含位置与处置方式。

## 第2节 异常处理

| 情形 | 处置 |
|---|---|
| 部件参数不全 | 保守默认值绘制（不标来源没有的数值），参数记 `未给出`，登记 exceptions |
| 连接关系不明 | 画**虚线**+方向问号，exceptions 登记"来源未明示，按上下游推断"；绝不画实线猜测 |
| 来源冲突 | 以更具体描述（方法段落>摘要）为准，两处来源均记入 content_map，exceptions 登记冲突 |
| 渲染失败回退链 | render_svg.py 内置 cairosvg→rsvg-convert→inkscape→chrome headless；全失败则保留 SVG，PNG/PDF 填 unknown，登记渲染器清单与报错。**调用脚本必须 try/except 包裹**：已知风险——cairosvg 已装但缺原生库（libcairo）时 `import cairosvg` 抛 OSError 而非 ImportError，绕过回退链直接崩溃（实测验证）；捕获后改用浏览器渲染或按全失败处置，traceback 全文记入 exceptions |
| 中文字体缺失/方框 | 检查 fontconfig 字体清单，改用存在的 CJK 字体名重渲 |
| 工单是编辑既有图 | source-preserving edit：复制原 SVG，只改指定元素，写 edit 记录；不整图重画 |
| 预算触顶 | 按第0节第3条收尾，已有内容优先保真 |

## 第3节 自检清单（收尾前逐项过）

**契约类**
- [ ] result.json 含 output_contract 全部键；case_id 一致；status 如实；JSON 可解析
**装置图专项**
- [ ] content_map 每条含 element_id+source+evidence（≤30字原文），element_id 与 SVG id 一一对应
- [ ] 部件数量与名称与来源逐项一致；介质标注齐全
- [ ] 连接方向核对表逐条完成，无一反向；不明连接均虚线且登记
**技术路线图专项**
- [ ] 阶段编号与正文顺序逐条对照；并行/分支与菱形仅来自来源明示；里程碑一致
**交付类**
- [ ] SVG 分层、元素有语义 id、文字均为 `<text>` 可编辑；svg_verify.py 机检通过且报告嵌入 result.json
- [ ] render_evidence（PNG 宽高/nonbg_ratio/PDF字节数）已嵌入 result.json
- [ ] 编辑工单：edit_diff 整份嵌入，未指定元素 changed=false 数量与预期一致
- [ ] 渲染成功：PNG 300dpi 且 --check 通过、PDF >1KB，render_evidence 已嵌入；渲染器不可用：已登记降级且 SVG 完整交付
- [ ] 图例与图面样式一一对应（双向核对）；文字无溢出
- [ ] exceptions 覆盖所有"未知/推断/失败"情形，无隐瞒

## 附：最小调用示例（示意，非正式案例结果）

输入 case.json 片段：`{"case_id":"demo-01","output_contract":["case_id","status","editable_source","export_artifact","content_map","compliance_checks","exceptions"],"materials":["method.txt"]}`
method.txt：*"载气（N2, 100 sccm）经质量流量计进入石英管反应器，尾气经冷阱排空。"*

示意流程：抄契约→写骨架→抽部件{质量流量计,石英管反应器,冷阱}、连接{气源→流量计→反应器→冷阱→排空，介质=载气N2}→content_map 3部件4连接，每条带 element_id+source+evidence→连接方向核对表逐条（"经质量流量计进入石英管反应器"=流量计→反应器）→SVG 水平链+图例→渲染 PNG/PDF+--check→填全 result.json，status=complete。

## 附：限制
- 不判断实验方案科学合理性；不做数据分析；不做期刊排版适配。
- 仅依据来源材料绘图；来源没写的不出现（或以虚线+登记方式呈现）。
- 渲染依赖环境内可用渲染器，全缺失时只交付 SVG 并如实登记。

### 步骤X：增益证据与效率计数（回填 result.json）
本节产出的必须是**本次运行真跑出来的数字**，不是文字声明：
```bash
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --baseline
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --write
```
- 第一条：基础模式对照——模拟「不做证据登记/不做方向核对」的路径，统计源材料里有多少实体与数值会变成不可核对项（需人工逐条核对的规模）。
- 第二条：当前模式实测——登记覆盖率、证据逐字回证率、关系/数值核对通过率、需人工核对条目数，并计算相对基线的削减量；`--write` 写入 `result.json.registry_evidence`（含 `baseline_comparison.reduction` 与 `efficiency` 计数；若本包另有脚本写 `gain_evidence`，两者互补不覆盖）。
