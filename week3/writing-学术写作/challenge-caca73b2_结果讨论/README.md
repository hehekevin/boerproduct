# acwrite-results — 结果与讨论章节写作 Skill

「学术效率」比赛 · 学术写作赛道 · 结果与讨论章节写作（challenge-caca73b2）参赛 Skill。

## 1. 目标用户与适用场景

**目标用户**：需要产出可投稿 Results & Discussion 章节的科研作者（生医/材料/化学/统计等任一学科）、论文返修与预审稿人、以及要求「每个数字都能回溯到图/表」的导师与期刊编辑。

**适用场景**：数据表、图、图注、统计输出**已经在手**，任务是把它们变成结构清楚、可核验的结果段与讨论段。
典型触发：写 Results & Discussion、把图转写成正文数字、核对正文数值与图表是否一致、给讨论结论补引用出处、审查因果表述是否越界。

**不适用**：需自行设计实验或生成科研绘图算法；材料完全缺失无法读数；要求本 Skill 代替真实实验数据（绝不补造数据）。

## 2. 核心能力

从数据表/图/图注/统计输出可靠读数，按图序写"只陈述观察"的结果段，讨论段每条论断带【依据】内联标注绑定本研究数据或具体文献，因果/相关边界受控、局限写到方法样本测量层面。交付**数字-来源逐条核对表**与**图表交叉引用完整性校验**，全部数值回溯到图表。

## 3. 安装与运行

### 依赖与版本
| 项 | 要求 | 缺失时行为 |
|---|---|---|
| Python | **3.8+**（标准库 `argparse/json/re/os/glob/hashlib/zipfile`） | 硬性要求 |
| python-docx | 可选，用于生成 `.docx` | 自动降级为 stdlib 最小 docx，降级事实写入 `render_log`/changelog |
| PyMuPDF (fitz) | 可选，PDF→PNG 预览 | 跳过 PNG，只出 PDF |
| openpyxl | 可选，读 xlsx | 降级为 zipfile 直接解 XML |
| 网络 / CDN / 配置文件 | **不需要**，全部路径为运行时契约 | — |

**零外部依赖是硬约束**：8 个脚本全部只用标准库；可选增强缺失时降级而非失败。

### 安装
无构建步骤、无包管理。直接把 `submission/` 目录放到 Agent 可读的位置即可：

```bash
# 目录结构
submission/
├── SKILL.md          # 主入口（强制协议 + 5 阶段工作流）
├── README.md         # 本文件
├── worklog.md        # 开发过程与双测证据
├── scripts/          # 8 个独立 CLI 脚本
└── examples/         # draft.json 结构示例 + gain_evidence 结构示例
```

### 运行（Agent 调用）
平台把 Skill 装到 `/skills/weekly-skill`，输入为 `/input/case.json` + `/input/task.md` + 原始材料，工作区 `/app/work`，交付 `/app/output`。

```bash
cd /skills/weekly-skill
# Stage 1 抄契约 + 抽材料
python3 scripts/extract_materials.py --input /input --outdir /app/work/extracted
# Stage 2 事实台账（读数登记由模型按 SKILL.md Stage 2 产出 readings.jsonl）
python3 scripts/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
# Stage 4 三重校验 + 同输入双跑
python3 scripts/trace_audit.py --draft /app/output/results_discussion.md --readings /app/work/readings.jsonl \
  --ledger /app/work/fact_ledger.jsonl --dclaims /app/work/dclaims.jsonl \
  --out-table /app/work/number_source_table.json --out /app/output/trace_audit.json
python3 scripts/trace_audit.py --draft /app/output/results_discussion.md --readings /app/work/readings.jsonl \
  --ledger /app/work/fact_ledger.jsonl --dclaims /app/work/dclaims.jsonl \
  --ablate stat_verify,strength_audit,claim_evidence,crossref,separation \
  --out /app/output/trace_audit_baseline.json
# Stage 5 构建 + 渲染 + 组装
python3 scripts/docx_build.py /app/work/draft.json --out-docx /app/output/results_discussion.docx \
  --out-md /app/output/results_discussion.md
python3 scripts/render_preview.py --src /app/output/results_discussion.docx --outdir /app/output/previews
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact results_discussion.docx --artifact-md results_discussion.md \
  --embed-md /app/output/results_discussion.md --readings /app/work/readings.jsonl \
  --trace-audit /app/output/trace_audit.json --gain-baseline /app/output/trace_audit_baseline.json \
  --source-table /app/work/number_source_table.json --dclaims /app/work/dclaims.jsonl \
  --status complete
```

**所有命令统一用 `python3` 调用。**

## 4. 输入输出解释

### 输入
| 输入 | 来源 | 必需 | 说明 |
|---|---|---|---|
| `case.json` | `/input/case.json` | 是 | 含 `case_id` 与 `output_contract`（最终 result.json 必须逐字段齐全，缺值填 null 并在 uncertainty 说明） |
| `task.md` | `/input/task.md` | 是 | 体裁/受众/字数/章节/引用样式等约束 |
| 原始材料 | `/input/` 下任意文件 | 是 | PDF/docx/xlsx/csv/图片/文本；**实际输入文件是事实依据**，不依据错误的领域标签补造数据 |
| `readings.jsonl` | 模型产出（Stage 2） | 是 | 读数登记：ref/panels/values/errorbar_meaning/caption_quote/locator |
| `fact_ledger.jsonl` | 脚本产出 | 是 | 事实台账：id/type/value/source/locator/quote |
| `dclaims.jsonl` | 模型产出（Stage 3） | 是 | 讨论结论溯源：did/claim/basis/locator/strength |

### 输出（全部落在 `/app/output`）
| 文件 | 内容 | 验收点 |
|---|---|---|
| `results_discussion.docx` / `.md` | 可编辑章节稿（结果/讨论分节，图注保留原文） | 满足体裁与受众 |
| `result.json` | **主交付**：契约字段齐全 + 主产物全文嵌入 + 全部核对表 + 增益证据 + 效率 + 语义映射 + uncertainty/changelog | 字段一个不缺，status 如实 |
| `number_source_table.json` | 每个数值 → source_ref + source_locator + verbatim + status | 逐条可回溯 |
| `readings.jsonl`（嵌入 result.json） | 图表读数全量登记 | 覆盖所有图表 |
| `fact_check.json` / `boundary_check.json` / `trace_audit.json` / `check_report.json` | 四份校验报告 | verdict 照实 |
| `trace_audit_baseline.json` | 退化基线模式报告（增益对照用） | 同输入指纹一致 |
| `previews/` | docx 的 PDF/PNG 渲染预览 | 无渲染器时如实标 `no_renderer`，不伪造 |

**result.json 关键字段**：`main_text_markdown`（全文）、`number_source_table`、`discussion_claims`、`readings`、`trace_audit`、`gain_evidence`（含 `metrics` 双口径对照）、`efficiency`、`output_semantics`（题面输出要求逐项 status）、`uncertainty`、`changelog`、`status`。

## 5. 机制清单

| 机制 | 实现 | 交付位置 |
|---|---|---|
| 数字-来源逐条核对表 | `trace_audit.py` 子检查 A：每个数值→source_ref+source_locator+verbatim+status | result.json `number_source_table` |
| 结果段↔图表交叉引用完整性 | `trace_audit.py` 子检查 B：登记↔引用双向核对，缺一 fail | result.json `trace_audit.crossref` |
| 讨论结论逐条溯源 | 句末【依据：…】内联标注 + `trace_audit.py` 子检查 C 机检 | result.json `discussion_claims` |
| 主产物全文嵌入 | `build_result.py --embed-md` | result.json `main_text_markdown` |
| 读数登记全量嵌入 | `build_result.py --readings` | result.json `readings` |
| 讨论结论 evidence 逐字五元组 | 子检查 C：{kind, evidence(≤40字逐字), source_id, location, strength} | result.json `discussion_claims.claims[]` |
| 限定强度机检 | 子检查 C：强断言词依据须为本研究数据；推测句须带限定语 | result.json `discussion_claims.strength_check` |
| 闸门状态显式枚举 | `gates` 输出 enforced / skipped_not_provided / not_found / unreadable / not_enforced_ablate | result.json `trace_audit.gates` |
| 描述/解释分离检测 | 子检查 D：结果段句含数值+推断词 → 推断-实测混淆数 | result.json `trace_audit.separation` |
| 结果表述逐句抽取 | 子检查 D：逐句记 numbers/refs/observation_only/issues | result.json `trace_audit.result_statements` |
| **退化/基线模式** | `trace_audit.py --ablate stat_verify,strength_audit,claim_evidence,crossref,separation` | result.json `gain_evidence` |
| **增益证据（双口径）** | fixed_evaluator（同一输入恒定→对照公平）＋ delivered（随护栏开关变化→增益落点） | result.json `gain_evidence.metrics` |
| **机制→指标映射** | 5 个可退化机制 → 对应指标与方向性说明 | result.json `gain_evidence.mechanism_to_metric` |
| **效率字段** | 步骤数/自动回证条数/待核条数/复核者负担/delivered 有据率/残留缺陷率 | result.json `efficiency` |
| **题面语义映射** | 结果表述/统计量/交叉引用/限定强度/解释与推断分离 + 三类输出内容逐项 status | result.json `output_semantics` |
| **全失败路径 exit 0** | 所有脚本失败路径退出码恒 0，verdict/error 照实落 stdout 与报告；`--strict-exit` 供 CI | 各脚本 stdout |
| 统计量提取修复 | NUM_RE 重写：p=/n=/CI/带±数/带单位数为必选 token，裸数字不误捕 | `trace_audit.number_source_summary` |

## 6. 增益证据（可复现，同输入两遍真实运行）

**方法**：同一草稿 + 同一 readings/ledger/dclaims，跑「完整模式」与「退化基线模式」（`--ablate` 关闭全部护栏）两遍，逐项对照。脚本内置**固定评估器**（`gain_metrics.fixed_evaluator`），对同一草稿恒定，用于证明两遍输入一致；`input_fingerprint` 给出 sha1。

**两层口径**（关键：固定评估器恒定，两遍相等正是"对照公平"的证据；增益要看 delivered 口径）：
| 口径 | 含义 | 作用 |
|---|---|---|
| `fixed_evaluator` | 对同一草稿恒定计算，与护栏开关无关 | 证明两遍跑输入一致（对照公平性） |
| `delivered` | 本模式实际交付给复核者的可核验量与人工负担 | 增益的真实落点（随护栏开关变化） |

**复现命令**：见 §3「运行」中 Stage 4 的两条 `trace_audit.py` 调用 + Stage 5 的 `build_result.py`。

**对照指标**：
- *fixed_evaluator 口径*（两遍恒定）：统计表述有据率、统计表述总数（分母）、有逐字来源的统计表述数、未回证数值数、强断言违规数、推断-实测混淆数、需人工核对条目数。
- *delivered 口径*（随护栏开关变化）：统计表述有据率、强断言违规数（已检出）、推断-实测混淆数（已检出）、复核者人工负担、残留缺陷率、流程步骤数、检出缺陷数、检出覆盖率、自动回证条数、仍需人工回材料核对条数。

**边界（已写入 result.json `gain_evidence.boundaries`）**：
- 对照是同一草稿的「机制开关」对照，证明护栏的**检出能力**；**不等于**「不加载 Skill 的基础 Agent」对照——后者由平台在固定案例上运行并比较，本包不预置其结果。
- 退化基线关闭护栏后计数归零属**统计假象**（未检出不等于不存在）；真实缺陷数一律以 fixed_evaluator 口径为准。
- 质量增益以检出缺陷数与覆盖率为代理指标；最终章节质量分由平台评分表给出，本包不臆造评分。
- 效率以步骤数与人工负担为代理指标；真实请求数/耗时由平台记录，本包不虚构平台数据。

## 7. 最小可运行自检清单（5 条命令）

复制到包目录下逐条执行，全部应返回**退出码 0** 且 stdout 为 JSON（下表用 `_acw/` 作临时目录，可用任意可写路径替代）：

```bash
mkdir -p _acw
# 1. 材料抽取（无输入也应如实报 total=0，不崩溃）
python3 scripts/extract_materials.py --input /input --outdir _acw/ext

# 2. 事实台账构建（无源文件应如实产出空台账）
python3 scripts/fact_ledger.py build --sources _acw/ext --out _acw/ledger.jsonl

# 3. 四合一审计（缺输入时应 gate 枚举 + exit 0）
python3 scripts/trace_audit.py --draft _acw/missing.md --readings _acw/missing.jsonl --out _acw/ta.json

# 4. 组装 result.json（缺契约也应照实产出，exit 0）
python3 scripts/build_result.py --case _acw/missing.json --out _acw/result.json

# 5. 退出码契约自检（校验类脚本失败路径必须为 0）
python3 scripts/boundary_check.py --draft _acw/missing.md; echo "exit=$?"   # 期望 exit=0
```

**通过标准**：5 条命令全部退出码 0；第 3 条 stdout 含 `"gates"` 且 `readings` 为 `not_found`/`skipped_not_provided`；第 4 条产出合法 JSON 且 `status` 如实为 `partial`。任一条返回非 0 即为**阻断性缺陷**（交付链会中断）。

## 8. 验收方式

| 层 | 验收动作 | 通过标准 |
|---|---|---|
| 脚本层 | 跑 §7 自检清单 | 5 条命令 exit=0；gate 状态如实枚举 |
| 机制层 | 对同一稿跑完整模式 + `--ablate` 退化模式 | `same_input_verified=true`；fixed_evaluator 两遍逐字段相等；delivered 口径 5 项核心指标有差异 |
| 产物层 | 抽读 `result.json` | 契约字段一个不缺（缺值 null + uncertainty 说明）；`main_text_markdown` 全文已嵌入；`number_source_table` 每行有 source_ref/locator/verbatim/status |
| 边界层 | 故意提交篡改数值/强断言/无依据结论/漏引图的稿 | 完整模式逐条报出且 exit=0；退化模式 `verdict=pass` 但 `gates` 标 `not_enforced_ablate` |
| 文档层 | 核 README 与 SKILL.md | README 含依赖/安装/输入输出/用户场景/验收/FAQ/限制/失败处理/复用/维护；SKILL.md ≤150 行 |

**双测证据**：见 `worklog.md`「本地双测证据」与「污染数据反例」两节，含真实运行数字。

## 9. 常见问题（FAQ）

**Q：脚本返回 0 但 `verdict=fail`，是 Bug 吗？**
不是。这是设计：所有失败路径退出码恒 0，交付链不中断；失败内容以 `verdict`/`fail_count`/`problems` 如实落在报告与 stdout。CI 需要非 0 时加 `--strict-exit`（仅校验类脚本支持）。

**Q：`gates` 里出现 `skipped_not_provided` / `not_found` / `unreadable` / `not_enforced_ablate` 怎么办？**
说明该检查项**没有真正运行**。下游不得宣称"已核对"。补齐该输入后重跑；退化对照遍的 `not_enforced_ablate` 是机制开关的正常标记。

**Q：图是位图、没有数据表，数值怎么写？**
视觉估读并在 `readings.jsonl` 标 `estimated_from_figure` + 给出估读依据；关键数值在 `uncertainty` 中声明建议作者以原始数据复核。**读不到的数值不写**，列入 `reading_gaps`。

**Q：图注没说误差棒含义（SD/SE/95%CI）？**
不臆断。正文写"图中误差棒（含义未注明）"并列入 `reading_gaps`，不替作者补一个含义。

**Q：`p=0.09` 能不能写"显著升高"？**
不能。`boundary_check.py` 会判 `significance_misuse`。正确写法："趋势一致但未达显著（p=0.09）"。

**Q：讨论段能不能写"导致/证明"？**
只有材料含干预设计（随机对照/干预/工具变量/DID 等依据）时才可用因果词；观察性数据用"相关/伴随/提示"。`boundary_check.py` 判 `causal_overreach`。

**Q：`build_result.py` 提示 gain_evidence 缺失？**
说明没传 `--gain-baseline`（退化基线运行的 trace_audit 报告）。补跑 Stage 4 的第二条命令再组装。

**Q：为什么增益对照不是"不加载 Skill 的基础 Agent"？**
平台固定案例的对照由平台运行；本包不预置其结果（也不得预置）。本包能做的是同一输入的**机制开关对照**，证明护栏的检出能力。

**Q：docx 没生成？**
python-docx 缺失时自动降级为 stdlib 最小 docx（仍在 `.docx` 路径）；`render_preview.py` 无渲染器时如实写 `status=no_renderer`，不伪造预览。

## 10. 已知限制

- 读数依赖模型视觉/文本抽取能力；极低分辨率图或复杂多面板图的精确读数可能不准，一律标 `estimated_from_figure` 并建议复核。
- `dclaims.jsonl` 与 `readings.jsonl` 的联动目前为条数绑定，尚未做语义级对齐。
- `boundary_check.py` 的 `reading_trace_note` 为提示性，完整数值核查以 `fact_ledger.py check` 为准。
- 增益证据为「同一输入的机制开关对照」，**不可外推**为「不加载 Skill 的基础 Agent」对照。
- 效率以步骤数与人工负担为代理指标，不等于模型请求数或真实耗时（由平台记录）。
- 未覆盖结构化/表格类"结果"产物（结果段必须成文），非中英双语并行写作。

## 11. 失败处理

| 情形 | 处置 |
|---|---|
| 图是位图无数据表 | 视觉估读 + 标 `estimated_from_figure`；关键数值建议作者以原始数据复核 |
| 图注未说明误差棒含义 | 不臆断；正文写"图中误差棒（含义未注明）"并列入 `reading_gaps` |
| 图注与图面数值不一致 | 记 `conflict`；正文以数据表为准；uncertainty 说明 |
| 统计输出缺失 p 值 | 不编显著性；写"差异未报告显著性检验" |
| 材料只有数据无图 | 按数据表写结果；建议作图列入 uncertainty |
| 任务要求合并写 R&D | 保持描述/解释分句纪律，段落角色分明 |
| 中英数据口径（万/亿 vs million） | 按材料原口径；换算时记录换算式于 `evidence_map` |
| 脚本报错/依赖缺失 | 三级容错（重试→降级→如实记录）；不阻塞交付，status 如实 |
| 校验脚本报 fail | 记录 fail 计数→修稿件→重跑；退出码恒 0，不因此放弃交付 |
| 熔断触发（48 请求 / 700 秒） | 立即收尾：现有内容过 Stage 5，缺项写 uncertainty |

**统一原则**：任何失败都不阻断交付。verdict/status 如实记录，缺口写进 uncertainty，绝不伪造成功。

## 12. 复用建议

| 资源 | 路径 | 复用方式 |
|---|---|---|
| 章节写作模板 | `examples/example_input.json` | draft.json 结构（章节/段落/表格/图/参考文献/待人工确认），复制改名即可起稿 |
| 读数登记 schema | `SKILL.md` Stage 2 | readings.jsonl 字段定义（ref/values/errorbar_meaning/caption_quote/locator） |
| 讨论结论表 schema | `SKILL.md` Stage 3 | dclaims.jsonl 字段定义（did/claim/basis/locator/strength） |
| 交付自查清单 | `SKILL.md` 第 4 节 | 逐项可勾选清单，对应题面五维考察点 |
| 增益对照方法 | 本文件 §6 + `gain_evidence.mechanism_to_metric` | 机制→指标映射表可套用到其他写作 Skill 的消融对照 |
| 增益证据结构示例 | `examples/gain_evidence_example.json` | 目标结构参考，换自己的稿件即可得对应数字 |
| 校验脚本（8 个） | `scripts/` | 均可独立 CLI 调用，参数化输入输出，可单独接入他人流程 |

**迁移到其他写作场景**（如引言、相关工作、方法章节）：
1. 换 `trace_audit.py` 的 `INFER_WORDS`/`REF_RE` 为目标章节的规则；
2. `WORKFLOW_STEPS`（步骤计数）按新流程改；
3. `--ablate` 的 5 个机制名换成新护栏名；
4. `output_semantics` 的 5 项换成新题面的输出要求。
其余（核对表结构、双口径对照、exit 0 契约、闸门枚举）可原样复用。

## 13. 评分表自评对照（供评审快速定位证据）

| 评分维度 | 本包对应交付物 | result.json 字段 |
|---|---|---|
| 实际效果·任务完成度 | results_discussion.docx/.md 全文嵌入 | `main_text_markdown`、`deliverable` |
| 实际效果·结果正确性 | 数值逐条回证表 | `number_source_table`、`trace_audit.number_source_summary` |
| 实际效果·结果完整性 | 图表登记 + 双向交叉引用 + 结论溯源 | `readings`、`trace_audit.crossref`、`discussion_claims` |
| 实际效果·结果可核验性 | 逐字 evidence + 定位 + 语义映射 | `discussion_claims.claims[]`、`output_semantics` |
| 使用增益·质量增益 | 同输入双跑（delivered 口径）检出率对照 | `gain_evidence.metrics`、`detection_coverage` |
| 使用增益·效率增益 | 自动回证数 vs 人工核对负担 | `efficiency`、`gain_evidence.metrics` |
| 使用增益·增益可验证性 | 复现命令 + sha1 指纹 + 双口径 + 边界声明 | `gain_evidence.how_to_reproduce`、`input_fingerprint`、`calibers`、`boundaries` |
| 创新增益·新增能力 | 退化模式 + 固定评估器 + 语义映射 | `trace_audit.gain_metrics`、`output_semantics` |
| 创新增益·方法改进 | 四合一审计（核对/交叉引用/溯源强度/分离） | `trace_audit` 四子检查 |
| 创新增益·创新证据 | 机制→指标映射 + 边界 | `gain_evidence.mechanism_to_metric` |
| 可靠体验·调用易用性 | SKILL.md 5 阶段 + 异常处置表 + 最小示例 + 自检清单 | — |
| 可靠体验·运行稳定性 | 全失败路径 exit 0 + 三级容错 + 顶层安全网 | 各脚本 `--strict-exit` 语义 |
| 可靠体验·异常处理 | 异常处置表 + gates 枚举 + 12 类失败处理 | `trace_audit.gates` |
| 生态贡献·文档完整性 | 本文件 + SKILL.md | — |
| 生态贡献·资源可复用性 | 见 §12 可复用资源表 | — |
| 生态贡献·分享推广价值 | 增益对照方法可迁移其他写作 Skill | `gain_evidence.mechanism_to_metric` |

## 14. 文件清单

- `SKILL.md` — 强制执行协议 + 5 阶段线性工作流 + 异常处置表 + 最小示例 + 自查清单（149 行）
- `scripts/`（8 个）— extract_materials / fact_ledger / boundary_check / consistency_check / trace_audit / docx_build / render_preview / build_result
- `examples/example_input.json` — draft.json 结构示意（含【依据】标注示例）
- `examples/gain_evidence_example.json` — gain_evidence 目标结构示例（合成夹具真实双跑数字，已标注非正式案例结果）
- `worklog.md` — 开发过程、对照题面五维差距清单、双测证据

## 15. 维护与版本

- **版本 2.2**（增益可验证 + 交付稳定版）：保留 83 公式全部要素（全文嵌入/闸门四态+ablate 态/status 诚实四级/逐字回证/五元组），新增双口径增益对照（fixed_evaluator + delivered）、全失败路径 exit 0 契约、README 生态贡献全套（依赖版本/输入输出/验收/FAQ/限制/失败处理/复用建议/最小自检清单）。
- **兼容性**：新增字段均为增量，不改变既有字段语义；旧版调用方式（不传 `--gain-baseline`）仍可用，此时 result.json 如实标注 gain_evidence 缺失并在 uncertainty 说明。
- **扩展点**：新材料格式扩展 `scripts/extract_materials.py` 的 `ext_map` 与对应解析函数；新护栏加入 `trace_audit.py` 的 `ABLATABLE` 与 `WORKFLOW_STEPS`。
- **维护者**：参赛者本人；问题反馈通过赛事平台提 issue。

## 16. 适用边界

- 仅处理给定材料支撑的写作任务；材料外的学科惯例改动记录在 changelog。
- 不做科研绘图算法本身；聚焦从材料到成稿与逐条溯源。
- 增益证据为「同一输入的机制开关对照」，不可外推为「不加载 Skill 的基础 Agent」对照。
