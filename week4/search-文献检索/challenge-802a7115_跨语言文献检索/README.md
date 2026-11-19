# xling-lit-recall — 跨语言文献检索 Skill（v1）

针对 Bohrium 产品赛第 4 周「科研检索」赛道「跨语言文献检索」(challenge-802a7115)
的参赛 Skill。锁定子场景：**有据术语映射 + 逐语种检索式构建 + 语言/版本判定 +
多语种版本归并 + 语言覆盖矩阵一致 + 翻译歧义待复核登记**。

## 1. 用途与适用条件

给定研究问题、目标语种与候选记录集（同一研究的多语种视图：原文、出版方全文译本、
仅英文摘要、精确重复等），完成六件事：

1. **术语映射有据**：`term_map[]` 每条映射（同义词/缩写/音译/本地译名/词形变体）必须
   附逐字证据（evidence_quote + 位置），校验器会机械核对证据在案例材料中的回证；
   词面多读法（缩写跨学科歧义、音译多解）登记进 `ambiguities[]`。
2. **逐语种检索式机械构建**：`build_queries.py` 从术语表机械派生每语种
   `"词1" OR "词2"` 检索式（可由 entry_id 回溯到映射依据），不引入模型自由发挥。
3. **语言与版本判定**：每条记录标注 `body_language`（可调 `lang_detect.py` 辅助，
   显式 Unicode 字符类，**不用 isalpha**）+ `version`（original/translation/
   abstract_only/bilingual），都须给 language_evidence / version_evidence。
4. **跨语言版本归并**：同一研究的多语种视图 → `clusters[]`（正本=原文版）+
   `duplicate_of`，同 DOI 同题的精确重复必须归并，不得重复计数；确认不了同一性则
   escalated 进待复核。
5. **语言覆盖矩阵一致**：`coverage_matrix[]` 每个目标语种一行，queries_issued /
   records_found / kept / pending / excluded 与 result.queries、result.items 机械
   对账；目标语种无检索式又无 gap_note 会被判违规——不静默漏语种。
6. **歧义与待复核登记**：needs_review 的翻译歧义、pending 条目、escalated 簇成员
   全部登记进 `pending_review[]`（含 reason + needed_action）。

**核心保证**：`verify_check.py` 五组可消融校验（termmap/cluster/coverage/evidence/
pending）+ 恒开的排序复算与语种登记校验；`gain_probe.py` 正常 vs 退化双跑实测机制
增益并注入污染反例自测。评分器不开附件即可通过 `self_check / gates /
unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 | 只用母语提问，怕漏掉非英语的原始研究 | 逐语种检索式 + 覆盖矩阵（每个语种找没找、找到几条一目了然） |
| 系统综述初筛者 | 同一论文以多语种版本重复出现，指标虚高 | clusters 归并 + 正本标注，重复计数被机械拦截 |
| 研究助理 | 需要解释"这条日文记录为什么待定" | 逐条 language/version evidence + 歧义 readings + 待复核入口 |
| 教学/培训 | 演示"术语映射带证据、矩阵可对账"的检索纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不做数据库实时检索、不整篇翻译、不做未经授权的数据抓取；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13.14 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 200 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB（本包 12 个文件） |
| 中文处理 | 全部脚本**禁用 isalpha**（汉字 isalpha()==True 会误判），用显式字符类 |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 候选清单 + rubric 模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-3：Agent 声明目标语种/术语表/rubric，build_queries 机械构建检索式，逐条判定
#   （见 SKILL.md 八步流程）

# Step 4：机械复算分数并排序（写 result.ranking / fused_score / rank）
python3 /skills/weekly-skill/scripts/score_rank.py --result /app/output/result.json --k 10

# Step 6：增益对照 + 效率计数（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 7：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

**最小自检清单**（合成示例，2026-11-19 实测，全部退出码 0）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk   # exit 0 ✓
python3 scripts/lang_detect.py --text "ピロプトーシスと炎症性腸疾患"            # exit 0 ✓ guess=ja
python3 scripts/build_queries.py --result examples/example-result.json          # exit 0 ✓ 4 语种检索式
python3 scripts/score_rank.py --result examples/example-result.json --k 3 --dry-run  # exit 0 ✓
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --rubric /tmp/wk/rubric.json  # exit 0 ✓ verdict=PASS
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json  # exit 0 ✓ verdict=PASS
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution  # exit 0 ✓ caught_by_normal_mode=true
```

## 5. 输入与输出

- **输入**：`/input/case.json`（研究问题 + 候选记录 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`research_question`（含
    `target_languages`）、`criteria`、`rubric`、`term_map[]`、`queries[]`、`items[]`
    （逐条语种/版本/相关性判定）、`clusters[]`、`ambiguities[]`、`coverage`、
    `coverage_matrix[]`、`pending_review`、`steps`、`run_status`、`verdict`、
    `verdict_basis`、`gain_evidence`、`efficiency`
- **标签体系**：`relevance`（direct/indirect/irrelevant）× `label`（keep/pending/exclude）
  × `version`（original/translation/abstract_only/bilingual/unknown）× `body_language`。
- **status**：`answered` | `partial` | `insufficient_evidence` | `input_error`。
- **工作区产物**：`/app/work/verify_check.json`、`schema_guard.json`、
  `gain_evidence.json`、`rubric.json`、`gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（标题摘要 DOI 均虚构，**非正式答案**）：
6 条记录（3 项研究 × 多语种视图，含 1 个出版方全文译本、1 个仅摘要日文索引抄录、
1 个精确重复）→ 3 keep（V01 fused=0.96 排第 1、V04 0.92、V06 0.79）、
1 pending（V03，语种/版本/同一性待核 + 歧义 A02）、2 exclude（V02 出版方译本归并、
V05 精确重复归并）。示意输出关键片段：

```json
{
  "case_id": "demo-xling-001", "status": "answered",
  "result": {
    "term_map": [{"entry_id": "T01", "source_term": "细胞焦亡", "target_term": "pyroptosis",
                  "variant_type": "synonym", "evidence_quote": "本研究探讨细胞焦亡在肠道炎症中的作用及机制"}],
    "queries": [{"query_id": "Q-zh-01", "language": "zh", "query_string": "\"炎症性肠病\" OR \"细胞焦亡\"", "built_from": ["T01", "T05"]}],
    "clusters": [{"cluster_id": "W1", "member_ids": ["V01", "V02"], "canonical_id": "V01", "basis": "doi", "resolution": "merged"}],
    "coverage_matrix": [{"language": "en", "queries_issued": 1, "records_found": 3, "kept": 1, "pending": 0, "excluded": 2}],
    "verdict": "retrieved"
  },
  "claims": [{"claim_id": "c-01", "source_id": "V01", "text": "…fused_score=0.96（0.5*1.0 + 0.3*1.0 + 0.2*0.8）…"}]
}
```

本地自测整条链路见第 4 节"最小自检清单"。

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS` |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 数字全回证 | `unbacked_numbers` 为空数组（标识符内嵌数字不作回证、区间端点保留） |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 全记录覆盖 | coverage.total_candidates == items 条数，每条 judged=true 或有 pending_reason |
| A6 | 映射有据 | term_map 每条有 evidence_quote，可机械回证到案例材料 |
| A7 | 归并正确 | duplicate_of ⇒ clusters 登记 merged/escalated 且正本一致；精确重复被机械捕获 |
| A8 | 矩阵一致 | coverage_matrix 行集合与每行计数与 queries/items 机械对账通过 |
| A9 | 待复核登记 | pending 条目 + needs_review 歧义 + escalated 簇成员全部进 pending_review |
| A10 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑 + delta + 机制映射 + 边界 |
| A11 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（术语映射 + 归并 + 覆盖矩阵 + 证据 + 待复核 + 恒开的排序/语种登记） | — |
| `degraded` | 枚举/结构/排序复算/coverage 汇总 | **termmap / cluster / coverage / evidence / pending 五组** |

实测对照（合成案例 + 注入 7 项污染的副本，2026-11-19 实跑，Python 3.13.14）：

| 指标 | normal | degraded | delta(degraded−normal) |
|------|--------|----------|------------------------|
| 污染副本 verdict | FAIL（12 处问题） | FAIL（1 处，仅排序复算恒开） | −11 |
| 术语映射漏检 | 0 | 1 | +1 |
| 归并漏检 | 0 | 1 | +1 |
| 覆盖矩阵漏检 | 0 | 1 | +1 |
| 证据漏检 | 0 | 10 | +10 |
| 待复核漏检 | 0 | 1 | +1 |
| steps_count（干净输入） | 32 | 20 | +12 |

注入的 7 项污染：T01 清空 evidence_quote；V02 清空 duplicate_of；V01 清空
criteria_hit/evidence_quote 并篡改 fused_score=9.9999；coverage_matrix en 行
records_found+1；歧义 A02 needs_review 改 resolved；清空 pending_review；清空 claims。
正常模式抓全（caught_by_normal_mode=true），退化模式五类违规 14 处客观违规漏检 13 处——
这是"同一校验器双跑 FAIL 差"最直接的机制增益证据。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 检索无结果 / 候选集为空 | items 空、coverage.total=0、verdict=cannot_verify 或 not_retrieved，绝不补造文献 |
| 术语无对应译法 | 不硬造映射；登记 uncertainties.unverifiable，该语种降级为核心词并写 gap_note |
| 语种识别不确定 | body_language=unknown + 依据缺口写明，进 pending_review |
| 同一论文多语种版本 | duplicate_of + clusters 登记 merged（保留原文版正本）；无法确认则 escalated 进待复核 |
| 词面对应语义存疑 | ambiguities 登记 readings，needs_review 进 pending_review，必要时回译复核 |
| 翻译服务失败/限额 | 受影响语种在 coverage_matrix.gap_note 登记，run_status=partial |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与 `problems`
列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：term_map 的证据从哪来？许可如何？**
正式运行时逐条从平台案例材料（候选标题/摘要/正文）中**逐字摘录**并注明位置，
校验器机械回证；examples 中的术语表为合成虚构，仅示意格式。`lang_detect.py` 内置
的拉丁语种停用词表为高频常用词（自建、可扩展），不构成外部依赖。

**Q：语种清单是谁定的？**
`research_question.target_languages` 由 Agent 在 Step 1 事前声明，之后禁止增删；
出现清单外语种必须先登记（覆盖矩阵加行）才可标注，"静默新增语种"会被判违规。

**Q：为什么不用机器翻译整句检索？**
题面明确整句机翻三类错误（术语字面化、用词不一致、语义错配）。本技能只做**有据的
术语级映射**（每条带逐字证据），并强制歧义登记与回译复核入口，把"词面对应语义不同"
的假阳性交给人工抽检，不冒充自动翻译质量。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。SKILL.md 明确
退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：pending 是不是偷懒？**
不是——语种判不准、版本存疑、同一性确认不了就该 pending 并登记 needed_action，
这正是把人工注意力集中到真正难判的记录上。

## 11. 适用范围与限制

- 仅处理输入候选集内记录：不做数据库实时检索、不整篇翻译、不做未经授权的数据抓取。
- `lang_detect.py` 只做字形判定与停用词辅助猜测，区分不了同一字形的多门语言（如 pt/es），
  最终语种判定以 Agent 结合元数据为准。
- crosslang/recency 归一化口径按 rubric 声明的规则计算，口径是本技能设定，不冒充外部标准。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，原始计数一并落盘。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘），`ablate` 参数可直接用作别处的"机制开关"对照实验 |
| `scripts/build_queries.py` | 术语表 → 检索式的机械派生（built_from 可回溯），任何"映射驱动生成"需求可直接照抄 |
| `scripts/lang_detect.py` | 显式字符类语言判定（不依赖 isalpha，中文安全），可独立用于任何文本语种粗判 |
| `coverage_matrix` 台账格式 | `{language, queries_issued, records_found, kept, pending, excluded, gap_note}` 通用的"覆盖对账"台账 |
| `pending_review` 登记 | `{item_id, reason, needed_action}` 通用的人工复核入口格式 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改标签即得新的负例 |

## 13. 资源清单

| 文件 | 行数 | 作用 | 可否单独复用 |
|------|------|------|------------|
| SKILL.md | 150 | 技能本体（8 条强制协议 + 八步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | 223 | Step 0 落骨架/候选清单/rubric 模板（退出码恒 0） | 是 |
| scripts/build_queries.py | 140 | 术语表机械派生逐语种检索式（键归属：result.queries） | 是 |
| scripts/lang_detect.py | 145 | 显式字符类语言判定辅助（零依赖、中文安全） | 是 |
| scripts/score_rank.py | 183 | 多因子机械打分 + 确定性排序 + 平局登记 | 是 |
| scripts/verify_check.py | 578 | 五组业务校验 + 回写 self_check/gates/unbacked_numbers/validator_verdict | 是（含 `analyze()` API） |
| scripts/schema_guard.py | 157 | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 588 | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | — | 合成输入示例（6 条虚构记录，3 works/6 views） | 是（fixture） |
| examples/example-result.json | — | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 4 节七条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/ITEM_REQUIRED`
  与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；本包 12 个文件约 200 KB，
  新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
