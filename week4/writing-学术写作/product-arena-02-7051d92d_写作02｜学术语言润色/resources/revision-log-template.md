# 逐句修改说明模板

用途：revision_log.md 的标准格式。每一处修改一条记录；未修改的句子不占条目。第三方应能仅凭一条记录判断这处该不该改。

## 表结构（Markdown 表）

| 编号 | 位置 | 原文 | 改文 | 修改类型 | 理由 | 风险 | 人工确认 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R001 | Introduction, para 1, sentence 2 | The experimental results prove that the proposed method is effective. | The experimental results demonstrate that the proposed method is effective. | hedge-preserving via register | prove 在非数学语境属绝对化表述，demonstrate 与原文证据强度同档，不改变结论强度 | low | 否 |
| R002 | Methods, para 3, sentence 1 | We use a deep learning model to process the datas. | We use a deep learning model to process the data. | grammar | datas 为不可数名词复数误用，属硬错误 | low | 否 |
| R003 | Experiments, para 2, sentence 4 | Our DL method is much better than other methods. | Our DL method outperforms the compared baselines on all three metrics. | register | much better 口语化；改文仅在原文确有 all three metrics 对比时成立，否则保留 much better 的模糊比较并记人工确认 | medium | 是（对比范围需作者核实） |

## 字段说明

1. 编号：R 加三位序号，全篇唯一，与 result.json 中 revision_log 条目的 id 一致。
2. 位置：章节、段、句三级定位，与 polished_text.md 中的实际位置可互相定位。
3. 原文与改文：完整句子级摘录，不做省略号截断；仅句内局部修改时也给出整句，便于回读比对。
4. 修改类型：受控词表 grammar、syntax、punctuation、spelling、terminology、consistency、register、conciseness、chinese-english。涉及限定强度档位替换的加注 hedge-preserving via 前缀说明。
5. 理由：一句话说明为什么改，涉及术语统一时引用术语表条目号，涉及语域时引用 style-rules.md 的规则组名。
6. 风险：low 表示零信息变化；medium 表示需要作者核实语境（如对比范围、指代对象）；high 不允许出现（高风险修改一律改为人工确认建议而非直接改）。
7. 人工确认：是 或 否。为是的条目同步写入 result.json 的 manual_review_items。

## 文末统计块（固定格式）

```
总句数：N
修改句数：n（占比 p%）
分类型计数：grammar a, syntax b, punctuation c, spelling d, terminology e, consistency f, register g, conciseness h, chinese-english i
未修改但建议人工确认：k 处
```

## 判读标准（给复核者）

一条合格记录应满足：不看原文上下文也能理解修改依据；改文能逐字在 polished_text.md 中找到；原文能逐字在原始输入中找到；类型标签与理由一致（标签 register 就不该写语法理由）。
