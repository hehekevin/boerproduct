# multi-db-merge — 多数据库联合检索 Skill（v1）

针对 Bohrium 产品赛第 4 周「科研检索」赛道「多数据库联合检索」(challenge-5c918ff0)
的参赛 Skill。锁定子场景：**库选择 → 检索式适配 → 合并去重 → 冲突登记 → 覆盖矩阵**。

## 1. 用途与适用条件

给定组织方提供的各学术数据库响应材料（Crossref/EuropePMC/publisher 等本地化响应），
完成五件事：

1. **按库编排查询**：每库按自身语法、字段能力适配检索式，禁止把同一条查询机械复制
   到所有库；逐库登记查询状态、失败阶段（connect/auth/rate_limit/syntax/parse）与原因。
2. **字段归一**：DOI 去前缀转小写、标题 CJK 逐字分词（规避 `isalpha` 汉字陷阱）、
   作者词元化、年份截取、期刊名空白/标点归一；缺失与 unknown 显式区分。
3. **去重合并**：DOI 精确匹配 + 标题 Jaccard/作者/年份模糊比对（并查集划分），
   策略参数**事前声明**（阈值/容差/优先级 + basis + declared_at，事后禁调）；
   阈值边缘判定走 `method=manual` 人工仲裁入口。
4. **冲突登记**：同组记录字段取值不一致（年份/期刊/作者写法等）逐条登记
   `{record_id, field, values, resolution, basis}`，按库优先级消解、其余值保留备查，
   不静默吞掉。
5. **覆盖矩阵与来源链**：库 × 字段覆盖矩阵 + 单库来源记录 + 系统性缺失字段；
   每条合并记录可沿「库—查询—原始响应(raw_ref)—字段来源」链路逐条回溯。

**核心保证**：合并划分、相似度、计数、冲突登记、覆盖矩阵全部由确定性引擎
`dedup_core.py` 机械复算；校验器在同一输入上重跑引擎做逐组比对，并把检查三元组
`{item, template_value, applied, match}`、闸门状态与 unbacked 清单回写
result.json（键 `self_check` / `gates` / `unbacked_numbers` / `validator_verdict`），
评分器不开附件即可核对。所有校验脚本失败路径**退出码恒 0**，结论记 verdict。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|------|------|---------|
| 科研人员 / 图书馆员 | 一个研究问题要查多个学术库，要一份能核对的不重复清单 | 合并记录集（带 relevance_basis）、去重判定解释、冲突登记、覆盖矩阵 |
| 系统综述作者 | PRISMA 式筛选需要保留每条记录的来源与筛选依据 | 来源链（库—查询—raw_ref）+ 每库登记的检索式台账 |
| 数据整合工程师 | 多源记录合并的字段冲突需要可解释的消解规则 | 字段优先级策略 + 冲突 values 全量留痕 + resolution basis |
| 教学 / 培训 | 演示"事前声明策略 + 机械复算去重"的检索纪律 | 可复算的对照实验（gain_evidence） |

**不适用**：不发起真实网络请求、不绕过服务限制、不做单库全文阅读、
不把未经授权的数据汇总到未批准服务。

## 3. 依赖与环境

| 项 | 要求 |
|----|------|
| Python | **3.8+**（本包在 3.13 上实测通过），只用标准库（json/os/re/sys/argparse/copy/math/time） |
| 第三方依赖 | **零**，无需联网 |
| 操作系统 | Linux / macOS / Windows（路径全部 argparse 参数化） |
| 磁盘 | 整包 < 200 KB |
| 资源上限 | 平台契约：≤50 个 UTF-8 文本文件、单文件 ≤500 KB、总计 ≤2 MB、无符号链接 |

## 4. 安装与运行

**安装**：把 `submission/` 目录挂到评测约定的技能路径（本赛题约定 `/skills/weekly-skill`），
无需安装步骤、无依赖解析、无需联网。

```bash
# Step 0：落骨架 + 材料签名扫描（必做，第一个动作）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
# Step 2：机械去重合并管线（只写 5 个业务键）
python3 /skills/weekly-skill/scripts/dedup_core.py --result /app/output/result.json --apply
# Step 5：增益对照 + 效率计数（真实数字回写 result.json）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into --inject-pollution
# Step 6：双重自检（退出码恒 0；判据是报告里的 verdict）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```

## 5. 输入与输出

- **输入**：`/input/case.json`（研究问题 + 各库响应材料 + output_contract）、`task.md`。
  **以实际文件为准，不依据标签假设内容**（build_skeleton 用内容签名扫描命中）。
- **输出**：`/app/output/result.json`
  - 顶层：`case_id` / `status` / `result` / `claims` / `uncertainties` / `changelog`
    + `self_check` / `unbacked_numbers` / `gates` / `validator_verdict`
  - `result` 内：`material_gaps`、`environment`、`databases`、`raw_hits`、
    `dedup_policy`、`merged_records`、`dedup_decisions`、`conflicts`、
    `coverage_matrix`、`dedup_metrics`、`attributions`、`steps`、`run_status`、
    `verdict`、`verdict_basis`、`gain_evidence`、`efficiency`
- **status**：`answered` | `partial` | `insufficient_evidence` | `input_error`。
- **工作区产物**：`/app/work/verify_check.json`、`/app/work/schema_guard.json`、
  `/app/work/gain_evidence.json`、`/app/work/dedup_policy.json`（策略声明台账）、
  `/app/work/gain_probe_polluted.json`（污染反例副本）。

## 6. 最小调用示例（示意，非正式案例答案）

`examples/` 提供合成案例：3 个模拟库返回 8 条记录（含 DOI 前缀/大小写陷阱、
CJK 标题空格陷阱）、另有 1 库模拟 429 限流失败；引擎合并为 5 条记录、
登记 5 处字段冲突（作者写法 ×2、标题空格、期刊缩写、年份差 1）。
示意输出关键片段：

```json
{
  "case_id": "demo-merge-001", "status": "answered",
  "result": {
    "dedup_metrics": {"raw_hits_total": 8, "merged_records_total": 5,
                       "duplicates_merged": 3, "single_source_records": 3},
    "dedup_decisions": [{"pair": ["H003", "H004"], "method": "title_fuzzy",
                          "similarity": 1.0, "reason": "CJK 逐字分词 Jaccard=1.0000 ≥ 0.82"}],
    "conflicts": [{"record_id": "R003", "field": "year",
                    "values": {"H005": 2019, "H006": 2020}, "resolution": "2019（europepmc 优先）"}],
    "verdict": "merged"
  }
}
```

## 7. 验收标准（最小自检清单，均实测）

| 编号 | 验收项 | 判定方式 | 实测 |
|------|--------|---------|------|
| A1 | 契约字段齐 | `schema_guard` verdict=PASS（output_contract 全字段 + 17 个业务键） | PASS |
| A2 | 业务逻辑齐 | `verify_check` verdict=PASS，problems 为空 | PASS |
| A3 | 数字全回证 | `unbacked_numbers` 为空数组 | ✓ |
| A4 | 来源链完整 | traceability_ratio=1.0（库+查询+raw_ref 三要素齐） | 1.0 |
| A5 | 划分与引擎一致 | partition_agree=5/5 | ✓ |
| A6 | 策略事前 | dedup_policy 含 threshold/basis/declared_at；相似度复算差 ≤±0.05 | ✓ |
| A7 | 冲突全登记 | 引擎检出 5 处 = conflicts 登记 5 处 | ✓ |
| A8 | 失败降级诚实 | pubmed failed + failure_stage=rate_limit + reason + 矩阵缺口标注 | ✓ |
| A9 | 增益有据 | gain_evidence.runs 含 normal/degraded 两遍实跑 + delta + 机制映射 + 边界 | ✓ |
| A10 | 污染被抓 | pollution_selftest.caught_by_normal_mode == true | true |
| A11 | 失败路径 exit 0 | 四条命令 + ablate 变体全部退出码 0（见 worklog 实测记录） | ✓ |

## 8. 增益对照机制（增益可验证性，全部实测）

`gain_probe.py` 对**同一份**输入跑两遍（同校验器双跑）：

| 模式 | 引擎参数 | 回证检查 |
|------|---------|---------|
| `normal` | 归一 + DOI/模糊匹配 + 冲突检测全开 | 开启 |
| `degraded`（ablate=all） | 归一关 / 模糊关 / 冲突检测关 | 关闭 |

合成案例实测（example-result.json 内为真实回写数字）：

| 指标 | normal | degraded | delta | 方向 |
|------|--------|----------|-------|------|
| machine_adjudicated_ratio | 100% | 0% | +1.0 | 高好 |
| engine_agreement_ratio | 1.0 | 0.6 | +0.4 | 高好 |
| manual_review_items | 0 | 12 | −12 | 低好 |
| steps_count | 71 | 62 | +9 | 参考 |
| clarification_rounds | 0 | 4 | −4 | 低好 |

**同校验器双跑 FAIL 差**：同一份正确交付，normal=PASS（0 problems），
degraded=FAIL（3 处划分误报）——退化引擎会把正确跨库合并误判为不一致，
每条误报都需人工复核，这就是归一+模糊匹配机制的量化价值。
污染反例自测：副本注入静默拆分/删冲突/断来源链/计数造假/清空 claims/静默失败 6 类污染，
normal 抓到 10 处 problems（caught=true），degraded 漏掉冲突登记检查（conflict_missed=1）。

> **重要边界**：这是本校验层"正常 vs 退化"两模式对照，**不等于**平台
> "基础 Agent vs 参赛 Skill"的白板对照；后者由平台生成，本探针不代替、不冒充。

## 9. 异常处理

| 异常 | 处置 |
|------|------|
| 某库响应缺失/限流/超时 | status=failed + failure_stage + failure_reason，矩阵标缺口，attributions 记 db_unavailable |
| 字段缺失/语义不等价 | field_sources 记实际来源库；缺失与 unknown 区分；系统性缺失入 uncertainties |
| 阈值边缘去重拿不准 | method=manual + arbitration=manual，保留人工仲裁入口，机器不复算 |
| 响应格式/编码异常 | raw_hits 照常登记 + raw_ref 指向原始片段，不脑补字段 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了如实登记 uncertainties |
| 校验脚本自身故障 | **退出码恒 0**，结论记在报告 verdict 字段，绝不中断交付 |
| 运行中断 | 仍写 result.json（status=partial），注明中断点与已完成部分 |

## 10. 常见问题 FAQ

**Q：为什么校验脚本失败也返回 0？**
平台契约要求"失败也要交付"。脚本把结论写进报告的 `verdict` 与 `problems`，Agent
读报告判断是否修复；退出码恒 0 保证流程不被校验器自身故障打断（协议第 7 条）。

**Q：`--ablate` 是不是让结果更好看？**
不是。退化模式让引擎变弱：正确交付会被误报划分不一致（FAIL）、数值位失去机器判定、
人工核对条目上升——它量化的是"关闭这些机制会损失多少"，只用于增益对照。

**Q：为什么去重判定要事前声明阈值？**
事后调参凑结果会让去重不可复算、不可信任。`dedup_policy` 必须在匹配前写定
basis 与 declared_at，verify_check 核对声称相似度与引擎复算差 ≤±0.05。

**Q：中文标题怎么分词？**
显式字符类 `[a-z0-9]+|[\u4e00-\u9fff]`：拉丁/数字整词、汉字逐字。
不用 `str.isalpha()`（汉字 isalpha=True 会把整句连成一个"词"），
引擎自含回归自测。

**Q：作者名写法不一致（Smith J vs John Smith）算冲突吗？**
算——登记但不判死：resolution 按库优先级取全名形式，其余写法保留备查。
宁可多登记，不静默吞掉（题面明确要求冲突显式说明）。

**Q：某库没返回结果怎么办？**
查询 status=failed/limited/skipped + failure_stage + failure_reason，
矩阵标 not_applicable/缺口，attributions 记 db_unavailable；不补造文献。

## 11. 适用范围与限制

- 检索在组织方提供的本地响应材料上进行：不发起真实网络请求、不装 pip 依赖。
- 去重阈值/容差是本技能事前声明（案例未给时按保守值设定并注明 basis）。
- 人工仲裁记录（arbitration=manual）机器不复算，属题面要求的仲裁入口。
- 增益对照是本校验层两模式对照，不等于平台基础 Agent 对照。
- 追问轮次按每轮 3 条折算是估计量，原始计数 manual_review_items 一并落盘可换算。
- `efficiency.model_requests` 不可由脚本采集，由 Agent 回填，缺失保持 null。

## 12. 复用建议（给其他作者/其他赛道）

| 可复用资源 | 复用方式 |
|-----------|---------|
| `scripts/dedup_core.py` 的 `engine_partition()` | 纯确定性去重/合并/冲突/覆盖引擎，任何多源整合场景可直接 import；`ablate` 参数即机制开关 |
| FIELD_ALIASES + DB_SIGNATURES | 内容签名式材料识别，不依赖文件名标签，可加条目扩展 |
| CJK 分词 `title_tokens()` | `[a-z0-9]+|[\u4e00-\u9fff]` 模式可直接抄，防 isalpha 陷阱 |
| `dedup_policy` 台账格式 | `{threshold, tolerance, priority, basis, declared_at}` 通用"事前声明"台账 |
| `verify_check.py` 的 `analyze()` | 纯函数式 + 三元组自检 + 闸门四态 + 引擎复算比对，换业务 schema 即可复用 |
| `gain_probe.py` 双模式对照 | 换掉 analyze 即可测任何校验器；指标公式写在 mechanism_to_metric_map |
| `examples/` 合成案例 | 自测 fixture：复制后改记录/加陷阱即得新负例 |

**建议复用顺序**：先抄 `dedup_core.engine_partition`（拿到确定性引擎），
再抄 `verify_check.analyze`（拿到三元组+闸门+回证），最后抄 `gain_probe`
双模式对照（拿到可验证的增益证据）。

## 13. 资源清单

| 文件 | 作用 | 可否单独复用 |
|------|------|------------|
| SKILL.md | 技能本体（8 条强制协议 + 七步流程 + schema + 校验说明） | 是（加载入口） |
| scripts/build_skeleton.py | Step 0 落骨架 + 内容签名材料扫描（三级容错，退出码恒 0） | 是 |
| scripts/dedup_core.py | 领域引擎：归一/去重/合并/冲突/覆盖（--apply 写 5 业务键） | 是（含 CJK 自测） |
| scripts/verify_check.py | 业务校验器（检索式合规/来源链/划分复算/相似度复算/冲突/覆盖/回证） | 是（含 analyze() API） |
| scripts/schema_guard.py | output_contract + 业务 schema 结构守卫 | 是（通用） |
| scripts/gain_probe.py | 正常 vs 退化双模式增益对照 + 效率计数 + 污染反例自测 | 是（含指标公式） |
| examples/example-case.json | 合成输入示例（3 库响应 + 限流失败 + 各类陷阱） | 是（fixture） |
| examples/example-result.json | 示意输出（含真实 gain_evidence，非正式答案） | 是（fixture） |
| README.md | 本说明（十项） | — |
| worklog.md | 开发记录与双测证据 | — |

## 14. 版本与维护

版本 **v1**（2026-11-19）。依赖：Python 3.8+ 标准库，无第三方依赖。

**维护约定**
- 改动 `scripts/*.py` 后必须重跑第 4 节五条命令 + `--ablate` 变体，确认 verdict=PASS。
- 改动 `SKILL.md` 后检查 `wc -l SKILL.md` ≤ 150。
- 改动业务 schema 时同步 `schema_guard.py` 的 `RESULT_REQUIRED` 与 SKILL.md schema 段。
- 脚本写键分工固定（见 SKILL.md 定位段），新增脚本前先核对不与现有脚本写同一键。
- 平台契约上限：≤50 文本文件、单文件 ≤500 KB、总计 ≤2 MB；新增文件前先核对。
- 不预置正式案例答案：`examples/` 全部为合成案例并标注"示意"。
