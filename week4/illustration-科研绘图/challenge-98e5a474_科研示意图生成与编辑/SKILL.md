---
name: scientific-schematic-generator
description: Generate and edit layered, editable scientific schematics (mechanism/pathway/workflow diagrams) as SVG with element-level source traceability, then render real PNG(300dpi)/PDF exports with pixel verification. Use when the task asks to create, modify, or edit a scientific figure/schematic/diagram/flowchart from source materials, workorders or existing SVG. Trigger words: 科研示意图, 机制图, 流程图, schematic, pathway diagram, editable SVG, figure editing, source-preserving edit, 图例映射.
---

# 科研示意图生成与编辑 Skill

走通「来源材料 → 可编辑 SVG → 合规导出件」，每一步落盘可核验。
核心纪律：**禁止编造**（图中不出现来源没有的实体名/数值/单位）；抑制/激活方向绝不画反。


## 主路径收敛令（P0，覆盖其他流程指令）

1. **交付优先序**：骨架落盘 → 主字段/主内容补全 → result.json 完整可解析（此步完成即达到可交付状态）→ 校验器 → 增益层。
2. **增益层降级为可选**：gain_probe 的消融双跑与污染反例自测只在剩余预算（请求+时间）≥40% 时执行；预算不足直接跳过，在 result.json 的 gain_evidence 写 {"available": false, "reason": "budget_exhausted"}，**禁止**为增益证据挤占交付预算。
3. **预算告急即定稿**：任一时刻请求次数或时间过半仍未完成校验，立即以当前 result.json 定稿交付，缺失键如实登记，禁止继续展开任何支线。
4. 主线禁止执行污染反例自测（那是离线取证工具，非交付必需）。
## 强制执行协议（最高优先级，覆盖所有步骤）

1. **先落地再优化**：读完 `/input` 下全部输入后，**立即**写 `/app/output/result.json` 骨架：键集合 = case.json 中 `output_contract` 声明的**全部字段**（预期为 `["case_id","status","editable_source","export_artifact","content_map","compliance_checks","exceptions"]`，以实际声明为准，一个不缺），写入真实 `case_id` 与 `status:"partial"`；暂无法产出的字段填 `"unknown"` 或 `[]`。
2. **每步一个写盘动作**：五步依次各有一个明确的写盘动作（result.json 骨架 → work/figure.svg → 导出件 → result.json 终稿）。任何时刻中断，盘内都是可评分状态。
3. **预算熔断**：模型请求超过 48 次（上限 64）或运行超过 700 秒（上限 900），立即停止新步骤，用已有产出收尾 result.json。
4. **失败也要写**：任何异常都更新 result.json，`status` 如实取 `partial`/`failed`，`exceptions` 记录失败点与已尝试的回退链。空 result.json 比崩溃更不可接受。不虚构软件状态或科学数据。

## 线性五步主流程（按顺序执行，禁止跳步）

### 步骤1：探测输入，抄录契约（只读，不写盘）
- 先 `ls -R /input` 探测实际文件，再逐一读取；不按文件名假设内容。PDF 用平台提供的解析工具读原文。
- 读 `/input/case.json`：抄下 `case_id` 与 `output_contract` **全部键名**（原样抄录，不增不减）。
- 读工单（如 figure-workorder）与全部来源材料，判定任务类型：**新建图稿** 或 **编辑现有 SVG**（工单附带现有 SVG 即为编辑任务，记录其路径）。
- 抄录导出约束（格式/尺寸/分辨率/字体）；未声明时默认 PNG 300dpi + PDF。

### 步骤2：写 result.json 骨架（写盘动作①）
按协议第 1 条立即落盘到 `/app/output/result.json`。此后每完成一步就回填对应字段。

### 步骤3：实体-关系抽取 → 写分层 SVG（写盘动作② work/figure.svg）
- 从来源材料抽取实体、关系、数值与单位。**凡在 content_map 找不到证据的实体/关系，一律不画。**
- 每个图面元素在 content_map 登记：`{"element_id":"<SVG id>","type":"entity|relation|annotation","label":"<图面文字>","source":"<文件名> p.<页/行/表>","evidence":"<原文摘录≤30字>"}`。
- **关系方向核对表（逐条核对后再落图）**：

| 关系语义 | 图形表达 |
|---|---|
| 激活/促进 | 实线箭头，方向=原文陈述方向，不颠倒 |
| 抑制 | T 型阻断端 ⊣，绝不画成箭头 |
| 包含/组成 | 嵌套分组框（子元素在父框内），不画成并列 |
| 并列 | 同级排布，无箭头 |
| 时序 | 左→右或上→下，配阶段编号 |

**逐条核对后，把核对表全量嵌入 result.json**：每条关系一个三元组 `{"item":"<关系A→B>","template_value":"<材料原文陈述（激活/抑制/包含/并列/时序）>","applied":"<实际图面表达>","match":true|false}`，写入 `compliance_checks.relation_checks` 数组。不许只写「已核对」汇总；任何一条 `match:false` 必须改图并复检，改不动则记入 exceptions。

- **新建图稿**：写分层 SVG——`<g>` 带 id 分层（`g-stage-1`/`g-entity-A`/`g-rel-A-B`/`g-legend`/`g-annotations`），语义 class（`entity`/`relation-activate`/`relation-inhibit`）；文字一律 `<text>` 不转路径；`font-family="Helvetica, Arial, sans-serif"`；抑制用 T 端 marker，激活用箭头 marker；图例项与颜色/分类逐项对应。
- **编辑现有 SVG（source-preserving edit）**：只改工单要求的元素；其余元素的 id、图层结构、坐标、样式原样保留；在 result.json 写 edit 记录 `{"changed":"<element_id>","what":"<改了什么>","basis":"<来源位置+摘录>"}`。

### 步骤4：真实渲染导出并校验（写盘动作③ /app/output 下 PNG+PDF）
```bash
python3 scripts/render_svg.py work/figure.svg --outdir /app/output --png --pdf --dpi 300
python3 scripts/render_svg.py /app/output/figure.png --check
```
- 若 `scripts/render_svg.py` 不在当前目录：`SCRIPT=$(find /skills /app/work . -name render_svg.py 2>/dev/null | head -1)` 后用 `$SCRIPT` 重试；**评测沙箱通常没有 cairosvg/浏览器：不要尝试内联导入这些库**（会 ImportError）。渲染器不可用属可预期降级：保留 SVG 源文件照常交付，`export_artifact` 如实登记 `renderer_unavailable` 与已尝试清单，脚本退出码恒 0 不中断交付。
- `--check` 必须运行并确认输出 `CHECK OK`（非空图、尺寸>0）；`PNG OK`/`PDF OK`/`CHECK OK` 三条输出**逐字全文**嵌入 `export_artifact.render_evidence`，供评分器不开文件即可核对。

### 步骤5：回填 result.json 全字段并自检（写盘动作④）
- `editable_source`：SVG 路径 + 分层说明 +（编辑任务）edit 记录。
- `export_artifact`：PNG/PDF 路径 + 像素尺寸 + DPI + `render_evidence`（渲染输出逐字全文）。
- `content_map`：步骤③完整清单，一个元素不缺。
- `compliance_checks`：**逐条三元组**，不许只写汇总。至少包含三组：
  - `relation_checks`：关系方向逐条（步骤③的核对表），每条 `{item, template_value, applied, match}`；
  - `entity_checks`：每个图面实体名与来源比对，每条 `{item, template_value, applied, match}`（`template_value` = 来源原文实体名）；
  - `export_checks`：格式/分辨率/尺寸逐项，每条 `{item, template_value, applied, match}`（`template_value` = 工单声明的导出参数；未声明项 `template_value:"not_declared"`）。
- **闸门状态显式化**：上述每个检查组自带 `gate` 字段，取值只允许 `enforced`（已逐条跑完）/ `skipped_not_provided`（来源未提供该项）/ `not_found`（来源里找不到核对依据）/ `unreadable`（材料无法读取）。**没跑 ≠ 通过**：凡非 `enforced`，必须加 `warn:true` 和 `gate_note:"下游不得宣称已核对"`，并写明原因。
- `exceptions`：全部异常与处置；`status`：`complete`/`partial`/`failed`，如实。
- 写盘前 JSON 自检：`python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"` 确认可解析且含 output_contract 全部键，通过才算完成。

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

| 异常 | 处置 |
|---|---|
| 找不到渲染脚本/渲染器 | find 定位 → 尝试标准库可用路径 → 如实登记 renderer_unavailable 与已尝试清单；SVG 仍交付，**退出码恒 0** |
| 来源缺失/矛盾 | 缺失实体不画不猜；矛盾处 content_map 标 `conflict` + 双方证据 |
| 数据与图例不一致 | 以数据为准改图例，写 exceptions |
| 字体缺失 | 通用 font-family 栈，记录回退，不虚构嵌入状态 |
| 导出失败 | PNG/PDF 互相降级；都失败交 SVG+说明 |
| 工单与材料冲突 | 以材料事实为准，差异写入 exceptions |

## 自检清单（收尾前逐项过）

- [ ] result.json 含 output_contract 全部键 + case_id（与输入一致），JSON 可解析
- [ ] status 如实；失败也写了 result.json
- [ ] 图中每个名字/数值在 content_map 有 source + evidence，无一个凭空出现
- [ ] 关系方向逐条与材料一致（激活→、抑制⊣、包含=嵌套、上下游不颠倒），且 relation_checks 逐条 match 已嵌入
- [ ] compliance_checks 三组逐条三元组齐全，每组 gate 状态显式（非 enforced 必有 warn+gate_note）
- [ ] 图例颜色/形状与数据分类逐项一致
- [ ] SVG 分层、g 带 id、文字均为 `<text>`；编辑任务仅改要求元素且保留其余 id，有 edit 记录
- [ ] 渲染成功则 PNG/PDF 真实存在且 `--check` 通过并已嵌入 render_evidence；渲染器不可用则已如实登记 renderer_unavailable 且 SVG 交付完整（不中断交付）

## 使用方式

1. 平台把本 Skill 装入 `/skills/weekly-skill`，Harness 在每个固定案例上执行。
2. 输入：`/input/case.json` + task.md + 工单与来源材料；工作目录 `/app/work`；产物写 `/app/output/`。
3. 依赖：Python 3（render_svg.py 仅用标准库；有 cairosvg 时优先使用）。详见 README.md。
