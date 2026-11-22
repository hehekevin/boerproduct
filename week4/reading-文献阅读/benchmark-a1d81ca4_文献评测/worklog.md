# benchkit v3 worklog（时间线，一行一条）

- 读毕 task.md 全文、Harbor 技术约定、Organizer revision2 四条 source-conditioned 工单声明与通用 result.json 契约（case_id/status/result/claims/uncertainties）
- 旧版失分点分析①（两版 55.33/55 共性）：case.json 解析只认 4 个硬编码顶层键，真实结构不同即产空题集，实际效果 40 分大块丢失 → v3 递归扫描任意层级识别工单条目与 output_contract，识别失败合成兜底题卡，绝不产空
- 旧版失分点分析②：「改得动——只重算受影响的分数」无实现（version 只有整包 items_sha，无法定位哪题变了）→ v3 新增 item 级 item_shas 快照 + diff 子命令，改题后只重算 rescore_only，comparable 题目历史分数可比，diff.json 即版本对比报告
- 旧版失分点分析③：「跑得一致——波动被记录和解释」无机制 → v3 techcheck 记录 check_sha，复跑不一致自动写入 version.changes
- 旧版失分点分析④：原始输出仅嵌摘要、未嵌全文，「查得回」弱 → v3 embed 把 run_results 全文与题卡、分数、失败样例、版本、materials 全量嵌入 result.json
- 旧版失分点分析⑤：硬编码 /skills/weekly-skill 平台路径 → v3 改为相对 SKILL.md 所在目录定位 + find 兜底
- 旧版失分点分析⑥：缺 README（文档完整性/资源可复用性失分）、claims 无模板致运行时易缺证据字段 → v3 补 README（示意示例标注示意）+ claims 四字段模板与 answered 时非空校验
- 旧版失分点分析⑦：v1 无强制协议与骨架先写纪律导致重放 result.json 缺键 → v3 协议置顶：第 1 步抄契约全键、第 2 步立即写 result.json 骨架、失败也交付
- 设计五步流程：抄契约 → 落骨架 → 题卡定稿+统一作答 → 评分与失败归因 → 嵌入+自检收尾；线性 ≤5 步，SKILL.md ≤250 行，命令式祈使句
- 编写 scripts/benchkit.py（init/diff/techcheck/embed/verify 五子命令，except Exception 全捕获降级，退出码恒 0，verify 结果以报告与打印表达）
- 解析鲁棒化：递归找工单条目（路径关键词加分）、任意层级找 output_contract（dict/键名列表两种形态）、字段名同义词映射（task/question/prompt 等 9 组）、extra 保留未识别字段不丢数据
- 技术检查增强：数值逐字覆盖、条件词覆盖（子串或 token 覆盖率≥0.6）、参考答案与来源数值矛盾如实标记；全部与语义评分分开记录
- 编写 examples/example-case.json：合成四条工单 + output_contract 演示契约抄写，标注示意非正式
- 编写 README.md：快速开始、六件产物表、status 四级、最小示意示例（标注示意）、异常降级、复用与维护
- 正例双测：example-case 全流程 init→diff→techcheck→embed→verify PASS（含作答与评分模拟）
- 反例双测：损坏 JSON / 空 case / 未知结构三种输入均不崩溃、六件+result.json 照常产出
- 自检：SKILL.md 行数 ≤250、协议置顶 frontmatter 后第一节、流程 5 步、资源文件 5 个（<8）、无平台路径硬编码
- 汇总交付清单与自检结论，回报 team-lead
