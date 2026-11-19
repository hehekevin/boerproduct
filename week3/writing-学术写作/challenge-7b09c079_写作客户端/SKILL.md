---
name: acwrite-revision-client
description: Academic writing revision client skill that completes the reviewable loop "receive manuscript -> apply instructions surgically -> keep per-edit revisions -> export editable document" in one place. Every edit is an itemized revision entry (paragraph anchor pid + verbatim before + after + rationale + level), applied onto a paragraph-level anchor index; deliverables are revised.docx/revised.md + edits.jsonl ledger + diff + versions lineage + a self-contained interactive revision client HTML (per-edit accept/reject/confirm, v1/v2 compare, filtered ledger, export accepted Markdown + decisions JSON) fully embedded in result.json with a registered feature list, plus same-input mechanism-ablation evidence (gain_evidence) and efficiency counters. Use when a task asks to revise a manuscript per instructions with tracked, itemized, accept/reject-able edits, keeping structure, citations and formatting intact.
---

## 强制执行协议（最高优先级，与下文任何步骤冲突时以本节为准）

1. **第 1 个写盘动作是落骨架**：读完 /input/case.json 后立即运行 `build_result.py --init` 写出
   /app/output/result.json 骨架（含 output_contract 全部键）。此后任何时刻 result.json 必须存在且 JSON
   可解析；每次更新都整文件覆盖为最新完整状态。**字段一个不缺**：终版必须含 output_contract 全部键；
   某项无法产出时保留键并填 unknown/空数组/说明，原因写进 uncertainties，不得删键、不得编造。
2. **广度优先**：先让全部要求产物以最小合格版本存在（骨架→锚点→拆解→台账→修订稿→客户端→自检），
   再对高价值部分加深；禁止在单一产物上耗尽预算。
3. **预算熔断**：模型请求已用超过 48 次、或运行超过 700 秒时，立即停止新增分析，用现有中间结果覆盖写
   result.json 并收尾（status=partial）。
4. **写盘前自检**：`check_all.py` 必须 verdict=pass 才算完成；不过 → 修复对应问题 → 重跑自检。
5. **失败也交付**：任何中断/异常后仍要写 result.json：status 如实填 complete/partial/failed/blocked，
   写明中断位置与已完成部分。
6. **不编造**：材料里没有的内容不写成事实。每处改动的 before 必须逐字来自原稿、after 必须逐字出现在
   修订稿；无法定位的指令标 unresolvable 并写入 uncertainties，不猜位置乱改。
7. **退出码恒 0**：本 Skill 所有脚本在任何路径（通过/失败/缺料/异常）都退出 0，结论一律由报告里的
   verdict 字段照实记录。**校验失败不中断交付**——按报告逐条修复再跑，不要当成"脚本坏了"而中断流程。

## 路径与脚本

- 输入：/input/case.json 与 task.md（以实际文件为准，不凭标签猜内容）。工作区 /app/work。
- 产物目录 /app/output：result.json、revised.docx、revised.md、diff.md、versions.jsonl、
  revision_client.html、edits_verify.json、gain_evidence.json、check_report.json、previews/。
- 脚本在本 SKILL.md 同级的 `scripts/` 目录（8 个脚本，纯标准库，无外部依赖、无 CDN）。调用前先定位
  `S=$(ls -d /skills/weekly-skill/scripts ./scripts 2>/dev/null | head -1)`，以下用 `$S` 指代脚本目录。

## 七步主流程

### 第 1 步：抄契约 + 落骨架（1 次脚本调用，0 次模型调用）
```bash
python "$S/extract_materials.py" --input /input --outdir /app/work/extracted
python "$S/build_result.py" --init --case /input/case.json --out /app/output/result.json
```
- 记下 task_instruction（要什么产物）、修改指令清单、允许的编辑层面（措辞/结构/术语/引用/格式）、
  格式规范 → /app/work/constraints.json。骨架保证契约字段一个不缺。

### 第 2 步：原稿段落锚点索引（1 次模型调用，产出 /app/work/structure.json）
每段 `{"pid":"P12","locator":"§3.2 para4","heading":"标题","text":"段落全文"}`。**pid 是改动定位的基础，
在修订中永不重编**（删段只标 deleted）；长文档逐节处理，禁止一次性吞整篇。
### 第 3 步：指令拆解（1 次模型调用，产出 /app/work/instructions.jsonl）
`{"iid":"I01","type":"措辞|结构|术语|引用|格式|内容","target":"§3.2 para4 / 全文所有'X'","action":"替换|删除|移动|合并|拆分|重编号|补充","scope_level":"句子|段落|章节|全文","status":"pending"}`。
一条指令含多个子要求时拆开；指令冲突/含糊 → 保守解释执行并记 ambiguity；不擅自替作者做主。

### 第 4 步：修订台账（1-2 次模型调用，产出 /app/work/edits.jsonl）
每处改动一行：`{"eid":"E001","iid":"I01","pid":"P12","locator":"§3.2 para4","before":"原句逐字","after":"改后文本","rationale":"依据（指令编号+理由）","level":"措辞","side_effects":["图1编号引用"],"status":"applied","decision":"accept|reject|confirm"}`。
- **外科手术原则**：改句子不动段落；语义漂移为零（除非指令是内容修改）。引用/编号联动：增删引用 →
  参考文献表重排 + 全文编号同步，联动改动各建一条 edit。标题层级、表格、题注不动（除非指令明确要求）。
  **每处改动先建条目再落稿**；未授权改动一字不做。

### 第 5 步：应用修订生成新稿（1 次模型调用 + 3 次脚本）
按 edits.jsonl 从 structure.json 组装 revised draft.json（保留原结构框架，只替换目标单元）：
```bash
python "$S/docx_build.py" /app/work/revised_draft.json --out-docx /app/output/revised.docx --out-md /app/output/revised.md
python "$S/render_preview.py" --src /app/output/revised.docx --outdir /app/output/previews
python "$S/build_result.py" --diff-from-edits --edits /app/work/edits.jsonl --out-diff /app/output/diff.md --out-versions /app/output/versions.jsonl
```
- `--diff-from-edits` 机械生成 diff.md（逐条 E001 [I01] §3.2 para4：~~原句~~ → 新句（依据…）+ 建议裁决）
  与 versions.jsonl（v1/v2 谱系），**不靠模型手写**，省预算且不会漏条。

### 第 6 步：claims 机械挂链 + 主产物修订客户端（2 次脚本调用，0 次模型调用）
```bash
python "$S/build_result.py" --claims-from-edits --edits /app/work/edits.jsonl --result /app/output/result.json
python "$S/export_client.py" --case /input/case.json --structure /app/work/structure.json --edits /app/work/edits.jsonl --result /app/output/result.json --out /app/output/revision_client.html --embed-result
```
- `--claims-from-edits`：每处改动机械生成一条 claim（kind=reported、source_id=case_id、location=pid、
  evidence=逐字原文），证据链每条挂齐不漏。
- `--embed-result`：生成自包含交互 HTML（浏览器直接打开即用，零 CDN 零外链）并**整份嵌入**
  result.result.client.embedded_html，同时登记 features 8 条功能清单与 artifacts 三条路径。
- 客户端八项交互：①修订逐条接受/拒绝/需确认（localStorage 跨会话持久）②修订卡锚点跳转回原稿
  ③v1 原稿/v2 按裁决合成修订稿对照 ④按裁决一键导出已接受修订 Markdown + 裁决 JSON
  ⑤按指令号/层面/裁决状态筛选 ⑥关键词搜索+导航 ⑦引用与格式哨兵 ⑧边界与人工确认项展示。
  客户端内裁决以"导出裁决 JSON"为持久化交接形式，与 Agent 端 edits.jsonl 相互独立。

### 第 7 步：增益对照 + 终局机械自检（2 次脚本调用，0 次模型调用）
```bash
python "$S/gain_eval.py" --structure /app/work/structure.json --edits /app/work/edits.jsonl --draft /app/work/revised_draft.json --revised /app/output/revised.md --result /app/output/result.json --out /app/output/gain_evidence.json --write-back
python "$S/check_all.py" --result /app/output/result.json --case /input/case.json --edits /app/work/edits.jsonl --structure /app/work/structure.json --revised /app/output/revised.md --client /app/output/revision_client.html --write-back
```
- **gain_eval（使用增益证据）**：同输入跑 full 与 degraded 两个条件（degraded = 关掉锚点/逐条裁决/
  导出校验的确定性基线重建），由同一套测量函数当场算出真实数字：修订可追溯率、改准率、落地逐字率、
  错落改动数、误改段落数、格式塌陷数、需人工核对条目数与字符量、步骤数与工具调用数。
  `--write-back` 把 gain_evidence（comparison + mechanism_to_metric + boundaries）与
  efficiency（steps/tool_calls/manual_review_*/reproduce）回填 result.json 顶层。
  **不得手填这些数字**；脚本测不出就如实记 missing_inputs。
- **check_all**：①契约字段齐全 ②case_id 一致 ③status 合法 ④修订 before 逐字命中原稿
  ⑤applied 的 after 逐字命中修订稿 + 引用编号连续 ⑥claims 证据链完整且引文逐字回证
  ⑦客户端 HTML 存在且 embedded_html 与磁盘一致 + features 登记 ⑧uncertainties 有 summary
  ⑨changelog 非空 ⑩gain_evidence/efficiency 齐备且对照项非空。逐条输出 {item, applied, match} 三元组
  + 闸门显式枚举（enforced / skipped_not_provided / not_found / unreadable）写回 result.json 顶层
  checks / gates / gate_note；闸门未 enforced 时 gate_note 写明"下游不得宣称已核对"。
  **PASS 后**确认 status 如实并写 changelog 终条目；FAIL → 按报告逐条修复再跑。

## 异常处置表

| 场景 | 处置 |
|---|---|
| 指令位置在原稿找不到 | 记 unresolvable 并入 uncertainties，不猜位置乱改 |
| 原稿是 PDF（不可直接编辑） | 转出可编辑文本层后执行；转换损耗如实登记 |
| 指令之间冲突 | 保守执行高优先级者，冲突记录 + uncertainties |
| 引用重编号后交叉引用错位 | edits_verify 检出 fail，回第 4 步修复 |
| 修订与格式规范冲突 | 格式规范优先，指令部分执行 + 说明 |
| 文档损坏/加密/样式不可识别/导出失败 | 保留已完成部分，status=partial，渲染失败如实登记不伪造 |
| structure.json 不可读 | 客户端仍生成（空段落渲染），uncertainties 注明定位降级 |
| 脚本异常 / 环境无渲染器 | 脚本自身全捕获并降级输出；渲染失败记 no_renderer 不伪造 |
| 预算熔断 | 立即收尾：现有中间结果覆盖写 result.json，status=partial，缺什么写什么 |

## result.json 结构

顶层 = output_contract 全部键（默认五字段）**+ 增益与自检字段**：`case_id` /
`status`(complete|partial|failed|blocked) / `result` / `claims` / `uncertainties` / `changelog[]` /
`gain_evidence` / `efficiency` / `checks[]` / `gates` / `gate_note` / `verdict`。
`result` 内：`client`（kind/path/features[8条]/embedded_html）、`target_artifact`、`revision_records`
（逐条四元组）、`adjudication`（裁决面）、`exports`（交付清单）、`version_and_boundary`、
`edits_count / instructions_total / instructions_executed`、`artifacts`；
`claims[]`：`{claim_id, text, kind, source_id, location, evidence:[{paragraph_id, quote}]}`（第 6 步机械生成）；
`uncertainties`：`{unexecuted_instructions, ambiguity, human_review, material_gaps, summary}`。

## 最小可运行自检 + 调用示例（示意，非正式案例答案）

```bash
python "$S/gain_eval.py" --selftest     # 脚本容错双测（合成正例 + 污染反例）
python "$S/gain_eval.py" --selfcheck    # 包内合成夹具上跑完整七步 + 对照 + 终局自检
```
- `--selftest`：正例必须通过、反例（缺文件/二进制乱码/锚点错位/嵌入不一致）必须被抓住且不得裸异常；
  退出码恒 0，结论看最后一行 SELFTEST PASS/FAIL。`--selfcheck`：在 `examples/demo/` 合成夹具上
  跑通全链路，校验 result.json 的 gain_evidence / efficiency 齐备、闸门全 enforced、8 件产物落盘，
  并打印 full vs degraded 对照数字。
- 合成 case（7 段材料 + 5 条指令 → 4 处改动）走七步：--init 落骨架（5 契约键齐全，client.features
  预登记，status=partial）→ structure.json 7 段锚点 / instructions.jsonl 5 条 / edits.jsonl 4 处改动
  （before 逐字来自原稿段落）→ revised.docx + revised.md + diff.md（--diff-from-edits 机械生成）+
  versions.jsonl + 渲染 previews → --claims-from-edits 出 4 条 claim 证据链，export_client --embed-result
  出 revision_client.html（4 张修订卡可逐条接受/拒绝，v2 视图实时合成，可导出已接受修订 Markdown 与
  裁决 JSON）嵌入 result.json + features 8 条 → gain_eval --write-back 落 gain_evidence + efficiency
  （真实对照数字，非自述），check_all verdict=pass（25 条校验）、gates 5 项全 enforced、status=complete。
  以上为流程示意；实际结果以平台固定案例输入为准。

## 已知限制

- revision_client.html 为单文件静态交互页（逐条裁决/版本对照/筛选/搜索/导出），不承载多人在线协作；
  客户端本机裁决存浏览器 localStorage，持久化以"导出裁决 JSON"为准。v2 视图为按裁决实时合成的预览，
  正式回填稿件以 revised.docx/revised.md 与导出 Markdown 为准；定位为精确子串匹配（忽略空白差异）；
  PDF 原稿先转文本层，转换损耗如实登记。渲染失败如实登记于 gates.render_preview 与 uncertainties，
  不伪造。
- gain_evidence 是**同输入机制级 A/B**（同一脚本、同一输入、只切换机制开关），不是平台
  "基础 Agent vs 加载 Skill 的 Agent"对照——后者由平台生成，本 Skill 不冒充、不改写。
