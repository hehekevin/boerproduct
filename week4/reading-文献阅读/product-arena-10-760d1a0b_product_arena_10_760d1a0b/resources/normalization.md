# 实体规范化与消歧规则

目标：同一对象不产生重复节点，不同对象不被错误合并。所有合并必须留下可回查的依据。

## 1. 篇内合并（允许，需记录）

满足以下任一条件即可合并为同一 entity_id：

1. 缩写定义：原文出现"全称 (缩写)"或"缩写 (全称)"模式。
2. 大小写/连字符/空格变体：如 GeneX 与 genex、multi scale 与 multi-scale，且语义上下文一致。
3. 指代链：原文用代词或"该方法""上述模型"明确回指同一对象，回指句可作证据。

合并动作：保留首次出现的完整全称为 normalized_name，其余写法进 aliases；各出现位置的 paragraph_id 全部追加进 evidence。合并依据写入 merges 记录（basis 填规则编号或原文短引）。

同名不同对象（篇内）：同一写法在文中指两个不同实例（如两个同名模型变体）时，用原文限定语后缀区分（如 模型A (大版本)），不合并，并在 note 说明区分依据。

## 2. 跨篇合并门槛（从严）

两篇论文的实体默认独立。仅当满足以下任一显式依据才合并：

1. 引用声明：第二篇明确引用第一篇，并用同指语言声明是同一对象（如 "the method proposed in [1]"）。
2. 全称一致且实例特征一致：全称相同，且原文可证两者是同一实例（同版本、同来源、同参数设置），而非仅同名。

以下情形一律不合并（常见错误来源）：

- 相同通用术语：两篇都提到 transformer、MRI、深度学习等通用方法或材料词。
- 同名数据集但版本或划分不同（原文可辨时）。
- 相同材料词但物理样品、样本、实验条件不同。

## 3. 合并记录 schema（merges.json）

```json
{
  "merges": [
    {
      "canonical_id": "M01",
      "members": ["P1-E03", "P2-E05"],
      "normalized_name": "合并后名称",
      "basis": "rule-1 或原文短引",
      "evidence": {"source_id": "P2", "paragraph_id": "p4", "quote": "短引"},
      "decision_time": "S5"
    }
  ],
  "conflicts": [
    {
      "entities": ["P1-E03", "P2-E05"],
      "kind": "cross_paper_same_name | cross_paper_result_conflict | in_paper_conflict",
      "reason": "为何不合并或为何矛盾",
      "evidence": {"source_id": "P2", "paragraph_id": "p7", "quote": "短引"},
      "resolution": "保留为独立节点；两条关系均保留并各自挂 source_id"
    }
  ]
}
```

跨篇合并产生的规范节点：canonical_id 用 M{两位序号}；nodes.csv 中为该规范节点加一行，members 写入 note；两篇的原始实体行保留，不删除。

## 4. 结果冲突处置

两篇对同类对象给出矛盾结论（数值、效果方向、适用性判断不一致）时：

1. 两条三元组都保留，各自挂各自 source_id 与证据。
2. 在 conflicts 登记 kind=cross_paper_result_conflict。
3. 禁止合成一个结论，禁止挑选其中一条。

## 5. 规范化细节

- 不改官方符号：基因、蛋白、化学名等保留原文大小写与写法，仅合并纯变体。
- 不翻译：normalized_name 保持原文语言；别名表可含原文中出现的其他写法，不得自行翻译生成。
- 数字与单位：抽取数值结果时连同单位与条件一起进 condition 或 note，不单独归一化数值。
