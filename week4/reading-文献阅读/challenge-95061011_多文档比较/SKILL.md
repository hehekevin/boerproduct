---
name: doc-compare-r3
description: 多文档比较与整合技能（r3 覆盖密度增强版）。读 /input/comparison-workorder.json 与全部语料文档，建统一字段字典，逐格抽取绑定 source_document_id+paragraph_id；核心新增 pairwise 两两比较矩阵——每对文档 × 每个比较维度一条结构化记录，verdict 判定必须同时附双方逐字引文（每格可回溯到两份原文）；冲突登记带归因维度标签；六维可比性检验先行，不池化不同口径；未报告/不可比格显式保留。Use when the task asks to compare and integrate multiple papers into a common-field comparison matrix with per-cell dual-document provenance, pairwise dimension verdicts, and conflict attribution.
---

## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 6 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

1. 第0步先落盘骨架：读完 /input/case.json 与题面后，第一个写盘动作就是在
   /app/output/result.json 写入骨架：case_id 取自 case.json；键名严格按 case.json
   或 task.md 中 output_contract 声明的每个字段生成（当前无法完成的字段值填
   unknown 或空数组，绝不省略键）；status 填 "partial"。此后任何时刻
   /app/output/result.json 必须存在且 JSON 可解析。
2. 字段一个不缺：最终 result.json 必须包含 output_contract 的全部键。某项确实
   无法产出时，保留键并填 unknown、空数组或说明字符串，同时把原因写入
   uncertainties，不得删除键、不得编造数据。
3. 广度优先：先让全部要求的产物以最小合格版本存在，再对高价值部分加深。
   禁止在单一产物上耗尽预算。
4. 预算保护：模型请求已用超过 48 次或运行时间超过 700 秒时，立即停止新增处理，
   用现有中间结果完成 result.json 并收尾。每次写 result.json 都覆盖为当前最新
   完整状态。
5. 最终写盘前自检：JSON 可解析、output_contract 字段一个不缺、case_id 与输入
   一致、status 如实。自检不过先修复再交付。
6. 失败也要交付：处理中断或失败时，仍写 result.json（status 如实降级，
   写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

## 输入与输出契约

- 输入：/input/case.json（output_contract + case_id）、/input/comparison-workorder.json
  （fields[]、documents[]、比较维度）、全部语料文档、task.md。以实际文件为准。
- 工作区：/app/work；产物：/app/output/result.json（含 output_contract 全部键 + case_id）。
- 预算：64 次模型请求 / 900 秒 / 单响应 16384 token。
- 依赖：Python 3（标准库即可，无第三方包）。

## 五步流程

### 第1步：抄契约，落骨架
1. 读 /input/case.json，提取 output_contract 全部键名与 case_id，抄入清单。
2. 读 /input/comparison-workorder.json，提取 documents[] 与 fields[]。
3. 读 task.md、`ls /input/`，确认语料文件全集与任务要求。
4. 立即写 /app/output/result.json 骨架：case_id + output_contract 每键（值填
   unknown / [] / {}）+ status="partial" + result 内预留 matrix:[]、pairwise:[]、
   comparability:{}、synthesis:{}、coverage:{}。

### 第2步：字段字典对齐（1 次响应）
1. 按七组（对象、数据、方法、条件、指标、结论、局限）为每个 field_id 写
   definition / group / unit_expectation / 取值规则 / aliases。
2. 各文档自己的叫法（如"去除率" vs "removal efficiency"）登记进 aliases，
   映射到标准字段，不做含义偷换。
3. 产出写入 result.field_dictionary。

### 第3步：逐格抽取 matrix（1-2 次响应）
- 逐文档 × 逐字段抽取，每格填：value、units、context（数据集/样本量/指标口径）、
  cell_status、evidence。
- cell_status 枚举：reported（原文有值）/ not_reported（原文没有）/
  not_comparable（有值但口径不符——保留原值 + incomparable_reason，不是删掉）。
- evidence 必含 source_document_id + paragraph_id + 逐字 quote。
- 每格的 units、数据集版本、样本量、指标口径随值记录。

### 第4步：两两比较矩阵 + 可比性 + 冲突登记（1-2 次响应）
1. **pairwise 两两比较矩阵（本技能核心产出）**：对每对文档 × 每个比较维度
   （默认六维 task/metric/units/material/pollutant/budget，工单另有维度时并入），
   写一条结构化记录：
   `{pair:[A,B], dimension, verdict: same|partial|different|not_judged, note,
     evidence:[{source_document_id:A, paragraph_id, quote 逐字},
               {source_document_id:B, paragraph_id, quote 逐字}]}`
   - **verdict 非 not_judged 时 evidence 必须同时含双方引文**——每个比较判断
     都能回溯到两份原文；not_judged 必须在 note 写明原因。
2. **可比性检验**：六维逐一给结论，划 comparable_subset（口径一致的文档子集）；
   pooled 恒为 false，不同数据集/染料/口径绝不合并进定量综合。
3. **冲突登记**：结论一致性判 consistent / partial / conflicts。每条冲突：
   `{what, docs, attribution, attribution_dimension: sample|method|metric|condition|object|scope|unattributable, quotes:[双方引文≥2条且来自不同文档]}`。
   无法归因时 attribution_dimension 填 "unattributable" 并记入 human_review。
4. 未报告与不可比格全部保留，原因写入 uncertainties。

### 第5步：校验收尾
1. 运行：`python /skills/weekly-skill/scripts/check_result.py --result /app/output/result.json --workorder /input/comparison-workorder.json --case /input/case.json --out /app/output/check_report.json`
2. 非 0 退出码逐条修复（缺格回填、补双方引文、补 reason）后重跑。
3. 回填 coverage 统计块：cells / reported / not_reported / not_comparable /
   pairwise_records / conflicts / claims 数量。
4. 自检：JSON 可解析；键一个不缺；case_id 一致；status 如实
   （全完成=answered，有缺口=partial，证据不足=insufficient_evidence，输入异常=input_error）。
5. 每条跨文档结论（synthesis 与关键 pairwise 判定）对应一条 claims 记录：
   `{claim_id, text, kind: reported|inferred, source_id, location,
     evidence:[{source_document_id, paragraph_id, quote}]}`；
   跨文档 claim 的 evidence 需含 ≥2 条不同文档的引文。

## 输出 schema（result.json）

```json
{
  "case_id": "取自 case.json",
  "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "field_dictionary": [
      {"field_id":"…","definition":"…","group":"对象|数据|方法|条件|指标|结论|局限",
       "unit_expectation":"…","aliases":{"论文内叫法":"标准字段"}}
    ],
    "matrix": [
      {"field_id":"…","source_document_id":"…","value":null,"units":"…",
       "context":"数据集/样本量/指标口径","cell_status":"reported|not_reported|not_comparable",
       "evidence":{"source_document_id":"…","paragraph_id":"…","quote":"逐字原文"},
       "incomparable_reason":null}
    ],
    "pairwise": [
      {"pair":["DOC-A","DOC-B"],"dimension":"metric","verdict":"same|partial|different|not_judged",
       "note":"判定说明",
       "evidence":[{"source_document_id":"DOC-A","paragraph_id":"p05","quote":"…"},
                   {"source_document_id":"DOC-B","paragraph_id":"p12","quote":"…"}]}
    ],
    "comparability": {
      "task":"…","metric":"…","units":"…","material":"…","pollutant":"…","budget":"…",
      "comparable_subset":["doc1+doc2（同口径）"],"pooled":false
    },
    "synthesis": {
      "consistent":["…"],"partial":["…"],
      "conflicts":[{"what":"…","docs":["A@p03","B@p12"],
        "attribution":"归因到条件差异",
        "attribution_dimension":"sample|method|metric|condition|object|scope|unattributable",
        "quotes":[{"source_document_id":"A","paragraph_id":"p03","quote":"…"},
                   {"source_document_id":"B","paragraph_id":"p12","quote":"…"}]}]
    },
    "coverage": {"cells":0,"reported":0,"not_reported":0,"not_comparable":0,
                 "pairwise_records":0,"conflicts":0,"claims":0}
  },
  "claims": [
    {"claim_id":"…","text":"跨文档结论","kind":"reported|inferred",
     "source_id":"doc id 或 cross-doc","location":"paragraph_id",
     "evidence":[{"source_document_id":"…","paragraph_id":"…","quote":"…"}]}
  ],
  "uncertainties": {
    "unreported":[],"unverifiable":[],"conflicts":[],"human_review":[],"summary":"…"
  },
  "changelog": []
}
```

## 校验器会抓的错（check_result.py）

1. 工单文档 × 字段全覆盖（漏格=FAIL）；reported 格缺 evidence=FAIL。
2. not_comparable 格缺 incomparable_reason=FAIL。
3. **pairwise 记录 verdict≠not_judged 但 evidence 少于 2 条或两方来自同一文档=FAIL**。
4. conflicts 每条引文少于 2 条或全部来自同一文档=FAIL。
5. pooled=true 但 comparable_subset 不足 2 篇=FAIL。
6. 跨文档 claim（evidence 声明多个文档）引文少于 2 条=FAIL。

## 异常处置

| 异常 | 处置 |
|------|------|
| PDF 解析失败 | 记入 uncertainties.unverifiable；用可用文本继续；相关格标 not_reported |
| 图表无法读取 | 格标 not_reported，context 注明"图表不可读" |
| 主题不相关 | status=insufficient_evidence，写明不相关原因 |
| 同一论文多版本 | 取最新版，旧版差异记入 uncertainties |
| 矛盾无法归因 | conflicts 保留双方引文，attribution_dimension="unattributable"，记入 human_review |
| 语料缺段落编号 | 按章节标题定位，paragraph_id 注明 "section:xxx"，粒度下降如实记录 |
| 工单字段与语料不匹配 | 保留全部工单字段，缺值格标 not_reported，原因记入 uncertainties |
| 仅 1 篇文档 | pairwise 置空并在 uncertainties.summary 说明单文档不构成比较，status=partial |

## 最小示例（示意，非正式答案）

场景：2 篇合成论文（DOC-A: MOF 吸附甲基蓝；DOC-B: 活性炭吸附甲基蓝）。
示意输出节选（完整见 resources/example-result.json，**仅说明接口**）：
- matrix 格：`{field_id:"max_adsorption_capacity", source_document_id:"DOC-A", value:312.5, units:"mg/g", cell_status:"reported", evidence:{...quote:"312.5 mg/g"}}`
- pairwise：`{pair:["DOC-A","DOC-B"], dimension:"material", verdict:"different", note:"MOF vs 颗粒活性炭", evidence:[DOC-A 引文, DOC-B 引文]}`
- conflicts：`{what:"吸附量差异", attribution_dimension:"object", quotes:[双方引文]}`

## 已知限制

- 依赖语料段落编号；无编号时按章节定位，溯源粒度下降。
- 指标同名不同义靠字段字典 + 可比性检验拦截，语义误判风险存在，冲突格建议人工复核。
- PDF 扫描件需 OCR，识别错误可能影响 quote 逐字性。
- 5-10 篇规模可稳定运行（pairwise 记录数 = 对数 × 维度数，10 篇 × 6 维 = 270 条，
  属预算内）；超过 15 篇建议按维度分批或缩减字段组。
