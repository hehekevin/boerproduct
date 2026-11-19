# topic-novelty-audit — 科研选题与创新性评估 Skill（v1）

针对 Bohrium 产品赛第 4 期「文献综述」赛道「科研选题与创新性评估」(challenge-041f89c5)
的参赛 Skill。锁定子场景：**候选选题四要素结构化 + 新颖性逐条对照已知工作 + 可行性
要素核查 + 事前口径的创新性分级排序 + 风险与替代路线登记**。

## 1. 用途与适用条件

给定候选选题清单与已知工作清单（真实署名文献/项目 + 可能混入的重复夹具），完成六件事：

1. **选题结构化**：把每条候选选题拆成 `problem / hypothesis / method /
   expected_contribution` 四要素；写不出就登记 `missing_elements[]`，不硬凑。
2. **新颖性逐条对照**：把创新陈述拆条（method/data/scene/theory），**每条**与
   known_works 逐条对照：`closest_work_id` + `overlap`（none/partial/covered/uncertain）
   + 逐字引文 + 位置；covered 的选题标 `not_novel` 并登记 `duplicate_of`；
   **对照不到标 uncertain，绝不写"尚无人研究"**。
3. **可行性要素核查**：data/method/resource/time 四要素各给 `status`
   （sufficient/partial/missing/assumption）+ `basis`；无来源的前提明确标 assumption。
4. **口径事前声明 + 分级排序**：五级 grade_rules（breakthrough/strong/incremental/
   not_novel/uncertain）与三因子权重（novelty/feasibility/evidence，合计=1.0）在**任何
   分级之前**声明；`novelty_rank.py` 机械复算 fused_score 并按平局规则产出稳定排序。
5. **评估回证**：每条已评估选题有 rationale + claims 证据链；novelty_claims 的引文
   与 fused_score 数字可逐字回证（空白归一化后子串匹配），未回证判 FAIL。
6. **登记完备**：grade=uncertain、缺要素、可行性缺口、冲突升级逐条进 `human_review`；
   每条选题登记 `risks[]` 与 `alternatives[]`（确无风险的写明「未识别到」）。

**核心保证**：`verify_check.py` 独立复算每条分数与期望顺序、逐条核对要素覆盖与分级
一致性、把无回证的引文与分数列入 `unbacked_numbers` 判 FAIL；`gain_probe.py` 用
正常 vs 退化双跑实测机制增益并写入 `result.gain_evidence`。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 / 研究生 | 立项、开题前要回答"增量在哪、能不能做成" | 四要素可检验表述 + 分级结论 + 可行性前提逐条来源 |
| 项目申报 / 基金评审辅助 | 多个候选选题要排序并说明理由 | 事前口径的稳定排序 + 逐条对照证据 + 人工复核清单 |
| 复核者 / 导师 | 抽查"凭什么说这个点没人做过" | novelty_claims 逐条 closest_work + 引文定位 + covered 项标重 |
| 教学 / 培训 | 演示"口径事前声明 + 机械复算 + 冲突证据登记"的评估纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不做数据库实时检索、不全文精读、不代写标书；"新颖"仅指输入清单范围内
未见覆盖，外部新颖性不作断言；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 130 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 选题/已知工作清单 + 分级口径模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 声明五级分级口径与权重，然后逐条结构化/对照/可行性核查（见 SKILL.md 七步流程）

# Step 3：机械复算分数并排序（写 result.ranking / fused_score / rank）
python3 /skills/weekly-skill/scripts/novelty_rank.py --result /app/output/result.json --k 5

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

- **输入**：`/input/case.json`（研究方向 + 候选选题 proposals + 已知工作 known_works +
  output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`research_context`、`criteria`、
    `rubric`（grade_rules + 三因子权重）、`proposals[]`（四要素 + novelty_claims +
    feasibility + 分级）、`ranking`、`coverage`、`conflicts`、`human_review`、
    `risks`、`alternatives`、`steps`、`run_status`、`verdict`、`verdict_basis`、
    `gain_evidence`、`efficiency`
- **分级体系**：`novelty_grade` 五级（口径事前声明）× `overlap` 四值（none/partial/
  covered/uncertain）× `feasibility.status` 四值；判定条件见 SKILL.md「Step 2」。
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`（校验报告）、`/app/work/schema_guard.json`
  （结构报告）、`/app/work/gain_evidence.json`（增益对照证据）、`/app/work/rubric.json`
  （分级口径台账）、`/app/work/known_works.json`（对照台账）、
  `/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（选题与文献均虚构）：4 条候选选题 → T01 breakthrough
（fused=0.865 排第 1）、T04 incremental（0.56 第 2）、T02 not_novel（0.51 第 3，
方法被 W02 覆盖标重）、T03 uncertain（0.48 第 4，转人工复核）。示意输出关键片段：

```json
{
  "case_id": "demo-topicaudit-001", "status": "answered",
  "result": {
    "rubric": {"weights": {"novelty": 0.5, "feasibility": 0.3, "evidence": 0.2}},
    "proposals": [{"proposal_id": "T01", "novelty_grade": "breakthrough",
                   "novelty_claims": [{"closest_work_id": "W03", "overlap": "none"}],
                   "fused_score": 0.865, "rank": 1}],
    "ranking": {"ordered_ids": ["T01", "T04", "T02", "T03"]},
    "coverage": {"total_proposals": 4, "judged": 4, "novelty_covered": 1},
    "verdict": "assessed"
  },
  "claims": [{"claim_id": "c-01", "source_id": "T01",
              "evidence": [{"paragraph_id": "known_works[W03].abstract",
                            "quote": "Our method operates post-hoc on completed projects and does not provide any early-warning mechanism during project selection."}]}]
}
```

本地自测整条链路（合成案例，非正式答案；实测 2026-11-19 全部 exit 0 且 verdict=PASS）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/novelty_rank.py --result examples/example-result.json --k 3 --dry-run
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
| A5 | 全记录覆盖 | coverage.total_proposals == proposals 条数，每条 judged=true 或有 pending_reason |
| A6 | 要素覆盖 | 四要素非空或登记 missing_elements；可行性四要素各有 status+basis |
| A7 | 对照有据 | 每条 novelty_claim 有 closest_work_id + 引文在 claims 逐字回证；covered ⇒ not_novel + duplicate_of |
| A8 | 口径事前 | rubric 权重合计=1.0、grade_rules 逐级声明、declared_at 非空；分级与声明一致 |
| A9 | 登记完备 | uncertain/缺要素/可行性缺口/冲突升级逐条进 human_review；risks/alternatives 登记 |
| A10 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A11 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（要素覆盖 + 口径与复算 + 评估回证 + 登记完备） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **structure / scoring / evidence / review 四组** |

实测对照（合成案例 + 注入 5 项污染的副本，2026-11-19 实跑，Python 3.13.14 / Windows）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入漏检（四类） | 0 | 0 | 0 |
| 干净输入 steps_count | 58 | 7 | +51 |
| 污染副本 verdict | FAIL（13 处问题） | FAIL（仅剩 1 处 coverage） | −12 |
| 污染副本要素漏检 | 0 | 1 | +1 |
| 污染副本口径/分级漏检 | 0 | 1 | +1 |
| 污染副本回证漏检 | 0 | 4 | +4 |
| 污染副本登记漏项 | 0 | 3 | +3 |

**同一校验器、同一污染输入**：正常模式抓全（四类漏检 0/0/0/0，caught_by_normal_mode=
true），退化模式 9 处客观违规漏掉 8 处、只剩一条常开 coverage 检查兜底——这是
"同一校验器双跑 FAIL 差"最直接的机制增益证据。数字由探针独立复算违规真值，与校验
层分开实现；详见 `mechanism_to_metric_map`。

注入的 5 项污染：清空 T01 的 method 要素且不登记；T01 首条创新陈述改 covered、清空
引文并标 breakthrough；清空 rubric.declared_at；清空 human_review；清空 claims。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 已知工作清单缺失 / 对照不到 | novelty_claims 标 uncertain、分级 uncertain、登记 human_review，绝不写"尚无人研究" |
| 选题要素写不出 | missing_elements 登记具体缺项 + 置信度降级 + human_review，不硬凑 |
| 可行性前提无来源 | status=assumption 且 basis 写明"假设"，登记 human_review；结论改 conditional |
| 证据互相冲突 | uncertainties.conflicts 登记双方 + 声明采用的优先序 |
| 选题重复 / 与已知工作重复 | duplicate_of + conflicts 登记 flagged（标 not_novel）；无法确认则 escalated 进 human_review |
| 大量同分 | 并列组记入 ties，按 tie_break 规则破平，不静默改分 |
| 算力/时间不足或运行中断 | 保留已评估部分，status=partial，changelog 注明截断/中断位置 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与 `problems`
列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q："新颖"到底指什么？**
只指"在输入 known_works 清单范围内未见覆盖"。清单外是否有人做过不可知，一律标
uncertain 转人工复核——这正是防止把"检索不到"说成"尚无人研究"的机械闸门。

**Q：排序会不会换一批选题就不稳定？**
不会静默变。fused_score 是 rubric 事前权重的线性组合，平局按固定规则破（分数→novelty
因子→proposal_id 字符串序），同输入重复运行顺序逐位一致；并列组全部在 `ranking.ties` 可见。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。SKILL.md 明确
退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：feasibility 的 assumption 是不是偷懒？**
不是。题面要求"可行性前提有来源或被明确标为假设"。assumption 必须写明假设内容、
登记 human_review，并把可行性结论压到 conditional——把人工注意力集中到真正缺前提的选题上。

**Q：为什么 covered 必须降级 not_novel 并登记 duplicate_of？**
题面要求"创新点与最近的工作逐条划清边界、重复项标出"。分级与对照结论矛盾会被
verify_check 的 grade_consistency 机械判 FAIL，防止"明知撞车还报突破"。

## 11. 适用范围与限制

- 仅对照输入 known_works 清单内的工作：不做实时检索、不全文精读；"新颖"不作外部断言。
- 三因子与五级分级口径是本技能在 rubric 事前声明并写明，不冒充外部标准。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘），`ablate` 参数可直接用作别处的"机制开关"对照实验 |
| `scripts/novelty_rank.py` 的确定性排序 | 权重事前声明 + 固定平局规则 + ties 登记，任何"稳定可解释排序"需求可直接照抄 |
| `rubric` 台账格式 | `{grade_rules, weights, tie_break, normalization, declared_at}` 是通用的"事前口径声明"台账 |
| `human_review` 登记 | `{proposal_id, reason, needed_action}` 通用的人工复核入口格式 |
| novelty_claims 对照格式 | `{claim_id, kind, closest_work_id, overlap, evidence_quote, evidence_location}` 通用的"逐条划界"结构 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改标签即得新的负例 |

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明，150 行） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/选题与已知工作清单/rubric 模板（退出码恒 0） | 是 |
| scripts/novelty_rank.py | 三因子机械打分 + 确定性排序 + 平局登记 | 是 |
| scripts/verify_check.py | 业务校验器（要素覆盖/口径与复算/评估回证/登记完备四组） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（4 条虚构选题 + 5 条虚构已知工作） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节五条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/PROPOSAL_REQUIRED`
  与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
