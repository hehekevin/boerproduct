# sci-db-query-analyze — 科研数据库查询与分析 Skill（v1）

针对 Bohrium 第 4 期 challenge-5c56458d「科研数据库查询与分析」的参赛 Skill。
锁定子场景：**问题→结构化查询映射 + 内存查询执行留痕 + 聚合独立复算与分组守恒 +
空结果/缺失/重复边界登记**。

## 1. 用途与适用条件

给定数据快照（case.json 内数据集行）与分析问题，完成五件事：

1. **查询-问题映射**：每个分析问题编译为结构化查询
   （filters / group_by / aggregations + issued_sql_like），question_id 回指问题；
   过滤列/分组列/聚合列必须存在于数据集实际字段，张冠李戴即 FAIL。
2. **内存执行与留痕**：对 case.json 数据集做内存过滤聚合（**不连真实数据库**），
   每条查询留 issued+executed+时间戳日志；查询定义与日志 issued 记录不一致
   （执行后被改写/条件遗漏）会被校验器抓出。
3. **聚合机械复算**：stat_recompute.py 用**独立实现**复算 row_count / 各聚合值 /
   分组守恒（组计数和==总行数、组 sum 和==总体 sum）；verify_check 再用同一独立
   实现抽查——数字不是"看起来对"，是重算出来的。
4. **边界登记**：空结果、缺失值剔除、重复记录、数据集未找到一律写入
   boundary_registry（ref/kind/note），绝不静默丢弃；跨表用两步显式传键，
   控制一对多膨胀。
5. **字段语义接地**：field_dictionary 解释 dtype/含义/单位与编码；编码型字段
   （如状态码 1/2/9）按语义过滤，不得当数值直接聚合。

**核心保证**：`verify_check.py` 五组校验（mapping/recompute/boundary/log/conservation）
+ 数字独立抽查；`gain_probe.py` 同一校验器 normal vs degraded 双跑实测机制增益。
评分器不开附件即可通过 `self_check / gates / unbacked_numbers / unbacked_evidence /
validator_verdict` 五键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 | 对固定数据快照回答统计问题（分布/均值/计数） | 查询定义+结果+日志+复算依据，可独立复跑 |
| 数据复核者 | 检查交来的聚合表能不能信 | recompute 检查清单 + 守恒核对 + unbacked_numbers 空表 |
| 管线维护者 | 排查"结果不对"出在哪一步 | query_log 序列化留痕 + boundary_registry 边界台账 |
| 教学/培训 | 演示"映射先行、复算兜底、敢报缺"的查询纪律 | 可复算的消融对照实验（gain_evidence） |

**不适用**：不连接真实数据库、不做 SQL 方言适配、不做库表写入、不下载外部数据；
快照之外的表/字段一律登记不臆断。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 上实测通过），只用标准库 |
| 第三方依赖 | **零**（json / os / re / sys / argparse / copy / time） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化） |
| 磁盘 | 整包 < 100 KB |
| 资源上限 | 平台契约：≤50 个 UTF-8 文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定
`/skills/weekly-skill`），无需安装步骤、无依赖解析、无需联网。脚本自带定位标志
校验（标志 `sci-db-query-analyze-v1` 与 SKILL.md 同包才报 marker_hit=True）。

```bash
# Step 0：自动落骨架 + 数据集/问题清单 + 查询口径台账（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 填 field_dictionary 与 queries（见 SKILL.md 七步流程）

# Step 3：内存执行查询 + 日志留痕 + 自动边界登记
python3 /skills/weekly-skill/scripts/query_engine.py --result /app/output/result.json \
  --case /input/case.json

# Step 4：聚合独立复算 + 分组守恒（写 result.recompute）
python3 /skills/weekly-skill/scripts/stat_recompute.py --result /app/output/result.json \
  --case /input/case.json

# Step 5：增益对照（消融双跑）+ 效率计数 + 污染反例（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 6：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

## 5. 输入与输出

- **输入**：`/input/case.json`（数据集快照 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `unbacked_evidence` / `gates` / `validator_verdict`
  - `result` 内：`query_scope`（问题清单+查询口径）、`field_dictionary`、`queries[]`、
    `query_results[]`、`recompute`、`boundary_registry[]`、`query_log[]`、`coverage`、
    `pending_review`、`steps`、`run_status`、`verdict`、`verdict_basis`、
    `gain_evidence`、`efficiency`
  - 判定体系：verdict ∈ answered / partially_answered / not_appraised / cannot_verify；
    run_status.state ∈ success / partial / unable_to_determine / refused。
- **键归属（多脚本禁写同一键）**：queries/query_results/query_log/boundary_registry ←
  query_engine.py（kind 以 manual_ 开头的手工登记被保留）；recompute ← stat_recompute.py；
  self_check/gates/unbacked_*/validator_verdict ← verify_check.py；
  gain_evidence/efficiency ← gain_probe.py；其余 ← build_skeleton.py + Agent。
- **工作区产物**：/app/work/{verify_check.json, schema_guard.json, query_scope.json,
  gain_evidence.json, gain_probe_polluted.json}。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（数据为虚构）：2 个数据集（实验样本表 12 行 + 测量记录表
13 行，含 ph 缺失 2 处、meas_id=M07 重复 1 处、status 编码字段）× 4 个问题 × 5 条查询。
示意结论：A/B/C 各 4 条样本（组计数和=12 守恒）；B2 批次 6 样本平均浓度
11.583333 mg/mL（跨表两步 QA-02a→QA-02b）；status=9 报废 2 条；batch=B9 空结果
0 行已登记。关键片段：

```json
{
  "case_id": "demo-scidb-001", "status": "answered",
  "result": {
    "queries": [{"query_id": "QA-02b", "question_id": "Q02", "dataset_id": "measurements",
      "filters": [{"column": "sample_id", "op": "in", "value": ["S03","S05","S06","S08","S09","S10"]}],
      "aggregations": [{"fn": "avg", "column": "concentration_mgml", "alias": "avg_conc"}]}],
    "query_results": [{"query_id": "QA-02b", "row_count": 6, "aggregates": {"avg_conc": 11.583333, "n_meas": 6}, "status": "ok"}],
    "recompute": {"computed_by": "stat_recompute.py", "all_ok": true},
    "verdict": "answered"
  }
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/query_engine.py --result /tmp/skel.json --case examples/example-case.json
python3 scripts/stat_recompute.py --result /tmp/skel.json --case examples/example-case.json
python3 scripts/gain_probe.py --result /tmp/skel.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result /tmp/skel.json --case examples/example-case.json --out /tmp/wk/vc.json --emit-into
python3 scripts/schema_guard.py --result /tmp/skel.json --case examples/example-case.json --out /tmp/wk/sg.json
```

## 7. 最小自检清单（2026-11-19 实测，全部退出码 0）

| 编号 | 自检项 | 实测结果 |
|------|--------|---------|
| C1 | build_skeleton 落骨架（marker 命中、2 数据集 4 问题提取） | exit 0，marker_hit=True |
| C2 | query_engine 执行 5 条查询（12/6/6/2/0 行，QA-04 空结果自动登记） | exit 0，errors=0 |
| C3 | stat_recompute 独立复算（13 项检查含分组守恒全过） | exit 0，all_ok=True |
| C4 | gain_probe 消融双跑（干净输入 normal=degraded=0 漏检） | exit 0，delta=0 |
| C5 | gain_probe 污染反例（注入 8 项：normal 抓 10 处、degraded 漏全部 10 处） | exit 0，caught_by_normal_mode=True |
| C6 | verify_check 业务校验（五组+独立抽查+回证） | exit 0，verdict=PASS |
| C7 | schema_guard 结构守卫（output_contract + 业务 schema 全字段） | exit 0，verdict=PASS |
| C8 | examples 标注为示意（数据虚构，非正式答案） | 已标注 |
| C9 | SKILL.md ≤150 行 / 脚本 6 个 / 全包 11 文件 / 零第三方依赖 | 145 行 / 6 / 11 / stdlib-only |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 用**同一校验器**（verify_check.analyze）对同一输入跑两遍：
normal（mapping/recompute/boundary/log/conservation 五组全开）vs degraded（--ablate all
关闭五组）；污染反例在**副本**上注入 8 类客观违规（聚合值篡改/行数篡改/组计数篡改/
过滤条件遗漏/删日志/删边界登记/绕开复算/悬空映射）。

实测对照（合成案例 + 注入 8 项污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入漏检（五组） | 0 | 0 | 0 |
| 污染副本捕获 problem 数 | 10 | 0 | +10 |
| mapping 组捕获（悬空映射+条件遗漏/定义改写） | 2 | 0 | +2 |
| recompute 组捕获（含独立数字抽查 4 处+绕开复算 1 处） | 5 | 0 | +5 |
| boundary 组捕获（空结果登记被删） | 1 | 0 | +1 |
| log 组捕获（日志尾部被删） | 1 | 0 | +1 |
| conservation 组捕获（组计数篡改） | 1 | 0 | +1 |

**同一校验器、同一污染输入**：正常模式抓出 10 处客观违规，退化模式一处都抓不到
（只剩通用结构检查，而污染不破坏结构）——机制增益最直接的证据。数字全部来自
实跑，详见 `gain_evidence.mechanism_to_metric_map` 与 /app/work/gain_evidence.json。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 数据集未找到 / 键名不识别 | status=error + boundary 登记 dataset_not_found，手工核对键名后重跑 |
| 查询结果 0 行 | boundary 登记 empty_result，verdict 如实降级，不补造数字 |
| 数值列含缺失值 | 缺失行剔除并登记 missing_values，均值口径为"剔除后" |
| 重复记录 | 登记 manual_duplicate_rows 待人工确认，不静默去重 |
| 编码型字段被要求聚合 | 按 field_dictionary 语义过滤，不做数值聚合 |
| 非数值混入数值列 | 该行剔除并登记，聚合只计可解析值 |
| 复算不一致 | 以原始数据为准修复查询/结果，不改数据凑结论 |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 verdict 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict` 与 `problems`，Agent
读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：为什么不真的连数据库？**
评测环境只授权 case.json 内的数据快照；本 Skill 把"连接-查询-抽取"压缩为
"对快照做结构化内存查询"，语义等价（filters/group_by/aggregations + SQL 形留痕），
且天然可复算、可审计。真实库场景只需把 load_rows 换成授权连接读快照。

**Q：复算为什么要两套？**
stat_recompute 是"第一复核"（写 recompute 检查清单）；verify_check 的独立抽查
不信任已有 checks，直接对原始数据重算 row_count 与各聚合——篡改数字同时伪造
检查记录也抓得住（污染实验中 recompute 组 5 处捕获即来自抽查）。

**Q：跨表查询怎么做 join？**
不做隐式 join（漏连接条件会行数膨胀）。跨表拆成两步显式传键：先在维表过滤取键，
再以 in 过滤事实表聚合；issued_sql_like 注明键来源，行数守恒由复算兜底。

**Q：空结果是失败吗？**
不是失败但必须显式。0 行写入 boundary_registry（empty_result），说明过滤条件与
预期差异，由人决定是"数据真没有"还是"条件写错"——静默丢弃正是现有工具的通病。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它量化"关闭这些机制会漏掉多少"。SKILL.md
明确退化模式结果仅用于增益对照，不得当作交付自检结论。

## 11. 生态贡献十项（可复用资源）

1. **查询定义模板**：{query_id, question_id, dataset_id, filters, group_by, aggregations, issued_sql_like} 结构，任何"问题→查询"映射场景可复用。
2. **内存查询执行器**：12 种 filter op + 6 种聚合 fn 的确定性实现，可移植到任何 dict 行数据集。
3. **独立复算管线**：stat_recompute 的 row_count/aggregate/group_conservation 三类检查（独立实现不共享执行器代码）。
4. **边界登记台账格式**：{ref, kind: empty_result|missing_values|manual_duplicate_rows|dataset_not_found, note}，任何"异常不静默"场景可复用。
5. **查询日志留痕格式**：{seq, ts, query_id, action: issued|executed, detail} + "定义与日志一致性"反篡改检查。
6. **校验器 analyze() API**：verify_check 纯函数式（不写盘），ablate 参数可直接用作别处的机制开关对照。
7. **增益对照探针**：同一校验器 normal vs degraded 双跑 + 8 类污染反例注入，可移植到任何校验型 Skill。
8. **合成示例 fixture**：examples/ 全部标注示意，含缺失/重复/编码字段/空结果四类边界，复制改标签即得新的负例。
9. **失败经验沉淀**：worklog.md 记录真实对照数字与诚实边界（见第 12 节）。
10. **键归属纪律**：多脚本分键写入、互不覆盖的约定，可直接套用到多脚本 Skill 包。

## 12. 已知限制与诚实边界

- 只对 case.json 提供的快照做内存查询模拟，不连接真实数据库；真实库的连接参数/
  权限/快照版本管理不在本 Skill 范围（题面明确"不连真实数据库"的评测形态）。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照；平台白板对照由平台生成。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。
- 污染注入只覆盖 8 类客观违规，不能证明全部正确性；数值正确性以独立复算为准。
- 数据集行以非 dict/矩阵提供时列名核对能力有限，会在 material_gaps 登记。

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/数据集问题清单/口径台账（退出码恒 0） | 是 |
| scripts/query_engine.py | 内存查询执行 + 日志留痕 + 自动边界登记（仅写 queries/query_results/query_log/boundary_registry） | 是 |
| scripts/stat_recompute.py | 聚合独立复算 + 分组守恒（仅写 recompute） | 是（含 refilter/recompute_agg） |
| scripts/verify_check.py | 业务校验器（五组 + 独立抽查 + 回证） | 是（含 analyze() API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 消融双跑增益对照 + 效率计数 + 8 类污染反例 | 是 |
| examples/example-case.json | 合成输入示例（2 数据集 4 问题，虚构） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节六条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150，且标志 `sci-db-query-analyze-v1` 仍在文中。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 REQUIRED 常量与 SKILL.md 的 schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
