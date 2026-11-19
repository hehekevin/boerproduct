---
name: benchkit
description: 文献阅读 Benchmark 与评测工具技能：把 benchmark-DRAFT 工单（source-conditioned 条目，来源为段落/表格文本）建成可判分、可复跑、可溯源、可迭代的最小评测包——题卡、统一运行原始输出、0/1/2 逐题评分（判分口径机械可观察+每行判分依据）、失败样例 8 类归因、逐题报告、item 级版本快照与定向重算、严格臂 vs 基础（无工具）判分的同输入增益对照、效率计数。评测包全量嵌入 result.json，每个分数顺 item_id 可追到原始输出与评分行。技术合成检查日志与 score_suggest 不是 DSH 分数也不是独立语义验证。Use when asked to build/run/score/version/audit a literature-reading benchmark, 题集, 评测工具, 评分表, 失败分析, 评测报告, benchmark workorder.
---

### 增益证据与效率计数（回填 result.json）
必须是**本次运行真跑出来的数字**，不是文字声明：
```bash
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --baseline
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --write
```
- 第一条：基础模式对照——模拟「不做证据登记/不做逐条回证」的路径，统计源材料里有多少实体与数值会变成不可核对项（需人工逐条核对的规模）。
- 第二条：当前模式实测——证据登记数、证据逐字回证率、三元组 match 通过率、需人工核对条目数，并计算相对基线的削减量；`--write` 写入 `result.json.registry_evidence`（含 `baseline_comparison.reduction` 与 `efficiency` 计数；若本包另有脚本写 `gain_evidence`，两者互补不覆盖）。
- 机检/闸门失败**一律 verdict 照实记录、退出码恒 0**：修一轮，仍不过则如实登记并继续交付，禁止以非零退出码结束会话。

## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 7 条是硬性纪律，优先级高于本文档其余内容；冲突时以本节为准。

1. **先抄契约**：读完 /input/case.json 与题面，把 output_contract 的**每个键名**原样抄成清单
   （任意层级出现即算，含嵌套；contract 为键名列表时逐个抄），并抄下 case_id。键一个不漏。
2. **立即落骨架**：第一个写盘动作就是在 /app/output/result.json 写骨架——契约全部键 + case_id/
   status/result/claims/uncertainties；无法完成的字段填 unknown 或空数组，绝不省略键，status 填
   partial。此后任何时刻 result.json 必须存在且 JSON 可解析。
3. **字段一个不缺**：最终 result.json 必须含契约全部键 + 本文档 result.result 的全部嵌入字段。
   无法产出时保留键并填 unknown/空数组，原因写进 uncertainties，不得删键、不得编造。
4. **广度优先**：先让全部产物以最小合格版本存在，再对高价值部分加深；禁止在单一产物上耗尽预算。
5. **预算熔断**：模型请求超 48 次或运行超 700 秒（平台预算 64 请求/900 秒），立即停止新增处理，
   用现有中间结果完成 result.json 收尾；每次写 result.json 都覆盖为当前最新完整状态。
6. **失败也要交付**：中断或失败时仍写 result.json（status 用题面约定的失败值，写明中断位置与已
   完成部分），绝不让 /app/output 缺少 result.json。
7. **分批写防截断**：单次响应 16384 token 上限——写 answer_raw、report 等长文本时每次只写一段
   （≤1500 字），写完即回填下一段直到写齐；每完成一步立即写盘，绝不在内存攒全文最后写。

写盘前自检：JSON 可解析、契约键一个不缺、case_id 与输入一致、status 如实、关键论断有 claims
证据。不过先修复再交付。

## 目标与边界

把 /input/case.json 的 benchmark-DRAFT 工单建成**最小评测包**，九件全部落盘且全量嵌入 result.json：
`items.json`（题卡）→ `run_results.json`（原始输出+技术检查）→ `scores.csv`（0/1/2+判分依据）→
`failure_samples.json`（失败样例）→ `version.json`（item 级快照）→ `diff.json`（版本对比）→
`report.md`（逐题报告）→ `gain_evidence.json`（同输入双臂判分对照）→ `efficiency.json`（效率计数）
→ `result.json`（全量嵌入+claims+uncertainties）。
六方面覆盖：任务定义=题卡 task/scoring_rule；数据与答案管理=source_text_snapshot+reference_answer+
version 快照；评分维度=0/1/2 判分线+scores；原始输出留存=run_results 全文嵌入；误差分析=
failure_samples 8 类归因+report.md 逐题报告；版本迭代=diff 定向重算+可比性标记。

诚实边界（必须如实声明，不得越过）：工单条目是 source-conditioned，来源是段落/表格文本而非 PDF 像素
金标；技术合成检查日志与 score_suggest 不是 DSH 分数也不是独立语义验证，只做确定性校验（数值逐字覆盖、
条件词覆盖），语义正确性只由 0/1/2 评分规则判定，两者分开记录；无参考答案的题如实标『仅规则评分』，
不编造分数或数据，推断不当事实；**gain_evidence 是判分口径增益**（同批作答在两套判分口径下的差异），
不是跨 Agent 能力增益，跨 Agent 对照由平台固定白板负责。

## 调用脚本

脚本在本 SKILL.md 同目录的 `scripts/benchkit.py`（记为 `$SK/scripts/benchkit.py`，$SK 为本文件所在目录；
找不到时 `find / -name benchkit.py -path '*scripts*' 2>/dev/null | head -1` 定位）。子命令：`init /
techcheck / diff / report / gain / efficiency / embed / verify`。脚本缺失或报错时按本文档 schema 手写
等价 JSON 继续，流程不中断，降级写入 uncertainties.summary。**所有命令异常时自动降级（warn.log +
退出码恒 0）**；case.json 损坏/结构未知时写兜底题卡，绝不产出空题集；verify 失败时 verdict 如实记
FAIL，退出码仍恒 0——校验器不得中断交付。

## 五步流程

**第 1 步 抄契约**。读 /input/case.json 与题面，抄下 output_contract 全键与 case_id。把工单条目
逐条抄成清单，一条不漏：task、input_ref、conditioning、source_text、reference_answer、
scoring_rule、difficulty。conditioning 逐条保留——出题条件丢了的题不算 source-conditioned。数值
逐字照抄，不改写不换算。同时列出 /input/ 下全部材料文件名（脚本会记入 materials）。

**第 2 步 落骨架**（每 item 一条待评记录）。
`python3 "$SK/scripts/benchkit.py" init --case /input/case.json --outdir /app/output`
一次性落九件最小版本：items.json（每 item 一张八字段题卡：item_id/task/input_ref/conditioning/
reference_answer/scoring_rule/difficulty/source_text_snapshot）、run_results.json（每 item 一条空记录）、
scores.csv（表头+每 item 一行）、failure_samples.json、version.json（v1+item 级 sha 快照）、diff.json、
report.md 占位、gain_evidence.json 占位、efficiency.json 占位、result.json 骨架（契约全键，status=
partial）。case.json 损坏或结构未知时脚本自动降级仍产出全套文件并写兜底题卡，此时人工核对题卡后继续。

**第 3 步 题卡定稿 + 统一作答**。逐题定稿：task 可判定（输出与评分规则一一对应）；**scoring_rule
必须机械可观察**——写出 0/1/2 判定线，每档落到可核对现象（"2=含数值 84.3% 且条件 1C/200 cycles 完整、
可回溯 p02"），写不出可观察判定线时改写为证据列举式（"来源 p02 数值 84.3% 原样出现"），仍不行移入备注
不硬造；reference_answer 与 source_text_snapshot 逐字一致；无参考答案填『仅规则评分』；difficulty 如实。
逐题作答：读 source_text_snapshot 原文真实推导答案，**不得凭领域标签编造**。把答案写入
run_results.json 对应条目：answer_raw（全文）、answer_struct（结构化要点）、evidence（每条 {quote:
原文片段, location: 段落/表格定位}）。改过题卡的题运行 `diff --outdir /app/output`（递增快照，标记
rescore_only 只重算受影响题目与 comparable 历史分数仍可比）与 `techcheck --outdir /app/output`
（确定性检查：答案非空、数值逐字覆盖、条件词覆盖、参考答案术语覆盖，给出 score_suggest 供复核，
记录 check_sha 供复跑一致性比对）。

**第 4 步 评分与失败归因 + 逐题报告**。按 0/1/2 判分线逐题评分写 scores.csv，每行必带 rationale
（判分依据：引评分规则判定线+原文定位）；score_suggest 与人工判分不一致时以评分规则为准并在 rationale
写明原因；只需重算 diff 标出的 rescore_only 题目。disputed=true 标存疑。典型失败写
failure_samples.json：`{item_id, answer_raw_excerpt, failure_type, why}`，failure_type 归到 8 类题型
（no_answer/text_mismatch/missing_condition/overclaim/format_error/file_unreadable/permission_denied/
disputed），作为下一版专项题来源。然后机械生成报告：`report --outdir /app/output`。

**第 5 步 增益对照 + 效率计数 + 嵌入自检（先修复再交付）**。
依次运行 `gain` → `efficiency` → `embed` → `verify --case /input/case.json`（子命令均带
`--outdir /app/output`）。
- **gain**：同一批作答（run_results 全文）分别用「严格评分器」与「基础（无工具）判分」各跑一遍——
  严格臂可见题卡 conditioning/reference_answer/来源快照并强制证据定位与编造/越界守卫（6 项检查），
  基础臂只可见 task 与答案表面。两臂输入完全相同、刻度相同，差异即判分口径增益。产出
  gain_evidence.json：逐题两臂分数与缺陷类型、一致率、漏检数（基础臂漏检/严格臂漏检）、耗时(ms/us)、
  步骤数，以及机制→指标映射、边界与失效条件。**数字必须本次运行真跑出来，不得手写编造。**
- **efficiency**：从台账自动统计工具调用数/判分轮次/返工轮次；模型请求数由平台记录或人工登记
  （`--model-requests N`），脚本不猜测，未登记为 null。
- **embed**：把题卡全量、run_results 全文、逐题分数（含 answer_raw_excerpt）、失败样例、版本快照、
  report.md 全文（result.report_md）、闸门状态（result.gates 九域四态）、verify 逐条校验三元组
  （result.verify_checks）、题面对齐索引（answers 答案/evidence_index 证据定位/run_status 运行状态/
  adjudication 裁定）、gain_evidence、efficiency、materials、summary 机械嵌入 result.json 的
  result 字段——评分器不开附件即可核对全部产物。
- **verify**：校验题卡字段齐、评分规则可观察、scores 与 items 无漏分多分、score∈{0,1,2} 且每行有
  rationale、每 item 有原始输出（空输出须有失败样例）、item_shas 一致、report.md 存在且已嵌入、
  gates 状态合法、result 契约键齐、answers/run_status 覆盖每一题且状态枚举合法、gain_evidence
  完整（per_item+机制映射+边界+失效条件+metrics）、efficiency 计数齐、claims 结构齐；并把三元组、
  gates 与 verdict 回写 result.json。verdict=FAIL 时逐条修复后重跑直到 PASS（**退出码恒 0**）。
- **手工补 claims 与 uncertainties**（embed 不覆盖已有内容）：claims 每条
  `{"claim_id":"c-1","text":"评测结论","kind":"reported|inferred","source_id":"<item_id 或材料
  文件名>","location":"scores.csv 行 N / run_results.results[M]","evidence":[{"quote":"原文片段",
  "location":"段落/表格定位"}]}`；关键结论（哪类题弱、哪个分数可疑、哪个评分规则不可观察、增益来自
  哪条机制）必须有 claim，不编造分数。uncertainties 分 unreported（无参考答案题）/unverifiable
  （需人工复核语义分）/conflicts（材料冲突）/human_review（disputed 项）/summary（缺口与降级记录）。

## result.json schema（键以 case.json/task.md 的 output_contract 为准，一个不缺）

```
{case_id, status, result:{items[], run_results[], scores[], failures[], version{}, materials[],
 diff{}, report_md, gates{九域}, verify_checks[{item,template_value,applied,match}],
 verdict{verdict,problems[],checked_at}, answers[{item_id,task,answer_raw,answer_struct,evidence[],
 score,failure_type}], evidence_index[{item_id,quote,location}],
 run_status[{item_id,status:success|partial|undetermined|refused,reason}],
 adjudication[{item_id,round1_score,round2_score,disputed,final_score,rationale,resolution,
 basis_location,rule_revision}], uncertainty_index[{item_id,kind,note}],
 gain_evidence{design,per_item[],metrics,mechanism_to_metric[],boundaries[],failure_conditions[]},
 efficiency{model_requests,tool_calls,judging_rounds,rework_rounds,counting_rule,reproduce},
 summary{items_total,items_with_reference,items_rule_only,items_with_conditioning,score_dist{0,1,2},
 avg,note}}, claims[{claim_id,text,kind,source_id,location,evidence[{quote,location}]}],
 uncertainties{unreported[],unverifiable[],conflicts[],human_review[],summary}}
```
契约多出的键照抄生成并填 unknown 或空数组。字段语义：`answers`=阅读/解析结果，`evidence_index`=证据
与边界（定位逐条），`run_status`=运行状态（成功/部分完成/无法判断/拒答+原因）——对应题面输出要求表
三类；`adjudication`=逐题结构化裁定；`verdict`=机械校验结论。`gates` 九域：items/run_results/scores/
failure_samples/version/diff/report/gain_evidence/efficiency，只允许 enforced（文件存在可解析非占位，
该步真实跑完）/ skipped_not_provided（组织方未提供）/ not_found（没跑或产物缺失，没跑≠通过）/
unreadable（存在但损坏，带原因）四值，非 enforced 必带 gate_note 写明「下游不得宣称已核对」。

## 判分线与分歧裁定

- **2**=正确且条件完整：主结论与参考答案/评分规则一致，conditioning 条件全部体现，关键结论可回溯
  source_text 定位。rationale 必须写明判分依据。
- **1**=部分正确：主结论方向对，但缺条件、缺定位或缺边界说明。rationale 写明缺什么。
- **0**=错误或未回答：与来源矛盾、编造未报告数据、把推断当事实、或空答。
- **双评裁定**：两人（或两次独立判分）按评分规则独立判 → 分歧按证据（原文定位）裁定 → 分歧超过
  一档时**修订评分规则而不是修改分数**，修订史记入 version.changes；分歧集中在哪条判据写进
  report.md 分歧裁定节。逐题结构化裁定写 result.result.adjudication（round1/round2/final_score/
  resolution/basis_location/rule_revision）。

## 异常处置

| 情形 | 处置 |
|-|-|
| 题目缺参考答案 | reference_answer 填『仅规则评分』，按 scoring_rule 判分，写入 uncertainties.human_review |
| 判分口径无法观察化 | 改写为证据列举式判定（"来源 p02 数值 84.3% 原样出现且条件 1C 完整"）；仍不行移入备注，不硬造 |
| 输出为空 | score=0，failure_type=no_answer 并留失败样例，评分行不删 |
| 输出超长 | run_results.json 存全文；result 嵌 answer_raw_excerpt（首 300+尾 100 字），不丢分 |
| JSON 格式不合规 | 修复到可解析；修不好则 status=input_error 并写明问题字段，保留全部已产出键 |
| 文件损坏/读失败 | 跳过该项记 failure_type=file_unreadable，其余照常，绝不中断交付 |
| 权限不足 | status=partial，原因写入 uncertainties.unreported，不编造替代数据 |
| case.json 结构未知 | 脚本写兜底题卡；人工核对后继续，降级记录写入 uncertainties.summary |
| 双评分歧超一档 | 修订评分规则而非改分；修订史入 version.changes，分歧判据写进报告 |
| verify 报 FAIL / 预算触顶 | verdict 照实记 FAIL 并逐条修复后重跑；退出码恒 0，不得中断交付；预算触顶按协议第 5 条停止新增，用现有中间结果收尾 |

## 最小调用示例（示意，非正式案例、非正式答案）

examples/example-case.json 为合成四条工单（电池循环数据，仅示意接口，不冒充正式结果）：
`init --case examples/example-case.json --outdir /tmp/bench` → （第 3-4 步人工定稿题卡、作答写入
run_results.json、逐题评分写 scores.csv，示意见 README.md）→ `diff` → `techcheck` → `report` →
`gain` → `efficiency` → `embed` → `verify --case examples/example-case.json`（每条命令均带
`--outdir /tmp/bench`）。产出九件 + result.json。脚本任何一步失败自动写 warn.log 降级，按 schema
手写 JSON 继续，流程不中断；所有命令退出码恒 0。

## 已知限制

- score_suggest/techcheck 是确定性建议（子串/token/数值覆盖），不是 DSH 分数也不是独立语义验证；
  语义 0/1/2 依赖评分规则质量，存疑标 disputed 交人工复核。
- gain 的两条臂都是确定性规则：严格臂不做语义理解，可能漏判「方向对但表述含糊」；基础臂是
  「无工具判分」的下界模拟，不是某个真实平台 Agent 的实测水平。
- 来源是段落/表格文本，不是 PDF 像素金标；不含 PDF 解析与像素级金标比对。
- 评测包不替代平台白板对照；跨 Agent 对照由平台固定白板负责，本包保证同输入同流程可复跑、分数可
  溯源；重复运行稳定性以 check_sha 记录差异。不改写来源数据，Public16scoring 与原始科学来源字节
  保持不变。
