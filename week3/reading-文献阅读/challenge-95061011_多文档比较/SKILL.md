---
name: doc-compare-r5
description: 多文档比较与整合技能（r5：题面对齐 + 同输入增益取证版）。读 /input/comparison-workorder.json 与全部语料文档，建统一字段字典，逐格抽取绑定 source_document_id+paragraph_id+逐字 quote；pairwise 两两比较矩阵（每对文档×每维度一条，verdict≠not_judged 必附双方逐字引文）；冲突登记带 attribution_dimension 枚举；六维可比性检验先行、不池化不同口径；数字逐字回证；result.json 嵌入 matrix/pairwise/comparability/synthesis/coverage/verification(三元组)/gates(四态)/gain_evidence(同输入三遍对照实测)/efficiency(效率计数)/sources/status_reason；gain_probe 跑 full 与两种退化模式（--ablate 关闭两两比对或冲突归因）产出逐项对照数字、机制→指标映射、边界与失效条件。Use when the task asks to compare and integrate multiple papers into a common-field comparison matrix with per-cell dual-document provenance, pairwise dimension verdicts, conflict attribution, verifiable gain evidence, and machine-checkable verification records.
---

## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 8 条是硬性纪律，优先级高于本文档其余内容；冲突时以本节为准。

1. **第0步先落盘骨架**：读完 /input/case.json 与题面后，第一个写盘动作就是在 /app/output/result.json 写入骨架：case_id 取自 case.json；键名严格按 case.json 或 task.md output_contract 声明的每个字段生成（无法完成的填 unknown 或空数组，绝不省略键）；status 填 "partial"，status_reason 写明为何。
2. **每步一个写盘动作**：五步流程每完成一步，立即把该步产物写进 result.json 并覆盖为当前最新完整状态（长文本分批写，每段 ≤1500 字，写完即回填，防 16384 token 截断）。任何时刻 /app/output/result.json 必须存在且 JSON 可解析。
3. **字段一个不缺**：最终 result.json 顶层须有 case_id/status/status_reason/result/claims/uncertainties/sources/changelog，result 内须有 field_dictionary/matrix/pairwise/comparability/synthesis/coverage/verification/gates/gain_evidence/efficiency。确实无法产出时保留键并填 unknown/[]/说明字符串，原因写入 uncertainties，不删键不编造。
4. **广度优先**：先让全部要求的产物以最小合格版本存在，再对高价值部分加深。
5. **预算熔断**：模型请求已用超过 44 次或运行超过 640 秒，立即停止新增处理，用现有中间结果完成 result.json 并收尾（增益取证与效率计数优先于新增比较维度）。
6. **写盘前自检**：JSON 可解析、契约字段一个不缺、case_id 一致、status 如实（全完成=answered，有缺口=partial，证据不足=insufficient_evidence，输入异常=input_error）。
7. **失败也要交付**：中断或失败时仍写 result.json（status 如实降级，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。
8. **校验失败不中断**：所有校验脚本失败路径 exit 0，判定写入 check_report.json 的 ok/verdict/problems；按 problems 逐条修复后重跑，不得因校验未过而拒绝交付。

## 输入与输出契约

- 输入：/input/case.json（output_contract + case_id）、/input/comparison-workorder.json（fields[]、documents[]、比较维度）、全部语料文档、task.md。以实际文件为准。
- 工作区 /app/work；产物 /app/output/result.json（含契约全键 + case_id）。
- 预算：64 次模型请求 / 900 秒 / 单响应 16384 token。依赖 Python 3 标准库。

## 五步流程

### 第1步：抄契约，落骨架
1. 读 /input/case.json，抄 output_contract 全部键名与 case_id。2. 读 /input/comparison-workorder.json，提取 documents[]、fields[]、comparison_dimensions[]。3. 读 task.md、`ls /input/`，确认语料全集与任务要求。
4. 写 result.json 骨架：case_id + 顶层 8 键（含 status_reason、sources=[]、uncertainties 六个分区、changelog[]）+ result 内预留全部 11 块，status="partial"。

### 第2步：字段字典对齐（1 次响应）
按七组（对象/数据/方法/条件/指标/结论/局限）为每个 field_id 写 definition / group / unit_expectation / 取值规则 / aliases；各文档自己的叫法登记进 aliases，不做含义偷换。写入 result.field_dictionary。

### 第3步：逐格抽取 matrix（1-2 次响应）
- 逐文档 × 逐字段抽取，每格填 value、units、context（数据集/样本量/指标口径）、cell_status、evidence。
- cell_status：reported（原文有值）/ not_reported（原文没有）/ not_comparable（有值但口径不符——保留原值 + incomparable_reason，不是删掉）。
- evidence 必含 source_document_id + paragraph_id + 逐字 quote（≤40 字，空白归一化后子串可核验）；**数字格的 value 必须逐字出现在 quote 里**，否则修正或标 unbacked。units、数据集版本、样本量、指标口径随值记录。
- 每篇文档在 result.sources 登记一行 {source_document_id, title, read_status, evidence_scheme, note}，read_status 如实写 read_ok/partial/failed。

### 第4步：两两比较矩阵 + 可比性 + 冲突登记（1-2 次响应）
1. **pairwise（核心产出）**：每对文档 × 每个比较维度（默认六维 task/metric/units/material/pollutant/budget，工单另有维度并入）一条记录 `{pair:[A,B], dimension, verdict: same|partial|different|not_judged, note, evidence:[{source_document_id:A, paragraph_id, quote 逐字}, {source_document_id:B, paragraph_id, quote 逐字}]}`。verdict≠not_judged 时 evidence 必须同时含双方引文；not_judged 必须在 note 写明原因。
2. **可比性检验**：六维逐一给结论，划 comparable_subset；pooled 恒为 false，不同数据集/染料/口径绝不合并进定量综合。
3. **冲突登记**：每条 `{what, docs, attribution, attribution_dimension: sample|method|metric|condition|object|scope|unattributable, quotes:[双方引文≥2条且来自不同文档]}`；无法归因填 unattributable 并记入 human_review。
4. 未报告与不可比格全部保留，原因写入 uncertainties。
5. 可选加速：跑 `python3 /skills/weekly-skill/scripts/compare_matrix.py --result /app/output/result.json --workorder /input/comparison-workorder.json --out /app/work/pairwise.json`，用其 pairwise/conflicts 作草稿再由你按原文语义修正。

### 第5步：增益取证 + 效率计数 + 校验 + 收尾
1. **增益取证（同输入对照）**：跑 `python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json --workorder /input/comparison-workorder.json --embed`。该脚本对同一份已交付产物跑三遍——full（正常）、ablate_no_pairwise（关闭两两比对）、ablate_no_attribution（关闭冲突归因）——产出 result.gain_evidence：同输入指纹（matrix_sha256 相同）、六项逐项对照指标（维度覆盖数/一致判定率/冲突发现数/需人工核对条目数/步骤数/追问轮次）、deltas、mechanism_map（机制→指标映射）、boundary、failure_conditions、verdict。**不要手写这些数字**：全部由脚本机械复算；gain_evidence.problems 非空即如实登记。
2. **效率计数**：跑 `python3 /skills/weekly-skill/scripts/efficiency_probe.py --result /app/output/result.json --workorder /input/comparison-workorder.json --embed`，得 result.efficiency（复算计数 counts + 你自报的 model_requests/tool_calls/rework_rounds 存 agent_reported 分区，含采集口径与复现方式）。
3. **校验**：跑 `python3 /skills/weekly-skill/scripts/check_result.py --result /app/output/result.json --workorder /input/comparison-workorder.json --case /input/case.json --out /app/output/check_report.json --embed`；按 report.problems 逐条修复后重跑（退出码恒 0，看 report.verdict）。
4. 把校验结果逐条嵌入 result.verification：`{item, template_value, applied:true|false, match:true|false}`——不许只写"已核对"。把闸门状态嵌入 result.gates：`{gate, state: enforced|skipped_not_provided|not_found|unreadable, gate_note}`。必查闸门：workorder 读取、语料文档读取、compare_matrix 运行、gain_probe 运行、check_result 运行、coverage 一致性。没跑 ≠ 通过；未运行必须 state≠enforced 且 gate_note 写明「下游不得宣称已核对」。
5. 回填 coverage：cells/reported/not_reported/not_comparable/pairwise_records/conflicts/claims 数量（与实际数组长度一致，校验器机检）。数字回证：全部 reported 数字格的 value 已出现在对应 quote 中；查不出的逐条列入 uncertainties.unbacked 并如实降级。
6. 每条跨文档结论对应一条 claims 记录 `{claim_id, text, kind: reported|inferred, source_id, location, evidence:[{source_document_id, paragraph_id, quote}]}`；跨文档 claim 的 evidence 需含 ≥2 条不同文档引文。
7. 最终自检（协议第 6 条）后交付。

## 输出 schema（result.json）

顶层 8 键：case_id / status / status_reason / result / claims / uncertainties / sources / changelog。result 内 11 块（键名不可改）：

```json
{"case_id":"取自 case.json","status":"answered|partial|insufficient_evidence|input_error","status_reason":"必填",
 "result":{
  "field_dictionary":[{"field_id":"…","definition":"…","group":"对象|数据|方法|条件|指标|结论|局限","unit_expectation":"…","aliases":{"论文内叫法":"标准字段"}}],
  "matrix":[{"field_id":"…","source_document_id":"…","value":null,"units":"…","context":"…","cell_status":"reported|not_reported|not_comparable","evidence":{"source_document_id":"…","paragraph_id":"…","quote":"逐字原文"},"incomparable_reason":null}],
  "pairwise":[{"pair":["A","B"],"dimension":"metric","verdict":"same|partial|different|not_judged","note":"…","evidence":[{"source_document_id":"…","paragraph_id":"…","quote":"…"},{"source_document_id":"…","paragraph_id":"…","quote":"…"}]}],
  "comparability":{"task":"…","metric":"…","units":"…","material":"…","pollutant":"…","budget":"…","comparable_subset":[],"pooled":false},
  "synthesis":{"consistent":[],"partial":[],"conflicts":[{"what":"…","docs":["A@p03","B@p12"],"attribution":"…","attribution_dimension":"…","quotes":[双方引文]}]},
  "coverage":{"cells":0,"reported":0,"not_reported":0,"not_comparable":0,"pairwise_records":0,"conflicts":0,"claims":0},
  "verification":[{"item":"coverage_cells","template_value":10,"applied":true,"match":true}],
  "gates":[{"gate":"workorder_read","state":"enforced","gate_note":""}],
  "gain_evidence":{"input_fingerprint":{"matrix_sha256":"…","same_input_across_runs":true,"unique_variable":"…"},"runs":[{"mode":"full|ablate_no_pairwise|ablate_no_attribution","metrics":{"dimension_coverage":0,"agreement_rate":0,"conflicts_found":0,"manual_review_items":0,"steps":0,"followup_rounds":0}}],"deltas":{"ablate_no_pairwise":{…}},"mechanism_map":[{"mechanism":"…","metric":"…","mapping_rule":"…","full_value":0,"ablate_value":0,"delta":0,"direction":"full_better"}],"boundary":["…"],"failure_conditions":["…"],"verdict":"gain_demonstrated","problems":[],"reproduce":"…"},
  "efficiency":{"collection_method":"…","reproduce":"…","counts":{"matrix_cells":0,"pairwise_records":0,"comparison_rounds":0,"conflict_records":0,"manual_review_items":0,"human_review_items":0,"followup_rounds":0,"steps":0},"agent_reported":{"model_requests":null,"tool_calls":null,"rework_rounds":null}}},
 "claims":[{"claim_id":"…","text":"…","kind":"reported|inferred","source_id":"…","location":"…","evidence":[…]}],
 "uncertainties":{"unreported":[],"unverifiable":[],"unbacked":[],"conflicts":[],"human_review":[],"summary":"…"},
 "sources":[{"source_document_id":"…","title":"…","read_status":"read_ok","evidence_scheme":"paragraph_id=pNN","note":"…"}],
 "changelog":[]}
```

## 校验器会抓的错（check_result.py，全部 = FAIL）

1. 顶层契约键缺任一 / status 不在四级枚举 / status_reason 为空 / sources 为空或缺 read_status。
2. uncertainties 缺六个分区（unreported/unverifiable/unbacked/conflicts/human_review/summary）。
3. 工单文档 × 字段全格覆盖（漏格）；reported 格缺 evidence；not_comparable 缺 incomparable_reason。
4. pairwise verdict 非法；verdict≠not_judged 但 evidence<2 条或两方同文档；not_judged 缺 note。
5. conflicts 引文<2 条或全同一文档；缺 attribution；pooled=true 但 comparable_subset<2 篇；跨文档 claim 引文<2 条。
6. **数字回证：reported 数字格 value 未出现在 quote（空白归一化）→ 逐条列 unbacked**。
7. coverage 数值与实际数组长度不符；gates 缺失/state 非法/非 enforced 缺 gate_note；verification 缺条目缺键/applied=false/match=false。
8. **gain_evidence 缺失/遍数<2/缺 full 遍/缺退化遍/指纹非同输入/缺逐项 delta/缺机制映射/缺边界/缺失效条件/缺 verdict/缺 reproduce**。
9. **efficiency 缺失/缺采集口径/缺复现方式/缺计数项；gain_evidence 与 efficiency 的 followup_rounds 不一致**。

## 异常处置

| 异常 | 处置 |
|------|------|
| PDF 解析失败 | 记 uncertainties.unverifiable；用可用文本继续；相关格标 not_reported；sources.read_status=partial |
| 图表无法读取 | 格标 not_reported，context 注明"图表不可读" |
| 主题不相关 | status=insufficient_evidence，写明原因 |
| 同一论文多版本 | 取最新版，旧版差异记入 uncertainties |
| 矛盾无法归因 | conflicts 保留双方引文，attribution_dimension="unattributable"，记 human_review |
| 语料缺段落编号 | 按章节标题定位，paragraph_id 注 "section:xxx"，粒度下降如实记录 |
| 工单字段与语料不匹配 | 保留全部工单字段，缺值格标 not_reported，原因记 uncertainties |
| 仅 1 篇文档 | pairwise 置空并在 uncertainties.summary 说明单文档不构成比较，status=partial；gain_evidence.problems 登记"槽位为0，比对类指标不可测" |
| 增益对照不可测 | matrix 为空或工单缺失 → gain_evidence.problems 如实登记，比对类指标按 0 记并在 uncertainties 说明，不伪造 |
| 效率计数缺失 | efficiency.counts 仍由脚本复算输出，agent_reported 留空并在 collection_method 说明 |

## 最小示例（示意，非正式答案）

场景：2 篇合成论文（DOC-A: MOF 吸附甲基蓝；DOC-B: 活性炭吸附甲基蓝）。完整见 resources/example-result.json，仅说明接口：
- matrix 格：`{field_id:"max_adsorption_capacity","DOC-A",value:312.5,units:"mg/g","reported",quote:"312.5 mg/g"}`
- pairwise：`{pair:["DOC-A","DOC-B"],dimension:"material",verdict:"different",evidence:[双方引文]}`
- gain_evidence：runs 三遍（full + 两个 ablate），deltas 逐项对照，mechanism_map 写机制→指标
- efficiency：counts 复算 + agent_reported 自报分区
- gates：`{"gate":"check_result_run","state":"enforced","gate_note":""}`

## 已知限制

- 依赖语料段落编号；无编号时按章节定位，溯源粒度下降。指标同名不同义靠字段字典+可比性检验拦截，语义误判风险存在，冲突格建议人工复核。PDF 扫描件需 OCR，识别错误可能影响 quote 逐字性。
- 增益对照是「同一份已交付产物的机制消融投影」，不是第二次模型推理，因此不含推理随机性；平台层面的「不加载 Skill vs 加载 Skill」对照由平台执行，本 Skill 不替代该对照。followup_rounds 为按缺口结构复算的投影值，与 Agent 自报实测值分区存放、不可混用。
- 5-10 篇规模稳定运行（pairwise = 对数×维度数，10 篇×6 维=270 条，预算内）；>15 篇按维度分批。
