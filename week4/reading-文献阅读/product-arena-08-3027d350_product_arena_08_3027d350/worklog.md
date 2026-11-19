# worklog

- 重设计起点：原版 13 文件、A-F 多分支流程（文字层/OCR/混合三路径并行）导致重放 Agent（64 请求/900 秒）执行重、产物残缺；解析结果未完整嵌入 result.json。本轮按「线性极简、结果内嵌、确定性工作交给工具」三原则推倒重做。
- 清空 submission/ 旧版 rules/（4 个分支规则文件）与 templates/（6 个模板文件）。
- 重写 SKILL.md：frontmatter name: pdf-paper-parse，英文 description 含触发词；主流程压缩为 5 步线性（读契约抄键名 → 立即写 result.json 骨架 → 单一路径提取全文 → 按 output_contract 填充 → 自检收尾），约 150 行，命令式祈使句，无 A-F 分支。
- 关键设计 1（抗残缺）：第 2 步强制先写 result.json 骨架（全键 + case_id + status=partial），每完成一块即回填，中途失败也有可评分产物；评分器主要读 result.json，解析结果完整内嵌。
- 关键设计 2（省预算）：路径判定合并为单一路径决策（有文字层直接抽，无文字层才 OCR，个别页无层只对那几页 OCR），删除三路径并行流程；文本提取、页眉剥离、栏序判断等确定性工作交给平台工具与规则，模型只做判断。
- 关键设计 3（不编造）：解析不出或模糊的字段保留键名填 unknown 并登记 uncertainty{field,page,reason}；status 三态如实收尾（success/partial/failed_with_cause），failed 时写明原因与人工接管位置。
- 关键设计 4（创新点精简保留）：跨页段落合并（截断+接续词判定+changes 留痕）与题注-正文引用配对（figure_id 配对+unmatched 标注）各一小段，收敛到 parsing-rules.md。
- 创建 parsing-rules.md：8 条确定性细则（页眉剥离、双栏顺序、跨页合并、题注配对、章节层级、参考文献切分、公式保真、证据定位约定），替代原 4 个分支规则文件。
- 创建 result-template.json：result.json 骨架模板，提示把键替换为 output_contract 实际键名。
- 重写 README.md：调用方式、输入输出、最小示意示例（标注"示意输出，非正式案例结果"）、适用范围与限制、文件清单。
- 交付自检：共 5 文件（SKILL.md、README.md、worklog.md、parsing-rules.md、result-template.json），全部 UTF-8 文本，总量约 15KB，符合 ≤5 文件 ≤100KB 限制；SKILL.md 约 150 行 <250 行上限。
