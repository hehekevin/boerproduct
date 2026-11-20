---
name: deck-edit-skill
description: 学术PPT生成与定点编辑技能：从论文/科研材料生成整稿，或对已有deck做source-preserving定点编辑（改文字/压缩/扩写/换受众/换语言/换图/改备注），全程页级证据映射、逐页diff、版本留痕与导出渲染校验，并输出可对照的增益记录。Use when the task asks to generate an academic slide deck from a paper AND/OR edit slides across rounds (学术汇报PPT、改某页、换受众改写、图表替换、版本回退、导出不塌版).
---

# deck-edit — 学术PPT生成 + 定点编辑 + 全程可核验

三件套缺一不可：① 可编辑 `deck.pptx`；② 页级证据映射 `evidence_map.jsonl`；③ 渲染与版本记录（`deck.pdf` + `previews/*.png` + `layout_log.json` + `verify_report.json` + `evidence_check.json` + `versions.jsonl` + 逐页 diff）。

## 0. 强制执行协议（置顶，每案例最先做，顺序不可换）

1. **抄契约**：`cat /input/case.json`，把 `output_contract` 的**全部字段名原样抄下** + `case_id`。终版 result.json 必须包含这些字段（原名）+ `case_id`，一个不缺。
2. **落骨架**：立即写 `/app/output/result.json`——含 case_id 与全部契约字段（值 null）、`status="in_progress"`。此后每步回填；**即使超时/失败，/app/output 下也必须有合法 result.json**。
3. **广度优先**：先打通"提取→页计划→建deck→校验→渲染→result.json"全链路交部分成果，再回头加深质量。禁止单页反复打磨而全链路未通。
4. **自熔断**：平台 64 请求/900 秒/16384 token，**自设 48 请求/700 秒**——超线立即收尾回填 result.json，停新动作。
5. **写盘自检**：每次写 result.json 前 `python -c "import json;json.load(open('/app/output/result.json',encoding='utf-8'))"`；JSON 非法 = 全盘丢分。
6. **状态四级诚实**：`in_progress` / `partial`（写清缺什么、为什么）/ `failed`（写原因，仍交 result.json）/ `complete`。不编造渲染状态、论文数据或软件状态。

## 1. 五步主流程（线性，每步 1 次响应 + 1-2 次脚本调用）

### Step 1 — 读契约、判路径
```bash
ls -la /input/ && cat /input/case.json
```
- 按 §0-1、§0-2 落契约与骨架；页数上限/时长/受众/模板路径记入 `/app/work/constraints.json`。
- 判路径：起点 pptx/要求改既有页 → 编辑路径（2b/3b）；论文/提纲从零生成 → 生成路径（2a/3a）；可串联。

### Step 2a — 材料提取（生成路径）
```bash
python scripts/extract_pdf.py <材料.pdf> --outdir /app/work/extracted --page-render
```
- 产出 `paper_text.txt`（`===== PAGE n =====` 锚点，evidence 定位用页码）、`figures/`、`manifest.json`。
- `scanned:true` → OCR，locator 用页码并写 uncertainty。无 PyMuPDF → 自动退 `pdftotext`（同样写 PAGE 锚点），此时无嵌图，改用平台 pdf-render-tool 整页渲染。
- `--page-render`：正文提到 Fig./图 n 但无位图可取的页，整页渲染为 `figures/page_pN.png`，evidence 标 `figure_mode:"page_render"`。**禁止占位图、禁止凭空重绘数据图**。
- 材料是 md/docx/txt → 直接读，locator 用章节标题。
### Step 2b — 盘点起点 deck（编辑路径）
```bash
python scripts/pptx_verify.py <起点.pptx> /dev/null 2>/dev/null; echo "exit=$?"; sha256sum <起点.pptx>
```
- 每页现有标题/要点/备注/图 → `/app/work/base_deck.json`；建初始 evidence_map（对不上论文的页标 uncertainty）。打不开则如实记录并改走源材料重建。

### Step 3a — 页计划 + deck.json（生成路径）
- 主线：问题 → 方法 → 结果 → 限制/结论；**按贡献排页序，不按章节搬运**。每页字段：`{"no","role"(hook/problem/method/result/limitation/conclusion/backup),"claim","layout","title","bullets","figure","notes"}`（schema 见 `examples/example-deck.json`，标注示意）。
- 一页一主张；要点 ≤5 条、每条 ≤40 字；页数超限先砍方法细节页，**不砍结果页与限制页**，取舍记 changelog。
- `notes`（40-600 字）三件套：①承上过渡 ②本页强调点+证据强度 ③一个可能被追问的问题及应对。
- **从论文到成稿的可复现映射**（生成路径必须留痕）：每个 bullet 指向 `evidence_map` 中该页至少一条 `quote`；数字/单位一律逐字，不改写不取整。
- `/app/work/evidence_map.jsonl` 每行：`{"slide_no","claim","type":"figure|table|section|quote","locator":"Fig.1 p.3 / §3.2 / Table 2","quote":"原文逐字","figure_mode":null}`。
### Step 3b — 编辑定位（编辑路径，source-preserving）
- 只改指令点名的页与字段；**其余页与母版/版式不动**（`pptx_edit.py` 定点操作，不整体重建）。
- 改数字前核对 evidence_map 该数字的 quote；改错数字=事故。
- 增/删页是唯一例外 → 改 deck.json → 重跑 build → 新快照 v(K+1)，diff 记为结构变更。

### Step 4 — 构建 / 定点编辑
```bash
# 生成
python scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx [模板.pptx] --log /app/output/layout_log.json
cp /app/work/deck.json /app/output/deck.v1.json
# 编辑（自动向 versions.jsonl 追加 ts/op/slide/前后值/文件哈希）
python scripts/pptx_edit.py /app/output/deck.pptx <op> --slide N ... --versions /app/output/versions.jsonl
cp /app/work/deck.json /app/output/deck.v2.json
```
- build 内置版面预算（18→16→14→12→11→10 阶梯）；缩到 10 仍溢出 → **删内容，禁止硬塞**。python-pptx 缺失 → 降级 `pptx_minimal`（stdlib 仍可编辑），layout_log 标 `builder: pptx_minimal(fallback)`。
- 有模板时 **deck_meta 不写 font_latin/font_ea**（留空才继承主题字体）；layout_log 须显示 `inheritance:"real"` 且 `placeholders_used` 非空，否则说明没真正继承模板。
- 编辑操作表：

| 意图 | 做法 |
|---|---|
| 改文字/数字 | `replace-text`（先核 quote） |
| 压缩页 | 要点合并 ≤40 字；单页仍 >700 字 → 删次要要点，不缩字号 |
| 扩写页 | 只用 evidence_map 已有证据；新事实先补 quote |
| 换受众 | §2 矩阵；术语符号不换 |
| 换语言 | 术语映射见 §2；数字/单位/图号永不翻译 |
| 换图 | `set-figure`；只插源材料真实图，示意必须标"示意" |
| 改备注 | `set-notes`；拒绝与页面正文雷同 |
| 回退 | 从 deck.vK.json 重跑 build；versions.jsonl 不删，回退原因写 changelog |
### Step 5 — 校验、diff、渲染、result.json 终稿
```bash
python scripts/pptx_verify.py /app/output/deck.pptx /app/work/deck.json --evidence /app/work/evidence_map.jsonl --out /app/output/verify_report.json
python scripts/evidence_check.py --paper /app/work/extracted/paper_text.txt --map /app/work/evidence_map.jsonl --deck /app/work/deck.json --out /app/output/evidence_check.json
python scripts/pptx_verify.py diff /app/output/deck.v1.json /app/output/deck.v2.json --out /app/output/diff_v1_v2.json
python scripts/render_preview.py /app/output/deck.pptx --outdir /app/output/previews
```
- `evidence_check`：①每行 quote 逐字命中原文；②**页级覆盖**（每页有证据行、有 locator）；③**数字对账**——页面上的百分数/小数/带单位数必须出现在该页 quote 里，`numeric_unbacked` 非空必须逐条修掉或写入 uncertainty。不过不得交终稿。
- `verify` 的 fail 必须修复重跑；**warn 不得静默通过**：逐条修复或写进 uncertainty 后方可交稿。`verify_report.evidence_gate` 非 `enforced`（`not_provided`/`not_found`/`coverage_incomplete`）即证据覆盖未执行或未覆盖全页，等同"没检查"，不得宣称已核。
- 渲染抽查 1-2 张 PNG：乱码→换字体，溢出→删内容，变形→查图源。无法渲染 → `render.status="no_renderer"` 如实写。

## 2. 受众矩阵与图表红线

| 受众 | 保留 | 压缩 | 备注侧重 |
|---|---|---|---|
| 导师/组会 | 方法细节、进度、数据口径 | 背景铺垫 | 下一步计划与风险 |
| 评审/答辩 | 创新点、证据强度、限制 | 实现细节 | 预判追问+备用页 |
| 跨领域听众 | 直觉解释、类比、结论 | 公式与内部机制 | 术语白话解释 |
| 同行 | 与SOTA对比、消融 | 通识背景 | 可复现细节 |

红线：同一概念全稿同一个词；数字/单位/图号永不改写；结论强度与证据一致，不为受众"加强"语气。
图表：①有原始数据表且页面需要 → 可重绘（`redrawn_from:"Table n"`，数值逐字一致）；②已渲染实验图/机制图 → 引用原图；③禁止假曲线、占位图、把示意图当实验结果。图注用原文。

## 3. result.json 终稿结构（契约原字段全保留 + 以下扩展）

```json
{
  "case_id": "...",
  "...output_contract 原字段逐个填...": {},
  "deck": {"file": "deck.pptx", "slides": 10, "builder": "python-pptx|pptx_minimal(fallback)",
            "page_plan_summary": "问题1页-方法2页-结果4页-限制1页", "versions": ["deck.v1.json","deck.v2.json"]},
  "slides": [
    {"no": 1, "role": "problem", "title": "...", "bullets": ["..."],
     "figure": {"path": "figures/fig_p3_1.png", "caption": "论文图注原文", "locator": "Fig.1 p.3"},
     "notes": "演讲备注全文",
     "evidence": [{"type": "quote", "locator": "§3.2 p.4", "quote": "原文逐字"}]}
  ],
  "evidence_map": ["evidence_map.jsonl 逐行内嵌"],
  "edit_log": {"versions": ["versions.jsonl 逐行内嵌"], "diffs": ["diff_v1_v2.json"],
                "preserved_slides": [1,2,4,5], "edited_slides": [3]},
  "render": {"pdf": "deck.pdf", "previews": "previews/", "status": "ok|pdf_only_no_png|no_renderer"},
  "verification": {"layout_log": "layout_log.json", "verify_report": "verify_report.json", "evidence_check": "evidence_check.json"},
  "gain": {"mode": "generate|edit", "rework_pages": 0, "reorders": 1, "export_checks": 1,
            "manual_edits": 0, "baseline_note": "与同输入的基础 Agent 结果对照；白板由平台提供，不自造分数"},
  "status": "in_progress|partial|failed|complete",
  "uncertainty": ["未能核验/被砍掉的内容与原因"],
  "changelog": ["每轮取舍、编辑与修复记录"]
}
```
- **`slides` 必须逐页内嵌标题/要点/备注/图表/证据**——评分与复核都以 result.json 为准，不能只给 pptx 路径。失败/部分完成时写已完成页，缺口在 uncertainty 说明。
- `gain` 记"返工几页、重排几次、导出复查几轮"，支撑增益可验证性；对照结论以平台白板为准，不编造分数。

## 4. 异常处置

| 情形 | 处置 |
|---|---|
| 起点pptx损坏 | 记录 + 初始哈希；从 deck.vK.json 或源材料重建 |
| 编辑目标文本不存在 | 脚本报 `text not found`；先 verify 查该页实际文本 |
| 改页数后图号错位 | 重跑 evidence_check 逐条修 |
| 模板槽位不足 | 独立文本框替代，layout_log 记 `template_slot_insufficient`；不改母版 |
| 字体缺失/渲染乱码 | deck_meta 换 fc-list 实际存在的 CJK 字体重建 |
| 备注与页面雷同 | set-notes 拒绝写入；按过渡/强调/预判重写 |
| 版本文件缺失 | versions.jsonl 是唯一事实源；缺失写 uncertainty，不伪造历史 |
| python-pptx 缺失 | build 走 pptx_minimal；定点编辑不可用则报 `partial` 并说明 |
| 导出失败 | render_log 记原因；交 pptx + 已完成部分，status=partial |
| 材料缺图缺数据 | 按现有材料组织；缺失列 uncertainty，不编造 |

## 5. 交付自查清单

- [ ] result.json 含 case_id 与契约全字段；`slides` 逐页内嵌
- [ ] 每页一主张；页数 ≤ 上限；要点 ≤5 条/页；evidence_map 覆盖全页，fail 与 numeric_unbacked 均空
- [ ] 编辑轮：versions.jsonl + 快照 + diff 齐；preserved/edited_slides 如实
- [ ] 抽查 2 个未改页确认未被改；图号-引用-图注一致；无占位图/假曲线；图注为原文
- [ ] notes 全覆盖、非页面复述；deck.pdf/PNG 与 pptx 一致；render.status 如实
- [ ] status 四级如实；失败也交了合法 result.json
