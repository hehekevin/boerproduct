# cite-fact-verify — 引用与事实核验 Skill（v1）

针对 Bohrium 产品赛第 4 期「学术审查」赛道「引用与事实核验：论文质量审查」
(challenge-cbe96f01) 的参赛 Skill。锁定子场景：**逐条引用核对（引用主张 vs 被引
内容对应关系）+ 编造引用检测 + 数值/单位/年份一致性复算 + 正文事实性陈述与材料
内证据比对 + pending 不冒充已核对**。

## 1. 用途与适用条件

给定一篇固定稿件（论文/科研材料）与审查要求，完成六件事：

1. **逐条引用核对（四态判定）**：正文论断与被引文献主张的对应关系判为
   `fully_supported / partially_supported / unsupported / cannot_determine` 四态，
   识别"结论超出引文范围"的过度推断（over_inference）；**读不到被引文献 →
   cannot_determine + pending，不冒充已核对**。
2. **编造引用检测**：citation_audit.py 机械提取正文引用标记（[n] 与
   Author-Year）并与参考文献表比对，产出编造引用候选清单；citation_fabrication
   发现的 cite_marker 必须命中该清单（校验器强制），防止凭空指认。
3. **数值一致性复算**：numeric_audit.py 机械复算两类确定性模式——同一前置
   标签+单位在不同节出现不同数值（样本量漂移）、显著性表述矛盾（摘要 p<0.01 vs
   结果 p=0.04 复算 0.04 不满足阈值）；发现里的 numeric_claims 必须逐字回证原文。
4. **事实比对**：正文事实性陈述与材料内证据（含被引主张）逐条对照，超出证据
   范围的外推单独成条。
5. **四类区分 × 三级口径**：fact_error / insufficient_evidence / norm_issue /
   suggestion × critical / major / minor（口径在任何判定之前声明，机械映射
   suggestion⇒minor、fact_error⇒critical/major）。
6. **待复核与误报抑制登记**：无法确认的条目标 pending 并登记
   `pending_review[]`（含 reason 与 needed_action）；学科惯例等误报按 FP-xx
   规则标 suppressed 并登记——既不误报，也不静默丢弃。

**核心保证**：`verify_check.py` 把每条 confirmed 发现的引文做空白归一化后逐字
回证于稿件原文（引文不在原文 = 定位失据 = FAIL）、核对引用四态与编造引用对齐、
数值回证、分级口径映射、claims 证据链与待复核/抑制登记；`gain_probe.py` 用正常
vs 退化双跑实测机制增益。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 投稿前自查的科研人员 | 引用是否支持结论、数字是否前后一致 | 逐条位置 + 严重度 + 修改建议的问题清单 |
| 审稿人 / 审稿助理 | 需要区分"引用存在"与"引用支持结论" | 四态判定 + 编造引用候选 + 待复核清单 |
| 编辑部 / 质量把关 | 需要证明引用、事实、数值三类检查都做过 | coverage 六分面 × 章节矩阵 + unchecked 缺口登记 |
| 复核者 | 回原文逐条核对审查结论 | quote 逐字回证 + claims 证据链 + 可复跑命令 |

**不适用**：不做外部文献检索、不查重、不润色改写、不做投稿排版；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13.14 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包约 160 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB（本包 10 个文件） |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 稿件结构清单 + 口径模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 声明严重度口径与误报抑制规则，然后六分面逐条审查（见 SKILL.md 七步流程）

# Step 3：引用/数值/覆盖三项机械审计（写 result.citation_audit / numeric_audit / coverage）
python3 /skills/weekly-skill/scripts/citation_audit.py --result /app/output/result.json --case /input/case.json --emit-into
python3 /skills/weekly-skill/scripts/numeric_audit.py --result /app/output/result.json --case /input/case.json --emit-into
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
    `suppression_rules`、`facets`、`findings[]`（逐条发现，含 cite_marker /
    citation_state / over_inference / numeric_claims）、`suppressed[]`、
    `pending_review[]`、`clearances[]`、`citation_audit`、`numeric_audit`、
    `coverage`、`unchecked`、`steps`、`run_status`、`verdict`、`verdict_basis`、
    `gain_evidence`、`efficiency`
- **引用四态**：`fully_supported` / `partially_supported` / `unsupported` /
  `cannot_determine`（读不到被引文献必须 pending，不冒充已核对）。
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
7 confirmed（F01 引用标记 [9] 不在参考文献表（编造引用）、F02 引用 [2] 证据边界
与论断冲突（过度推断）、F04 摘要 48 名 vs 方法 36 名样本量矛盾、F05 摘要 p<0.01
vs 结果 p=0.04 复算矛盾、F06 结论外推超出材料证据、F07 来源适用范围不一致、
F08 分组结果缺可回查定位）+ 1 pending（F03 引用 [4] 全文未获取，cannot_determine
→ pending，不冒充已核对）+ 1 suppressed（F09 作者自陈局限，按 FP-01 抑制）。
机械审计实测命中：编造候选 `[9]`、未引用文献 `[3]`、标签冲突（受试者名 48/36）、
p 表述违规（p<0.01 vs p=0.04）。示意输出关键片段：

```json
{
  "case_id": "demo-citefact-001", "status": "answered",
  "result": {
    "findings": [{"finding_id": "F04", "facet": "numeric_consistency", "category": "fact_error",
                  "severity": "critical", "quote": "共纳入受试者 48 名",
                  "numeric_claims": [{"value": "48", "unit": "名", "where": "S1 摘要"},
                                      {"value": "36", "unit": "名", "where": "S3 方法"}],
                  "status": "confirmed"}],
    "citation_audit": {"fabricated_markers": ["[9]"], "uncited_refs": ["[3]"]},
    "numeric_audit": {"label_conflicts": 1, "p_violations": 1},
    "verdict": "audited"
  },
  "claims": [{"claim_id": "c-03", "source_id": "F04",
              "evidence": [{"paragraph_id": "manuscript.sections[0].text", "quote": "共纳入受试者 48 名"}]}]
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/citation_audit.py --result examples/example-result.json --case examples/example-case.json --emit-into
python3 scripts/numeric_audit.py --result examples/example-result.json --case examples/example-case.json --emit-into
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
| A3 | 引用逐字回证 | 每条 confirmed 的 quote 空白归一化后逐字命中稿件原文 |
| A4 | 引用四态诚实 | citation_state=cannot_determine ⇒ status=pending；confirmed 的 cite_marker 回证参考文献表 |
| A5 | 编造引用对齐 | citation_fabrication 的 cite_marker 命中 citation_audit.fabricated_markers 机械候选 |
| A6 | 数值回证 | numeric_claims value+unit 逐字命中原文；numeric_consistency 必须给 numeric_claims |
| A7 | 分级有锚点 | severity_rubric 事前声明；suggestion⇒minor；fact_error⇒critical/major |
| A8 | 待复核登记 | 每个 pending 条目进 pending_review（含 reason+needed_action） |
| A9 | 误报抑制 | suppressed 全登记且 rule_id 在事前规则表内 |
| A10 | 六分面全覆盖 | 六分面计数与实际一致；零发现分面/章节有 unchecked/clearances 登记 |
| A11 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A12 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部六组（定位回证 + 分级口径 + 证据链 + 待复核/抑制登记 + 引用规则 + 数值回证） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **上述六组全部关闭** |

实测对照（合成案例 + 注入 7 项领域化污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| 污染副本 verdict | FAIL（13 处问题） | PASS（0 处） | −13 |
| 污染副本引用定位失据漏检 | 0 | 1 | +1 |
| 污染副本证据缺失漏检 | 0 | 7 | +7 |
| 污染副本待复核漏登记 | 1 | 2 | +1 |
| 污染副本编造引用漏检 | 0 | 1 | +1 |
| 污染副本数值漂移漏检 | 0 | 1 | +1 |
| 干净输入漏检（六类） | 0 | 0 | 0 |
| steps_count | 51 | 7 | +44 |

注入的 7 项污染：F01 清空 quote/location（定位失据）；F01 篡改 cite_marker 为
[99]（参考文献表不存在的编造引用）；F04 篡改 numeric_claims 数值为原文不存在的
999（数值漂移）；F03 标 pending 但清空 pending_reason；F01（fact_error）清空
对照依据 evidence；清空 pending_review；清空 claims。

**同一校验器、同一污染输入**：正常模式抓全（verdict=FAIL，编造引用与数值漂移
漏检均为 0），退化模式 11 处客观违规全部漏掉且 verdict 从 FAIL 翻成 PASS——机制
增益最直接的证据。数字由探针独立复算违规真值，与校验层分开实现；详见
`mechanism_to_metric_map`。干净输入上六类漏检均为 0（无违规可漏），增益证据主要
来自污染反例副本。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 稿件解析失败 / 输入不可读 | material_gaps 登记 + verdict=cannot_verify，绝不编造审查结论 |
| 被引文献全文读不到 | citation_state=cannot_determine + pending + pending_review 登记（含 needed_action），不冒充已核对 |
| 引用标记/参考文献表扫描异常 | citation_audit 闸门记 not_found，退化为独立复算并在 steps 注明 |
| 数值无法复算（表格/图不可读） | clearances 登记 artifact:* 豁免 + material_gaps 注明 |
| 学科惯例/格式差异 | 按 FP-xx 规则标 suppressed 并登记，不判缺陷也不静默丢弃 |
| 稿件超长/预算不足 | 保留已审部分，unchecked 登记未审范围，status=partial |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 最小自检清单（每项实测过，2026-11-19）

1. `python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk-cite/severity_rubric.json` → PASS（44 检查项全 applied），退出码 0
2. `python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json` → PASS，退出码 0
3. 污染副本双跑：normal → FAIL（13 处）；degraded → PASS（0 处）——FAIL 差实测
4. 七个脚本对缺失 result.json 全部退出码 0，不中断交付（实测）
5. `wc -l SKILL.md` = 150（≤150 达标）
6. `gain_probe --inject-pollution` → caught_by_normal_mode=true，原 result.json 未被改动（实测）
7. 干净输入 `--ablate citation,numeric` → 仍 PASS 且 44 检查项 applied（消融开关不误伤，实测）

## 11. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与
`problems` 列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：编造引用会不会误伤？**
机械扫描只产**候选清单**（正文有、参考文献表无的标记）。Agent 须逐条复核后才
能写成 confirmed 发现，且发现里的 cite_marker 必须命中候选清单；反过来，若发现
指认的标记实际在文献表里，verify_check 会判"编造判定与扫描结果矛盾"。两头都锁死。

**Q：读不到被引文献为什么必须标 pending？**
题面明确要求"对无法确认的条目标记待复核，不凭空补结论"。引用支持的语义核对
无法在读不到文献时机械完成——标 cannot_determine + pending 并登记 needed_action，
把人工注意力集中到真正难判的条目上，这就是"引用存在 ≠ 引用支持"的诚实边界。

**Q：数值复算覆盖什么、不覆盖什么？**
机械复算两类确定性模式：同标签+单位跨节数值漂移、显著性表述矛盾（p=值逐条
对阈值复算）。复杂表格内的数值关系不在机械范围，登记 clearances 或待复核；
发现里的 numeric_claims 一律逐字回证原文，防止数值冒充。

**Q：--ablate 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。
SKILL.md 明确退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：severity 的口径是谁定的？**
本技能在 severity_rubric 事前声明（题面未给定时按量级保守设定并写明），声明后
禁止调整；verify_check 核对 declared_at 与 levels 三级判据非空。

## 12. 适用范围与限制

- 仅审查输入稿件本身与其自带参考文献：不做外部检索、不查重、不润色、不做排版。
- 编造引用识别是"正文标记 vs 参考文献表"的机械比对，脚注式等异常标记样式可能漏检，候选须经 Agent 复核。
- 数值复算覆盖"同标签漂移 + 显著性矛盾"两类确定性模式，复杂表格内数值关系不在机械范围。
- 引文回证是逐字命中的机械下界，不替代被引文献主张的语义核对（读不到标 pending）。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 13. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/citation_audit.py` 的标记提取与文献表比对 | 任何"正文标记 vs 清单比对"需求可直接照抄（换标记正则即可） |
| `scripts/numeric_audit.py` 的标签分组漂移扫描 + p 值复算 | 任何"数值一致性扫描"需求可复用（标签窗口长度可调） |
| `scripts/verify_check.py` 的 `analyze()` + 六组消融开关 | 纯函数式（不写盘），ablate 参数可直接用作"机制开关"对照实验 |
| `scripts/coverage_audit.py` 的分面×章节覆盖矩阵 | 任何"多项检查覆盖审计"需求可直接照抄 |
| severity_rubric 台账 + FP-xx 抑制规则 + pending_review 登记 | 通用的事前口径声明 / 误报抑制 / 人工复核入口格式 |
| 闸门五态命中 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改标记即得新的负例 |

## 14. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明，150 行） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/稿件结构/口径模板（退出码恒 0） | 是 |
| scripts/citation_audit.py | 引用标记 vs 参考文献表机械比对（编造引用候选） | 是（含提取函数 API） |
| scripts/numeric_audit.py | 数值漂移候选 + 显著性复算底账 | 是（含扫描函数 API） |
| scripts/coverage_audit.py | 六分面×章节覆盖机械审计 + unchecked 缺口登记 | 是 |
| scripts/verify_check.py | 业务校验器（六组校验 + 回写 self_check/gates 等四键） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 领域化污染反例 | 是 |
| examples/example-case.json | 合成输入示例（虚构稿件与文献，含编造引用 [9] 与数值矛盾） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案，全链路实跑回写后落盘） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 15. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/FINDING_REQUIRED`
  与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
