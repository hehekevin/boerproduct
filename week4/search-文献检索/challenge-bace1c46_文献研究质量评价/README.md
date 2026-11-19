# lit-quality-appraise — 文献研究质量评价 Skill（v1）

针对 Bohrium 第 4 期 challenge-bace1c46「文献研究质量评价」的参赛 Skill。
锁定子场景：**量表驱动的逐条方法学质量评价 + 逐字证据锚定 + 分级机械复算 +
设计缺陷/报告不全区分 + 弃权登记**。

## 1. 用途与适用条件

给定若干篇文献（含全文/摘要的分节文本），完成五件事：

1. **清单逐条评价**：每篇文献按事前量表（design / sample / control / blinding /
   statistics / other 六维度，可按文献类型裁剪）逐条判定
   `adequate / concerns / inadequate / unreported / not_applicable / unassessable`，
   缺一个维度即被校验器判 FAIL。
2. **证据锚定**：每条判断给逐字引文（evidence_quote）+ 定位（doc_id#章节）；
   校验器做双闸回证——既要在 claims 证据链中逐字命中，也要在 case.json 实际
   来源文本中逐字存在，转述/编造即 FAIL（unbacked_evidence）。
3. **分级口径一致**：grade 与 category 必须由 judgment 经**事前声明**的
   grade_map / category_map 机械导出（声明后禁止调整），杜绝「同一篇文献两个人
   分级对不上」的口径漂移。
4. **缺陷与报告不全区分**：inadequate ⇒ design_flaw（设计缺陷），
   unreported ⇒ reporting_gap（报告不全），两者不得互换——这是本Skill 与
   "整体评价式"基础 Agent 的核心能力差异之一。
5. **分级汇总与弃权**：grade_rollup.py 按事前 penalty_map / thresholds /
   abstain_rule / direction_rule 机械复算每篇 penalty_total、risk_of_bias
   （low / medium / high / uncertain）与偏倚方向；证据不足的条目按弃权规则
   abstain（uncertain，不罚分）并登记 pending_review，绝不补一个"看起来合理"的判断。

**核心保证**：`verify_check.py` 独立复算分级映射与汇总、逐条回证引文；
`gain_probe.py` 用正常 vs 退化双跑实测机制增益并写入 result.gain_evidence。
评分器不开附件即可通过 `self_check / gates / unbacked_numbers / unbacked_evidence /
validator_verdict` 五键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 研究者 / 系统综述作者 | 拿到一篇文献要判断设计是否支持结论、偏倚落在哪个环节 | 六维度逐条评价表 + 逐字证据定位 + 可复算的风险等级 |
| 期刊编辑 / 初筛 | 快速识别报告缺项与设计缺陷的差别 | design_flaw 与 reporting_gap 逐条区分的清单 |
| 复核者 | 按记录独立复核每条判断是否可回溯 | claims 证据链 + unbacked_* 空表 + 机械复算一致的汇总 |
| 教学 / 培训 | 演示"事前声明口径 + 机械导出分级 + 敢于弃权"的评价纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不做同行评审、事实核验、临床/政策决策；不做数据库检索与全文下载；
缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 上实测通过），只用标准库 |
| 第三方依赖 | **零**（json / os / re / sys / argparse / copy / time / math） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化） |
| 磁盘 | 整包 < 100 KB |
| 资源上限 | 平台契约：≤50 个 UTF-8 文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定
`/skills/weekly-skill`），无需安装步骤、无依赖解析、无需联网。脚本自带定位标志
校验（与 SKILL.md 同包才报 marker_hit=True）。

```bash
# Step 0：自动落骨架 + 文献清单 + 分级口径模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 声明量表与 grading_rules，然后逐条评价（见 SKILL.md 七步流程）

# Step 3：机械复算每篇 penalty/risk/direction（写 result.risk_summary）
python3 /skills/weekly-skill/scripts/grade_rollup.py --result /app/output/result.json

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

- **输入**：`/input/case.json`（文献分节文本 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `unbacked_evidence` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`review_scope`、`checklist`、
    `grading_rules`、`papers[]`（每篇含 appraisals[] 逐条评价）、`risk_summary`、
    `coverage`、`pending_review`、`steps`、`run_status`、`verdict`、`verdict_basis`、
    `gain_evidence`、`efficiency`
  - 判定体系：`judgment`（六枚举）→ `grade`（high/medium/low/uncertain）×
    `category`（design_flaw / reporting_gap / none）× `bias_direction`
    （favors/against/unclear）；映射与阈值全部在 grading_rules 事前声明。
- **键归属（多脚本禁写同一键）**：risk_summary ← grade_rollup.py；
  self_check/gates/unbacked_*/validator_verdict ← verify_check.py；
  gain_evidence/efficiency ← gain_probe.py；其余 ← build_skeleton.py + Agent。
- **工作区产物**：/app/work/{verify_check.json, schema_guard.json,
  grading_rules.json, gain_evidence.json, gain_probe_polluted.json}。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（标题摘要均为虚构）：2 篇文献 × 6 维度 = 12 条评价。
示意结论：Q01 penalty=5 → risk=high（direction=against_conclusion，含 1 处
设计缺陷 inadequate + 1 处报告不全 unreported）；Q02 penalty=1 但 1 条弃权 →
risk=uncertain（direction=unclear）。关键片段：

```json
{
  "case_id": "demo-quality-001", "status": "answered",
  "result": {
    "papers": [{"paper_id": "Q01", "appraisals": [
      {"checklist_id": "ST-01", "judgment": "inadequate", "grade": "low", "category": "design_flaw",
       "evidence_quote": "两组差异采用t检验，未报告置信区间与效应量", "evidence_location": "doc-q01#methods"}]}],
    "risk_summary": {"per_paper": [{"paper_id": "Q01", "penalty_total": 5, "risk_of_bias": "high",
                                    "direction": "against_conclusion"}]},
    "verdict": "appraised"
  }
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/grade_rollup.py --result examples/example-result.json --rules /tmp/wk/grading_rules.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --rubric /tmp/wk/grading_rules.json --out /tmp/vc.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/sg.json
```

## 7. 最小自检清单（2026-11-19 实测，全部退出码 0）

| 编号 | 自检项 | 实测结果 |
|------|--------|---------|
| C1 | build_skeleton 落骨架（marker 命中、2 篇文献提取） | exit 0，marker_hit=True |
| C2 | grade_rollup 机械复算（Q01 penalty=5→high / Q02 penalty=1+弃权→uncertain） | exit 0，risk_summary 回写 |
| C3 | gain_probe 双模式对照（干净输入正常=退化=0 漏检，steps_count 59 vs 18，delta=41） | exit 0 |
| C4 | gain_probe 污染反例（注入 7 项：正常模式 21 处全抓、漏检 0；退化模式漏检 13） | exit 0，caught_by_normal_mode=True |
| C5 | verify_check 业务校验（53 条检查项） | exit 0，verdict=PASS |
| C6 | schema_guard 结构守卫（output_contract + 业务 schema 全字段） | exit 0，verdict=PASS |
| C7 | examples 标注为示意（标题摘要虚构，非正式答案） | 已标注 |
| C8 | SKILL.md ≤150 行 / 脚本 5 个 / 全包 10 文件 / 零第三方依赖 | 141 行 / 5 / 10 / stdlib-only |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍（违规真值由探针独立复算，
与校验层分开实现）：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（清单覆盖 + 分级一致 + 证据回证 + 缺陷区分 + 弃权登记） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **coverage / grading / evidence / defect / pending 五组** |

实测对照（合成案例 + 注入 7 项污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入漏检（五类） | 0 | 0 | 0 |
| steps_count（已执行检查项+流程步） | 59 | 18 | +41 |
| 污染副本 verdict | FAIL（21 处） | FAIL（仅剩 1 处通用结构问题） | −20 |
| 污染副本清单覆盖漏检 | 0 | 1 | +1 |
| 污染副本分级口径漏检 | 0 | 2 | +2 |
| 污染副本证据回证漏检 | 0 | 8 | +8 |
| 污染副本缺陷区分漏检 | 0 | 1 | +1 |
| 污染副本弃权登记漏检 | 0 | 1 | +1 |

**同一校验器、同一污染输入**：正常模式漏检 0，退化模式漏掉 13 处客观违规且只剩
一条通用结构问题可看——机制增益最直接的证据。数字全部来自实跑，详见
`gain_evidence.mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 全文不可得 / 仅有摘要 | material_gaps 登记，评价范围如实缩小，绝不补造 |
| 关键证据缺失 | unassessable + abstain_reason + 登记 pending_review，弃权不罚分 |
| 图表不可解析 | evidence_location 注明不可解析与原因，按可用文本评价 |
| 维度不适用 | not_applicable + na_reason，grade 置 null，不参与罚分 |
| 语言/预印本特殊 | paper_type 如实标注，量表按类型裁剪并在 review_scope 写明 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 verdict 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict` 与 `problems`，Agent
读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：分级会不会换一个人就对不上？**
grade 与 category 不是自由发挥——必须等于 grade_map[judgment] 与
category_map[judgment] 的导出值，汇总等级由 penalty_map/thresholds 机械复算。
口径在任何复算前声明并落台账，声明后禁止调整；verify_check 独立复算比对。

**Q：为什么"未报告"不算设计缺陷？**
设计缺陷（inadequate → design_flaw）说明方法本身有问题；报告不全（unreported →
reporting_gap）只说明作者没写，设计可能没问题。两者混报会让改进建议失去指向，
校验器对互换判 FAIL。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它量化"关闭这些机制会漏掉多少"。SKILL.md
明确退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：弃权是不是偷懒？**
不是——弃权（unassessable）是题面要求的"不可评价要明确说明"。弃权必须写
abstain_reason 并登记 pending_review（含 needed_action），且不参与罚分，
恰恰是把人工注意力集中到真正缺证据的条目上。

**Q：引文可以被转述吗？**
不可以。每条引文要做双闸回证：claims 证据链逐字命中 + case.json 来源文本逐字
存在（空白归一化后子串匹配），转述或编造进 unbacked_evidence 判 FAIL。

## 11. 生态贡献十项（可复用资源）

1. **量表定义**：六维度 checklist（checklist_id + domain + prompt），JSON 直接复用或按文献类型裁剪。
2. **分级口径台账**：grade_map / category_map / penalty_map / thresholds / abstain_rule / direction_rule 的声明格式，通用于任何"口径先行"场景。
3. **证据定位模板**：`{evidence_quote, evidence_location: doc_id#章节}` + claims 证据链双闸回证格式。
4. **校验器 `analyze()` API**：verify_check.py 纯函数式（不写盘），ablate 参数可直接用作别处的机制开关对照。
5. **机械汇总复算 `rollup()`**：罚分→分档→弃权规则→方向判定的确定性管线，任何风险分级需求可照抄。
6. **三元组自检格式**：`{item, template_value, applied, match}` + 闸门四态（enforced/skipped_not_provided/not_found/invalid）。
7. **增益对照探针**：正常 vs 退化双跑 + 污染反例注入，可移植到任何校验型 Skill。
8. **合成示例 fixture**：examples/ 全部标注示意，复制改标签即得新的负例。
9. **失败经验沉淀**：worklog.md 记录真实对照数字与诚实边界（见第 12 节）。
10. **键归属纪律**：多脚本分键写入、互不覆盖的约定，可直接套用到多脚本 Skill 包。

## 12. 已知限制与诚实边界

- 量表与分级口径是本技能事前声明的设定，不冒充 Cochrane/JBI 等外部标准；题面
  未给定时按保守量级设定并写明。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照；追问轮次按每轮 3 条
  折算是估计量。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。
- 汇总复算依赖来源文本在 case.json 中可读；全文仅以图片形式提供时证据回证降级为
  claims 链回证并在 material_gaps 登记。

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/文献清单/口径模板（退出码恒 0） | 是 |
| scripts/grade_rollup.py | 分级机械复算 + risk_summary 回写（仅写此键） | 是（含 rollup()） |
| scripts/verify_check.py | 业务校验器（覆盖/分级/证据/缺陷/弃权五组） | 是（含 analyze() API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（2 篇虚构文献） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节五条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 REQUIRED 常量与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
