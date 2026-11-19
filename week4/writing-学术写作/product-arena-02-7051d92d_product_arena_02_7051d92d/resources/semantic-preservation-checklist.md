# 语义保持核查清单（含限定强度守恒表）

用途：第 3 步逐句编辑时对照执行，第 6 步回读校验时逐项复核。目标是润色后每个句子仍表达作者原本的主张，不加强也不削弱。

## 限定强度等级表（hedging 守恒）

| 档位 | 强度 | 典型标记词 |
| --- | --- | --- |
| 1 | 谨慎推测 | may, might, could, possibly, perhaps, cannot rule out |
| 2 | 倾向判断 | suggest(s), indicate(s) 弱用, appear(s) to, tend(s) to, likely, be speculated that |
| 3 | 有据断言 | show(s), demonstrate(s), confirm(s), is/are associated with, provide(s) evidence that |
| 4 | 强断言 | prove(s)（限数学）, establish(es), ensure(s), unambiguously, will（承诺语境除外） |

守恒规则：

1. 修改前后句子档位必须相同。同档换词允许：may 与 might 互换；suggest 与 appear to 互换。
2. 跨档替换禁止。唯一例外：不改就存在语法硬错误且作者原意可由上下文确证时允许跨档，此时 risk 置 medium，manual_review 置是，理由写明原档位与新档位。
3. 强度相同的否定也要守恒：not impossible 不等于 possible；fails to show 强于 does not show，降档需人工确认。
4. will 在基金申请书与审稿回复中是承诺语境，不按第 4 档处理。

## 六项语义不变量（每个被修改句子逐项过）

1. 限定强度：档位不变（见上表）。
2. 否定范围：not、no、neither、only 的辖域不移位。原句 few studies have examined 不改成 many studies have failed to examine。
3. 条件与因果：if、unless、provided that 保留条件关系；causes 与 is associated with 不互换；leads to 与 correlates with 不互换。
4. 量词：all、some、most、few、none、at least、up to 原样保留。
5. 数据与指向：数字、单位、有效位、百分比、区间、引用编号（[n]）、图表指向（Figure n、Table n、Eq. n、Section n）逐字符保留。原文疑似有误不改，记人工确认。
6. 信息增删：不新增原文没有的事实、例证、文献；不删除原文的让步、限定、例外说明。

## 中译英语义陷阱对照

| 中式表达 | 陷阱 | 安全处理 |
| --- | --- | --- |
| 证明了 | 强度升级为第 4 档 | 按原文证据用 demonstrate 或 show（第 3 档） |
| 在一定程度上 | 常被整句删除 | 译为 to some extent 保留，档位第 2 |
| 如果，那么 | 条件被改写成并列 | 保留 if then 结构 |
| 表明 | 误升级为 proves | suggest 或 indicate（第 2 档） |
| 显著提高 | 显著被当作 very | 统计显著译 significantly 保留原数字检验依据；非统计语境用 markedly 并保持原模糊度 |

## 回读校验程序（第 6 步执行）

1. 集合比对：提取原文与润色文的数字串、引用编号、图表指向三个集合，三者必须完全相等。
2. 档位比对：对每个被修改句标注前后档位，全部一致方可通过。
3. 结构比对：段落数、章节数、句子数差异应能被修改说明表完全解释。
4. 任何一项不通过：回退该处修改或转为人工确认项，不得带病输出。
