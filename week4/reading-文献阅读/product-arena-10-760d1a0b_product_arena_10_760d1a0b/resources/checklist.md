# 交付前自检清单

逐项核对，全部通过才允许把 status 写为 success；无法通过的项写入 limitations 并调整为 partial。

## A. 实体正确性

- [ ] 每个实体都有至少一条证据（paragraph_id 加原文短引），无凭常识补全的实体。
- [ ] 实体类型全部在 types.md 体系内，other 均有 note。
- [ ] 归属标注（self_reported / cited_other / unclear）与证据句一致。
- [ ] 篇内别名合并均基于缩写定义、变体或回指，合并依据已记录。
- [ ] 基因、蛋白等官方符号未改变大小写或写法。

## B. 关系正确性

- [ ] 每条三元组的 subject 与 object 均引用登记表中存在的 entity_id。
- [ ] 每条三元组有 source_id、paragraph_id、原文短引，quote 为直接摘录且不超过 60 字。
- [ ] 方向与 types.md 谓词定义一致，抽查全部 uses、outperforms、part_of 方向。
- [ ] 否定句未生成肯定边；比较句方向从优到劣；条件性结论带 condition。
- [ ] 无纯共现边；转述边 confidence 不高于 medium 且 attribution=cited_other。

## C. 跨篇处置

- [ ] 每条边只属于一个 source_id，无跨篇融合三元组。
- [ ] 跨篇合并均有显式依据；通用术语同名未合并。
- [ ] 冲突均登记在 conflicts，矛盾结论未合成一条。
- [ ] 第二篇未套用第一篇的 DOI、title、authors。

## D. 查询与输出

- [ ] 至少 3 个查询真实执行，结果附证据；无结果时如实返回空。
- [ ] nodes.csv 与 edges.csv 与 triples.json 同源一致。
- [ ] result.json 含 case_id 和 output_contract 要求的全部字段。
- [ ] status 诚实：partial / failed 均有 status_reason 与可人工接管位置。
- [ ] unreported 与 limitations 已填写（如材料无 PDF 页码的说明）。
- [ ] change_record 记录了主要步骤与增量变更。

## E. 定位合规

- [ ] 全部定位使用组织方段落 ID，无自造 PDF 页码。
- [ ] quote 未改写公式与上下标的线性化形式。
