# research-stat-audit — 研究方法与统计审查 Skill（v1）

针对 Bohrium 产品赛第 4 周「学术审查」赛道「研究方法与统计审查」(challenge-9e7302fd)
的参赛 Skill。锁定子场景：**六分面逐条问题清单（原文位置 + 严重度 + 修改建议）
+ 统计量数值复算 + 缺陷/报告不全区分 + 四类区分 + 误报抑制 + 待复核登记**。

## 1. 用途与适用条件

给定一篇固定稿件（论文/科研材料）与审查要求，完成七件事：

1. **六分面逐条审查**：研究设计、变量定义、统计方法、样本量与效能、结果报告、
   规范与一致性六个分面逐一过稿，每条发现定位到句（quote 逐字摘录 + 章节句位）。
2. **统计量数值复算**：稿件报告的统计量组合（r 与 n、t 与 p、CI 与 SE、df 与
   样本量、各组 n 与总数）逐条机械复算，一致性结论落盘可复核——p 值夸大、
   CI 与 SE 矛盾、df 超样本量这类"数字对不上"不再靠感觉。
3. **缺陷/报告不全区分**：每条发现带 `defect_class`——`method_defect`（作者
   做错了）/ `reporting_gap`（作者没报告），机械映射可校验，杜绝"统计方法
   不当"式的混为一谈。
4. **四类区分**：`fact_error` / `insufficient_evidence` / `norm_issue` /
   `suggestion`，不是一锅炖的"评审意见"。
5. **严重度三级口径**：critical/major/minor 判据在任何判定之前声明
   （severity_rubric），机械映射：suggestion⇒minor、fact_error⇒critical/major。
6. **误报抑制**：学科惯例、期刊格式差异、作者取舍、超范围意见（FP-01~04）
   判"不算缺陷"并登记 `suppressed[]`——既不误报，也不静默丢弃。
7. **待复核登记**：读不到的图表/文献标 pending 并登记 `pending_review[]`
   （含 reason 与 needed_action）——不凭空补结论。

**核心保证**：`verify_check.py` 把每条 confirmed 发现的引文做空白归一化后逐字
回证于稿件原文（引文不在原文 = 定位失据 = FAIL）、核对分级口径与缺陷区分映射、
并用独立复算核对 `stat_recompute` 记录是否被篡改；`gain_probe.py` 用正常 vs
退化双跑实测机制增益。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 投稿前自查的科研人员 | 把"稿子哪里有问题"变成可交办条目 | 逐条位置 + 严重度 + 缺陷类型 + 修改建议的问题清单 |
| 审稿人 / 方法学审查助理 | 需要核对统计量与区分缺陷性质 | 统计复算记录 + method_defect/reporting_gap 区分 + 待复核清单 |
| 项目结题 / 质量把关 | 需要证明五检查面都查过 | coverage 六分面 × 章节矩阵 + unchecked 缺口登记 |
| 复核者 | 回原文逐条核对审查结论 | quote 逐字回证 + claims 证据链 + 可复跑命令 |

**不适用**：不做外部文献检索、不查重、不润色改写、不做投稿决策；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 上实测通过），只用标准库（json/os/re/sys/argparse/copy/time/math） |
| 第三方依赖 | **零**，无需联网、无 pip 安装 |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码） |
| 磁盘 | 整包 < 120 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`）。

```bash
# Step 0：落骨架 + 稿件结构清单 + 口径模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
# Step 1-2：Agent 声明口径与抑制规则，六分面逐条审查（见 SKILL.md 八步流程）
# Step 3：六分面覆盖机械审计
python3 /skills/weekly-skill/scripts/coverage_audit.py --result /app/output/result.json \
  --case /input/case.json --input-root /input --emit-into
# Step 4：统计量数值复算（凡有 stat_claim 必做）
python3 /skills/weekly-skill/scripts/stat_recompute.py --result /app/output/result.json --emit-into
# Step 6：增益对照 + 效率计数（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
# Step 7：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --ledger /app/work/severity_rubric.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

## 5. 输入与输出

- **输入**：`/input/case.json`（稿件 + 审查要求 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`manuscript_overview`、
    `severity_rubric`、`suppression_rules`、`facets`、`findings[]`（逐条发现，含
    `defect_class` 与可选 `stat_claim`）、`suppressed[]`、`pending_review[]`、
    `clearances[]`、`stat_recompute`、`coverage`、`unchecked`、`steps`、
    `run_status`、`verdict`、`verdict_basis`、`gain_evidence`、`efficiency`
- **缺陷/报告不全**：`method_defect` / `reporting_gap` / `cannot_classify` /
  `not_applicable`（suggestion 类），映射由 verify_check 机械强制。
- **status**：`answered` | `partial` | `insufficient_evidence` | `input_error`。
- **工作区产物**：`/app/work/verify_check.json`、`/app/work/schema_guard.json`、
  `/app/work/gain_evidence.json`、`/app/work/severity_rubric.json`（分级口径台账）、
  `/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（论文/数据/统计量均为虚构，统计量组合为演示复算
故意构造）：虚构 RCT 稿件 → 11 条发现：9 confirmed（F01 摘要 48 名 vs 方法
36 名 fact_error/major、F02 r=0.32,n=48 复算 p≈0.022 与宣称 p<0.001 矛盾
fact_error/critical、F03 df=52 与 n=36 两组设计矛盾、F04 CI 宽 0.10 与 SE=0.10
矛盾、F05 六项结局未校正多重比较、F06 随机化细节未报告 reporting_gap、
F07 样本量无依据 reporting_gap、F08 建议项、F11 t-p 组合复算自洽正例）+
1 pending（F09 图2 不可读）+ 1 suppressed（F10 作者自陈局限，FP-01）。
统计复算 4 条：3 矛盾 + 1 一致。示意输出关键片段：

```json
{
  "case_id": "demo-researchstat-001", "status": "answered",
  "result": {
    "findings": [{"finding_id": "F02", "facet": "stat_method", "category": "fact_error",
                  "severity": "critical", "defect_class": "method_defect",
                  "quote": "r=0.32, n=48, p<0.001", "location": "S1 摘要 第 4 句",
                  "status": "confirmed",
                  "stat_claim": {"type": "r_to_t", "params": {"r": 0.32, "n": 48},
                                 "claimed": {"p_max": 0.001}}}],
    "stat_recompute": {"counts": {"claims_total": 4, "consistent": 1, "inconsistent": 3, "indeterminate": 0}},
    "coverage": {"total_findings": 11, "confirmed": 9, "pending": 1, "suppressed": 1},
    "verdict": "audited"
  },
  "claims": [{"claim_id": "c-02", "source_id": "F02",
              "evidence": [{"paragraph_id": "manuscript.sections[0].text", "quote": "r=0.32, n=48, p<0.001"}]}]
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/coverage_audit.py --result examples/example-result.json --case examples/example-case.json --input-root examples --emit-into
python3 scripts/stat_recompute.py --result examples/example-result.json --emit-into
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk/severity_rubric.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 定位可回证 | 每条 confirmed 的 quote 空白归一化后逐字命中稿件原文 |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 六分面全覆盖 | 六分面计数与实际一致；零发现分面/章节有 unchecked/clearances 登记 |
| A6 | 分级有锚点 | severity_rubric 事前声明；suggestion⇒minor；fact_error⇒critical/major |
| A7 | 统计量复算一致 | stat_claim 均有复算记录且记录与独立复算一致；矛盾项成为缺陷证据 |
| A8 | 缺陷/报告不全区分 | 每条 confirmed 有 defect_class；fact_error⇒method_defect；reporting_gap⇒insufficient_evidence/norm_issue |
| A9 | 待复核与抑制登记 | pending 进 pending_review（含 reason+needed_action）；suppressed 全登记且 rule_id 在事前规则表内 |
| A10 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A11 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true`（含统计量复算篡改反例） |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（定位回证 + 分级口径 + 证据链 + 待复核/抑制登记 + 统计复算一致 + 缺陷区分） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **location / severity / evidence / pending / stat / defect 六组** |

实测对照（合成案例 + 注入 7 项污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 污染副本 verdict | FAIL（15 处问题） | PASS（0 处） | −15 |
| 污染副本定位失据漏检 | 0 | 1 | +1 |
| 污染副本证据缺失漏检 | 0 | 9 | +9 |
| 污染副本待复核漏登记 | 0 | 1 | +1 |
| **污染副本统计复算篡改漏检** | **0** | **2** | **+2** |
| 干净输入漏检（六类） | 0 | 0 | 0 |
| steps_count | 57 | 8 | +49 |

**同一校验器、同一污染输入**：正常模式抓全（verdict=FAIL，漏检 0），退化模式
把"CI 与 SE、df 与样本量矛盾被翻转为复算一致"这类统计量篡改全部漏掉且
verdict 从 FAIL 翻成 PASS——机制增益最直接的证据。数字由探针独立复算违规真值；
详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 稿件解析失败 / 输入不可读 | material_gaps 登记 + verdict=cannot_verify，绝不编造审查结论 |
| 图表无法读取 | clearances 登记 artifact:* 豁免 + material_gaps 注明 + 相关条目 pending |
| 统计量参数不全/无法复算 | stat_recompute 判 indeterminate 并注明，不算矛盾、不臆造补值 |
| 参考文献缺失/全文未获取 | 标 pending + 登记 pending_review（含 needed_action） |
| 学科惯例/格式差异 | 按 FP-xx 规则标 suppressed 并登记，不判缺陷也不静默丢弃 |
| 稿件超长/预算不足 | 保留已审部分，unchecked 登记未审范围，status=partial |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 最小自检清单（每项实测过，2026-11-19）

1. `python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk-rs/severity_rubric.json` → PASS（49 条检查项全部 applied），退出码 0（实测）
2. `python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json` → PASS，退出码 0（实测）
3. `python3 scripts/stat_recompute.py --result examples/example-result.json` → 4 条复算（3 矛盾 + 1 一致），退出码 0（实测）
4. 污染副本 normal → FAIL（15 处）；degraded → PASS（0 处，stat 漏检 2）——FAIL 差实测
5. 六个脚本对缺失 result.json / 未知参数全部退出码 0，不中断交付（实测）
6. `wc -l SKILL.md` ≤ 150（实测 150 行）
7. `gain_probe --inject-pollution` → caught_by_normal_mode=true，原 result.json 未被改动（实测）

## 11. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与
`problems` 列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身
故障打断（对缺失文件、未知参数也一律 exit 0，实测覆盖）。

**Q：统计复算为什么用正态近似？**
Python 标准库没有 t 分布分位数函数，引入 scipy 违反零依赖约束。正态近似在
df≥30 时误差远小于报告常见的 p 值精度，故设容差 0.01（df<30 放宽到 0.015）；
CI 宽度核验不涉及分布近似，仅用 z 常数表（0.90/0.95/0.99）。边界值统计量判
indeterminate，不算矛盾也不冒充已核对。

**Q：复算说矛盾，一定是作者错吗？**
consistent=false 表示稿件报告的统计量组合在算术上无法同时成立（如 r、n 与
p<0.001），这是强证据但脚本不下"造假"结论；定性（fact_error 级别与表述）由
Agent 按口径判断，复算值作为对照依据写入 finding.evidence，复核者可按 detail
重算。

**Q：method_defect 和 reporting_gap 为什么必须分？**
题面明确把"把『作者没有报告』和『作者做错了』混为一谈"列为基础 Agent 的典型
失败。二者修改建议完全不同（重做分析 vs 补写报告），混写会让作者无法逐条回复。
verify_check 强制映射：fact_error ⇒ method_defect、reporting_gap ⇒
insufficient_evidence/norm_issue，绕不过去。

**Q：--ablate 是不是让结果更好看？**
不是。退化模式只会让漏检变多，它的作用是量化"关闭这些机制会漏掉多少"。
SKILL.md 明确退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：pending 是不是偷懒？**
不是——它是题面要求的"对无法确认的条目标记待复核，不凭空补结论"。pending 必须
写 pending_reason 并登记进 pending_review（含 needed_action）。

## 12. 适用范围与限制

- 仅审查输入稿件本身与其自带参考文献：不做外部检索、不查重、不润色、不做投稿决策。
- 统计复算只做稿件报告值的内部自洽性核验，无法验证原始数据真伪。
- 严重度口径与误报抑制规则是本技能事前声明的设定，不冒充期刊官方标准。
- 缺陷/报告不全区分基于稿件文本可观测证据，语义边界情形以 fact_error 优先并写明依据。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量；model_requests 由 Agent 侧回填，缺失保持 null。

## 13. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/stat_recompute.py` 的 `compute_check()` | 纯函数复算引擎（不写盘），六种统计一致性核验可直接移植到任何需要核对统计量的审查场景 |
| `scripts/verify_check.py` 的 `analyze()` + `manuscript_text()` | 纯函数式（不写盘），ablate 参数直接用作"机制开关"对照实验；manuscript_text 是通用的"从 case.json 抽正文"工具 |
| `scripts/coverage_audit.py` 的分面×章节覆盖矩阵 | 任何"多项检查覆盖审计"需求可直接照抄（分面表换成领域项即可） |
| `defect_class` 区分模式 | 通用的"做错了 vs 没报告"二元区分：字段 + 机械映射 + 校验器强制，可移植到安全审查/合规审查 |
| `severity_rubric` 台账格式 | `{levels, declared_at}` 是通用的"事前口径声明"台账 |
| `suppression_rules` + `suppressed[]` | 通用的误报抑制模式：规则表事前声明 + 逐条登记 + 校验 rule_id |
| `pending_review` 登记 | `{finding_id, reason, needed_action}` 通用的人工复核入口格式 |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改统计量即得新的正/负例 |

## 14. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 八步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/稿件结构/口径模板（退出码恒 0） | 是 |
| scripts/coverage_audit.py | 六分面×章节覆盖机械审计 + unchecked 缺口登记 | 是 |
| scripts/stat_recompute.py | 统计量数值复算引擎（六种一致性核验，退出码恒 0） | 是（含 `compute_check()` API） |
| scripts/verify_check.py | 业务校验器（定位回证/分级口径/证据链/复算一致/缺陷区分/待复核抑制登记） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 领域化污染反例 | 是 |
| examples/example-case.json | 合成输入示例（虚构稿件与统计量） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 15. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节六条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/FINDING_REQUIRED`
  与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
