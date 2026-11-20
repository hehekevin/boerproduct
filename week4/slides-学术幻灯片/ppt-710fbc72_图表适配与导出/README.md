# template-fit-skill — 学术 PPT 模板与格式适配（v3）

面向「学术 PPT 模板与格式适配」赛道（ppt-710fbc72）。把论文/科研材料按**指定模板**真实套用为可编辑学术汇报 pptx，
并交付**机器生成**的三张证据表：逐页模板对账表（template_value→applied→match）、母版→版式→占位符继承链、适配前后五维 diff。

## 用途与适用条件

- 适用：有指定 pptx 模板（母版/版式/占位符）或起点 deck 的学术汇报适配任务；套模板、版式统一、字体配色规范、批量排版。
- 不适用：无模板约束的自由 deck 生成。
- 输入：`/input/case.json`（case_id、output_contract、材料与模板路径、约束）+ `task.md` + 材料文件。
- 输出：`/app/output/` 下 `deck.pptx`（可编辑）、`deck.pdf` + `previews/*.png`、`result.json`、`layout_log.json`、`fit_audit.json`、`verify_report.json`。

## 完整调用流程

1. 读 `/input/case.json`，抄下 output_contract 全部字段 + case_id，**立即**写 `result.json` 骨架。
2. `probe_template.py` — 探查母版/版式/占位符几何/主题字体/色板，产出 `template_report.json`（后续一切映射的唯一原始值来源）。
3. `extract_pdf.py` — 提取材料文本与图片（非 PDF 直接读；扫描件 OCR/页渲染）。
4. 生成 `deck.json` + `evidence_map.jsonl`（数值逐字 quote；备注 40-600 字，含过渡/强调/预判问题）。
5. `pptx_build.py deck.json out/deck.pptx <模板> --report template_report.json --log layout_log.json` — 真实继承构建。
6. `pptx_build.py deck.json work/baseline.pptx` — 同一内容的**无模板基线**，用于算适配增益。
7. `fit_audit.py out/deck.pptx --deck --report --baseline --log --out fit_audit.json` — 自动生成对账表/继承链/diff。
8. `pptx_verify.py` + `render_preview.py` — 结构校验与导出渲染；抽查 PNG 后回填 result.json 终稿。

## 关键方法

- **真实继承**：克隆模板构建；占位符内标题/正文的 typeface 与颜色**不显式写入**，交给母版主题（改主题即整册换字变色）；强调色取自报告 `theme_colors[0]`（主题 accent1）。
- **对账不可编造**：`format_fit` 的 `template_value` 抄自 `template_report.json`，`applied` 由 python-pptx 从真实 pptx 读出，`match` 由脚本判定（layout 比对 `slide_layout.name`；font 判断 run 是否残留显式字体；color 判断是否属主题色板或中性正文色；text 判断内容是否真进了占位符）。
- **继承链分层**：`master_theme_inherited` / `layout_placeholder` / `layout_placeholder_plus_textbox_fallback` / `standalone_textbox_no_inheritance`，每页标注实际生效层级。
- **版面预算**：`layout_budget` 按占位符几何估算行高，字号阶梯 18→16→14→12→11→10；10pt 仍溢出则删内容，禁止硬塞。
- **图表 contain-fit**：等比缩放，图片框宽高比与源图一致性由 verify/consistency 校验。
- **适配增益可量化**：`diff` 给出逐页五维改动，`gain.diff_changed_pages` = 需要模板适配才达标的页数，`gain.manual_fix_pages` = 对账未通过的页数（人工仍需处理的量）。
- **检查项必须计入总账**：`pptx_verify.py` 的 notes（缺失/过短/与正文雷同）、空页、缺标题、图未嵌入、几何越界、页级无证据，都直接计 `fail` 并让 `summary.verdict` 与退出码变红——只打印 `ok:false` 而不计分等于静默通过。
- **输入状态显式**：`fit_audit.py` 输出 `inputs`（每个输入四态：`loaded` / `skipped_not_provided` / `not_found` / `unreadable`）与 `audit_gate`（format_fit / diff 各为 `enforced` 或 `not_run` + 原因）。对账没跑时 `gate_notes` 写明"不得宣称已核对模板落点/已有增益证据"，非 `enforced` 即代表该项未执行——避免"缺参数 → 报告里少个字段 → 看起来像通过"。
- **数字对账闸门**：`pptx_verify.py` 把页面文本（title/bullets/columns/table/caption，不含 notes）里的百分数/小数/带单位数与**同页 evidence quote** 逐字比对，输出 `slide_coverage[].numeric_unbacked` 与 `summary.numeric_unbacked`。口径：无证据行=fail（页级 fail 冒泡到 `summary.verdict` 与退出码 1）；有证据行但数字未回证=warn（允许模板页码等新数字，但须登 uncertainty）；只抓高风险数，纯整数不抓（避免"3 个阶段"类误报）。未提供 `--evidence` 时 `coverage_gate.status="skipped_no_evidence"` 并记 warn，明确"闸门未执行"，不当成通过。

## 模板准备规范清单（复用他模板时逐项过）

1. 文件为 `.pptx`（非 `.pot`/`.ppt`），能被 python-pptx 打开；加密或损坏会在 probe 阶段报错并降级。
2. 至少含 title / content（或 two content）/ blank 类版式，版式名建议含 `Title Slide`、`Title and Content`、`Two Content`、`Title Only`、`Blank` 等可识别关键词（中英文均可）。
3. 占位符保留标准 `p:ph` 标记（title/body/ctrTitle），不要全删改成纯图形——否则无法真实继承，只能文本兜底。
4. 主题（theme1.xml）定义 `majorFont/minorFont` 与 `accent1-6`；中英文字体分别配置 `latin` 与 `ea`，避免回退。
5. 页脚/页码/日期由母版承载，不要在每页手画，以保证批量一致性。
6. 母版板式固定 16:9（13.333×7.5in）或与材料一致；混用尺寸会导致 contain-fit 计算偏差。
7. 字体需在渲染环境存在（`fc-list` 可见），否则导出 PDF 会替换字体。

## 导出与字体要求

- 渲染用 LibreOffice（`soffice`）；无渲染器时 result.json 记 `render.status="no_renderer"`，不伪造。
- 中文字体建议 `Noto Sans CJK SC` / 思源黑体；无模板时才显式指定，且须先 `fc-list` 验证存在。
- 导出后抽查至少 2 张 PNG（含图文页与表格页），确认无乱码方框、无溢出、无拉伸。

## 异常处理与限制

- 模板损坏/版式缺失/占位符不足/字体缺失/图表源失效/导出失败 → 按 SKILL.md「异常处置与降级链」逐级降级，每级登记 `degrade_chain`。
- python-pptx 缺失 → `pptx_minimal.py`（纯 stdlib，仍可编辑），继承降级写 `standalone_minimal_fallback`。
- status 四级：complete / partial / failed / blocked；材料缺失、无法判断、运行失败分开写。
- 预算熔断：48 请求或 700 秒即收口保存部分结果。
- 已知限制：`fit_audit` 的颜色判定把中性灰/黑视为合规正文色，强调色须落在主题色板；字体只做"是否残留显式字体"的判定，不做字形度量级一致性核验。
- 数字对账的已知短板：中文数字（"三成"）与区间（"3–5"）抓不到；归一化后为子串匹配，`12.4` 可能命中 `12.45`。token 已按"带单位/百分号优先"设计以压低误报，但不等于零误报——线上仍以抽查 quote 为准。
- 取样面：title + bullets + columns（含嵌套）+ table.rows + 图注，notes 不参与对账；**图片内嵌数字抓不到**（只能靠图注/正文引用）。表格单元格若是数字类型，`0.92` 会被当作独立 token（不会自动换算成 `92%`），内容侧应统一写成带 `%` 的字符串。

## 最小调用示例（示意，非正式案例结果）

```bash
python scripts/probe_template.py /input/materials/template.pptx --out /app/work/template_report.json
# → 示意：{"layouts":11,"theme_fonts":{"majorFont":{"latin":"Calibri","ea":""}},"theme_colors":["4F81BD",...]}
# （模型响应生成）deck.json + evidence_map.jsonl
python scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx /input/materials/template.pptx \
    --report /app/work/template_report.json --log /app/output/layout_log.json
# → 示意：builder: python-pptx | warnings: 0 | font_mode: theme_inherit
python scripts/fit_audit.py /app/output/deck.pptx --deck /app/work/deck.json \
    --report /app/work/template_report.json --baseline /app/work/baseline.pptx --out /app/output/fit_audit.json
# → 示意：{"slides":12,"fit_match_pages":12,"fit_match_rate":1.0,"diff_changed_pages":12,"fail":0}
python scripts/render_preview.py /app/output/deck.pptx --outdir /app/output/previews
# → 示意：{"status":"ok","pdf":".../deck.pdf","pngs":12}
```

## 资源清单与复用

| 文件 | 用途 | 依赖 |
|---|---|---|
| scripts/probe_template.py | 母版/版式/占位符/主题字体色板探查 | python-pptx |
| scripts/extract_pdf.py | 论文文本与图片提取 | PyMuPDF |
| scripts/layout_budget.py | 版面预算（行高/字号阶梯），构建前置防溢出 | 纯 stdlib |
| scripts/pptx_build.py | 真实继承构建 + 预算 + contain-fit + 主题色/字体继承 | python-pptx → 降级 pptx_minimal |
| scripts/pptx_minimal.py | stdlib 兜底构建（可编辑） | 纯 stdlib |
| scripts/fit_audit.py | 逐页对账表 + 继承链 + 前/后五维 diff + 整册一致性 | python-pptx |
| scripts/pptx_verify.py | 结构/证据/备注/溢出校验 | python-pptx |
| scripts/render_preview.py | PDF/PNG 渲染 | libreoffice/soffice |

复用方式：整目录拷入技能目录即可（无平台硬编码路径，参数化传入）；`fit_audit.py` 可独立用于任何"模板 vs 成品 pptx"的对账复核。
版本：v3（2026-11-13）；Python 3.8+；python-pptx 1.0+。
