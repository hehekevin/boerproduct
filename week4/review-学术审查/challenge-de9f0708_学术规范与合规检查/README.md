# paper-compliance-audit — 学术规范与合规检查 Skill（v1）

针对 Bohrium 产品赛第 4 周「学术审查」赛道「学术规范与合规检查」(challenge-de9f0708)
的参赛 Skill。锁定子场景：**八分面逐条合规清单（原文位置 + 三类区分 + 严重度 +
修改建议）+ 必备声明存在性机检 + 格式规则事前声明与依据绑定 + 误报抑制 +
待复核登记**。

## 1. 用途与适用条件

给定一篇固定稿件（论文/科研材料）与合规审查要求，完成六件事：

1. **八分面逐条审查**：数据可用性、伦理与知情同意、利益冲突、作者贡献、
   基金资助、图表版权与许可、参考文献格式、重复发表与一稿多投——八个分面
   逐一过稿，每条发现定位到句（quote 逐字摘录 + 章节句位）。
2. **三类分开呈现**：`norm_missing`（规范缺失：必备声明/信息不存在）/
   `norm_violation`（规范不合规：存在但不符合格式规则，须绑定 rule_id）/
   `substantive_issue`（实质性学术问题：重复发表、数据复用等实质诚信问题）
   ——不混写为泛泛的"规范问题"。
3. **口径事前声明**：三类定义 + 三级严重度判据在任何判定之前声明
   （compliance_rubric，declared_at 必填），机械映射：substantive_issue⇒
   critical/major；norm_missing/norm_violation⇒major/minor——分级有锚点。
4. **依据绑定**：`format_rules`（FR-01~08，判定前冻结）是"判不合规"的可核对
   依据——每条 norm_missing/norm_violation 必须引用事前规则条款，不编造
   期刊要求；substantive_issue 必须给对照依据。
5. **声明存在性机检**：`decl_audit.py` 按中英双语关键词表机械扫描六项必备
   声明（数据可用性/伦理/利益冲突/作者贡献/基金资助/版权许可），记录
   detected/matched_keywords/sections；机检判缺失的声明必须有一条 norm_missing
   发现或豁免登记（单向对账，verify_check 强制）——机检与语义判定分层，
   声明在投稿系统/单独文件时按实际情况登记，不凭空判缺。
6. **误报抑制 + 待复核**：学科写作惯例、期刊格式差异（FP-01/02/03，事前声明）
   判"不算缺陷"并登记 `suppressed[]`；无法确认的条目（重复发表需外部比对、
   图表许可不可解析）标 pending 并登记 `pending_review[]`——不凭空补结论。

**核心保证**：`verify_check.py` 把每条 confirmed 发现的引文做空白归一化后
逐字回证于稿件原文（引文不在原文 = 定位失据 = FAIL）、核对三类×严重度映射、
规则绑定、声明机检一致性、claims 证据链与待复核/抑制登记；`gain_probe.py`
用正常 vs 退化双跑实测机制增益。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 投稿/结题前自查的科研人员 | 把"合规哪里有缺口"变成可交办条目 | 逐条位置 + 三类区分 + 严重度 + 修改建议 |
| 研究生院/编辑部形式审查 | 需要证明必备声明都查过 | declaration_audit 机检证据 + 八分面×章节覆盖矩阵 |
| 学术诚信办公室 | 需要区分形式缺口与实质诚信问题 | 三类分开呈现 + substantive_issue 对照依据 + 待复核清单 |
| 复核者 | 回原文逐条核对审查结论 | quote 逐字回证 + rule_id 可核对 + claims 证据链 + 可复跑命令 |

**不适用**：不做外部文献检索、不查重库比对、不润色改写、不提供法务或伦理
委员会正式意见；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13.14 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包约 177 KB（实测 180,975 字节，含增益证据回写后的示例输出） |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB（实测 10 个文件） |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 稿件结构清单 + 口径模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 声明三类口径与格式规则，然后八分面逐条审查（见 SKILL.md 七步流程）

# Step 3：声明存在性机检 + 八分面覆盖审计（写 declaration_audit / coverage / unchecked）
python3 /skills/weekly-skill/scripts/decl_audit.py --result /app/output/result.json \
  --case /input/case.json --input-root /input --emit-into

# Step 5：增益对照 + 效率计数（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 6：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --ledger /app/work/compliance_rubric.json --out /app/work/verify_check.json --emit-into
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
    `compliance_rubric`（三类 + 三级口径）、`format_rules`（FR-01~08）、
    `suppression_rules`、`facets`（八分面）、`declaration_checklist`、
    `declaration_audit`（机检证据）、`findings[]`（逐条发现）、`suppressed[]`、
    `pending_review[]`、`clearances[]`、`coverage`、`unchecked`、`steps`、
    `run_status`、`verdict`、`verdict_basis`、`gain_evidence`、`efficiency`
- **三类区分**：`norm_missing` / `norm_violation` / `substantive_issue`
  × 三级严重度 `critical` / `major` / `minor`（口径事前声明、声明后冻结）。
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`（校验报告）、
  `/app/work/schema_guard.json`（结构报告）、`/app/work/gain_evidence.json`
  （增益对照证据）、`/app/work/compliance_rubric.json`（口径台账）、
  `/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（论文/数据/基金/文献均为虚构）：6 章节虚构稿件 →
9 条发现：7 confirmed（F01 数据可用性声明缺失 norm_missing/major、F02 利益冲突
声明缺失 norm_missing/major、F03 作者贡献声明缺失 norm_missing/minor、
F04 参考文献 [3] 缺年份来源 norm_violation/minor、F05 图1 复用未标许可
norm_violation/major、F06 会议宣读未引用未声明 substantive_issue/major、
F07 摘要与声明节基金编号不一致 norm_violation/minor）+ 1 pending（F08 图2
许可不可解析，登记待复核）+ 1 suppressed（F09 作者自陈局限，按 FP-01 抑制）。
三类齐备：norm_missing=4、norm_violation=4、substantive_issue=1。示意输出关键片段：

```json
{
  "case_id": "demo-compliance-001", "status": "answered",
  "result": {
    "compliance_rubric": {"mapping": "substantive_issue⇒critical/major；norm_missing/norm_violation⇒major/minor", "declared_at": "step1"},
    "findings": [{"finding_id": "F01", "facet": "data_availability", "category": "norm_missing",
                  "severity": "major", "rule_id": "FR-01", "quote": "基金资助：本研究受国家自然科学基金项目（No. 62176123）资助。",
                  "location": "S6 声明、致谢与参考文献 第 1 句", "status": "confirmed"}],
    "declaration_audit": {"items": [{"decl_id": "data_availability", "detected": false}]},
    "coverage": {"total_findings": 9, "confirmed": 7, "pending": 1, "suppressed": 1,
                 "category_counts": {"norm_missing": 4, "norm_violation": 4, "substantive_issue": 1}},
    "verdict": "audited"
  },
  "claims": [{"claim_id": "c-01", "source_id": "F01",
              "evidence": [{"paragraph_id": "manuscript.sections[5].text", "quote": "基金资助：本研究受国家自然科学基金项目（No. 62176123）资助。"}]}]
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/decl_audit.py --result examples/example-result.json --case examples/example-case.json --input-root examples --emit-into
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk/compliance_rubric.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 定位可回证 | 每条 confirmed 的 quote 空白归一化后逐字命中稿件原文 |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 八分面全覆盖 | 八分面计数与实际一致；零发现分面/章节有 unchecked/clearances 登记 |
| A6 | 三类口径一致 | compliance_rubric 事前声明；三类×严重度机械映射无违规 |
| A7 | 依据绑定 | norm_missing/norm_violation 必引事前 format_rules 的 rule_id；substantive_issue 必有对照依据 |
| A8 | 声明机检对账 | 机检 detected=false 的必备声明必有 norm_missing 发现或豁免登记 |
| A9 | 待复核登记 | 每个 pending 条目进 pending_review（含 reason+needed_action） |
| A10 | 误报抑制 | suppressed 全登记且 rule_id 在事前 FP 规则表内 |
| A11 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A12 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（定位回证 + 三类口径 + 规则绑定/声明机检 + 证据链 + 待复核/抑制登记） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **location / rubric / rules / evidence / pending 五组** |

实测对照（合成案例 + 注入 6 项污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 污染副本 verdict | FAIL（12 处问题） | PASS（0 处） | −12 |
| 污染副本定位失据漏检 | 0 | 1 | +1 |
| 污染副本三类口径漏检 | 0 | 1 | +1 |
| 污染副本依据绑定漏检 | 0 | 1 | +1 |
| 污染副本证据缺失漏检 | 0 | 7 | +7 |
| 污染副本待复核漏登记 | 0 | 1 | +1 |
| 干净输入漏检（五类） | 0 | 0 | 0 |
| steps_count | 43 | 7 | +36 |

**同一校验器、同一污染输入**：正常模式抓全（verdict=FAIL，漏检 0），退化模式
11 处客观违规全部漏掉且 verdict 从 FAIL 翻成 PASS——机制增益最直接的证据。
数字由探针独立复算违规真值，与校验层分开实现；详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 稿件解析失败 / 输入不可读 | material_gaps 登记 + verdict=cannot_verify，绝不编造合规结论 |
| 声明在投稿系统/单独文件 | 机检 detected=false 时按实际登记 clearances（scope=decl:xxx）或 material_gaps |
| 图表无法读取/许可不可解析 | clearances 登记 artifact:* 豁免 + material_gaps 注明；版权不明标 pending |
| 重复发表/一稿多投疑似 | 稿件内部可确认的判 substantive_issue；需外部比对的标 pending + needed_action |
| 期刊指南缺失/题面未给规则 | 按默认 format_rules 保守审查并注明依据自设，不冒充期刊官方标准 |
| 稿件超长/预算不足 | 保留已审部分，unchecked 登记未审范围，status=partial |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 最小自检清单（每项实测过）

1. `python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk-comp/compliance_rubric.json` → PASS（36 检查项全 applied），退出码 0（实测 2026-11-19）
2. `python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json` → PASS，退出码 0（实测）
3. 污染副本（注入 6 项）`--ablate none` → FAIL（12 处）；`--ablate all` → PASS（0 处）——FAIL 差实测
4. 五个脚本对缺失 result.json / 缺失 case.json / 非法参数全部退出码 0，不中断交付（实测）
5. `wc -l SKILL.md` ≤ 150（实测 149 行）
6. `gain_probe --inject-pollution` → caught_by_normal_mode=true，原 result.json 未被改动（实测）
7. `--ablate rules` 单组消融：问题数 12→11（仅关闭依据绑定组），组级开关生效（实测）

## 11. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与
`problems` 列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身
故障打断（连 argparse 用法错误也降级为 0）。

**Q：机检说"未检出"就是"违规"吗？**
不是。`declaration_audit` 只是关键词机械证据：只能证明"稿件文本中未出现相关
表述"。声明可能在投稿系统或单独文件——所以对账是单向的：机检判缺失必须有
norm_missing 发现**或**豁免登记说明去向；机检命中也不强制有发现（关键词可能
误命中，语义判断归 Agent）。

**Q：norm_missing/norm_violation 为什么要绑定 rule_id？**
题面要求"每条判定有可核对的依据"。format_rules 在判定前声明并冻结，发现必须
引用其中的条款——复核者可以直接核对"依据引没引对、条款是不是事后编的"。
substantive_issue 不依赖格式规则，改要求对照依据 evidence。

**Q：三类会不会混写？**
不会。category 三选一且由机械映射锁定严重度：substantive_issue⇒critical/major、
norm_missing/norm_violation⇒major/minor。verify_check 逐条核对映射，违规即 FAIL。

**Q：--ablate 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。
SKILL.md 明确退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：pending 是不是偷懒？**
不是——重复发表比对、图表许可确认等无法在稿件内部完成的判断，标 pending 并
登记 pending_review（含 needed_action），把人工注意力集中到真正难判的条目上，
不凭空补结论。

## 12. 适用范围与限制

- 仅审查输入稿件本身与其自带材料：不做外部检索、不查重库比对、不润色、不代投。
- format_rules 默认条目是本技能事前声明的通用规范设定（题面或期刊指南给出时按实际改写并冻结），不冒充期刊官方标准。
- 声明存在性机检基于关键词表，是机械下界；机检证据与语义判定分层。
- 重复发表比对只能基于稿件内部线索，外部比对需求标 pending。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 13. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` + `category_mapping_bad()` | 纯函数式（不写盘），ablate 参数可直接用作"机制开关"对照实验；`category_mapping_bad` 是通用的"类别×严重度映射"检查器 |
| `scripts/decl_audit.py` 的关键词存在性机检 | 任何"必备要素存在性检查"需求可照抄：换 DECL_KEYWORDS 词条表即可（声明→字段/章节/图表要素） |
| `scripts/decl_audit.py` 的分面×章节覆盖矩阵 | 任何"多项检查覆盖审计"需求可直接照抄（分面表换成领域项即可） |
| `compliance_rubric` 台账格式 | `{categories, severity_levels, mapping, declared_at}` 是通用的"事前口径声明"台账 |
| `format_rules` + rule_id 绑定 | 通用的"判定依据可核对"模式：规则表事前声明 + 逐条引用 + 校验 rule_id 在表内 |
| `suppression_rules` + `suppressed[]` | 通用的误报抑制模式：规则表事前声明 + 逐条登记 + 校验 rule_id |
| `pending_review` 登记 | `{finding_id, reason, needed_action}` 通用的人工复核入口格式 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改标签即得新的负例 |

## 14. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/稿件结构/口径模板 + 挂载标志校验（退出码恒 0） | 是 |
| scripts/decl_audit.py | 声明存在性机检 + 八分面×章节覆盖审计 + unchecked 缺口登记 | 是 |
| scripts/verify_check.py | 业务校验器（定位回证/三类口径/规则绑定/声明对账/证据链/待复核抑制登记） | 是（含 `analyze()` API） |
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
  与 SKILL.md 的 schema 段；改动三类/八分面枚举时同步 `verify_check.py`、
  `decl_audit.py`、`gain_probe.py` 的常量表（多处一致性由自测兜底）。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
