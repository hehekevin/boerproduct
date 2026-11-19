# worklog — bio-pathway-figure（第4周「生物机制图与通路图」challenge-83d4f050）

## 版本沿革
- 本版为第4周首版，骨架方法论沿用第3周绘图赛道冠军包（challenge-1bd90d8a，83 分公式：协议置顶/机械校验逐条明细/增益真跑证据），SVG 渲染管线直接复用 render_svg.py。
- 本周题面明确「SVG 手写渲染」，故主渲染器改为 spec→分层 SVG 的 pathway_svg.py（无 matplotlib）。

## 领域设计（对题面五个突破方向的覆盖）
1. **实体与命名规范**：type 七分类（gene/protein/receptor/ligand/complex/enzyme/cell）；命名用 `[A-Za-z]` 正则校验——显式规避 `isalpha()` 汉字陷阱（`"激".isalpha()==True` 会漏检）；每节点带 source+evidence。
2. **相互作用语义**：七种关系→七种可区分箭头（实线箭头/T棒/圆点/方点/菱形/空心箭头/虚线），渲染与校验共用同一映射表。
3. **通路方向与拓扑**：区室带自上而下（细胞外→膜→胞质→核），跨膜受体骑膜带中线；边方向用向量点积机器判定。
4. **图例与数据编码**：图例项键集合==图面实际使用集合（边类型/节点类别），色块配色逐项核对。
5. **可编辑源文件与导出**：分层命名 `<g id="compartment-*/node-*/edge-*/legend">` + `data-source`/`data-evidence` 属性，矢量编辑器可逐层改标签重导出；PNG(300dpi)+PDF 经回退链导出并像素检查。

## 增益层实现（全部真跑，非文字声明）
- `--ablate edge_semantics,compartment,legend`：同输入消融臂，模拟基础 Agent 退化画法。
- 同一校验器（validate_pathway.py）对两臂各跑一遍，FAIL 数差为机器判定。
- 污染反例注入副本（语义反转/区室错位/图例删除，按 spec 可注入项执行），校验器必须抓到。
- 基线对照：不做证据登记路径的需人工核对条目数 vs 本包逐条登记后的条目数。
- 唯一写入者约定：仅 gain_evidence.py 写 result.json 的 `gain_evidence`/`efficiency` 两键。

## 本地自测真实对照数字（examples/ 示意输入，Python 3.12 Windows）
- 全量臂：`fail_count=0`，校验项 141 条全过（entity/edge_semantics/direction/compartment/legend 全 match=true）
- 消融臂：`fail_count=21`；`fail_count_diff=21`（机器判定增益）
- 污染反例：注入 2 处错画（边 e01 语义反转 binding→inhibition、EGF 区室错位），`fail_count=6`，`caught=true`
- 基线对照：不做证据登记时需人工核对 74 项 → 本包登记后 0 项
- 像素检查：合成 400x300 PNG 实测 `CHECK OK nonbg_ratio=0.67`（本机无渲染器，PNG 为合成验证件）
- 失败路径 exit 0 实测：spec 缺失 / spec 坏 JSON / argparse 错误 / 渲染器全失败（RENDER DEGRADED）/ --check 文件不存在，均 exit 0
- 汉字陷阱实测：node label 改「信号分子」→ naming_ascii_regex 抓到（match=false）
- SKILL.md 127 行（≤150）；YAML frontmatter 合规

## 诚实边界
- 本机无 SVG 渲染器，PNG/PDF 导出在评测沙箱按回退链真跑；本机仅以合成 PNG 验证了像素检查逻辑，未验证真实渲染产物像素。
- 图例项删除类污染仅在 spec 显式给出 `legend.edge_types` 时注入（示例 spec 图例为派生，实际注入 2 处）。
- 颜色→表达量等数值编码映射只做图例一致性校验，不做数值统计结论（题面归相邻课题）。
- 方向点积校验依赖渲染器写入的 data-from/to 与节点中心几何；自反馈环（src==dst）只查存在性，不查几何方向。
- examples 为示意输入非正式案例；三个正式案例的真实表现以平台 Harness 运行为准。

## 交付物（8 文件，未提交，未动 git）
- SKILL.md（127 行）/ README.md（生态十项+自检清单）/ worklog.md（本文件）
- scripts/：pathway_svg.py、validate_pathway.py、render_svg.py（复用第3周+标志行）、gain_evidence.py
- examples/：example-spec.json、example-source.txt（均标注示意，非正式案例）
