# 三元组输出规范

## 1. 三元组 schema（triples.json 中每条记录）

```json
{
  "triple_id": "P1-T001",
  "subject": {"entity_id": "P1-E01", "name": "规范化名称", "type": "method"},
  "predicate": "uses",
  "object": {"entity_id": "P1-E02", "name": "规范化名称", "type": "dataset"},
  "direction": "subject_to_object",
  "condition": "适用条件，来自原文；无则空串",
  "stance": "affirmed",
  "confidence": "high",
  "evidence": {
    "source_id": "P1",
    "paragraph_id": "p12",
    "quote": "不超过60字的原文短引"
  },
  "attribution": "self_reported",
  "note": "推断理由或空串"
}
```

字段规则：

| 字段 | 必填 | 规则 |
| - | - | - |
| triple_id | 是 | {source_id}-T{三位序号}，论文内唯一；跨篇按 source_id 区分 |
| subject / object | 是 | 必须引用 entity-registry 中已存在的 entity_id；name 与 type 取规范化值 |
| predicate | 是 | 必须来自 types.md 第 2 节 |
| direction | 是 | 固定 subject_to_object；方向语义由谓词定义锁定 |
| condition | 是 | 原文有限定语必须原样保留；无则空串，不得编造条件 |
| stance | 是 | affirmed / negated / conditional / speculative |
| confidence | 是 | high / medium / low，判据见 types.md 第 3 节 |
| evidence | 是 | source_id、paragraph_id、quote 三项缺一不可；没有证据的三元组不许存在 |
| attribution | 是 | self_reported / cited_other / unclear |
| note | 否 | 放推断理由、存疑说明 |

## 2. 证据定位强制回填规则

- quote 必须是原文连续片段的直接摘录（允许截断，不允许改写、翻译或重排公式符号）。
- paragraph_id 使用材料自带的组织方段落 ID；材料无段落 ID 时用可回查的章节标题加段内序号，并在 result.json 的 limitations 中说明定位方式。
- 禁止生成 PDF 页码。本流程不掌握真实页码，任何页码字段都是编造。
- 一条三元组对应一条主证据；若多个段落共同支撑，evidence 用数组，按重要性排序。

## 3. 实体 schema（entity-registry 与 nodes.csv 源）

```json
{
  "entity_id": "P1-E01",
  "mention": "首次出现的原文表面形式",
  "normalized_name": "规范化名称",
  "type": "method",
  "aliases": ["其他原文写法"],
  "source_id": "P1",
  "evidence": [{"paragraph_id": "p3", "quote": "短引"}],
  "attribution": "self_reported",
  "note": ""
}
```

## 4. 建边禁忌清单

1. 纯共现不建边：两实体同段出现但句子无关系语义，不建边。
2. 综述转述降级：转述他人工作建边时 confidence 最高 medium，attribution=cited_other。
3. 条件不丢失：原文的条件性结论（在 X 条件下优于）不得抽成无条件事实。
4. 否定不反转：原文说"不优于"时，不得抽出 outperforms（正向）边；按 stance=negated 记录。
5. 跨篇不融合：两篇论文的条件、样本、数值结果不得合成一条三元组；每条边只属于一个 source_id。
6. 常识不补全：原文未提及的关系，即使领域常识上显然成立，也不建边。

## 5. CSV 导出格式

edges.csv 表头：triple_id,subject_id,subject_name,predicate,object_id,object_name,direction,condition,stance,confidence,source_id,paragraph_id,quote,attribution,note

nodes.csv 表头：entity_id,normalized_name,type,source_id,aliases,attribution,evidence_paragraph_ids,note

多值字段（aliases、evidence_paragraph_ids）用分号分隔；字段内含逗号时按 CSV 规则加双引号。
