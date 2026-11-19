# worklog — benchmark-d57ad64a 最终包（83 公式对照增量增强）

## 基线
redo 版 submission（旧聚合最高 66.00，SKILL 211 行）全量复制为起点，只增不推翻。

## 对照 83 公式的缺失清单（逐要素核查结果）
| # | 83 公式要素 | redo 版状态 | 处置 |
|---|---|---|---|
| 1 | 强制执行协议 7 条 | 只有 6 条，缺「每步一个写盘动作」 | 协议补足 7 条 |
| 2 | 主产物全量嵌入 result.json | 七件中 report.md 全文未嵌入 | embed 新增 report_md 嵌入 |
| 3 | 机械校验器逐条结果嵌入 | acbench_verify.json 只落盘未嵌入 | verify 报告回写 result.verify |
| 4 | gate 状态显式枚举 | 无（只有 ok/problems） | 9 校验域输出 5 态枚举 |
| 5 | claims evidence 逐字回证 | 只查字段存在，不查 quote 真伪 | evidence_backing 域：空白归一化子串匹配，unbacked 逐条列出 |
| 6 | 分歧裁定机制显式 | SKILL 有文字，result 无结构记录 | adjudication.json（judge_a/judge_b/delta/adjudicated/anchor_revision/evidence）+ embed 嵌入 + disputed 无裁定 verify FAIL |
| 7 | item_shas 快照与 verify | 已有 | 保留；verify 校验一致性 |
| 8 | SKILL.md ≤150 行 | 211 行超硬约束 | 压缩重写到 150 行，机制零丢失 |

## 补强实现（scripts/acbench.py，单文件不变）
- `norm_ws()`/`corpus_from_case()`：quote 回证的空白归一化语料（case.json 全字符串值）。
- `cmd_verify` 重构：gate(name, ran, errs, skipped) 辅助函数，每个校验域登记状态；
  裁定检查（disputed − adjudication.rounds 逐条比对）；evidence_backing（claims 与
  run_results.evidence 的 quote ≤40 字截断后回证）；报告含 checked_at 时间戳，
  保存 acbench_verify.json 并回写 result.json 的 result.verify。
- `cmd_embed`：新增读取 report.md 全文与 adjudication.json 嵌入。

## 双测证据
- 正例（example-case.json 全链路）：init→稿件/评分/裁定/claims 写入→diff→techcheck→
  report→embed→verify **PASS**，gate 9 域全 enforced。
- 反例 A（注入脏数据）：幽灵评分行 ghost-9/非法分值 5/disputed 无裁定/编造 quote
  "99.9"/嵌入滞后 → verify FAIL 抓出 5 处，gate 正确降 enforced_with_findings。
- 反例 B（case.json 截断损坏）：init 兜底题卡不崩溃产全套文件；verify 如实 FAIL 6 处，
  gate 出现 not_found（failures）与 skipped_not_provided（未提供 --case 时
  evidence_backing）——四种枚举状态实测均可达。

## 遗留/边界
- evidence 回证语料仅 case.json；/input 独立材料文件需 Agent 手工核对后补入（SKILL
  已知限制中如实声明，不伪造可回证性）。
- 退出码恒 0（平台流程不中断优先），问题通过 verify 报告 FAIL + status 降级 + gate
  状态显式呈现，等效满足「问题不许打印了事」。
- 资源 5 文件（SKILL/README/worklog/example-case/acbench.py）远低于 50 文件上限；
  脚本纯标准库，无 CDN/外部依赖；未硬编码平台路径（$SK 动态定位 + find 兜底）。
