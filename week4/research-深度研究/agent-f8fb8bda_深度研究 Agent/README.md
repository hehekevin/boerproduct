# deep-research-loop — 深度研究证据综合 Skill（v1）

针对 Bohrium 产品赛第 4 周「深度研究 Agent」赛道 (agent-f8fb8bda) 的参赛 Skill。
锁定子场景：**研究计划事前拆解 + 逐轮检索-综合-缺口迭代留痕 + 带强度标注的证据综合 +
分歧观点并陈 + 未决问题登记**。

## 1. 用途与适用条件

给定研究问题与研究来源集合（真实署名文献/记录，可能混入冲突夹具），完成六件事：

1. **计划事前声明**：把研究问题拆成可独立检索的子问题（`sq_id + 依赖 DAG + 证据需求 +
   检索式 + 停止规则`），并声明收敛判据；**在任何检索迭代之前**写定并通过 `plan_audit.py`
   审计（sha256 指纹锁定），声明后禁止调整——防止事后改计划凑结果。
2. **逐轮迭代留痕**：每轮检索-综合-缺口循环向 `iterations[]` 追加一条（round_id 顺序编号、
   queries_run / sources_found / synthesis_note / gaps_found / artifacts_ref 缺一不可），
   整条路径可被他人按记录复跑。
3. **带强度标注的证据综合**：每条结论标 `kind`（material_fact/inference/uncertain）×
   `strength`（strong=≥2 个独立带引文来源方向一致 / moderate=1 个 / weak / unverified=无来源），
   并在 `claims[]` 证据链中逐字回证全部引文（空白归一化后子串匹配）。
4. **分歧观点并陈**：冲突研究结论双方各带 claim+source_ids 进 `divergent_views[]`，
   不做静默取舍；unresolved 的必须登记进 open_questions。
5. **未决问题登记**：无中等及以上强度结论的子问题逐条登记 `open_questions[]`
   （含 reason——必须指向具体检索缺口 gaps_found——与可执行的 needed_action）。
6. **机械自检**：`verify_check.py` 独立复算覆盖面/强度汇总、核对计划一致性、迭代留痕、
   结论-证据对齐与登记完整性；`gain_probe.py` 正常 vs 退化双跑实测机制增益。

**核心保证**：`verify_check.py` 用四组消融开关（plan/trace/evidence/registry）做机械校验，
把无回证引文列入 `unbacked_numbers` 判 FAIL；`gain_probe.py` 用同一校验器双跑 +
污染反例副本自测，把真实对照数字写进 `result.gain_evidence`。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 / 研究助理 | 交一段多步研究任务，要 Agent 拆解、检索、综合并给有边界的结论 | 事前锁定的计划 + 逐轮留痕 + 强度标注的结论 |
| 综述撰写者 | 证据互相冲突时不想被"尚存争议"一句话糊弄 | divergent_views 双方并陈（各带来源）+ 未决问题登记 |
| 复核者 | 抽查"这个结论是从哪一步来的" | finding → sources → iterations.sources_found → claims 全链可回放 |
| 教学 / 培训 | 演示"计划先锁定 + 证据回链 + 漏检对照"的研究纪律 | 可复算的对照实验（gain_evidence + 污染反例） |

**不适用**：不做数据库实时检索接入、不全文精读、不做元数据方法学审查；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13.14 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math` / `hashlib`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 100 KB |
| 资源上限 | 平台契约：≤50 个 UTF-8 文本文件、单文件 ≤500 KB、总计 ≤2 MB、无符号链接 |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：落骨架 + 子问题/来源清单 + 计划模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1：Agent 事前声明研究计划（子问题/依赖/证据需求/检索式/收敛判据），然后审计
python3 /skills/weekly-skill/scripts/plan_audit.py --result /app/output/result.json --work-dir /app/work

# Step 2-3：Agent 逐轮迭代（R1..Rn 留痕）+ 结论/分歧/未决问题（见 SKILL.md 八步流程）

# Step 4：覆盖面与强度机械汇总（写 result.coverage / strength_summary）
python3 /skills/weekly-skill/scripts/coverage_calc.py --result /app/output/result.json --work-dir /app/work

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

- **输入**：`/input/case.json`（研究问题 + 材料/来源 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`research_question`、`plan`（事前声明）、
    `iterations[]`（逐轮留痕）、`findings[]`（强度标注结论）、`divergent_views[]`（分歧并陈）、
    `open_questions[]`（未决登记）、`coverage`、`strength_summary`、`plan_audit`、`steps`、
    `run_status`、`verdict`、`verdict_basis`、`gain_evidence`、`efficiency`
- **强度体系**：`kind`（material_fact/inference/uncertain）× `strength`
  （strong/moderate/weak/unverified）；判级条件与边界约定见 SKILL.md「Step 3」。
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`（业务校验报告）、`/app/work/schema_guard.json`
  （结构报告）、`/app/work/gain_evidence.json`（增益对照证据）、`/app/work/plan_ledger.json`
  （计划台账）、`/app/work/coverage_ledger.json`（覆盖面台账）、
  `/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（研究问题与来源均为虚构）：3 个子问题（依赖 SQ-02→SQ-01、
SQ-03→SQ-02）→ 3 轮迭代留痕 → 4 条结论（F1 strong 双来源、F2 moderate、F3 weak 冲突
并陈、F4 inference）→ 1 组分歧并陈（V1 unresolved）→ 1 条未决问题（OQ-01）。
示意输出关键片段：

```json
{
  "case_id": "demo-deepresearch-001", "status": "answered",
  "result": {
    "plan": {"declared_at": "step1（…声明后禁止调整）", "sub_questions": ["SQ-01","SQ-02","SQ-03"]},
    "iterations": [{"round_id": "R1", "queries_run": ["caffeine acute working memory RCT"], "sources_found": ["S01","S02"]}],
    "findings": [{"finding_id": "F1", "kind": "material_fact", "strength": "strong",
                  "sources": [{"source_id": "S01", "quote": "Participants receiving 200 mg caffeine…"}]}],
    "divergent_views": [{"topic_id": "V1", "handling": "unresolved", "open_question_ref": "OQ-01"}],
    "coverage": {"sub_questions_total": 3, "answered": 2, "partially_answered": 1},
    "verdict": "partially_synthesized"
  },
  "claims": [{"claim_id": "c-01", "source_id": "F1",
              "evidence": [{"paragraph_id": "sources[0].content", "quote": "Participants receiving 200 mg caffeine…"}]}]
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/plan_audit.py --result examples/example-result.json --work-dir /tmp/wk
python3 scripts/coverage_calc.py --result examples/example-result.json --work-dir /tmp/wk
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/sg.json
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 引文全回证 | `unbacked_numbers` 为空数组 |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 计划全覆盖 | 每个子问题有 finding（判定）或 open_questions 登记；coverage/强度汇总与实际一致 |
| A6 | 计划可锁定 | plan 事前声明 + plan_audit state=declared；依赖成 DAG；子问题引用不越界 |
| A7 | 轮次可回放 | iterations 按 R1..Rn 留痕齐全；结论来源 ⊆ 各轮 sources_found；末轮收敛记录 |
| A8 | 结论-证据对齐 | strength 与带引文来源数匹配；全部引文在 claims 逐字回证 |
| A9 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A10 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（计划声明 + 迭代留痕 + 证据对齐 + 未决登记） | — |
| `degraded` | 枚举/结构/coverage 与 strength 汇总/verdict 一致性 | **plan / trace / evidence / registry 四组** |

实测对照（合成案例 + 注入 5 项污染的副本，2026-11-19 实跑，Python 3.13.14）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入四类漏检 | 0 | 0 | 0 |
| steps_count | 44 | 8 | +36 |
| 污染副本 verdict | FAIL（10 处问题） | PASS（0 处） | −10 |
| 污染副本计划漏检 | 0 | 1 | +1 |
| 污染副本留痕漏检 | 0 | 1 | +1 |
| 污染副本证据漏检 | 0 | 7 | +7 |
| 污染副本未决漏登记 | 0 | 2 | +2 |

**同一校验器、同一污染输入**：正常模式抓全（10 处问题，漏检 0），退化模式 11 处客观违规
全部漏掉且 verdict 从 FAIL 翻成 PASS——这是机制增益最直接的证据。数字由探针独立复算
违规真值，与校验层分开实现；详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 检索无结果 / 来源集合为空 | findings 空、coverage.total=0、verdict=cannot_verify 或 not_synthesized，绝不补造来源 |
| 来源互相冲突 | 双方并陈进 divergent_views；unresolved 登记进 open_questions，不取一方 |
| 计划与材料对不上 | 不改已锁定计划：执行可执行部分，缺口登记 open_questions + material_gaps |
| 工具报错/限流/解析失败 | 该轮 status=failed_with_record；连续失败 next_action=blocked 并人工接管 |
| 强度无法定级 | 按下限标 weak/unverified，never 高估；unverified 必须 sources=[] |
| 算力/时间不足 | 保留已完成轮次，status=partial，末轮 next_action=budget_stop |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与 `problems`
列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：计划声明后还能改吗？**
不能。plan 在任何检索迭代之前写定并通过 plan_audit（sha256 指纹锁进 /app/work/plan_ledger.json），
声明后禁止调整——这是防"事后改计划凑结果"的机械闸门。材料对不上计划时照实登记缺口，不改计划。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。SKILL.md 明确
退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：strength=strong 的"方向一致"谁说了算？**
方向一致性由 Agent 依据来源内容判定并写进 confidence_basis；校验器机械核对的是可测部分：
strong 必须有 ≥2 个同时带 quote+location 的来源、引文必须逐字回证。冲突来源不允许标 strong。

**Q：为什么 unverified 结论必须 sources=[]？**
"unverified"的含义就是"无来源支撑"。带着来源却标 unverified 会被判"强度标注矛盾"；
反之 material_fact 不带来源会被判"材料事实必须回链来源"。双向核对防两头钻空子。

**Q：open_questions 是不是偷懒？**
不是——它是题面要求的"研究空白与无法确定项登记"。登记必须写明 reason（指向具体检索缺口
gaps_found）与可执行的 needed_action，恰恰是把人工注意力集中到真正的证据边界上。

## 11. 适用范围与限制

- 仅处理输入来源集合内材料：不做数据库实时检索、不全文精读、不做元数据方法学审查。
- strength 判级口径是本技能事前设定的机械规则，不冒充外部标准；方向一致性由 Agent 判定。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘），`ablate` 参数可直接用作别处的"机制开关"对照实验 |
| `scripts/plan_audit.py` 的声明-指纹-台账模式 | "事前声明 + sha256 锁定 + 台账落盘"适用于任何"口径先行"场景 |
| `scripts/coverage_calc.py` 的机械汇总 | 按状态机汇总 + 独立复算对照，任何覆盖面统计需求可直接照抄 |
| `open_questions` 登记 | `{oq_id, question, related_sq_ids, reason, needed_action}` 通用的人工复核入口格式 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改标签/清字段即得新的负例 |

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 八步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/子问题/来源清单/计划模板（退出码恒 0） | 是 |
| scripts/plan_audit.py | Step 1 计划事前声明审计 + sha256 指纹台账 | 是 |
| scripts/coverage_calc.py | Step 4 覆盖面/强度机械汇总 | 是 |
| scripts/verify_check.py | 业务校验器（plan/trace/evidence/registry 四组消融校验） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（3 子问题 + 6 条虚构来源） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节六条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/FINDING_REQUIRED/
  SQ_REQUIRED/ITER_REQUIRED` 与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
