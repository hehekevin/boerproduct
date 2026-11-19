# quest-search — 科研问题驱动检索 Skill（v1）

针对 Bohrium 产品赛第 4 周「科研问题驱动检索」(challenge-e7598a44) 的参赛 Skill。
锁定子场景：**科研问题拆解 → 检索式规划 → 执行检索 → 相关性判定 → 缺口登记** 的结构化可复跑流程。

## 1. 用途与适用条件

给定科研问题与案例内文献记录集（fixture 快照，无联网数据库），完成六件事：

1. **问题拆解**：把问题填进 `research_question` 六维（对象/机制/方法/时间范围/比较/证据要求）
   + 检索范围 scope；拆成**可检索**的结构化子问题清单 `subquestions[]`。
2. **查询规划**：`query_plan[]` 为子问题安排检索顺序与依赖（前置/并行），
   每条查询做同义词/缩写/上下位**术语扩展**，控制发散。
3. **停止条件事前声明**：检索前写定 `stop_criteria`（declared_before + marginal_rule），
   事后禁止放宽——这是"什么时候可以停"的前置条件，不是事后找理由。
4. **执行检索**：`search_rounds[]` 逐轮记录查询执行、发现与调整，形成可解释的迭代路径。
5. **相关性判定**：`candidates[]` 每条候选保留来源/定位（可追溯）、逐字摘录的
   relevance_basis、included 与排除原因；不补造文献。
6. **缺口登记**：`gaps[]` 按枚举登记 no_result / conflict / metadata_missing / permission
   / other，附 follow_up；缺什么登记什么，不默默跳过。

**核心保证**：每个 relevance_score 数字在 `claims[]` 有证据链（材料逐字摘录 quote +
评分 + 依据说明），数字逐字回证（空白归一化子串匹配，未回证列入 `unbacked_numbers`
并判 FAIL）；verify_check 把每条检查三元组 `{item, template_value, applied, match}`、
闸门状态与 unbacked 清单回写 result.json（键 `self_check` / `gates` /
`unbacked_numbers` / `validator_verdict`），评分器不开附件即可核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 / 研究生 | 复杂科研问题要查文献，不想"一轮关键词打天下" | 子问题清单、查询计划（含术语扩展）、候选集与缺口登记 |
| 系统综述作者 | 筛选过程要可审计、可复核 | 每条候选的来源定位 + 相关性逐字依据 + 排除原因 |
| Agent 开发者 | 给检索 Agent 加结构化检索纪律 | 可复用的拆解/规划/判定/登记模板与机械校验器 |
| 教学 / 培训 | 演示"事前声明停止条件 + 机械校验覆盖"的检索纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不联网检索、不访问外部数据库；单篇精读、全文翻译、写作润色、
开放式科研问答不在范围；不宣称全域召回（finite snapshot only）。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 与 3.12 上实测通过；平台沙箱为 3.12+，命令一律 `python3`） |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 100 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB（本包 10 个文件） |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 材料清单 + 停止条件模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 5：增益对照 + 效率计数（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 6：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

**脚本定位纪律**：一律走固定路径；使用前确认标志文件
`scripts/.package-marker.json`（`package=quest-search`），或跑
`python3 scripts/verify_check.py --selftest`。禁止 `find | head -1` 式定位（会串包）。

## 5. 输入与输出

- **输入**：`/input/case.json`（科研问题 + 文献记录集 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容；合成重复/冲突记录按输入事实处理并如实标注。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`research_question`、`subquestions`、`query_plan`、`search_rounds`、
    `candidates`、`gaps`、`stop_criteria`、`steps`、`reproducibility`、`run_status`、
    `verdict`、`verdict_basis`、`material_gaps`、`environment`、`gain_evidence`、`efficiency`
  - **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
    `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`（校验报告）、`/app/work/schema_guard.json`
  （结构报告）、`/app/work/gain_evidence.json`（增益对照证据）、
  `/app/work/stop_criteria.json`（停止条件声明台账）、
  `/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例：虚构研究问题（锂空位复合体与电导率）+ 3 条虚构记录，
演示问题拆解、查询规划、两轮检索、相关性判定（R3 被排除且给排除原因）、
冲突缺口登记。示意输出关键片段：

```json
{
  "case_id": "demo-quest-001", "status": "answered",
  "result": {
    "subquestions": [{"subq_id": "sq1", "text": "空位聚集是否形成连通锂离子迁移通道？",
                       "query_ids": ["q1"], "status": "covered"}],
    "query_plan": [{"query_id": "q3", "subq_id": "sq3", "phase": 2, "depends_on": ["q1"],
                     "query_string": "grain boundary resistance bulk conductivity perovskite electrolyte",
                     "term_expansions": ["LLTO", "grain-boundary impedance"]}],
    "candidates": [{"candidate_id": "R3", "subq_ids": ["sq3"], "relevance_score": 0.30,
                     "included": false, "exclusion_reason": "无空位复合体证据，仅作机制对照"}],
    "gaps": [{"gap_id": "g1", "subq_id": "sq3", "kind": "conflict",
               "description": "R3 晶界主导 vs R1 空位通道主导", "follow_up": "补对比检索或人工裁定"}],
    "stop_criteria": {"declared_before": "step1", "applied": true},
    "verdict": "search_completed"
  },
  "claims": [{"claim_id": "k3", "kind": "inferred", "location": "candidates[2]",
               "evidence": [{"paragraph_id": "records[2].abstract_excerpt",
                              "quote": "Total conductivity of LLTO is dominated by grain-boundary resistance"}]}]
}
```

## 7. 验收标准与最小可运行自检清单（逐条实测 exit 0）

| 编号 | 自检命令 | 预期（实测见 worklog） |
|------|---------|----------------------|
| S1 | `python3 scripts/verify_check.py --selftest` | 输出 `selftest PASS`，exit 0 |
| S2 | `python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out "$TMP/skel.json" --work-dir "$TMP/wk"` | 骨架落盘，exit 0 |
| S3 | `python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out "$TMP/vc.json"` | `verdict=PASS`，exit 0 |
| S4 | `python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json` | `PASS: 结构完整`，exit 0 |
| S5 | `cp examples/example-result.json "$TMP/demo.json" && python3 scripts/gain_probe.py --result "$TMP/demo.json" --case examples/example-case.json --work-dir "$TMP/wk" --emit-into --inject-pollution` | 双模式实跑 + 污染自测 `caught_by_normal_mode=true`，exit 0 |
| S6 | `python3 scripts/verify_check.py --result "$TMP/不存在.json"` | `FAIL` 但 exit 0（失败路径不中断交付） |
| A1 | 契约字段齐 | S4 `verdict=PASS`（output_contract 全字段 + 本题 16 个业务字段） |
| A2 | 业务逻辑齐 | S3 `verdict=PASS`，`problems` 为空 |
| A3 | 数字全回证 | `unbacked_numbers` 为空数组 |
| A4 | 子问题全覆盖 | 每 subq 有有效 query_id；`reproducibility` 与实际一致 |
| A5 | 候选判定有据 | 每候选有 source/location + relevance_basis；排除有因 |
| A6 | 停止条件事前 | `stop_criteria.declared_before` 非空且有实质规则 |
| A7 | 步骤可重跑 | `steps[]` 非空，至少一条含可执行 `command` |
| A8 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑 + delta + 机制映射 + 边界 + 失效条件 |
| A9 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（子问题覆盖 + 相关性判定 + 缺口登记） | — |
| `degraded` | 查询式合法性/依赖/枚举/结构守卫 | **子问题覆盖校验**（query_coverage + reproducibility 一致性）+ **相关性判定校验**（relevance_basis / exclusion_reason / 数字回证）+ **缺口登记校验**（kind 枚举 + follow_up） |

逐项对照五项指标（全部实测，不臆造）：
`coverage_ratio`（子问题覆盖机器判定占比）、`relevance_missed`（相关性依据缺失漏检数）、
`manual_review_items`（需人工核对条目数）、`steps_count`（步骤数）、
`clarification_rounds`（追问轮次，公式 `ceil(manual_review_items/3)` 随记录落盘）。

同一套校验器对两臂各跑一遍，FAIL 数差与漏检差是机器判定；每项指标都写明
**机制 → 指标映射**（`mechanism_to_metric_map`）、**边界**（`boundaries`）与
**失效条件**（`failure_conditions`）。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 记录集/材料不可访问 | material_gaps 登记，verdict=cannot_verify，绝不编造候选 |
| 查询无结果 | gaps kind=no_result + follow_up，不重试凑数 |
| 证据冲突 | gaps kind=conflict 双方摘录，登记 human_review |
| 元数据缺失/权限不足 | gaps kind=metadata_missing / permission，按现有证据判定并写明 |
| 术语严重歧义 | term_expansions 与 uncertainties 登记，查询串用上位概念兜底 |
| 预算不足 | 保留已覆盖子问题，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| 运行中断 | 仍写 result.json（status=partial），注明中断点与已完成部分 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与
`problems` 列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器
自身故障打断。SKILL.md 协议第 7 条明确"自检只判 verdict"。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**（normal 漏检 0 → degraded 漏检上升），
它的作用是量化"关闭这些机制会漏掉多少"，作为增益证据。SKILL.md 明确：
退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：没有联网检索工具，这个 Skill 的价值是什么？**
把「拆解→检索式→执行→相关性判定→缺口登记」做成结构化可复跑流程：
子问题覆盖、检索式合规、相关性判定有据、缺口登记都有机械校验器兜底，
Agent 自由发挥的部分被压缩到"读材料写依据"，而依据是可以逐字回证的。

**Q：`gain_evidence` 里的数字是真实的吗？**
是。两遍都由 `verify_check.analyze()` 在同一份输入上实跑产出；
`relevance_missed` 的真值由探针独立复算（relevance_basis 为空 / included=false
缺排除原因），与校验层分开算。污染反例只在副本上注入，原 result.json 不被改动。

**Q：为什么 `steps_count` 正常模式反而更大？**
正常模式执行更多检查项，所以步骤数更高——这正是"步骤少不等于质量高"的证据，
`mechanism_to_metric_map` 里对该指标标了 `higher_is_better: null`。

**Q：能不能跳过某个子问题省时间？**
不能。协议第 3 条"广度优先"要求覆盖全部子问题；未挂查询的子问题会被
`verify_check` 记 FAIL（query_coverage）。

**Q：relevance_score 是金标准吗？**
不是——它是本技能基于材料原文的判定分数，必须逐字回证（claim text 含评分数字，
quote 为材料原句）；证据冲突时登记 human_review，不冒充人工标注。

**Q：停止条件可以检索完再补吗？**
不可以。`stop_criteria.declared_before` 必须在检索前写定并同步
`/app/work/stop_criteria.json`；`verify_check` 强校验，缺失即 FAIL。

## 11. 适用范围与限制

- 仅在案例提供的记录集（finite snapshot）上检索：不联网、不访问外部数据库、
  不装 pip 依赖（stdlib-only）；不宣称全域召回、不冒充人工评审。
- 合成重复/冲突记录是输入 fixture，不是期望答案；按输入事实筛查并如实标注。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数；
  原始计数 `manual_review_items` 一并落盘，可换批量重算。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，
  缺失保持 null，不得臆造。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘、不读环境），可直接 `import` 到别的校验器里；`--ablate` 可复用为别处的"机制开关"对照实验 |
| `scripts/gain_probe.py` 的双模式对照 | 换掉 `analyze` 即可测任何校验器的机制增益；指标公式全部写在 `mechanism_to_metric_map` 里，可照抄改造 |
| `subquestions[]/query_plan[]` 模板 | `{subq_id, text, dimension, query_ids}` + `{query_id, subq_id, phase, depends_on, query_string, term_expansions, rationale}` 适用于任何"问题拆解→查询规划"型交付 |
| `gaps[]` 缺口登记格式 | `{gap_id, subq_id, kind, description, follow_up}` 是通用的"缺口显式登记"台账 |
| `stop_criteria` 事前声明台账 | `{declared_before, applied, stop_reason, marginal_rule, rationale}` 适用于任何"何时可以停"型决策 |
| `steps[]` 复现步骤格式 | `{step, action, command, output_ref, status}` 适合任何"他人可重跑"型交付 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` 可直接抄到别的 Skill |
| `scripts/.package-marker.json` 标志文件 | 校验式脚本定位（防串包）可直接移植 |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改记录即得新的负例 |

**建议的复用顺序**：先抄 `verify_check.py` 的 `analyze()` 骨架（拿到三元组 + 闸门 + 回证），
再抄 `gain_probe.py` 的双模式对照（拿到可验证的增益证据），最后按自己的业务 schema
改 `RESULT_REQUIRED` 列表。

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明 + 速查表） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 自动落骨架/材料清单/停止条件模板（三级容错，退出码恒 0） | 是 |
| scripts/verify_check.py | 业务逻辑校验器（子问题覆盖/相关性有据/缺口登记/停止条件/回证/闸门/三元组；含 `--selftest` 包身份校验） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例自测 | 是（含指标公式） |
| scripts/.package-marker.json | 包标志文件（校验式定位，防串包） | 是 |
| examples/example-case.json | 合成输入示例（示意，非正式案例） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式案例答案） | 是（fixture） |
| README.md | 本说明（用途/依赖/安装/输入输出/验收/FAQ/限制/异常/复用/维护） | — |
| worklog.md | 开发记录、真实对照数字与双测证据 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 7 节 S1–S6 自检清单，确认 verdict=PASS、污染被抓。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150、frontmatter name/description 单行合法。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED` 与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注「示意，非正式案例答案」。
