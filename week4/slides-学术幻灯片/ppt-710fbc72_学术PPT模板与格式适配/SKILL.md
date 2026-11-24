---
name: template-fit-skill
description: 学术PPT模板与格式适配技能：先探查模板母版/版式/占位符真实结构，再把论文内容填进正确版式槽位（真实继承主题字体配色），逐页产出可核验的模板规则映射（模板原始值→应用值→依据），带版面预算防溢出、图表等比适配、整册一致性校验与导出核验。Use when the task is to apply/adapt an academic PPT template (套模板/母版/版式/字体配色/批量排版/格式适配), not free-form deck generation.
---

# template-fit — 模板真实继承 + 逐页规则映射可核验

评分看三件事：**指定模板被真实套用**（母版/版式/占位符继承可查）、**页内内容与源材料对得上**、**整册版式与导出可逐页核对**。本技能核心产出是**逐页模板规则映射**：每一页用了哪个版式、哪些占位符、模板原始值是什么、我们应用了什么、依据是什么——全部写进 result.json，供评分器逐条核验。

## 执行协议（最高优先级，先于一切工作）

1. **第1步（首个响应内完成）**：读 `/input/case.json`，把 `output_contract` 的**全部字段名原样抄下** + `case_id`。禁止遗漏、禁止改名字段。
2. **第2步（同响应内）**：立即写 `/app/output/result.json` **骨架**——含 case_id 与 output_contract 全字段（值先置 null）、`status: "in_progress"`。此后每完成一步就回填。**即使中途熔断/失败，result.json 也必须存在**。
3. **广度优先**：先跑通全流程拿到完整低配产物（pptx + result.json 可评版本），再回头逐页精修。禁止在一个页面上打磨到完美才开始下一页。
4. **预算熔断**：预算以 task.md 为准（64 请求 / 900 秒）。**当用到 48 次请求或 700 秒时，立即停止新工作**：保存当前 pptx、把已完成的页面信息写入 result.json、status 如实降级为 partial。宁可交 80 分完整度的部分结果，不交 40 分完整度的"快完成了"。
5. **写盘自检**：每次写 result.json 前先 `python -c "import json;d=json.load(open('/app/output/result.json'));print(len(d))"` 校验可解析；写完后再跑一次确认字段数没变少。
6. **失败也写 result.json**：任何阶段失败，result.json 必须记录 status、失败原因、已完成部分的位置。材料缺失/无法判断/运行失败三者分开写。

## 主流程（线性 5 步，按序执行）

### 第 1 步 — 契约与骨架落盘
```bash
ls -la /input/ && cat /input/case.json
```
- 找到**模板文件路径**（case.json 或 task.md 指定）。无模板 → 走学术默认版式，result.json 的 template_rule_map 里 rationale 写明"输入未提供模板文件"。
- task.md 给了"起点 deck"（改稿任务）→ 记下路径，第 3 步同样先探查再只改内容不动版式。
- 按执行协议第 1、2 条写出 result.json 骨架。同时把页数上限/时长/受众等约束记入 `/app/work/constraints.json`。

### 第 2 步 — 模板与材料探查（先探查，后动手）
```bash
python scripts/probe_template.py <模板.pptx> --out /app/work/template_report.json
python scripts/extract_pdf.py <材料.pdf> --outdir /app/work/extracted
```
- probe 产出：版式清单（名称+占位符 idx/type/几何）、主题字体（majorFont/minorFont 的 latin+ea）、主题色板、页型推荐映射。**探查结果决定一切，不编造模板规范**——后面每条映射决策都要引用这里的原始值。
- 材料非 PDF（md/docx/txt）→ 直接读取，extract 跳过；扫描件 → OCR 或整页渲染，locator 用页码。

### 第 3 步 — 页计划 + 模板规则映射 + 证据（1-2 次响应）
产出 `/app/work/deck.json` 与 `/app/work/evidence_map.jsonl`（schema 见 references/page-plan-and-evidence.md）。
- 页计划按论文主线排页：标题→问题→方法→结果（每关键结果一页）→限制→结论。页数超限先砍方法细节页，**不砍结果页与限制页**，取舍记 changelog。
- 每页在 deck.json 的 `rule_map` 字段记录映射决策（这是评分器重点读取的内容）：
```json
{"no":3, "role":"result", "layout":"bullets+figure",
 "template_layout":"Two Content", "placeholders_used":[1,2],
 "template_original":{"placeholder1":"idx1 type=BODY w=4.2in h=4.8in", "theme_font_ea":"Segoe UI", "accent":"accent1 #2E5B9A"},
 "applied":{"title":"标题占位符原字号未覆盖", "body":"占位符内填充，字号16pt", "figure":"右侧内容占位符contain-fit", "font":"继承主题未显式指定"},
 "rationale":"结果页=图文版型，探查报告推荐Two Content；保留主题字体实现真实继承",
 "inheritance":"real"}
```
- 规则：`template_original` 必须抄自 template_report.json 的真实探查值；`rationale` 必须能回溯到探查报告或题目约束；占位符缺失的页型用独立文本框兜底，inheritance 记 `real_plus_textbox_fallback` 并在 rationale 说明。
- 字体策略：模板主题已定义 → deck_meta.font_latin/font_ea **留空**（继承）；无主题 → 才显式指定（Arial + fc-list 验证存在的 CJK 字体）。
- 数值页逐字 quote 挂 evidence_map；`python scripts/evidence_check.py --paper /app/work/extracted/paper_text.txt --map /app/work/evidence_map.jsonl` 必须 pass 才进第 4 步。

### 第 4 步 — 构建（真实继承 + 版面预算 + 等比适配）
```bash
python scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx <模板.pptx> --log /app/output/layout_log.json
cp /app/work/deck.json /app/output/deck.v1.json
```
- 有 python-pptx + 模板 → **克隆模板文件构建**，逐页记录 template_layout / placeholders_used / inheritance: real（母版继承可查的直接证据）。
- 三级容错：python-pptx 缺失 → stdlib 兜底（pptx_minimal，仍可编辑，inheritance 如实记 standalone_minimal_fallback）；模板损坏 → 学术默认版式 + uncertainty 声明"模板不可用"。
- 内置规则（偏离即记 layout_log）：图片 contain-fit 不拉伸；字号阶梯 18→16→14→12→11→10，10pt 仍溢出**删内容不许再缩**；图注统一 10pt 斜体灰；表格首行加粗；页码/页脚沿用模板自带。

### 第 5 步 — 校验、渲染、result.json 终稿
```bash
python scripts/pptx_verify.py /app/output/deck.pptx /app/work/deck.json --evidence /app/work/evidence_map.jsonl --out /app/output/verify_report.json
python scripts/consistency_check.py /app/output/deck.pptx --out /app/output/consistency_report.json
python scripts/render_preview.py /app/output/deck.pptx --outdir /app/output/previews
```
- verify/consistency 的 fail 必须修复重跑；warn 列入 uncertainty。渲染后抽查 PNG：字体替换/图片丢失/版式塌陷 → 修复重跑并记 changelog。无渲染器如实记 `render.status="no_renderer"`，不伪造。
- **result.json 终稿**（先跑执行协议第 5 条自检再写）：
```json
{
  "case_id": "...",
  "...(output_contract 原字段逐个填，一个不缺)...": {},
  "template": {"file": "<模板路径>", "report": "template_report.json", "inheritance": "real|standalone_minimal_fallback"},
  "deck": {"file": "deck.pptx", "slides": N},
  "template_rule_map": ["第3步 deck.json 各页 rule_map 的完整内嵌——每页模板原始值→应用值→依据→inheritance"],
  "font_color_layout_mapping": {
    "fonts": {"latin": {"template_value": "Calibri(majorFont)", "applied": "inherit未覆盖", "rationale": "探查报告 theme_fonts"}},
    "colors": {"accent": {"template_value": "accent1 #2E5B9A", "applied": "仅用于强调文本", "rationale": "只用主题色板"}},
    "layout": {"footer": {"template_value": "模板自带页脚", "applied": "未改动", "rationale": "批量一致性"}}
  },
  "evidence_map": ["evidence_map.jsonl 逐行内嵌"],
  "render": {"pdf": "deck.pdf", "previews": "previews/", "status": "ok|pdf_only_no_png|no_renderer"},
  "verification": {"layout_log": "layout_log.json", "verify_report": "verify_report.json", "consistency_report": "consistency_report.json", "evidence_check": "evidence_check.json"},
  "status": "complete|partial|failed|blocked",
  "uncertainty": ["未能核验/降级/缺失项及原因"],
  "changelog": ["每条取舍、修复与逐页偏差记录"]
}
```
- status 四级语义：complete=全链路完成且校验通过；partial=某阶段失败但有可评部分（写明哪步为什么）；failed=无可用产物（也要写全字段）；blocked=输入材料缺失/模板不可用导致无法开始（模板探查报告与失败原因必须附上）。

## 异常处置

| 情形 | 处置 |
|---|---|
| 模板损坏/非pptx | probe 报错如实记录；默认版式兜底；uncertainty 写"模板不可用"；status=blocked 或 partial |
| 占位符缺失/版式不够 | 独立文本框兜底 + inheritance=real_plus_textbox_fallback；不伪造继承 |
| 槽位太小装不下内容 | 先删内容再降字号；再不行换探查报告推荐的更合适版式 |
| 字体缺失（渲染方框） | 换 fc-list 中实际存在的中文字体重建；changelog 记录 |
| 文本框溢出 | 回第 3 步删要点；禁止 <10pt 硬塞 |
| 图表源失效/提取不到 | 整页渲染 page_p{n}.png；figure_mode=page_render；禁止占位图 |
| 只改前几页其余旧模板 | 全册走同一脚本一次性生成；verify 的 slide_count 校验兜底 |
| python-pptx 缺失 | stdlib 兜底；继承降级如实记录；不隐瞒 |
| 导出失败 | render_log 记原因；交 pptx + 已完成部分；status=partial |

## 最小调用示例（示意，非正式案例结果）

```bash
python scripts/probe_template.py /input/materials/template.pptx --out /app/work/template_report.json
# → {"layouts":11, "theme_fonts":{"majorFont":{"latin":"Calibri"}}, "recommendation":{"result":"Two Content",...}}
python scripts/extract_pdf.py /input/materials/paper.pdf --outdir /app/work/extracted
# （模型响应）deck.json(含逐页rule_map) + evidence_map.jsonl
python scripts/evidence_check.py --paper /app/work/extracted/paper_text.txt --map /app/work/evidence_map.jsonl
# → {"summary":{"rows":14,"fail":0,"verdict":"pass"}}
python scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx /input/materials/template.pptx --log /app/output/layout_log.json
# → builder: python-pptx | pages: 12 | inheritance: real (逐页)
python scripts/pptx_verify.py /app/output/deck.pptx /app/work/deck.json --evidence /app/work/evidence_map.jsonl --out /app/output/verify_report.json
python scripts/consistency_check.py /app/output/deck.pptx --out /app/output/consistency_report.json
python scripts/render_preview.py /app/output/deck.pptx --outdir /app/output/previews
# → {"status":"ok","pdf":".../deck.pdf","pngs":12}
```

## 交付自查清单（写 result.json 终稿前逐项过）

- [ ] result.json 含 case_id 与 output_contract **全部**字段，无 null 遗留或已在 uncertainty 解释
- [ ] template_rule_map 覆盖**每一页**：template_original 抄自探查报告、applied 具体明确、rationale 可回溯、inheritance 如实
- [ ] font_color_layout_mapping 三组（字体/颜色/版式）逐条有 template_value→applied→rationale
- [ ] evidence_map 覆盖全部页面，数值页逐字 quote 且 evidence_check pass
- [ ] layout_log 逐页有 template_layout + placeholders_used；无 content_exceeds_page 未处理项
- [ ] 全册字号/图注/页码一致（consistency pass 或已解释）；无拉伸变形图
- [ ] deck.pdf/PNG 存在且与 pptx 抽查一致；渲染状态如实
- [ ] status/uncertainty/changelog 如实；失败环节写明原因不编造
