# lib-file-organizer — 科研资料库与文件管理 Skill（v1）

针对 Bohrium 第 4 期「library 资料管理」赛道「科研资料库与文件管理」(challenge-2bfd9194)
的参赛 Skill。锁定子场景：**清单化盘点（哈希+元数据出处）+ 规则驱动的归类与重命名 +
内容级去重 + 版本链重建 + 操作审计链**。

## 1. 用途与适用条件

给定一批科研文件（真实文件或 case.json 内联清单），完成六件事：

1. **清单化盘点**：逐文件计算 sha256、识别类型、保守抽取 year/version_hint 等元数据，
   逐字段记录出处（metadata_source），抽不到就留空不猜；文件缺失/无权限/损坏照实登记
   `skipped_conflicts`（含恢复方式），不静默跳过。
2. **规则事前声明**：分类规则（rule_id + priority + ext/path/name 三类匹配）与命名规范
   （pattern/regex/example）必须在任何归类之前声明（declared_at 闸门），之后禁止调整。
3. **机械归类与重命名**：按 priority 重放规则匹配（首个命中生效，全不中归 fallback），
   逐文件引用 rule_hit；按命名规范生成 rename_suggestion（正则校验）；产出目标目录树
   directory_plan。中文匹配一律子串/正则，禁用 isalpha（汉字返回 True 的陷阱）。
4. **内容级去重**：sha256 完全相同才判重复（绝不按文件名），保留最早 mtime 为正本，
   其余 duplicate_of 并入；重复组、成员、正本全部登记。
5. **版本链重建**：归一化文件名主干（去 v2/final/draft/副本/定稿等版本词）+ 哈希互异 +
   mtime 升序 → version_rank，最新者为 current；哈希相同的一律进重复组不进版本链。
6. **操作审计链**：每个非 keep 操作生成 op_id + prev_op_id + chain_hash（sha256 链式）+
   replay 复放命令；任何一条操作可按记录复跑核对，执行后回填 op.status=done。

**核心保证**：`verify_check.py` 独立重放规则、重算哈希分组与链哈希（与生产脚本分开实现），
把无回证的哈希/引用列入 `unbacked_numbers` 判 FAIL；`gain_probe.py` 用正常 vs 消融多跑
+ 污染反例实测机制增益写入 `result.gain_evidence`。评分器不开附件即可通过
`self_check / gates / unbacked_numbers / validator_verdict` 四键核对。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 / 课题交接 | 结题要交几百个混着原始数据、扫描件、旧版本稿的文件 | 哈希清单 + 分类目录树 + 重命名建议 |
| 资料管理员 | 半年后还要能找到、信任这批资料 | 每文件元数据出处 + 重复组 + 版本链 |
| 复核者 / 合作方 | 要确认"动了哪些文件、为什么这么归" | 逐条 rule_hit + 审计链（chain_hash + replay） |
| 教学 / 培训 | 演示"规则事前声明 + 内容判重 + 可回放审计"的整理纪律 | 可复算的消融对照实验（gain_evidence） |

**不适用**：不做网盘上传、不解析 PDF 全文、不做存储迁移；缺什么登记什么，不脑补。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13.12 上实测通过），只用标准库 |
| 第三方依赖 | **零**（`json/os/re/sys/argparse/copy/time/hashlib/datetime`） |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化，无硬编码路径） |
| 磁盘 | 整包 < 200 KB |
| 资源上限 | 平台契约：≤50 个文本文件、单文件 ≤500 KB、总计 ≤2 MB、无符号链接 |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需任何安装步骤、无依赖解析、无需联网。

```bash
# Step 0：落骨架 + 文件清单 + 哈希 + 规则声明模板（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work

# Step 1-2：Agent 事前声明分类规则与命名规范，逐文件登记元数据/跳过（见 SKILL.md 七步流程）

# Step 3：机械归类 + 重命名建议（写 category/rule_hit/rename_suggestion/directory_plan）
python3 /skills/weekly-skill/scripts/classify_files.py --result /app/output/result.json \
  --rules /app/work/classification_rules.json

# Step 4：内容哈希去重 + 版本链重建（写 duplicates/versions/duplicate_of/version_*）
python3 /skills/weekly-skill/scripts/duplicate_check.py --result /app/output/result.json

# Step 5：审计链生成 + 增益对照（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/audit_ops.py --result /app/output/result.json --work-dir /app/work
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution

# Step 6：双重自检（退出码恒 0；判据是报告里的 verdict 字段 PASS/FAIL）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

## 5. 输入与输出

- **输入**：`/input/case.json`（文件清单/内联内容 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容。**
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`library_profile`、`classification_rules`、
    `files[]`（逐文件清单+判定）、`directory_plan`、`duplicates`、`versions`、`ops`（审计链）、
    `coverage`、`skipped_conflicts`、`steps`、`run_status`、`verdict`、`verdict_basis`、
    `gain_evidence`、`efficiency`
- **动作体系**：`action` ∈ keep/move/rename/move_rename/merge/skip × `sha256_status`
  ∈ ok/ok_inline/no_content/unreadable × `op.status` ∈ planned/done/failed/skipped；
  判定条件与边界约定见 SKILL.md「Step 2-5」。
- **status**：`answered`（全部完成）| `partial`（部分完成/中断）|
  `insufficient_evidence`（关键材料缺失）| `input_error`（输入不可读）。
- **工作区产物**：`/app/work/verify_check.json`（业务校验报告）、`/app/work/schema_guard.json`
  （结构报告）、`/app/work/gain_evidence.json`（增益对照证据）、
  `/app/work/classification_rules.json`（规则声明台账）、`/app/work/audit_chain.json`
  （审计链摘要）、`/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例（文件内容均为虚构）：8 个文件 → 7 个完成哈希归类
（F01 归 raw_data 并为重复组正本、F02 同哈希并入、F03/F04 重建版本链 V01）、
1 个文件缺失条目（F08）照实跳过并登记 skipped_conflicts。示意输出关键片段：

```json
{
  "case_id": "demo-library-001", "status": "answered",
  "result": {
    "classification_rules": {"declared_at": "step1-before-any-classification", "rules": [{"rule_id": "R-01", "category": "raw_data"}]},
    "files": [{"file_id": "F01", "category": "raw_data", "rule_hit": "R-01", "action": "move_rename"}],
    "duplicates": [{"group_id": "D01", "member_ids": ["F01", "F02"], "keep_id": "F01", "evidence": "sha256 完全相同"}],
    "versions": [{"group_id": "V01", "member_ids": ["F03", "F04"], "current_id": "F04"}],
    "coverage": {"total_files": 8, "judged_files": 8, "classified": 7, "skipped": 1, "ratio": 1.0},
    "verdict": "organized"
  },
  "claims": [{"claim_id": "c-01", "source_id": "F01",
               "evidence": [{"paragraph_id": "files[F01].path", "quote": "raw/仪器A_2025_batch1.csv"}]}]
}
```

本地自测整条链路（合成案例，非正式答案；`<空目录>` 用任意空文件夹即可）：

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root <空目录> --out /tmp/r.json --work-dir /tmp/wk
python3 scripts/classify_files.py --result /tmp/r.json --rules examples/example-rules.json
python3 scripts/duplicate_check.py --result /tmp/r.json
python3 scripts/audit_ops.py --result /tmp/r.json --work-dir /tmp/wk
python3 scripts/gain_probe.py --result /tmp/r.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution
python3 scripts/verify_check.py --result /tmp/r.json --case examples/example-case.json --out /tmp/wk/vc.json --emit-into
python3 scripts/schema_guard.py --result /tmp/r.json --case examples/example-case.json
```

## 7. 最小自检清单（2026-11-19 实测，全部 exit 0）

| 编号 | 自检项 | 命令 | 实测结果 |
|------|--------|------|---------|
| C1 | 骨架+清单+哈希 | `python3 scripts/build_skeleton.py --case examples/example-case.json --input-root <空目录> --out /tmp/r.json --work-dir /tmp/wk` | exit 0，8 文件 7 哈希 |
| C2 | 机械归类 | `python3 scripts/classify_files.py --result /tmp/r.json --rules examples/example-rules.json` | exit 0，8/8 归类 |
| C3 | 去重+版本链 | `python3 scripts/duplicate_check.py --result /tmp/r.json` | exit 0，重复组 1、版本链 1 |
| C4 | 审计链 | `python3 scripts/audit_ops.py --result /tmp/r.json --work-dir /tmp/wk` | exit 0，ops 8 条链完整 |
| C5 | 增益对照+污染 | `python3 scripts/gain_probe.py --result /tmp/r.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution` | exit 0，污染 caught=true |
| C6 | 业务校验 | `python3 scripts/verify_check.py --result /tmp/r.json --case examples/example-case.json --out /tmp/wk/vc.json --emit-into` | exit 0，verdict=PASS |
| C7 | 结构守卫 | `python3 scripts/schema_guard.py --result /tmp/r.json --case examples/example-case.json` | exit 0，verdict=PASS |
| C8 | 失败路径也 exit 0 | 对不存在路径重复运行 C6 | exit 0，报告内 verdict=FAIL |

## 8. 验收标准

| 编号 | 验收项 | 判定方式 |
|------|--------|---------|
| A1 | 契约字段齐 | `schema_guard` 报告 `verdict=PASS`（output_contract 全字段 + 本题业务字段） |
| A2 | 业务逻辑齐 | `verify_check` 报告 `verdict=PASS`，`problems` 为空 |
| A3 | 证据全回证 | `unbacked_numbers` 为空数组 |
| A4 | 闸门诚实 | `gates[]` 每项 state ∈ 四态枚举；非 enforced 必有 note |
| A5 | 全记录覆盖 | coverage.total_files == files 条数，每条 judged=true 或有 skip_reason |
| A6 | 归类可回溯 | 逐文件 rule_hit 引用事前规则 id；重放与登记一致 |
| A7 | 判重按内容 | duplicates 与 sha256 重算分组一致；版本链哈希互异、mtime 升序 |
| A8 | 审计可回放 | ops 链哈希逐条重算一致、每条有 replay、非 keep 文件都有记录 |
| A9 | 增益有据 | `gain_evidence.runs` 含 normal + 4 组消融实跑记录 + delta + 机制映射 + 边界 |
| A10 | 污染被抓 | `gain_evidence.pollution_selftest.caught_by_normal_mode == true` |

## 9. 增益对照机制（增益可验证性）

`gain_probe.py` 对**同一份** result.json 内容跑五遍（复用 verify_check.analyze 纯函数）：

| 模式 | 开启的检查 | 关闭的检查 |
|------|-----------|-----------|
| `normal` | 全部（规则重放 + 判重/版本复算 + 审计链 + 证据回证 + 覆盖底线） | — |
| `ablate:rules` | 其余 | **规则重放** |
| `ablate:duplicates` | 其余 | **判重/版本复算** |
| `ablate:audit` | 其余 | **审计链** |
| `ablate:all` | 覆盖底线 | **四组全关** |

实测对照（合成案例 + 注入 4 项污染的副本，2026-11-19 实跑，数字见 worklog.md）：

| 指标 | normal | ablate:all | 差值 |
|------|--------|-----------|------|
| 干净输入 problems / 机制漏检 | 0 / 0 | 0 / 0 | 0（干净输入四组检查本就不触发） |
| 污染副本 problems | 10 | 1 | +9 |
| 污染副本机制漏检合计 | 8 | 0 | +8 |

**同一校验器、同一污染输入**：正常模式抓到 10 处（规则 2 + 判重 2 + 审计 4 + 证据 1 +
底线 1），全消融模式只抓到 1 处底线违规、8 处机制违规全部漏掉——这是机制增益最直接的
证据。污染判定真值由探针独立注入，与校验层分开实现；详见 `mechanism_to_metric_map`。

> **重要边界**：这是本校验层"正常 vs 消融"对照，**不等于**平台"基础 Agent vs 参赛 Skill"
> 的白板对照；后者由平台生成，本探针不代替、不冒充。

## 10. 异常处理

| 异常 | 处置 |
|------|------|
| 清单为空 / 无文件 | files 空、coverage.total=0、verdict=cannot_verify，绝不补造文件 |
| 文件缺失/无权限/哈希失败 | sha256_status=unreadable 或 skip_reason + skipped_conflicts（含恢复方式），不静默跳过 |
| 元数据无据 | 留空 + metadata_source=not_extracted，不按文件名猜作者/仪器 |
| 同名不同内容 | 进版本链（mtime 排序）；同内容不同名进重复组（保留最早正本） |
| 中文/特殊字符文件名 | 一律子串/正则匹配，禁用 isalpha |
| 算力/时间不足 | 保留已判定部分，status=partial，changelog 注明截断位置 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties |
| **任何校验脚本失败** | **退出码恒为 0**，绝不中断交付；结论记在报告 `verdict` 字段 |

## 11. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict`（PASS/FAIL）与 `problems`
列表，Agent 读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断。

**Q：重复判断为什么不用文件名？**
题面明确要求"重复与版本关系是否按内容判断而不是按文件名判断"。脚本只信任 sha256：
同哈希=重复，不同哈希且主干相同=版本。文件名只用于归一化分组候选，最终以哈希互异约束。

**Q：归类的规则是谁定的？**
由 Agent 在 Step 1 依据题面规则事前声明并落盘（declared_at 台账），之后禁止调整；
verify_check 会逐文件重放规则核对归类一致性——事后改规则凑结果会被判 FAIL。

**Q：`--ablate` 是不是让结果更好看？**
不是。消融模式**只会让漏检变多**，它的作用是量化"关闭这些机制会漏掉多少"。SKILL.md 明确
消融结果仅用于增益对照，不得当作交付自检结论。

**Q：脚本会不会真的移动我的文件？**
不会。脚本只产出 category/rename_suggestion/directory_plan 与审计链（status=planned）；
实际落库由调用方按计划执行，执行后把对应 op.status 改为 done 并附证据路径——审计链记录
"计划与结果"，不冒充"已完成"。

**Q：中文文件名会有坑吗？**
匹配一律用子串包含与正则，显式禁用 `str.isalpha()`（对汉字返回 True，会把中文文件名
误判为"字母名"），并在规则模板与 SKILL.md 中双重提示。

## 12. 适用范围与限制

- 只整理输入清单内的文件：不上传网盘、不解析文档全文、不做存储迁移；真实移动文件由
  调用方按 directory_plan/ops 执行后回填 op.status。
- 版本链按「归一化文件名主干 + mtime」重建，主干相同但实为不同文档的极端情况会误并入链
  （哈希互异约束可缓解，残余风险登记在 uncertainties）。
- 增益对照是本校验层多模式对照，不等于平台基础 Agent 对照。
- 模型请求数不可由脚本采集，`efficiency.model_requests` 由 Agent 侧回填，缺失保持 null。

## 13. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/verify_check.py` 的 `analyze()` | 纯函数式（不写盘），`ablate` 参数可直接用作别处的"机制开关"对照实验 |
| `scripts/audit_ops.py` 的链式哈希 | op_id + prev_op_id + chain_hash 是通用"可回放操作日志"格式，任何需要审计链的场景可照抄 |
| `scripts/duplicate_check.py` 的哈希判重 | sha256 分组 + 最早正本 + 版本链归一化主干，任何"按内容去重"需求可直接照抄 |
| `classification_rules` 台账格式 | `{declared_at, rules[{rule_id,priority,match,category,basis}], fallback, naming_convention}` 是通用的"事前口径声明"台账 |
| `skipped_conflicts` 登记 | `{file_id, kind, detail, recovery}` 通用的"失败与恢复"入口格式 |
| `examples/` 合成案例 | 作为自测 fixture：复制一份改标签即得新的负例 |

## 14. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架/文件清单/哈希/规则模板（退出码恒 0） | 是 |
| scripts/classify_files.py | 规则机械重放归类 + 重命名建议 + 目录树 | 是 |
| scripts/duplicate_check.py | sha256 内容判重 + 版本链重建 | 是 |
| scripts/audit_ops.py | 操作审计链生成 + 链哈希自校验 | 是 |
| scripts/verify_check.py | 业务校验器（规则重放/判重复算/审计链/证据回证） | 是（含 `analyze()` API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 消融多模式增益对照 + 效率计数 + 污染反例 | 是 |
| examples/example-case.json | 合成输入示例（8 个虚构文件，含重复/版本/损坏条目） | 是（fixture） |
| examples/example-rules.json | 示例事前声明的分类规则与命名规范 | 是（fixture） |
| examples/example-result.json | 示意输出（非正式答案，流水线真实产出） | 是（fixture） |
| README.md | 本说明 | — |
| worklog.md | 开发记录、实测对照数字与诚实边界 | — |

## 15. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 7 节 C1–C8 自检 + 污染反例，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步更新 `schema_guard.py` 的 `RESULT_REQUIRED/FILE_REQUIRED`
  与 SKILL.md 的 schema 段；各脚本键归属见 SKILL.md「脚本分工」，新增脚本不得写他人键。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
