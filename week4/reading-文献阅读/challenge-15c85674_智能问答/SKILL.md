---
name: literature-qa
description: Literature QA skill for numbered-paragraph papers with Chinese question lists. Answers every question and sub-question, binds EACH factual clause to its own claim with paragraph_id + verbatim quote (whitespace-normalized substring verified), separates reported from inferred, honestly marks partial / insufficient_evidence / input_error, embeds a machine verification gate (per-item checks + gate state) into result.json, and writes the five-field contract (case_id/status/result/claims/uncertainties) to /app/output/result.json. Use when answering supplied questions about a supplied paper with source evidence.
---

### 增益证据与效率计数（回填 result.json）
必须是**本次运行真跑出来的数字**，不是文字声明。两个脚本互补、写入不同键、互不覆盖：
```bash
python3 /skills/literature-qa/scripts/measure_gain.py --case /input/case.json \
    --result /app/output/result.json --mode compare --embed
python3 /skills/literature-qa/scripts/gain_evidence.py --result /app/output/result.json \
    --source /input/case.json --write
```
- measure_gain.py：同输入「完整机制 vs 退化重放」双跑 → `gain_evidence`（6 项指标 delta + 机制→指标映射 + 适用边界 + 失效条件）与 `efficiency`（自动采集计数）。
- gain_evidence.py：证据登记口径 → `registry_evidence`（证据登记数、逐字回证率、相对「不做登记」基线的人工核对削减量）。
- 机检/闸门失败**一律 verdict 照实记录、退出码恒 0**：修一轮，仍不过则如实登记并继续交付，禁止以非零退出码结束会话。


## 主路径收敛令（P0，覆盖其他流程指令）

1. **交付优先序**：骨架落盘 → 主字段/主内容补全 → result.json 完整可解析（此步完成即达到可交付状态）→ 校验器 → 增益层。
2. **增益层降级为可选**：gain_probe 的消融双跑与污染反例自测只在剩余预算（请求+时间）≥40% 时执行；预算不足直接跳过，在 result.json 的 gain_evidence 写 {"available": false, "reason": "budget_exhausted"}，**禁止**为增益证据挤占交付预算。
3. **预算告急即定稿**：任一时刻请求次数或时间过半仍未完成校验，立即以当前 result.json 定稿交付，缺失键如实登记，禁止继续展开任何支线。
4. 主线禁止执行污染反例自测（那是离线取证工具，非交付必需）。
## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 7 条是硬性纪律，优先级高于本文档其余内容；冲突时以本节为准。

1. 第0步先落盘骨架：读完 /input/case.json 与题面后，第一个写盘动作就是在 /app/output/result.json
   写入骨架：case_id 原样取自 case.json；键名严格按 case.json 的 output_contract（无则按本文 schema）逐个生成，
   当前无法完成的字段填 unknown 或空数组，绝不省略键；顶层 status 先填 "partial"。此后任何时刻该文件必须存在且 JSON 可解析。
2. 字段一个不缺：最终 result.json 必须包含契约全部键。某项确实无法产出时，保留键并填 unknown、空数组或说明字符串，
   同时把原因写入 uncertainties，不得删键、不得编造数据。
3. 广度优先 + 分批写：先让全部问题都有最小合格答案，再对高价值部分加深；每完成 2-3 题就整体覆盖回写一次
   result.json，单次写入正文 ≤1500 字，规避单响应 16384 token 截断。禁止在单一问题上耗尽预算。
4. 预算保护：模型请求已用超过 48 次或运行时间超过 700 秒时，立即停止新增处理，用现有中间结果收尾。
5. 最终写盘前自检：JSON 可解析、契约字段一个不缺、case_id 与输入一致、每问 status 如实。自检不过先修复再交付。
6. 失败也要交付：处理中断或失败时，仍写 result.json（status 用题面约定的失败值，写明中断位置与已完成部分），
   绝不让 /app/output 缺少 result.json。
7. 不编造：quote 必须逐字来自对应段落；无依据就如实标 partial 或 insufficient_evidence。宁可少答，不可编造引用。

## 用途与适用条件

- 根据带段落编号的论文文本逐题回答中文问题：每个事实性子句都能点回段落编号 + 逐字短引文；材料没写的答
  "材料未报告"，不用常识补。解决的白板不足：漏子问、引文不逐字、整题只挂一条笼统 claim、混淆实测与推断、缺信息硬编。
- 输入：/input/case.json（case_id、paper_id、material_version、带 paragraph_id 的段落清单、questions 清单、可能带
  output_contract）+ 题面。段落清单字段名可能是 paragraphs/passages/sections，以实际文件为准。仅依据给定材料作答。
- 不适用：PDF 解析、图像识别、联网检索、补充附件——一律按"材料未提供"处理。
- 运行环境：DSH 64 次模型请求 / 单次 16384 输出 token / 900 秒；工作区 /app/work；产物 /app/output/result.json。
  Skill 装入 /skills/literature-qa，脚本用该绝对路径。

## 输出 schema（result.json）

顶层五字段通用契约 + 题面业务字段同层 + verification 机检闸门 + gain_evidence/efficiency。业务结构放
result 内，**顶层同时保留 paper_id / material_version / answers / coverage**（题面《输出要求》表要求它们与
case_id 同层；校验器会把 result 内同名字段逐字重述到顶层，只搬运不生成）。若 case.json 声明 output_contract，
键名以其为准、含义与下表一致；缺省用下表：

```json
{
  "case_id": "原样回填", "paper_id": "原样回填", "material_version": "原样回填",
  "status": "answered | partial | insufficient_evidence | input_error",
  "coverage": {"read_paragraphs": ["p01"], "unread_sections": ["未读及原因"], "note": "阅读范围说明"},
  "answers": [
    {"question_id": "原样", "answer": "直接回答文本，子问逐个覆盖，句句可核",
     "conditions": ["数值/单位/比较对象/实验条件等成立条件"],
     "status": "answered | partial | insufficient_evidence | input_error",
     "claims": [{"claim_id": "c-01", "text": "一条子句级论断", "kind": "reported | inferred",
                  "source_id": "paper_id", "location": "paragraph_id",
                  "evidence": [{"paragraph_id": "p03", "quote": "逐字原文短引文"}]}],
     "unanswered_parts": [{"part": "未答子问题", "reason": "材料未报告 | 证据不足 | 读取失败"}]}],
  "result": {"paper_id": "原样回填", "material_version": "原样回填", "coverage": {}, "answers": []},
  "claims": "全部 answers[].claims 的汇总副本（claim_id 全局唯一，字段结构相同）",
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [{"what": "", "where": []}], "human_review": [], "summary": "整体边界说明"},
  "verification": "校验器回写的机检闸门：state 枚举 enforced/skipped_not_provided/not_found/unreadable；verdict 枚举 PASS/FAIL；checks 逐条 {item, template_value, applied, match, detail}；跳过时 gate_note 写明「下游不得宣称已核对」",
  "gain_evidence": "同输入「完整机制 vs 退化重放」双跑的实测对照：6 项指标 delta + 机制→指标映射 + 适用边界 + 失效条件（measure_gain.py --embed 写入）",
  "efficiency": "自动采集计数：model_requests / tool_calls / evidence_lookups / repair_rounds / steps / 条目数 + 每项来源 + 复现命令（measure_gain.py --embed 写入）",
  "registry_evidence": "证据登记口径：证据登记数、逐字回证率、相对基线的人工核对削减量（gain_evidence.py --write 写入，与 gain_evidence 互补不覆盖）"
}
```

## 证据密度纪律（answer ↔ claims 双向对齐）
1. 子句级拆分：answer 按语义拆子句——一个数值、一处比较、一条结论、一组条件各成一条 claim。经验密度：每问至少
   1 条 reported claim；含数值/比较/因果的问题 2-4 条；跨章节综合题每个章节来源各至少 1 条。
2. 双向对齐：answer 里每个事实性子句都能在 claims 中找到对应条目；claims 里每条都要支撑 answer 的某个子句，
   不挂无关装饰性 claim。
3. 数值逐字回证：answer 中每个 ≥2 位数值必须出现在某条 quote 中；推断计算值例外（数值出现在对应 inferred
   claim 文本中即覆盖）；标识符/引用标签编号不计入（p01、c-01、表 12、图 23、第 3.2 节），但中文紧邻数值必须
   计入（"保持率为84.3%" 的 84.3 要回证；区间 1.2-3.4 两端都要回证）；unbacked 逐条列出计 fail。
4. 逐字引文：quote 从段落文本原样截取（空白归一化后必须是该段子串），≤2 句，优先选包含关键数值/术语的最短充分
   片段；禁止改写、翻译、拼接两句。
5. 来源分开：论文实测结果与作者陈述 → reported；由材料推出的结论 → inferred 且 answer 中用"据材料推断"等措辞区分，
   evidence 给推断依据段。
6. conditions 收全：数值题必含数值、单位、比较对象、实验条件四要素，缺哪样就在 answer 里注明材料未报告。

## 执行流程（6 步）

流水线阶段名（写 run_log 用，固定）：load_input → read_questions → decompose_subquestions → locate_evidence
→ draft_claims → structure_check → evidence_verify → numeric_verify → repair_loop → deliver。

1. **读题抄契约**：读 /input/case.json 与题面全文不跳读；抄录 case_id、paper_id、material_version、questions
   全清单（question_id + 文本 + 全部子问）、段落清单字段名与段数；有 output_contract 则列出全部键名，后续键名严格照抄。
2. **落盘骨架**：立即写 /app/output/result.json 骨架（协议第1条）。每个 question_id 一条空记录
   `{"question_id":…, "answer":"", "conditions":[], "status":"partial", "claims":[], "unanswered_parts":[问题全文]}`；
   coverage 置空对象；顶层 status="partial"。问题清单缺失/乱码：全部 status="input_error"，unanswered_parts 写明
   原因，仍输出合法 result.json。
3. **逐题证据与作答（子句级密度）**：广度优先，每 2-3 题回写一次。逐题：拆子问 → 每个子问定位证据
   （1-3 段）→ 记 paragraph_id + 逐字短引文 → 拆子句级 claims → 撰写与 claims 对齐的 answer；数值题四要素
   进 conditions[]，缺项注明"材料未报告"；无依据子问标 insufficient_evidence 并写明检索范围；材料内部冲突
   双方引文都列、指出出处、写入 uncertainties.conflicts。
4. **机械自检（闸门回写）**：运行
   `python3 /skills/literature-qa/scripts/check_result.py --result /app/output/result.json --case /input/case.json`
   （脚本缺失/报错时降级手动核对，不阻塞交付）。脚本逐条机检并把 verification 闸门（逐条 {item,
   template_value, applied, match, detail} + gate 状态 + gate_note）回写嵌入 result.json：五字段、题面字段
   语义、question_id 全覆盖、status 枚举、quote 逐字子串、claim 四要素（kind/source_id/location）、证据密度、
   answer 数值逐字回证（unbacked 逐条列出计 fail）。不过则回第3步对着原文修复，直到 verification.verdict=PASS。
   **该脚本退出码恒为 0**：PASS/FAIL 看 result.verification.verdict 与 problems，勿用退出码判断。
5. **增益与效率取证**：运行 `measure_gain.py --case /input/case.json --result /app/output/result.json
   --mode compare --embed`（同输入「完整机制 vs 退化重放」双跑 → gain_evidence：6 项指标 delta + 机制→指标映射
   + 适用边界 + 失效条件；efficiency：自动采集计数），再运行 `gain_evidence.py --result /app/output/result.json
   --source /input/case.json --write`（证据登记口径 → registry_evidence）。两脚本写不同键、互不覆盖。脚本缺失/
   报错时跳过，不阻塞交付（字段缺失只记 warn）。为让计数真实，运行中每完成一个阶段就往
   /app/output/run_log.jsonl 追加一行：`{"kind":"stage","stage":"locate_evidence"}` / `{"kind":"model_request"}` /
   `{"kind":"tool_call"}` / `{"kind":"write"}` / `{"kind":"repair"}`。
6. **终稿交付**：补全 coverage（read_paragraphs 列实际读过的段落 id，unread_sections 列未读章节及原因）；按状态
   判定表更新每问与顶层 status；顶层 claims 从 answers 汇总（复制，claim_id 全局唯一）；补全 uncertainties
   五键；最终写盘后再跑一次第4步自检，verdict=PASS 才交付。

## 状态判定与异常处置

| status | 判定条件 | 异常情形 → 处置 |
|---|---|---|
| answered | 子问完整回答，主要子句均有证据支撑 | 问题无依据 → insufficient_evidence + 检索范围，不硬答不编造 |
| partial | 只能回答部分子问/方面，缺口写入 unanswered_parts | 只能答子问题 → partial + unanswered_parts 逐项列缺口 |
| insufficient_evidence | 材料无依据，answer 写明检索范围；"材料未报告"是有效回答 | 段落编号与引文对不上 → 以实际段落文本重新定位，禁止猜编号 |
| input_error | 输入读取失败 / 问题清单缺失乱码 | case.json 缺失/乱码 → 全部 input_error 仍输出合法 result.json；材料内部数值/结论冲突 → 双方引文都列并写入 uncertainties.conflicts；预算逼近上限 → 按协议第4条收尾 |

整体 status：全部 answered → answered；存在 partial 或 insufficient_evidence → partial；全部 insufficient_evidence → insufficient_evidence；输入读取失败 → input_error。完成度结合回答依据与材料边界判断，不能仅凭 status 标签。

## 最小示例（示意，非正式）

输入（合成材料，仅演示接口）：`{"case_id":"demo-001","paper_id":"demo-A","material_version":"v1","paragraphs":[{"paragraph_id":"p01","text":"The coating retained 84.3% capacity after 200 cycles at 1C, versus 71.0% for the uncoated electrode."}],"questions":[{"question_id":"q1","text":"涂层的循环保持率是多少？与未涂层相比如何？"}]}`

输出要点（示意）：q1.answer = "涂层电极在 1C、200 次循环后保持率为 84.3%；据材料推断，涂层使保持率高于未涂层电极（71.0%）约 13.3 个百分点。"
claims 拆多条子句级条目（84.3%、71.0%、归因各一条 reported；13.3% 差值为 inferred 且数值出现在其 claim 文本中），每条带 source_id/location + 逐字 quote。
完整结构见 examples/example-result.json（本地校验 PASS）与上方 schema。此为示意输出，不作为正式效果证明。

## 已知限制

- 依据完全依赖给定段落文本：编号错位或段落截断会降低定位质量。不读 PDF/图像/补充材料，此类内容按"材料未提供"处理。
- inferred 论断的语义正确性无法机械校验；脚本只校验结构、引文逐字性、数值回证与密度。
- gain_evidence 为**同输入机制消融**（完整机制 vs 退化重放），不是平台白板实测；平台白板由平台侧生成。
- 复用建议：同类"论文+问题清单→结构化作答"任务可直接复用；换领域只需替换段落与问题，schema 与纪律不变。
