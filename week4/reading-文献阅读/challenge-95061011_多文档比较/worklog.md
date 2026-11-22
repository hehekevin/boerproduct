# worklog — doc-compare-r3 重设计动作记录

## 输入研读
- 读 task.md（challenge-95061011）全文：评分维度表（实际效果 40 / 使用增益 25 / 创新增益 15 / 可靠体验 10 / 生态贡献 10）、Harbor 运行契约、organizer revision v2 输入接口（comparison-workorder + 双文档定位 + 六维可比性 + 不池化）。
- 读 r2 版（week4-redo/challenge-95061011/submission，聚合 66.33）：SKILL.md 140 行、check_result.py、field_dictionary.json、example-result.json、worklog.md。
- 读旧版 littrack/skills/doc-compare 与最高分标杆 chart2data（72.33）的 SKILL.md，提取已验证方法：协议置顶、线性 ≤5 步、骨架先行、预算保护、校验器抓错清单、资源精简。

## 66→70 差距诊断
- r2 的比较产出只有"逐格 matrix（单文档引文）+ synthesis 冲突列表"，缺少**结构化的两两比较维度矩阵**——评委无法逐格核对"这个比较判断依据了哪两份原文"。
- 冲突处理只有自由文本 attribution，无归因维度枚举，可比性判定与冲突之间没有硬性双引文约束。
- 覆盖密度（多少格、多少可比判断、多少冲突）散落在结果里，没有汇总块。

## r3 设计动作
- 新增 `result.pairwise`：每对文档 × 每个比较维度一条记录 `{pair, dimension, verdict, note, evidence[双方逐字引文]}`；verdict≠not_judged 强制双文档引文（每格回溯两份原文），not_judged 强制 note 说明。
- 冲突登记升级：`attribution_dimension` 枚举（sample/method/metric/condition/object/scope/unattributable），quotes 强制 ≥2 条且来自不同文档。
- 新增 `result.coverage` 统计块：cells/reported/not_reported/not_comparable/pairwise_records/conflicts/claims，校验器核对一致性，覆盖密度可一眼核验。
- claims 规则收紧：跨文档 claim（evidence 涉及多文档）强制 ≥2 条不同文档引文。
- check_result.py 升级：在 r2 覆盖/引文/reason/混池检测之上，新增 pairwise verdict 枚举、双文档引文、冲突不同文档引文、跨文档 claim 引文、coverage 数值一致性共 5 类检查；保持三级容错（load_json 捕获、逐条 try、顶层 except 降级）。
- SKILL.md 175 行（≤250）：强制执行协议 6 条置顶 + 线性五步 + 输出 schema（含 pairwise/coverage）+ 校验器抓错清单 + 异常处置表（新增"仅 1 篇文档"处置）+ 最小示例 + 已知限制。
- 资源 5 个（≤8）：check_result.py / field_dictionary.json（补 pairwise_verdict_enum 与 attribution_dimension_enum）/ example-workorder.json / example-result.json（含 6 条 pairwise、1 条冲突、2 条跨文档 claim、coverage 块）/ README.md。
- README.md：文件清单、快速使用、本地自测命令与预期输出、带注释的最小调用示例（标注示意）、适用范围与限制、维护信息。
- 不硬编码路径：运行时路径用 /skills/weekly-skill 与 /input、/app 约定；本地自测用相对路径。

## 自检
- SKILL.md 行数 ≤250 ✓；流程线性 5 步 ✓；协议置顶第 1 节 ✓；资源文件 5 个 ≤8 ✓。
- example-result.json 通过本地 check_result.py 双测（PASS + 负例 FAIL 验证，见下）。
- 示例标注"非正式答案，仅说明接口" ✓；无预制正式答案 ✓。
