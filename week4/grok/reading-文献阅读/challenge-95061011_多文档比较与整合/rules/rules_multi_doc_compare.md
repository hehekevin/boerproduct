# DOMAIN RULES — 多文档比较与整合 (kind=multi_doc_compare)

## Focus
- 对得齐: fields unified to one definition so cell-by-cell comparison is meaningful.
- 填得准: each cell from its labelled paper; units/dataset/metric口径 recorded with value.
- 说得清: consistency/conflict explained by sample/method/condition/metric with checkable source.
- 查得回: every value & difference conclusion traceable.

## Rules
1. Define common fields (object/data/method/condition/metric/conclusion/limit); extract per doc with value rules.
2. Normalize dataset version/sample/split/baseline/metric; decide comparable vs comparable-subset.
3. Build matrix cells with source_document_id+paragraph_id+units; run compare.py for coverage/comparability/conflicts.
4. Explain conflicts with attribution + per-cell sources; never hide disagreement.

## Self-check
- [ ] common fields unified
- [ ] cells sourced (doc+paragraph+units)
- [ ] comparability tested; conflicts explained
- [ ] traceable matrix + result.json
- [ ] can't-judge not written as fact; gaps flagged; result.json honest
