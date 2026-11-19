# lit-search-pro — 学术文献检索 Skill（v1）

针对 Bohrium 产品赛第 4 周「科研检索」赛道「学术文献检索：找到文献，也保留筛选依据」
(challenge-a2909a72) 的参赛 Skill。锁定子场景：**开放学术数据库上的检索规划、
关键词扩展、去重与来源可追溯**。

## 1. 用途与适用条件

给定一个科研问题与检索响应材料（Crossref / EuropePMC / OpenAlex 等真实响应片段），
完成六件事：

1. **多轮查询规划**：把科研问题拆成 round1 核心术语 / round2 扩展术语 /
   round3 相关与上位术语 / round4 补漏验证的四轮计划（`query_plan[]`），
   每轮带数据库组合与目的。
2. **关键词扩展**：机械生成同义词、缩写展开（内置常见学术缩写表）、复数/
   连字符变体、相关概念（`keyword_expansion[]`），每条带 `kind` 与 `source_basis`
   （规则名或材料位置），Agent 可人工补充领域私有缩写。
3. **执行与逐条登记**：每次查询尝试（含空结果）记入 `queries_executed[]`；
   每条命中文献记入 `papers[]`，必须带 `source_db` + `matched_queries` +
   `rationale` 三要素，缺一即不可追溯（校验器判 FAIL）。
4. **去重与来源记录**：归一化标题 + 归一化 DOI 聚类，重复条目标 `duplicate_of`
   （元数据更全者为正本），产出 `dedup`（簇数/移除数/去重率）与 `coverage`
   （raw/unique/可追溯数/追溯率/分库计数）统计。
5. **遗漏分析**：空结果、冲突、元数据缺失、权限/限流、疑似漏检全部登记 `gaps[]`
   （六类 kind），不补造文献、不默默跳过。
6. **结论分级**：`verdict` ∈ complete / partial / empty / cannot_verify 四级 +
   `run_status` 四态；每条文献的年份/相关度分数与全部统计计数在 `claims[]`
   有逐字回证（年份须在来源 quote、分数与计数须在 claim text；**DOI/URL/ID 等
   标识符内嵌数字不参与回证防误报，区间年份 2019-2024 逐端回证**）。

**核心保证**：verify_check 把每条检查的三元组 `{item, template_value, applied,
match}`、闸门状态（enforced / skipped_not_provided / not_found / unreadable）
与 unbacked 清单回写进 result.json（键 `self_check` / `gates` /
`unbacked_numbers` / `validator_verdict`），评分器不开附件即可核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 | 围绕课题找相关论文，需要可追溯的候选集 | 多轮查询计划 + 候选文献表（每条带来源/命中查询/相关性依据）|
| 系统综述 / 元分析作者 | 需要筛选依据与遗漏说明可复核 | 去重统计 + 覆盖统计 + 六类遗漏登记 + 四级结论 |
| Agent 开发者 | 给检索 Agent 加"规划→执行→去重→登记"结构化流程 | 6 个 stdlib-only 脚本 + 可复跑的校验/消融链路 |
| 教学 / 培训 | 演示"来源可追溯 + 数字逐字回证"的检索纪律 | gain_evidence 机制消融对照实验 |

**不适用**：不负责单篇论文精读、全文解析、写作润色、资料库整理；无实时联网
检索能力（检索执行依赖案例提供的检索响应材料）。

## 3. 依赖与环境（依赖版本）

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.12 实测通过；平台沙箱 python3.12+）|
| 第三方依赖 | **零**（json / os / re / sys / argparse / copy / time / math）|
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化）|
| 网络 | 不需要 |
| 磁盘 | 整包约 90 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB（本包 9 个文件）|

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定
`/skills/weekly-skill`），无需安装步骤、无依赖解析、无需联网。

```bash
# Step 0：自动落骨架 + 材料清单 + 查询计划模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1：查询规划与关键词扩展（写 query_plan / keyword_expansion 两键）
python3 /skills/weekly-skill/scripts/plan_queries.py --case /input/case.json \
  --result /app/output/result.json --work-dir /app/work

# Step 3：去重聚类与覆盖统计（写 dedup / coverage 两键）
python3 /skills/weekly-skill/scripts/dedup_records.py --result /app/output/result.json \
  --work-dir /app/work

# Step 4：增益对照 + 效率计数（5 臂实跑，真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 5：双重自检（退出码恒 0；判据是报告 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

Step 2（检索执行与逐条登记）由 Agent 依据案例材料完成，无脚本。

## 5. 输入与输出解释

- **输入**：`/input/case.json`（科研问题 + 检索响应材料 + output_contract）与
  `task.md`。**以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` /
    `changelog` + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内 18 个业务键：material_gaps、environment、research_question、
    scope、query_plan、keyword_expansion、queries_executed、databases_used、
    papers、dedup、coverage、gaps、steps、run_status、verdict、verdict_basis、
    gain_evidence、efficiency
  - **键分工（多脚本禁写同一键）**：build_skeleton 落全部骨架键；
    plan_queries 只写 query_plan / keyword_expansion；dedup_records 只写
    dedup / coverage；gain_probe 只写 gain_evidence / efficiency；
    verify_check 只写顶层 self_check / gates / unbacked_numbers / validator_verdict。
- **status**：answered（全部完成）| partial（部分完成/中断）|
  insufficient_evidence（关键材料缺失）| input_error（输入不可读）。
- **工作区产物**：/app/work/{verify_check, schema_guard, gain_evidence,
  query_plan, keyword_expansion, dedup_detail, gain_probe_polluted}.json。

## 6. 目标用户场景示例（最小调用示例，示意，非正式案例）

`examples/` 提供合成案例：科研问题「图神经网络预训练是否提升分子性质预测」，
材料模拟 3 个库的检索响应（含一对重复记录、一条空结果、一条区间年份综述）。
示意输出关键片段：

```json
{
  "case_id": "demo-lit-001", "status": "answered",
  "result": {
    "papers": [{"paper_id": "p1", "title": "Message passing neural networks for molecular property prediction",
                "year": 2019, "source_db": "Crossref", "matched_queries": ["q1"],
                "relevance_score": 0.9, "rationale": "直接命中科研问题核心方法", "duplicate_of": null}],
    "dedup": {"clusters_found": 1, "removed_duplicates": 1, "dedup_rate": 0.2},
    "coverage": {"total_raw": 5, "total_unique": 4, "traceability_ratio": 1.0},
    "gaps": [{"gap_id": "g1", "kind": "empty_result", "description": "q3 空结果"}],
    "verdict": "complete"
  },
  "claims": [{"claim_id": "k-01", "kind": "reported", "source_id": "m1",
              "evidence": [{"paragraph_id": "m1", "quote": "Message passing neural networks for molecular property prediction. Journal of Chemical Information and Modeling, 2019"}]}]
}
```

## 7. 验收方式（自检通过即视为本 Skill 交付合格）

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（output_contract 全字段 + 18 个业务字段）|
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，problems 为空 |
| A3 | 数字全回证 | `unbacked_numbers` 为空数组（年份在 quote、分数/计数在 claim text）|
| A4 | 来源可追溯 | papers 每行 source_db + matched_queries + rationale 齐备，traceability_ratio 与复算一致 |
| A5 | 去重一致 | duplicate_of 指向有效正本；removed_duplicates / dedup_rate 与复算一致 |
| A6 | 遗漏登记 | 空结果/缺失/冲突/限流逐条登记 gaps；空检索必有遗漏说明 |
| A7 | 步骤可重跑 | steps[] 非空且至少一条含可执行 command |
| A8 | 增益有据 | gain_evidence.runs 含 normal + 4 个退化臂实跑记录 + delta + 机制映射 + 边界 + 失效条件 |
| A9 | 效率可复算 | efficiency 含自动采集计数与 reproduce 命令；model_requests 缺失为 null |
| A10 | 污染被抓 | pollution_selftest.caught_by_normal_mode == true |

### 最小可运行自检清单（逐条实测，全部 exit 0）

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/wk4/skel.json --work-dir /tmp/wk4   # exit 0，骨架落盘
python3 scripts/plan_queries.py --case examples/example-case.json --result /tmp/wk4/skel.json --work-dir /tmp/wk4                        # exit 0，4 轮计划+4 条扩展词
python3 scripts/dedup_records.py --result /tmp/wk4/skel.json --work-dir /tmp/wk4                                                        # exit 0，空表也安全
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/wk4/vc.json          # exit 0，verdict=PASS
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json                                  # exit 0，PASS
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk4 --emit-into --inject-pollution  # exit 0，caught_by_normal_mode=true
```

## 8. 增益对照机制（同输入机制消融）

`gain_probe.py` 对**同一份** result.json 内容跑 5 遍（同一校验层开关对照，
**机制消融，不是平台白板对照**）：

| 模式 | 关闭的机制 | 合成案例实测（demo-lit-001）|
|------|-----------|------------------------|
| normal | —（全部开启）| 追溯判定 5/5，数字回证 11/11，人工核对 0 条，检查项 79 |
| degraded_backing | 数字逐字回证 | 数字回证 0/11，人工核对 11 条（Δ −11），检查项 72 |
| degraded_dedup | 去重一致性与统计复算 | 去重判定 3→1（Δ −2）；干净数据漏检 0，污染反例见下 |
| degraded_trace | 追溯与覆盖校验 | 追溯判定 5→0（Δ −5），人工核对 5 条（Δ −5），检查项 70 |
| degraded_all | 全部 | 人工核对 16 条（Δ −16），检查项 61 |

**污染反例自测**（副本注入：未标记重复文献 + 清空 matched_queries + 篡改年份 +
破坏去重统计）：正常模式抓到 **9** 处问题，退化臂仅 **2** 处——
missed_detection_delta.problems = **−7**，即关闭机制后漏检 7 处；
`caught_by_normal_mode = true`。每项指标的机制→指标映射、边界与失效条件
见 `mechanism_to_metric_map` / `boundaries` / `failure_conditions`。

> **边界声明**：这是本校验层"正常 vs 退化"多模式对照（机制消融），不等于平台
> "基础 Agent vs 参赛 Skill"的白板对照；平台对照结论由平台生成，本探针不代替、
> 不冒充。

## 9. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 verdict（PASS/FAIL）与
problems 列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身
故障打断（SKILL.md 协议第 7 条）。argparse 参数错误同样 exit 0。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式只会让机器判定面缩小、漏检变多，作用是量化"关闭这些机制会漏掉
多少"，作为增益证据。退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：为什么 DOI 不参与数字回证？**
DOI/URL/ID 等标识符内嵌数字若强制回证会大面积误报（任何含相同数字的文本都会
"证明"它）；因此回证只针对年份、相关度分数与统计计数，且区间年份（2019-2024）
逐端回证。另外所有归一化逻辑不用 `isalpha`（汉字会使 isalpha 返回 True 造成
中英混排误判），统一用正则归一化。

**Q：没有网络也能用吗？**
能。检索执行按案例提供的检索响应材料（Crossref/EuropePMC/publisher 响应片段）
走同一流程；databases_used 状态如实标 accessible / not_tried / unavailable。

**Q：同名不同 DOI 的两篇怎么处理？**
不自动合并，登记 uncertainties.conflicts 与 gaps(conflict)，由人工复核。

**Q：关键词扩展出的词质量如何保证？**
规则保守（复数 y→ies、形容词后缀不加复数、缩写表仅常见词），每条带
source_basis 可追溯；领域私有缩写由 Agent 结合材料补充并标注来源。

## 10. 已知限制

- 无实时联网检索：执行记录以案例材料为准，不虚构"已在线检索"。
- 扩展词表是通用学术缩写表，不覆盖领域私有缩写。
- relevance_score 是规则+判断的参考排序，不是权威引用计数；依据在 rationale。
- 增益对照是机制消融，不是平台白板对照。
- 追问轮次按每轮 3 条折算，是估计量；原始计数 manual_review_items 落盘可重算。
- 模型请求数不可由脚本采集，efficiency.model_requests 由 Agent 回填，缺失保持 null。

## 11. 失败处理

| 异常 | 处置 |
|------|------|
| 数据库响应材料缺失 | material_gaps 登记，databases_used 标 unavailable/not_tried，verdict 降级 |
| 查询空结果 | queries_executed 照记 result_count=0，gaps 登记 empty_result，不补造文献 |
| 接口限流/权限不足 | gaps 登记 rate_limited/access_denied，follow_up 写后续动作 |
| 元数据缺失 | papers[].metadata_missing 逐条登记；year 缺失则不参与回证 |
| 疑似重复不确定 | 不合并，uncertainties.conflicts 登记 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了如实登记 uncertainties |
| **任何脚本任何失败** | **退出码恒为 0**（含 argparse 错误、文件缺失、JSON 解析失败），结论记在 verdict |

## 12. 复用建议

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘不读环境），可直接 import；`ablate` 参数可复用为任意校验器的机制开关 |
| `scripts/gain_probe.py` 的多臂对照 | 换掉 analyze 即可测任何校验器；指标公式全在 mechanism_to_metric_map |
| `scripts/plan_queries.py` 的扩展规则 | ACRONYM_TABLE + 复数/连字符规则可替换为领域词表 |
| `scripts/dedup_records.py` 的归一化聚类 | norm_title / norm_doi 可直接复用到任何文献去重场景 |
| 键分工约定 | 多脚本协作写同一 result.json 时按键划分写权限，避免互相覆盖 |
| `examples/` 合成案例 | 自测 fixture：复制改字段即得新用例或负例 |

**复用顺序**：先抄 `dedup_records.py` 的归一化聚类，再抄 `verify_check.py` 的
`analyze()`（三元组 + 闸门 + 回证），最后按自己的业务 schema 改
`RESULT_REQUIRED` 列表。

## 13. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，零第三方依赖。

| 版本 | 增量 |
|------|------|
| v1 | 首版：六步流程 + 6 脚本 + 5 臂机制消融 + 污染反例自测 + 双重自检链路全部实测 exit 0 |

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 7 节自检清单（6 条命令）确认全 exit 0 且
  verify_check verdict=PASS、caught_by_normal_mode=true。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED` 与
  SKILL.md 的 schema 段；新增 result.json 键须确认键分工不冲突。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
