# sci-code-exec — 科研代码生成与执行 Skill（v1）

针对 Bohrium 第 4 期 challenge-9ec929fe「科研代码生成与执行」的参赛 Skill。
锁定子场景：**需求-代码覆盖映射 + 清洗口径事前声明 + 带留痕执行 +
数值独立复算 + 异常登记不静默**。

## 1. 用途与适用条件

给定数据字典 + 科研数据（内联 CSV / CSV 文件 / SQLite）+ 分析要求，完成五件事：

1. **需求-代码全覆盖**：题目要求逐条映射到代码产物（coverage_map），
   uncovered/partial 必须登记并写明缺口——杜绝"看起来对了"的漏实现。
2. **清洗口径事前声明**：缺失/去重/过滤/截断/填补规则在任何计算之前声明
   （declared_at 落台账，之后禁止调整）；每条统计的 rule_refs 必须指向已声明
   规则——防口径漂移。
3. **带留痕执行**：每次运行经 run_trace.py 留痕（命令、python 版本、退出码、
   日志路径、墙钟），失败现场保留不删，命令一律 `python3`——他人可独立重跑。
4. **数值独立复算**：recompute.py 与生成的分析代码**分开实现**，从原始数据按
   声明口径再算一遍，逐条比对——专抓"跑通了但算错了"的静默错误（缺失值当 0
   参与均值、重复未去重、t 检验前提未查、超量程值混入等）。
5. **异常登记不静默**：缺失/重复/异常值/类型不符/查询为空逐条登记，处理方式
   （dropped/imputed/clipped/filtered）必须与声明口径一致，校验器抓静默处理。

**核心保证**：`verify_check.py` 机械审计四组机检点；`gain_probe.py` 用正常 vs
退化双跑实测机制增益并写入 result.gain_evidence。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / unbacked_evidence / validator_verdict`
五键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 | 仪器导出/多批次合并的脏数据要出统计结论 | 清洗口径表 + 可复算的统计结果 + 异常登记表 |
| 复核者 / 审稿 | 质疑数字是怎么算出来的 | 执行留痕（命令/版本/退出码/日志）+ 独立复算比对 |
| 数据工程 | 接手别人的分析脚本要判断能不能信 | 需求-代码覆盖映射 + 口径声明台账 + 失败现场 |
| 教学 / 培训 | 演示"口径先行 + 留痕执行 + 敢登记"的纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不做实验方案设计、机理解释、论文写作；不装第三方库（只用标准库）；
数据或字段缺失照实登记，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13.14 上实测通过），只用标准库 |
| 第三方依赖 | **零**（json / csv / io / sqlite3 / argparse / subprocess / re / math） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化） |
| 磁盘 | 整包 < 100 KB |
| 资源上限 | 平台契约：≤50 个 UTF-8 文本文件、单文件 ≤500 KB、总计 ≤2 MB |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定
`/skills/weekly-skill`），无需安装步骤、无依赖解析、无需联网。脚本自带定位标志
校验（与 SKILL.md 同包才报 marker_hit=True）。

```bash
# Step 0：自动落骨架 + 数据清单 + 清洗口径模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1：Agent 声明 cleaning_rules（declared_at 落台账），任何计算之前完成

# Step 2：生成分析脚本到 /app/work，每次运行都经 run_trace 留痕
python3 /skills/weekly-skill/scripts/run_trace.py --script /app/work/analysis_01.py \
  --result /app/output/result.json --work-dir /app/work --timeout 120

# Step 3：数值独立复算（写 result.recompute）
python3 /skills/weekly-skill/scripts/recompute.py --case /input/case.json \
  --input-root /input --result /app/output/result.json --emit-into

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

- **输入**：`/input/case.json`（数据字典 + 数据集 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `unbacked_evidence` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`task_scope`、`data_dictionary`、
    `cleaning_rules`、`requirements`、`code_artifacts`、`coverage_map`、`steps`、
    `execution_traces`、`stats`、`recompute`、`anomalies`、`coverage`、
    `pending_review`、`run_status`、`verdict`、`gain_evidence`、`efficiency`
  - 口径体系：`cleaning_rules`（五动作：dropna/dedup/filter/clip/impute）→
    `stats`（八类型：count/count_missing/mean/sum/min/max/group_mean/group_count）→
    `recompute`（独立复算逐条比对）
- **键归属（多脚本禁写同一键）**：execution_traces ← run_trace.py；
  recompute ← recompute.py；self_check/gates/unbacked_*/validator_verdict ←
  verify_check.py；gain_evidence/efficiency ← gain_probe.py；其余 ←
  build_skeleton.py + Agent。
- **工作区产物**：/app/work/{cleaning_rules.json, verify_check.json,
  schema_guard.json, gain_evidence.json, gain_probe_polluted.json,
  execution_traces.json, logs/run_NNN.log}。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（数据与结论均为虚构）：7 行仪器数据含 1 缺失、
1 重复主键、1 超量程值、1 范围外批次。示意结论：清洗后 4 行，A 批均值 10.6
（2 行）、B 批均值 54.2（250 截断为 100 后 (8.4+100)/2），原始缺失 1 行；
4 条统计全部独立复算 PASS。关键片段：

```json
{
  "case_id": "demo-sci-code-001", "status": "answered",
  "result": {
    "stats": [{"stat_id": "S3", "type": "group_mean", "value": 54.2,
               "rule_refs": ["CR-01","CR-02","CR-03","CR-04"], "source": "exp_a"}],
    "recompute": {"verdict": "PASS", "mismatches": []},
    "verdict": "completed"
  }
}
```

本地自测整条链路（合成案例，非正式答案）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/run_trace.py --script examples/demo_analysis.py --result /tmp/skel.json --work-dir /tmp/wk
python3 scripts/recompute.py --case examples/example-case.json --input-root examples --result /tmp/skel.json --emit-into
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --rubric /tmp/wk/cleaning_rules.json --out /tmp/vc.json --emit-into
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json --out /tmp/sg.json
```

## 7. 最小自检清单（2026-11-19 实测，全部退出码 0）

| 编号 | 自检项 | 实测结果 |
|------|--------|---------|
| C1 | build_skeleton 落骨架（marker 命中、1 数据集 + 5 需求提取） | exit 0，marker_hit=True |
| C2 | run_trace 失败留痕（字段名笔误脚本 exit 1，日志/退出码落盘） | exit 0，exit_code=1 已记录 |
| C3 | run_trace 成功留痕（demo_analysis exit 0） | exit 0，exit_code=0 |
| C4 | recompute 独立复算（4/4 PASS：4 / 10.6 / 54.2 / 1） | exit 0，mismatches=0 |
| C5 | gain_probe 双模式（干净输入 normal=degraded=PASS，漏检均 0，steps_count 26 vs 4） | exit 0 |
| C6 | gain_probe 污染反例（注入 8 项：正常模式 9 处全抓、漏检 0；退化模式漏检 2/3/1/2） | exit 0，caught_by_normal_mode=True |
| C7 | verify_check 业务校验（22 条检查项） | exit 0，verdict=PASS |
| C8 | schema_guard 结构守卫（45 条检查项） | exit 0，verdict=PASS |
| C9 | 六脚本失败路径（case/脚本/result 全缺失场景） | 全部 exit 0 |
| C10 | examples 标注为示意（数据结论虚构，非正式答案） | 已标注 |
| C11 | SKILL.md ≤150 行 / 脚本 6 个 / 全包 12 文件 / 零第三方依赖 | 145 行 / 6 / 12 / stdlib-only |

## 8. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑两遍（违规真值由探针独立复算，
与校验层分开实现）：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（覆盖映射 + 执行留痕 + 数值复算 + 异常口径） | — |
| `degraded` | 枚举/结构/steps 基础检查 | **coverage / trace / recompute / anomaly 四组** |

实测对照（合成案例 + 注入 8 项污染的副本，2026-11-19 实跑）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| 干净输入漏检（四类） | 0 | 0 | 0 |
| steps_count（已执行检查项+流程步） | 26 | 4 | +22 |
| 污染副本 verdict | FAIL（9 处） | FAIL（仅剩 1 处通用结构问题） | −8 |
| 污染副本覆盖映射漏检 | 0 | 2 | +2 |
| 污染副本执行留痕漏检 | 0 | 3 | +3 |
| 污染副本数值复算漏检 | 0 | 1 | +1 |
| 污染副本异常口径漏检 | 0 | 2 | +2 |

**同一校验器、同一污染输入**：正常模式漏检 0（8 处注入违规全部捕获，另有 1 处
coverage 汇总连带被抓），退化模式漏掉全部 8 处客观违规且只剩一条通用结构问题
可看——机制增益最直接的证据。数字全部来自实跑，详见
`gain_evidence.mechanism_to_metric_map`。

注入的 8 项污染：删覆盖映射条目、artifact_id 指向不存在代码、篡改统计值 4→5、
rule_refs 指向 GHOST-RULE、删 exit_code、清空 log_ref、environment.python_version
置空、anomaly rule_ref 改 GHOST-RULE——与题面机检点（覆盖映射/执行留痕/数值
复算/异常登记）一一对应。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 数据文件缺失 / SQLite 打不开 | material_gaps 登记，verdict=cannot_verify，绝不编造数据 |
| 缺列 / 类型不符 | anomaly 登记（kind=type_mismatch），按声明规则处理或降级，不静默改列名 |
| 脚本运行失败 | run_trace 留存 exit_code 与日志 → 读日志定位 → 修复重跑；失败记录保留不删除 |
| 依赖不可用 | 只用标准库；需要第三方时登记 material_gaps 并给降级路径，不现场 pip install |
| 数值溢出 / 除零 | 生成代码内防御（分母保护、范围检查），异常按 overflow 登记 |
| 查询为空 / 结果为空集 | 空 result 如实返回 0 行并登记 empty_query，不拿上一轮结果顶替 |
| 复算与声明不符 | 修代码重跑直到一致；修不了就 mismatches 照实报告 + verdict 降级，不改数凑数 |
| **任何脚本自身失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 verdict 字段 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict` 与 `problems`，Agent
读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：清洗口径会不会中途变来变去？**
不会。cleaning_rules 必须在任何计算之前声明（declared_at 落台账），之后禁止
调整；每条 stats 的 rule_refs 必须指向已声明规则，verify_check 对引用不存在
规则的统计直接判 FAIL（口径漂移）。

**Q：recompute.py 和我生成的分析代码有什么关系？**
同一套数字算两遍、两遍分开实现：recompute.py 是校验侧的独立实现，从原始数据
按声明口径重算每条统计再与 result.stats 比对。你的分析代码错了（比如缺失值当
0 参与均值），recompute 会给出 MISMATCH，逼你修代码而不是改数。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式**只会让漏检变多**，它量化"关闭这些机制会漏掉多少"。SKILL.md
明确退化模式结果仅用于增益对照，不得当作交付自检结论。

**Q：异常"登记"是不是就是删掉了事？**
不是。dropped/imputed/clipped/filtered 这类主动处理必须写 rule_ref 指向声明
口径，并给 rows_affected 与 evidence_location；静默处理（处理方式说不清、
规则不存在）校验器判 FAIL。

**Q：为什么命令必须以 python3 开头？**
平台运行时约定命令一律 python3（不假设 python 别名或虚拟环境）。verify_check
对非 python3 前缀的命令判 FAIL，这是"他人可重跑"的前提。

## 11. 生态贡献十项（可复用资源）

1. **清洗口径声明格式**：cleaning_rules（五动作 + params + rationale + declared_at
   台账），通用于任何"口径先行"的数据处理场景。
2. **统计声明格式**：stats 条目（stat_id + type + params + rule_refs + source），
   让"算什么、按什么口径算"先于"算出多少"。
3. **独立复算器 `recompute.py`**：从原始数据（csv_inline/csv/sqlite）按声明口径
   复算八类基础统计，可直接移植为任何数据任务的数值防漂移闸。
4. **执行留痕包装器 `run_trace.py`**：subprocess 包装 + 日志落盘 + 痕迹回写，
   任何需要"跑过留痕"的 Skill 可直接复用。
5. **需求-代码覆盖映射模板**：requirements[] + coverage_map[] + pending_review
   三件套，适用于任何"逐条要求逐条落实"场景。
6. **校验器 `analyze()` API**：verify_check.py 纯函数式（不写盘），ablate 参数
   可直接用作别处的机制开关对照。
7. **增益对照探针**：正常 vs 退化双跑 + 污染反例注入（8 类注入与机检点一一
   对应），可移植到任何校验型 Skill。
8. **合成示例 fixture**：examples/ 全部标注示意（7 行脏数据：缺失/重复/超量程/
   范围外批次各一处），复制改标签即得新的负例。
9. **失败经验沉淀**：worklog.md 记录真实对照数字与诚实边界（见第 12 节）。
10. **键归属纪律**：多脚本分键写入、互不覆盖的约定（traces/recompute/self_check/
    gain_evidence 各归其主），可直接套用到多脚本 Skill 包。

## 12. 已知限制与诚实边界

- cleaning_rules 的动作阈值（如 clip 边界）是本技能事前声明的设定（题面未给定
  数值口径时按保守量级设定并写明），不冒充外部统计规范。
- recompute.py 只覆盖八类基础统计与五种清洗规则；更复杂的模型类结果（回归系数、
  检验 p 值等）由生成的分析脚本自行留痕 + claims 回证，独立复算闸不覆盖。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照；追问轮次按每轮 3 条
  折算是估计量。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失
  保持 null。
- run_trace 在无 python3 命令的环境会记 exit_code=spawn_error 并照常交付
  （痕迹里注明），不中断流程。

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/数据清单/口径模板（退出码恒 0） | 是 |
| scripts/run_trace.py | 执行留痕包装器（命令/版本/退出码/日志回写 execution_traces） | 是 |
| scripts/recompute.py | 数值独立复算器（八类统计 × 五种清洗规则） | 是 |
| scripts/verify_check.py | 业务校验器（覆盖/留痕/复算/异常四组） | 是（含 analyze() API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（虚构 7 行仪器数据） | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案） | 是（fixture） |
| examples/demo_analysis.py | 演示"生成的分析脚本"（自包含、参数化路径） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 6 节六条自测命令 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 REQUIRED 常量与 SKILL.md 的
  schema 段。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
