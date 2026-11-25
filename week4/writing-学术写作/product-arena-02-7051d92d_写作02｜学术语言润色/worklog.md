# worklog

- 接到第02题任务，完整读取 task.md，确认交付口径为润色后完整文本加逐句修改说明，运行契约输入为 /input/case.json，产物写入 /app/output/ 含 result.json，预算 64 次请求 900 秒。
- 设计决策一：采用分句级最小编辑而非整段重写，编辑优先级为硬错误、术语一致性、语域、简洁化、直译腔，保证改得对与没改坏两条底线可核查。
- 设计决策二：建立四档限定强度守恒表（谨慎推测、倾向判断、有据断言、强断言），每个被修改句子前后档位必须一致，跨档仅允许硬错误例外且强制人工确认，对应创新点限定强度守恒检查。
- 设计决策三：术语表驱动的全篇一致性回扫作为独立步骤，术语表在长文分段间作为共享状态，缩写首现展开规则写入模板，对应创新点术语一致性回扫。
- 设计决策四：第 6 步加入回读校验通道，做段落结构比对与数字、引用编号、图表指向三集合比对，任何一项不通过回退或转人工确认，防止改写后语义漂移与偷偷改数据。
- 创建 submission/SKILL.md：英文 description frontmatter，中文正文含用途、适用条件、触发判断、输入约定、六步工作流程、输出约定、异常处理表（超长、编码、公式混杂、引用疑错、术语冲突、文体不明、混排、预算不足、空输入）、十项自检清单；流程按 8 次请求内设计，满足 64 次预算。
- 创建 submission/resources/glossary-template.md：术语表 Markdown 表结构、建立规则六条、JSON 导出格式供回扫程序化比对，含双语对齐要求。
- 创建 submission/resources/style-rules.md：通用红线加期刊论文、学位论文、基金申请书、审稿回复、英文摘要五个语域规则组，文体不明默认期刊论文体。
- 创建 submission/resources/revision-log-template.md：逐句修改表八字段（编号、位置、原文、改文、类型、理由、风险、人工确认），受控类型词表九种，附统计块格式与复核判读标准。
- 创建 submission/resources/result-template.json：result.json 字段模板，含 case_id、status、polished_text、revision_log、glossary、evidence 事实来源映射、manual_review_items、uncertainty、stats，并注明 output_contract 优先。
- 创建 submission/resources/semantic-preservation-checklist.md：四档守恒表加规则、六项语义不变量、中译英语义陷阱对照表、回读校验四步程序。
- 创建 submission/README.md：目录结构、适用场景、平台与人工两种调用方式、流程概要、输出解释、最小调用示例（明确标注示意输出非正式案例结果）、自查方法、限制与维护信息。
- 资源文件均控制在 500KB 内且为 UTF-8 文本，总计 7 个文件加 worklog 共 8 个，远低于 50 文件与 2MB 限制。
- 复核全部交付物与 task.md 交付要求逐项对照：SKILL.md、配套资源、README、worklog 四类齐备。

- 根据首轮评分反馈（评语：refine for a more complete and rigorous solution；未找到完整真实推导的解）修订 SKILL.md：在 frontmatter 后新增「强制执行协议」节，明确第0步先落盘 result.json 骨架、output_contract 字段缺数据不省略、广度优先、预算阈值（48次请求/700秒）强制收尾、最终写盘自检、失败也交付六条硬性纪律。
