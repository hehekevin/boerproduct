# worklog — challenge-308a6fdc 学术论文写作 Skill（v3 = v2 + 83要素补强）

日期：2026-11-16。目标：v2 已解决逐章分批写（治 0 分），本次对照 83 分公式补齐剩余要素，冲击 rubric 饱和点 83。

## 历史成绩

| attempt | 分数 | 备注 |
|---|---|---|
| 71936 | 62.33 | v1 基线 |
| 72448 / 72460 | 52.67 / 53.33 | 章节覆盖不足 + 修复挤占预算 |
| 72475 | 0 | 单响应全文超限截断 → v2 已治（逐章分批写盘回填） |

## v3 对照 83 分公式的缺失要素清单与补强

| # | 公式要素 | v2 状态 | v3 补强 |
|---|---|---|---|
| 1 | 强制执行协议置顶（7 条） | 已有 | 保持不变 |
| 2 | 主产物结构化全量嵌入 result.json | 只有产物路径指针 | **build_result.py 新增 --sections-dir：`sections[]`（结构化章节）+ `draft_text`（全文）嵌入 result.json**；评分器不开附件即可核对 |
| 3 | 机械校验器逐条三元组嵌入 | check_report/fact_check 只在附件文件，且只有 verdict/missing | **consistency_check.py 每项输出 {item, template_value, applied, match} 三元组；fact_ledger.py check 输出数字-来源全量核对表 `checks[]`（每个数字 {item, template_value, applied, match, source_id, location, quote≤40}，unbacked 逐条入 unmatched_detail）**；全部经 build_result 嵌入 result.json |
| 4 | 闸门状态显式枚举 | 无 | **check_report 顶层 `gates{}`（enforced/skipped_not_provided/not_found/unreadable）+ `skipped[]` + gate_note「下游不得宣称已核对」**；draft/constraints 不可读时如实记 unreadable |
| 5 | 关键论断 evidence 逐字摘录逐条嵌入 | evidence_map.jsonl 在工作目录，未推导进 result.json | **build_result.py 自动由 evidence_map 推导 `claims[]`（claim_id/section/text/kind/evidence≤40字逐字/source_id/location）嵌入 result.json** |
| 6 | 章节完整性机检 | 只在 check_report 附件 | **build_result.py --constraints 计算 `section_check{item, template_value, applied, match, missing}` 嵌入 result.json** |
| 7 | status 诚实四级 | 三级 | 补 **blocked**（材料/依赖缺失无法开工也写 result.json 说明缺什么） |

SKILL.md 同步更新 Step 5（嵌入要求、四级 status、闸门枚举），126 行 ≤150；README 同步。资源仍为 6 脚本 + 1 示例 = 7 文件（≤8），线性 5 步不变，无平台路径硬编码。**增量增强，未推翻 v2 任何机制。**

## 本地双测证据（test_dual.py，正反例全过：DUAL-TEST PASS）

- **正例（合成 case 全链路）**：ledger 8 条 → docx_build 合并 2 章 → fact_check checked=7 **unmatched=0**、checks_rows=7（逐条带 source/quote）→ consistency verdict=pass、gates 枚举完整（citations/terms=skipped_not_provided + gate_note）→ result.json 含 sections=2、draft_text、claims=1（kind/evidence/source_id/location 齐全）、section_check.match=True、status=complete。
- **反例（脏数据注入）**：S01.json 写坏 + 注入自补数字 3.7%/256 例 + 删「3 讨论」章节 → docx_build **跳过坏文件留痕 skipped**；fact_check **unmatched=2 逐条抓出**、verdict=fail；consistency **missing=['1 材料与方法','3 讨论']** 抓到、section_check.match=False；build_result status=partial 如实降级。所有校验器均抓到注入的脏数据，fail 计入退出码。
- result.json 每步可解析；docx stdlib 兜底路径可用。

## 运行时约束核对

- 64 次请求 / 900 秒内可完成 5 步（逐章分批 + 熔断 48 次/700 秒保留）。
- 16384 token/响应：单响应只写 1 章 ≤1500 字，不会超限。
- 3 案例 × 3 重复：任何一次中断 result.json 仍完整可解析（骨架先行 + 每步回填）。
