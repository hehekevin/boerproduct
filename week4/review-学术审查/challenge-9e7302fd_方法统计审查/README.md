# 数字一致性审查 Skill（num-consistency-audit）

研究方法与统计审查题（challenge-9e7302fd）的重构参赛包，锁定唯一方向：**结果报告审查——数字一致性**。

## 目标

核对稿件正文 / 表格 / 图注 / 摘要之间的 样本量(n)、p 值、效应量、置信区间(CI)、百分比、统计量、自由度 是否**自相矛盾**，产出可逐条回原文位置的审查单。这是本题五方向里**最机械、最可复算、最低误报**的方向。

## 为什么不审其它四个方向

研究设计 / 变量定义 / 统计方法匹配 / 样本量估算 依赖语义判断，误报率高、难以机器复算。本包把它们记为 `out_of_scope`（见 result.unchecked），把全部机械精度集中在一个方向，冲「结果正确性 + 结果可核验性」的分数。

## 文件清单

| 文件 | 作用 |
|------|------|
| `SKILL.md` | 技能入口，5 步流程 + schema + 4 条保命纪律 |
| `scripts/build_skeleton.py` | Step0 落骨架，提取 output_contract + 稿件结构，写 work 标志/台账 |
| `scripts/number_audit.py` | **核心**：正则 `\d` 提取六类数字 + 6 条交叉比对规则 |
| `scripts/verify_check.py` | 业务校验：定位回证、number↔finding 双向一致、口径、状态 |
| `scripts/schema_guard.py` | 结构守卫：契约字段 + 业务 schema 不缺键 |
| `examples/` | 合成示意案例（数字矛盾为演示故意构造）+ 示意输出 |

## 数字比对怎么做（6 条机械规则）

| 规则 | 检查 | 严重度 |
|------|------|--------|
| R1 | 入组总数在多个位置（摘要/方法/图表）互不相同 | critical |
| R2 | 同一统计量标签（r/d/t/F/df）多位置出现不同值 | major |
| R3 | 自由度 df 超过 n-1 | major |
| R4 | p ≤ 0.05 却写"不显著"，或 p > 0.05 却写"显著" | critical |
| R5 | CI 排除/包含 null(0) 却与显著性表述相反 | critical |
| R6 | CI 宽 ≠ 2×1.96×SE（容差 10%） | major |

数值提取一律正则 `\d`（不用 `isalpha` 判汉字），每条约数字卡片记 `audit_id + kind + value + source + raw + location`。

## 运行

```bash
python3 scripts/build_skeleton.py --case /input/case.json --input-root /input \
  --out /app/output/result.json --work-dir /app/work
python3 scripts/number_audit.py --result /app/output/result.json \
  --case /input/case.json --input-root /input --emit-into
python3 scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --emit-into
python3 scripts/schema_guard.py --result /app/output/result.json --case /input/case.json
```

## result.json 关键键

- `result.number_audits[]`：每条提取数字的出处+值+是否一致+冲突对象
- `result.findings[]`：不一致处（逐字 quote + location + severity + revision）
- `result.conflict_summary`：冲突计数/分布/已应用规则
- `result.unchecked`：out_of_scope 的四个方向
- `result.verdict`：audited / partially_audited / not_audited / cannot_verify
- 顶层 `claims` / `uncertainties` / `changelog` / `self_check` / `validator_verdict` / `gates`

## 失败处理

- 脚本退出码**恒为 0**，判据只看报告内 `verdict` 与 `problems`。
- 任何脚本异常都会降级写出可用 result.json，绝不缺文件。
- 稿件无结构化数字 → `verdict=cannot_verify`，material_gaps 登记，不编造。
- 图表无法解析 → material_gaps 注明，相关数字不硬比。

## 限制

仅做稿件内部数字自洽性核对，不验证原始数据真伪；不覆盖四方向（记 unchecked）；增益层预算过半降级为 `available=false`。