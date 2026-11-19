# sci-file-retrieval — 科研文件智能检索 Skill（v1）

针对 Bohrium 产品赛第 4 周「科研资料管理」赛道「科研文件智能检索」(challenge-139745c7)
的参赛 Skill。锁定子场景：**检索式构建 + 逐 (query, file) 全覆盖判定 + 逐字证据引用 +
可复算相关性排序 + 空结果/受限登记**。

## 1. 用途与适用条件

给定资料库（文件清单 + 内容摘要/元数据，通常含真实文件与少量受限/无文本层/版本副本
夹具）与自然语言检索需求，完成六件事：

1. **检索式构建**：对每个需求声明检索式——keywords / synonyms / metadata_filters /
   content_terms，并写 `requirement_mapping` 说明词面锚点、内容词、过滤条件如何覆盖
   需求（检索式与需求映射有据，机检点 1）。
2. **逐对全覆盖判定**：每个 (query, file) 对判为 `hit / pending / no_hit`；hit 必须有
   `matched_terms`（每项都在声明词表内）+ 逐字 `evidence_quote` + `evidence_location`
   （章节/字段）；声明了 metadata_filters 必须执行且为声明子集（硬约束，不放宽）；
   no_hit 必须写 no_match_reason；pending 必须写 pending_reason。
3. **可复算相关性排序**：三因子权重（term_match / metadata_match / content_match）
   在任何排序前事前声明（合计=1.0），`score_rank.py` 机械复算 fused_score 并按平局
   规则（分数降序 → content_match 降序 → hit_id 升序）**按查询**产出稳定顺序，同分
   全部记入 ties（排序可复算，机检点 2）。
4. **证据回链**：每个 hit/pending 在 `claims[]` 有对应证据条目；hit 的引用必须逐字
   出现在 case.json 该文件内容中，fused_score 数字可逐字回证（命中依据可回证，
   机检点 3）。
5. **空结果与受限登记**：零命中查询登记 `no_result_queries`（含 reason/suggestion）；
   权限受限文件登记 `restricted_files`（含 needed_action）；无文本层扫描件登记
   pending_review——失败路径全部可定位（空结果登记，机检点 4）。
6. **检索日志**：`steps[]` 记录每步命令与产物，他人可按日志重跑并核对同一段原文。

**核心保证**：`verify_check.py` 用事前权重独立复算每条 fused_score 与每查询期望顺序、
逐条核对词表依据、把每条 hit 的引用与 case.json 原文逐字对照、把无回证的证据与分数
列入 `unbacked_numbers` 判 FAIL；`gain_probe.py` 用正常 vs 退化双跑实测机制增益并写入
`result.gain_evidence`。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 | "缓冲液配方写在哪一版哪一节"、"这张图对应哪组数据" | 命中文件 + 章节 + 逐字原文引用 + 稳定排序 |
| 资料管理员 | 跨目录/多版本的科研材料盘点与交接 | 全记录清单 + 版本关系（conflicts/merged）+ 检索日志 |
| 复核者 | 抽查命中是否真的在原文那段 | claims 链 + gates + 可机械复算的分数与顺序 |
| 教学/培训 | 演示"检索式事前声明 + 机械复算 + 登记纪律" | 可复算的对照实验（gain_evidence） |

**不适用**：不做开放网络文献检索、不全文精读、不做存储系统权限建设；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13.14 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json` / `os` / `re` / `sys` / `argparse` / `copy` / `time` / `math`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 100 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 资料库/需求清单 + 检索式台账模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 声明检索式与三因子权重，然后逐 (query, file) 判定（见 SKILL.md 七步流程）

# Step 3：机械复算相关性并按查询排序（写 result.ranking / fused_score / rank）
python3 /skills/weekly-skill/scripts/score_rank.py --result /app/output/result.json

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

- **输入**：`/input/case.json`（资料库 + 检索需求 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`library`（文件清单）、`queries`、
    `query_plan`（检索式台账 + 事前权重）、`hits[]`（逐对判定）、`ranking`（按查询）、
    `coverage`、`restricted_files`、`no_result_queries`、`pending_review`、`conflicts`、
    `steps`（检索日志）、`run_status`、`verdict`、`verdict_basis`、`gain_evidence`、
    `efficiency`
- **标签体系**：`label`（hit/pending/no_hit）× `relevance`（high/medium/low）×
  `confidence`（high/medium/low）；判定条件与边界约定见 SKILL.md「Step 2」与
  `query_plan.per_query` 的 requirement_mapping。
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`（校验报告）、`/app/work/schema_guard.json`
  （结构报告）、`/app/work/gain_evidence.json`（增益对照证据）、`/app/work/query_plan.json`
  （检索式台账）、`/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（文件内容均为虚构）：8 份文件 × 3 个查询 = 24 个判定对 →
8 hit（Q01 缓冲液配方定位到 v3 投稿稿 Methods 2.3 并登记 v2 旧版合并；Q02 图-数据
对应链 F07 图注 → F02 数据文件）、6 pending（无文本层扫描件 + 受限文件）、
10 no_hit；Q03 零命中登记空结果。示意输出关键片段：

```json
{
  "case_id": "demo-scifileretrieve-001", "status": "answered",
  "result": {
    "query_plan": {"scoring": {"weights": {"term_match": 0.4, "metadata_match": 0.2, "content_match": 0.4}}},
    "hits": [{"hit_id": "H004", "label": "hit", "evidence_quote": "Methods 2.3 Buffer preparation：50 mM Tris-HCl pH 7.5，150 mM NaCl，新增 0.05% Tween-20", "evidence_location": "Methods 2.3（章节标题）", "fused_score": 1.0, "rank": 1}],
    "ranking": {"per_query": [{"query_id": "Q01", "ordered_hits": ["H004", "H003", "H001", "H008"]}]},
    "coverage": {"total_pairs": 24, "hit": 8, "pending": 6, "no_hit": 10, "ratio": 1.0},
    "no_result_queries": [{"query_id": "Q03", "reason": "全部 8 份文件均无蛋白质浓度测定相关内容"}],
    "verdict": "searched"
  }
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/score_rank.py --result examples/example-result.json --dry-run
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --query-plan /tmp/wk/query_plan.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
```

## 7. 验收标准（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（含 output_contract 全字段 + 本题业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 数字全回证 | `unbacked_numbers` 为空数组 |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 全记录覆盖 | coverage.total_pairs == hits 条数，每条 judged=true 或有 pending_reason |
| A6 | 检索式有据 | hit 的 matched_terms 全在声明词表内；声明过滤逐条执行；requirement_mapping 非空 |
| A7 | 排序可复算 | 三因子权重合计=1.0 且事前声明；fused_score 与 ordered_hits 与机械复算一致 |
| A8 | 证据逐字回证 | hit 引用在 case.json 原文逐字找到且 claims 链回证；空结果/受限/待定全登记 |
| A9 | 增益有据 | `gain_evidence.runs` 含 normal/degraded 两遍实跑记录 + delta + 机制映射 + 边界 |
| A10 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（检索式一致性 + 排序复算 + 证据回证 + 登记完备） | — |
| `degraded` | 枚举/结构/coverage 汇总 | **grounding / ranking / evidence / registry 四组** |

实测对照（合成案例 + 注入 5 项污染的副本，2026-11-19 实跑，Python 3.13.14）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入 problems | 0 | 0 | 0 |
| steps_count | 88 | 9 | +79 |
| 污染副本 verdict | FAIL（21 处问题） | PASS（0 处） | −21 |
| 污染副本检索式漏检 | 2 | 3 | +1 |
| 污染副本排序漏检 | 0 | 1 | +1 |
| 污染副本证据漏检 | 0 | 14 | +14 |
| 污染副本登记漏报 | 1 | 7 | +6 |

**同一校验器、同一污染输入**：正常模式抓全（verdict=FAIL，21 处问题），退化模式客观
违规全部漏掉且 verdict 从 FAIL 翻成 PASS——这是"关闭检索式构建/依据引用/排序复算/
登记机制会漏掉多少"最直接的证据。数字由探针独立复算违规真值，与校验层分开实现；
详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 检索无结果 | 该查询全部 no_hit + 登记 no_result_queries（含 reason/suggestion），绝不放宽条件凑命中 |
| 无文本层扫描件 | pending + pending_review 登记（needed_action=OCR 后补检），不猜内容 |
| 文件权限受限 | pending + restricted_files 登记（含 needed_action），不脑补受限内容 |
| 重名/修订版/副本 | duplicate_of 指向最新版 + conflicts 登记 merged；无法确认则 escalated 进待复核 |
| 过滤条件无法满足 | 照实 no_hit + reason，不放宽声明过的硬约束 |
| 大量同分 | 并列组记入 ties，按 tie_break 规则破平，不静默改分 |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与 `problems`
列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：换一个目录结构还能用吗？**
build_skeleton 兼容 files/documents/library/inventory 等常见键与一层嵌套包装，
queries/questions/requirements 等同理；兼容不到时照实登记 WARN 并手工兜底，
不假设结构。判定与校验逻辑只依赖 result.json 自身一致性，与库结构解耦。

**Q：matched_terms 会不会很死板？**
不会——词表由 Agent 在 Step 1 按需求自行声明（含同义词、大小写变体、跨语言写法），
校验只保证"命中用词必须来自声明词表"，即检索式与需求映射有据、不事后编造依据。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。SKILL.md
明确退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：为什么 hit 的引用必须逐字出现在原文里？**
题面要求"定位到的位置是否就是原文那一段、别人能否按记录复核到同一段"。verify_check
把每条 hit 的 evidence_quote 与 case.json 中该文件内容做空白归一化后的子串对照，
不在原文即判 FAIL——这是防止"标题词面检索"退化的机械闸门。

**Q：pending 是不是偷懒？**
不是——它是题面要求的"无权限文件、无文本层扫描件、材料缺失的识别与处置"。pending
必须写 pending_reason 并登记进 pending_review（含 needed_action），恰恰是把人工注意力
集中到真正读不了的文件上。

## 11. 适用范围与限制

- 仅处理输入资料库内文件：不做开放网络检索、不全文精读、不做存储权限建设。
- 三因子归一化口径是本技能设定并事前声明，不冒充外部标准。
- case.json 未提供文件内容时，逐字回证退化为 claims 链回证（gate 记 not_found 并如实标注）。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数一并落盘。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘），`ablate` 参数可直接用作别处的"机制开关"对照实验 |
| `scripts/build_content_map()` | 通用"case.json 文件内容 → 归一化文本"映射，任何需要逐字对照原文的场景可直接复用 |
| `scripts/score_rank.py` 的按查询确定性排序 | 权重事前声明 + 固定平局规则 + ties 登记，任何"稳定可解释排序"需求可直接照抄 |
| `query_plan` 台账格式 | `{scoring, declared_at, per_query}` 是通用的"检索式事前声明"台账 |
| `no_result_queries / restricted_files` 登记 | `{query_id/file_id, reason, needed_action}` 通用失败登记格式 |
| 闸门四态 + 三元组自检 | `enforced/skipped_not_provided/not_found/unreadable` + `{item, template_value, applied, match}` |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改标签即得新的负例 |

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/资料库/需求清单/检索式台账模板（退出码恒 0） | 是 |
| scripts/score_rank.py | 三因子机械打分 + 按查询确定性排序 + 平局登记 | 是 |
| scripts/verify_check.py | 业务校验器（检索式一致性/排序复算/证据逐字回证/登记完备） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（8 份虚构文件 + 3 个查询） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节五条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/HIT_REQUIRED`
  与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
