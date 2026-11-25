# worklog

- 2026-11-11 完整阅读题目文件 task.md，确认评分维度（实际效果40/使用增益25/创新增益15/可靠体验10/生态贡献10）、Harbor 运行契约（64次模型请求、900秒、16384 tokens/响应、50个文本文件/500KB/2MB）与输入修订（两篇论文、JATS paragraph_id 定位、跨篇合并门槛、禁造页码）。
- 2026-11-11 阅读 challenge.json，确认无额外的 output_contract 细节，评分 strategy 为 human_review_only。
- 2026-11-11 创建 submission/SKILL.md。设计决策：两阶段流程（S3 只抽实体、S4 基于登记表抽关系）防止实体漂移和幻觉实体；固定谓词方向规则防止方向颠倒；证据定位强制回填（无 paragraph_id 加短引不许建边）；S5 从严跨篇合并门槛呼应输入修订中"通用术语不代表同一实例"；S7 要求先落盘 result.json 骨架再增量补全以适应 900 秒预算。
- 2026-11-11 创建 submission/resources/types.md。设计决策：10 类实体（method/dataset/material/task/metric/result/disease/gene/researcher/other）加 other 兜底防强行归类；11 个谓词全部带方向规则、正例、反例，禁 related_to 用于纯共现；confidence 与 stance 分离，否定句可 high。
- 2026-11-11 创建 submission/resources/triple-spec.md。设计决策：三元组 schema 含 direction/condition/stance/confidence/evidence/attribution；六条建边禁忌（共现不建边、否定不反转、跨篇不融合、常识不补全等）；CSV 导出格式与 JSON 同源。
- 2026-11-11 创建 submission/resources/normalization.md。设计决策：篇内合并三依据（缩写定义、变体、回指链）；跨篇仅两条显式依据可合并；canonical_id 用 M 前缀且原始实体行保留；冲突处置为双保留加登记，禁止合成结论。
- 2026-11-11 创建 submission/resources/result-template.json。设计决策：默认字段集覆盖 output_contract 常见要求（case_id/status/entities/triples/merges/conflicts/queries/unreported/limitations/uncertainty/change_record），contract 额外字段并入顶层；status_reason 必填异常编号与人工接管位置。
- 2026-11-11 创建 submission/resources/checklist.md。设计决策：自检分五组（实体/关系/跨篇/查询输出/定位合规），全过才允许 status=success，未过项写 limitations。
- 2026-11-11 创建 submission/README.md。设计决策：含完整调用步骤、输入输出表、最小调用示例（JSON 加 CSV 各一，明确标注"示意输出，非正式案例结果"）、关键设计五点、限制与失败处理、跨学科复用说明。
- 2026-11-11 创建本 worklog.md，记录时间顺序关键动作与设计决策。
- 2026-11-11 执行交付核验：7 个文件均在 500KB 内、总量约 40KB、全部 UTF-8 文本、无 symlink、无二进制；SKILL.md frontmatter 为合法 YAML（name 英文小写连字符，description 英文三要素齐全）。
