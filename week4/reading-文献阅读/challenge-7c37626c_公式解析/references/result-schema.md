# result.json 输出契约（完整字段规格）

> 本文件是 `SKILL.md` §2 schema 的展开版。SKILL.md 只保留骨架与纪律，
> 逐字段说明在此，便于按需查阅而不必把整份 schema 常驻上下文。

## 顶层键（缺一不可）

| 键 | 类型 | 说明 |
|---|---|---|
| `case_id` | string | 取自 `/input/case.json` 的 `case_id`/`id`，原样抄写 |
| `status` | string | 诚实四级：`answered` / `partial` / `insufficient_evidence` / `input_error` |
| `result` | object | 主产物（见下） |
| `claims` | array | 关键论断，每条带逐字 evidence |
| `uncertainties` | object | 未报告/不可核验/冲突/需人工/摘要 |
| `changelog` | array | 变更记录 `{step, change}` |
| `gain_evidence` | object | 由 `gain_probe.py` 写入：两臂对照数字 + 机制→指标映射 + 边界与失效条件 |
| `efficiency` | object | 由 `gain_probe.py` 写入：可自动采集的效率计数 |

`case.json` 的 `output_contract` 若含更多键，**原样照抄生成**并填 `unknown` 或空数组，
不得删键、不得编造数据。

## result.formulas[]（数组，不许空）

| 字段 | 说明 |
|---|---|
| `formula_id` | 公式标识（XML `id` 或 `math-N`） |
| `source_locator` | 回原文定位：`publisher-source.xml#f2 / Eq.(3) §3.1` |
| `latex` | 还原的 LaTeX（非空串是生命线） |
| `conversion` | `full` / `partial` / `failed` |
| `ambiguity_notes` | `partial` 时必填：降级原因与待人工校对点 |
| `mathml_raw_present` | 原文是否含 MathML 节点 |
| `semantics[]` | 逐符号语义块（见下） |

### result.formulas[].semantics[]（逐符号解读，"讲得清"）

| 字段 | 说明 |
|---|---|
| `symbol` | 符号（与 `variables[].symbol` 对齐，希腊字母用统一形态） |
| `meaning` | 该符号在此公式中的物理/数学含义（论文原话或最近定义改写） |
| `dimension` | 量纲或类型（W / 无量纲 / 矩阵 m×n / 无量纲算子） |
| `typical_value` | 论文给出的取值；**未给一律 `null`，不猜** |
| `provenance` | `原文定义` / `上下文推断` / `常识补充`（枚举，三者不可混用） |
| `source_location` | 定义位置（段落号/公式号/表号）；`原文定义` 时必填 |

## result.variables[]（全局变量表）

`symbol`、`latex`、`definition`、`units`、`range`、`first_defined_at`、`provenance`。
与 `semantics` 同符号对齐；同名符号两处定义必须一致。`provenance=原文定义` 时
`first_defined_at` 必填。常识补充项须同时登记进 `uncertainties.human_review`。

## result.derivations[]（推导链，"推得顺"）

| 字段 | 说明 |
|---|---|
| `step_no` | 步序号（依赖顺序即计算顺序） |
| `expression` | 该步表达式 |
| `recomputable` | bool；true = 代入论文参数即可算出 |
| `using[]` | 所用假设/近似 |
| `depends_on[]` | 跨公式依赖（如 `["Eq.(3)"]`） |
| `why_valid` | 为何这一步成立 |
| `gap` | bool；true = 原文跳步，须列入 `uncertainties` |
| `intermediate_value` | 该步算出的中间值；`recomputable=true` 时**必填** |
| `evidence[]` | `{paragraph_id, quote}` 逐字摘录论文参数；`recomputable=true` 时**必填且 quote 非空** |

## result.verification[]（数值核验，"算得回"，数组不许空）

| 字段 | 说明 |
|---|---|
| `formula_id` | 对应公式 |
| `inputs[]` | `{symbol, value, units, source}`；`units`+`source` **必填**（别人才能用同一套输入重跑） |
| `expected` | 原文报告值 |
| `computed` | 本 Skill 复算值（不得只填其一） |
| `within_tolerance` | bool；声明容差时相对误差须 ≤5% |
| `status` | `verified` / `not_recomputable` |
| `missing[]` | `not_recomputable` 时逐项列出缺失输入（必填） |
| `notes` | 数量级异常时先怀疑读数与单位并说明 |

## result.coverage（计数汇总）

`formulas_total`、`converted_full`、`variables_defined`、`derivation_steps`、
`verified`、`not_recomputable`、`semantics_covered`、`recomputed_steps`。

## claims[]（关键论断）

`claim_id`、`text`、`kind`（`reported`/`inferred`）、`source_id`、`location`、
`evidence[]`（`{paragraph_id, quote}`，quote 必须逐字非空）。

## uncertainties（证据与边界）

| 键 | 内容 |
|---|---|
| `unreported[]` | 材料未报告的项 |
| `unverifiable[]` | 不可核验的结论 |
| `conflicts[]` | 材料冲突 |
| `human_review[]` | 需人工接管的位置（含常识补充符号、降级公式） |
| `summary` | 缺口与降级记录摘要 |

## gain_evidence（增益取证，由 gain_probe.py 写入）

| 键 | 内容 |
|---|---|
| `baseline_kind` | 固定为 `skill_mechanism_ablation`（本 Skill 机制消融基线） |
| `baseline_disclaimer` | 明示：非平台「基础 Agent 不加载 Skill」白板 |
| `mechanism_to_metric[]` | 机制 → 开关 → 指标 → 期望方向 → 证据类型 |
| `projection_rules[]` | 消融投影规则（P1-P5，确定性可复算） |
| `arms` | `skill_full` / `skill_mechanism_ablation` 两臂的公式层/变量表/核验/推导/人工核对指标 |
| `comparison` | 逐项 `{skill_full, skill_mechanism_ablation, delta, source}` |
| `boundaries[]` | 对照的适用边界 |
| `failure_conditions[]` | 失效条件（缺输入、产物不可读、投影非确定等） |
| `run_log[]` | 双跑的真实 argv / returncode / wall_seconds |

## efficiency（效率计数，由 gain_probe.py 写入）

`wall_clock_seconds`（各脚本真实耗时）、`script_invocations`(+detail)、
`artifact_counts`（公式/语义块/变量/推导步/核验/论断/不确定项计数）、
`conversion_throughput`（完整模式 vs 消融模式公式数与吞吐）、
`artifacts_written`、`model_requests`（**null**，平台记录，Skill 不编造）、
`official_score`（**null**，平台生成，不预置）、`reproduce`（复现命令）。
