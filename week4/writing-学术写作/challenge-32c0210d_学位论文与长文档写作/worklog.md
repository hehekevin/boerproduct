# worklog — acwrite-thesis v3 重做记录（challenge-32c0210d）

## 旧版失分点分析（v1 55.33 / v2 53）

1. **主产物内嵌从未真正执行（关键 bug）**：v2 SKILL.md Step 4 调用 `build_result.py --embed-file ... --embed-key deliverable_content`，但脚本实际不存在这两个参数（argparse 直接报错退出）。协议第 3 条形同虚设，result.json 交付不完整 → 实际效果（任务完成度/完整性）与可核验性直接失分。
2. **模式误判风险，与组织方输入修订脱节**：题目 Organizer input repair v1 明确"W16 提供的是分章可编辑工作章节 + organizer-edit-workorder.json（明确实际编辑目标与离线本地工作流范围），不是一篇完整论文待起草"。v2 只有"从材料起草全稿"一种流程，若真实案例是成稿/改稿任务，v2 会按起草模式错误地重新规划章节，违反"只动需要动的地方、保留作者原意"（评分维度"改得动"）。
3. **缺"改得动"产出**：四个考察点中立得住/连得上/查得清都有机制（chapter_plan/registers/evidence_map），唯独改动记录只有一句 changelog，无逐处修订留痕（原句/改句/理由/依据），版本管理方向零产出。
4. **SKILL.md 缺最小调用示例**：交付要求明确"至少一组输入、调用方式和示意输出"，v2 SKILL.md 与 README 均无 → 生态贡献（文档完整性/可复用性）失分。
5. **16384 token 限制应对不足**：v2 说"一次性写进 draft_all.json"，数万字全稿攒到一次响应输出必然截断，缺"分批写、逐章回填"的明确操作指令。

## 新版关键改进（v3）

1. **修复内嵌 bug**：重写 build_result.py，真正实现 `--embed-file/--embed-key`（读文件内容写入 result[key]，记录 embed_info.chars），并新增 `--revision-log`。协议第 3 条落地。
2. **双模式 Step 0 强制识别**：检测 organizer-edit-workorder.json / 工作章节 → 成稿模式 B（工单拆解为逐条修改项，只动指定处，作者原句保留）vs 起草模式 A。直接对应组织方输入修订。
3. **revision_log.jsonl 修订留痕**：`{loc, original(逐字≤40字), revised, reason, basis, type}`，Step 3 要求 original 能在原稿中找到；覆盖"改得动：可回退、可比较、可说明"。
4. **分批内嵌协议**：每章单独成段写，写完一章即用 build_result.py --embed-file 刷新回填，规避 16384 token 单响应截断。
5. **补最小调用示例**（SKILL.md 示意节 + README），标注"示意，非正式案例结果"。
6. 保留 v2 已验证有效的全部机制：协议置顶、广度优先、48请求/700秒熔断、脚本动态定位（find /skills，不硬编码路径）、脚本三级容错、status 四级诚实、契约全键。

## 验证记录
- build_result.py 本地冒烟：`--set`/`--embed-file`/`--revision-log` 均正常写入 result.json（见提交前自测）。
- 资源规模：SKILL.md 约 120 行（≤250）；脚本 6 个（≤8）；均为 UTF-8 文本，无硬编码平台路径。
