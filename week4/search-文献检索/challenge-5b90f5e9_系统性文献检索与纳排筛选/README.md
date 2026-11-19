# sysrev-search-screen — 系统性文献检索与纳排筛选 Skill（v1）

针对 Bohrium 产品赛第 4 周「科研检索」赛道「系统性文献检索与纳排筛选」
(challenge-5b90f5e9) 的参赛 Skill。锁定子场景：**题录快照上的检索协议声明 +
确定性去重 + 逐条纳排判定 + 双人分歧仲裁 + PRISMA 漏斗计数审计**。

## 1. 用途与适用条件

给定研究问题、纳排标准草案与题录快照（真实署名论文 + 可能混入的重复导出/
分歧夹具，夹具是输入不是期望答案），完成七件事：

1. **检索协议事前声明**：把研究问题（PICO）转成可执行的检索式，写清数据库、
   字段、时间范围、语种限制与检索日期，并逐条说明与纳入标准的对应关系；
   快照模式只对输入题录全集做全记录筛选，不宣称实时全域召回。
2. **标准版本化事前声明**：纳入/排除标准在任何判定**之前**声明版本号与
   declared_at，登记进 criteria_ledger 台账；筛选途中禁止口头修改，确需修改
   必须新增版本并逐条回溯重判（防标准漂移）。
3. **确定性去重**：DOI 归一化精确一致 / 标题归一化精确一致 → 直接合并并保留
   合并依据；标题相似 ≥0.90 → 升级人工确认，不静默合并（防误并不同研究）。
   保留规则固定：published > 有 DOI > 标题长 > 序号小。
4. **逐条纳排判定**：每条题录给 decision（included/excluded/pending_review）+
   理由码（字典 RC-EX-*/RC-PD-*）+ criteria_ref + 逐字摘要证据 + rationale +
   置信度；排除原因枚举完备，excluded_by_reason 分布合计必须等于 excluded。
5. **双人分歧仲裁**：标注者分歧记入 annotation 并登记 conflicts；实质性分歧
   不用平均/多数掩盖——有判据依据则仲裁（arbitrated），不确定则升级人工。
6. **漏斗计数闭合**：PRISMA 五级计数（识别→去重→筛选→纳入/排除/待复核）
   由 flow_audit.py 机械复算并逐级核对，closure=closed 才算闭合。
7. **待复核登记**：每个 pending 条目与升级冲突都进 pending_review
   （含 reason 与 needed_action）；模型输出只是待复核建议，最终纳入由研究者确认。

**核心保证**：`verify_check.py` 机械核对标准事前声明（版本/台账/漂移）、理由码
字典合法性、证据逐字回证、漏斗逐级闭合；`gain_probe.py` 用正常 vs 退化双跑 +
污染反例副本实测机制增益并写入 `result.gain_evidence`。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 系统综述作者 | 检索导出几十上百条题录，要按纳排标准完成可复核的初筛 | 全记录 decision + 理由码 + 逐字证据 + 漏斗计数 |
| 研究助理 / 文献管理员 | 需要向团队解释"为什么这篇被排除、重复怎么合并" | criteria_ref / merge_basis / excluded_by_reason 逐条可回溯 |
| 双人筛选团队 | 两位标注者意见不一致，需要规范的分歧处理 | conflicts 登记 + 仲裁依据 + 升级人工入口 |
| 复核者 / 审稿人 | 质疑"条目数怎么从 N 变成 M" | funnel 五级闭合 + steps 审计日志（in/out 计数逐步可追） |
| 教学 / 培训 | 演示"标准事前声明 + 机械计数 + 分歧仲裁"的筛选纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不做数据库实时检索、不全文精读、不做数据提取/统计分析/论文写作；
缺什么登记什么，不脑补、不补造文献。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math` / `difflib`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 120 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 题录清单 + 标准台账模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-4：Agent 声明检索协议与纳排标准（判定前），然后逐条判定与仲裁
# （见 SKILL.md 八步流程）

# Step 2：机械去重（合并依据写回 conflicts / duplicate_of）
python3 /skills/weekly-skill/scripts/dedupe.py --result /app/output/result.json \
  --apply --report /app/work/dedupe_report.json

# Step 5：漏斗机械复算与闭合审计（写 result.funnel）
python3 /skills/weekly-skill/scripts/flow_audit.py --result /app/output/result.json \
  --report /app/work/funnel_audit.json

# Step 6：增益对照 + 效率计数（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 7：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

## 5. 输入与输出

- **输入**：`/input/case.json`（研究问题 + 纳排标准 + 题录快照 + output_contract）、
  `task.md`。**以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`research_question`(PICO)、
    `search_protocol`、`criteria`(版本化)、`records[]`（逐条判定）、`funnel`、
    `conflicts`、`pending_review`、`coverage`、`steps`、`run_status`、`verdict`、
    `verdict_basis`、`gain_evidence`、`efficiency`
- **判定体系**：`decision`（included/excluded/pending_review）× 理由码字典
  （RC-EX-* 排除 9 码 / RC-PD-* 待复核 5 码）× `confidence`（high/medium/low）。
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`、`/app/work/schema_guard.json`、
  `/app/work/funnel_audit.json`、`/app/work/dedupe_report.json`、
  `/app/work/criteria_ledger.json`（标准台账）、`/app/work/gain_evidence.json`、
  `/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（标题/摘要/DOI 均为虚构）：7 条题录 → 3 included
（R01/R02/R04）、1 excluded（R07 叙述性综述 RC-EX-DESIGN）、1 重复合并排除
（R03 预印本 ← R04 正式版 doi_exact）、2 pending_review（R05 双人分歧升级、
R06 无摘要）。示意输出关键片段：

```json
{
  "case_id": "demo-searchscreen-001", "status": "answered",
  "result": {
    "criteria": {"version": "v1.0", "declared_at": "step1（任何逐条判定之前声明）"},
    "records": [{"record_id": "R03", "decision": "excluded", "reason_code": "RC-EX-DUPLICATE",
                  "duplicate_of": "R04", "merge_basis": "doi_exact", "judged": true}],
    "funnel": {"identified": 7, "duplicates_removed": 1, "screened": 6,
                "excluded": 1, "included": 3, "pending_review": 2,
                "excluded_by_reason": {"RC-EX-DESIGN": 1}, "closure": "closed"},
    "verdict": "screened"
  },
  "claims": [{"claim_id": "c-01", "source_id": "R01",
               "evidence": [{"paragraph_id": "records[0].abstract",
                              "quote": "Working memory reaction times were significantly faster after caffeine (p = .008)"}]}]
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/dedupe.py --result examples/example-result.json --apply --report /tmp/dedupe.json
python3 scripts/flow_audit.py --result examples/example-result.json --report /tmp/funnel.json
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 标准事前声明 | criteria.version/declared_at 非空；台账多版本时判定引用版本 == 最终版本 |
| A4 | 理由码合法 | 每条 excluded/pending 的 reason_code 均在 `resources/reason_codes.json` 字典内 |
| A5 | 全记录覆盖 | coverage.total_records == records 条数，每条 judged=true 或有 pending_reason |
| A6 | 纳排可回溯 | included/excluded 逐条引用存在的 criterion_id；证据逐字回证 claims |
| A7 | 漏斗闭合 | funnel.closure == closed；五级计数与 excluded_by_reason 与逐条复算一致 |
| A8 | 待复核登记 | 每个 pending 条目与 escalated 冲突都进 pending_review（含 reason+needed_action） |
| A9 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A10 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（标准声明核对 + 理由回证 + 漏斗闭合 + 待复核登记） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **criteria / reasons / funnel / pending 四组** |

实测对照（合成案例 + 注入 6 项污染的副本，2026-11-19 实跑，Python 3.13）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入漏检（四类） | 0 | 0 | 0（无违规可漏） |
| steps_count | 42 | 8 | +34 |
| 污染副本 verdict | FAIL（14 处问题） | PASS（0 处） | −14 |
| 污染副本纳排漏检 | 0 | 3 | +3 |
| 污染副本计数漏检 | 0 | 2 | +2 |
| 污染副本证据漏检 | 0 | 5 | +5 |
| 污染副本待复核漏检 | 0 | 3 | +3 |

注入的 6 项污染：R01 判 included 但清空 criteria_ref/evidence_quote；R07 判
excluded 但清空 reason_code/criteria_ref；funnel.included 篡改 +1；R05 清空
pending_reason；清空 pending_review；清空 claims。**同一校验器、同一污染输入**：
正常模式抓全（四类漏检全 0），退化模式 13 处客观违规全部漏掉且 verdict 从 FAIL
翻成 PASS——机制增益最直接的证据。数字由探针独立复算违规真值，与校验层分开实现。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 题录清单为空 | records 空、funnel.identified=0、verdict=cannot_verify 或 not_screened，绝不补造文献 |
| 无摘要/缺 DOI/年份 | missing_metadata 登记 + 置信度降级；无法判定则 pending（RC-PD-NO-ABSTRACT/METADATA） |
| 标准互相冲突 | uncertainties.conflicts 登记双方 + 声明优先序；改标准必须新增版本并回溯重判 |
| 预印本/重复导出 | doi_exact/title_exact 直接合并（保留 published）；title_similar 升级人工 |
| 标注者分歧 | 实质性分歧不掩盖：有判据依据则仲裁，否则 escalated 进 pending_review |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与
`problems` 列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：题面说 search09 有"重复导出/分歧夹具"，Skill 会不会把它们当答案？**
不会。夹具是**输入**：重复导出走 dedupe 的确定性去重（合并依据落 conflicts），
分歧意见走 annotation 记录 + 仲裁流程。SKILL.md 与 examples 均明确标注夹具
不是期望答案，正式结论只能来自实际判定。

**Q：--ablate 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。
SKILL.md 明确退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：标题相似就一定合并吗？**
不。相似度 ≥0.90 只登记为疑似（escalated），必须人工确认后才合并——这正是防止
"两条不同研究因标题相似被误合并"的机械闸门；精确一致（DOI/归一化标题）才直接合并。

**Q：pending 是不是偷懒？**
不是——它是题面要求的"人工最终确认"方向。pending 必须写 pending_reason 并登记进
pending_review（含 needed_action），恰恰是把研究者注意力集中到真正难判的条目上。

**Q：标准中途要改怎么办？**
禁止口头修改（标准漂移）。必须新增版本号登记进 criteria_ledger，并逐条回溯重判
受影响记录；verify_check 会核对判定引用版本与台账最终版本一致。

## 11. 适用范围与限制

- 仅处理输入题录快照：不做实时数据库全域召回、不全文精读、不做系统综述后续阶段。
- 理由码字典是本技能设定的方法学约定（参考 PRISMA 常规排除原因），可按综述扩展并声明版本。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/dedupe.py` 的确定性去重 | DOI/标题归一化 + difflib 相似度 + 三级合并依据 + 保留规则，任何"防误并"需求可直接照抄 |
| `scripts/flow_audit.py` 的漏斗复算 | 五级计数 + 闭合判据 + 存值差异对照，任何"计数闭合"需求可复用 |
| `resources/reason_codes.json` 理由码字典 | 扩展后声明版本即可用于自己的综述；字典与校验器解耦（加载失败回退内置） |
| `criteria_ledger.json` 台账格式 | `{versions, final_version}` 是通用的"标准版本管理"台账 |
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘），`ablate` 参数可直接用作别处的"机制开关"对照实验 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 八步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/题录清单/标准台账模板（退出码恒 0） | 是 |
| scripts/dedupe.py | 确定性去重 + 合并依据登记 + 疑似升级 | 是 |
| scripts/flow_audit.py | PRISMA 漏斗机械复算 + 闭合审计 | 是 |
| scripts/verify_check.py | 业务校验器（标准声明/理由回证/漏斗闭合/待复核登记） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| resources/reason_codes.json | 理由码字典（排除 9 码 + 待复核 5 码，可扩展） | 是 |
| examples/example-case.json | 合成输入示例（7 条虚构题录，含重复对与分歧夹具） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节六条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 扩展理由码字典时同步更新 `resources/reason_codes.json` 并声明新版本号。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
