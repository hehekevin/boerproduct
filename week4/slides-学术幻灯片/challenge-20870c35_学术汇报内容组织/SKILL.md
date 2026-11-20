---
name: talk-plan
description: 学术汇报内容组织技能：先把"报告目标—听众—时长—页数"落成可机械校验的 talk_plan.json（每页 目的/要点/证据/时长 四元组 + 来源定位 + 证据强度），再派生可编辑 pptx、讲稿备注与问答备用页，最后把主产物整体内嵌进 result.json 便于独立复核。Use when the task asks to organize research material into a talk for a given audience and duration (组会/答辩/评审/基金申请汇报；页级规划、讲稿、问答准备), not raw paper summarization.
---

# talk-plan — 学术汇报内容组织（目标先行 · 四元组可核验 · 时长自洽）

汇报不是把论文压缩一遍：组会讲方法与进度，答辩讲创新与边界，评审讲结论与证据强度。核心不是"生成页"，而是**先写一份可被机器校验的汇报计划**再派生产物——于是"取舍"天然可复核。

**唯一事实源** `talk_plan.json`：每页四元组（目的/要点/证据/时长）+ 来源定位 + 证据强度；`talkplan.py check` 机械校验时长加总、页数密度、逐字引文与数字出处。**校验不过，不许出稿。**

## 0. 运行协议（先读，再动手）

| 项 | 约定 |
|---|---|
| 输入/输出 | 输入 `/input/case.json` + `task.md`（材料按 case.json 路径**实际读取**）；中间件 `/app/work`，交付 `/app/output` |
| 预算 | 64 请求 / 900 秒 / 单响应 16384 token。**按 S1–S5 线性推进，每步 1–2 次响应，禁止逐页对话** |
| 硬规则 | ① 数字/单位/结论上页前先挂 quote；② 页数 ≤ 上限；③ 时间加总 = 时长；④ 缺失写 uncertainty，不编造 |
| 依赖 | 仅标准库；`extract` 用 PyMuPDF、`build` 用 python-pptx，缺失时如实降级并记 status |
| 不适用 | 论文精读、学术写作成稿、科研绘图生产（相邻课题）；纯模板美化 |


## 1. 五步流程

### S1 契约与材料（1 响应 + 1 命令）
```bash
ls -la /input && cat /input/case.json
python scripts/talkplan.py extract /input/<材料> --outdir /app/work/extracted
```
- `output_contract` 字段名**原样抄下**；受众/时长/页数上限记进 `constraints`，来源写 `case.json`/`task.md`/`assumed`。
- **立刻**写骨架 `/app/output/result.json`（契约字段 null + `status:"in_progress"`），每步回填，超时也交得出部分结果。
- `scanned: true` → OCR，locator 用 `PAGE n`；材料非 PDF → 直读，locator 用章节标题。

### S2 写 talk_plan.json（1–2 响应）
字段全集见 `examples/example-talkplan.json`（**示意非答案**）：
```json
{"case_id": "...",
 "audience": {"type": "defense|group_meeting|review|public|grant|lecture", "prior_knowledge": "...", "concerns": ["...","..."], "objections": ["..."]},
 "goal": {"statement": "让评委认可方法新颖性", "checkpoints": ["评委能复述机制", "结论强度与证据一致"]},
 "constraints": {"duration_min": 15, "slides_max": 12, "source": "task.md", "evidence": "原文依据"},
 "adaptation": [{"decision": "创新点单独成页", "because": "听众为评委", "from": "audience|goal|duration|evidence"}],
 "narrative": {"pattern": "问题驱动", "sections": [{"id": "problem", "minutes": 3.0, "slides": [1,2,3]}]},
 "slides": [{"no": 1, "section": "problem", "layout": "title|bullets|figure|table|closing",
             "purpose": "这页要让听众相信什么", "claim": "≤25 字唯一主张", "points": ["≤40 字，≤5 条"],
             "evidence": [{"locator": "§3.2 p.5 / Fig.1 / Table 2", "quote": "逐字原文"}],
             "minutes": 1.5, "evidence_strength": "强|中|弱", "figure_ref": null,
             "notes": "过渡+强调+预判问题（40–600 字，不复述页面）", "backup": false}],
 "qa": [{"q": "...", "category": "mechanism|data|control|limitation", "answer": "...", "pointer_slide": 6, "backup_slide": 12, "evidence_strength": "中"}]}
```
- **时长先算再排页**：页数上限 ≈ `duration ÷ 1.5`；正片分钟之和 = duration；备用页 `minutes: 0` 不计入。
- **顺序服从听众**（规则见 `references/audience-narrative.md`）：答辩创新点前移独立成页；评审结论与强度前置；组会方法与进度为主；公众加背景删公式。
- **强度分档**：强=多组/消融；中=单实验或作者承认限制；弱=推论。语气与强度同档（弱证据不写"证明"）。
- 每条要点能指回 locator；带数字的要点，quote 必须含同一数字。

### S3 机械校验（必须 pass 才继续）
```bash
python scripts/talkplan.py check /app/work/talk_plan.json \
  --source /app/work/extracted/source_text.txt --out /app/output/check_report.json
```
19 项：契约 / 受众适配 / 四元组完整 / 时长加总（节=页=总）/ 页数密度 / 主张字数 / locator / 引文逐字 / 数字出处 / 强度语气 / 图表绑定 / 备注不复述 / 问答与备用页。
- 退出码非 0 → **改计划不改规则**：找不到 quote 就改主张；数字无出处就删数字；时长不齐就调 section。
- "quote 非逐字"是红线（改写/取整/换算均不可）；`--source` 缺失时降为 warn，须写进 uncertainty。

### S4 出稿与渲染
```bash
python scripts/talkplan.py build /app/work/talk_plan.json /app/output/deck.pptx \
  --template /input/<模板.pptx> --log /app/output/layout_log.json   # 无模板则省 --template
python scripts/talkplan.py render /app/output/deck.pptx --outdir /app/output/previews
```
- 有模板 → 克隆模板版式（母版/页脚不改）；无模板 → 学术版式（白底、深灰蓝标题、CJK 字体）。四元组落到页面：标题=claim、正文=points、角标=强度/图示/备用页，`notes` 写入备注。
- `layout_log` 报溢出 → 回 S2 删要点，**不允许缩字硬塞**；`no_renderer` → 如实记 status，不说成已渲染。

### S5 result.json 定稿（主产物全量内嵌）
```json
{"case_id": "...", "...(output_contract 原字段逐个填)...": {},
 "deliverable": {"goal": {}, "audience": {}, "adaptation": [],
                 "timing_table": [{"section": "problem", "minutes": 3.0, "slides": [1,2,3], "share": "20%"}],
                 "slides": ["<talk_plan.slides 原样内嵌：目的/要点/证据/时长/强度/备注>"], "qa": []},
 "checks": {"summary": {}, "metrics": {}, "checks": []},
 "files": {"plan": "talk_plan.v1.json", "deck": "deck.pptx", "slides": 12, "main": 10, "backup": 2, "layout_log": "layout_log.json"},
 "render": {"pdf": "...", "previews": "previews/", "status": "ok|pdf_only_no_png|no_renderer"},
 "status": "complete|partial|failed", "uncertainty": ["..."], "changelog": ["每条取舍：砍了什么/为什么/被谁约束"]}
```
- **`deliverable.slides` 必须全量内嵌**（不是文件名），评审无需打开附件即可核对"目的—要点—证据—时长"；并 `cp talk_plan.json /app/output/talk_plan.v1.json` 存档。
- `status` 按事实填：全链路完成=complete；缺渲染/缺建=partial（写明阶段）；无产物=failed（仍要写 result.json）。

## 2. 异常处置

| 情形 | 处置 |
|---|---|
| 未指定受众/时长 | 按 task.md 场景词推断：`constraints.source="assumed"` + `evidence` 写依据，进 uncertainty |
| 扫描件 / 图表提不出来 | OCR 或整页渲染（`figure_mode="page_render"`），locator 用 `PAGE n`，注明来源；不得用占位图 |
| 证据撑不住主张 | 降 `evidence_strength` 或改写主张；不改 quote 迁就页面 |
| 页数上限极小（≤6）/ 时长冲突 | 合并方法页，保结果页+限制页；先砍 `adaptation` 标为低优先的内容，再重跑 check，取舍进 changelog |
| 模板版式不足 / 字体缺失 | 最近版式+独立文本框并记 `template_slot_insufficient`；换 fc-list 存在的 CJK 字体重建，不改母版 |
| python-pptx 缺失 / 导出失败 | 交 talk_plan + result.json（status=partial），render_log 记原因，不编造渲染状态 |

## 3. 调用示例（示意，非正式案例结果）

```bash
python scripts/talkplan.py extract /input/materials/paper.pdf --outdir /app/work/extracted
# → {"ok":true,"tool":"pymupdf","pages":12,"chars":21544,"scanned":false}
#   （模型响应：写 talk_plan.json，10 正片 + 2 备用页）
python scripts/talkplan.py check /app/work/talk_plan.json --source /app/work/extracted/source_text.txt --out /app/output/check_report.json
# → {"total":19,"pass":19,"fail":0,"warn":0,"verdict":"pass"} / metrics.duration_min=15.0 section_sum=15.0 slide_sum=15.0
python scripts/talkplan.py build /app/work/talk_plan.json /app/output/deck.pptx --log /app/output/layout_log.json
# → {"ok":true,"slides":12,"warnings":0}
python scripts/talkplan.py render /app/output/deck.pptx --outdir /app/output/previews  # → {"status":"ok","pngs":12}
```
完整方案见 `examples/example-talkplan.json`（标注"示意"，配套材料见 `README.md`「示例材料」，非真实论文）。

## 4. 交付自查（逐项勾）

- [ ] result.json 含 `case_id` + output_contract 全字段，无未解释的 null
- [ ] `deliverable.slides` 全量内嵌，每页 目的/要点/证据/时长 齐全（claim ≤25 字、points ≤5 条）
- [ ] `check` verdict=pass；`metrics` 中 duration = section_sum = slide_sum
- [ ] 每条要点有 locator，数字可在 quote 或源文本找到，quote 逐字；强度与语气一致，限制页用作者原话
- [ ] qa ≥4 条覆盖机制/数据/对照/局限，pointer 页与备用页真实存在
- [ ] 备注 ≥40 字、非复述、含预判问题与页间过渡；pptx 可编辑且备注在 notes、母版未被覆盖
- [ ] render 状态如实；status/uncertainty/changelog 无粉饰
