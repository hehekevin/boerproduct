---
name: acbench
description: 学术写作 Benchmark 与评测工具技能：把写作评测工单建成可判分、可复跑、可溯源、可迭代的最小评测包——可观察必需要点题卡、参考答案（变体与不可接受错误分开）、0/1/2 逐题评分（每行判分依据）、失败样例归因、item 级版本快照与定向重算、双评分歧裁定记录、机械生成的逐题报告、同输入双评分器增益对照（含机制消融与效率计数）。评测包全量嵌入 result.json（含 report 全文、verify 校验报告、gain_evidence、efficiency、output_contract_map），每个分数顺 item_id 可追到原稿全文与评分行。score_suggest 不是语义终判。Use when asked to design/run/score/version/audit a writing benchmark (task set, reference answers, scoring anchors, annotation consistency, reproducible runs, per-item report), 建题集, 评分锚点, 评测报告, benchmark workorder.
---
# acbench — 写作评测包工具（要点可观察 · 分数可复算 · 逐题报告 · 增益可证）

把 /input/case.json 的写作评测工单建成**最小评测包**，七件全部落盘且全量嵌入
result.json（评分器不开附件即可逐项核对）：items.json（写作题卡）→ run_results.json
（原稿全文+技术检查）→ scores.csv（0/1/2+判分依据）→ failure_samples.json（失败样例）
→ version.json（item 级快照）→ report.md（逐题报告）→ result.json（题卡+原稿+评分+
失败+快照+diff+报告全文+verify 报告+gain_evidence+efficiency+output_contract_map 全量嵌入 + claims）。
闭环：题能判定=题卡 must_points/reject/verdict_rule；答案站得住=reference_answer+
variants（风格差异与实质错误分开）；锚点打得齐=must_points 全部可观察化；跑得可复现
=version 快照+check_sha+固定输入重跑；报告说得清=逐题得分/证据/失败类型/改进建议。
诚实边界：score_suggest 只是确定性建议，不是语义终判，语义 0/1/2 由 verdict_rule 判定
并分开记录；无参考答案的题如实标『仅规则评分』；不编造分数、数据或平台未提供的对照结果；
题面要求 Office 产物时用 python-docx 生成，无渲染能力不伪造预览，写入 uncertainties。
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
1. 先抄契约：读完 /input/case.json 与题面后，把 output_contract 的**每个键名**原样抄成
   清单（任意层级出现即算；contract 为键名列表时逐个抄），并抄下 case_id 与题面要求
   （体裁/受众/字数/引用要求）。键一个不漏，抄完再动手。
2. 立即落骨架：第一个写盘动作就是 init 写出 /app/output/result.json——契约全部键+
   case_id/status/result/claims/uncertainties；无法完成的字段填 unknown/空数组，绝不
   省略键；status 填 partial；此后 result.json 必须始终存在且 JSON 可解析。
3. 字段一个不缺：无法产出的项保留键填 unknown/空数组，原因写进 uncertainties，不得
   删键、不得编造数据。
4. 每步一个写盘动作：每个流程步骤（抄契约/落骨架/定稿题卡/撰写稿件/评分/裁定/报告）
   都对应一次实际写盘（init/techcheck/diff/report/gain/embed 或手工写 run_results.json/
   scores.csv/adjudication.json），不得把多步攒在内存里最后一次性落盘。
5. 广度优先：先让题卡、原稿、评分、报告四类产物全部以最小合格版本存在，再加深高价值
   部分；禁止在单一产物上耗尽预算。
6. 预算熔断：模型请求已用超过 48 次或运行超过 700 秒时（平台预算 64 请求/900 秒），
   立即停止新增处理，用现有中间结果完成 result.json 并收尾；每次写都覆盖为最新完整状态。
7. 失败也要交付：处理中断或失败时仍写 result.json（写明中断位置与已完成部分），绝不
   让 /app/output 缺少 result.json。
写盘前自检：JSON 可解析、契约键一个不缺、case_id 与输入一致、status 如实、每个关键
论断有 claims 证据。自检不过先修复再交付。

## 调用脚本
脚本位于本文件同目录 `scripts/`（记为 `$SK/scripts/`）：`acbench.py`（主工具，七命令
init/techcheck/diff/report/gain/embed/verify）与 `gain_eval.py`（增益对照引擎，可被
他人独立复用于自己的学科题集）。找不到时用
`find / -name acbench.py -path '*scripts*' 2>/dev/null | head -1` 定位。脚本缺失或
报错时按本文档 schema 手写等价 JSON 继续，流程不中断，降级写入 uncertainties.summary。
所有命令异常自动降级（warn.log+**退出码恒 0**）；case.json 损坏/结构未知时写兜底题卡，
绝不产出空题集。**校验失败必须如实记录（verify FAIL + problems），但退出码恒 0，
不得因校验未过而中断交付。**

## 六步流程
1. **抄契约**：读 /input/case.json 与题面，抄下 output_contract 全键与 case_id；工单
   条目逐条抄成清单（task/materials/must_points/variants/reject/verdict_rule/
   reference_answer），数值与格式约束逐字照抄；列出 /input/ 全部材料文件名。
2. **落骨架**：`python3 "$SK/scripts/acbench.py" init --case /input/case.json --outdir /app/output`
   一次落七件最小版本（题卡/空 run_records/评分表/失败样例/version 快照/报告占位/
   result.json 骨架）。case.json 损坏或结构未知时自动降级仍产全套文件并写兜底题卡。
3. **题卡定稿+撰写**：must_points 全部可观察化（"保留数值 12.3±1.1 原样"而非"数据
   充分"）；否定式要点写成可机械核验形式（"不引入表外数值"，而不是"数据准确"）；
   reject 写清实质错误（把触发词加引号，如"出现'证明'等因果结论词"），variants 写清
   允许风格差异；reference_answer 至少一份可接受写法。读 materials 真实撰写稿件，不得
   凭领域标签编造；稿件写入 run_results.json 对应条目：draft_md 全文、draft_struct、
   evidence（每条 {quote: 材料原文片段≤40字逐字, location: 段落/图表定位}）。改过题卡
   则运行 diff（递增快照，标记 rescore_only 需重算与 comparable 历史分数可比）与
   techcheck（确定性检查+score_suggest+check_sha）。
4. **评分+分歧裁定+报告**：按 verdict_rule 逐题评分写 scores.csv（2=must_points 全满足
   且忠实材料；0=命中 reject/实质错误/未作答；其余=1），每行必带 rationale（引题卡要点
   +材料定位）；score_suggest 与判分不一致时以 verdict_rule 为准并在 rationale 写明。
   双评逐题写 adjudication.json，格式
   `{"rounds":[{"item_id":"","judge_a":2,"judge_b":1,"delta":1,"adjudicated":1,
   "anchor_revision":"","evidence":"材料定位"}]}`：分歧按证据裁定；分歧超一档时修订锚点
   而不是修改分数，修订史记入 version.changes；disputed=true 的题必须有裁定记录，否则
   verify FAIL。典型失败写 failure_samples.json（8 类：no_answer/missing_must_point/
   overclaim/format_error/text_mismatch/file_unreadable/permission_denied/disputed）。
   然后 `python3 "$SK/scripts/acbench.py" report --outdir /app/output` 机械生成逐题报告。
5. **增益对照**（本题天然可做，真实数字）：`python3 "$SK/scripts/acbench.py" gain --outdir
   /app/output --case /input/case.json`。对**同一批作答**跑两个评分器：完整评分器
   （要点覆盖+reject 红线+证据逐字回证+分歧裁定）vs 基础判分（只对照要点覆盖率），
   另做三组机制消融（去 reject/去回证/去裁定），产出逐项分数、一致率、漏检数、误判数、
   与人工判分的一致率、耗时、步骤数、机制→指标映射与边界，写入 gain_evidence.json
   并嵌入 result.json。**数字必须由脚本实跑产生，不得手填**；跑不出就如实留空并写明。
6. **嵌入+自检收尾**：先手工补 claims（每条 claim_id/text/kind/source_id/location/
   evidence[{quote≤40字逐字,location}]，关键结论必带 claim，不编造分数）与 uncertainties
   （unreported/unverifiable/conflicts/human_review/summary）。然后
   `python3 "$SK/scripts/acbench.py" embed --outdir /app/output`（题卡/原稿全文/逐题分数/
   失败样例/快照/diff/**report.md 全文**/adjudication/materials/gain_evidence/efficiency/
   output_contract_map 机械嵌入）→
   `python3 "$SK/scripts/acbench.py" verify --outdir /app/output --case /input/case.json`。
   verify 逐域机械校验并给出 gate 状态显式枚举（enforced/enforced_with_findings/
   skipped_not_provided/not_found/unreadable）——没跑≠通过，skipped/not_found 必须修复
   或如实写入 uncertainties。校验域（12 域）：items、run_results、scores（漏分多分/分值域/
   rationale）、failures（原稿配平）、version（item_shas 一致）、adjudication（disputed
   须有裁定）、report 存在、embed（嵌入字段齐/数量一致/report_md 非空）、evidence_backing
   （claims 与原稿 evidence 的 quote 空白归一化后在 case.json 语料中逐字命中；已判合格
   的题引文不可回证=硬问题，已判不合格的题=软发现并须写进失败样例与判分理由）、
   gain_evidence（有真实对照数字+机制映射+边界）、efficiency（效率计数+复现说明）、
   contract_map（题面输出要求表→字段语义映射齐备）。**verify 报告自动回写嵌入
   result.json 的 result.verify**；FAIL 逐条修复后重跑直到 PASS，**退出码始终为 0**。

## result.json schema（键以 case.json/task.md 的 output_contract 为准，一个不缺）
```json
{
  "case_id": "取自 case.json",
  "status": "answered | partial | insufficient_evidence | input_error",
  "result": {"items": [{"item_id":"","task":"","genre":"","input_ref":"","materials":[],
              "must_points":["可观察现象"],"variants":[],"reject":[],"verdict_rule":"",
              "reference_answer":"原值或 仅规则评分","scoring_rule":"","difficulty":"","extra":{}}],
    "run_results": [{"item_id":"","draft_md":"","draft_struct":{},"evidence":[{"quote":"","location":""}],"technical_check":{}}],
    "scores": [{"item_id":"","score":0,"rationale":"","disputed":false,"failure_type":"","draft_excerpt":""}],
    "failures": [{"item_id":"","answer_raw_excerpt":"","failure_type":"","why":""}],
    "version": {"snapshot":"v1","items_sha":"","item_shas":{},"changes":[],"comparable_with":[]},
    "materials": [{"file":"","bytes":0}],
    "diff": {"changed":[],"added":[],"removed":[],"rescore_only":[],"comparable":[]},
    "adjudication": {"rounds":[{"item_id":"","judge_a":0,"judge_b":0,"delta":0,"adjudicated":0,"anchor_revision":"","evidence":""}]},
    "report_md": "report.md 全文",
    "verify": {"ok":true,"gate_state":{},"problems":[],"findings":[]},
    "gain_evidence": {"metrics":{"agreement_rate":0.0,"missed_detections":0,"false_downgrades":0,
                    "vs_human_semantic_scores":{"basic":{"agreement_rate":0.0},"full":{"agreement_rate":0.0}}},
                    "scorers":{"basic_points_only":{},"full":{}},"ablation":{},"mechanism_to_metric":[],"boundaries":[]},
    "efficiency": {"tool_steps":0,"tool_step_sequence":[],"tool_elapsed_ms_total":0,
                   "manual_steps_estimated":0,"reproduce":{"commands":[],"runtime":"","deps":"","determinism":"","fingerprint":{}}},
    "output_contract_map": {"题集":{},"评分":{},"失败样例":{},"报告":{},"裁定":{},"分歧":{},
                   "目标产物":{},"事实与来源映射":{},"版本与边界":{},"增益证据":{}},
    "summary": {"items_total":0,"items_with_reference":0,"items_rule_only":0,"must_points_total":0,
                "score_dist":{"0":0,"1":0,"2":0},"avg":null,
                "note":"score_suggest 不是语义终判；复算路径：scores 行→题卡→原稿全文"}},
  "claims": [{"claim_id":"","text":"","kind":"reported|inferred","source_id":"","location":"","evidence":[{"quote":"","location":""}]}],
  "uncertainties": {"unreported":[],"unverifiable":[],"conflicts":[],"human_review":[],"summary":""}
}
```
契约多出的键照抄生成并填 unknown 或空数组。0/1/2 判分线：2=达标（must_points 全满足、
事实/数值/术语与材料一致、reject 未命中、体裁格式符合，rationale 写明依据与定位）；
1=部分达标（方向对但缺要点/缺定位/格式偏差/变体处理不当）；0=不达标（命中 reject、事实与材料矛盾、编造未报告数据、论断强度升级、空稿）。

## 异常处置
| 情形 | 处置 |
|---|---|
| 题目缺参考答案 | reference_answer 填『仅规则评分』，按 verdict_rule 判分，写入 uncertainties.human_review |
| 必需要点无法观察化 | 改写为证据列举式判定（"材料 M03 数值 12.3 原样出现"）；仍不行移入备注，不硬造锚点 |
| 稿件为空 | score=0，failure_type=no_answer 并留失败样例，评分行不删 |
| 稿件超长 | run_results.json 存全文；result 嵌入 draft_excerpt（首 300 字+尾 100 字），不丢分 |
| JSON 格式不合规 | 修复到可解析；修不好则 status=input_error 并写明问题字段，保留全部已产出键 |
| 文件损坏/读失败 | gate=unreadable，跳过该项记 failure_type=file_unreadable，其余照常，绝不中断交付 |
| 权限不足 | status=partial，原因写入 uncertainties.unreported，不编造替代数据 |
| case.json 结构未知 | 脚本写兜底题卡；人工核对后继续，降级记录写入 uncertainties.summary |
| 双评分歧超一档 | 修订锚点而非改分；修订史入 version.changes，分歧判据写进报告 |
| 增益对照跑不出 | gain_evidence 记 {ok:false,status:"unavailable"} 并写明原因；不得手填数字，不得宣称已验证 |
| 预算触顶 | 按协议第 6 条：停止新增，用现有中间结果完成 result.json 收尾 |

## 最小调用示例（示意，非正式案例、非正式答案）
examples/example-case.json 为合成五条写作工单（果蝇嗅觉记忆数据，仅示意接口）；
examples/demo-fixture.json 为配套合成演示稿（含刻意缺陷，用于复现全链路与增益对照）。
```bash
python3 "$SK/scripts/acbench.py" init --case examples/example-case.json --outdir /tmp/bench
# 第 3-4 步：定稿题卡、稿件写入 run_results.json、评分写 scores.csv、双评写 adjudication.json（示意见 README.md）
python3 "$SK/scripts/acbench.py" diff --outdir /tmp/bench && python3 "$SK/scripts/acbench.py" techcheck --outdir /tmp/bench
python3 "$SK/scripts/acbench.py" report --outdir /tmp/bench
python3 "$SK/scripts/acbench.py" gain --outdir /tmp/bench --case examples/example-case.json
python3 "$SK/scripts/acbench.py" embed --outdir /tmp/bench
python3 "$SK/scripts/acbench.py" verify --outdir /tmp/bench --case examples/example-case.json
# → 产出七件 + adjudication.json + gain_evidence.json + result.json（全量嵌入含报告全文、增益证据、效率计数）
# 退化对照：python3 "$SK/scripts/acbench.py" gain --outdir /tmp/bench --case examples/example-case.json --degrade
```

## 已知限制
- score_suggest/techcheck 是确定性建议，不是语义终判；语义 0/1/2 依赖 verdict_rule
  质量，存疑标 disputed 交人工复核。
- evidence 回证是对 case.json 语料的子串匹配；/input 独立文件需手工核对后补入 case 引用，
  无法回证的 quote 如实列入 verify 报告 findings（已判合格=硬问题，已判不合格=软发现）。
- 增益对照只证明"同一评分器内部不同机制配置"的差异，**不等于**平台白板的人工对照结果；
  基础判分档只是"人工手写要点对照评分表"的机械下界，不代表人工水平。
- 评测包不替代平台白板对照；不改写来源数据，原文与数值逐字保持不变；单轮流程，重复
  运行稳定性以 check_sha 记录差异，不自动聚合多次运行。
