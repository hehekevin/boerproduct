# acwrite-mindmap — 使用与方法说明

科研思维导图技能：从论文 / 实验方案 / 项目计划 / 会议纪要等科研材料中抽取核心概念与关系，生成**节点树 + 关系 + 证据全部作为结构化数据嵌入 result.json** 的可编辑思维导图，另产出 FreeMind(.mm) / OPML / 自包含 SVG / PNG 渲染预览四种格式。节点可回溯原文段落，关系带依据，材料外连接为零。

## 1. 用途与适用条件

- **用途**：把科研材料整理为"抓得准、理得清、连得对、证据可追溯"的思维导图。
- **适用**：单一或少量文档（论文、综述、实验方案、项目计划、会议纪要，docx/pdf/txt/md/csv/xlsx/html）。
- **不适用**：多语言混合超大语料的全书知识图谱；图片扫描件无 OCR 环境时降级为部分提取并如实标注。

## 2. 依赖

- Python 3.8+，仅标准库即可运行全部核心脚本。
- 可选增强（缺失时自动降级、如实记录，不报错）：
  - 材料解析：python-docx / PyMuPDF / pypdf（docx、pdf 提取）
  - PNG 渲染：cairosvg / svglib+reportlab / rsvg-convert / inkscape / playwright+chromium 任一
  - 像素校验：Pillow

## 3. 调用方式（完整流程 5 步）

脚本随 SKILL.md 一起安装，运行时以 `$SD` 指向 scripts 目录（自动探测，不硬编码路径）：

```bash
SD=$(find /skills -type d -name scripts 2>/dev/null | head -1); SD=${SD:-./scripts}

# Step 0 读契约、落骨架（第一个写盘动作，保证任何时刻 result.json 存在且可解析）
python $SD/build_result.py init --case /input/case.json --out /app/output/result.json

# Step 1 材料盘点与事实台账
python $SD/extract_materials.py --input /input --outdir /app/work/extracted
python $SD/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl

# Step 2 要点抽取与结构设计（模型响应，产出 coverage.jsonl / tree.json / relations.jsonl / node_evidence.jsonl）

# Step 3 生成四格式、真实渲染、机检
python $SD/map_build.py --tree /app/work/tree.json --relations /app/work/relations.jsonl --evidence /app/work/node_evidence.jsonl --outdir /app/output
python $SD/render_preview.py --svg /app/output/mindmap.svg --outdir /app/output/previews
python $SD/map_check.py --coverage /app/work/coverage.jsonl --tree /app/work/tree.json --relations /app/work/relations.jsonl --evidence /app/work/node_evidence.jsonl --out /app/output/map_check.json

# Step 4 主产物嵌入 result.json + 自检（verify 必须 verdict=pass）
python $SD/build_result.py embed --case /input/case.json --out /app/output/result.json \
  --embed-file /app/work/tree.json:mindmap_tree \
  --embed-file /app/work/relations.jsonl:mindmap_relations \
  --embed-file /app/work/node_evidence.jsonl:node_evidence \
  --embed-file /app/output/outline.md:deliverable_content \
  --embed-file /app/output/previews/render_log.json:render \
  --consistency /app/output/map_check.json --set status=complete --changelog '取舍记录'
python $SD/build_result.py verify --case /input/case.json --out /app/output/result.json
```

## 4. 输入 / 输出

**输入**：`/input/case.json`（含 case_id 与 output_contract）+ 题面 + 材料文件。

**输出**（/app/output）：

| 文件 | 说明 |
|---|---|
| result.json | 主交付：case_id + output_contract 全键 + mindmap_tree（节点树）+ mindmap_relations（关系）+ node_evidence（证据挂接）+ deliverable_content（大纲全文）+ render（渲染证据）+ uncertainty/changelog |
| mindmap.mm | FreeMind 格式，节点含 TEXT_TYPE 与 EVIDENCE 属性，可导入 FreeMind/XMind 编辑 |
| mindmap.opml | OPML 大纲，可导入 WorkFlowy/幕布等 |
| mindmap.svg | 自包含 SVG（径向布局、类型着色、关系连线、证据角标） |
| outline.md | Markdown 大纲（层级 + 类型标签 + 证据定位 + 跨分支关系） |
| previews/mindmap.png | 真实渲染 PNG，render_log.json 记录引擎、字节数、尺寸、非空白像素占比 |
| map_check.json | 机检报告：覆盖缺口 / 悬空引用 / 缺证据 / 层级深度 |

## 5. 关键方法

1. **契约先行**：Step 0 用脚本抄 output_contract 全键落骨架，此后任何时刻 result.json 存在且可解析，失败也交付（status=failed + 已完成部分）。
2. **覆盖对账**：coverage.jsonl 逐材料抽要点并分类（core_concept/question/method/evidence/conclusion/task/risk/decorative），map_check 校验每个非装饰要点都有节点落点，装饰性套话不入图并给理由。
3. **关系有据**：跨分支关系六类（causal/dependency/contrast/support/conflict/temporal），每条带 basis（原文定位）；材料没说的因果不连。矛盾要点都入图并标 conflict，不擅自合并。
4. **证据挂接**：带数字节点、结论节点、冲突/支持关系必须挂 locator + 逐字摘录（≤30 字），区分 fact/summary/inference，全部嵌入 result.json 供逐条回溯。
5. **真实渲染 + 像素校验**：render_preview.py 依次尝试 5 种渲染引擎，对 PNG 做字节 + 尺寸 + 非空白像素占比三重校验（<0.01 判无效并删除重报）；无渲染器时如实记 no_renderer，SVG 照常交付，绝不伪造渲染证据。
6. **预算熔断**：模型请求 >48 次或运行 >700 秒立即收尾，最小合格版本优先。

## 6. 异常处理

| 情形 | 处置 |
|---|---|
| 材料缺失 / 格式不支持 | extract_materials 逐格式降级，extracted:false 如实标记；缺口写 uncertainty |
| 扫描件 | OCR 后抽取；uncertainty 注明 |
| 要点矛盾 | 都入图 + conflict 关系，不合并 |
| 节点 >60 | 聚合同粒度兄弟节点，build_report 给 warning |
| 无渲染器 | render_log 如实记 no_renderer，四文本格式照常交付 |
| 脚本报错 | 逐级 try/except，日志落盘；用手写 .mm XML 兜底，status=failed 也交付 result.json |

## 7. 最小调用示例（示意，非正式案例结果）

输入：examples/example_input.json（case_id=demo-case-001）+ examples/example_tree.json 等。

```bash
python scripts/map_build.py --tree examples/example_tree.json --relations examples/example_relations.jsonl --evidence examples/example_evidence.jsonl --outdir /tmp/out
python scripts/render_preview.py --svg /tmp/out/mindmap.svg --outdir /tmp/out/previews
python scripts/build_result.py init --case examples/example_input.json --out /tmp/out/result.json
python scripts/build_result.py embed --out /tmp/out/result.json --embed-file examples/example_tree.json:mindmap_tree --embed-file examples/example_evidence.jsonl:node_evidence --set status=complete
```

示意输出（节选，标明为示例）：

```json
{
  "case_id": "demo-case-001", "status": "complete",
  "mindmap_tree": {"root": "血脑屏障纳米给药研究", "nodes": [
    {"id": "N01", "parent": null, "label": "血脑屏障纳米给药", "type": "core_concept"},
    {"id": "N03", "parent": "N01", "label": "穿透率提升3.2倍", "type": "evidence"}]},
  "mindmap_relations": [{"rel": "R01", "from": "N02", "to": "N03", "type": "causal",
    "basis": "M01:p2|para3 转铁蛋白修饰使穿透率提升", "evidence_state": "fact"}],
  "node_evidence": [{"nid": "N03", "type": "fact", "locator": "M01:p2|para3", "quote": "穿透率为对照组的3.2倍"}],
  "render": {"status": "ok", "engine": "cairosvg", "png_bytes": 68213, "nonwhite_ratio": 0.083}
}
```

以上为示意数据，正式运行时节点与证据来自实际材料并通过 map_check 校验（coverage_gaps=0、evidence_missing=0）。

## 8. 适用范围与限制

- 关系类型固定六类，超出类型的关系以"dependency + basis 说明"表达。
- 图内节点为 ≤8 字短语，完整论述在 note 与 outline.md，不把长句塞进节点。
- 渲染引擎依赖环境预装；评测镜像若无任何引擎，交付以 SVG + .mm + .opml + outline.md 为准，render_log 如实记录。
- 本 Skill 不预置任何正式案例答案；所有节点内容在运行时从实际输入材料抽取。
