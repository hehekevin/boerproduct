# worklog — num-consistency-audit（challenge-9e7302fd 重构）

## 时间线（2026-11-22）

1. 读题面 `week4-dl/challenge-9e7302fd/task.md`，确认「突破方向 5：结果报告审查——数字一致性」为最机械可校验方向。
2. 读旧 40 分包（六分面 + stat_recompute 6 类复算 + gain_probe 消融），读 77 分标杆结构，复用其「保命纪律 + 骨架 + 校验 + 守卫」骨架模式。

## 砍了什么

- 砍掉研究设计 / 变量定义 / 统计方法匹配 / 样本量估算 4 个方向 → `result.unchecked` 记 `out_of_scope`。
- 砍掉 `coverage_audit.py`、`stat_recompute.py`（6 类统计复算）、旧 `gain_probe.py` 三个脚本，改为单一 `number_audit.py` 核心。
- 删掉 6 分面 schema（facets/manuscript_overview 六面/defect_class/pending_review/suppressed 等），精简为 number_audits + findings + conflict_summary。
- 增益层降级为 `available=false`（预算过半跳过），不实跑正常/退化消融。

## 数字比对怎么做（number_audit.py）

1. 读 case.json 提取全文/章节/表格/图注成段。
2. 正则机械提取六类数字：样本量 n、p 值、效应量(r/d/OR/RR/HR)、CI、百分比、统计量(t/F/χ²/df)。一律 `\d`，不用 isalpha。
3. 每条约数字记 audit_id + kind + value + source + raw（取匹配处前后文，全文子串，天然可回证）+ location。
4. 6 条交叉比对规则（R1 总数一致 / R2 同名统计量冲突 / R3 df 越界 / R4 p 值与显著措辞 / R5 CI vs null / R6 CI 宽 vs SE）产 findings[]，每条带逐字 quote + severity + revision。
5. 模型只负责在"同一统计量多值冲突"时辅判哪次是笔误，不做全文语义精读。

## 对照数字（example-case 自检，故意埋的坑全被抓住）

- 摘要"共纳入 48 名" vs 方法"招募 36 名" vs 图注"共 51 名" → R1 critical 命中。
- t(52) 的 df=52 > n-1=47 → R3 major 命中（2 处 t(52) 各报一次）。
- p=0.03 却写"不显著" → R4 critical 命中。
- CI [0.20,0.30] 宽 0.10 ≠ 2×1.96×SE(0.10)=0.39 → R6 major 命中。
- 遏制误报的关键修复：p 值/CI 的显著性措辞匹配窗口收紧为"同句"（sentence_window），避免把下一句的"不显著"误挂到上一句的 p=0.04（该句实际写"显著"，正确地未报错）。

## 自检结果

- 全链路：build_skeleton → number_audit → verify_check → schema_guard，退出码全 0。
- verify_check PASS（11 条 self_check 全通过）；schema_guard PASS（契约+schema 不缺键）。
- SKILL.md 97 行（≤150）；脚本 4 个（≤8）；零依赖 python3 标准库。

## 已知限制

- 仅做数字自洽性核对，不验证原始数据真伪；不覆盖四方向。
- R4/R5 的措辞匹配基于同句内正则，跨句措辞或复杂否定句仍有漏判可能（记 uncertainties，不硬报）。
- 平台白板对照由平台生成，本结果不预置任何案例答案。