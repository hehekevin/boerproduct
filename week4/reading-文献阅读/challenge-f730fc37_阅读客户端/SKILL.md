---
name: reading-client-loop
description: Scientific reading client MVP skill that completes the full reviewable loop "open paper -> locate paragraph -> selection QA -> save anchored annotations -> export interactive client" in one place. Answers are bound to verbatim anchors (paragraph_id + quote + offsets) on the current material; annotations persist to disk; a self-contained interactive HTML client embeds the paper text, highlights selections and evidence, and lets every answer jump back to its source location. Use when a task requires reading a scientific document, answering questions grounded in specific paragraphs/pages, saving annotations with exact anchors, or exporting a reviewable reading record. Handles paragraph-JSON, txt, md and PDF materials, including scanned PDFs without a text layer (graceful page-level degradation).
---

## 强制执行协议（最高优先级，与下文任何步骤冲突时以本节为准）

1. **第 1 个写盘动作是落骨架**：读完 /input/case.json 后，立即运行 `make_result.py --init` 写出
   /app/output/result.json 骨架（含 output_contract 全部键）。此后任何时刻 result.json 必须存在
   且 JSON 可解析；每次更新都整文件覆盖为最新完整状态。
2. **字段一个不缺**：终版 result.json 必须含 output_contract 全部键（机械校验会查）。某项无法产出
   时保留键并填 unknown/空数组/说明，把原因写进 uncertainties，不得删键、不得编造。
3. **广度优先**：先让全部要求产物以最小合格版本存在（骨架→索引→逐问答→批注→客户端→自检），
   再对高价值部分加深。禁止在单一产物上耗尽预算。
4. **预算熔断**：模型请求已用超过 48 次、或运行超过 700 秒时，立即停止新增分析，用现有中间结果
   覆盖写 result.json 并收尾（status=partial）。
5. **写盘前自检**：`check_all.py` 必须 PASS 才算完成。不过 → 修复对应问题 → 重跑自检。
6. **失败也交付**：任何中断/异常后仍要写 result.json：status 如实填
   answered / partial / insufficient_evidence / input_error，写明中断位置与已完成部分。
7. **不编造**：材料里没有的内容不写成事实。每个关键结论必须带逐字引文证据；
   无法判断就标 insufficient_evidence 并写入 uncertainties。

## 路径与脚本

- 输入：/input/case.json 与 task.md（以实际文件为准，不凭标签猜内容）。工作区 /app/work。
- 产物目录 /app/output：result.json、annotations.json、reading_log.jsonl、reading_client.html、
  check_report.json。
- 脚本在本 SKILL.md 同级的 `scripts/` 目录。调用前先定位：
  ```bash
  S=$(ls -d /skills/weekly-skill/scripts ./scripts 2>/dev/null | head -1)
  echo "$S"
  ```
  以下用 `$S` 指代脚本目录。

## 五步主流程

### 第 1 步：抄契约 + 落骨架（1 次脚本调用，0 次模型调用）

```bash
python "$S/make_result.py" --init --case /input/case.json --out /app/output/result.json
```

- 读 case.json 全文与 task.md：记下 task_instruction（任务到底要什么产物）、材料形态
  （paragraph-json / txt / md / pdf）、output_contract 全部键。
- 脚本机械生成骨架并保证契约字段一个不缺；若 case.json 不可读，骨架仍会落盘并注明。
- 顺带创建 /app/output/annotations.json（内容 `[]`）与 /app/output/reading_log.jsonl（空文件）。
- 追加一条 reading_log：`{"ts":"<ISO时间>","action":"init","detail":"骨架+契约抄录"}`。

### 第 2 步：建定位索引（1 次脚本调用，0 次模型调用）

```bash
python "$S/build_locator.py" --case /input/case.json --out /app/work/locator.json --input-root /input
```

- 产出逐段索引 `{paragraph_id, page, heading, text}`。支持 paragraph-json/txt/md/pdf；
  PDF 先 PyMuPDF 后 pypdf 兜底；扫描件无文本层 → locator.note=scanned_no_text_layer，
  定位降级为页码级，写入 uncertainties。
- 关键词定位（不耗模型请求）：`python "$S/build_locator.py" --case /input/case.json --out /app/work/locator.json --find "关键词"`

### 第 3 步：定位 + 选区问答（每问 1 次模型调用，逐问落盘）

对任务要求的每个问题/选区：
1. **定位**：先用 `--find` 或人工读索引锁定相关段落。上下文 = 选中文本 + 所在段落全文
   （最多加相邻 1 段）。禁止把整篇材料塞进提示。
2. **回答**：仅基于当前段落回答。依据不足 → 该问 status=insufficient_evidence，不硬答。
3. **绑锚点**：每问记录
   `{question_id, question, selection:{paragraph_id, quote(逐字), offsets}, answer, status, evidence:[{paragraph_id, quote(逐字), page}]}`。
   选区跨页/跨段 → 拆多条锚点，answer 说明合并语义。
4. **逐问落盘**：用 make_result.py --merge 把该问 qa 条目与 changelog 合入 result.json（机械合并，
   不重写全文件）；同时 append 一行 reading_log。**每问做完立即落盘，不留到最后。**

### 第 4 步：批注沉淀 + 主产物客户端

- 为每条问答生成批注（写 /app/output/annotations.json，数组逐条 append）：
  `{annotation_id, paragraph_id, page, selection_quote(逐字), offsets, question, answer, evidence_quote(逐字), status, created_at}`。
  selection_quote / evidence_quote 必须逐字存在于对应段落（自检会机械验证）。
- 更新 result.result.annotations_count 与 result.result.reading_position（最后阅读的段落号）。
- **生成阅读客户端界面 MVP**（主产物，0 次模型调用）：

```bash
python "$S/export_client.py" --result /app/output/result.json --annotations /app/output/annotations.json --locator /app/work/locator.json --out /app/output/reading_client.html --embed-result
```

  产出自包含交互 HTML：正文按段落渲染（段落号跳转、关键词搜索）、选区黄色高亮、证据绿色高亮、
  右栏问答卡片可一键跳回原文锚点、批注列表、阅读位置、边界说明。`--embed-result` 同时机械完成
  三件事：把整份 HTML 字符串嵌入 result.result.client.embedded_html（主产物嵌入 result.json）、
  登记 result.result.artifacts 三条路径、保留外部文件。

### 第 5 步：机械自检 + 终写（1 次脚本调用，0 次模型调用）

```bash
python "$S/check_all.py" --result /app/output/result.json --annotations /app/output/annotations.json --case /input/case.json --locator /app/work/locator.json
```

自检项：① 契约字段一个不缺；② case_id 一致；③ status 合法；④ 批注引文逐字命中 + offsets 越界；
⑤ qa 结构与 status；⑥ 客户端 HTML 存在且 embedded_html 与磁盘一致；⑦ reading_log 非空；
⑧ claims 每条带 kind/source_id/location/evidence；⑨ uncertainties 有 summary。
**PASS 后**用 --merge 写 changelog 终条目并确认 status 如实；FAIL → 按报告逐条修复再跑。

## 异常处置表

| 场景 | 处置 |
|---|---|
| case.json 不可读/乱码 | 骨架照常落盘（默认五字段），status=input_error，uncertainties 注明 |
| 扫描件无文本层 | 页码级定位，note=scanned_no_text_layer，uncertainties 注明 |
| 加密/超大 PDF | 保留已完成部分，status=partial，uncertainties 注明原因 |
| 选区跨页 | 拆多条锚点，answer 说明合并语义 |
| 问答缺依据 | 该问 status=insufficient_evidence，不硬答，写 uncertainties.unverifiable |
| 批注写盘失败 | 数据保留在 result.json 内，uncertainties 注明，继续流程 |
| 脚本异常 | 脚本自身 except Exception 全捕获并降级输出；仍失败则手工等效完成该步 |
| 预算熔断 | 立即收尾：现有中间结果覆盖写 result.json，status=partial，缺什么写什么 |

## result.json 结构

顶层 = output_contract 全部键（默认五字段）：
`case_id` / `status`(answered|partial|insufficient_evidence|input_error) / `result` / `claims` / `uncertainties`。

- `result.qa[]`：`{question_id, question, selection:{paragraph_id, quote, offsets}, answer, status, evidence:[{paragraph_id, quote, page}]}`
- `result.client`：`{kind:"self-contained-html", path, embedded_html}`（主产物嵌入）
- `result.annotations_count`、`result.reading_position`
- `result.artifacts`：`{client_html, annotations, reading_log}` 路径
- `claims[]`：`{claim_id, text, kind:reported|inferred, source_id, location, evidence:[{quote, paragraph_id, page}]}` —— 每条关键结论一条，evidence 为逐字引文
- `uncertainties`：`{unreported, unverifiable, conflicts, human_review, summary}`
- `changelog[]`：`{ts, action, detail}` 每步追加

## 脚本自测（已内置，可复现）

```bash
python "$S/make_result.py" --selftest && python "$S/build_locator.py" --selftest && python "$S/export_client.py" --selftest && python "$S/check_all.py" --selftest
```

四个脚本各含合成正例（正常输入必须通过）与反例（缺文件/二进制乱码/损坏 JSON 不得裸异常、
不得产出空结果）双测。全部 PASS 即脚本容错达标。

## 最小调用示例（示意，非正式案例答案）

合成 case（2 段材料 + 1 问）走五步：
1. make_result --init → result.json 骨架（5 契约键齐全，status=partial）。
2. build_locator → 2 段索引；`--find "Alpha"` 命中 p01。
3. 第 3 步：上下文=p01 全文 → 答 "recall 提升 12%"，锚点 selection.quote="Alpha improves"
   逐字命中 p01，evidence.quote="recall by 12%"；merge 入 result.json + reading_log 一行。
4. 第 4 步：批注 a-1 落盘；export_client 生成 reading_client.html（p01 内两处高亮，
   问答卡可跳回 anchor-p01）并嵌入 result.json。
5. 第 5 步：check_all PASS（9 项全过），status=answered。

以上为流程示意；实际结果以平台固定案例输入为准。

## 已知限制

- PDF 物理页与印刷页不一致时以物理页为准并注明差异；扫描件定位降级为页码级。
- 跨页选区拆多条锚点，合并语义在 answer 说明。
- reading_client.html 为单文件静态交互页（跳转/搜索/高亮/回看），不承载在线协作编辑。
- --find 关键词定位为精确子串匹配（忽略空白差异），不做语义检索。
