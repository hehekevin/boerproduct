# deck-edit-skill — 使用与方法说明

## 用途
把论文/科研材料生成学术汇报 PPT（可编辑 pptx + 页级证据映射 + 演讲备注 + PDF/PNG 渲染件），或对已有 deck 做**source-preserving 定点编辑**（只改指令要求的页，母版与其余页保持不变），全程版本留痕、逐页 diff、可回退。

## 适用 / 不适用
- 适用：论文转学术汇报（组会/开题/答辩/评审）、按指令改某页内容、压缩/扩写/换受众/换语言、图表替换、多轮迭代带版本记录。
- 不适用：论文精读与文献综述、科研绘图的数据可视化算法、学术文字润色、PPT 软件开发。

## 依赖与安装
- Python 3.8+；PyMuPDF、python-pptx、Pillow（缺失时 build 自动降级 stdlib 兜底 `pptx_minimal.py`，渲染降级为仅 PDF 或如实报 `no_renderer`）。
- 渲染优先级：LibreOffice (soffice) → pdf 工具链 → 无渲染器时诚实标注。
- 脚本位于本 Skill `scripts/`，调用方式 `python scripts/<脚本> ...`；无平台路径硬编码，输入输出路径全部由参数传入。

## 输入 / 输出
- 输入：`/input/case.json`（case_id、output_contract、材料路径、约束）+ task.md + 论文/材料文件 +（编辑任务）起点 pptx。
- 输出（/app/output）：`result.json`（含 case_id、output_contract 全字段、每页标题/要点/备注/证据内嵌清单）、`deck.pptx`、`deck.vK.json` 快照、`evidence_map.jsonl`、`verify_report.json`、`evidence_check.json`、`layout_log.json`、`versions.jsonl`、`diff_v*.json`、`deck.pdf` + `previews/*.png`。

## 调用方式（概要）
按 SKILL.md 五步主流程执行：读契约 → 提取/盘点 → 页计划或编辑定位 → 构建/定点编辑 → 校验+diff+渲染+result.json。详细命令见 SKILL.md，无需额外配置文件。

## 最小调用示例（示意，非正式案例结果）
```bash
python scripts/extract_pdf.py paper.pdf --outdir /app/work/extracted
# → {"ok":true,"tool":"pymupdf","pages":12,"figures":6,"scanned":false}
python scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx --log /app/output/layout_log.json
# → builder: python-pptx | warnings: 0
python scripts/pptx_edit.py /app/output/deck.pptx replace-text --slide 3 --find "38.2" --text "41.7" --versions /app/output/versions.jsonl
# → {"ok": true, "op": "replace-text", "slide": 3, "versions_log": "/app/output/versions.jsonl"}
python scripts/pptx_verify.py diff /app/output/deck.v1.json /app/output/deck.v2.json --out /app/output/diff_v1_v2.json
# → diff: 1 ops across slides [3] -> /app/output/diff_v1_v2.json
python scripts/pptx_verify.py /app/output/deck.pptx /app/work/deck.json --evidence /app/work/evidence_map.jsonl --paper /app/work/extracted/paper_text.txt --out /app/output/verify_report.json
# → verify: {'fail': 0, 'warn': 0, 'verdict': 'pass'}
python scripts/render_preview.py /app/output/deck.pptx --outdir /app/output/previews
# → {"status":"ok","pdf":"/app/output/deck.pdf","pngs":10}
```
result.json 中 `slides` 字段示意（真实运行时逐页完整填写）：
```json
{"slides": [{"no": 3, "role": "result", "title": "主结果", "bullets": ["准确率 41.7%（vs 基线 38.2%）"],
  "figure": {"path": "fig_p5.png", "caption": "Figure 3: ...", "locator": "Fig.3 p.5"},
  "notes": "承上：方法页指出…；强调：41.7 来自 §4.1 原文，未被取整；预判：为何不与 XX 比较→见备用页",
  "evidence": [{"type": "quote", "locator": "§4.1 p.5", "quote": "our method achieves 41.7% ..."}]}]}
```

## 失败处理与自查
- 任何环节失败仍写 result.json（status=partial/failed + 原因）；材料缺失、无法判断、运行失败分开写。
- 提交前逐项过 SKILL.md §5 自查清单（字段完整性、证据 pass、版本记录齐、渲染一致、status 诚实）。

## 已知限制
- 定点编辑依赖 python-pptx；缺失时只能走 deck.json 重建路径并如实标注。
- 无法解析的矢量图整页渲染为 PNG 引用，不做数据还原。
- 渲染器不可用时导出件缺失，不影响 pptx 交付。
