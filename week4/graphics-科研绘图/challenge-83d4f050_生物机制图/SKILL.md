---
name: bio-pathway-figure
description: >
  Biological mechanism & pathway diagram Skill. Reads /input/case.json + task.md
  (+ artifacts/figure-workorder.json), extracts entities (gene/protein/complex/
  receptor/ligand/cell) and interactions (activation/inhibition/phosphorylation/
  ubiquitination/binding/recruitment/translocation) with verbatim evidence quotes,
  renders a layered editable SVG (compartment bands extracellular-membrane-
  cytoplasm-nucleus, transmembrane receptors on the membrane midline, semantic
  arrow styles: arrow/T-bar/circle/square/diamond) via pathway_svg.py, exports
  PNG(300dpi)/PDF via render_svg.py renderer fallback chain, and mechanically
  validates entity naming ([A-Za-z] regex, never isalpha which passes CJK chars),
  edge-type vs arrow-style, direction (vector dot product), compartment placement,
  and legend-vs-encoding consistency with validate_pathway.py. Writes
  /app/output/result.json with all output_contract fields, content_map (every
  node/edge traced to source), reproducibility block, and gain_evidence /
  efficiency (same-validator ablation A/B + pollution counterexample injection,
  machine-judged). All failure paths exit 0; never fabricates sources or data.
---

# bio-pathway-figure：生物机制图与通路图（可编辑 SVG + 机械校验）

核心承诺：**图上每个实体、每条边都逐字回证到输入材料；相互作用语义映射为可区分箭头样式；区室/跨膜位置按约束布局；图例与图面样式一一对应；全部机械校验逐条写入 compliance_checks（match=false 必修或登记）；交付分层可编辑 SVG + PNG(300dpi)/PDF 导出；gain_evidence 由同输入消融两臂 + 污染反例注入真跑得出。** 任何失败都如实登记（材料缺失/无法判断/运行失败三类分写），不编造、不静默改判。

## 0. 强制执行协议（最高优先级）

1. **读完 `/input/case.json`、task.md、工单（artifacts/figure-workorder.json）后第一件事写 `/app/output/result.json` 骨架**：`output_contract` 以 case.json 实际声明为准（预期 `["case_id","status","editable_source","export_artifact","content_map","compliance_checks","exceptions"]`），读到什么抄什么，一个键不缺；暂无内容填 `"unknown"`/`[]`，`status="partial"`。此后每次实质进展增量回写。
2. **预算硬闸**：模型请求超 48 次（上限 64）或运行超 700 秒（上限 900）立即收尾填 result.json。
3. **失败也写 result.json**：崩溃/缺环境/缺数据时写含 `status="partial"` + exceptions 完整骨架；材料缺失、无法判断、运行失败三类在 exceptions 分别说明；禁止编造软件状态或科学数据。
4. **所有失败路径 exit 0**：脚本 verdict 写 JSON 不写退出码；校验 FAIL 不是终止，是修复指令。
5. 写盘前确认 `json.loads` 可解析、`case_id` 与输入一致。

## 1. 线性六步主流程

### 步骤① 读输入（1-2 请求）
- 读 case.json：抄 `case_id` 与 `output_contract` 全键。
- 读 task.md + 工单：确认是**生成**还是**编辑**（source-preserving edit）、要求的通路/实体/导出格式。
- 定位机制材料原文（PDF/文本）：材料是实体、关系、方向、数据的**唯一合法来源**；不凭记忆补造通路。

### 步骤② 写 result.json 骨架（1 请求）
按协议第 1 条立即落盘，之后增量回填。

### 步骤③ 实体/关系抽取 → pathway_spec.json（3-5 请求）
从材料逐句抽取，写 `/app/work/pathway_spec.json`：
- `nodes`: `{id, label, type(gene|protein|receptor|ligand|complex|enzyme|cell|metabolite), compartment, source, evidence}`——`evidence` 必须是材料**逐字引文**；基因/蛋白书写区分（基因斜体、蛋白正体）；实体符号含 ASCII 字母。
- `edges`: `{id, src, dst, type(activation|inhibition|phosphorylation|ubiquitination|binding|translocation|recruitment), evidence}`——**方向按原文陈述**（主语→宾语），"A promotes B"=A→B activation；模糊关系登记 exceptions 不硬画。
- `compartments`: 按材料生物学层级（默认 `["extracellular","membrane","cytoplasm","nucleus"]`）；受体标 `membrane`（跨膜）。
- 命名陷阱：判断"实体符号是否拉丁字母"用 `[A-Za-z]` 正则，**禁用 `isalpha()`**（`"激".isalpha()` 为 True 会漏检）。

### 步骤④ 渲染 + 导出（2-4 请求）
先定位脚本（标志文件校验式命中，禁 `find|head -1`）：
```bash
SCRIPTS=""; for p in /skills/weekly-skill/scripts ./scripts /app/work/scripts; do
  [ -f "$p/pathway_svg.py" ] && grep -q "bio-pathway-figure/v1" "$p/pathway_svg.py" && SCRIPTS="$p" && break; done
```
```bash
python3 "$SCRIPTS/pathway_svg.py" /app/work/pathway_spec.json --out /app/output/figure.svg
python3 "$SCRIPTS/render_svg.py" /app/output/figure.svg --outdir /app/output --png --pdf --dpi 300
python3 "$SCRIPTS/render_svg.py" --check /app/output/figure.png
```
- 产物：分层 SVG（`<g id="compartment-*"/"node-*"/"edge-*"/"legend">`，图元带 `data-source`/`data-evidence`）+ PNG(300dpi) + PDF。
- 渲染器回退链 cairosvg→rsvg-convert→inkscape→chrome headless 全失败：SVG 保留（仍可编辑），PNG/PDF=unknown 登记 exceptions。
- **编辑工单**：只改 spec 中工单要求的节点/边/标签/样式，记 `edit`（旧值→新值+原因），重跑步骤④。

### 步骤⑤ 机械校验（2-3 请求，match=false 必修）
```bash
python3 "$SCRIPTS/validate_pathway.py" /app/work/pathway_spec.json /app/output/figure.svg \
  --corpus <材料目录或文件> --report /app/work/validate_report.json
```
六组校验逐条明细：entity_checks（存在/标签/区室属性/ASCII 命名/引文逐字回证）、edge_semantics（type 属性/箭头样式与语义映射一致/虚线约定/引文）、direction_checks（data-to−data-from 与 src→dst 中心向量点积>0）、compartment_checks（区室带顺序=细胞外→膜→胞质→核；节点中心在带内；膜上节点骑膜带中线）、legend_checks（图例项键=图面实际使用集合、配色一致）、export_checks（PNG 像素检查）。任一 match=false：改 spec 重渲染重校验；修不好 → status=partial + exceptions。

### 步骤⑥ 填充 result.json 全字段（2-3 请求）
```json
{
  "case_id": "<抄自 case.json>", "status": "complete | partial",
  "editable_source": {"svg": "/app/output/figure.svg", "spec": "/app/work/pathway_spec.json",
    "rerun_command": "python3 <scripts>/pathway_svg.py /app/work/pathway_spec.json --out /app/output/figure.svg"},
  "export_artifact": {"png": {"path": "/app/output/figure.png", "dpi": 300, "pixel_check": "CHECK OK nonbg_ratio=<实测>"},
    "pdf": {"path": "/app/output/figure.pdf"}, "font": "Helvetica/Noto Sans CJK/Microsoft YaHei"},
  "content_map": {
    "nodes": [{"element_id": "EGFR", "label": "EGFR", "type": "receptor", "compartment": "membrane", "source": "<材料:行/页>", "evidence": "<逐字引文>", "color": "#C44E52"}],
    "edges": [{"element_id": "e02", "src": "EGFR", "dst": "GRB2", "type": "recruitment", "arrow_style": "marker-arrow+dashed", "evidence": "<逐字引文>"}]},
  "compliance_checks": {"entity_checks": [], "edge_semantics": [], "direction_checks": [],
    "compartment_checks": [], "legend_checks": [], "export_checks": []},
  "reproducibility": {"spec_fingerprint": "11 nodes x 11 edges sha256=<实测>", "deps": "python3.8+ 标准库",
    "export_params": "svg+png(300dpi)+pdf", "manual_edits": "无", "rerun_command": "<同 editable_source>"},
  "exceptions": [], "edit": {}
}
```
**compliance_checks 直接抄 validate_report.json 的 checks 分组**（含逐条 match）；`content_map` 与 spec 双向一致；任何 match=false 不得删除键，如实保留并登记 exceptions。

### 步骤X 增益证据（回填 result.json，最后执行）
```bash
python3 "$SCRIPTS/gain_evidence.py" --spec /app/work/pathway_spec.json \
  --corpus <材料目录或文件> --result /app/output/result.json --outdir /app/output --write
```
同输入消融两臂（全量臂 vs `--ablate edge_semantics,compartment,legend` 消融臂），同一校验器各跑一遍，FAIL 数差 `fail_count_diff` 是机器判定增益；污染反例注入副本（语义反转/区室错位/图例删除）必须被抓到（caught=true）；写入 `gain_evidence` 与 `efficiency` 两键（本包唯一写入者）。

## 2. 异常处理速查

| 情况 | 处置 |
|---|---|
| 材料缺失/无法判断/运行失败 | exceptions 三类分别说明；已产出的 SVG/result 照常交付 |
| 关系方向模糊（原文未指明促进/抑制） | 登记无法判断不硬画；有把握才入 edges |
| 同名基因/蛋白歧义 | 按材料上下文消歧并在 node.source 注明；消歧不了标 partial |
| 图例项≠使用集合 / 箭头样式错 / 区室错位 / 方向反 | 改 spec 重渲染重校验；修不好 status=partial + exceptions |
| 渲染器全失败 | SVG 保留，PNG/PDF=unknown + exceptions（renderer_unavailable） |
| 中文变方框 | 用环境 font-discovery 找 CJK 字体；不行改英文标签 + exceptions |
| spec 过大写 result.json 被截断 | 分批增量写（每批 ≤1500 字），写完验 json.loads |
| 预算触顶（48 请求/700 秒） | 立即收尾，未完成项 unknown，status 如实 |

## 3. 自检清单（收尾前逐项过）

- [ ] result.json 可 json.loads；键与 output_contract 完全一致（不删键）；case_id 一致；status 如实
- [ ] 每个节点/边 element_id 可在 SVG 中找到对应 `<g id=...>`，evidence 为材料逐字引文且回证通过
- [ ] 箭头样式与关系类型一一对应；方向点积>0；区室带顺序正确；膜上节点骑膜中线
- [ ] 图例项键=图面实际使用集合，配色一致；PNG 过 --check（非空+尺寸），PDF 存在（或 unknown+exceptions）
- [ ] 实体符号命名用 [A-Za-z] 正则校验（未用 isalpha）
- [ ] gain_evidence 两臂 FAIL 数差与污染反例 caught=true 为本次真跑数字；efficiency 已回填
- [ ] exceptions 覆盖材料缺失/无法判断/运行失败三类（如适用）；全部文本 UTF-8

## 4. 设计要点（为什么这样做）

- **逐字回证优先于画得像**：每条 evidence 是材料原文引文且校验器做空白归一后的子串匹配——画错一处等于错误论断，回证让"像而不对"无所遁形。
- **语义→图元映射可区分**：箭头/T棒/圆点/方点/菱形/虚线七种样式与激活/抑制/磷酸化/泛素化/结合/转运/募集一一对应，校验器按同表核对 marker 与虚线，杜绝"随意连线"。
- **区室即布局语义**：受体—胞内—核层级由带状区室自上而下表达，跨膜受体骑膜带中线，布局本身传达机制结构，方向用向量点积机器判定。
- **同校验器消融对照**：消融臂模拟基础 Agent 退化画法，FAIL 数差为机器判定而非自述；污染反例注入证明校验器真有判别力。
