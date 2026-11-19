# lit-review-bind — 文献综述生成 Skill（v1）

针对 Bohrium 产品赛第 4 期「深度研究与文献综述」赛道「文献综述生成」(challenge-e97137c9)
的参赛 Skill。锁定子场景：**主题归纳 + 段落-来源绑定 + 引用逐字回证 + 分歧对照 + 覆盖遗漏登记**。

## 1. 用途与适用条件

给定研究问题、纳排标准与文献集（真实署名论文），完成四步并交付可复核的综述：

1. **逐条筛选**：每篇文献判 `keep / pending / exclude`，keep 命中纳入标准 id、exclude 命中
   排除标准 id、pending 必须写理由并登记 pending_review——无依据标签被校验器判 FAIL。
2. **主题归纳**：`themes[]` 每个主题必须写 basis（从哪些文献的什么分歧/方法/对象中长出来），
   禁止套「背景/方法/挑战/展望」通用框架；大纲（时间脉络 + 方法论脉络）在草稿写作**之前**
   声明进 `/app/work/outline.json` 台账，之后只许补充不许推翻。
3. **段落-来源绑定 + 逐字回证**：每个非空段落 `source_ids` 必须非空且来自输入文献集；每条
   实质论断进 `claims[]`，其 `evidence.quote` 必须在来源文献的 case.json 实际正文/摘要里
   **逐字命中**（空白归一化后子串匹配）——编造引用被 `unbacked_quotes` 机械拦截。
4. **分歧与共识并列**：结论相反的文献在 `disputes[]` 双方并列（各立场附文献 + 逐字 quote，
   双方文献不得重叠）；论断强度三级 `established（≥2 来源）/ suggestive / disputed（须指向
   dispute_id）`——结论不超出文献支持范围。
5. **覆盖与遗漏登记**：`theme_group.py` 机械重算 coverage（total/included/cited/uncited/ratio），
   未入大纲的 keep 文献必须在 `omissions[]` 登记原因，不准静默丢文献。

**核心保证**：`verify_check.py` 汇聚四组机械校验（绑定/回证/分歧/覆盖，全部对应题面机检点），
把编造引用列入 `unbacked_quotes` 判 FAIL；`gain_probe.py` 用正常 vs 退化双跑实测机制增益并
写入 `result.gain_evidence`。评分器不开附件即可通过 `self_check / gates / unbacked_quotes /
validator_verdict` 核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 | 一批文献要写成综述，要求每句都能指回具体文献具体位置 | 绑定段落的草稿 + 逐字回证的 claims + 证据表 |
| 研究助理 / 综述作者 | 领域内结论互相矛盾，怕综述抹平分歧 | disputes[] 双方并列呈现 + 强度三级标注 |
| 复核者 / 导师 | 抽查「这句是哪篇文献支持的」 | para_ref→claim→evidence.quote→papers[n].abstract 全链回溯 |
| 教学 / 培训 | 演示"先声明大纲、后写草稿、机器拦编造"的写作纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不做数据库实时检索、不全文精读、不做单篇事实审查；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包实测 3.13），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化） |
| 磁盘 | 整包 < 100 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 文献清单 + 大纲台账模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-3：Agent 声明标准与主题大纲，逐条筛选后写草稿并绑定段落来源（见 SKILL.md 七步流程）

# Step 4：分歧核对 + 覆盖机械重算
python3 /skills/weekly-skill/scripts/dispute_table.py --result /app/output/result.json --emit-into
python3 /skills/weekly-skill/scripts/theme_group.py --result /app/output/result.json --case /input/case.json --emit-into

# Step 5：增益对照 + 效率计数（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 6：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

## 5. 输入与输出

- **输入**：`/input/case.json`（研究问题 + 纳排标准 + 文献 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_quotes` / `gates` / `validator_verdict`（+ 校验器回写的
    `quote_audit` / `dispute_audit`）
  - `result` 内：`material_gaps`、`environment`、`research_question`、`criteria`、`items[]`
    （逐条筛选）、`themes[]`（主题分组）、`outline`（段落-来源绑定草稿）、`evidence_table[]`、
    `disputes[]`、`omissions[]`、`coverage`、`steps`、`run_status`、`verdict`、`verdict_basis`、
    `gain_evidence`、`efficiency`
- **强度体系**：`established`（≥2 来源）/ `suggestive`（提示性）/ `disputed`（指向 dispute_id）。
- **status**：`answered` | `partial` | `insufficient_evidence` | `input_error`。
- **工作区产物**：`/app/work/verify_check.json`、`schema_guard.json`、`gain_evidence.json`、
  `outline.json`（大纲台账）、`gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（标题摘要均为虚构）：6 条候选 → 4 keep（全部入大纲并绑定来源）、
2 exclude（动物实验 / 会议摘要重复合并）；2 主题、3 段落、4 条 claims（2 established /
1 suggestive / 1 disputed）、1 个分歧对照 D-01 + 1 个共识 D-02；coverage ratio=1.0。
关键片段：

```json
{
  "case_id": "demo-litreview-001", "status": "answered",
  "result": {
    "themes": [{"theme_id": "T1", "basis": "R01/R02/R03 三项试验对同一结局给出方向不同的结果", "paper_ids": ["R01", "R02", "R03"]}],
    "outline": {"sections": [{"paragraphs": [{"para_id": "P-01", "source_ids": ["R01", "R02"], "claim_ids": ["c-01"]}]}]},
    "disputes": [{"dispute_id": "D-01", "status": "disputed", "positions": [{"side": "positive", "paper_ids": ["R01", "R02"]}, {"side": "negative", "paper_ids": ["R03"]}]}],
    "coverage": {"total_papers": 6, "included_papers": 4, "cited_in_outline": 4, "uncited": 0, "ratio": 1.0},
    "verdict": "drafted"
  },
  "claims": [{"claim_id": "c-02", "strength": "disputed", "dispute_id": "D-01",
               "evidence": [{"paragraph_id": "R03", "quote": "Overall symptom relief did not differ between groups at week 10 (p=0.31)"}]}]
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/draft_bind.py --result examples/example-result.json --case examples/example-case.json --out /tmp/db.json
python3 scripts/dispute_table.py --result examples/example-result.json --out /tmp/dt.json
python3 scripts/theme_group.py --result examples/example-result.json --case examples/example-case.json --out /tmp/tg.json
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --outline /tmp/wk/outline.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS` |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 引用全回证 | `unbacked_quotes` 为空数组 |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 全记录覆盖 | coverage 与机械重算一致；每篇 keep 归属主题或登记 omissions |
| A6 | 段落必带来源 | 每个非空段落 source_ids 非空且来自输入文献集 |
| A7 | 分歧并列呈现 | disputed 条目 ≥2 立场、双方文献不重叠、各附逐字 quote |
| A8 | 强度不越界 | established ≥2 来源；disputed claim 的 dispute_id 有效 |
| A9 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A10 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（段落绑定 + 逐字回证 + 分歧对照 + 覆盖检查） | — |
| `degraded` | 枚举/结构/verdict 一致性 | **binding / quote / dispute / coverage 四组** |

实测对照（合成案例 + 注入 3 项污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入漏检（四类） | 0 | 0 | 0 |
| steps_count | 25 | 7 | +18 |
| 污染副本 verdict | FAIL（8 处问题） | PASS（0 处） | −8 |
| 污染副本无来源论断漏检 | 0 | 1 | +1 |
| 污染副本编造引用漏检 | 0 | 1 | +1 |
| 污染副本分歧漏检 | 0 | 1 | +1 |
| 污染副本覆盖遗漏漏检 | 0 | 3 | +3 |

**同一校验器、同一污染输入**：正常模式抓全（漏检 0，8 处问题全部报出），退化模式 6 处客观
违规全部漏掉且 verdict 从 FAIL 翻成 PASS——机制增益最直接的证据。违规真值由探针独立复算
（与校验层分开实现）；详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台"基础 Agent vs
> 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 检索无结果 / 文献集为空 | items 空、coverage.total=0、verdict=cannot_verify 或 not_drafted，绝不补造文献 |
| 缺全文/元数据不全 | missing_metadata 登记 + pending 进 pending_review |
| case 未提供文献正文 | 逐字回证降级为 evidence_table 摘录底本，登记 unverifiable_text |
| 结论冲突 | disputes[] 双方并列 + uncertainties.conflicts；claims 标 disputed |
| 文献不入大纲 | omissions[] 登记原因，coverage 留痕，不静默丢弃 |
| 算力/时间不足 | 保留已完成段落，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与 `problems` 列表，
Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：quote 逐字回证会不会太严格导致误报？**
匹配前做空白归一化（`\s+` 折叠），跨行/跨空格的摘录不受影响；不做大小写折叠以防语义误伤。
对不上的进入 `unbacked_quotes` 并给出 claim 定位，可人工复核后再修。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。SKILL.md 明确
退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：established 的 ≥2 来源阈值谁定的？**
本技能的保守口径（题面未给定阈值时按可核验性保守设定并在 SKILL.md 写明）；单来源但有
强证据的论断请标 suggestive，不冒充 established。

**Q：某篇文献确实该丢怎么办？**
登记 `omissions[]`（paper_id + reason + needed_action）并留 coverage 痕迹。综述只准把
"丢文献"变成显式登记，不准静默消失。

**Q：同一篇文献进了两个主题算错吗？**
不算。theme_group 会把跨主题文献记入 theme_overlap 供复核；禁止的是主题无 basis 或主题
之间完全重叠空洞。

## 11. 适用范围与限制

- 仅处理输入文献集内材料：不做实时检索、不全文精读、不做单篇事实审查（由相邻课题输入）。
- established 阈值与归一化口径是本技能设定并事前声明，不冒充外部标准。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/draft_bind.py` 的 `analyze_binding()` | 纯函数式；"论断-来源-逐字引用"回证可移植到任何需要引用核查的场景 |
| `scripts/dispute_table.py` 的强度三级 | established/suggestive/disputed + dispute_id 断链检查，任何"结论分级"场景可照抄 |
| `scripts/theme_group.py` 的覆盖重算 | "手填值 vs 机械重算值"对照模式可移植到任何覆盖/完整性检查 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改标签/换假 quote 即得新的负例 |
| 键归属约定 | 每个脚本独占自己的顶层键，多脚本并发回写互不覆盖 |

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明，141 行） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/文献清单/大纲台账模板（退出码恒 0） | 是 |
| scripts/theme_group.py | 主题归属核对 + coverage 机械重算（键归属 coverage） | 是 |
| scripts/draft_bind.py | 段落-来源绑定 + 引用逐字回证（键归属 quote_audit） | 是（含 `analyze_binding()` API） |
| scripts/dispute_table.py | 分歧对照登记 + 强度不越界（键归属 dispute_audit） | 是 |
| scripts/verify_check.py | 总校验器（汇聚四组 + 闸门 + 回写自检四键） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（6 条虚构文献） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节七条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/ITEM_REQUIRED/CLAIM_REQUIRED`
  与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
