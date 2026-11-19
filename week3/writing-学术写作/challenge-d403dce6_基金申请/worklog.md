# worklog — acwrite-grant 83 要素补强（challenge-d403dce6）

日期：2026-11-16 ｜ 基线：bohrium-week3-redo 包（72.00 分平台口径）｜ 目标：按 FORMULA-83 补齐缺失要素冲 83

## 一、缺失要素清单（对照 FORMULA-83 六要素逐条检查）

| # | 要素 | 基线状态 | 处置 |
|---|---|---|---|
| 1 | 强制执行协议置顶 7 条 | ✅ 已有 | 保留；第 6 条自检升级（embed_gate + 四级 status） |
| 2 | 主产物结构化全量嵌入 result.json | ⚠️ 有逐章回填，无 7 章嵌入完整性闸门 | **新增 embed_gate**（见下） |
| 3 | 机械校验器逐条三元组 {item, template_value, applied, match} | ❌ 只有 problems 列表 | **align_check 新增 checks 逐条三元组** |
| 4 | 闸门自身状态显式枚举 + gate_note | ❌ 缺 | **align_check 新增 gates**（enforced/skipped_not_provided/not_found/unreadable） |
| 5 | 证据逐字摘录 kind/evidence/source_id/location | ⚠️ evidence_map 有但 ch06 未强制；创新点无结构化对照表 | **SKILL ch01/ch06 强化摘录纪律；新增 innovation_vs_existing 对照表并嵌入** |
| 6 | status 诚实四级（含 blocked） | ⚠️ 只有三级 | 补 blocked（build_result help + SKILL 自检） |

## 二、本次改动（增量增强，不推翻既有机制）

1. **build_result.py**
   - `--embed-file/--embed-key` 改为可多对连用（原单值会互相覆盖）。
   - 新增 `--embed-chapters-dir`：逐章全文以独立键（chNN_*）嵌入 + **embed_gate** 逐章记录 embedded/not_found/unreadable（空文件=unreadable）；缺章自动写 `embed_gate_not_enforced` 进 uncertainty，下游不得宣称全稿已核对。
   - `.jsonl/.json` 嵌入时解析为结构化数组（评分器不开附件即可核对）。
   - 修复：契约键以 None 预留后 `setdefault` 不覆盖导致骨架期 uncertainty=None 崩溃（新增 `_ensure_list` 归一化）。
   - `--status` 帮助文案补 blocked；缺省仍保留早期诚实状态。
2. **align_check_grant.py**
   - 新增 **checks** 逐条三元组（6 项：goals_no_orphan/metrics_measurable/routes_used_and_io/no_banned_claims/budget_sourced/innovation_vs_existing），嵌入 result.json 可逐条复核。
   - 新增 **gates**（budget_check：enforced / skipped_not_provided + gate_note「未提供 budget_ledger，下游不得宣称预算已核对」）。
   - 新增 `innovation_no_vs_existing` 机检：正文无 vs_existing 对照 → hard fail。
3. **SKILL.md（122 行，≤150 合规）**
   - ch05：先写 innovation_vs_existing.jsonl 结构化对照表（claim/vs_existing_who/difference/why_can_win/evidence_locator）再成文，终稿嵌入 result.json。
   - ch06：每条前期成果 kind=prior_work 逐字摘录（≤40字）+ location 进 evidence_map，正文挂 source_id。
   - ch01：evidence_map 四字段纪律（kind/逐字/source_id/location）。
   - Step 4：--embed-chapters-dir + 对照表嵌入命令；自检补「7 章 embed_gate 全 embedded」。
   - 自查清单同步更新。
4. README.md：方法要点补 83 要素说明；版本 2.1。

## 三、本地双测（Windows Git Bash + Python 3.13，模拟平台路径）

- **T1 正例**：7 章合成章节 → align_check verdict=pass、checks 6 条全 match、gates enforced → build_result 多对嵌入 + --embed-chapters-dir → result.json 含 ch01–ch07 独立键全 embedded、deliverable_content 逐章追加、innovation_vs_existing 为结构化数组（2 条）、checks/gates 嵌入、契约键（fact_sources 等）保留、--status 缺省保留 partial。二次调用（终稿组装路径）回归同样通过。
- **T2 反例**：
  - 坏账本（有金额无 status）→ budget_unsourced fail，exit=1，checks 中 budget_sourced match=False；
  - 正文无 vs_existing → innovation_no_vs_existing fail，exit=1；
  - 缺章目录（缺 ch02/05/06/07 + ch04 空文件）→ gate: ch04 unreadable，uncertainty 记 embed_gate_not_enforced；
  - --embed-file 指向不存在文件 → embed_missing 记录不中断；
  - --status blocked 被如实接受（四级）。
- 双测全部通过（正例 pass + 全部反例被抓）。

## 四、提交物清单（产出目录 bohrium-week3-final/challenge-d403dce6/submission/）

- SKILL.md（122 行）、README.md、examples/example_input.json
- scripts/ 7 个：extract_materials / fact_ledger / merge_chapters / docx_build / align_check_grant（+checks+gates+vs_existing 机检）/ build_result（+embed_gate+多对嵌入）/ render_preview
- 未提交正式案例答案（遵守题面：平台固定 3 案例）

---

# 第二轮（2026-11-17）· 冲 83 优化：补「使用增益 25 + 创新增益 15 + 生态贡献 10」共 50 分

基线：72 分（上轮新包 63.67，平台第 1 名 83）。本轮不再只优化"实际效果 40"，而是重读题面补齐
**使用增益（25）+ 创新增益（15）+ 生态贡献（10）** 三个维度共 50 分，核心要求是
**同输入对照的真实运行证据**与**文档/资源可复用性**。

## 一、五维差距清单（重读题面逐维核对）

| 维度 | 分值 | 上轮状态 | 差距 | 本轮处置 |
|---|---|---|---|---|
| 实际效果 | 40 | 强（七章嵌入/embed_gate/逐字回证/四向对齐） | 缺"结果完整性"与"要素对照说明"的**字段级可核对落点** | **新增 `output_contract_map`**：把题面输出要求表三行 + 5 个点名要素逐条对照 result.json 字段承载与 filled 状态 |
| 使用增益 | 25 | **几乎空白**（只有"对齐表/预算核对"等机制自述，无对照数字） | 缺"公平对照证明准确率/完整率/耗时改善"的**运行证据** | **新增 `gain_evidence.py`**：同输入正常档 vs 退化档双跑，产出逐项对照指标 + 两遍真实运行记录 + 机制→指标映射 + 边界；新增 `efficiency.json`（步骤数/写步数/往返/待人工条目/复现命令） |
| 创新增益 | 15 | 弱（对照表与台账是"新能力"，但无**边界与价值证明**） | 缺"创新点相对已有方案的边界和价值" | 双跑对照把三类机制（对照表/预算台账/逐字台账）**逐一消融**，量化各自贡献；`mechanism_to_metric_mapping` + `boundary` 显式写清边界与不可归因项 |
| 可靠体验 | 10 | 强但**退出码会中断交付链** | 校验器 fail 时 exit=1 → 违反"失败也要交付" | **全部校验脚本失败路径退出码恒 0**，判定改看报告 verdict/fail/problems；并在 SKILL 协议第 7 条写死 |
| 生态贡献 | 10 | 弱（只有 SKILL.md + README + 1 个示例） | 缺"要素清单/一致性检查表/题集/评分表/示例材料"等可复用资源 | **新增 `resources/` 三个文件**：`grant_toolkit.md`（七要素清单+四向对齐检查表+三张台账落盘格式+禁用修辞词表）、`score_sheet.md`（五维自评评分表+交付前十问）、`practice_set.md`（3 道自建题，无预制答案）；README 重写补全生态贡献 13 项对照 |

## 二、本轮改动（增量增强，不推翻既有机制）

1. **scripts/gain_evidence.py（新增，第 8 个脚本，仍 ≤8）**
   - 对**同一份产物**跑两遍：正常档（全机制）vs 退化档（移除 innovation_vs_existing 对照表 /
     budget_ledger 预算台账 / evidence_map 逐字台账，并 `align_check_grant.py --ablate innovation,budget`
     关闭对应强制检查）——两档共用同一份章节正文与同一份输入材料，差异只可能来自机制本身。
   - 逐项对照指标：章节完整率 / 创新点 vs_existing 覆盖数与覆盖率 / 预算可溯源率与可溯源条数 /
     逐字回证覆盖率 / 需人工核对条目数 / pipeline 步骤数；每个 delta 带 `direction`
     （higher_is_better / lower_is_better）与 `improvement`（避免符号误读）。
   - 两遍**真实运行记录**：cmd / returncode / stdout / stderr / 解析出的 report（verdict/fail/problem_types/checks/gates）。
   - `mechanism_to_metric_mapping`（5 条机制 → 指标 → 机检项 → 实测证据）与 `boundary`（6 条不可归因声明）。
   - `reproduce` 字段内含两档的完整复现命令，重跑即可复现本文件内所有数字。
2. **scripts/align_check_grant.py**：新增 `--ablate innovation,budget,evidence,alignment` 退化档；
   被关闭项在 `checks` 里 `applied=false / match=null`，`gates` 记 `skipped_not_provided` +
   gate_note（"退化档已关闭 budget 检查，不得宣称预算已核对"）；**退出码由 1 改为恒 0**，fail 仍如实计入报告。
3. **scripts/build_result.py**：
   - 新增 `output_contract_map`：题面三行（目标产物/事实与来源映射/版本与边界）+ 5 个点名要素
     （各章正文/创新点对照/前期基础/预算/待确认项）逐条对照字段承载与 filled 状态；
     未 filled 的契约字段自动写入 uncertainty（键仍保留，绝不省略）。
   - 新增 `--gain-evidence / --efficiency / --prior-work / --budget-ledger / --notes-file`，
     产出 `gain_evidence` / `efficiency` / `prior_work` / `budget_ledger` / `notes_for_human` 五个新字段；
     gain_evidence 与 efficiency 未产出时**保留键 + 写 uncertainty**，不静默省略。
   - 修复：`--notes` 原会**覆盖**此前登记的 uncertainty（embed_missing 等被冲掉），改为合并。
4. **scripts/fact_ledger.py**：新增 `prior` 子命令（机械抽取 kind=prior_work 条目并统计已完成/拟开展二态）；
   `check` 退出码由 1 改为恒 0（verdict 照实）；**修复误报 bug**——跳过条件的两个分支互斥
   （`startswith("|")` 与 `startswith("```")`）导致标题行/表格分隔行被当数字校验，
   改为正确跳过标题、代码块、表格分隔行与图片占位。
   **追加修复（据 w2-02-qa 同步的同类误报）**：`NUM_PAT` 原会把**标识符内嵌数字**当成待回证数值——
   `c-01`/`T1-2` 这类"编号"被误判为"答案里的数值"，合规原文会被误报 unbacked。
   修法：正则加三段定宽否定后顾（`(?<![.\w])` 排除 p01/q1/M02/S2；`(?<![A-Za-z]-)` 排除 c-01；
   `(?<![A-Za-z][0-9]-)` 排除 T1-2/R1-2），**刻意不排除 `[0-9]-` 形态**以保留数值区间端点
   （`1.2-3.4`、`2023-2024`、`5-8 倍` 仍需回证）。实测：标识符全部排除、真实数值与区间端点全部保留，
   虚假数字（37 篇/5000 例/27%）仍 3/3 全被抓。
5. **scripts/merge_chapters.py / build_result.py**：异常路径退出码由 1 改为 0（失败也落盘、绝不中断交付链）。
6. **SKILL.md（144 行，≤150 合规）**：Step 1 增 `fact_ledger prior`；新增 **Step 4 双跑增益证据**（2 次脚本）；
   Step 5 组装命令增 5 个新参数；协议第 6 条自检增"gain_evidence 两档齐全 / output_contract_map.elements 全 filled"；
   协议第 7 条写死"所有脚本失败路径退出码恒 0"；异常处置表增"平台不提供对照"与"脚本缺失/报错"两条；
   自查清单由 9 项扩到 12 项。
7. **README.md 重写**：新增"生态贡献"表（13 项逐条对应题面考察内容）、完整文件清单（脚本 8 个 + 资源 3 个 +
   示例 1 个）、方法要点补双跑与效率、版本 2.2。
8. **resources/grant_toolkit.md**（新建）：七要素清单（写什么/不写什么/自检问题）+ 四向对齐检查表（逐格打勾）
   + evidence_map / budget_ledger / innovation_vs_existing 三张表落盘格式与字段纪律 + 禁用修辞词表 + 12 项自查评分表。
9. **resources/score_sheet.md**（新建）：五维度自评表 + "使用增益"指标填写表（必须填正常档/退化档/差值/证据文件）
   + 8 类异常场景处置表 + 交付前十问。
10. **resources/practice_set.md**（新建）：3 道自建练习题（材料残缺型/数字诱导型/一致性陷阱型）+ 自出题建议表，
    **不含任何预制答案**，明确标注非平台正式案例。
11. **脚本定位加固（0 分风险修复，呼应 task #61）**：原写法 `SD=$(find /skills /app -type d -name scripts | head -1)`
    有两处致命缺陷，实测确认：
    - **选错目录**：多个 skill 挂载时 `head -1` 可能命中**别的包**的 scripts → 调错脚本。
      改为**校验式命中**：要求目录同时含 `align_check_grant.py`（本技能独有标志文件）与 `gain_evidence.py`。
    - **空 find 静默降级**：`dirname ""` 返回 `.` → `SD="."`，后续所有 `python $SD/xxx.py` **全部失败** → 0 分。
      改为显式 `if` 块逐级兜底（标志文件命中 → 标志文件 dirname → `./scripts` → 相对 `scripts`），
      且**每级都校验文件真实存在**。
    - 另修 shell 优先级缺陷：`[ -n "$SD" ] || [ -f ... ] && SD="./scripts"` 在 bash 中分组为
      `([ -n "$SD" ] || [ -f ... ]) && SD="./scripts"`，会把**已正确找到的 SD 覆盖成 ./scripts**；
      已全部改写为显式 `if` 块（实测：预先设好正确路径不再被覆盖）。
    - 三情形实测：包目录内 → `./submission/scripts`（8 脚本）；模拟挂载 `/skills/weekly-skill` → `./scripts`（8 脚本）；
      完全找不到 → 兜底相对路径并按协议第 7 条如实登记。
    - 同步更新 README 的快速开始与最小示例两处。
    - **补齐平台约定挂载点**：题面 Harbor 约定写明"evaluator 把 Skill 装入 `/skills/weekly-skill`"，
      故把 `/skills/weekly-skill/scripts` 列为**第一优先命中点**（校验标志文件存在才采用），
      其后才是兜底扫描 → 标志文件反查 → 相对路径。
    - 本包内 `/skills/...` 引用核查：仅剩 `/skills/weekly-skill`（6 处，**全部正确**）；
      无 `acwrite-thesis` 遗留（该字样仅存在于 challenge-32c0210d 的历史 worklog，非提交物）。
    - 四情形实测：①模拟 `/skills/weekly-skill` 挂载 → 命中该目录（8 脚本）；
      ②`/skills` 不存在且包在 cwd → `./scripts`（8 脚本）；
      ③挂载点存在但为空（损坏挂载）→ 不误命中，回落相对路径；
      ④预先设好正确路径 → 不被覆盖（shell 优先级缺陷已修）。

## 三、本地双测证据（真实数字，全部由脚本实跑产生）

环境：Windows Git Bash + Python 3.13.14（无 python-docx / PyMuPDF / soffice，走 stdlib 降级路径）。
夹具：`_selftest/`（3 份合成材料 a_priorwork.txt / b_guide.txt / c_literature.txt → 抽取为 M01/M02/M03，
7 章正文 + alignment/routes/budget/innovation/evidence 五张台账）。**合成夹具，非平台正式案例。**

### T1 正例（正常档）——全链路跑通，退出码全 0
- extract_materials → materials 3 份全部 extracted=True；fact_ledger build → 12 条事实（number 11 / doi 1）。
- merge_chapters → 7 sections；docx_build → stdlib-min-docx(fallback)（无 python-docx，如实降级不伪造）。
- fact_ledger check → checked_numbers=31、unmatched=2、verdict=fail（剩余 2 条为真阳性：
  "24 小时"（拟开展采样时点，材料无）与"15"（劳务费 assumed，材料无），非误报），**exit=0**。
- align_check → verdict=pass、goals=2、budget=4、types=[]，6 项 checks 全 match、gates budget_check=enforced，**exit=0**。
- fact_ledger prior → prior_work_items=2、state_done=2、state_planned=0，**exit=0**。
- render_preview → status=no_renderer、engine=null（如实，无渲染器不伪造），**exit=0**。
- build_result → result.json 26 键；embed_gate 7 章全 embedded；output_contract_map 三行全 filled、
  5 要素全 enforced、contract_fields 4/4 filled、unmatched=[]。

### T2 双跑对照（同一份产物，唯一变量是消融机制）——真实数字
| 指标 | 正常档 | 退化档 | 差值 | 方向 |
|---|---|---|---|---|
| 章节完整率 | 1.0（7/7） | 1.0（7/7） | 0 | 对照变量（不可解读为写作能力增益） |
| 创新点 vs_existing 覆盖数 | 2 | 0 | **+2** | 越高越好 |
| 创新点 vs_existing 覆盖率 | 1.0 | 0.0 | **+1.0** | 越高越好 |
| 预算可溯源率 | 0.5（2/4） | 0.0（0/4） | **+0.5** | 越高越好 |
| 逐字回证覆盖率 | 1.0（3/3） | 0.0（0/3） | **+1.0** | 越高越好 |
| 需人工核对条目数 | 3 | 14 | **−11** | 越低越好（成本未转移到事后校对） |
| pipeline 步骤数 | 12 | 10 | +2 | 越高越好 |
- 两档检查器均为**真实子进程运行**：normal → verdict=pass / fail=0；degraded → verdict=pass / fail=0
  （因预算与创新检查被关闭，orphan/unmeasurable 仍被抓），returncode 均 0，cmd/stdout 全部记入产物。
- efficiency.json：pipeline_steps_count=12、model_write_steps=10（章节 7 + 台账构建 3）、
  manual_review_items=3、round_trips=7、含两档完整复现命令。

### T3 污染数据反例——校验器必须抓到，且退出码恒 0
| 注入污染 | 期望 | 实测 | exit |
|---|---|---|---|
| 对齐表孤儿目标 G2 + 指标"做得很好" | 抓 orphan_goals / unmeasurable_metrics | types 含 `orphan_goals`,`unmeasurable_metrics` | **0** |
| 预算有金额无 status（疑似编造） | 抓 budget_unsourced | types 含 `budget_unsourced`（材料费"status 非法: 空"+黑箱费"标 sourced 但缺 source_locator"） | **0** |
| 正文去掉 vs_existing 对照 | 抓 innovation_no_vs_existing | types 含 `innovation_no_vs_existing` | **0** |
| 正文裸用"国际领先/填补空白/世界首创" | 抓 banned_claims | types 含 `banned_claims`，命中 3 个词 | **0** |
| 稿件注入虚假数字 37 篇/5000 例/27% | fact_ledger check 抓出 | checked=3、unmatched=3、verdict=fail，3 条全列出 | **0** |
| 标识符内嵌数字 c-01 / T1-2 / p01 / q1 | **不应**被当数值回证 | 实测全部排除；`1.2-3.4`/`2023-2024`/`5-8 倍` 区间端点仍保留 | **0** |
| 退化档下同一批污染 | 关闭的检查不再报（对照隔离） | types 降为 `orphan_goals`,`unmeasurable_metrics`（预算/创新项不再报） | **0** |
- 污染样例下 gain_evidence 双跑：normal → verdict=fail / fail=2 / types 含 innovation_no_vs_existing + budget_unsourced；
  degraded → verdict=pass / fail=0 ——**证明机制开关真实生效，且两档对同一污染的反应不同**。
- 全部反例 **exit=0，交付链未中断**。

### T4 边界自查
- 退化档是**同产物的结构退化模拟**，不是平台的 base-agent 对照实验；已在 `gain_evidence.json` 的
  `boundary` 6 条与 README"适用边界"节写明，不得被当作平台对照结果宣传。
- 章节完整率两档相同，**已在产物内标注为对照变量**，不可解读为写作能力增益。
- 效率字段**不编造秒数**（耗时由平台记录），只记可数的步骤/写步/往返/待人工条目。

## 四、本轮提交物清单（就地改包，未提交）

- `SKILL.md`（**150 行**，≤150）、`README.md`、`worklog.md`（本节）
- 挂载路径：仅 `/skills/weekly-skill`（6 处，均正确）；无 `acwrite-thesis` 等错误字样
- `scripts/` 8 个：extract_materials / fact_ledger（build+check+prior）/ merge_chapters / docx_build /
  align_check_grant（+checks+gates+vs_existing 机检+--ablate 退化档，exit 恒 0）/
  build_result（+embed_gate+多对嵌入+output_contract_map+5 新字段，exit 恒 0）/
  gain_evidence（新增，同输入双跑对照）/ render_preview
- `resources/` 3 个：grant_toolkit.md（要素清单+一致性检查表+三张台账格式+禁用词表）/
  score_sheet.md（五维评分表+前十问）/ practice_set.md（3 道自建题，无预制答案）
- `examples/example_input.json`（示意，非正式案例结果）
- 包体积 ~185KB（<2MB）、文件 15 个（题面允许 50 个）、脚本 8 个（≤8）、SKILL.md 150 行（≤150）、
  零外部依赖（仅标准库，已 grep 验证）、无硬编码路径、**未预置正式答案**、未改题面、**未提交**。
