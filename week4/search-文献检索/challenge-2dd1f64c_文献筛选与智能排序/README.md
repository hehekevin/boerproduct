# lit-screen-rank — 文献筛选与智能排序 Skill（v1）

针对 Bohrium 产品赛第 4 周「科研检索」赛道「文献筛选与智能排序」(challenge-2dd1f64c)
的参赛 Skill。锁定子场景：**候选集逐条相关性判断 + 纳排标签分层 + 可解释多因子排序 + 待复核登记**。

## 1. 用途与适用条件

给定研究问题、纳排标准与候选文献集（真实署名论文 + 可能混入的预印本重复/冲突夹具），完成六件事：

1. **逐条相关性判断**：依据研究问题、研究对象、方法、人群、时间范围，把每条候选判为
   `direct / indirect / irrelevant`，并给 `high / medium / low` 置信度。
2. **纳排标签分层**：`keep / pending / exclude` 三层；keep 必须命中 ≥1 条纳入标准（引用
   criterion_id），exclude 必须命中 ≥1 条排除标准，pending 必须写明待定原因——无依据的
   标签会被校验器判 FAIL。
3. **可解释多因子排序**：relevance/quality/recency 三因子权重**在任何排序前事前声明**
   （rubric，合计=1.0），`score_rank.py` 机械复算 fused_score 并按平局规则
   （分数降序 → recency 降序 → item_id 升序）产出稳定顺序；同分并列全部记入 `ties`。
4. **冲突与重复处理**：预印本与正式发表版本、同一研究多篇报道 → `duplicate_of` +
   `conflicts[]` 登记 `merged`（保留正式版本）或 `escalated`（升级人工复核）。
5. **逐条理由与证据链**：每条判定给出 rationale + 逐字摘要证据（evidence_quote + 位置）+
   纳排命中 id；keep/pending 条目在 `claims[]` 有对应证据条目，fused_score 数字可逐字回证。
6. **待复核登记**：每个 pending 条目与每个升级冲突都登记进 `pending_review[]`
   （含 reason 与 needed_action），人工复核入口一个不漏。

**核心保证**：`verify_check.py` 用事前权重独立复算每条 fused_score 与期望顺序、逐条核对
纳排一致性、把无回证的证据与分数列入 `unbacked_numbers` 判 FAIL；`gain_probe.py` 用
正常 vs 退化双跑实测机制增益并写入 `result.gain_evidence`。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 / 系统综述初筛者 | 检索返回几十上百条候选，要按纳排标准快速分层并把关键文献提到前面 | 全记录分层标签 + 稳定排序 + 逐条理由 |
| 研究助理 / 文献管理员 | 需要向导师/团队解释"为什么这篇被排除、那篇排第一" | criteria_hit / excluded_by / evidence_quote 逐条可回溯 |
| 复核者 | 抽查相关性判断是否与标准一致 | pending_review 清单 + coverage 汇总 + 可机械复算的分数 |
| 教学 / 培训 | 演示"事前声明权重 + 机械复算 + 平局规则"的筛选纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不做数据库实时检索、不全文精读、不做系统综述纳排全流程；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 100 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 候选清单 + 打分口径模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 声明纳排标准与 rubric，然后逐条判定（见 SKILL.md 七步流程）

# Step 3：机械复算分数并排序（写 result.ranking / fused_score / rank）
python3 /skills/weekly-skill/scripts/score_rank.py --result /app/output/result.json --k 10

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

- **输入**：`/input/case.json`（研究问题 + 纳排标准 + 候选文献 + output_contract）、
  `task.md`。**以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`research_question`、`criteria`、
    `rubric`、`items[]`（逐条判定）、`ranking`、`coverage`、`conflicts`、
    `pending_review`、`steps`、`run_status`、`verdict`、`verdict_basis`、
    `gain_evidence`、`efficiency`
- **标签体系**：`relevance`（direct/indirect/irrelevant）× `label`（keep/pending/exclude）
  × `confidence`（high/medium/low）；判定条件与边界约定见 SKILL.md「Step 2」与
  `criteria` 的 criterion_id 编号。
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`（校验报告）、`/app/work/schema_guard.json`
  （结构报告）、`/app/work/gain_evidence.json`（增益对照证据）、`/app/work/rubric.json`
  （打分口径台账）、`/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（标题摘要均为虚构）：6 条候选 → 2 keep（P01 fused=0.91 排第 1、
P02 fused=0.82 排第 2）、1 pending（P04，登记待复核）、3 exclude（P03 预印本重复合并、
P05 综述、P06 动物实验）。示意输出关键片段：

```json
{
  "case_id": "demo-litscreen-001", "status": "answered",
  "result": {
    "rubric": {"weights": {"relevance": 0.5, "quality": 0.3, "recency": 0.2}},
    "items": [{"item_id": "P01", "label": "keep", "criteria_hit": ["IN-01", "IN-02"],
                "evidence_quote": "Sleep-restricted participants showed significantly reduced working memory accuracy (p < .01)",
                "fused_score": 0.91, "rank": 1}],
    "ranking": {"ordered_ids": ["P01", "P02", "P04"], "k_value": 3},
    "coverage": {"total_candidates": 6, "judged_items": 6, "keep": 2, "pending": 1, "exclude": 3},
    "verdict": "screened"
  },
  "claims": [{"claim_id": "c-01", "source_id": "P01",
               "evidence": [{"paragraph_id": "candidates[0].abstract", "quote": "Sleep-restricted participants showed significantly reduced working memory accuracy (p < .01)"}]}]
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/score_rank.py --result examples/example-result.json --k 3 --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --rubric /tmp/wk/rubric.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 数字全回证 | `unbacked_numbers` 为空数组 |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 全记录覆盖 | coverage.total_candidates == items 条数，每条 judged=true 或有 pending_reason |
| A6 | 纳排可回溯 | keep/exclude 逐条引用 criterion_id；irrelevant 不得标 keep |
| A7 | 排序可复算 | rubric 权重合计=1.0 且事前声明；fused_score 与 ordered_ids 与机械复算一致 |
| A8 | 待复核登记 | 每个 pending 条目与 escalated 冲突都进 pending_review（含 reason+needed_action） |
| A9 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A10 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（纳排一致性 + 排序复算 + 证据回证 + 待复核登记） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **consistency / ranking / evidence / pending 四组** |

实测对照（合成案例 + 注入 4 项污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入漏检（四类） | 0 | 0 | 0 |
| steps_count | 19 | 7 | +12 |
| 污染副本 verdict | FAIL（9 处问题） | PASS（0 处） | −9 |
| 污染副本纳排漏检 | 0 | 2 | +2 |
| 污染副本排序漏检 | 0 | 1 | +1 |
| 污染副本证据漏检 | 0 | 3 | +3 |
| 污染副本待复核漏检 | 0 | 1 | +1 |

**同一校验器、同一污染输入**：正常模式抓全（漏检 0），退化模式 7 处客观违规全部漏掉且
verdict 从 FAIL 翻成 PASS——这是机制增益最直接的证据。数字由探针独立复算违规真值，
与校验层分开实现；详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 检索无结果 / 候选集为空 | items 空、coverage.total=0、verdict=cannot_verify 或 not_screened，绝不补造文献 |
| 摘要/年份/元数据缺失 | missing_metadata 登记 + 置信度降级；关键信息缺失则 pending 并登记待复核 |
| 标注标准互相冲突 | uncertainties.conflicts 登记双方 + 声明采用的优先序 |
| 预印本/重复报道 | duplicate_of + conflicts 登记 merged（保留正式版本）；无法确认则 escalated 进待复核 |
| 大量同分 | 并列组记入 ties，按 tie_break 规则破平，不静默改分 |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与 `problems`
列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：排序会不会换一批候选就不稳定？**
不会静默变。fused_score 是 rubric 事前权重的线性组合，平局按固定规则破（分数→recency→
item_id 字符串序），同输入重复运行顺序逐位一致；并列组全部在 `ranking.ties` 可见。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。SKILL.md 明确
退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：quality/recency 的归一化口径是谁定的？**
本技能在 rubric.normalization 里事前声明（论文/平台未给定时按量级保守设定并写明），
声明后禁止调整；verify_check 核对 weights 合计=1.0 与 declared_at 非空。

**Q：为什么 keep 条目必须有 evidence_quote？**
题面要求"每一条保留、待定、排除的决定能否被他人复核"。没有摘要证据的 keep 会被
verify_check 判 FAIL，这正是防止"标题词面排序"退化的机械闸门。

**Q：pending 是不是偷懒？**
不是——它是题面要求的"不确定项标待复核"。pending 必须写 pending_reason 并登记进
pending_review（含 needed_action），恰恰是把人工注意力集中到真正难判的条目上。

## 11. 适用范围与限制

- 仅处理输入候选集内文献：不做数据库实时检索、不全文精读、不做系统综述纳排全流程。
- quality/recency 归一化口径是本技能设定并事前声明，不冒充外部标准。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘），`ablate` 参数可直接用作别处的"机制开关"对照实验 |
| `scripts/score_rank.py` 的确定性排序 | 权重事前声明 + 固定平局规则 + ties 登记，任何"稳定可解释排序"需求可直接照抄 |
| `rubric` 台账格式 | `{weights, tie_break, normalization, declared_at}` 是通用的"事前口径声明"台账 |
| `pending_review` 登记 | `{item_id, reason, needed_action}` 通用的人工复核入口格式 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改标签即得新的负例 |

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/候选清单/rubric 模板（退出码恒 0） | 是 |
| scripts/score_rank.py | 多因子机械打分 + 确定性排序 + 平局登记 | 是 |
| scripts/verify_check.py | 业务校验器（纳排一致性/排序复算/证据回证/待复核登记） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（6 条虚构文献） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节五条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/ITEM_REQUIRED`
  与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
