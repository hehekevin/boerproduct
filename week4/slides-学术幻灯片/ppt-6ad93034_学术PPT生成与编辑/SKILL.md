---
name: deck-edit-skill
description: 学术PPT生成与定点编辑技能：从论文/科研材料生成整稿，或对已有deck做source-preserving定点编辑（改文字/压缩/扩写/换受众/换语言/换图/改备注），全程页级证据映射、版本留痕、逐页diff、导出渲染校验。Use when the task asks to generate an academic slide deck from a paper AND/OR edit/revise slides across rounds (学术汇报PPT、改某页、换受众改写、图表替换、版本回退、导出不塌版).
---

# deck-edit — 学术PPT生成 + 定点编辑 + 全程可核验

产出三件套，缺一不可：① 可编辑 deck.pptx；② 页级证据映射 evidence_map.jsonl；③ 渲染与版本记录（deck.pdf + previews/*.png + layout_log.json + verify_report.json + versions.jsonl + 逐页 diff）。

## 0. 强制执行协议（置顶，每案例必须最先做，顺序不可换）

1. **第 1 步**：`cat /input/case.json`，把 `output_contract` 的**全部字段名原样抄下** + `case_id`。最终 result.json 必须包含所有这些字段（保留原字段名）+ `case_id`，一个不缺。
2. **第 2 步**：立即写 `/app/output/result.json` 骨架——含 case_id 与全部 output_contract 字段，值置 null，`status="in_progress"`。此后每完成一步就回填。**即使中途超时/失败，/app/output 里也必须有 result.json**。
3. **广度优先**：先打通"提取→建deck→构建→校验→渲染→result.json"全链路，交出部分成果；再回头加深质量。禁止在单个环节（如某页措辞）反复打磨而全链路未通。
4. **自熔断**：预算 64 请求 / 900 秒 / 单响应 16384 token。**自设熔断线：48 请求 / 700 秒**——超线立即收尾：回填 result.json、停新动作。
5. **写盘自检**：每次写 result.json 前先 `python -c "import json;json.load(open('/app/output/result.json',encoding='utf-8'))"` 自检；JSON 非法会丢失全部评分，务必修好再交。
6. **状态四级诚实**：`in_progress`（未完成）/ `partial`（部分完成，写明缺什么为什么）/ `failed`（失败，写明原因，也要交 result.json）/ `complete`（全链路完成）。不编造渲染状态、论文数据或软件状态。

## 1. 五步主流程（线性推进，每步 1 次响应 + 1-2 次脚本调用）

### Step 1 — 读契约与判断任务类型
```bash
ls -la /input/ && cat /input/case.json
```
- 按 §0 第 1、2 步落契约与骨架。
- 判定任务类型：case.json/task.md 给了**起点 pptx 或要求修改既有页** → 编辑路径（Step 2b、3b）；给论文/提纲**从零生成** → 生成路径（Step 2a、3a）。两条路径都走也允许（先生成后按指令编辑）。
- case.json 声明的页数上限、时长、受众、模板文件路径 → 记入 `/app/work/constraints.json`。

### Step 2a — 材料提取（生成路径）
```bash
python scripts/extract_pdf.py <材料.pdf> --outdir /app/work/extracted
```
- 得 `paper_text.txt`（PAGE 锚点）+ `figures/fig_p*.png`。扫描件走 OCR，locator 用页码并写入 uncertainty。
- 嵌入图少于正文提及的图 → 用 PyMuPDF 整页渲染为 `page_p{n}.png`，evidence 标 `figure_mode:"page_render"`；**禁止占位图、禁止凭空重绘数据图**。
- 材料是 md/docx/txt → 直接读，locator 用章节标题。

### Step 2b — 盘点起点 deck（编辑路径）
```bash
python scripts/pptx_verify.py <起点.pptx> /dev/null 2>/dev/null; echo "exit=$?"
sha256sum <起点.pptx>   # 记录初始哈希
```
- 读出每页现有标题/要点/备注/图 → 存 `/app/work/base_deck.json`。损坏打不开时如实记录，改走从源材料重建。
- 建初始 evidence_map：把起点页内容对应到论文图/表/章节；对不上的页在 uncertainty 标注，不编造。

### Step 3a — 页计划 + deck.json（生成路径）
- 主线四件套：问题 → 方法 → 结果 → 限制/结论；**按论文贡献排页序，不按章节搬运**。每页：`{"no","role"(hook/problem/method/result/limitation/conclusion/backup),"claim","layout","title","bullets","figure","notes","evidence"}`。
- 一页一主张，要点 ≤5 条、每条 ≤40 字；页数超限先砍方法细节页，**不砍结果页与限制页**，取舍记 changelog。
- `notes` 与页面文字分离（40-600 字）：①承上过渡 ②本页强调点与证据强度 ③一个可能被追问的问题及应对。
- 同时展开 `/app/work/evidence_map.jsonl`：每行 `{"slide_no","claim","type":"figure|table|section|quote","locator":"Fig.1 p.3 / §3.2 / Table 2","quote":"论文原文逐字","figure_mode":null}`。**带数字/单位的事实必须 type=quote 且逐字**（换行空白可容忍，改写/取整/单位换算不可）。

### Step 3b — 编辑定位（编辑路径，source-preserving）
- 只改任务指令点名的页；**其余页与母版/版式保持字节不变**（用 `pptx_edit.py` 定点操作，不用整体重建）。
- 改数字前先核对 evidence_map 里该数字的 quote；改错数字 = 事故。
- 增/删页是唯一例外 → 走重建：改 deck.json → Step 4 重跑 build → 快照 v(K+1)。

### Step 4 — 构建 / 定点编辑
```bash
# 生成路径（模板存在时把模板路径作为第4个参数传入）
python scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx [模板.pptx] --log /app/output/layout_log.json
cp /app/work/deck.json /app/output/deck.v1.json

# 编辑路径（每次调用自动在 versions.jsonl 追加一行：ts/op/slide/前后值/文件哈希）
python scripts/pptx_edit.py /app/output/deck.pptx <op> --slide N ... --versions /app/output/versions.jsonl
cp /app/work/deck.json /app/output/deck.v2.json    # 每轮快照
```
- build 内置版面预算（字号 18→16→14→12→11→10 阶梯收缩）；缩到 10 仍溢出 → **删内容，禁止硬塞**。python-pptx 缺失 → 自动降级 pptx_minimal（stdlib 兜底仍可编辑），layout_log 如实标 `builder: pptx_minimal(fallback)`。
- 编辑操作规范：

| 意图 | 做法 |
|---|---|
| 改文字/数字 | `replace-text`（先核 quote） |
| 压缩页 | 要点合并为 ≤40 字短语；单页仍 >700 字 → 删次要要点，不缩字号 |
| 扩写页 | 只能用 evidence_map 已有证据；新事实先补 quote |
| 换受众 | 见 §2 矩阵；术语符号不换 |
| 换语言 | 术语映射见 §2；数字/单位/图号永不翻译 |
| 换图 | `set-figure`；只插源材料真实图，示意标注"示意" |
| 改备注 | `set-notes`；内置校验拒绝与页面正文雷同 |
| 回退 | 从 deck.vK.json 重跑 build；versions.jsonl 不删，回退原因写 changelog |

### Step 5 — 校验、diff、渲染、result.json 终稿
```bash
python scripts/pptx_verify.py /app/output/deck.pptx /app/work/deck.json --evidence /app/work/evidence_map.jsonl --paper /app/work/extracted/paper_text.txt --out /app/output/verify_report.json
python scripts/pptx_verify.py diff /app/output/deck.v1.json /app/output/deck.v2.json --out /app/output/diff_v1_v2.json
python scripts/evidence_check.py --paper /app/work/extracted/paper_text.txt --map /app/work/evidence_map.jsonl --out /app/output/evidence_check.json
python scripts/render_preview.py /app/output/deck.pptx --outdir /app/output/previews
```
- verify/evidence_check 的 fail 项必须修复重跑；warn 项列入 uncertainty。**evidence_check 不过不得交终稿**。
- 编辑轮的"逐页 diff" = `diff` 模式输出（改了哪页/哪个字段/前后值）+ versions.jsonl 行；两份证据都必须写盘。
- 渲染后抽查 1-2 张 PNG：乱码（换字体）、溢出（删内容）、变形（查图源）。无法渲染 → `render.status="no_renderer"` 如实写，不伪造。
- 回填 result.json 终稿（结构见 §3），写盘前按 §0 第 5 步自检。

## 2. 受众矩阵与图表红线

| 受众 | 保留 | 压缩 | 备注侧重 |
|---|---|---|---|
| 导师/组会 | 方法细节、进度、数据口径 | 背景铺垫 | 下一步计划与风险 |
| 评审/答辩 | 创新点、证据强度、限制 | 实现细节 | 预判追问+备用页 |
| 跨领域听众 | 直觉解释、类比、结论 | 公式与内部机制 | 术语白话解释 |
| 同行 | 与SOTA对比、消融 | 通识背景 | 可复现细节 |

改写红线：同一概念全稿同一个词；数字/单位/图号永不改写；结论强度与证据一致，不得为受众"加强"语气。
图表红线：①有原始数据表且页面需要 → 可重绘（evidence 记 `redrawn_from:"Table n"`，数值逐字一致）；②论文已渲染的实验图/机制图 → 必须引用原图不改写；③禁止假数据曲线、占位图、把示意图当实验结果。图注用论文图注原文。

## 3. result.json 终稿结构（output_contract 原字段全部保留 + 以下扩展）

```json
{
  "case_id": "...",
  "...output_contract 原字段逐个填...": {},
  "deck": {"file": "deck.pptx", "slides": N, "builder": "python-pptx|pptx_minimal(fallback)",
            "page_plan_summary": "问题x页-方法x页-结果x页-限制x页", "versions": ["deck.v1.json","deck.v2.json"]},
  "slides": [
    {"no": 1, "role": "problem", "title": "...", "bullets": ["...", "..."],
     "figure": {"path": "fig_p3.png", "caption": "论文图注原文", "locator": "Fig.1 p.3"},
     "notes": "演讲备注全文",
     "evidence": [{"type": "quote", "locator": "§3.2 p.4", "quote": "原文逐字"}]}
  ],
  "evidence_map": ["evidence_map.jsonl 逐行内嵌"],
  "edit_log": {"versions": ["versions.jsonl 逐行内嵌"], "diffs": ["diff_v1_v2.json"],
                "preserved_slides": [1,2,4,5], "edited_slides": [3]},
  "render": {"pdf": "deck.pdf", "previews": "previews/", "status": "ok|pdf_only_no_png|no_renderer"},
  "verification": {"layout_log": "layout_log.json", "verify_report": "verify_report.json",
                    "evidence_check": "evidence_check.json"},
  "status": "in_progress|partial|failed|complete",
  "uncertainty": ["未能核验/被砍掉的内容与原因"],
  "changelog": ["每轮取舍、编辑与修复记录"]
}
```
**`slides` 数组必须完整内嵌每页标题/要点/备注/证据**——评分器主要读 result.json，不得只给文件路径。失败/部分完成时 `slides` 写已完成页，缺的部分在 uncertainty 说明。

## 4. 异常处置

| 情形 | 处置 |
|---|---|
| 起点pptx损坏 | 如实记录 + 初始哈希；从 deck.vK.json 或源材料重建 |
| 编辑目标文本不存在 | 脚本报 `text not found`；先 verify 查该页实际文本再操作 |
| 改页数后图号错位 | 重跑 evidence_check；fail 行逐条修复 |
| 模板槽位不足 | 独立文本框替代，layout_log 记 `template_slot_insufficient`；不改母版 |
| 字体缺失/渲染乱码 | deck_meta 换 fc-list 实际存在的 CJK 字体重建 |
| 备注与页面雷同 | set-notes 拒绝写入；按过渡/强调/预判三件套重写 |
| 版本文件缺失 | versions.jsonl 是唯一事实源；缺失如实写 uncertainty，不伪造历史 |
| python-pptx 缺失 | build 走 pptx_minimal 兜底；定点编辑不可用时如实报 `partial` 并说明 |
| 导出失败 | render_log 记原因；交 pptx + 已完成部分，status=partial |
| 材料缺图缺数据 | 按现有材料组织；缺失列 uncertainty，不编造 |

## 5. 交付自查清单

- [ ] result.json 含 case_id 与 output_contract 全字段；`slides` 内嵌每页标题/要点/备注/证据
- [ ] 每页一主张；页数 ≤ 上限；要点 ≤5 条/页
- [ ] evidence_map 覆盖全部页；数值页有逐字 quote 且 evidence_check pass
- [ ] 编辑轮：versions.jsonl 行 + deck.vK 快照 + diff 文件齐；preserved_slides 如实
- [ ] 定点编辑未动母版与其他页（抽查 2 页未动页）
- [ ] 图号-引用-图注一致；无占位图/假曲线；图注为原文
- [ ] notes 全覆盖且非页面复述
- [ ] deck.pdf/PNG 存在且与 pptx 一致；render.status 如实
- [ ] status 四级如实；失败也交了合法 result.json（JSON 自检通过）
