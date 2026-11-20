---
name: acwrite-mindmap
description: 科研思维导图技能：从论文/实验方案/项目材料/会议纪要抽取核心概念与关系，生成带证据挂接的可编辑思维导图——节点树+关系+证据全部作为结构化数据嵌入 result.json（评分器无需打开文件即可核对），另产出 FreeMind(.mm)+OPML+自包含 SVG+PNG 渲染预览四种格式。节点含类型与来源 locator，关系标注因果/依赖/对比/支持/冲突，渲染 PNG 带像素级校验证据。Use when the case asks to build a mind map / concept map from research materials with node coverage, typed relations, evidence hooks, editable outputs and rendered preview.
---

# acwrite-mindmap — 科研思维导图（结构化嵌入 · 真渲染 · 可追溯）

## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 7 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个写盘动作是
   `python $SD/build_result.py init --case /input/case.json --out /app/output/result.json`
   它把 output_contract 的全部键抄进骨架（缺值填 unknown，status=partial）。此后任何时刻 result.json 必须存在且 JSON 可解析。
2. **字段一个不缺**：最终 result.json 必须含 output_contract 全部键。某项无法产出时保留键填 unknown/空数组，原因写进 uncertainty，不得删键、不得编造。
3. **主产物结构化嵌入 result.json**（本技能核心，缺一即不完整交付）：
   - `mindmap_tree` ← tree.json（节点树：id/parent/label/type，评分器据此核对层级与覆盖）
   - `mindmap_relations` ← relations.jsonl（跨分支关系：类型+依据，评分器据此核对连接）
   - `node_evidence` ← node_evidence.jsonl（证据挂接：locator+逐字摘录，评分器据此核对追溯）
   - `deliverable_content` ← outline.md（大纲全文）
   - `render` ← render_log.json（真实渲染证据：engine/png 字节数/尺寸/非空白像素占比）
   只有文件指针而无内容 = 不完整交付。以上 5 个键全部用 `--embed-file 路径:键名` 嵌入。
4. **广度优先 + 预算熔断**：先让全部产物以最小合格版本存在，再对高价值分支加深。模型请求 >48 次或运行 >700 秒时立即停止新增处理，用现有中间结果收尾。每次写 result.json 都覆盖为最新完整状态。
5. **渲染必须真实执行**：SVG 由脚本真实生成后，必须运行 render_preview.py 得到 PNG 并经像素校验（非空白占比 ≥0.01）。无渲染器时如实记 no_renderer，绝不伪造渲染证据；SVG 本身照常交付。
6. **最终自检**：`python $SD/build_result.py verify --case /input/case.json --out /app/output/result.json` 必须输出 verdict=pass 才算完成；不过先修复再交付。
7. **失败也要交付**：中断/失败时仍写 result.json（status=failed，写明中断位置与已完成部分），绝不让 /app/output 缺 result.json。

## 流程（5 步线性执行）

脚本定位：`SD=$(find /skills -type d -name scripts 2>/dev/null | head -1)`；为空则用相对路径 `./scripts`。绝不假设具体安装路径。

### Step 0 — 读契约、落骨架（最先做，1 次脚本）
```bash
SD=$(find /skills -type d -name scripts 2>/dev/null | head -1); SD=${SD:-./scripts}
cat /input/case.json
python $SD/build_result.py init --case /input/case.json --out /app/output/result.json
```
constraints.json 记：导图用途（论文梳理/实验方案/项目计划/会议纪要）、期望深度、格式偏好。

### Step 1 — 材料盘点与事实台账（2 次脚本）
```bash
python $SD/extract_materials.py --input /input --outdir /app/work/extracted
python $SD/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
```

### Step 2 — 要点抽取与结构设计（1-2 次响应）
产出四份中间文件到 /app/work：
- coverage.jsonl 逐材料抽要点：`{"sid","locator","point","kind":"core_concept|question|method|evidence|conclusion|task|risk|decorative"}`。装饰性套话标 decorative 不入图并给理由；**每个非装饰要点都要有节点落点**。
- tree.json：`{"root","nodes":[{"id","parent","label","type","note"}]}`。节点 ≤8 字短语、同级粒度一致、层级 ≤4、核心结论上提。
- relations.jsonl 跨分支关系：`{"rel","from","to","type":"causal|dependency|contrast|support|conflict|temporal","basis","evidence_state":"fact|summary|inference"}`。**材料没说的因果不连**。
- node_evidence.jsonl 证据挂接：全部带数字节点、全部结论节点、全部冲突/支持关系必须挂（locator+逐字摘录 ≤30 字）。

### Step 3 — 生成、渲染、机检（4 次脚本）
```bash
python $SD/map_build.py --tree /app/work/tree.json --relations /app/work/relations.jsonl --evidence /app/work/node_evidence.jsonl --outdir /app/output
python $SD/render_preview.py --svg /app/output/mindmap.svg --outdir /app/output/previews
python $SD/map_check.py --coverage /app/work/coverage.jsonl --tree /app/work/tree.json --relations /app/work/relations.jsonl --evidence /app/work/node_evidence.jsonl --out /app/output/map_check.json
```
map_build 写盘自检（四文件非空 + SVG 良构）记入 build_report.json；render_preview 输出像素校验证据到 render_log.json。map_check fail 项（覆盖缺口/悬空引用/缺证据）修复一轮后重跑。

### Step 4 — 嵌入组装 + 自检（2 次脚本）
```bash
python $SD/build_result.py embed --case /input/case.json --out /app/output/result.json \
  --embed-file /app/work/tree.json:mindmap_tree \
  --embed-file /app/work/relations.jsonl:mindmap_relations \
  --embed-file /app/work/node_evidence.jsonl:node_evidence \
  --embed-file /app/output/outline.md:deliverable_content \
  --embed-file /app/output/previews/render_log.json:render \
  --artifact /app/output/mindmap.mm --artifact-md /app/output/outline.md \
  --consistency /app/output/map_check.json \
  --set status=complete --changelog '取舍与修改记录'
python $SD/build_result.py verify --case /input/case.json --out /app/output/result.json
```
verify 输出 verdict=pass 才结束；否则按提示修复。

## 异常处置

| 情形 | 处置 |
|---|---|
| 材料是扫描件 | OCR 后抽取；uncertainty 注明 |
| 要点相互矛盾 | 两要点都入图 + conflict 关系标注，不擅自合并 |
| 节点爆炸（>60） | 聚合同粒度兄弟节点；coverage 仍逐条对账 |
| 无明显中心主题 | 按任务类型选根（研究问题/项目目标/会议主题） |
| 无渲染器 | render_log 如实记 no_renderer；SVG+.mm+.opml+outline 照常交付 |
| 脚本缺失/报错 | 全部异常捕获、如实登记；用现有中间结果走协议第 4/7 条（可手写最小 .mm XML 兜底） |
| 接近预算上限 | 立即收尾：已有 tree/outline 组装 result.json，缺口写 uncertainty |

## 交付自查清单

- [ ] result.json 含 case_id 与 output_contract 全部键；mindmap_tree/mindmap_relations/node_evidence/deliverable_content/render 五键全部嵌入
- [ ] coverage_gaps=0（非装饰要点全有落点）；decorative 有理由
- [ ] 节点带类型、≤8 字、层级 ≤4；关系带类型与依据；材料外连接为零
- [ ] 数字/结论/冲突节点全部挂账（evidence_missing=0），locator 可回原文
- [ ] PNG 渲染成功且有 nonwhite_ratio 证据；无渲染器时 render_log 如实
- [ ] verify verdict=pass；status/uncertainty/changelog 如实
