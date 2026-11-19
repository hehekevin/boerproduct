# argchain-review — 论文逻辑与论证审查 Skill（v1）

针对 Bohrium 产品赛第 4 周「学术审查」赛道「论文逻辑与论证审查」(challenge-16d4414d)
的参赛 Skill。锁定子场景：**论证链逐环追踪（假设→前提→推理→结论，逐节点定位）
+ 六类逻辑问题清单（断链/循环论证/因果相关混淆/外推超界/强度不匹配/反驳缺失）
+ 结论-证据强度匹配判定登记 + 反驳与局限性覆盖检查**。

## 1. 用途与适用条件

给定一篇固定稿件（论文/科研材料）与审查要求，完成六件事：

1. **论证链逐环追踪**：把每条主论证拆成节点（`hypothesis` / `premise` /
   `reasoning` / `conclusion`），每个节点带逐字引文与句位；`chain_audit.py`
   机械审计节点完备性（缺前提/缺结论/引文不可回证 → 落 unchecked）。
2. **六类问题口径一致**：`broken_chain` / `circular_reasoning` /
   `correlation_causation` / `over_extrapolation` / `strength_mismatch` /
   `missing_rebuttal`——口径在**任何判定之前**声明（issue_taxonomy，declared_at
   必填），每条发现 issue_type 必居其一，分类可映射回事前口径。
3. **强度匹配判定登记**：双侧标尺（证据 E3 对照实验→E0 无实证；主张 C3 因果
   断言→C1 假说性表述）判定前声明；每条核心结论登记 `strength_matches[]`
   （claim_strength × evidence_strength × verdict），机械规则 C3须E3。
4. **误报抑制**：作者有意设置的对照组、明确标注的假设情形、转述他人观点
   （FP-01/02/03，事前声明）判"不算缺陷"并登记 `suppressed[]`——不把对照、
   假设、转述误读成作者自相矛盾，也不静默丢弃。
5. **待复核登记**：无法确认的条目标 pending 并登记 `pending_review[]`
   （含 reason 与 needed_action）——不凭空补结论。
6. **反驳与局限覆盖检查**：rebuttal_coverage 分面逐条过替代解释、反例与
   局限性声明；作者自陈的局限不算缺陷、但缺失的实质局限要报。

**核心保证**：`verify_check.py` 把每条 confirmed 发现与每个链节点的引文做
空白归一化后逐字回证于稿件原文（引文不在原文 = 定位失据 = FAIL）、核对分类
口径与分级映射、链节点完备性、强度匹配登记与待复核/抑制登记；
`gain_probe.py` 用正常 vs 退化双跑实测机制增益。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 投稿前自查的科研人员 | 把"论证哪里断了"变成可交办条目 | 逐节点链路图 + 六类问题清单（位置+严重度+建议） |
| 审稿人 / 审稿助理 | 需要判断结论是否超出证据 | strength_matches 强度判定表 + 待复核清单 |
| 领域编辑 / 质量把关 | 需要证明逻辑审查覆盖完整 | 六分面 × 章节 × 链完备三重覆盖矩阵 + unchecked 缺口 |
| 复核者 | 回原文逐条核对审查结论 | quote 逐字回证 + claims 证据链 + 可复跑命令 |

**不适用**：不做外部文献检索、不查重、不润色改写、不做统计复算；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包约 192 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB（本包 10 个文件） |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 稿件结构清单 + 口径三合一模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 声明三口径（严重度/问题类型/强度标尺），然后抽链 + 六类逐条审查（见 SKILL.md 七步流程）

# Step 3：链完备与覆盖机械审计（写 result.chain_audit / coverage / unchecked）
python3 /skills/weekly-skill/scripts/chain_audit.py --result /app/output/result.json \
  --case /input/case.json --input-root /input --emit-into

# Step 5：增益对照 + 效率计数（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 6：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --ledger /app/work/rubrics.json --out /app/work/verify_check.json --emit-into
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
    `severity_rubric`、`issue_taxonomy`、`strength_scale`、`suppression_rules`、
    `facets`、`argument_chains[]`（论证链节点）、`findings[]`（逐条发现，含
    issue_type）、`strength_matches[]`（强度判定）、`suppressed[]`、
    `pending_review[]`、`clearances[]`、`coverage`、`unchecked`、`steps`、
    `run_status`、`verdict`、`verdict_basis`、`gain_evidence`、`efficiency`
- **六类问题**：`broken_chain` / `circular_reasoning` / `correlation_causation` /
  `over_extrapolation` / `strength_mismatch` / `missing_rebuttal`
  × 四类区分（fact_error / insufficient_evidence / norm_issue / suggestion）
  × 三级严重度（critical / major / minor，口径事前声明）。
- **强度判定**：verdict ∈ `supported` / `overstated` / `understated` / `pending`。
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`（业务校验报告）、
  `/app/work/schema_guard.json`（结构报告）、`/app/work/gain_evidence.json`
  （增益对照证据）、`/app/work/rubrics.json`（三口径台账）、
  `/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（论文/数据/文献均为虚构，文件头已标注示意）：
5 章节虚构稿件 → 2 条论证链 → 12 条发现：9 confirmed（F01 因果相关混淆
critical、F02 政策外推超界、F03 反驳缺失、F04 时间先后隐含假设断链、F05
反向数据印证正向主张的循环论证、F06 摘要"首次证实因果路径"强度不匹配、
F07 引言承诺干预方案未交付、F11 方法-结果测量口径断裂、F12 亚组反转被隐去）
+ 1 pending（F08 引用 [3] 全文未获取）+ 2 suppressed（F09 转述他人观点按
FP-02、F10 明确标注的假设情形按 FP-01）。示意输出关键片段：

```json
{
  "case_id": "demo-argchain-001", "status": "answered",
  "result": {
    "issue_taxonomy": {"types": {"correlation_causation": "仅相关/观察证据却做因果表述", "…": "…"}},
    "argument_chains": [{"chain_id": "C1", "nodes": [
      {"node_id": "C1-N3", "role": "reasoning", "quote": "相关分析显示…正相关（r=0.28, p=0.03）", "location": "S4 第1句"},
      {"node_id": "C1-N4", "role": "conclusion", "quote": "结果表明减少社交媒体使用能够改善青少年抑郁状况", "location": "S5 第1句"}]}],
    "findings": [{"finding_id": "F01", "facet": "strength_match", "issue_type": "correlation_causation",
                  "category": "fact_error", "severity": "critical", "chain_ref": "C1-N4", "status": "confirmed"}],
    "strength_matches": [{"match_id": "M01", "finding_id": "F01", "claim_strength": "C3",
                          "evidence_strength": "E2", "verdict": "overstated"}],
    "coverage": {"total_findings": 12, "confirmed": 9, "pending": 1, "suppressed": 2,
                 "issue_type_counts": {"broken_chain": 3, "circular_reasoning": 2, "correlation_causation": 1,
                                        "over_extrapolation": 2, "strength_mismatch": 3, "missing_rebuttal": 1}},
    "verdict": "audited"
  }
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/chain_audit.py --result examples/example-result.json --case examples/example-case.json --input-root examples --emit-into
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk/rubrics.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 定位可回证 | 每条 confirmed 与每个链节点的 quote 空白归一化后逐字命中稿件原文 |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 覆盖完整 | 六分面计数与实际一致；零发现分面/章节有 unchecked/clearances 登记 |
| A6 | 链节点完备 | 每条链 ≥2 节点，含 premise/hypothesis 与 conclusion；chain_ref 有效 |
| A7 | 口径有锚点 | 三口径（severity/issue_taxonomy/strength_scale）事前声明；suggestion⇒minor；fact_error⇒critical/major |
| A8 | 强度判定登记 | 每条 confirmed 的 strength_mismatch 均有 strength_matches 登记；C3 配 E2 以下不得判 supported |
| A9 | 待复核登记 | 每个 pending 条目进 pending_review（含 reason+needed_action） |
| A10 | 误报抑制 | suppressed 全登记且 rule_id 在事前规则表内（对照/假设/转述不误报） |
| A11 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A12 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部五组（定位回证 + 分类口径 + 强度登记 + 链完备 + 待复核/抑制登记） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **location / taxonomy / strength / chain / pending 五组** |

实测对照（合成案例 + 注入 9 项污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入 verdict / 五类漏检 | PASS / 全 0 | PASS / 全 0 | 0（无假阳性） |
| 干净输入 steps_count | 78 | 7 | +71 |
| 污染副本 verdict（problems 数） | FAIL（21 处） | FAIL（3 处） | −18 |
| 污染副本定位失据漏检 | 0 | 1 | +1 |
| 污染副本分级口径违规漏检 | 0 | 1 | +1 |
| 污染副本强度登记缺失漏检 | 0 | 1 | +1 |
| 污染副本链完备违规漏检 | 0 | 1 | +1 |
| 污染副本待复核/证据链漏登记 | 0 | 10 | +10 |

**同一校验器、同一污染输入**：正常模式五类漏检全 0（verdict=FAIL，21 处全抓），
退化模式五组检查关闭后 14 处客观违规漏掉——机制增益最直接的证据。数字由探针
独立复算违规真值，与校验层分开实现；详见 `mechanism_to_metric_map`。
（注入的非法枚举篡改由始终开启的基础枚举层在两模式下都抓到，不参与消融 delta。）

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 稿件解析失败 / 输入不可读 | material_gaps 登记 + verdict=cannot_verify，绝不编造审查结论 |
| 图表无法读取 | clearances 登记 artifact:* 豁免 + material_gaps 注明 |
| 参考文献缺失/全文未获取 | 标 pending + 登记 pending_review（含 needed_action） |
| 对照组/假设情形/转述观点 | 按 FP-xx 规则标 suppressed 并登记，不报成作者自相矛盾 |
| 稿件超长/预算不足 | 保留已审部分，unchecked 登记未审范围，status=partial |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 最小自检清单（每项实测过）

1. `python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk/rubrics.json` → PASS，退出码 0（实测 2026-11-19）
2. `python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json` → PASS，退出码 0（实测）
3. 污染副本双跑 → normal FAIL（21 处）vs degraded FAIL（3 处），五类漏检 0/0/0/0/0 vs 1/1/1/1/10（实测 FAIL 差 18）
4. 五个脚本对缺失 result.json 全部退出码 0，不中断交付（实测）
5. `wc -l SKILL.md` ≤ 150（实测 142 行）
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
这是可机械执行的定位下界：连原文都命不中的引文一定是定位失据。而论证链的语义
完备性无法完全机械判定——chain_audit 只保证节点完备（有前提有结论）且引文可回证，
语义层面的断链由 issue_type=broken_chain 的发现承载。

**Q：强度标尺 E/C 等级是谁定的？**
本技能在 strength_scale 事前声明（题面未给定时按量级保守设定并写明），声明后
禁止调整；verify_check 核对 declared_at 与双侧等级定义非空，C3 配 E2 以下判
supported 会直接 FAIL。

**Q：--ablate 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。
SKILL.md 明确退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：pending 是不是偷懒？**
不是——它是题面要求的"对无法确认的条目标记待复核，不凭空补结论"。pending 必须
写 pending_reason 并登记进 pending_review（含 needed_action），把人工注意力集中到
真正难判的条目上（如引用全文无法获取的引用支持核对）。

## 12. 适用范围与限制

- 仅审查输入稿件本身与其自带参考文献：不做外部检索、不查重、不润色、不复算统计。
- 三口径（严重度/问题类型/强度标尺）是本技能事前声明的设定，不冒充期刊官方标准。
- 引文回证是逐字命中的机械下界；链抽取靠语义判断，机械审计只保证节点完备与引文可回证。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 13. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` + `manuscript_text()` | 纯函数式（不写盘），ablate 参数可直接用作"机制开关"对照实验；manuscript_text 是通用的"从 case.json 抽正文"工具 |
| `scripts/chain_audit.py` 的节点完备审计 + 分面×章节覆盖矩阵 | 任何"多节点结构完备性审计"（流程链、证据链、推理链）可直接照抄 |
| `issue_taxonomy` + `findings[].issue_type` | 通用的"口径事前声明 + 枚举一致校验"模式，换成领域枚举即可 |
| `strength_scale` 双侧标尺 + `strength_matches[]` | 通用的"主张-证据分级对齐"模式：双侧等级表 + 逐条判定登记 + 机械映射规则 |
| `suppression_rules` + `suppressed[]` | 通用的误报抑制模式：规则表事前声明 + 逐条登记 + 校验 rule_id |
| `pending_review` 登记 | `{finding_id, reason, needed_action}` 通用的人工复核入口格式 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改标签即得新的负例 |

## 14. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明，142 行） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/稿件结构/口径三合一模板（退出码恒 0） | 是 |
| scripts/chain_audit.py | 论证链节点完备 + 六分面×章节覆盖机械审计 | 是 |
| scripts/verify_check.py | 业务校验器（定位回证/分类口径/强度登记/链完备/待复核抑制登记） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（虚构稿件与文献，头标注示意） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案，头标注示意） | 是（fixture） |
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
- 不预置正式案例答案：`examples/` 全部为合成案例并在文件头标注"示意"。
