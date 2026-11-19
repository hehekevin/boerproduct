# 自检清单（详版）

与 SKILL.md 第 8 节一致，此处给出每项判据与核查方法。输出前逐项打勾；任何一项不通过，先修正再重查，不能通过的按降级规则处理并如实标注 status。

## 1. 断言质量（对得上拆得细）

- [ ] 每条断言只有一个可判断真假的主张。核查法：把断言念一遍，问“这命题能一次判真假吗”，出现“并且/同时/以及”连接两个事实即未拆干净。
- [ ] 量词与限定词逐字一致。核查法：在原文中找到 evidence_quote，逐词比对 all/some/most/only/in mice 等修饰成分。
- [ ] 否定与方向正确。核查法：确认谓词方向（increases/decreases）与原文动词方向一致，主语是动作发出者。
- [ ] 数值与单位逐字保留。核查法：numeric_items 每一项都能在 evidence_quote 中原样找到。
- [ ] hedging 强度一致。核查法：hedging_markers 非空时，断言文本中必须出现同强度标记；assertion_strength 与词表判定一致；correlational 未写成因果谓词。
- [ ] 无编造。核查法：断言中每个实体、关系、数值都能在原文某句中找到来源。

## 2. 证据与定位（追得回）

- [ ] evidence_quote 为逐字引用且不超过 300 字符。核查法：与原文比对标点大小写；省略处有 [...]。
- [ ] 最小充分。核查法：单独读引文即可核对断言真假；不能则扩片段或标 inferred。
- [ ] evidence_location 四字段齐全且非空。核查法：page/section/paragraph/sentence 逐字段检查；缺失项触发降级。
- [ ] page_basis 全局一致。核查法：所有断言同用 paper 或 pdf。
- [ ] inferred 已标注且有 inference_note。核查法：evidence_type=inferred 的条目 inference_note 非空。

## 3. RDF 结构（读得懂）

- [ ] validate_np.py 通过（四图齐全非空、head 三元组完整、花括号配平、必需前缀已声明）。
- [ ] 每条 np 的 assertion 图只有一条主张三元组加 label 三元组。
- [ ] 谓词全部为 URI 且来自受控词表或已记录 relation_map。
- [ ] provenance 含 prov:wasDerivedFrom、evidenceQuote、evidenceLocation、pageBasis、assertionStrength、hedgingMarkers、evidenceType 七要素。
- [ ] pubinfo 含 createdBy、generatedAtTime、license、primaryTopic 四要素。
- [ ] 无空节点主体；字面量转义正确；无伪造正式 np URI。

## 4. 交付完整性

- [ ] result.json 含 case_id 且与输入一致。
- [ ] output_contract 要求的字段全部出现。
- [ ] status 诚实：degraded/dropped 存在时不得写 success。
- [ ] uncertainties、unreported、limits、change_log 字段存在（可为空数组但不可缺失）。
- [ ] assertion-source-table.md 条数与 nanopub_count 一致。
- [ ] 所有输出在 /app/output/ 下，路径与 result.json 的 outputs 字段一致。

## 5. 快速复核脚本

机械项用 scripts/validate_np.py 自动检查；语义项（1、2 类）由 Agent 在阶段二完成并在 verified.json 留 verification 标记；最终人工（或团队复核者）可用 assertion-source-table.md 对照原文逐条抽查。
