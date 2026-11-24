# template-fit-skill — 学术 PPT 模板与格式适配（重做版）

面向「学术 PPT 模板与格式适配」赛道（ppt-710fbc72）的 Skill：把论文/科研材料按**指定模板**真实套用为可编辑学术汇报 pptx，核心特色是**逐页模板规则映射可核验**。

## 用途与适用条件

- 适用：有指定 pptx 模板（母版/版式/占位符）或起点 deck 的学术汇报适配任务；套模板、版式统一、字体配色规范、批量排版。
- 不适用：无模板约束的自由 deck 生成（该场景请用通用论文转 PPT 流程）。
- 输入：`/input/case.json`（case_id、output_contract、材料与模板路径、约束）+ `task.md` + 材料文件。
- 输出：`/app/output/` 下 `deck.pptx`（可编辑）、`deck.pdf` 与 `previews/*.png`（渲染件）、`result.json`（含逐页模板规则映射与全链路证据）、layout_log / verify_report / consistency_report / evidence_check 等核验记录。

## 调用方式（完整流程）

1. 读 `/input/case.json`，抄下 output_contract 全部字段 + case_id；**立即**写 `/app/output/result.json` 骨架。
2. `python scripts/probe_template.py <模板.pptx> --out /app/work/template_report.json` — 探查母版/版式/占位符/主题字体色板。
3. `python scripts/extract_pdf.py <材料.pdf> --outdir /app/work/extracted` — 提取源材料（非 PDF 直接读取）。
4. 生成 deck.json（每页带 rule_map：模板原始值→应用值→依据）与 evidence_map.jsonl；`python scripts/evidence_check.py ...` 必须 pass。
5. `python scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx <模板.pptx> --log /app/output/layout_log.json` — 真实继承构建，三级容错。
6. `python scripts/pptx_verify.py` + `python scripts/consistency_check.py` + `python scripts/render_preview.py` — 校验、整册一致性、渲染。
7. 回填 result.json 终稿（写盘前后各做一次 JSON 可解析自检）。

## 关键方法

- **真实继承**：构建时克隆模板文件填充占位符，不覆盖母版/主题字体/页脚；layout_log 逐页记录所用版式与占位符 idx，作为继承证据。
- **逐页规则映射**：每页记录 template_original（抄自探查报告）→ applied → rationale → inheritance，全部内嵌 result.json 的 `template_rule_map` 与 `font_color_layout_mapping` 字段，评分器可逐条核验。
- **版面预算**：按探查到的占位符几何估算字数，字号阶梯 18→16→14→12→11→10；10pt 仍溢出删内容，禁止硬塞。
- **图表 contain-fit**：等比缩放不变形；矢量优先；consistency_check 校验宽高比偏差 >2% 记 fail。
- **批量一致性**：全册同一脚本一次性生成；字号阶梯/图注样式/页码位置统一。

## 异常处理与限制

- 模板损坏、占位符缺失、字体缺失、图表源失效、导出失败等处置见 SKILL.md「异常处置」表；所有降级如实记录，不伪造继承或渲染状态。
- python-pptx 缺失时自动降级 stdlib 构建（pptx_minimal.py，仍可编辑），继承降级在 result.json 声明。
- status 四级：complete / partial / failed / blocked，语义见 SKILL.md。
- 预算熔断：达 48 请求或 700 秒即收口保存部分结果。

## 最小调用示例（示意，非正式案例结果）

```bash
# 输入：/input/materials/template.pptx（11个版式）、/input/materials/paper.pdf（12页论文）
python scripts/probe_template.py /input/materials/template.pptx --out /app/work/template_report.json
# → 示意输出：{"layouts":11, "theme_fonts":{"majorFont":{"latin":"Calibri","ea":""}}, "recommendation":{"result":"Two Content"}}
# （模型响应生成）deck.json + evidence_map.jsonl
python scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx /input/materials/template.pptx --log /app/output/layout_log.json
# → 示意输出：builder: python-pptx | pages: 12 | layout_log 逐页含 {"template_layout":"Two Content","placeholders_used":[1,2],"inheritance":"real"}
python scripts/render_preview.py /app/output/deck.pptx --outdir /app/output/previews
# → 示意输出：{"status":"ok","pdf":".../deck.pdf","pngs":12}
```

## 资源清单与复用

| 文件 | 用途 | 依赖 |
|---|---|---|
| scripts/probe_template.py | 模板母版/版式/占位符/主题探查 | python-pptx（缺失时降级 stdlib zip 解析） |
| scripts/extract_pdf.py | 论文文本与图片提取 | PyMuPDF |
| scripts/pptx_build.py | 真实继承构建 + 版面预算 + contain-fit | python-pptx → 降级 pptx_minimal |
| scripts/pptx_minimal.py | stdlib 兜底构建（可编辑） | 纯 stdlib |
| scripts/pptx_verify.py | 结构/证据/备注校验 | python-pptx |
| scripts/consistency_check.py | 整册一致性（页码/字号/图注/图片比例） | python-pptx |
| scripts/render_preview.py | PDF/PNG 渲染 | libreoffice/soffice |
| references/page-plan-and-evidence.md | 页计划与证据映射 schema 细则 | - |

版本：本包为重做版（v2）；Python 3.8+；脚本无平台硬编码路径，参数化传入。
