# 论断抽取规范

本规范覆盖两个阶段：阶段一抽取候选论断，阶段二逐条核对原文并绑定证据。核心原则：**断言忠实原文，不夸大，不编造；证据最小充分，定位强制**。

## 1. 论断粒度判据（拆得细）

一条合格断言满足全部条件：

1. **单一主张**：只有一个可判断真假的命题。复合句按下列规则拆分：
   - 并列结构（A and B 两个独立事实）：拆成两条断言。
   - 因果结构（A 导致 B）：拆成两条，即“A 导致 B”一条，若原文分别陈述“A 出现”与“B 随之变化”则再拆。
   - 条件从句（Under X condition, Y happens）：保留为一条断言，条件作为限定词并入断言文本，不得丢掉。
   - 转折结构（A but B）：拆成两条，方向各自保留。
2. **保留量词与限定词**：all / some / most / significantly / only / in vivo / in mice 等逐字保留。
3. **保留否定与方向**：not / did not / inhibited / prevented；increase 与 decrease 的主客体方向不得颠倒。
4. **数值与单位逐字保留**：含精度（p = 0.03）、区间（10 to 20 mg）、近似（approximately 3-fold）。
5. **不推断原文没有的内容**：断言不得引入原文未出现的实体、机制或数值。

反例与正例（同一段原文：“Treatment with drug X significantly reduced tumor volume in mice (p = 0.01), and increased survival by 40%”）：

- 错误：一条断言塞两句（复合塞入）。
- 正确断言 1：“Treatment with drug X significantly reduced tumor volume in mice (p = 0.01)”。
- 正确断言 2：“Treatment with drug X increased survival by 40% in mice”。
- 错误改写：“Drug X shrinks tumors”（丢了 significantly、in mice、数值；shrinks 与 reduced 措辞漂移）。

## 2. Hedging 标记词表（论断强度闸门）

扫描原文句子，命中即触发强度判定：

| 类别 | 标记 | 强度判定 |
|-|-|-|
| 概然标记 | may, might, could, can, possibly, perhaps, likely, unlikely | suggestive |
| 提示性动词 | suggest, indicate, appear, seem, imply, point to | suggestive |
| 近似与约量 | approximately, about, roughly, around, nearly, tend to | suggestive（数值类另在断言中保留约量词） |
| 条件限定 | under ... condition, in the presence of, when, upon, in (mice/cells/patients), at ... dose | conditional（限定范围并入断言文本） |
| 相关性措辞 | correlate, associate, linked with, correspond | correlational（不得升格为因果） |
| 明确陈述 | 无上述标记且为直接陈述（showed, demonstrated, was, reduced 等） | definitive |

规则：

1. 断言文本必须保留与原文同强度的 hedging 词；`may increase` 不得写 `increase`，`associated with` 不得写 `causes`。
2. `assertion_strength` 字段按上表填写；命中多类时取最低强度（最保守）。
3. `hedging_markers` 逐个记录命中的词。
4. correlational 断言的谓词用关联类关系词，不得映射为因果类关系词。

## 3. 受控关系词表（谓词映射）

核心三元组谓词从下列词表选择；都不合适时允许 `npex:hasCustomRelation` 之外新建 `npex:rel_{slug}`，但必须在 result.json 的 `relation_map` 字段记录原文措辞到关系词的映射理由。

| 关系词 | 对应原文措辞 | 类别 |
|-|-|-|
| npex:increases | increases, elevates, upregulates, promotes | 方向 |
| npex:decreases | decreases, reduces, downregulates, lowers, inhibits(量) | 方向 |
| npex:associatedWith | associated with, correlated with, linked with | 关联 |
| npex:causes | causes, drives, leads to, results in（仅 definitive 因果） | 因果 |
| npex:treats | treats, ameliorates, improves (disease/phenotype) | 应用 |
| npex:expresses | expresses, is expressed in | 表达 |
| npex:locatedIn | located in, accumulates in | 定位 |
| npex:measuredAs | p = ..., N = ..., percentage of ... | 数值报告 |
| npex:reportsMethod | used, performed, measured by | 方法 |

方向性与主体规则：

1. 谓词方向以原文语法主语为 subject：原文 “B is increased by A” 映射为 `A increases B` 时，方向以原文动词原意为准，主体转换需在 label 中保留原句式。
2. 主体混淆检查：断言的 subject 必须是原文动作的发出者；比较句（X vs Y）确认谁高谁低。

## 4. 证据绑定与定位（对得上、追得回）

每条断言绑定：

1. `evidence_quote`：最小充分证据片段，逐字引用（可跨句但去掉无关内容），不超过 300 字符；保留原标点与大小写；省略处用 `[...]` 标注。
2. `evidence_location` 四字段全必填：
   - `page`：正文页码优先，`page_basis` 声明 `paper` 或 `pdf`；
   - `section`：章节号或章节名（如 `3.2 Results` 或 `Discussion`）；
   - `paragraph`：所在章节内段序（从 1 计数）；
   - `sentence`：段内句序（从 1 计数）。
3. `evidence_type`：direct（该片段单独直接支撑）或 inferred（需综合多处信息；此时 `inference_note` 必填，写明用哪些片段经何推理得到）。
4. 最小充分性判据：把该片段单独拿出来，不懂全文的人也能核对断言真假；若不能，扩到相邻句或标注 inferred。
5. 引文与断言冲突时以原文为准回改断言；矛盾表述整体记入 uncertainties，不输出。

## 5. 候选清单字段（阶段一产出，candidates.json）

```json
{
  "case_id": "{case_id}",
  "candidates": [
    {
      "id": "NP001",
      "candidate_text": "原文措辞的断言文本",
      "source_span": {"section": "", "paragraph": 1, "sentence": 1},
      "hedging_markers": [],
      "numeric_items": [],
      "notes": "拆分依据或疑问"
    }
  ]
}
```

## 6. 核对记录字段（阶段二产出，verified.json）

```json
{
  "case_id": "{case_id}",
  "assertions": [
    {
      "id": "NP001",
      "statement": "核对后的断言文本",
      "subject": "", "predicate": "npex:increases", "object": "",
      "qualifiers": ["in mice", "at 10 mg"],
      "assertion_strength": "definitive",
      "hedging_markers": ["none"],
      "evidence_quote": "",
      "evidence_location": {"page": "", "page_basis": "paper", "section": "", "paragraph": 1, "sentence": 1, "figure": ""},
      "evidence_type": "direct",
      "inference_note": "",
      "verification": "pass | degraded | dropped",
      "drop_reason": ""
    }
  ]
}
```

`verification` 取值：pass（进入 RDF）；degraded（降级输出，如证据只能 inferred、定位缺页码）；dropped（删除，写明原因，进 result.json 的 unreported）。
