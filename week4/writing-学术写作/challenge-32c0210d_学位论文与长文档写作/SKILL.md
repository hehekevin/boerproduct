---
name: acwrite-thesis
description: 学位论文与长文档写作技能：双模式（起草模式全章节规划/成稿模式按工单改稿），跨章节登记簿（术语/符号/定义/结论）保持数万字一致，修订日志逐处留痕（原句/改句/理由/依据，只动需要动的地方），广度优先全章最小合格版先行再加深，主产物全文内嵌 result.json 并分批回填。Use when the case asks to plan/draft a thesis or long multi-chapter academic document from materials, or complete/revise provided working chapters per an edit workorder, maintaining cross-chapter consistency with auditable change records.
---

# acwrite-thesis — 学位论文长文档（双模式 · 登记簿制 · 修订留痕 · 主产物内嵌）

## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 7 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

1. **第0步先落盘骨架**：读完 /input/case.json 与题面后，第一个写盘动作就是在 /app/output/result.json 写入骨架：case_id 取自 case.json；键名严格按 case.json 或 task.md 中 output_contract 声明的每个字段生成（当前无法完成的字段值填 unknown 或空数组，绝不省略键）；status 填 "partial"。此后任何时刻 /app/output/result.json 必须存在且 JSON 可解析。
2. **字段一个不缺**：最终 result.json 必须包含 output_contract 的全部键。某项确实无法产出时，保留键并填 unknown、空数组或说明字符串，同时把原因写入 uncertainty，不得删除键、不得编造数据。
3. **主产物嵌入 result.json，分批回填**：论文章节全文（Markdown）必须完整写入 result.json 的 deliverable_content 键，同时另存 thesis.docx/thesis.md。单次响应 ≤16384 tokens——**每章单独成段写，写完一章就用 build_result.py --embed-file 刷新回填一次**，禁止把全文攒到最后一次性输出。result.json 里只有文件指针而无正文 = 不完整交付。
4. **广度优先 + 预算保护（本题生死线）**：先让**全部章节以最小合格版本存在**（每章 300-500 字骨架成文），再对高价值章节加深。禁止在单一章节耗尽预算。模型请求已用超过 48 次或运行时间超过 700 秒时，立即停止新增处理，用现有中间结果完成 result.json 并收尾。每次写 result.json 都覆盖为当前最新完整状态。
5. **模式识别（Step 0 必做）**：读 /input 下是否有 organizer-edit-workorder.json 或成段的"工作章节"（working chapters）——有 → **成稿模式 B**（按工单对指定章节做完成/改写，逐处修订留痕）；没有 → **起草模式 A**（按提纲从材料起草全稿）。判错模式 = 判错任务，Step 0 必须先定模式再动手。
6. **最终写盘前自检**：JSON 可解析、output_contract 字段一个不缺、case_id 与输入一致、status 如实、论文全文已嵌入 deliverable_content、revision_log 覆盖全部改动处。自检不过先修复再交付。
7. **失败也要交付**：处理中断或失败时，仍写 result.json（status="failed" 或 "partial"，写明中断位置与已完成章节），绝不让 /app/output 缺少 result.json。

## 流程（5 步线性执行）

脚本定位：先执行 `SD=$(find /skills -type d -name scripts 2>/dev/null | head -1)`；为空则用相对路径 `./scripts`。下文 `$SD/xxx.py` 均指此目录，绝不假设具体安装路径。

### Step 0 读契约、定模式、落骨架（最先做）
```bash
ls -la /input/ && cat /input/case.json
```
抄下 output_contract 全部键名与 case_id → 按**协议第5条**判定模式（A 起草 / B 成稿）→ **立即写 /app/output/result.json 骨架**（全部键+case_id，未完成字段填 unknown，status="partial"）。工单里的编辑目标（哪几章、什么动作：完成/改写/校对/格式/双语）逐条抄进 /app/work/workorder.json，作为 Step 2 的唯一任务清单——工单没要求的章节不动。

### Step 1 材料盘点 + 登记簿 + 工作章节清单（2 次脚本）
```bash
python $SD/extract_materials.py --input /input --outdir /app/work/extracted
python $SD/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
```
- 登记簿 /app/work/registers.jsonl 初始化：`{"kind":"term|symbol|definition|conclusion","key":...,"canonical":...,"aliases":[...],"basis":"M01:p3"}`。已有工作章节时，**先把原稿已有术语/符号/定义/结论全部抽取入册**（这是 B 模式"保留作者既有表述"的依据），再动手。
- B 模式额外记 constraints：作者原句保护范围、工单明确的格式/双语/引用约束。

### Step 2 章节规划/修改项拆解 + 全章最小合格版（2-4 次响应，产出 draft_all.json + revision_log.jsonl）
**A 起草模式**：
- chapter_plan.jsonl：`{"ch":"3","title":...,"role":"回答研究问题Q2","word_budget":8000,"evidence":["M03"],"outputs":"结论C3.1"}`；字数预算合计=总字数；每节写清"回答什么问题、需要哪些证据"。
- **第一轮：全部章节最小合格版**——每章标题+300-500 字成文（含核心论断与证据引用），逐章写入 draft_all.json 并回填 result.json。绪论-文献综述-方法-结果-讨论-局限-结论骨架齐全。
- **第二轮（预算允许时）**：按 word_budget 加深高价值章节（方法、结果、结论优先）。

**B 成稿模式**：
- 把 workorder.json 拆成逐条修改项：`{"item":1,"target_ch":"3.2","action":"补完","requirement":...}`。
- 只动工单指定的位置；改前先查登记簿与原文，**作者原句能保留就保留**；每一处改动写 revision_log.jsonl：`{"loc":"3.2:p2","original":"作者原句（逐字≤40字）","revised":"改后句","reason":"工单条目2要求补样本量","basis":"M03:t4","type":"rewrite|complete|format|flag"}`——"改得动"由此留痕，可回退、可比较。
- 材料支撑不了工单要求的章节：保留原稿+缺口说明+type:"flag"，不编造。
- 逐章写 draft_all.json → 每章完成即 build_result.py 回填（协议第3条）。

通用纪律：每章论断挂 evidence_map（locator+逐字摘录≤30字）；图表编号按章（图3-1）并在正文引用；术语/符号/结论先查登记簿再入册；材料不够标 [材料缺口]。

### Step 3 构建与机检（3 次脚本）
```bash
python $SD/docx_build.py /app/work/draft_all.json --out-docx /app/output/thesis.docx --out-md /app/output/thesis.md
python $SD/fact_ledger.py check --draft /app/output/thesis.md --ledger /app/work/fact_ledger.jsonl --out /app/output/fact_check.json
python $SD/cross_check.py --registers /app/work/registers.jsonl --draft /app/output/thesis.md --out /app/output/cross_check.json
```
fail 项修复一轮后重跑；仍 fail 的项如实写入 uncertainty（术语别名/符号冲突/结论失配必须修；B 模式修订处必须通过原文比对复核：original 字段能在原稿找到）。

### Step 4 渲染、组装、自检（2 次脚本 + 自检）
```bash
python $SD/render_preview.py --src /app/output/thesis.docx --outdir /app/output/previews
python $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact thesis.docx --artifact-md thesis.md \
  --evidence /app/work/evidence_map.jsonl --fact-check /app/output/fact_check.json \
  --consistency /app/output/cross_check.json --revision-log /app/work/revision_log.jsonl \
  --render /app/output/previews/render_log.json \
  --embed-file /app/output/thesis.md --embed-key deliverable_content \
  --status complete --changelog '取舍记录'
```
自检（协议第6条）：JSON 可解析 / 契约键不缺 / case_id 一致 / thesis.md 全文已嵌入 deliverable_content / revision_log 与改动一一对应 / status 如实。

## 异常处置

| 情形 | 处置 |
|---|---|
| 工单要求与材料冲突 | needs_supervisor 标注；不改数据事实；revision_log 记 type:"flag" |
| 材料只够写部分章 | 规划全骨架，全章最小版仍要写全（可写为缺口说明+材料需求），有据章节加深 |
| 前章结论在后章被推翻 | 按材料更强证据取新口径，两处联动改；revision_log 两条联动记录 |
| 术语多版本 | 选学科规范写法入册，aliases 记录变体 |
| 工作章节格式无法解析 | extract_materials 降级读纯文本；解析失败事实写入 changelog |
| 接近预算上限 | 立即收尾：已有章节组装 result.json，未完成章节在 chapter_plan/uncertainty 标注 |
| 脚本缺失/报错 | 全部异常捕获、如实登记；用现有中间结果继续走协议第4/7条 |

## 最小调用示例（示意，非正式案例结果）
```bash
SD=$(find /skills -type d -name scripts | head -1)
ls /input/   # 若有 organizer-edit-workorder.json → 成稿模式 B
python $SD/extract_materials.py --input /input --outdir /app/work/extracted
# （模型响应：registers.jsonl 40条登记 / workorder 拆解 6 个修改项 / 逐章成文并回填 result.json）
python $SD/docx_build.py /app/work/draft_all.json --out-docx /app/output/thesis.docx --out-md /app/output/thesis.md
python $SD/cross_check.py --registers /app/work/registers.jsonl --draft /app/output/thesis.md --out /app/output/cross_check.json
# → {"problems": [], "verdict": "pass"}
python $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact thesis.docx --artifact-md thesis.md --embed-file /app/output/thesis.md \
  --embed-key deliverable_content --revision-log /app/work/revision_log.jsonl --status complete
# → result.json 含 case_id、契约全键、deliverable_content 全文、revision_log 逐处改动记录
```

## 交付自查清单
- [ ] result.json 含 case_id 与 output_contract 全部键；deliverable_content 为论文全文
- [ ] 模式判定正确：B 模式严格按工单、只动指定处、作者原句保留
- [ ] 全部章节有最小合格版（无空标题）；高价值章节已加深
- [ ] registers 四类登记齐全；cross_check pass 或已说明
- [ ] 每章论断挂 evidence_map；图表编号跨章有序
- [ ] revision_log 逐处留痕（原句/改句/理由/依据）；fact_check pass
- [ ] thesis.docx/md 可编辑；status/uncertainty/changelog 如实
