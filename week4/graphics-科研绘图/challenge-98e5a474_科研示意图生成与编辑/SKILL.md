---
name: relationship-schematic-skill
description: Generate and edit layered, editable scientific relationship schematics (SVG) with traceable entity-relation extraction, direction-verified relation semantics, legend compliance, and real PNG/PDF export with pixel checks. Reads actual case sources, never fabricates entities, relation directions, or values.
---

# 科研示意图（关系示意图）Skill

把一份真实科研材料（机制/通路/流程）变成一张**可逐条质疑、可回溯、可编辑**的通路图。核心纪律：**禁止编造**——图中不出现来源材料里不存在的实体名、浓度、时间点、单位；抑制/激活方向绝不画反。

## 强制执行协议（最高优先级，覆盖后续所有步骤）

1. **先落地再优化**：读完 `/input/case.json`、工单（如 `artifacts/figure-workorder.json`）与来源材料后，**立即**写 `/app/output/result.json` 骨架。键集合 = case.json 中 `output_contract` 声明的**全部字段**（预期为 `["case_id","status","editable_source","export_artifact","content_map","compliance_checks","exceptions"]`，以实际声明为准，一个不缺），并写入真实 `case_id` 与 `status:"partial"`；暂无法产出的字段填 `"unknown"` 或 `[]`，不得留空、不得编造。
2. **广度优先**：先保证每个阶段都有粗产出（骨架→实体清单→粗版 SVG→导出→精化），不在单步耗尽预算。
3. **预算熔断**：模型请求超过 48 次（上限 64）或运行超过 700 秒（上限 900 秒）时，立即停止新步骤，用已有产出填写并收尾 result.json。
4. **写盘前自检**：每次写 result.json 前，确认 JSON 可解析（`python -c "import json;json.load(open('/app/output/result.json'))"`)、output_contract 全键存在、`case_id` 与 case.json 一致。
5. **失败也要写**：任何异常/熔断/渲染失败，都更新 result.json：`status` 如实取 `partial`/`failed`，`exceptions` 记录失败点与已尝试的回退链。**空 result.json 比崩溃更不可接受。**

## 线性五步主流程

### 步骤1：读取输入，抄录契约
- 读 `/input/case.json`：抄 `case_id`、`output_contract` 全键（原样，不增不减不排序）。
- 读工单（若有）：区分两类任务——**新建图**（从来源材料生成机制图）与**编辑工单**（对已有 SVG 做 source-preserving 修改），以及指定导出格式/尺寸/分辨率。
- 通读来源材料（论文正文/图注/表格/数据文件）。所有实体与关系**只从实际文本中抽取**，不凭领域常识补造。

### 步骤2：写 result.json 骨架
按强制执行协议第 1 条立即落盘。此后每次实质进展都增量回写。

### 步骤3：通路抽取与关系语义核对（结果正确性的第一道防线）
从来源材料抽取：
- **实体**：基因/蛋白/复合物/家族成员/细胞类型/区室/刺激物/药物，逐一记录：名称（按原文书写，区分基因斜体惯例）、类型、来源位置。
- **相互作用**：逐条记录：主体（上游）→ 客体（下游）、关系类型（激活/抑制/磷酸化/结合/泛素化/转录调控/募集/转运）、原文证据（来源位置+原文摘录）、不确定性（若原文表述模糊）。
- 生成 `content_map`：每个实体与每条相互作用都附证据 `{source_ref, quote}`。**凡在 content_map 中找不到证据的实体/关系，一律不画。**

**关系语义核对表（必须逐条执行，禁止跳过）**：

| 关系类型 | 图元约定 | 方向规则 |
|---|---|---|
| 激活/促进 | 实线箭头 `→` | 从原因（上游）指向结果（下游） |
| 抑制 | T型短横端 `⊣`（SVG: 直线 + 垂直短横端帽） | T端指向被抑制者 |
| 磷酸化 | 箭头 + 标注 "P"（或按原文记号） | 激酶 → 底物 |
| 结合/复合物 | 无方向连线或共置同一复合物框 | 依原文；无方向依据则不画箭头 |
| 转录调控 | 箭头指向基因符号并标注 | 调控因子 → 靶基因 |
| 转运/易位 | 箭头跨区室 | 从原区室指向目标区室 |

执行方法：把每条边写成「原文句子 → 判定类型 → 方向：A→B」三列，与原文逐条比对后再落 SVG。**方向拿不准时按上下文取最保守解释（如仅写"关联"虚线）并登记 exceptions。**

### 步骤4：写分层可编辑 SVG 并真实导出
- **区室分层**：外层膜/核/质用嵌套 `<g id="compartment-膜外">` 分区；跨膜蛋白置于膜边界线上的独立分组。每个区室一个 `<g>`，内含实体 `<g id="entity-XXX">`。
- **可编辑性**：所有文字用 `<text>` 元素（不用转曲路径）；`id`/`class` 语义化命名（`entity-EGFR`、`edge-EGFR-inhibits-STAT3`、`legend`、`compartment-nucleus`）；分层顺序：底色→区室→实体→边→标注→图例。
- **图例**：图面用到的每种线型/箭头/颜色必须在 `<g id="legend">` 中有对应说明项；颜色映射与图面一一对应。
- **新建图**：按抽取结果从空 SVG 构建；**编辑工单**：在原 SVG 上只改工单要求的元素（改标签/位置/颜色），**保留其余 id、图层结构与未涉及元素**，并在 result.json 的 `compliance_checks.edit_record` 中记录：改了哪些元素、保留了哪些 id。
- **导出**：`python scripts/render_svg.py figure.svg --outdir /app/output --png --pdf --dpi 300`，随后 `python scripts/render_svg.py /app/output/figure.png --check` 校验尺寸与非空像素（nonbg_ratio>0.01）。失败时按脚本内置回退链（cairosvg→rsvg-convert→inkscape→chromium headless）逐级排查，全部失败则登记 exceptions 并在 result.json 标注导出缺口。

### 步骤5：填写 result.json 全字段并自检
- `editable_source`：SVG 路径 + 分层说明（区室/实体/边/图例的 id 结构）。
- `export_artifact`：PNG/PDF 路径 + 尺寸/分辨率/像素检查结果。
- `content_map`：步骤3产物（实体清单+边清单+证据）。
- `compliance_checks`：至少含三项记录——①关系方向逐条核对表结果（每条边：原文句子↔图元方向）；②实体名与来源逐一比对结果（图中每个名字↔来源原文）；③图例完整性（线型/颜色↔图面用量）。
- `exceptions`：材料未给出的关系、方向模糊取保守解释、渲染回退、字体回退等，逐条说明。
- `status`：`complete` / `partial` / `failed`，如实。
- 最后按协议第 4 条做 JSON 自检。

## 异常处理

| 场景 | 处置 |
|---|---|
| 材料未给出某实体/关系 | 不画，不补常识；在 exceptions 登记"来源未提及" |
| 关系类型/方向模糊 | 按上下文取最保守解释（如虚线"关联"），登记 exceptions 并给出原文依据 |
| 基因名/蛋白名歧义（同名异义） | 以原文上下文和物种前缀为准，无法消歧则用原文原写法并登记 |
| 渲染失败 | 回退链：cairosvg→rsvg-convert→inkscape→chromium headless；全失败则保留 SVG、标 partial、登记 exceptions |
| 字体缺失 | SVG 中 font-family 使用通用栈（如 `Arial, Helvetica, sans-serif`），不依赖特定字体文件 |
| 图面元素过多不可读 | 优先保证核心通路可读；省略项在 exceptions 说明 |
| 输入数据与图示矛盾 | 以来源文本为准，矛盾点登记 exceptions，不擅自调和 |

## 自检清单（交稿前逐项打勾）

- [ ] 图中**每个名字**（基因/蛋白/复合物/药物/区室）都能在来源材料中找到原词——专项：逐个 text 元素与来源比对，无一个凭空出现。
- [ ] 每条边的方向与原文一致，激活→、抑制⊣ 无一画反；每条边有原文句子佐证。
- [ ] 关系类型可区分：实线箭头/T端/P标注/无向连线使用正确。
- [ ] 跨膜蛋白画在膜上、区室位置正确、通路流向（受体→胞内→核）与原文一致。
- [ ] 图例覆盖图面全部线型/箭头/颜色，说明与实际一致。
- [ ] SVG 分层、id 语义化、文字均为 `<text>`；编辑工单仅改动要求元素且保留其余 id/图层，有 edit 记录。
- [ ] PNG(300dpi)+PDF 已真实导出，`--check` 像素校验通过（非空白）。
- [ ] result.json 键集合与 output_contract 完全一致，case_id 一致，JSON 可解析。
- [ ] exceptions 如实登记，status 如实。

## 使用方式

1. 平台把本 Skill 装入 `/skills/weekly-skill`，Harness 在每个案例上执行。
2. 输入：`/input/case.json` + task.md + 来源材料与工单；工作目录 `/app/work`；产物写 `/app/output/`。
3. 依赖：Python 3（仅标准库即可运行 render_svg.py；有 cairosvg 时优先使用）。详见 README.md。
