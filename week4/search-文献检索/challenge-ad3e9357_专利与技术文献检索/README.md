# patent-search-verify — 专利与技术文献检索 Skill（v1）

针对 Bohrium 产品赛第 4 周「科研检索」赛道「专利与技术文献检索」(challenge-ad3e9357)
的参赛 Skill。锁定子场景：**号码规范化 + 专利族归并 + 法律状态登记 + 论文-专利交叉引用回证 + 技术要点摘录 + 待复核登记**。

## 1. 用途与适用条件

给定检索问题、纳排标准与候选条目集（专利 + 技术文献，可能混入同族成员、镜像转载、
OCR 截断夹具），完成六件事：

1. **号码规范化**：公开号/授权号/申请号归一为 `国家码+数字+种类码` 规范形式
   （`norm_family.py` 机械产出），并核对 norm 必须等于 raw 的归一结果——号码失据
   会被校验器判 FAIL。
2. **专利族归并**：按事前声明口径（simple/extended），用规范化优先权号（缺省申请号）
   机械归并族组 `family_groups[]`；无族键条目 `family_id=null` 不臆造族关系；同键成员
   被拆组、幽灵族成员都会被抓。
3. **法律状态登记**：keep 专利条目必须登记 `legal_status`（status/source/query_date/
   lag_note），source 必须在 `sources[]` 登记且标注 green/yellow/red 授权分级——
   转载页面不能冒充官方登记依据。
4. **论文-专利交叉引用**：`cross_refs[]` 逐条登记引证句（逐字摘录）+ 目标条目；
   引证无逐字回证、目标不存在都会被抓。
5. **技术要点摘录**：`tech_points[]` 逐条 `{point_id, quote, location}`，quote 逐字
   来自实际材料，不脑补。
6. **待复核登记**：每个 pending 条目与 escalated 冲突登记进 `pending_review[]`
   （含 reason 与 needed_action），人工复核入口一个不漏。

**核心保证**：`verify_check.py` 独立复算族分组与筛选顺序、逐条核对号码与标签一致性、
把无回证的证据与号码列入 `unbacked_numbers` 判 FAIL；`gain_probe.py` 用正常 vs 退化
双跑实测机制增益并写入 `result.gain_evidence`。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 技术查新 / 专利研究人员 | 拿到一批专利与论文候选，要归并同族、核对法律状态并区分官方/转载来源 | 规范号码 + 族组 + 状态登记（来源/查询日期/滞后） |
| 企业研发情报分析员 | 要判断一个技术主题还有谁在做、这些信息能不能对外展示 | 绿黄红授权分级 + 可回证交叉引用 + 筛选顺序 |
| 复核者 / 专利律师协作方 | 抽查族关系与状态是否对得上登记 | pending_review 清单 + 可机械复算的族分组与顺序 |
| 教学 / 培训 | 演示"口径事前声明 + 机械归并 + 逐字回证"的检索纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不做付费库实时抓取、不绕过付费墙、不做侵权判定/自由实施/专利价值评估；
缺什么登记什么，不脑补。

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
# Step 0：自动落骨架 + 候选清单 + 口径台账模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 声明纳排标准与口径台账（ledger），然后逐条判定（见 SKILL.md 七步流程）

# Step 3：号码规范化 + 族归并 + 筛选排序（写 norm_number/family_id/family_groups/screening）
python3 /skills/weekly-skill/scripts/norm_family.py --result /app/output/result.json

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

- **输入**：`/input/case.json`（检索问题 + 纳排标准 + 候选条目 + output_contract）、
  `task.md`。**以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`research_question`、`criteria`、
    `sources[]`（授权分级）、`items[]`（逐条判定 + 号码 + 族 + 状态 + 交叉引用 +
    技术要点）、`family_groups[]`、`legal_status_registry[]`、`cross_registry[]`、
    `screening`、`coverage`、`conflicts`、`pending_review`、`steps`、`run_status`、
    `verdict`、`verdict_basis`、`gain_evidence`、`efficiency`
- **标签体系**：`relevance`（direct/indirect/irrelevant）× `label`（keep/pending/exclude）
  × `confidence`（high/medium/low）；判定条件与边界约定见 SKILL.md「Step 2」与
  `criteria` 的 criterion_id 编号。
- **授权分级**：`green`（著录项/摘录可展示）| `yellow`（仅登记元数据）|
  `red`（仅登记存在性，不引用原文）。
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`（校验报告）、`/app/work/schema_guard.json`
  （结构报告）、`/app/work/gain_evidence.json`（增益对照证据）、`/app/work/ledger.json`
  （口径台账）、`/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（号码/著录项/摘录均为虚构）：6 条候选 → 3 keep（P01/P02 同族
F-US16123456、P05 论文引证）、1 pending（P04，OCR 截断登记待复核）、2 exclude
（P03 镜像转载归并、P06 主题无关）。示意输出关键片段：

```json
{
  "case_id": "demo-patent-001", "status": "answered",
  "result": {
    "items": [{"item_id": "P01", "norm_number": "US20200123456A1", "label": "keep",
               "criteria_hit": ["IN-01", "IN-02"], "family_id": "F-US16123456",
               "legal_status": {"status": "active（转述）", "source": "src-uspto", "query_date": "2026-11-19"}}],
    "family_groups": [{"family_id": "F-US16123456", "key": "US16123456",
                       "member_ids": ["P01", "P02"], "scope": "simple"}],
    "screening": {"ordered_ids": ["P01", "P02", "P03", "P04", "P05", "P06"]},
    "coverage": {"total_candidates": 6, "judged_items": 6, "keep": 3, "pending": 1, "exclude": 2},
    "verdict": "screened"
  },
  "claims": [{"claim_id": "c-01", "source_id": "P01",
               "evidence": [{"paragraph_id": "candidates[0].abstract",
                             "quote": "a solid electrolyte layer comprising a sulfide-based conductor and a coating layer having a thickness of 5 to 50 nm"}]}]
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/norm_family.py --result examples/example-result.json --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --ledger /tmp/wk/ledger.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 号码/证据全回证 | `unbacked_numbers` 为空数组 |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 全记录覆盖 | coverage.total_candidates == items 条数，每条 judged=true 或有 pending_reason |
| A6 | 判定可回溯 | keep/exclude 逐条引用 criterion_id；irrelevant 不得标 keep |
| A7 | 号码与族可复算 | norm == normalize(raw)；族分组与 screening 顺序与机械复算一致 |
| A8 | 登记完备 | pending/escalated 进 pending_review；keep 专利 legal_status 有 status/source/query_date；来源有授权分级 |
| A9 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A10 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（号码与标签一致性 + 族归并复算 + 证据回证 + 登记完备性） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **numbers / family / evidence / registry 四组** |

实测对照（合成案例 + 注入 6 项污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入漏检（四类） | 0 | 0 | 0 |
| steps_count | 31 | 8 | +23 |
| 污染副本 verdict | FAIL（15 处问题） | PASS（0 处） | −15 |
| 污染副本号码漏检 | 0 | 1 | +1 |
| 污染副本族归并漏检 | 0 | 1 | +1 |
| 污染副本证据漏检 | 0 | 4 | +4 |
| 污染副本登记漏检 | 0 | 1 | +1 |

**同一校验器、同一污染输入**：正常模式抓全（漏检 0），退化模式 7 处客观违规全部漏掉且
verdict 从 FAIL 翻成 PASS——这是机制增益最直接的证据。数字由探针独立复算违规真值，
与校验层分开实现；详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 检索无结果 / 候选集为空 | items 空、coverage.total=0、verdict=cannot_verify 或 not_screened，绝不补造文献 |
| 号码缺失/OCR 截断 | missing_metadata 登记 + 置信度降级；族归属不明则 pending 并登记待复核 |
| 只有二手聚合站数据 | sources[] 登记 red 分级，结论标注「非官方著录项」 |
| 法律状态冲突/过期 | lag_note 写明查询日期与滞后；冲突登记 uncertainties.conflicts |
| 同号转载/镜像 | duplicate_of + conflicts 登记 merged；无法确认则 escalated 进待复核 |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与 `problems`
列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：同族归并会不会把不同专利混成一族？**
不会。族键是规范化后的优先权号（缺省申请号），只有共享同一族键的成员才进同一组；
无族键条目 `family_id=null` 保持独立。simple/extended 口径差异在 ledger 事前声明，
校验器会核对「有族键条目恰好归入一个组、无族键条目不归组」。

**Q：法律状态是官方结论吗？**
不是。legal_status 是登记快照转述，必须带 source（已在 sources[] 登记授权分级）与
query_date，lag_note 说明可能的滞后；verify_check 会抓「keep 专利状态无来源/无查询日期」
和「source 未登记分级」两类违规。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。SKILL.md 明确
退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：为什么 keep 条目必须有逐字证据摘录？**
题面要求"每条结果保留来源和相关性依据，他人可按记录复核"。没有逐字摘录的 keep 会被
verify_check 判 FAIL，norm_number 也要出现在 claim 里（号码回证），防止"号码凭空出现"。

**Q：pending 是不是偷懒？**
不是——OCR 截断、优先权缺失、状态来源不明这类条目标 pending 并登记 needed_action，
恰恰是把人工注意力集中到真正需要回官方库核对的条目上。

## 11. 适用范围与限制

- 仅处理输入候选集内条目：不做付费库实时检索、不绕过付费墙、不上传受限数据。
- 族归并口径以 ledger 事前声明为准，不冒充官方 INPADOC 口径。
- 法律状态是登记快照转述（来源+查询日期+滞后说明），不是官方实时核验结论。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/norm_family.py` 的号码归一 | `normalize_number()` 是独立的纯函数，任何需要专利号规范化的场景可直接调用 |
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘），`ablate` 参数可直接用作别处的"机制开关"对照实验 |
| `expected_families()` 族键复算 | 族键=规范化优先权号（缺省申请号）的确定性归并规则，可直接照抄 |
| `ledger` 台账格式 | `{declared_at, family_scope_default, screening_tie_break, licensing_policy}` 是通用的"事前口径声明"台账 |
| `pending_review` 登记 | `{item_id, reason, needed_action}` 通用的人工复核入口格式 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改标签即得新的负例 |

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/候选清单/口径台账模板（退出码恒 0） | 是 |
| scripts/norm_family.py | 号码规范化 + 族归并 + 确定性筛选排序引擎 | 是（normalize_number 纯函数） |
| scripts/verify_check.py | 业务校验器（号码一致性/族复算/证据回证/登记完备） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（6 条虚构专利/论文） | 是（fixture） |
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
