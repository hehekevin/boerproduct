---
name: acwrite-grant
description: 基金申请书写作技能：从申报指南/前期成果/文献材料逐章生成立项依据、科学问题、研究目标、研究内容、技术路线、创新点、研究基础与可行性、预算各节。四向对齐表（目标↔内容↔路线↔考核指标）保证逐条对应；创新点写实（vs_existing 对照，禁用"首次/国际领先/填补空白"裸用）；预算数字-来源核对表（无来源不写金额）；关键论断带来源映射，材料不足标缺口不编造；逐章分批写作防截断，主产物全文内嵌 result.json。Use when the case asks to draft grant/proposal sections (立项依据/科学问题/研究目标/技术路线/创新点/可行性/预算) from guide texts and prior-work materials with objective-content-route-metric alignment and traceable evidence.
---

# acwrite-grant — 基金申请书写作（逐章分批 · 四向对齐 · 预算溯源）

申请书写作的最大风险是**一次性输出全稿被截断**和**数字编造**（预算金额、样本量、指标值）。本技能用**逐章分批写作 + 数字来源核对**管住这两点。交付三件套：

1. **申请书章节稿**：grant.docx + grant.md（立项依据→科学问题与目标→研究内容→技术路线→创新点→研究基础与可行性→预算，逐章可编辑），全文内嵌 result.json
2. **溯源与对齐**：evidence_map.jsonl（关键论断→材料位置）+ alignment.jsonl/routes.jsonl（四向对齐）+ budget_ledger.jsonl（预算数字-来源核对表）
3. **版本与边界**：待确认项 + 材料缺口 + changelog

硬规则：**先立对齐表再动笔**；每章一次响应写完即落盘、即回填 result.json；实质性论断无来源不落稿；金额无来源不写数字（标 missing）；前期成果"已完成/拟开展"二态分清。

## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 7 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

1. **第 0 步落骨架**：读完 /input/case.json 与题面后，第一个写盘动作就是在 /app/output/result.json 写入骨架：case_id 取自 case.json；键名严格按 output_contract 声明的每个字段生成（暂无法完成的字段填 unknown/空数组，绝不省略键）；status 填 "partial"。此后任何时刻 /app/output/result.json 必须存在且 JSON 可解析。
2. **字段一个不缺**：最终 result.json 必须包含 output_contract 全部键。某项确实无法产出时，保留键并填 unknown/空数组/说明字符串，原因写入 uncertainty；不得删键、不得编造数据。
3. **逐章分批防截断**：申请书全文禁止在一次响应中写完。每章独立 1 次响应，写完立即落盘 /app/work/chapters/chNN_*.md，并立即用 build_result.py --embed-file --append 回填进 result.json。单章也不超过该章目标字数的 1.2 倍，写不下先落盘已写部分、下章响应续写。
4. **广度优先 + 熔断**：先让全部要求的章节/字段以最小合格版本存在，再对高价值章节加深。模型请求超过 48 次或运行超过 700 秒：立即停止新增写作，用现有章节组装 result.json 收尾（缺章在 uncertainty 说明）。每次写 result.json 都是覆盖保存当前最新完整状态。
5. **数字-来源核对**：预算金额、样本量、指标值、时间节点等一切数字，落稿前先入 budget_ledger.jsonl 或 evidence_map.jsonl（locator+逐字摘录）；无来源的金额只能标 status=missing 且正文写占位符；无来源的量写成"拟/约/按 X 估算"并挂账。机检不过的数字必须删除或降级为假设。
6. **最终写盘前自检**：JSON 可解析、output_contract 字段一个不缺、case_id 与输入一致、status 如实（complete/partial/failed 与实际相符）、grant.md 全文已嵌入 deliverable_content、align_check verdict 与问题数一致。自检不过先修复再交付。
7. **失败也要交付**：处理中断或失败时，仍写 result.json（status="failed"，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 流程（5 步线性执行）

脚本定位（不假设安装路径）：`SD=$(find /skills /app -type d -name scripts 2>/dev/null | head -1)`；为空则用相对路径 `./scripts`。下文 `$SD/xxx.py` 均指此目录。

### Step 0 读契约、落骨架（最先做）
`cat /input/case.json` 与题面 → 抄下 output_contract 全部键名与 case_id → **立即写 /app/output/result.json 骨架**（全部键+case_id，未完成字段填 unknown，status="partial"）。同时记 constraints：required_sections、word_range、citation_style、目标基金类型。

### Step 1 材料盘点与事实台账（2 次脚本）
```bash
python $SD/extract_materials.py --input /input --outdir /app/work/extracted
python $SD/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
```
读 manifest 分类登记：指南条款（限项/格式/周期/资助强度）、前期成果（**已完成/拟开展二态**）、文献、团队平台。缺口记入 /app/work/constraints.json。

### Step 2 四向对齐表 → 逐章分批写作（每章 1 次响应，核心步）
先建 /app/work/alignment.jsonl（每个 goal 含 contents/routes/metrics 对应项与可考核指标）与 /app/work/routes.jsonl（每条路线含 steps[input/out/节点/风险/备选]）。然后按顺序逐章写作，**每章一次响应**，格式：先写 /app/work/chapters/chNN_xxx.md，随后立即回填：

```bash
python $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --embed-file /app/work/chapters/chNN_xxx.md --embed-key deliverable_content --append
```

各章写法要点：
- **ch01 立项依据**：按"别人做到哪（引文献）→还差什么（缺口）→为什么是申请人（前期成果）→为什么是现在"组织；每句实质论断挂 evidence_map（locator+逐字摘录≤30字）。
- **ch02 科学问题与研究目标**：科学问题收敛 1-3 个，各写判断标准（什么结果算回答）；目标数量与 alignment 的 goal 一一对应。
- **ch03 研究内容**：与 goal 的 contents 对应项逐条展开；**数字（样本量/周期/数据量）无来源标"拟"** 并挂账。
- **ch04 技术路线**：按 routes.jsonl 展开：输入/输出/关键节点/风险/备选；写可行性依据，不罗列方法名。
- **ch05 创新点**：每条列 vs_existing（与谁比、差在哪、凭什么做得成）；**无对照依据禁用"首次/国际领先/填补空白"**。
- **ch06 研究基础与可行性**：只写材料可证实的成果（二态分清）；能力-证据-与本研究的关系；缺口列 notes_for_human。
- **ch07 预算（如有要求）**：逐条先入 budget_ledger.jsonl：`{"item":"…","amount":45.0,"source_locator":"M02:p3","status":"sourced|assumed|missing"}`；无来源金额不写数字，正文写占位符并标 missing。**与研究内容数字互相核对：预算口径与内容工作量一致**。

字数超限先压背景综述，不动技术路线与指标。

### Step 3 合稿与机检（4 次脚本）
```bash
python $SD/merge_chapters.py --chapters-dir /app/work/chapters --out /app/work/draft.json --title "…"
python $SD/docx_build.py /app/work/draft.json --out-docx /app/output/grant.docx --out-md /app/output/grant.md
python $SD/fact_ledger.py check --draft /app/output/grant.md --ledger /app/work/fact_ledger.jsonl --out /app/output/fact_check.json
python $SD/align_check_grant.py --alignment /app/work/alignment.jsonl --routes /app/work/routes.jsonl \
  --draft /app/output/grant.md --budget /app/work/budget_ledger.jsonl --out /app/output/align_check.json
```
fail 项修复一轮后重跑；仍 fail 的项如实写入 uncertainty（孤儿目标/不可考核指标/禁用断言/无来源预算必须修）。

### Step 4 渲染、组装、自检（2 次脚本 + 自检）
```bash
python $SD/render_preview.py --src /app/output/grant.docx --outdir /app/output/previews
python $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact grant.docx --artifact-md grant.md \
  --evidence /app/work/evidence_map.jsonl --fact-check /app/output/fact_check.json \
  --consistency /app/output/align_check.json --render /app/output/previews/render_log.json \
  --embed-file /app/output/grant.md --embed-key deliverable_content \
  --status complete --changelog '取舍记录'
```
自检（协议第 6 条）：JSON 可解析 / 契约键不缺 / case_id 一致 / deliverable_content 为全文 / status 如实 / 预算核对通过。

## 异常处置

| 情形 | 处置 |
|---|---|
| 无申报指南/模板 | 按目标基金通用章节组织；模板项标 unspecified；uncertainty 说明 |
| 前期成果材料不全 | 只写可证实的；缺口列 gaps + uncertainty；已完成/拟开展绝不混淆 |
| 预算信息缺失 | 逐条标 status=missing，金额写占位符；不编造金额；notes_for_human 提示人工核定 |
| 科学问题过大 | 收窄并在 changelog 记依据 |
| 单章响应被截断 | 已写部分先落盘回填；下一响应只写余下小节再合并 |
| 熔断触发（48 次/700 秒） | 立即收尾：已有章节组装，缺章与未核数字写 uncertainty |
| 脚本缺失/报错 | 全部异常捕获、如实登记；用现有中间结果走协议第 4/7 条 |

## 最小调用示例（示意，非正式案例结果）
```bash
SD=$(find /skills /app -type d -name scripts 2>/dev/null | head -1)
python $SD/extract_materials.py --input /input --outdir /app/work/extracted
# （模型逐章响应：ch01.md 立项依据 4 段带 evidence_map / ch07.md 预算 6 条全部 status=sourced）
python $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --embed-file /app/work/chapters/ch01.md --embed-key deliverable_content --append
python $SD/align_check_grant.py --alignment /app/work/alignment.jsonl --routes /app/work/routes.jsonl \
  --draft /app/output/grant.md --budget /app/work/budget_ledger.jsonl --out /app/output/align_check.json
# → {"verdict":"pass","goals":3,"budget":6,"types":[]}
python $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact grant.docx --artifact-md grant.md --status complete --embed-file /app/output/grant.md --embed-key deliverable_content
```

## 交付自查清单

- [ ] result.json 含 case_id 与 output_contract 全部键；deliverable_content 为申请书全文（逐章回填）
- [ ] 每章独立落盘且回填过（embedded_files 有记录）；无单响应全稿
- [ ] 四向对齐无孤儿项；指标可考核；路线含输入输出/风险/备选
- [ ] 创新点有 vs_existing；无"首次/领先/填补空白"裸用
- [ ] budget_ledger 逐条有 status；无来源金额未落数字；预算与内容口径一致
- [ ] 引用真实可溯（fact_check pass）；前期成果二态清楚
- [ ] grant.docx/grant.md 可编辑；渲染记录真实（无渲染器如实标 no_renderer）
- [ ] status/uncertainty/changelog 如实
