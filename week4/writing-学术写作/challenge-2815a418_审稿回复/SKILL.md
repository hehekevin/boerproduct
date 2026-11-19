---
name: acwrite-rebuttal
description: 审稿回复与论文修改技能：把审稿意见拆到子要求逐条回应（采纳/部分采纳/不采纳+理由），每处修改带 revision_log（original/revised/reason/basis）留痕并映射到稿件可检索锚点，证据补充清单跟踪到位状态，回复信-修订稿-基线稿三方一致机检，语气分四档受控；同输入对照脚本产出逐项增益证据，result.json 骨架由脚本先行落盘、主产物分批嵌入、任何失败都交付合法结果。Use when the case asks to draft point-by-point reviewer responses, revise the manuscript, map every revision to locators, track evidence status, keep response letter, revised manuscript and baseline consistent, or measure the gain of a rebuttal workflow against a degraded baseline.
---

# acwrite-rebuttal — 返修工作台（拆净 · 落位 · 留痕 · 对齐 · 可证）

返修的难点是**对得上**：意见的每个子要求都被识别、每处声称的修改真实落在正文、修改有留痕可回溯。交付四件：

1. **回复信** response_letter.docx/.md（逐条：意见→回应→修改位置→证据）
2. **修订稿** revised.docx/.md（只改指定基线，改动可检索）
3. **意见-改动台账** response_ledger.jsonl（子要求→决策→revision_log→锚点→证据状态）
4. **result.json**（case_id + 契约字段 + 主产物嵌入 + 三角对应表 + 增益证据 + 效率计数 + 诚实 status）

## 0. 强制执行协议（每条由脚本保证，违反即返工）

- **P1 骨架先行**：接手后第一个动作就是 `build_result.py init`——此后任何时刻崩溃，result.json 都是合法 JSON。这是脚本行为，不是提示词约定。
- **P2 字段一个不缺**：init 自动把 case.json `output_contract` 全部字段补进 result.json（缺值为 null）；`verify` 机检，fail 必须修复或写进 uncertainty。
- **P3 主产物必须嵌入**：回复信与修订稿除 docx/md 外，必须按审稿人/章节**分批** `build_result.py embed` 进 result.json（`letter_markdown` / `revised_markdown`）。status=complete 时嵌入为空或 <200 字 → verify fail。
- **P4 广度优先**：先把全部意见拆净、每个子要求都有决策行，再回头深化。禁止前 2 条意见精雕、后面意见空白。
- **P5 熔断**：自设预算 **48 次模型请求 / 700 秒**（平台 64/900 之内）。计数到 40 或 600 秒：立即 `finalize --status partial --notes 列缺口`。
- **P6 每阶段落盘**：每阶段产物写成文件（jsonl/json/md）再继续；Stage 4 与收尾各跑一次 `verify`。
- **P7 失败也交付**：材料缺失、解析失败、校验不过 → `finalize --status partial --notes`（finalize 会自愈重建骨架）。绝不空手、绝不伪造。
- **P8 status 诚实四级**：complete 仅当 回复信+修订稿+台账+三角对应表+ledger_audit verdict=pass 全齐；partial/failed/blocked 必须在 uncertainty 列出未完成项。
- **P9 脚本失败不中断**：所有校验脚本退出码恒为 0。verdict/problem 记录在报告与 result.json 里——**失败被如实记录，但绝不阻断交付**。
- **P10 增益必须真跑**：`gain_compare.py` 在**本次真实产物**上派生退化变体并跑同一机检器，数字写进 `gain_evidence`；禁止编造对照数字。

## 1. 运行环境

- 输入：`/input/case.json` + `/input/task.md` + 指定基线稿（materials/manuscript-baseline）+ 意见摘要（materials/reviewer-comments）。**读真实文件**，不按文件名猜内容。
- 工作区 `/app/work`，交付 `/app/output`。路径均可参数化（`--input/--out`），不存在时指向实际位置，不硬编码。
- 预算 64 请求 / 900 秒 / 16384 token；本技能按 P5 自设 48/700 熔断线，先广后深。

## 2. 线性五步

### Stage 0 — 读输入 + 落骨架（1 次脚本，最先执行）
```bash
ls -la /input/ && cat /input/case.json
python3 scripts/extract_materials.py --input /input --outdir /app/work/extracted
python3 scripts/build_result.py init --case /input/case.json --out /app/output/result.json
```
- 从 case.json 抄下 output_contract 字段清单；constraints.json 记录：意见条数、基线稿版本标识、语气惯例、修改允许范围。
- 意见摘要/基线是组织方整理稿：只修订指定基线，逐条处理实际给出的意见；不冒称真实审稿人逐字全文。

### Stage 1 — 意见拆解（1 次响应，写 /app/work/comments.jsonl）
每条意见拆到子要求（类型/严重度判定与拆净信号见 `templates/comment_taxonomy.md`）：
```json
{"cm":"C01","reviewer":"R1","type":"方法|数据|写作|格式|伦理","severity":"major|minor",
 "raw_quote":"意见逐字",
 "subs":[{"sid":"C01a","requirement":"子要求","action_needed":"…"}],
 "relates_to":["C03"]}
```
- 一条意见含多问必拆净（"补实验并更新图3"→两条）；交叉意见（R1-3 与 R2-1 同问题）关联，后续回复口径一致。
- **广度优先**：本轮覆盖全部意见，先不写回复文字。

### Stage 2 — 决策与改动台账（1-2 次响应，写 /app/work/response_ledger.jsonl）
每个子要求一行（字段说明见 `templates/ledger_template.jsonl`，定位写法见 `templates/locator_scaffold.md`）：
```json
{"sid":"C01a","cm":"C01","decision":"adopted|partially_adopted|rejected",
 "decision_rationale":"…",
 "edits":[{"eid":"E001","pid":"P12","locator":"§3.2 para4",
   "revision_log":{"original":"基线原句","revised":"改后句","reason":"回应C01a","basis":"M03 数据/意见依据"}}],
 "evidence":[{"what":"补数据 X","status":"done|replaced_by_alternative|not_possible","source":"M04 表2|替代说明"}],
 "letter_text":"回复信该条文字",
 "tone":"accept|clarify|polite_pushback|appeal"}
```
- **改得准**：每处修改外科手术式——revision_log 四字段（original/revised/reason/basis）一个不缺；联动改动（重编号、摘要同步）各建条目；locator 必填。
- **证得住**：材料能补的注明数据来源（M 编号 + 可逐字回证的引文）；不能补的给替代方案（补充分析/引用已有研究/列入局限），不用空话搪塞。
- **语气四档**：accept（致谢+已改）；clarify（澄清误解，引原文）；polite_pushback（先认可再给理由）；appeal（仅明显误判）。禁冒犯、禁过度承诺、禁无原则顺从。
- **可执行修改不得跳过**：意见摘要中的实质性修改必须真实落进基线稿；不能仅声明缺材料后跳过。

### Stage 3 — 生成修订稿与回复信 + 分批嵌入（2-3 次响应 + 脚本）
```bash
python3 scripts/docx_build.py /app/work/revised_draft.json --out-docx /app/output/revised.docx --out-md /app/output/revised.md
python3 scripts/docx_build.py /app/work/letter_draft.json --out-docx /app/output/response_letter.docx --out-md /app/output/response_letter.md
# 分批嵌入（长文按审稿人/章节分多次，规避单次响应 token 限制）
python3 scripts/build_result.py embed --out /app/output/result.json --key letter_markdown --file /app/output/response_letter.md --part full
python3 scripts/build_result.py embed --out /app/output/result.json --key revised_markdown --file /app/output/revised.md --part full
```
- 回复信格式：开头版本说明（基线版本+轮次）→ 按审稿人分组逐条（意见原文 → 回应 → 修改位置 §/段/锚点 → 新文本摘录）；骨架见 `templates/response_letter_template.md`。
- 若单文件过长，可先写分段文件再 embed 多次追加（--part R1/R2/...）。

### Stage 4 — 机检 + 增益对照 + 收尾（4-5 次脚本）
```bash
python3 scripts/ledger_audit.py --ledger /app/work/response_ledger.jsonl --letter /app/output/response_letter.md \
  --revised /app/output/revised.md --original /app/work/extracted --out /app/output/ledger_audit.json
python3 scripts/gain_compare.py --ledger /app/work/response_ledger.jsonl --letter /app/output/response_letter.md \
  --revised /app/output/revised.md --original /app/work/extracted \
  --out /app/output/gain_evidence.json --runlog /app/work/run_log.jsonl
python3 scripts/render_preview.py --src /app/output/response_letter.docx --outdir /app/output/previews
python3 scripts/build_result.py finalize --case /input/case.json --out /app/output/result.json --status complete \
  --artifact /app/output/response_letter.docx --artifact-md /app/output/response_letter.md \
  --evidence /app/work/response_ledger.jsonl --audit /app/output/ledger_audit.json \
  --gain /app/output/gain_evidence.json --runlog /app/work/run_log.jsonl \
  --render /app/output/previews/render_log.json --notes "C05b 证据需作者确认" --changelog "五步全部完成"
python3 scripts/build_result.py verify --case /input/case.json --out /app/output/result.json --report /app/output/verify.json
```
- **三方机检**：ledger_audit 输出**逐条三元组** {sid, item, applied, match}（回复↔回复信 letter_in_letter、修改↔修订稿 revised_in_revised、修改↔基线 original_in_baseline、revision_log 四字段、basis 定位、决策合法性、证据逐字回证、locator 存在、语气、覆盖、triad_ok）；unbacked 逐条列出并计入 fail。
- **闸门状态显式枚举** enforced/skipped_not_provided/not_found/unreadable：某输入缺失时审计记 gate_note，**未运行 ≠ 通过**，回复信不得宣称该项已核对。
- **同输入增益对照**：gain_compare 在**本次真实产物**上按确定性规则派生退化变体（baseline/no_decompose/no_revision_log/no_locator/no_verbatim），每个变体跑**同一个机检器与同一套指标口径**（分母固定为全量模式计数），产出逐项对照数字 + 机制→指标映射 + 效率计数 + 边界声明。数字是跑出来的，不是写出来的。
- **result.json 语义字段（题面《输出要求》三行，由 finalize 从台账+审计派生）**：`triad`（意见↔修改↔回复↔修订稿四角对应）、`fact_source_map`（事实与来源映射）、`version_boundary`（基线版本/修改差异/需人工确认项/材料缺口/异常）、`efficiency`（脚本调用与耗时实测计数）、`gain_evidence`（对照证据）。
- ledger_audit fail → 修台账/回复信/修订稿 → 重跑（审计报告始终写盘，verdict 如实；退出码仍为 0）。
- finalize 输出的 `contract_null_fields` 非空时：能填的回填（`set`），确无内容的写进 uncertainty。
- verify verdict=pass 才结束（complete 时级联机检：consistency_check 必须存在且 verdict=pass）；中途熔断：直接 finalize --status partial。

## 3. 异常处置表

| 情形 | 处置 |
|---|---|
| 意见指向内容基线稿找不到 | 记 unresolvable；回复信如实说明"基线稿无此内容，可能指…"；不乱改 |
| 要求补实验但材料无数据 | status=not_possible + 替代方案（补充分析/文献佐证/列入局限） |
| 两位审稿人意见冲突 | 不和稀泥：分别回应，说明取舍依据；needs_author 写入 uncertainty |
| 意见超出修改允许范围 | partially_adopted，说明范围限制 |
| 上一轮材料存在且承诺未兑现 | 逐条列出并补齐或说明原因；不假装已完成 |
| 纯格式意见 | 批量处理 + 一条汇总回复（列明细表） |
| 基线稿/意见文件缺失或不可提取 | extract 如实标记；finalize --status partial --notes 缺口 |
| 语气审计不过 | 回 Stage 2 重写该条再校验 |
| 台账某行 JSON 损坏 | audit 跳过该行并记 ledger_parse_error；回 Stage 2 修复该行 |

## 4. 最小调用示例（示意输出，非正式案例结果）
```bash
python3 scripts/extract_materials.py --input /input --outdir /app/work/extracted
# → {"ok":true,"summary":{"total":3,"extracted":3}}
python3 scripts/build_result.py init --case /input/case.json --out /app/output/result.json
# → {"ok":true,"cmd":"init","case_id":"case-demo","contract_fields":["case_id","summary","status"]}
# （模型响应：comments.jsonl 8 意见→19 子要求；response_ledger.jsonl 19 行、edits 31 处全带 revision_log）
python3 scripts/docx_build.py /app/work/letter_draft.json --out-docx /app/output/response_letter.docx --out-md /app/output/response_letter.md
python3 scripts/build_result.py embed --out /app/output/result.json --key letter_markdown --file /app/output/response_letter.md --part full
# → {"ok":true,"cmd":"embed","key":"letter_markdown","chars":4120,"total_chars":4120}
python3 scripts/ledger_audit.py --ledger /app/work/response_ledger.jsonl --letter /app/output/response_letter.md --revised /app/output/revised.md --original /app/work/extracted --out /app/output/ledger_audit.json
# → {"verdict":"pass","subs":19,"checks":95,"matched":95,"unbacked":0,"gates":{...enforced}}
python3 scripts/gain_compare.py --ledger /app/work/response_ledger.jsonl --letter /app/output/response_letter.md --revised /app/output/revised.md --original /app/work/extracted --out /app/output/gain_evidence.json --runlog /app/work/run_log.jsonl
# → {"ok":true,"modes":{"full":{...},"baseline":{...}},"manual_review_saved":7}
python3 scripts/build_result.py finalize --case /input/case.json --out /app/output/result.json --status complete --artifact /app/output/response_letter.docx --artifact-md /app/output/response_letter.md --evidence /app/work/response_ledger.jsonl --audit /app/output/ledger_audit.json --gain /app/output/gain_evidence.json --runlog /app/work/run_log.jsonl
python3 scripts/build_result.py verify --case /input/case.json --out /app/output/result.json
# → {"verdict":"pass","problems":[],"status":"complete","semantic_fields":{"triad":19,"fact_source_map":50,...}}
```

## 5. 交付自查清单（可观察判定见 `templates/scoring_sheet.md`）
- [ ] result.json 骨架是 Stage 0 脚本产物；崩溃后仍合法（P1/P7）
- [ ] output_contract 字段一个不缺（verify pass）
- [ ] letter_markdown / revised_markdown 已嵌入且 ≥200 字（P3）
- [ ] 每条意见拆到子要求；每个子要求有决策+回复+改动+证据状态（P4）
- [ ] 每处修改 revision_log 四字段齐全，revised 在修订稿可检索、original 在基线稿可检索、letter_text 在回复信可检索、locator 非空（ledger_audit 逐条三元组 pass，unbacked=0）
- [ ] triad / fact_source_map / version_boundary 三个语义字段非空（题面《输出要求》三行）
- [ ] gain_evidence 是本次真跑出来的：含 full vs baseline 逐项数字、机制→指标映射、边界声明
- [ ] efficiency 为实测计数（脚本调用数、耗时），不是自述
- [ ] 证据状态真实；语气审计通过；rejected 有据；闸门状态如实（未运行的项不宣称已核对）
- [ ] revised + response_letter 均可编辑；status 如实（complete 仅当全齐）；所有脚本退出码 0，失败未被吞掉（P9）
