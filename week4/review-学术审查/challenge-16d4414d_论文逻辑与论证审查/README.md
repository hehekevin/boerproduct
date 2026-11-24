# evidence-support-review — 论文证据支撑核查 Skill（v2 极简重构版）

针对 Bohrium 产品赛第 4 周「学术审查」赛道「论文逻辑与论证审查」(challenge-16d4414d)
的参赛 Skill。锁定**单一方向**：**证据支撑核查**——从摘要与结果抽取作者核心主张，
逐条判断"支撑证据是否存在 + 是否足以支撑该强度的表述"，识别"结论超出数据"与
"引用不支持观点"。论证链完整性、章节衔接一致性、严重度分级建议三方向**刻意不做**。

## 1. 用途与适用条件

给定一篇固定稿件（论文/科研材料）与审查要求，完成四件事：

1. **核心主张抽取（只做摘要+结果）**：每案例 5-10 条，写进 `result.claims[]`，
   每条带 claim_strength×evidence_strength×judge 强度匹配判定。
2. **证据支撑逐条核查**：对每条主张判断证据有无（E0 无实证 / 有实证）与强度
   是否足够（C3须E3、C2须≥E2），识别"结论超出数据"。
3. **定位可回证**：每条发现与主张的 quote 空白归一化后逐字回证于稿件原文，
   定位到句位——评审直接回原文核对，不落到章节名就完事。
4. **待复核登记**：参考文献无法获取、证据无法核对的条目标 pending 并登记
   `pending_review[]`——不凭空补结论。

**核心保证**：`evidence_check.py` 把每条确认发现与主张的引文做空白归一化后逐字
回证于稿件原文（引文不在原文 = 定位失据 = FAIL）、核对三口径声明、枚举合法、
C3须E3 标尺规则、pending/suppressed 登记与 coverage 一致性。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 投稿前自查的科研人员 | 想知道"每个结论有没有证据、证据够不够" | 主张清单 + 强度匹配判定 + 逐条发现 |
| 审稿人 / 审稿助理 | 需要判断结论是否超出数据 | 超出数据/证据不足的条目，位置+严重度+改法 |
| 复核者 | 回原文逐条核对审查结论 | quote 逐字回证 + 复跑命令 |

**不适用**：不做外部文献检索、不查重、不润色、不做统计复算；不做论证链追踪、
不做章节衔接一致性审查、不做严重度分级建议体系。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部参数化） |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500KB、总计 ≤2MB（本包 8 个文件，约 115KB） |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 稿件结构清单 + 口径模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 声明三口径（证据标尺/严重度/问题类型），然后抽主张 + 逐条核查（见 SKILL.md 五步流程）

# Step 3：机械校验与覆盖计数（写 self_check / gates / validator_verdict / coverage / unchecked）
python3 /skills/weekly-skill/scripts/evidence_check.py --result /app/output/result.json \
  --case /input/case.json --ledger /app/work/rubrics.json \
  --out /app/work/evidence_check.json --emit-into

# Step 4：结构守卫（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

## 5. 输入与输出

- **输入**：`/input/case.json`（稿件 + 审查要求 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `uncertainties` / `changelog` + `self_check` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`manuscript_overview`、
    `evidence_scale`、`severity_rubric`、`issue_taxonomy`、`suppression_rules`、
    `claims[]`（主张+强度匹配）、`findings[]`（逐条发现）、`suppressed[]`、
    `pending_review[]`、`clearances[]`、`coverage`、`unchecked`、`steps`、
    `run_status`、`verdict`、`verdict_basis`、`gain_evidence`、`efficiency`
- **五类问题**：`no_evidence` / `insufficient_evidence` / `strength_mismatch` /
  `citation_unsupported` / `overgeneralization` × 四类区分
  （fact_error / insufficient_evidence / norm_issue / suggestion） × 三级严重度。
- **强度判定**：judge ∈ `supported` / `overstated` / `understated` / `pending`。
- **verdict**：`audited` / `partially_audited` / `not_audited` / `cannot_verify`。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（论文/数据/文献均为虚构，文件头已标注示意）：
5 章节虚构稿件 → 8 条主张 → 6 条发现（5 confirmed + 1 pending）。本地自测：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/evidence_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk/rubrics.json --out /tmp/ec.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 7. 异常处理

| 异常 | 处置 |
|------|------|
| 稿件解析失败 / 输入不可读 | material_gaps 登记 + verdict=cannot_verify，绝不编造审查结论 |
| 图表无法读取 | clearances 登记 artifact:* 豁免 + material_gaps 注明 |
| 参考文献缺失/全文未获取 | 标 pending + 登记 pending_review（含 needed_action） |
| 对照组/假设情形/转述观点 | 按 FP-01/02 标 suppressed 并登记，不报成作者自相矛盾 |
| 稿件超长/预算不足 | 保留已审部分，unchecked 登记未审范围，status=partial |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 8. 已知限制

- 只审查输入稿件本身与其自带参考文献：不做外部检索、不查重、不润色、不复算统计。
- 锁定证据支撑核查单方向：不做论证链完整性、章节衔接一致性、严重度分级建议。
- 三口径（证据标尺/严重度/问题类型）是本技能事前声明的设定，不冒充期刊官方标准。
- 引文回证是"逐字出现于稿件原文"的机械下界；主张抽取与强度定级靠语义判断。
- 增益层在预算过半即降级为 available=false，不编造对照数字；平台白板对照由平台生成。

## 9. 资源清单

| 文件 | 作用 |
|------|------|
| SKILL.md | 技能本体（4 条铁纪律 + 五步流程 + schema + 校验说明，112 行） |
| scripts/build_skeleton.py | Step 0 落骨架/稿件结构/口径模板（退出码恒 0） |
| scripts/evidence_check.py | 机械校验（定位回证/口径一致/登记一致）+ 覆盖计数 |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 |
| examples/example-case.json | 合成输入示例（虚构稿件，头标注示意） |
| examples/example-result.json | 示意输出（非正式答案，头标注示意） |
| README.md | 本说明 |
| worklog.md | 开发记录与诚实边界 |