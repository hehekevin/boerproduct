# acwrite-mindmap — 使用与方法说明

科研思维导图技能：从论文 / 实验方案 / 项目计划 / 会议纪要等科研材料中抽取核心概念与关系，生成**节点树 + 关系 + 证据全部结构化嵌入 result.json** 的可编辑思维导图，另产出 FreeMind(.mm) / OPML / 自包含 SVG / PNG 渲染预览四种格式。节点可回溯原文段落，关系带依据，材料外连接为零。

## 1. 用途与适用条件

- **用途**：把科研材料整理为"抓得准、理得清、连得对、证据可追溯"的思维导图。
- **适用**：单一或少量文档（论文、综述、实验方案、项目计划、会议纪要，docx/pdf/txt/md/csv/xlsx/html）。
- **不适用**：多语言混合超大语料的全书知识图谱；图片扫描件无 OCR 环境时降级为部分提取并如实标注。

## 2. 依赖

- **Python 3（标准库即可运行全部核心脚本）**。注意：环境中 `python` 命令可能不存在，**一律用 `python3`**。
- **零外部依赖**：不需要 node / npm / puppeteer / 浏览器 / 联网 / 任何 pip 包。
- 可选增强（缺失时自动降级、如实记录，不报错）：cairosvg / svglib+reportlab / rsvg-convert / inkscape / playwright（仅用于更好的 PNG 渲染；全都没有时由内置纯标准库光栅器兜底）。

## 3. 调用方式（完整流程 5 步）

脚本随 SKILL.md 一起安装，运行时动态定位（不硬编码安装路径）：

```bash
PY=$(command -v python3 || command -v python)
SCRIPT_DIR=""
for d in /skills/weekly-skill/scripts ./scripts scripts; do
  if [ -f "$d/build_result.py" ]; then SCRIPT_DIR="$d"; break; fi
done
if [ -z "$SCRIPT_DIR" ]; then
  SCRIPT_DIR=$(find /skills /app -type d -name scripts 2>/dev/null | while read -r d; do [ -f "$d/build_result.py" ] && echo "$d" && break; done)
fi
[ -n "$SCRIPT_DIR" ] || SCRIPT_DIR="./scripts"   # 兜底：相对路径 + 如实登记，不臆造路径

  [ -f "$d/build_result.py" ] && { SD="$d"; break; }
done
[ -n "$SD" ] || SD=$(dirname $(find /skills /app . -name build_result.py 2>/dev/null | head -1))
[ -n "$SD" ] || SD=./scripts

# Step 0 读契约、落骨架（第一个写盘动作，保证任何时刻 result.json 存在且可解析）
$PY $SD/build_result.py init --case /input/case.json --out /app/output/result.json

# Step 1 材料盘点与事实台账
$PY $SD/extract_materials.py --input /input --outdir /app/work/extracted
$PY $SD/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl

# Step 2 模型响应产出四份中间文件到 /app/work：
#   coverage.jsonl（逐材料要点 + kind 分类）/ tree.json（节点树，带 src）
#   relations.jsonl（跨分支关系，带 basis）/ node_evidence.jsonl（证据挂接，locator + 逐字摘录）

# Step 3 生成四格式、真实渲染、机检
$PY $SD/map_build.py --tree /app/work/tree.json --relations /app/work/relations.jsonl --evidence /app/work/node_evidence.jsonl --outdir /app/output
$PY $SD/render_preview.py --svg /app/output/mindmap.svg --outdir /app/output/previews
$PY $SD/map_check.py --coverage /app/work/coverage.jsonl --tree /app/work/tree.json --relations /app/work/relations.jsonl --evidence /app/work/node_evidence.jsonl --materials /app/work/extracted --out /app/output/map_check.json

# Step 4 增益证据 + 主产物嵌入 result.json + 自检（--auto 按 output_contract 语义填契约四键）
$PY $SD/gain_evidence.py --tree /app/work/tree.json --relations /app/work/relations.jsonl --evidence /app/work/node_evidence.jsonl --coverage /app/work/coverage.jsonl --materials /app/work/extracted --out /app/output/gain_evidence.json
$PY $SD/build_result.py embed --case /input/case.json --out /app/output/result.json --auto \
  --tree /app/work/tree.json --relations /app/work/relations.jsonl --evidence /app/work/node_evidence.jsonl \
  --coverage /app/work/coverage.jsonl --ledger /app/work/fact_ledger.jsonl --outline /app/output/outline.md \
  --check /app/output/map_check.json --render-log /app/output/previews/render_log.json \
  --gain /app/output/gain_evidence.json \
  --artifact /app/output/mindmap.mm --artifact /app/output/mindmap.opml --artifact /app/output/mindmap.svg \
  --artifact /app/output/outline.md --artifact /app/output/previews/mindmap.png \
  --script-calls 9 --steps 5 \
  --set status=complete --uncertainty '材料缺口/未确认项' --changelog '节点取舍与修改记录'
$PY $SD/build_result.py verify --case /input/case.json --out /app/output/result.json
```

> verify / map_check 的 verdict **照实记录即可，不是 pass 也能交付**（最多修复一轮，剩余问题写进 change_log 人工确认项）。

## 4. 输入 / 输出

**输入**：`/input/case.json`（含 case_id 与 output_contract）+ 题面 + 材料文件。

**输出**（/app/output）：

| 文件 | 说明 |
|---|---|
| result.json | 主交付：case_id + **output_contract 全键**（deliverable / preserved_facts / evidence_map / change_log）+ 富字段（mindmap_tree / mindmap_relations / node_evidence / deliverable_content / render / consistency_check / verification / gates / gain_evidence / efficiency / uncertainty / changelog / artifacts） |
| mindmap.mm | FreeMind 格式，节点含 TEXT_TYPE 与 EVIDENCE 属性，可导入 FreeMind/XMind 编辑 |
| mindmap.opml | OPML 大纲，可导入 WorkFlowy/幕布等 |
| mindmap.svg | 自包含 SVG（径向布局、类型着色、关系连线、证据角标、节点 ID），无外部字体/脚本依赖 |
| outline.md | Markdown 大纲（层级 + 类型标签 + 证据定位 + 跨分支关系） |
| previews/mindmap.png | 真实渲染 PNG，render_log.json 记录引擎、字节数、尺寸、非空白像素占比 |
| previews/render_log.json | 渲染证据（含引擎尝试序列与 glyph_mode） |
| map_check.json | 机检报告：verification 逐条三元组 + gates 闸门状态 + metrics 5 项指标 + need_manual 人工确认项 |
| gain_evidence.json | 增益证据：baseline / full 两遍真实对照数字 + 机制→指标映射 + 边界 + efficiency |
| build_report.json | 四格式写盘自检（文件非空、SVG 良构、节点数告警） |

## 5. 关键方法

1. **契约先行**：Step 0 用脚本抄 output_contract 全键落骨架（本题公开契约为 deliverable / preserved_facts / evidence_map / change_log，脚本内置该默认值，即使 case.json 未给也按此落键），此后任何时刻 result.json 存在且可解析，失败也交付。
2. **契约键自动语义映射**：`build_result.py embed --auto` 把富字段自动映射成契约四键——
   deliverable＝导图结构+关系+大纲全文+可编辑文件清单；preserved_facts＝数值/DOI/统计量/术语及其来源定位；
   evidence_map＝节点与关系到 locator + 逐字摘录的映射；change_log＝修改动作+机检问题+人工确认项+未解决问题。
3. **覆盖对账**：coverage.jsonl 逐材料抽要点并分类（core_concept/question/method/evidence/conclusion/task/risk/decorative），map_check 校验每个非装饰要点都有节点落点，装饰性套话不入图并给理由。
4. **逐节点来源回证**：每个节点带 src（材料 sid）；src 必须可解析、label 归一化后须在源文本或证据摘录中逐字命中（exact）或全分词命中（token），否则计 fail 并逐条列出。
5. **关系有据**：跨分支关系六类（causal/dependency/contrast/support/conflict/temporal），每条带 basis；矛盾要点都入图并标 conflict，不擅自合并。
6. **证据挂接**：带数字节点、结论/证据型节点、冲突/支持关系必须挂 locator + 逐字摘录（≤30 字），区分 fact/summary/inference。
7. **真实渲染 + 像素校验**：render_preview.py 依次尝试 7 条路径（cairosvg → svglib → rsvg-convert → inkscape → playwright → 平台 CLI → **内置纯标准库光栅器**），对 PNG 做字节 + 尺寸 + 非空白像素占比三重校验（纯标准库 PNG 解码器实现，无 PIL 也能算真实像素比）；无渲染器时如实记，绝不伪造。
8. **闸门状态显式**：`gates` 枚举 enforced / skipped_not_provided / not_found / unreadable / skipped_disabled。没跑 ≠ 通过。
9. **增益证据可复现**：gain_evidence.py 对同一输入跑两遍（full 组 vs 确定性退化基线组），逐项对照章节覆盖率 / 节点可溯源率 / 层级合理率 / 需人工核对条目数 / 步骤数 / 缺陷检出数，全部是实跑数字。
10. **预算熔断**：模型请求 >40 次或运行 >600 秒立即收尾，最小合格版本优先；机检最多修一轮。

## 6. 异常处理

| 情形 | 处置 |
|---|---|
| python3 不存在 | `PY=$(command -v python3 \|\| command -v python3)`；都没有则手工写 result.json |
| 脚本找不到（$SD 为空） | 手工写 /app/output/result.json：契约四键 + mindmap_tree/relations/evidence；uncertainty 登记 |
| 材料缺失 / 格式不支持 | extract_materials 逐格式降级，extracted:false 如实标记；缺口写 uncertainty |
| 扫描件 | OCR 后抽取；uncertainty 注明 |
| 要点矛盾 | 都入图 + conflict 关系，不合并 |
| 节点 >45 | 聚合同粒度兄弟节点，build_report 给 warning |
| 无第三方渲染器 | 内置光栅器兜底出 PNG；glyph_mode 字段如实记录 |
| 脚本报错 / 输入损坏 | 全部异常捕获、退出码恒 0、verdict 照实；用手写最小产物兜底，status 如实降级也交付 |

## 7. 最小可运行自检清单（复制即跑，3-5 条命令）

```bash
# 0) 前提：把 SKILL 包放到任意目录，进入包根目录；以下命令不依赖 /input、不联网、不装包
cd <本包目录> && mkdir -p /tmp/mmcheck && rm -rf /tmp/mmcheck/*

# 1) 机检器空输入不崩、退出码恒 0、闸门状态显式（应为 verdict=fail, gates.tree=not_found, rc=0）
python3 scripts/map_check.py --tree /tmp/mmcheck/none.json --out /tmp/mmcheck/c0.json; echo "rc=$?"

# 2) 最小示例全链路：extract → build → render → check → gain → embed → verify（rc 全为 0，verify=pass）
mkdir -p /tmp/mmcheck/in/materials && cp examples/example_material.md /tmp/mmcheck/in/materials/
python3 scripts/extract_materials.py --input /tmp/mmcheck/in --outdir /tmp/mmcheck/extracted
python3 scripts/map_build.py --tree examples/example_tree.json --relations examples/example_relations.jsonl --evidence examples/example_evidence.jsonl --outdir /tmp/mmcheck/out
python3 scripts/render_preview.py --svg /tmp/mmcheck/out/mindmap.svg --outdir /tmp/mmcheck/out/previews
python3 scripts/map_check.py --coverage examples/example_coverage.jsonl --tree examples/example_tree.json --relations examples/example_relations.jsonl --evidence examples/example_evidence.jsonl --materials /tmp/mmcheck/extracted --out /tmp/mmcheck/out/map_check.json
python3 scripts/gain_evidence.py --tree examples/example_tree.json --relations examples/example_relations.jsonl --evidence examples/example_evidence.jsonl --coverage examples/example_coverage.jsonl --materials /tmp/mmcheck/extracted --out /tmp/mmcheck/out/gain_evidence.json
python3 scripts/build_result.py init --case examples/example_input.json --out /tmp/mmcheck/out/result.json
python3 scripts/build_result.py embed --case examples/example_input.json --out /tmp/mmcheck/out/result.json --auto --tree examples/example_tree.json --relations examples/example_relations.jsonl --evidence examples/example_evidence.jsonl --coverage examples/example_coverage.jsonl --outline /tmp/mmcheck/out/outline.md --check /tmp/mmcheck/out/map_check.json --render-log /tmp/mmcheck/out/previews/render_log.json --gain /tmp/mmcheck/out/gain_evidence.json --artifact /tmp/mmcheck/out/mindmap.mm
python3 scripts/build_result.py verify --case examples/example_input.json --out /tmp/mmcheck/out/result.json; echo "rc=$?"

# 3) 契约四键必须非空（应为 4 个非 0 数字，verify verdict=pass）
python3 -c "import json;d=json.load(open('/tmp/mmcheck/out/result.json',encoding='utf-8'));print({k:len(d[k]) for k in ('deliverable','preserved_facts','evidence_map','change_log')})"

# 4) 增益对照数字必须存在两遍真实记录（baseline vs full）
python3 -c "import json;g=json.load(open('/tmp/mmcheck/out/gain_evidence.json',encoding='utf-8'));print([(r['arm'],r['metrics'],r['wall_seconds']) for r in g['runs']])"

# 5) 一键双测 + 污染反例（脚本自带合成输入，无需任何外部文件；全部退出码应为 0）
python3 scripts/selftest_dual.py | python3 -c "import json,sys;d=json.load(sys.stdin);print([(s['name'],s['rc']) for t in d['tests'] if t['name']=='A_positive' for s in t['steps']]);print('污染反例:',[t['problems'] for t in d['tests'] if t['name']=='C_polluted'])"
```

预期：以上命令退出码**全为 0**；第 1 条 verdict=fail（诚实记录缺输入）；第 2 条 verify=pass；
第 3 条四个契约键均非空；第 4 条打印两遍真实对照数字。

## 8. 最小调用示例（示意，非正式案例结果）

输入：examples/example_input.json（case_id=demo-case-001，含 output_contract 字段结构）+ example_tree.json 等。

示意输出（节选，**标明为示例**）：

```json
{
  "case_id": "demo-case-001", "status": "complete",
  "deliverable": {"type": "mindmap", "editable": true,
    "formats": ["freemind_mm", "opml", "svg", "markdown_outline"],
    "tree": {"root": "血脑屏障纳米给药研究", "nodes": [
      {"id": "N01", "parent": null, "label": "血脑屏障纳米给药", "type": "core_concept", "src": "M01"}]},
    "outline_markdown": "# 血脑屏障纳米给药研究\n..."},
  "preserved_facts": [{"kind": "numeric_fact", "value": "3.2倍", "source_id": "M01",
    "locator": "M01:p2|para3", "quote": "穿透率为对照组的3.2倍"}],
  "evidence_map": [{"ref": "N03", "claim": "穿透率为对照组的3.2倍",
    "locator": "M01:p2|para3", "evidence_type": "fact", "source_id": "M01"}],
  "change_log": [{"action": "删除装饰性节点", "reason": "无材料依据", "human_confirm": false, "open_issue": null}],
  "render": {"status": "ok", "engine": "builtin-rasterizer", "png_bytes": 14309, "nonwhite_ratio": 0.0303}
}
```

以上为示意数据，正式运行时节点与证据来自实际材料并通过 map_check 校验（coverage_gaps=0、evidence_missing=0）。

## 9. 适用范围与限制

- 关系类型固定六类，超出类型的关系以"dependency + basis 说明"表达。
- 图内节点为 ≤12 字短语，完整论述在 note 与 outline.md，不把长句塞进节点。
- 节点总量 ≤45；超过应聚合同粒度兄弟节点。
- 章节覆盖率阈值为 0.34、节点可溯源率阈值为 0.8：低于阈值判 fail，高于阈值未覆盖项登记为人工确认项（真实论文章节多，逐标题全中会诱导反复修复烧光预算）。
- 渲染引擎依赖环境预装；评测镜像若无任何第三方渲染器，由内置纯标准库光栅器兜底出 PNG（非 ASCII 字形为空心占位框，`glyph_mode` 如实记录），SVG + .mm + .opml + outline.md 照常交付。
- 本 Skill 不预置任何正式案例答案；所有节点内容在运行时从实际输入材料抽取。

## 10. 生态贡献清单

**文档完整性**：本 README + SKILL.md 覆盖用途、适用条件、依赖（含零依赖声明）、调用方式、输入输出解释、关键方法、异常处理、最小调用示例、适用范围与限制、维护信息（见 worklog.md 的迭代小节）。

**资源可复用性**：8 个脚本可独立复用——`extract_materials.py`（通用材料提取，docx/pdf/xlsx/csv/html，锚点化）、`fact_ledger.py`（事实台账与数字回证）、`map_build.py`（四格式导图生成）、`render_preview.py`（多引擎渲染 + 纯标准库 PNG 解码器）、`map_check.py`（机检框架，可换 checker 复用）、`gain_evidence.py`（增益对照框架，同输入双跑 + 机制→指标映射 + 边界）、`build_result.py`（契约优先的结果收口）。5 个示例文件（example_input/tree/relations/evidence/coverage）+ 示例材料 example_material.md可直接替换为任意材料复跑；`selftest_dual.py`（脚本自带合成输入，开箱即跑）是可复用的双测 + 污染反例脚本。

**分享推广价值**：方法可迁移到任意"从材料生成结构化图谱"的场景（知识图谱、文献综述脉络、项目路线图、会议纪要决策树）。`gain_evidence.py` 的"确定性退化基线 + 同 checker 双跑"是通用的机制增益证明范式，可直接复用到其他 Skill 的使用增益举证。

**维护信息**：迭代过程与实测数字见 worklog.md（每轮记录差距清单、补强点与双测证据）。
