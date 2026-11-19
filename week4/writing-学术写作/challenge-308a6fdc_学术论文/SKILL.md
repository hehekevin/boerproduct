---
name: acwrite-paper
description: 学术论文写作技能：把实验记录/数据表/图表/文献等固定科研材料写成结构完整、可编辑的论文章节稿（IMRaD），硬事实挂台账逐条回溯材料原文，主产物逐章分批写盘回填 result.json（防单响应截断），交付 docx+md+evidence_map+一致性检查。Use when the case asks to draft/complete/revise an academic paper or thesis chapter from given research materials, keeping facts, numbers and citations traceable to sources.
---

# acwrite-paper — 论文写作（事实挂账 · 逐章落盘 · 成稿可编辑）

核心思想：写作是**受约束的转写**——正文每个数字、引用、结论都能指回材料具体位置。交付三件套：① 可编辑稿件 draft.docx + draft.md；② 事实与来源映射 evidence_map.jsonl；③ 版本与边界 fact_check.json + check_report.json + result.json（status/uncertainty/changelog 如实）。

### 增益证据与效率计数（回填 result.json）
必须是**本次运行真跑出来的数字**，不是文字声明：
```bash
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --baseline
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --write
```
- 第一条：基础模式对照——模拟「不做证据登记/不做逐条回证」的路径，统计源材料里有多少实体与数值会变成不可核对项（需人工逐条核对的规模）。
- 第二条：当前模式实测——证据登记数、证据逐字回证率、三元组 match 通过率、需人工核对条目数，并计算相对基线的削减量；`--write` 写入 `result.json.registry_evidence`（含 `baseline_comparison.reduction` 与 `efficiency` 计数；若本包另有脚本写 `gain_evidence`，两者互补不覆盖）。
- 机检/闸门失败**一律 verdict 照实记录、退出码恒 0**：修一轮，仍不过则如实登记并继续交付，禁止以非零退出码结束会话。

## ⚠️ 强制执行协议（每次运行先读完本节再动手，顺序不可调换）

1. **抄契约**：第一动作 `cat /input/case.json`，逐字抄下 `output_contract` 全部字段名与 `case_id`。result.json 必须包含全部字段，一个不缺（无值先置 null）。
2. **立即落骨架**：读完契约立刻用 build_result.py 写出骨架 result.json（status="in_progress"）。此后任何时刻中断，result.json 都完整可解析。
3. **广度优先**：先把全部必需章节各写出一版（短但有据），再逐章充实。禁止把预算耗在打磨单章而让其他章节缺失。
4. **逐章分批写盘**：主产物**每次响应只写 1 个章节**的小文件 `/app/work/sections/S##.json`，写完立即自检并回填 result.json。**禁止在一次响应里输出全文**——单响应超限截断是本技能最高优先级防范的失败模式。
5. **熔断**：累计约 48 次模型请求或 700 秒即停止新增工作，直接执行收尾（合并→校验→build_result），status 如实。
6. **写盘自检**：每次写 JSON/文本后自检：文件存在、json 可 `json.loads`、无 null 主字段遗漏。失败立即重写一次；再失败改写为纯文本兜底并在 uncertainty 记录。
7. **失败也交付**：任何异常都不允许空手退出。partial/failed 也要有 result.json + 已完成部分的可编辑稿件。

## 线性流程（5 步，按序执行）

### Step 1 — 契约与骨架
```bash
ls -la /input/ && cat /input/case.json
cat /input/task.md 2>/dev/null || true
python3 scripts/extract_materials.py --input /input --outdir /app/work/extracted
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --status in_progress
```
- 从 case.json/task.md 提炼 `/app/work/constraints.json`：`required_sections`（学科模板章节）、`citation_style`、`word_range`、受众、体裁、图表清单。
- case.json 未给 required_sections 时按体裁默认：期刊论文=摘要/引言/材料与方法/结果/讨论/结论/参考文献/数据可得性声明；假设写进 uncertainty。
- **对照契约字段逐个确认**：把每个 output_contract 字段映射到"由哪个产物回填"，写进 constraints.json 的 `field_plan`。

### Step 2 — 材料索引与事实台账
```bash
python3 scripts/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
```
- extract 产出 `extracted/materials_manifest.json` 与 `M01.txt…`（每行带 `[SRC:Mxx:p3|line12]` 锚点）。**读真实文件，不按文件名/标签猜内容**。
- 用一次响应产出 `/app/work/material_index.jsonl`：每条材料 `{"id":"M01","kind":"实验记录|数据表|图|文献|…","supports":["结果3.1","方法2.2"],"gaps":"缺失"}`。数值冲突记 conflicts，不擅自取舍。
- 台账自动抓取数值+单位、n=、p 值/CI、DOI、年份——这是"写得实"的底座。

### Step 3 — 逐章写作（每响应 1 章，写盘→自检→回填）
按 constraints.required_sections 顺序循环。**每次响应**：
1. 写 `/app/work/sections/S01.json`（一个 section 对象：`{"order":"01","heading":"1 引言","level":1,"paragraphs":[…],"comments":[…]}`；references/notes 可随最后两章写入）。控制在 1500 字内，超长拆两个响应。
2. 写盘自检：`python3 -c "import json;json.load(open('/app/work/sections/S01.json',encoding='utf-8'));print('ok')"`。
3. 立即回填 result.json：
```bash
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --status partial --set sections_done='["1 引言"]'
```

写作规则（每章都适用）：
- **数值/单位/样本量/统计量**与材料逐字一致（不取整不换算），先查台账再落稿；材料没有的要么不写要么标 [待核]。
- **图表**：图注沿用材料原文；"图X显示…"须与图实际内容对应；误差棒/显著性标记照抄含义。
- **引用**：每条 [n] 明确支撑所在论断；作者/年份/期刊/DOI 从材料文献条目抄录；**材料中没有的文献一律不引**；不堆装饰性引用。
- **结构与衔接**：引言=已知→未知→本文做什么；讨论=结果→与文献对照→局限；详略按 word_range 分配；相关≠因果，"表明/提示/证实"按证据强度选词；术语首现给全称，全篇同一写法。
- 材料不足的必需章节：写标题+占位说明，notes_for_human 显式挂"材料缺口"，不编造。

### Step 4 — 组稿与双重校验（fail 必须修复）
```bash
python3 scripts/docx_build.py --sections-dir /app/work/sections --out-docx /app/output/draft.docx --out-md /app/output/draft.md
python3 scripts/fact_ledger.py check --draft /app/output/draft.md --ledger /app/work/fact_ledger.jsonl --out /app/output/fact_check.json
python3 scripts/consistency_check.py --draft /app/output/draft.md --constraints /app/work/constraints.json --out /app/output/check_report.json
```
- fact_check 的 unmatched 数字：逐条回材料找原句→改回材料口径，或改非数值表述，或标 [待核] 并记 uncertainty。**禁止保留来源不明的数值**。修复只改对应 S##.json 后重跑合并，不重写全文。
- 同时产出 `/app/work/evidence_map.jsonl`（可穿插在 Step 3 各响应尾部）：每行 `{"claim_id":"C01","section":"3.2","text":"稿件原句摘要","type":"number|statistic|citation|figure|term","locator":"M03:p5|line40 或 文献[2] DOI:…","quote":"材料逐字原文"}`。全部数值句、引用、图注挂账。

### Step 5 — 渲染与收尾（主产物全量嵌入 result.json）
```bash
python3 scripts/render_preview.py --src /app/output/draft.docx --outdir /app/output/previews
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact draft.docx --artifact-md draft.md --evidence /app/work/evidence_map.jsonl \
  --fact-check /app/output/fact_check.json --consistency /app/output/check_report.json \
  --sections-dir /app/work/sections --constraints /app/work/constraints.json \
  --render /app/output/previews/render_log.json --status complete --changelog '关键决策; 降级事实'
```
- **嵌入要求**：result.json 必须含 `sections`（结构化章节）+ `draft_text`（全文）+ `claims`（由 evidence_map 自动推导：每条 kind/evidence≤40字逐字/source_id/location）+ `fact_check.checks`（数字-来源全量核对表，含 match/source/quote）+ `check_report.results`（逐项 {item, template_value, applied, match}）+ `section_check`——评分器不开附件即可核对。
- status 四级：全链路=complete；部分失败=partial（写明环节）；无法产出=failed；材料/依赖缺失无法开工=blocked（也写 result.json 说明缺什么）。
- 闸门诚实枚举：检查项带 `gate: enforced/skipped_not_provided/not_found/unreadable`；未运行的闸门必须 warn + gate_note「下游不得宣称已核对」，不硬凑。
- uncertainty 必含：材料缺口、[待核] 条目、冲突口径、降级事实、渲染状态。
- 熔断触发时跳过渲染，直接本步收尾。

## 异常处置表

| 情形 | 处置 |
|---|---|
| 章节 JSON 写盘自检失败 | 重写一次；再失败改写纯文本 `/app/work/sections/S##.txt`，docx_build 自动跳过坏文件（skipped 列表留痕），uncertainty 记录 |
| 响应被截断/中断 | 已落盘章节不受影响；从下一章继续，不动已完成部分 |
| 材料 PDF 扫描件/图片 | extract 如实标 extracted:false；有 ocr-tool 则 OCR 重建锚点，uncertainty 注明 OCR 来源 |
| 两份材料数值冲突 | 不擅改；取任务指定口径或并列注明；记 conflicts + uncertainty |
| 必需章节无材料支撑 | 标题+占位说明+notes_for_human；不编造 |
| 文献条目字段缺失 | 按已有字段著录并在 evidence_map 标 incomplete；不猜补 |
| 字数超限 | 删方法细节与重复论述，不动结果与局限；changelog 记录 |
| python-docx 缺失 | docx_build 自动 stdlib 兜底（仍合法可编辑），changelog 记录 |
| 渲染器缺失 | render.status=no_renderer，交付 docx+md，不伪造渲染 |
| 预算将尽（≥48 次或 ≥700 秒） | 立即 Step 5 收尾，status 如实 |

## 最小调用示例（示意，非正式案例结果）

```bash
# Step 1
python3 scripts/extract_materials.py --input /input --outdir /app/work/extracted
# → {"ok":true,"summary":{"total":6,"extracted":6}}
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --status in_progress
# → {"ok":true,"status":"in_progress","keys":["case_id","title",...,"status"]}
# Step 3（每次响应一章）
# 写 /app/work/sections/S03.json（示例内容见 examples/example_input.json）
python3 -c "import json;json.load(open('/app/work/sections/S03.json',encoding='utf-8'));print('ok')"
# → ok
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --status partial --set sections_done='["摘要","1 引言","2 材料与方法"]'
# Step 4
python3 scripts/docx_build.py --sections-dir /app/work/sections --out-docx /app/output/draft.docx --out-md /app/output/draft.md
# → {"ok":true,"builder":"python-docx","sections_merged":8}
python3 scripts/fact_ledger.py check --draft /app/output/draft.md --ledger /app/work/fact_ledger.jsonl --out /app/output/fact_check.json
# → {"checked_numbers":96,"unmatched":0,"verdict":"pass"}
# Step 5
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --artifact draft.docx --status complete
```

## 交付自查清单

- [ ] result.json 含 case_id 与 output_contract 全部字段；任何时刻可解析（先骨架后回填）
- [ ] 全部必需章节落盘；缺项在 notes_for_human/uncertainty 显式声明
- [ ] 全部数值句、引用、图注在 evidence_map 挂账且 fact_check verdict=pass
- [ ] 引用全部来自材料文献条目；无装饰性引用、无材料外文献
- [ ] 相关/因果与"表明/证实"用词匹配证据强度；局限性具体
- [ ] draft.docx/draft.md 章节层级完整、可继续编辑
- [ ] status/uncertainty/changelog 如实；未编造数据、文献或渲染状态
