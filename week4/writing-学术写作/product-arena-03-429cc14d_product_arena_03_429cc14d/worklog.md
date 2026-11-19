# worklog

- 2026-11-11 12:13 完整读取题目文件 task.md 与 challenge.json，确认评分维度（实际效果40/使用增益25/创新增益15/可靠体验10/生态贡献10）、Harbor 运行契约（64 次请求、900 秒、16384 tokens、/app/output + result.json 含 case_id 与 output_contract 字段）与资源限制（50 文件、单文件 500KB、总量 2MB）。
- 2026-11-11 创建 submission/ 目录与 references/ 子目录。
- 2026-11-11 设计决策：以引用-条目双向映射矩阵为 Skill 核心产物，而非逐条凭印象核对，对应创新增益"正文与列表双向同步、论断级引用匹配"。
- 2026-11-11 设计决策：流程固定为 6 阶段（0 读契约、1 抽取、2 去重、3 双向校验、4 元数据分级、5 格式化、6 写出自检），预估 8 到 14 次请求，远低于 64 次预算，保证三个案例都能稳定跑完；中间状态集中在 audit_state.md，避免重复读大文件。
- 2026-11-11 写入 SKILL.md：frontmatter name=citation-consistency-audit，description 英文（是什么/何时用/如何触发），正文中文，含用途、适用条件、调用方式、六阶段流程、输入输出约定、8 条异常要点、8 项自检清单。
- 2026-11-11 设计决策：元数据核验采用保守策略，只做 DOI 格式校验与材料内交叉核对，verified 仅允许 verified_by_material/verified_by_doi_lookup/unverified 三值，杜绝无证据的"已核实"声明，保证可靠体验与诚实标注。
- 2026-11-11 写入 references/workflow-checklists.md：五阶段核查清单加 16 类异常分支详表（E1 到 E16）加终局自检清单。
- 2026-11-11 写入 references/format-mapping.md：BibTeX/RIS/CNKI/EndNote 字段对照表，GB/T 7714-2015、APA 7、BibTeX 三种目标格式的输出模板与字段规则，6 条转换陷阱。
- 2026-11-11 写入 references/dedup-rules.md：J1 到 J7 合并判据分级、5 类禁止合并条款、逐字段择优规则、去重对账公式。
- 2026-11-11 写入 references/result-json-template.md：默认 result.json 模板（case_id、status 三值、counts 对账、三清单、去重记录、元数据分级、人工确认清单、change_records、sources 三层锚点、uncertainty、limits、self_check），并规定运行时以 case.json 的 output_contract 为准补充字段。
- 2026-11-11 写入 references/common-errors.md：25 条常见错误（抽取/一致性/去重/元数据/格式化/交付六类）与预防方法。
- 2026-11-11 写入 README.md：功能概览、文件清单、调用步骤、最小调用示例（显式标注示意输出非正式案例结果）、适用范围与限制、失败处理与自查方法。
- 2026-11-11 设计决策：README 示例使用编造的 demo-case-001 数据并两次声明为示意，符合交付要求"不冒充正式案例结果"。
- 2026-11-11 待办：自检文件大小与格式合规（无 emoji、无破折号、frontmatter 合法），通过后向 team-lead 汇报。

- 根据首轮评分反馈（评语：refine for a more complete and rigorous solution；未找到完整真实推导的解）修订 SKILL.md：在 frontmatter 后新增「强制执行协议」节，明确第0步先落盘 result.json 骨架、output_contract 字段缺数据不省略、广度优先、预算阈值（48次请求/700秒）强制收尾、最终写盘自检、失败也交付六条硬性纪律。
