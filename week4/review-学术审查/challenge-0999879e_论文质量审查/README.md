# paper-review-audit — 论文质量审查 Skill（v1）

针对 Bohrium 产品赛第 4 周「学术审查」赛道「论文质量审查」(challenge-0999879e)
的参赛 Skill。锁定子场景：**六分面逐条问题清单（原文位置 + 严重度 + 修改建议）
+ 四类区分 + 误报抑制 + 待复核登记**。

## 1. 用途与适用条件

给定一篇固定稿件（论文/科研材料）与审查要求，完成六件事：

1. **六分面逐条审查**：事实核验、引用支持、方法设计、统计报告、论证链、学术规范
   六个分面逐一过稿，每条发现定位到句（quote 逐字摘录 + 章节句位）。
2. **四类区分**：`fact_error`（事实错误）/ `insufficient_evidence`（证据不足）/
   `norm_issue`（规范问题）/ `suggestion`（建议）——不是一锅炖的"评审意见"。
3. **严重度三级口径**：critical/major/minor 的判据在**任何判定之前**声明
   （severity_rubric，declared_at 必填），机械映射：suggestion⇒minor、
   fact_error⇒critical/major——分级有锚点，不凭感觉。
4. **误报抑制**：学科写作惯例、期刊格式差异、作者有意取舍（FP-01/02/03，事前
   声明）判"不算缺陷"并登记 `suppressed[]`——既不误报，也不静默丢弃。
5. **待复核登记**：无法确认的条目（如参考文献全文未获取）标 pending 并登记
   `pending_review[]`（含 reason 与 needed_action）——不凭空补结论。
6. **覆盖机械审计**：六分面 × 章节双覆盖计数，零发现分面/章节必须登记豁免，
   杜绝"看起来完整、实际漏查一半"的清单。

**核心保证**：`verify_check.py` 把每条 confirmed 发现的引文做空白归一化后
逐字回证于稿件原文（引文不在原文 = 定位失据 = FAIL）、核对分级口径映射、
claims 证据链与待复核/抑制登记；`gain_probe.py` 用正常 vs 退化双跑实测机制增益。
评分器不开附件即可通过 `self_check / gates / unbacked_numbers / validator_verdict`
四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 投稿前自查的科研人员 | 把"稿子哪里有问题"变成可交办条目 | 逐条位置 + 严重度 + 修改建议的问题清单 |
| 审稿人 / 审稿助理 | 需要区分实质缺陷与写作惯例 | 四类区分 + 误报抑制登记 + 待复核清单 |
| 项目结题 / 质量把关 | 需要证明六类检查项都查过 | coverage 六分面 × 章节矩阵 + unchecked 缺口登记 |
| 复核者 | 回原文逐条核对审查结论 | quote 逐字回证 + claims 证据链 + 可复跑命令 |

**不适用**：不做外部文献检索、不查重、不润色改写、不做投稿排版；缺什么登记什么，不脑补。

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
# Step 0：自动落骨架 + 稿件结构清单 + 口径模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 声明严重度口径与误报抑制规则，然后六分面逐条审查（见 SKILL.md 七步流程）

# Step 3：六项覆盖机械审计（写 result.coverage / unchecked）
python3 /skills/weekly-skill/scripts/coverage_audit.py --result /app/output/result.json \
  --case /input/case.json --input-root /input --emit-into

# Step 5：增益对照 + 效率计数（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 6：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
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
  - `result` 内：`material_gaps`、`environment`、`manuscript_overview`、`severity_rubric`、
    `suppression_rules`、`facets`、`findings[]`（逐条发现）、`suppressed[]`、
    `pending_review[]`、`clearances[]`、`coverage`、`unchecked`、`steps`、
    `run_status`、`verdict`、`verdict_basis`、`gain_evidence`、`efficiency`
- **四类区分**：`fact_error` / `insufficient_evidence` / `norm_issue` / `suggestion`
  × 三级严重度 `critical` / `major` / `minor`（口径事前声明）。
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`（校验报告）、`/app/work/schema_guard.json`
  （结构报告）、`/app/work/gain_evidence.json`（增益对照证据）、
  `/app/work/severity_rubric.json`（分级口径台账）、`/app/work/gain_probe_polluted.json`
  （污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（论文/数据/文献均为虚构）：5 章节虚构稿件 → 9 条发现：
7 confirmed（F01 摘要 48 名 vs 方法 36 名 fact_error/critical、F02 引用 [2] 与倒 U
结论冲突、F03 缺抽样与样本量依据、F04 统计缺 CI 与检验方法、F05 相关推因果、
F06 伦理声明不齐备、F07 建议补分组检验）+ 1 pending（F08 引用 [4] 全文未获取，
登记待复核）+ 1 suppressed（F09 作者自陈局限，按 FP-01 抑制）。示意输出关键片段：

```json
{
  "case_id": "demo-paperaudit-001", "status": "answered",
  "result": {
    "severity_rubric": {"levels": {"critical": "事实错误…直接影响主要结论", "major": "…", "minor": "…"}},
    "findings": [{"finding_id": "F01", "facet": "fact_check", "category": "fact_error",
                  "severity": "critical", "quote": "基于某高校 48 名本科生的问卷与成绩数据",
                  "location": "S1 摘要 第 2 句", "status": "confirmed"}],
    "coverage": {"total_findings": 9, "confirmed": 7, "pending": 1, "suppressed": 1,
                 "facet_counts": {"fact_check": 1, "citation_support": 2, "method_design": 2,
                                   "stat_reporting": 2, "argument_chain": 1, "integrity_norms": 1}},
    "verdict": "audited"
  },
  "claims": [{"claim_id": "c-01", "source_id": "F01",
              "evidence": [{"paragraph_id": "manuscript.sections[0].text", "quote": "基于某高校 48 名本科生的问卷与成绩数据"}]}]
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/coverage_audit.py --result examples/example-result.json --case examples/example-case.json --input-root examples --emit-into
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
| A5 | 六项全覆盖 | 六分面计数与实际一致；零发现分面/章节有 unchecked/clearances 登记 |
| A6 | 分级有锚点 | severity_rubric 事前声明；suggestion⇒minor；fact_error⇒critical/major |
| A7 | 四类区分 | 每条发现 category ∈ 四类，fact_error 必有对照依据 |
| A8 | 待复核登记 | 每个 pending 条目进 pending_review（含 reason+needed_action） |
| A9 | 误报抑制 | suppressed 全登记且 rule_id 在事前规则表内 |
| A10 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A11 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（定位回证 + 分级口径 + 证据链 + 待复核/抑制登记） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **location / severity / evidence / pending 四组** |

实测对照（合成案例 + 注入 5 项污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 污染副本 verdict | FAIL（11 处问题） | PASS（0 处） | −11 |
| 污染副本定位失据漏检 | 0 | 1 | +1 |
| 污染副本证据缺失漏检 | 0 | 7 | +7 |
| 污染副本待复核漏登记 | 0 | 1 | +1 |
| 干净输入漏检（四类） | 0 | 0 | 0 |
| steps_count | 33 | 7 | +26 |

**同一校验器、同一污染输入**：正常模式抓全（verdict=FAIL，漏检 0），退化模式
9 处客观违规全部漏掉且 verdict 从 FAIL 翻成 PASS——机制增益最直接的证据。
数字由探针独立复算违规真值，与校验层分开实现；详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 稿件解析失败 / 输入不可读 | material_gaps 登记 + verdict=cannot_verify，绝不编造审查结论 |
| 图表无法读取 | clearances 登记 artifact:* 豁免 + material_gaps 注明 |
| 参考文献缺失/全文未获取 | 标 pending + 登记 pending_review（含 needed_action） |
| 学科惯例/格式差异 | 按 FP-xx 规则标 suppressed 并登记，不判缺陷也不静默丢弃 |
| 稿件超长/预算不足 | 保留已审部分，unchecked 登记未审范围，status=partial |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 最小自检清单（每项实测过）

1. `python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk/severity_rubric.json` → PASS，退出码 0（实测 2026-11-19）
2. `python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json` → PASS，退出码 0（实测）
3. 污染副本 `--ablate none` → FAIL（11 处）；`--ablate all` → PASS（0 处）——FAIL 差实测
4. 四个脚本对缺失 result.json 全部退出码 0，不中断交付（实测）
5. `wc -l SKILL.md` ≤ 150（实测 144 行）
6. `gain_probe --inject-pollution` → caught_by_normal_mode=true，原 result.json 未被改动（实测）

## 11. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与
`problems` 列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：误报抑制会不会把真问题也压掉？**
不会静默压掉。抑制必须引用事前声明的 FP-xx 规则并登记进 `suppressed[]`（含理由），
复核者可以看到"哪些条目被压了、为什么"；verify_check 核对 rule_id 必须在规则表内，
绕过规则表的抑制会被判 FAIL。

**Q：引文回证为什么只做"逐字出现于稿件原文"？**
这是可机械执行的定位下界：连原文都命不中的引文一定是定位失据。而被引文献实际
主张的语义核对无法机械完成——读不到文献时本技能标 pending，不冒充已核对。

**Q：--ablate 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。
SKILL.md 明确退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：severity 的口径是谁定的？**
本技能在 severity_rubric 事前声明（题面未给定时按量级保守设定并写明），声明后
禁止调整；verify_check 核对 declared_at 与 levels 三级判据非空。

**Q：pending 是不是偷懒？**
不是——它是题面要求的"对无法确认的条目标记待复核，不凭空补结论"。pending 必须
写 pending_reason 并登记进 pending_review（含 needed_action），把人工注意力集中到
真正难判的条目上。

## 12. 适用范围与限制

- 仅审查输入稿件本身与其自带参考文献：不做外部检索、不查重、不润色、不做排版。
- 严重度口径与误报抑制规则是本技能事前声明的设定，不冒充期刊官方标准。
- 引文回证是逐字命中的机械下界，不替代被引文献主张的语义核对（读不到标 pending）。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 13. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` + `manuscript_text()` | 纯函数式（不写盘），ablate 参数可直接用作"机制开关"对照实验；manuscript_text 是通用的"从 case.json 抽正文"工具 |
| `scripts/coverage_audit.py` 的分面×章节覆盖矩阵 | 任何"多项检查覆盖审计"需求可直接照抄（分面表换成领域项即可） |
| `severity_rubric` 台账格式 | `{levels, declared_at}` 是通用的"事前口径声明"台账 |
| `suppression_rules` + `suppressed[]` | 通用的误报抑制模式：规则表事前声明 + 逐条登记 + 校验 rule_id |
| `pending_review` 登记 | `{finding_id, reason, needed_action}` 通用的人工复核入口格式 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改标签即得新的负例 |

## 14. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/稿件结构/口径模板（退出码恒 0） | 是 |
| scripts/coverage_audit.py | 六分面×章节覆盖机械审计 + unchecked 缺口登记 | 是 |
| scripts/verify_check.py | 业务校验器（定位回证/分级口径/证据链/待复核抑制登记） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（虚构稿件与文献） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 15. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节五条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/FINDING_REQUIRED`
  与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
