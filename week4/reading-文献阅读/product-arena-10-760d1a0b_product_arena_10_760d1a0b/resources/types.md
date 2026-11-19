# 实体与关系类型体系（默认版本，可配置扩展）

本文件是类型体系的唯一事实源。抽取时类型必须从本表选择；体系外的对象归入 other 并在 note 写明真实类别。替换学科时只改本文件的表内容，流程与 schema 不变。

## 1. 实体类型

| type | 定义 | 典型例子 | 判定要点 |
| - | - | - | - |
| method | 论文中使用、提出或改进的方法、模型、算法、技术路线 | 某训练框架、某网络结构、某算法 | 必须是论文实际讨论的对象，不是背景常识概念 |
| dataset | 数据集、语料库、基准测试集 | 某公开基准、自建语料 | 区分"提及"与"实际使用"，使用关系在边中表达 |
| material | 材料、样品、试剂、设备、实验系统 | 某合金样品、某试剂盒、某仪器 | 同名材料在不同论文中默认不代表同一物理样品 |
| task | 任务、研究问题、应用场景 | 某预测任务、某分割任务 | 任务与 method 不混用 |
| metric | 评价指标、统计量 | 准确率、AUC、某误差指标 | 指标的具体数值属于 result，不属于 metric |
| result | 结论、发现、数值结果 | "方法 X 在数据集 D 上达到 m" | 必须带条件（数据集、设置），抽入 condition 字段 |
| disease | 疾病、表型、临床状态 | 某疾病、某综合征 | 医学案例常用 |
| gene | 基因、蛋白、靶点、变异 | 某基因、某蛋白、某突变 | 保留原文写法（含大小写），规范化时不得改变官方符号 |
| researcher | 研究者、团队、机构 | 第一作者、某实验室 | 仅当原文以研究者为关系主体或对象时抽取 |
| other | 体系外对象 | 任意 | note 必须写明真实类别，禁止强行套用近似类型 |

## 2. 关系类型（谓词）与方向规则

每条谓词有固定方向，direction 一律为 subject 指向 object；写反即为错误。建边前按本表核对方向。

| predicate | 语义 | 方向规则 | 合法示例 | 反例（禁止） |
| - | - | - | - | - |
| uses | 使用、采用 | 使用者 指向 被用物 | 方法A uses 数据集D | 数据集D uses 方法A |
| compares | 比较 | 比较主体 指向 被比较对象（比较基准写入 condition） | 论文/方法A compares 方法B | 反向 |
| improves | 改进、扩展 | 改进者 指向 被改进物（通常是新方法指向旧方法） | 方法A improves 方法B | 反向 |
| outperforms | 优于 | 优者 指向 劣者，条件写入 condition | 方法A outperforms 方法B | 比较句读反方向 |
| achieves | 达到 | 方法/系统 指向 metric 或 result | 方法A achieves 指标M | 指标M achieves 方法A |
| supports | 支持 | 证据 指向 被支持的结论 | 实验E supports 结论C | 反向 |
| contradicts | 矛盾 | 证据/结论 指向 被矛盾的对象 | 结果A contradicts 结果B | 反向 |
| part_of | 组成 | 部分 指向 整体 | 模块B part_of 系统A | 整体指向部分 |
| evaluates | 评估 | 评估主体 指向 被评估对象 | 数据集D evaluates 方法A | 反向 |
| derived_from | 来源于 | 产物 指向 来源 | 指标M derived_from 数据集D | 反向 |
| related_to | 关联（兜底） | 语义弱关联 | 任意 | 兜底谓词必须有原文依据句，禁止用于纯共现 |

方向判定口诀：找证据句的语法主语和宾语。主语侧实体做 subject，宾语侧实体做 object；被动句先还原主动语态再定向。

## 3. 限定字段约定

- condition：适用条件必须来自原文（如"仅在数据集 D 上""样本量 n 时"），无条件的结论不得凭空加条件，原文无条件则留空。
- stance：affirmed（肯定）、negated（否定，原文明确说不成立）、conditional（条件性陈述）、speculative（原文自述为推测）。
- confidence：high（原文明确陈述的直接证据句）、medium（同段或紧邻段落可显式推导、缩写定义处）、low（跨段推断、综述转述、拿不准）。confidence 与 stance 独立：否定句若原文明确，同样是 high。
- 归属标注（实体级）：self_reported（作者自述）、cited_other（转述他人工作）、unclear。

## 4. 配置扩展方法

跨学科复用时：复制本文件为 types-custom.md，保留表结构，替换类型行；新增谓词必须给出语义、方向规则、合法示例、反例四项，缺一不可。新增实体类型时同步在 triple-spec.md 的 schema 枚举中登记。
