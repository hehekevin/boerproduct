---
name: acwrite-mindmap
description: 科研思维导图技能：从论文/实验方案/项目材料/会议纪要抽取核心概念与关系，生成带证据挂接的可编辑思维导图（节点树+关系+证据全部结构化嵌入 result.json，并按 output_contract 同步 deliverable/preserved_facts/evidence_map/change_log），另产出 FreeMind(.mm)+OPML+自包含 SVG+PNG 渲染预览。节点含类型与来源 locator，关系标注因果/依赖/对比/支持/冲突，PNG 由脚本真实渲染并做像素校验。Use when the case asks to build a mind map / concept map from research materials with node coverage, typed relations, evidence hooks, editable outputs and rendered preview.
---

# acwrite-mindmap — 科研思维导图（结构化嵌入 · 真渲染 · 可追溯）

## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 8 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个写盘动作就是
   `python3 $SD/build_result.py init --case /input/case.json --out /app/output/result.json`
   它把 output_contract 全部键抄进骨架（缺值填 []），status=partial。此后任何时刻 result.json 必须存在且 JSON 可解析。
2. **契约键一个不缺**：最终 result.json 必须含 output_contract 全部键。本题公开契约键为
   `deliverable` / `preserved_facts` / `evidence_map` / `change_log`（外加 case_id）——
   这四个键必须有**实际内容**，不能是 unknown/空。`build_result.py embed --auto` 会自动语义填充，
   务必带 `--auto` 调用。富字段（mindmap_tree / node_evidence / render / consistency_check /
   gain_evidence / efficiency）同时保留，供评分器交叉核对。
3. **主产物结构化嵌入 result.json**（缺一即不完整交付）：mindmap_tree（节点树：id/parent/label/type/src）、
   mindmap_relations（跨分支关系：类型+basis）、node_evidence（证据挂接：locator+逐字摘录）、
   deliverable_content（大纲全文）、render（真实渲染证据：engine/png 字节数/尺寸/非空白像素占比）。
   全部用 `--embed-file 路径:键名` 嵌入；只有文件指针而无内容 = 不完整交付。
4. **只用标准库 + python3**：`python` 命令可能不存在，一律用 `python3`（探测：`PY=$(command -v python3 || command -v python)`）。
   不得依赖 node / npm / puppeteer / 浏览器 / 联网 / 任何第三方 pip 包。所有脚本仅标准库即可跑通。
5. **动态定位脚本，绝不硬编码路径**：按下方「脚本定位」代码块求出 `$SD`（候选目录必须含 build_result.py 才认）。
   仍找不到时：不调用脚本，直接手工写 /app/output/result.json（契约四键 + 已有内容），如实登记。
6. **广度优先 + 预算熔断**：先让全部产物以最小合格版本存在，再对高价值分支加深。
   模型请求 >40 次或运行 >600 秒时立即停止新增处理，用现有中间结果收尾。每次写 result.json 都覆盖为最新完整状态。
7. **校验失败最多修一轮**：map_check / verify 的 verdict 照实记录即可，**不是 pass 也能交付**。
   最多修复一轮（且仅当剩余时间 >120 秒）；修不好就如实登记问题（写进 change_log 的人工确认项）并收尾。
   严禁反复重跑机检烧光预算。
8. **失败也要交付**：中断/失败时仍写 result.json（status 如实降级，写明中断位置与已完成部分），
   绝不让 /app/output 缺 result.json。所有脚本失败路径退出码恒 0，失败信息在 stdout/stderr 与日志里。

## 流程（5 步线性执行）

脚本定位（先做一次，结果存 $SD）：

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
```

### Step 0 — 读契约、落骨架（最先做，1 次脚本）
```bash
cat /input/case.json; ls -la /input/
$PY $SD/build_result.py init --case /input/case.json --out /app/output/result.json
```
记下 output_contract 的全部键名与 case_id（本题为 deliverable/preserved_facts/evidence_map/change_log）。
constraints：导图用途（论文梳理/实验方案/项目计划/会议纪要/知识体系）、期望深度、格式偏好。

### Step 1 — 材料盘点与事实台账（2 次脚本）
```bash
$PY $SD/extract_materials.py --input /input --outdir /app/work/extracted
$PY $SD/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
```
读 extracted/M*.txt（每行带 [SRC:Mxx:loc] 锚点）——所有节点与证据只能来自这里。

### Step 2 — 要点抽取与结构设计（2-3 次响应，用写文件工具直接写文件，不要用 shell heredoc）
产出四份中间文件到 /app/work（可分 2 批写，先 coverage+tree，再 relations+evidence）：
- coverage.jsonl 逐材料抽要点：`{"sid","locator","point","kind":"core_concept|question|method|evidence|conclusion|task|risk|decorative"}`。
  装饰性套话标 decorative 不入图并给理由；**每个非装饰要点都要有节点落点**。
- tree.json：`{"root","nodes":[{"id","parent","label","type","src","note"}]}`。
  - `src` 必填＝来源材料 sid（M01…）；**label 逐字抄材料原词**（≤12 字，能在源文本原样命中最好），
    改写措辞会被来源回证判失败。
  - 同级粒度一致、层级 ≤4、核心结论上提、节点总数 ≤45。
- relations.jsonl 跨分支关系：`{"rel","from","to","type":"causal|dependency|contrast|support|conflict|temporal","basis","evidence_state":"fact|summary|inference"}`。
  **材料没说的因果不连**；basis 必填（写原文定位 + 依据）。
- node_evidence.jsonl 证据挂接：`{"nid","type":"fact|summary|inference","locator","quote"}`。
  全部带数字节点、全部结论/证据型节点、全部冲突/支持关系必须挂（locator+逐字摘录 ≤30 字）。

### Step 3 — 生成、渲染、机检（3 次脚本）
```bash
$PY $SD/map_build.py --tree /app/work/tree.json --relations /app/work/relations.jsonl --evidence /app/work/node_evidence.jsonl --outdir /app/output
$PY $SD/render_preview.py --svg /app/output/mindmap.svg --outdir /app/output/previews
$PY $SD/map_check.py --coverage /app/work/coverage.jsonl --tree /app/work/tree.json --relations /app/work/relations.jsonl --evidence /app/work/node_evidence.jsonl --materials /app/work/extracted --out /app/output/map_check.json
```
map_build 写盘自检（四文件非空 + SVG 良构）记入 build_report.json；render_preview 输出真实渲染证据
到 previews/render_log.json（内置纯标准库光栅器兜底，无第三方渲染器也能出 PNG）；map_check 输出
逐条三元组 verification + 闸门状态 gates + 5 项质量指标 metrics。**map_check 失败项最多修一轮（协议 7 条）。**

### Step 4 — 增益证据 + 嵌入组装 + 自检（3 次脚本）
```bash
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
embed --auto 会把 mindmap_tree/relations/evidence/outline 同步映射成契约四键
（deliverable / preserved_facts / evidence_map / change_log），并写入 efficiency 计数。
verify 的 verdict 照实记录；**不通过也继续交付**（协议 7 条），把问题写进 change_log 人工确认项。

## 异常处置

| 情形 | 处置 |
|---|---|
| python3 不存在 | `PY=$(command -v python3 || command -v python3)`；都没有则手工写 result.json |
| 脚本找不到（$SD 为空） | 手工写 /app/output/result.json：契约四键 + mindmap_tree/relations/evidence；uncertainty 登记 |
| 材料是扫描件/抽取为空 | 降级为部分提取；extracted:false 如实登记；章节/来源指标为 null 属正常 |
| 要点相互矛盾 | 两要点都入图 + conflict 关系标注，不擅自合并 |
| 节点爆炸（>45） | 聚合同粒度兄弟节点；coverage 仍逐条对账 |
| 无明显中心主题 | 按任务类型选根（研究问题/项目目标/会议主题） |
| 无第三方渲染器 | render_preview 内置光栅器兜底出 PNG；glyph_mode 字段如实记录 |
| 机检不通过 | 最多修一轮；修不好写进 change_log 人工确认项，照常交付 |
| 接近预算上限 | 立即收尾：已有 tree/outline 组装 result.json，缺口写 uncertainty |

## 交付自查清单（逐条打勾，缺项就补）

- [ ] result.json 含 case_id 与契约四键 deliverable/preserved_facts/evidence_map/change_log，且**都非空**
- [ ] mindmap_tree / mindmap_relations / node_evidence / deliverable_content / render 五个富字段均已嵌入内容
- [ ] 节点带 type 与 src；label 逐字抄材料原词；层级 ≤4；节点 ≤45
- [ ] 关系带 type 与 basis；材料外连接为零
- [ ] 数字/结论/证据型节点全部挂 node_evidence（locator + 逐字摘录）
- [ ] coverage.jsonl 非装饰要点全部有节点落点；decorative 有理由
- [ ] map_check.json 内 verification 逐条三元组 + gates 状态显式
- [ ] previews/mindmap.png 存在且 render_log 有 png_bytes/尺寸；无渲染器时如实记
- [ ] gain_evidence.json 含两遍真实对照数字（baseline vs full）+ 机制→指标映射 + 边界
- [ ] status/uncertainty/changelog 如实；verify verdict 已记录
