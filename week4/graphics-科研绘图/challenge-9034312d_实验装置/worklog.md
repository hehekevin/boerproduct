# worklog — challenge-9034312d（实验装置与技术路线图）final 增强

基线：bohrium-week3-plotfix/challenge-9034312d/submission（72.67 分版本 + plotfix 增强，SKILL.md 108 行）。
本次按 83 分公式逐要素查缺后的增量增强，产出目录 bohrium-week3-final/challenge-9034312d/submission/。

## 缺失要素清单（对照 83 分公式 + 83 分样本 ppt-710fbc72）

83 分样本的关键差异：拥有**专门机检脚本**（scripts/pptx_verify.py，268 行）产出 verify_report.json 嵌入 result.json，而非纯人工自检。本基线包对照后缺三件事：

1. **SVG 分层可编辑性无机检**：分层/语义 id/文字可编辑/legend 齐全全靠 Agent 自查清单，评分器无法机械复核。
2. **渲染校验证据未结构化嵌入**：--check 输出（宽/高/nonbg_ratio）只在终端打印，未以 render_evidence 字段落进 result.json——"打印了事"违反公式要素3。
3. **编辑工单无逐元素 diff 证据**：source-preserving edit 只要求"写 edit 记录"，无机械 diff 证明未触碰元素真的没变。

## 补强点（保留基线全部机制，只做增量）

1. **新增 scripts/svg_verify.py**（纯标准库 xml.etree，约 175 行）：
   - 机检模式：`svg_verify.py figure.svg --map content_map.json --out verify_report.json`，五项逐条 `{item, template_value, applied, match}`：layer-* 分层 ≥4 类 / 语义 id（part-*/edge-*/stage-*）存在且唯一 / 文字均为 `<text>`（无位图文字）/ legend 层非空 / content_map ↔ SVG id 双向一致（in_svg_not_in_map、in_map_not_in_svg 逐条列出）。fail 冒泡退出码。
   - diff 模式：`svg_verify.py edited.svg --diff original.svg`，对**所有带 id 元素**（含图层）逐条输出 `{element_id, changed, before, after}`；changed=false 构成 source-preserving 保留证据，changed=true 应能对应工单/content_map 依据。整份 edit_diff 可嵌入 result.json。
2. **SKILL.md 步骤④**：渲染后强制跑 svg_verify.py 机检；`--check` 输出逐字记入 render_evidence；新增"渲染证据嵌入"硬约束（render_evidence: {png_width, png_height, nonbg_ratio, pdf_bytes, checker}）；编辑工单强制 --diff 并整份嵌入 edit_diff。
3. **SKILL.md 步骤⑤**：compliance_checks 从五项扩为六项（新增⑥分层可编辑性机检 + edit_diff 嵌入）。
4. **自检清单**：交付类新增三条（机检报告嵌入 / render_evidence 嵌入 / edit_diff 嵌入且 unchanged 数量符合预期）。
5. **README.md**：同步可核验性设计、脚本用法、文件清单。
6. 行数：SKILL.md 108 → 114 行（≤150 合规）。

## 双测证据（本地实测）

- **正例**：合成 figure.svg（2 部件 + 1 连接 + 4 层 + legend）+ content_map.json（3 条）→ `svg_verify.py --map` → status=pass，fail_count=0，exit=0。
- **反例**：注入脏数据（删 layer-legend 层 + 把 edge-01 篡改为 edge-XX）→ 机检抓到 legend_present=False、map_consistency=False，fail_count=2，exit=1。
- **编辑 diff 正例**：只改 layer-labels 内文字 → diff 模式报 total=8 / changed=1（layer-labels）/ unchanged=7，其余图层与部件全部 preserved——即 source-preserving 机械证据。
- **发现并修复的盲点**：diff 初版只比对 part-*/edge-*/stage- 前缀元素，layer-labels 的修改抓不到；已改为比对所有带 id 元素（含图层 id），重测通过。正例回归重跑仍 pass。
- 渲染脚本 render_svg.py 与基线一致未改动（基线已实测其回退链与 --check）。

## 产出文件（5 个，未提交）
- SKILL.md（114 行）
- scripts/render_svg.py（基线复制，未改）
- scripts/svg_verify.py（新增）
- README.md（同步更新）
- worklog.md（本文件）

## 风险评估
- 新增机检脚本不改变绘图执行路径，只在步骤④追加校验调用；正/反例均实测通过。
- content_map.json 的落盘格式（步骤③已要求 content_map 存在）与 --map 参数对齐；若运行时未落盘 map 文件，机检退化为前四项（脚本对 --map 缺省容错），SVG 编辑仍受 layer/id/text 检查保护。
