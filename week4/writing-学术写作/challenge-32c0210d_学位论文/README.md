# acwrite-thesis — 学位论文与长文档写作

「学术效率」比赛 · 学术写作赛道 · 学位论文与长文档写作（challenge-32c0210d）参赛 Skill（v3）。

## 用途
双模式长文档写作技能：
- **起草模式 A**：从固定科研材料按提纲起草学位论文全稿——章节规划带论证任务与字数预算，广度优先全章最小合格版先行再加深。
- **成稿模式 B**：按 organizer-edit-workorder 对给定的"分章可编辑工作章节"做完成/改写/校对——只动工单指定处，作者原句保留，每处改动写修订日志（原句/改句/理由/依据），可回退可比较。
两模式共用跨章节登记簿（术语/符号/定义/结论）与证据挂账（locator+逐字摘录），主产物全文内嵌 result.json。

## 快速开始（Harness 执行环境）
1. 读取 `/input/case.json` 与 `task.md`，抄下 `output_contract` 全部字段名与 case_id，立即写 `/app/output/result.json` 骨架（status="partial"）。
2. 检查 `/input/` 是否含 `organizer-edit-workorder.json` 或分章工作章节 → 有则成稿模式 B，无则起草模式 A。
3. 按 SKILL.md 的 5 步流程执行；脚本先 `find /skills -type d -name scripts` 定位后调用。
4. 最终交付到 `/app/output`：thesis.docx + thesis.md + result.json（契约全键 + case_id + deliverable_content 全文内嵌 + revision_log）。

## 依赖
- Python 3.8+，仅使用环境预装库。
- 可选增强：python-docx（docx 构建质量更好）、PyMuPDF（PDF 提取）、openpyxl（xlsx）。
- 任一可选库缺失时脚本自动降级（stdlib 兜底），降级事实写入 changelog，不阻塞交付。

## 文件清单
- `SKILL.md` — 强制执行协议（7 条）+ 双模式 5 步流程 + 异常处置表 + 最小调用示例 + 交付自查清单
- `scripts/` — 6 个脚本：材料提取 / 事实台账 / 跨章一致性校验 / 文档构建 / 渲染预览 / 结果组装（含全文内嵌）
- `examples/example_input.json` — draft.json 最小输入示意（仅示意结构，非正式案例结果）

## 方法要点
- **立得住**：章节规划 chapter_plan 每节写明回答什么问题、需要哪些证据、字数预算，合计等于总字数。
- **连得上**：登记簿四类条目（term/symbol/definition/conclusion）先查后用；cross_check.py 机检术语别名、符号冲突、定义重复、结论失配、图表编号错位。
- **改得动**：B 模式修订逐处写 revision_log（original 逐字≤40字 + revised + reason + basis + type），只动工单指定处。
- **查得清**：每条论断挂 evidence_map（locator+逐字摘录≤30字）；fact_ledger.py 对全文机检引用匹配；材料不足标 [材料缺口]。
- **主产物内嵌**：deliverable_content 收论文全文；单响应 ≤16384 tokens，按章分批写、逐章回填。
- **诚实降级**：渲染/解析库缺失或解析失败如实记录，不伪造状态。

## 适用边界
- 仅处理给定材料与工单支撑的写作任务；材料外的学科惯例改动记录在 changelog。
- 不做科研绘图算法本身、不做文献检索（只用给定材料中的文献）。
- 长文档规模下依赖分批写入与登记簿可见性，超出单次运行预算时按协议第 4 条广度优先收尾。

## 维护
- 版本 3.0（2026-11-13）：修复 v2 build_result.py 缺 --embed-file/--embed-key 导致内嵌失败的 bug；新增工单/成稿模式与修订日志；新增最小调用示例。
- 如遇新格式材料，扩展 `scripts/extract_materials.py` 的 ext_map 与对应解析函数。
