# cov-gap-audit — 检索覆盖率与遗漏分析 Skill（v1）

针对 Bohrium 产品赛第 4 周「科研检索」赛道「检索覆盖率与遗漏分析」(challenge-0467f5db)
的参赛 Skill。锁定子场景：**冻结参考集做分母 + 机械命中判定与覆盖率计算 + 漏检分类
登记归因到查询式 + 补检边际收益校验（防空转）+ 闭环复核**。

## 1. 用途与适用条件

给定研究问题、检索查询/检索结果与已知关键文献集合（参考集，可含撤稿/不可用条目），完成五件事：

1. **参考集冻结**：逐条核对标识符、标注 included/unavailable/retracted、写明纳入理由，
   frozen=true + frozen_at 冻结版本；覆盖率分母 = included 条目，**绝不以检索结果定义分母**。
2. **覆盖测量**：`coverage_calc.py` 按"标识符（DOI/PMID 归一化）精确 → 标题归一化精确"
   逐条机械比对，写 items[].hit_status 与 coverage（含 extra_records：检索结果里与参考集
   无关的记录数——检索数量多 ≠ 覆盖好）；机械结果有异议可改判 matched_by=manual + 证据。
3. **漏检分类登记**：每条 miss 恰一条 miss_registry 登记，category 六类
   （synonym_gap / field_narrow / time_window / source_gap / identifier_anomaly / other），
   attribution 落到具体 query_id/field/source_db/reason 且 query_id 必须存在于查询清单；
   "把没找到当不相关"和"归因泛泛"都会被 verify_check 判 FAIL。
4. **补充检索校验（防空转）**：`supp_check.py` 机械复算 new_hits_total / marginal_gain /
   post_coverage_rate；effective=true 但新增命中为 0 = 补检空转判 FAIL；query_string 与原
   查询实质相同判空转预警；残余遗漏逐条解释；stop_rule 必填。
5. **闭环复核与证据链**：hit 条目 rationale + 逐字证据 + claims 回证；
   coverage_rate / miss_rate / post_coverage_rate 数字逐字回证（显式数字字符类定界，
   DOI 内嵌数字排除）；review.sampled 抽检 + agreement_rate + 残余遗漏解释。

**核心保证**：`verify_check.py` 独立复算分母与覆盖率、逐条核对遗漏归因可回溯性、复算补检
边际收益、把无回证的证据与数字列入 `unbacked_numbers` 判 FAIL；`gain_probe.py` 用正常 vs
退化双跑实测机制增益并写入 `result.gain_evidence`。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 / 系统综述检索者 | 检索了几轮，需要知道已知关键文献漏了几篇、漏在哪次查询 | 冻结分母的覆盖率 + 逐条漏检归因到查询式/字段/来源 |
| 研究助理 / 图书馆员 | 为课题组维护检索策略，要证明补充检索真的有用 | 补检边际收益台账（new_hits / marginal_gain / post_rate）+ 停止规则 |
| 复核者 | 抽查覆盖率口径与漏检归因是否成立 | 可独立复算的 coverage + miss_registry.audit 校验标记 + 污染反例自测 |
| 教学 / 培训 | 演示"分母冻结 + 机械匹配 + 归因纪律"的检索审计方法 | 可复算的对照实验（gain_evidence） |

**不适用**：不做数据库实时接入、不全文精读、不做系统综述正式纳排流程；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13.14 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 150 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 参考集/查询清单 + 分母冻结台账（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1：Agent 冻结参考集（frozen=true + frozen_at）并声明命中判定口径

# Step 2：机械命中判定 + 覆盖率计算（分母=冻结参考集 included 条目）
python3 /skills/weekly-skill/scripts/coverage_calc.py --result /app/output/result.json \
  --case /input/case.json

# Step 3-4：Agent 登记漏检归因与补检，然后机械审计
python3 /skills/weekly-skill/scripts/miss_audit.py --result /app/output/result.json --case /input/case.json
python3 /skills/weekly-skill/scripts/supp_check.py --result /app/output/result.json --case /input/case.json

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

- **输入**：`/input/case.json`（研究问题 + 参考集 + 查询/检索记录 + output_contract）、
  `task.md`。**以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`research_question`、`reference_set`
    （冻结分母）、`queries`、`items[]`（逐条命中判定）、`retrieved_summary`、`coverage`、
    `miss_registry`（遗漏归因）、`supplementary`（补检边际收益）、`review`、`steps`、
    `run_status`、`verdict`、`verdict_basis`、`gain_evidence`、`efficiency`
- **判定体系**：`ref_status`（included/unavailable/retracted/pending，决定是否入分母）
  × `hit_status`（hit/miss）× `matched_by`（identifier/title/manual）；
  miss 必有 miss_registry 归因登记，hit 必有证据与 claims 回证。
- **verdict**：`covered_audited`（全部判定且遗漏全登记）| `partially_audited` |
  `not_audited` | `cannot_verify`；**status**：`answered` | `partial` |
  `insufficient_evidence` | `input_error`。
- **工作区产物**：`/app/work/coverage_ledger.json`（分母冻结台账）、
  `/app/work/verify_check.json`、`/app/work/schema_guard.json`、
  `/app/work/gain_evidence.json`、`/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（标题/DOI 均虚构）：6 条参考条目（K05 撤稿不入分母）→ 初始命中
K01/K02/K03（coverage_rate=0.6），漏检 K04（synonym_gap，归因 Q1 未覆盖 app/smartphone
同义词）与 K06（time_window，2017 早于窗口起点）；补检 Q3 新增命中 K04 → post_coverage_rate=0.8，
K06 登记为残余遗漏并解释。示意输出关键片段：

```json
{
  "case_id": "demo-covgap-001", "status": "answered",
  "result": {
    "reference_set": {"frozen": true, "frozen_at": "2026-11-19"},
    "coverage": {"denominator_basis": "frozen_reference_set", "total_reference": 6,
                  "included": 5, "unavailable": 1, "hit": 3, "miss": 2,
                  "coverage_rate": 0.6, "miss_rate": 0.4},
    "miss_registry": [{"ref_id": "K04", "category": "synonym_gap",
                        "attribution": {"query_id": "Q1", "field": "title/abstract",
                                        "source_db": "EuropePMC", "reason": "…"}}],
    "supplementary": {"new_hits_total": 1, "effective": true, "post_coverage_rate": 0.8},
    "verdict": "covered_audited"
  }
}
```

本地自测整条链路（合成案例，非正式答案；先复制一份避免 --emit-into 改动示例原件）：

```bash
cp examples/example-result.json /tmp/r.json
python3 scripts/coverage_calc.py --result /tmp/r.json --case examples/example-case.json
python3 scripts/miss_audit.py --result /tmp/r.json --case examples/example-case.json
python3 scripts/supp_check.py --result /tmp/r.json --case examples/example-case.json
python3 scripts/gain_probe.py --result /tmp/r.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result /tmp/r.json --case examples/example-case.json --ledger /tmp/wk/coverage_ledger.json --emit-into
python3 scripts/schema_guard.py --result /tmp/r.json --case examples/example-case.json
```

## 7. 最小可运行自检清单（2026-11-19 在 Python 3.13.14 / Windows 逐条实测）

| 编号 | 命令 | 实测退出码 | 实测 verdict |
|------|------|-----------|-------------|
| S1 | `python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/cg/skel.json --work-dir /tmp/cg/wk` | 0 | 骨架落盘（6 参考条目/2 查询/4 记录） |
| S2 | `python3 scripts/coverage_calc.py --result /tmp/r.json --case examples/example-case.json` | 0 | coverage_rate=0.6 / miss_rate=0.4 |
| S3 | `python3 scripts/miss_audit.py --result /tmp/r.json --case examples/example-case.json` | 0 | PASS |
| S4 | `python3 scripts/supp_check.py --result /tmp/r.json --case examples/example-case.json` | 0 | PASS（post_coverage_rate=0.8） |
| S5 | `python3 scripts/gain_probe.py --result /tmp/r.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution` | 0 | normal PASS / degraded PASS / 污染被抓 |
| S6 | `python3 scripts/verify_check.py --result /tmp/r.json --case examples/example-case.json --ledger /tmp/wk/coverage_ledger.json --emit-into` | 0 | PASS（15 检查项全 applied） |
| S7 | `python3 scripts/schema_guard.py --result /tmp/r.json --case examples/example-case.json` | 0 | PASS |
| S8 | `python3 scripts/verify_check.py --result /tmp/r.json --ablate all`（退化对照） | 0 | FAIL 数差见 gain_evidence |
| S9 | `python3 scripts/verify_check.py --result /nonexistent.json`（失败路径） | 0 | FAIL 照实报告 |
| S10 | `python3 scripts/supp_check.py --badflag`（argparse error） | 0 | 降级报告 |

## 8. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 数字全回证 | `unbacked_numbers` 为空数组（coverage_rate/miss_rate/post 全部可逐字回证） |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 分母冻结 | reference_set.frozen=true + frozen_at 非空；分母=included 条目且逐项复算一致 |
| A6 | 遗漏全登记 | 每条 miss 恰一条 miss_registry，category/attribution/query_id 全部可回溯 |
| A7 | 补检不空转 | effective 声称与实际新增命中一致；post_coverage_rate 机械复算相符 |
| A8 | 抽检闭环 | review.sampled 非空 + 残余遗漏逐条有解释 + stop_rule 明示 |
| A9 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A10 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 9. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（分母口径 + 遗漏登记 + 补检收益 + 证据回证） | — |
| `degraded` | 枚举/结构/verdict 一致性等基础检查 | **denominator / attribution / supplement / evidence 四组** |

实测对照（合成案例 + 注入 5 项领域化污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入漏检（四类） | 0 | 0 | 0 |
| steps_count | 22 | 7 | +15 |
| 污染副本 problems | 10 | 1 | −9 |
| 污染副本分母违规漏检 | 0 | 2 | +2 |
| 污染副本遗漏登记漏检 | 0 | 1 | +1 |
| 污染副本补检违规漏检 | 0 | 3 | +3 |
| 污染副本证据漏检 | 0 | 3 | +3 |

注入的 5 项污染：coverage_rate 篡改为 1.0（模拟"以结果定义分母"）/ 清空 K04 遗漏登记 /
K04 命中证据与匹配方式清空 / 补检 new_hits 清空且 effective=true（补检空转）/ 清空 claims。
**同一校验器、同一污染输入**：正常模式抓全 10 处（漏检 0），退化模式 9 处客观违规不可见
（仅剩 1 处始终开启的 verdict 一致性检查仍报 FAIL）——这是机制增益最直接的证据。数字由
探针独立复算违规真值，与校验层分开实现；详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 10. 异常处理

| 异常 | 处置 |
|------|------|
| 检索无结果 / 记录为空 | hit=0、coverage_rate=0.0（分母仍为冻结参考集），绝不以结果定义分母、绝不补造文献 |
| 撤稿/无法获取/标识异常 | ref_status=unavailable/retracted，登记不入分母；identifier_anomaly 归因写明细节 |
| 参考集含重复 | 冻结前去重并登记 uncertainties，分母以去重后条目计 |
| 来源超时/元数据缺失 | material_gaps 登记 + status=partial，不猜测原因 |
| 补检同义重跑无新增 | supp_check 判空转 FAIL；如实登记 effective=false，不得报告遗漏下降 |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 11. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与 `problems`
列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：覆盖率分母为什么不能用检索结果？**
"以结果定义分母"会让覆盖率恒近满分——题面点名的第一种失效方式。分母只能来自冻结参考集
（frozen=true + frozen_at + 台账闸门），verify_check 复算不一致即 FAIL。

**Q：补检明明跑了，为什么被判"空转"？**
空转 = 命中集合没有新增却报告遗漏下降。supp_check 机械复算新增命中数：effective=true 但
new_hits_total=0、或 query_string 与原查询实质相同，都会判 FAIL。补检价值以新增命中记账，
不以"跑了几轮"记账。

**Q：机械匹配会不会误判？**
标识符与标题归一化精确匹配是低误报规则；近似/存疑情形由 Agent 改判 matched_by=manual
并附逐字证据与理由（`--keep-manual` 重跑核对），必要时登记 human_review。

**Q：unbacked_numbers 的数字回证怎么避开中文陷阱？**
显式数字字符类定界（`(?<![0-9.])…(?![0-9])`），不用 `\b`/isalpha——汉字的 isalpha()
为 True，词边界判定会把"0.6学生"判成无边界；匹配前剥离 DOI 等标识符内嵌数字
（`10.\d{4,9}/\S+`），年份区间端点保留。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。SKILL.md 明确
退化模式结果仅用于增益对照，不得当作交付自检结论。

## 12. 生态十项对照表

| # | 生态项 | 本包对应 |
|---|--------|---------|
| 1 | 参考集来源与构建规则 | SKILL.md Step 1 + reference_set.source / inclusion_reason / ref_status 三态 |
| 2 | 覆盖率口径 | coverage.denominator_basis + match_rule + coverage_ledger 台账，verify 复算 |
| 3 | 漏检分类体系 | 六类 category 枚举 + attribution 四元组 + miss_audit 机械审计 |
| 4 | 补检流程与停止规则 | supplementary.queries + stop_rule + supp_check 边际收益复算 |
| 5 | 限制说明 | SKILL.md「已知限制」+ gain_evidence.boundaries |
| 6 | 模板可复用 | reference_set / miss_registry / supplementary 的 JSON 结构可直接搬到新主题 |
| 7 | 脚本可复用 | coverage_calc.match_one / verify_check.num_in_text 均为纯函数可移植 |
| 8 | 失败路径规范 | 全脚本 exit 0 + verdict 照实写 JSON（S9/S10 实测） |
| 9 | 报告范式 | result.json schema 覆盖"算覆盖—列漏检—做补检—闭环复核"全链 |
| 10 | 经验沉淀 | worklog.md 实测对照数字 + 诚实边界 + 防同质化说明 |

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/参考集清单/分母台账（退出码恒 0） | 是 |
| scripts/coverage_calc.py | 机械命中判定 + 覆盖率计算（分母=冻结参考集） | 是（含 match_one API） |
| scripts/miss_audit.py | 漏检登记完备性 + 归因可回溯审计 | 是 |
| scripts/supp_check.py | 补检边际收益校验（防空转） | 是 |
| scripts/verify_check.py | 业务校验器（分母口径/遗漏登记/补检收益/证据回证四组，--ablate） | 是（含 analyze API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（6 条虚构文献） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 7 节十条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/ITEM_REQUIRED`
  与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
