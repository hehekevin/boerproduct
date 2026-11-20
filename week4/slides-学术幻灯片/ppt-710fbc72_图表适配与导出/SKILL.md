---
name: template-fit-skill
description: 学术PPT模板与格式适配技能：先探查模板母版/版式/占位符/主题字体配色的真实结构，再把论文内容写进正确版式槽位实现真实继承；构建后由脚本自动生成"模板原始值→实际落点值→是否吻合"逐页对账表、母版→版式→占位符三级继承链、以及适配前后五维 diff。Use when the task is to apply/adapt an academic PPT template (套模板/母版/版式/字体配色/批量排版/格式适配), not free-form deck generation.
---

# template-fit — 真实继承 · 逐页对账 · 适配增益可量化

评分只看三件事：**指定模板被真实套用**（母版/版式/占位符继承可查）、**页内内容与源材料对得上**、**整册与导出可逐页复核**。
本技能把这三件事变成**机器生成的对账数据**：模板原始值来自 `template_report.json`，落点值由 python-pptx 从**真实产出的 pptx** 读取，两者都不经模型转述——因此不可编造、可复跑。

## 执行协议（最高优先级，先于一切工作）

1. **第1步（首个响应内）**：读 `/input/case.json`，把 `output_contract` **全部字段名原样抄下** + `case_id`。
2. **第2步（同响应内）**：立即写 `/app/output/result.json` **骨架**（case_id + 全字段，值 null，`status:"in_progress"`）。此后每完成一步回填；即使熔断，result.json 必须存在且字段完整。
3. **广度优先**：先跑通全流程拿到可评产物，再回头逐页精修。禁止单页打磨到完美才继续。
4. **预算熔断**：48 请求 / 700 秒即停止新工作，保存 pptx、回填已完成页、status 如实降级为 partial。
5. **写盘自检**：每次写 result.json 前 `python -c "import json;d=json.load(open('/app/output/result.json'));print(len(d))"`，写完再验字段数未减少。
6. **不许编造**：模板规范只抄探查报告，渲染状态只报实际结果，缺项写进 uncertainty。材料缺失/无法判断/运行失败三者分开写。

## 主流程（线性 5 步）

### 第 1 步 — 契约、骨架与约束
```bash
ls -la /input/ && cat /input/case.json
```
- 定位**模板文件**与**起点 deck**（改稿任务）。无模板 → 走学术默认版式，并在 rationale 写"输入未提供模板"。
- 按协议 1、2 写骨架；页数上限/时长/受众记入 `/app/work/constraints.json`。

### 第 2 步 — 模板与材料探查（先探查，后动手）
```bash
python scripts/probe_template.py <模板.pptx> --out /app/work/template_report.json
python scripts/extract_pdf.py <材料.pdf> --outdir /app/work/extracted
```
- 探查产出：版式清单（名称 + 占位符 idx/type/几何）、主题 `majorFont/minorFont` 的 latin+ea、accent1-6、页型推荐映射。**后续每条映射都必须引用这里的原始值**。
- 材料非 PDF 直接读；扫描件 OCR 或整页渲染，locator 用页码。

### 第 3 步 — 页计划 + 证据（1-2 次响应）
产出 `/app/work/deck.json` 与 `/app/work/evidence_map.jsonl`：
```json
{"no":3,"role":"result","layout":"bullets+figure","title":"...","bullets":["..."],
 "figure":{"path":"...","caption":"论文图注原文","source_locator":"Fig.2 p.5"},
 "notes":"过渡+强调点+预判问题（40-600字，不复述页面文字）"}
```
- 排页：标题→问题→方法→结果（每关键结果一页）→限制→结论。超限先砍方法细节页，**不砍结果页与限制页**，取舍记 changelog。
- evidence 每行 `{"slide_no","claim","type","locator","quote","figure_mode"}`；**数值/单位逐字 quote**，改写取整一律不允许。
- 每页 `template_layout` 可留空，实际用了哪个版式由第 5 步从 pptx 实读对账。

### 第 4 步 — 双份构建（适配后 + 适配前基线）
```bash
python scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx <模板.pptx> \
    --report /app/work/template_report.json --log /app/output/layout_log.json
python scripts/pptx_build.py /app/work/deck.json /app/work/baseline.pptx --log /app/work/baseline_log.json
cp /app/work/deck.json /app/output/deck.v1.json
```
- 模板在 → **克隆模板文件构建**，占位符填充；`--report` 让强调色取自主题 accent1。
- **真实继承规则**：`deck_meta` 未显式指定字体/颜色时，run 上不写 typeface 与颜色，交给母版主题（改主题即整册换字变色）。仅无模板时才显式写字体。
- **基线 deck 是"适配前"对照**：同一份内容、无模板、默认版式，第 5 步据此算适配增益。
- 三级容错：python-pptx 缺失 → `pptx_minimal` stdlib 兜底（仍可编辑，继承如实降级）；模板损坏 → 学术默认版式 + 登记；版面超限 → 字号阶梯 18→16→14→12→11→10，10pt 仍溢出**删内容不许再缩**。

### 第 5 步 — 对账审计、校验、渲染、终稿
```bash
python scripts/fit_audit.py /app/output/deck.pptx --deck /app/work/deck.json \
    --report /app/work/template_report.json --baseline /app/work/baseline.pptx \
    --log /app/output/layout_log.json --out /app/output/fit_audit.json
python scripts/pptx_verify.py /app/output/deck.pptx /app/work/deck.json \
    --evidence /app/work/evidence_map.jsonl --out /app/output/verify_report.json
python scripts/render_preview.py /app/output/deck.pptx --outdir /app/output/previews
```
- `fit_audit.json` 四块，**原样内嵌** result.json：
  - `format_fit`：逐页 `template_value`（探查原值）→ `applied`（pptx 实读值）→ `match`（layout/font/color/text 四维）
  - `inheritance`：逐页 `master → layout → placeholders → textbox_fallback` + `effective_level`
  - `diff`：逐页适配前/后五维（title/body/font/color/layout）`changed`
  - `checks`：整册一致性（页码/标题字号/图注/图片框/字体清单）
- `match:false` 必须修（改版式映射、补占位符、对齐主题色）；修不了写 uncertainty 说明。
- **数字闸门**：页面上的百分数/小数/带单位数必须在**同页 quote** 里逐字出现（`summary.numeric_unbacked` 非空即 warn）。发现未回证 → 改页面或补 quote，**不许改 quote 迁就页面**；确属模板占位/页码等新数字，登 uncertainty。无证据行的页直接 fail（会冒泡到 verdict 与退出码），`coverage_gate.status=skipped_no_evidence` 说明闸门没跑，须登记。
- 渲染后抽查 PNG：乱码/溢出/图片变形 → 修复重跑。无渲染器如实记 `render.status="no_renderer"`。
- **result.json 终稿**（对账类字段一律从 fit_audit.json 复制，禁止手写）：
```json
{
  "case_id": "...",
  "...(output_contract 原字段逐个填，一个不缺)...": {},
  "template": {"file": "<模板路径>", "report": "template_report.json",
               "inheritance": "real|real_plus_textbox_fallback|standalone_minimal_fallback"},
  "deck": {"file": "deck.pptx", "slides": N},
  "format_fit_table": "fit_audit.json 的 format_fit 全量内嵌（每页每维 template_value→applied→match）",
  "inheritance_chain": "fit_audit.json 的 inheritance 全量内嵌（含 effective_level）",
  "slide_diff": "fit_audit.json 的 diff 全量内嵌（适配前/后五维）",
  "gain": {"fit_match_rate": "来自 summary", "diff_changed_pages": "来自 summary",
           "manual_fix_pages": "match:false 的页数"},
  "font_color_layout_mapping": {"fonts": {"template_value": "报告 majorFont", "applied": "pptx 实读", "match": true},
                                "colors": {"template_value": "报告 accent", "applied": "pptx 实读", "match": true},
                                "layout": {"template_value": "报告版式", "applied": "slide_layout.name", "match": true}},
  "evidence_map": ["evidence_map.jsonl 逐行内嵌"],
  "render": {"pdf": "deck.pdf", "previews": "previews/", "status": "ok|pdf_only_no_png|no_renderer"},
  "verification": {"layout_log": "layout_log.json", "fit_audit": "fit_audit.json", "verify_report": "verify_report.json"},
  "degrade_chain": [{"stage": "probe|build|render", "fallback": "...", "reason": "..."}],
  "status": "complete|partial|failed|blocked",
  "uncertainty": ["..."], "changelog": ["..."]
}
```
- status 四级：complete=全链路通过；partial=某阶段失败但有可评产物（写明哪步）；failed=无可用产物（仍写全字段）；blocked=材料缺失/模板不可用导致无法开始（附探查报告与原因）。

## 异常处置与降级链

| 情形 | 处置（按序降级，每级登记 degrade_chain） |
|---|---|
| 模板缺失/损坏/非 pptx | 探查失败登记 → 学术默认版式构建 → uncertainty 写"模板不可用" → status=partial/blocked |
| 版式缺失、占位符不够 | 选探查推荐的最接近版式 + 独立文本框兜底 → `effective_level=layout_placeholder_plus_textbox_fallback` |
| 槽位装不下 | 先按字号阶梯降，10pt 仍溢出则删要点；再不行换更宽版式 |
| 字体缺失/乱码 | 有模板→继承主题字体（不写 typeface）；无模板→换 fc-list 实存 CJK 字体 |
| 图表源失效 | 整页渲染 `page_p{n}.png`，`figure_mode=page_render`，禁止占位图 |
| python-pptx 缺失 | `pptx_minimal` 兜底，继承降级写 `standalone_minimal_fallback` |
| 只修了前几页 | 全册一次性脚本生成，`verify` 页数与 fit_audit 页数双校验 |
| 导出失败 | render 记原因，交 pptx + 已完成部分，status=partial |

## 最小调用示例（示意，非正式案例结果）
```bash
python scripts/probe_template.py /input/materials/template.pptx --out /app/work/template_report.json
# → 11 layouts; theme_fonts.majorFont.latin=Calibri; theme_colors[0]=4F81BD; recommendation.result="Two Content"
python scripts/extract_pdf.py /input/materials/paper.pdf --outdir /app/work/extracted   # → pages 12, figures 6
# （模型响应）deck.json + evidence_map.jsonl
python scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx /input/materials/template.pptx \
    --report /app/work/template_report.json --log /app/output/layout_log.json   # → builder: python-pptx, font_mode: theme_inherit
python scripts/fit_audit.py /app/output/deck.pptx --deck /app/work/deck.json \
    --report /app/work/template_report.json --baseline /app/work/baseline.pptx --out /app/output/fit_audit.json
# → {"slides":12,"fit_match_pages":12,"fit_match_rate":1.0,"diff_changed_pages":12,"fail":0}
```

## 交付自查清单
- [ ] result.json 含 case_id 与 output_contract 全部字段，无未解释 null
- [ ] format_fit_table 覆盖**每一页每一维**，template_value 与探查报告逐字一致，applied 与 pptx 实读一致
- [ ] inheritance_chain 每页有 effective_level；文本框兜底的页如实标注
- [ ] slide_diff 五维齐全，gain 里可量化人工修改量
- [ ] evidence_map 覆盖全页，数值逐字 quote；notes 每页 40-600 字且不复述正文（verify 里 notes 不合格=fail）
- [ ] `numeric_unbacked` 为空（否则已改页/补 quote 或登 uncertainty）；无证据行页 0 页
- [ ] 全册字号/图注/页码一致；无拉伸图；10pt 以下字号零出现
- [ ] deck.pdf/PNG 存在且与 pptx 一致；渲染状态如实
- [ ] degrade_chain 记录每次降级；status/uncertainty/changelog 诚实
