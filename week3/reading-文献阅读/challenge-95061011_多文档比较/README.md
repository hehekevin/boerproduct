# doc-compare-r5 — 多文档比较与整合 Skill

面向"同一研究问题的多篇论文"，产出**可逐格回溯的两两比较矩阵 + 共同字段比较矩阵**，
并附带**同输入三遍对照的增益取证**与**可复算效率计数**。

相对 r4 的核心增强：①按题面「Skill 运行后的输出要求」表逐项对齐，新增 `status_reason`
（运行状态附原因）与 `sources`（来源登记）两个契约键，uncertainties 强制六分区；②新增
`gain_evidence`：对**同一份已交付产物**跑 full / ablate_no_pairwise / ablate_no_attribution
三遍，逐项对照六项指标（维度覆盖数/一致判定率/冲突发现数/需人工核对条目数/步骤数/追问轮次），
含同输入指纹、机制→指标映射、边界与失效条件，数字全部由脚本机械复算；③新增 `efficiency`：
可自动采集的效率计数落盘并说明复现方式；④新增 `compare_matrix.py` 规则化对照器（带 `--ablate`
退化开关）；⑤**所有校验脚本失败路径恒 exit 0**，判定写入 report 的 ok/verdict/problems，
禁止中断交付；⑥新增 `selftest_r5.py`（38 项正例/反例/退出码契约自测）。

---

## 1. 依赖与版本

| 项 | 版本 / 要求 |
|---|---|
| Python | ≥ 3.8（仅用标准库：json / os / sys / re / hashlib / argparse / itertools / subprocess / tempfile） |
| 第三方依赖 | **零**。无 （评测沙箱无 pip，禁止安装：改用标准库实现）、无 CDN、无网络请求、无外部模型调用 |
| 运行时资源 | 脚本 7 个 + 资源 3 个 + 3 份文档 = 13 个文本文件，共约 200 KB（限额 50 文件 / 2 MB） |
| 平台契约 | Harbor：`/input/case.json`、`/input/comparison-workorder.json`、语料文档；产物 `/app/output/result.json`；Skill 安装到 `/skills/weekly-skill` |
| 平台遥测 | 模型请求数与耗时由平台记录；本包 `efficiency.agent_reported` 是 Skill 自测口径，**不替代**平台遥测 |

## 2. 安装与运行方式

```bash
# 1) 安装：把整个 submission/ 目录放到 /skills/weekly-skill（路径可换，脚本命令按实际路径改）
cp -r submission/ /skills/weekly-skill

# 2) 一键跑完整流程（对照器三遍 → 增益取证 → 效率计数 → 校验）
python3 /skills/weekly-skill/scripts/run_pipeline.py \
  --result /app/output/result.json \
  --workorder /input/comparison-workorder.json \
  --case /input/case.json \
  --work /app/work/r5 --embed

# 3) 或分步跑（Agent 按 SKILL.md 五步流程时用的就是这四条命令）
python3 /skills/weekly-skill/scripts/compare_matrix.py   --result R.json --workorder WO.json --out P.json
python3 /skills/weekly-skill/scripts/gain_probe.py       --result R.json --workorder WO.json --embed
python3 /skills/weekly-skill/scripts/efficiency_probe.py --result R.json --workorder WO.json --embed
python3 /skills/weekly-skill/scripts/check_result.py     --result R.json --workorder WO.json --case C.json --out report.json --embed

# 4) 本地自测（38 项）
python3 /skills/weekly-skill/scripts/selftest_r5.py
```

`--embed` 只写回 `result.json` 的 `result.gain_evidence` / `result.efficiency` / `result.verification`
三个块，不改动其他键。脚本路径全部相对自身目录解析，不硬编码 `/app` 与 `/skills`。

## 3. 输入与输出解释

**输入**
- `/input/case.json`：`case_id` + `output_contract`（声明 result.json 必须有的键）。
- `/input/comparison-workorder.json`：`documents[]`（source_document_id + title）、`fields[]`
  （field_id + definition + unit_expectation）、`comparison_dimensions[]`（默认六维
  task/metric/units/material/pollutant/budget）。
- 语料文档：真实论文（PDF/文本），**不预置任何正式答案或预抽取内容**。

**输出**：`/app/output/result.json`，顶层 8 键 + `result` 内 11 块。

| 块 | 回答题面哪一问 | 说明 |
|---|---|---|
| `field_dictionary` | 对得齐 | 七组统一字段定义 + aliases（各论文叫法归一） |
| `matrix` | 填得准 / 查得回 | 文档×字段全格；每格 value/units/context + 逐字 quote 定位 |
| `pairwise` | 说得清 | 每对文档×每维度一条 verdict，附双方逐字引文 |
| `comparability` | 对得齐 | 六维可比性结论 + comparable_subset；pooled 恒 false（不混池） |
| `synthesis` | 说得清 | consistent / partial / conflicts（含归因维度与双方引文） |
| `coverage` | 结果完整性 | 各产物计数，与实际数组长度机检一致 |
| `verification` | 可核验性 | 逐条 {item, template_value, applied, match} 机检三元组 |
| `gates` | 可核验性 | 闸门四态：enforced / skipped_not_provided / not_found / unreadable |
| `gain_evidence` | 使用增益 | 同输入三遍对照：逐项 delta + 机制→指标映射 + 边界 + 失效条件 |
| `efficiency` | 效率增益 | 可复算计数 + Agent 自报计数（分区存放） |
| `sources` | 证据与边界 | 每篇语料的来源与读取状态 |
| `status` / `status_reason` | 运行状态 | 诚实四级 + 原因说明 |
| `uncertainties` | 证据与边界 | unreported / unverifiable / unbacked / conflicts / human_review / summary |
| `claims` / `changelog` | 可复核 | 每条结论带定位引文；变更记录 |

## 4. 目标用户与场景

- **科研文献综述作者**：5-10 篇同主题论文做统一字段逐格对照，避免"各写各的"。
- **Meta 分析 / 系统综述筛选**：需要可比性判定 + 不可比条件保留，而不是混池数字。
- **评审与尽调**：多篇材料结论冲突时，要能指出差异来自样本、方法、条件还是指标口径。
- **Agent 编排者**：需要一个输出契约稳定、可机检、失败不中断的 Skill。
- **教学/示范**：字段字典 + 冲突归因经验可作为比较方法学的现成模板。

## 5. 验收方式

```bash
# 正例：完整示例应 verdict=pass
python3 scripts/run_pipeline.py --result resources/example-result.json \
  --workorder resources/example-workorder.json --case /nonexistent.json \
  --work /tmp/r5 --embed
# 期望：[check_result] PASS（10 格 = 2 文档 × 5 字段；…；gain_evidence 3 遍
#       （verdict=gain_demonstrated）；efficiency 已落盘），退出码 0

# 反例：注入脏数据后校验器必须抓到，且退出码仍为 0
python3 scripts/selftest_r5.py     # 38 项：正例 + 幂等 + 反例 + 退出码契约
```

验收口径：①`check_report.json` 的 `verdict=pass` 且 `problems=[]`；②`gain_evidence.verdict`
为 `gain_demonstrated`（若指标不可测则如实为 `no_measurable_difference` 并带 problems）；
③`gain_evidence` 与 `efficiency` 的 `followup_rounds` 数值一致（校验器交叉机检）；
④所有脚本退出码恒 0。

## 6. 常见问题（FAQ）

| 症状 | 原因 | 处理 |
|---|---|---|
| `check_report.problems` 里有"缺格" | 工单 fields×documents 未全覆盖 | 补齐 matrix 格；确实没有值则标 `not_reported`（不是删格） |
| "数字回证失败（unbacked）" | value 里的数字没出现在 quote 中 | 回原文核对后修正 value，或把该格降级为 `not_reported` 并记 uncertainties |
| "pairwise evidence 两方来自同一文档" | 引文只挂了一边 | verdict≠not_judged 必须补另一方逐字引文 |
| `gain_evidence.verdict` = `no_measurable_difference` | 三遍指标完全相同（如仅 1 篇文档） | 查 `gain_evidence.problems`；属"对照不可测"，如实保留，不修饰 |
| `gain_evidence.problems` 有"文档数 < 2" | 只有 1 篇文档 | 单文档不构成比较，status=partial 并在 uncertainties 说明 |
| efficiency 的 `agent_reported` 是空的 | Agent 未写运行期计数 | 计数是复算值，不影响交付；平台另有真实遥测 |
| `sources` 里 read_status=partial | 该篇 PDF 部分解析失败 | 相关格标 `not_reported`，记 uncertainties.unverifiable |
| 脚本找不到 | Skill 未装到 `/skills/weekly-skill` | 按第 2 节改路径；脚本之间用相对路径互相 import |

## 7. 已知限制

- 依赖语料段落编号；无编号时按章节标题定位（`paragraph_id` 注 `section:xxx`），溯源粒度下降。
- 指标同名不同义靠字段字典 + 可比性检验拦截，仍存在语义误判风险，冲突格建议人工复核。
- PDF 扫描件需 OCR，识别错误会影响 quote 逐字性。
- **增益对照的性质**：是"同一份已交付产物的机制消融投影"（唯一变量 = 被消融的机制，
  `matrix_sha256` 三遍相同），**不是第二次模型推理**，因此不含推理随机性，也不构成
  平台层面的"不加载 Skill vs 加载 Skill"对照——后者由平台执行，本 Skill 不替代。
- `followup_rounds` 是按缺口结构复算的**投影值**，与 Agent 自报实测值分区存放，不可混用；
  只能作效率趋势说明，不能当实测效率结论。
- `compare_matrix.py` 是规则化对照器（归一化后逐字段比对），不理解语义；它产出的是
  草稿与退化基线，最终判定仍以 Agent 按原文语义给出的 `result.pairwise` 为准
  （两者一致率记录在 `gain_evidence.delivered_vs_rule_crosscheck`）。
- 5-10 篇规模稳定运行（pairwise = 对数×维度数，10 篇×6 维 = 270 条）；>15 篇需按维度分批。

## 8. 失败处理

- **校验未过**：不阻断交付。看 `check_report.json` 的 `problems` 逐条修复后重跑；
  修不了的如实写进 `uncertainties` 并把对应 `verification.match` 置 false、`status` 降级。
- **脚本异常**：所有脚本捕获异常后降级打印并 exit 0，绝不抛栈中断流水线。
- **输入异常**：`status=input_error`，`status_reason` 写明缺什么，`uncertainties.summary` 说明。
- **中断/超时**：仍写 `result.json`（status 如实降级 + 写明中断位置与已完成部分）。
- **闸门未跑**：state ≠ enforced 且 `gate_note` 必须写明"下游不得宣称已核对"。

## 9. 复用建议（给别人的用法）

1. **换主题**：保留 `SKILL.md` 五步流程与 `check_result.py`，只换 `resources/field_dictionary.json`
   的字段体系（七组 → 你的领域组），并在 `compare_matrix.py` 的 `DIM_KEYWORDS` 里登记
   你的比较维度关键词。字段字典是复用的核心资产。
2. **加维度**：工单 `comparison_dimensions` 里加维度即可，`compare_matrix.py` 会自动按
   `fields_for()` 选字段；需语义判定时以 Agent 产出的 `result.pairwise` 为准。
3. **改指标口径**：`gain_probe.py` 的 `compute_metrics()` 是六项指标的唯一定义处，
   `efficiency_probe.py` 复用同一函数，两处数值自动保持一致。
4. **接入 CI**：退出码不再是门禁信号，门禁语义由 `check_report.json` 的 `verdict` 承担；
   CI 直接读 report 的 `ok`/`problems`，不要依赖退出码（本包全部脚本恒 exit 0）。
5. **产出可复用中间物**：`compare_matrix.py --out` 落下的 `pairwise_all` / `conflicts`
   可直接作为新一轮比较的输入草稿，不必重做全表。

## 10. 文件清单与维护

| 文件 | 作用 |
|------|------|
| `SKILL.md` | Skill 本体：8 条强制协议 + 五步流程 + 输出 schema + 校验器抓错清单 + 异常处置（119 行 ≤150） |
| `scripts/check_result.py` | 校验器：14 类机检（题面对齐/覆盖/引文/数字回证/gates/verification/gain_evidence/efficiency/交叉一致性），失败恒 exit 0 |
| `scripts/cli_guard.py` | 本包统一的「退出码恒 0」契约：参数错误 / 异常 / 内容级失败一律 exit 0，门禁语义由 report.verdict 承担 |
| `scripts/compare_matrix.py` | 规则化跨文档对照器，支持 `--ablate no_pairwise` / `--ablate no_attribution` 退化开关 |
| `scripts/gain_probe.py` | 增益取证器：同输入三遍对照 → `result.gain_evidence` |
| `scripts/efficiency_probe.py` | 效率计数器 → `result.efficiency`（与 gain_probe 同公式） |
| `scripts/run_pipeline.py` | 一键跑完五步流水线（对照器三遍 → 增益 → 效率 → 校验） |
| `scripts/selftest_r5.py` | 38 项自测（正例 + 幂等 + 26 类反例 + 退出码契约） |
| `resources/field_dictionary.json` | 七组字段字典模板 + 枚举定义（**复用核心资产**，可换领域） |
| `resources/example-workorder.json` | 合成比较工单示例（2 文档 × 5 字段 × 6 维度，标注"合成示例"） |
| `resources/example-result.json` | 示意输出（**非正式答案**）；`gain_evidence`/`efficiency` 由脚本真实执行生成，数值可复算 |
| `worklog.md` | 逐轮增强记录（五维差距清单 + 补强点 + 双测真实数字） |

**版本**：r5（2026-11）。r4 = 83 公式对齐版；r5 = 题面对齐 + 同输入增益取证 + 效率计数 +
退出码契约。变更记录见 `worklog.md`。

**维护约定**：①`gain_probe.py` 的 `compute_metrics()` 是指标唯一定义处，改指标只改这里；
`efficiency_probe.py` 复用它。②`check_result.py` 加新检查时，必须同时确认该检查的失败
路径仍 exit 0。③字段体系变更时同步更新 `resources/field_dictionary.json` 与
`compare_matrix.py` 的 `DIM_KEYWORDS`。④每次改动后跑 `selftest_r5.py`，38 项全过再提交。

**许可与来源**：全部内容原创，Python 纯标准库，无外部代码引入。
