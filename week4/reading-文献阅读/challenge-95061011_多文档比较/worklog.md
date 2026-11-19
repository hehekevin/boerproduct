# worklog — doc-compare-r4 增量增强记录（83 公式对齐）

## 输入研读
- 读 FORMULA-83.md 全文：83 分公式六要素 + 工作流程 + 硬约束（SKILL.md ≤150 行）。
- 读 task.md（challenge-95061011）全文：评分维度、Harbor 契约、organizer revision v2。
- 读 r3 包（bohrium-week3-redo/challenge-95061011/submission，68.00）全部文件 + worklog 差距分析。

## 83 公式逐要素对照（r3 缺失清单）
1. 强制执行协议置顶 —— r3 有 6 条，缺「每步一个写盘动作」与「分批写（每段 ≤1500 字）
   防 16384 token 截断」→ **补强为 7 条**。
2. 主产物结构化全量嵌入 result.json —— r3 已达标（matrix/pairwise/comparability/
   synthesis/coverage/claims/uncertainties）→ 保留。
3. 机械校验器逐条结果嵌入 result.json —— r3 校验结果只写 check_report.json，未嵌入
   result.json，且无 `{item, template_value, applied, match}` 三元组 → **补 verification 块**。
4. 闸门状态显式枚举 —— r3 无 gates 块 → **补 gates 块（enforced/skipped_not_provided/
   not_found/unreadable；非 enforced 必须 gate_note 写明「下游不得宣称已核对」）**。
5. 数字逐字回证 —— r3 无 unbacked 检测 → **补：reported 数字格 value 必须出现在
   quote（空白归一化子串匹配），失败逐条列 uncertainties.unbacked 并计入 FAIL**。
6. status 诚实四级 —— r3 已达标 → 保留。

其他硬约束差距：r3 SKILL.md 175 行 > FORMULA 上限 150 行 → 压缩重写至 150 行。

## r4 设计动作（增量，不推翻 r3）
- SKILL.md：协议扩 7 条（第 2 条并入"每步一个写盘动作"+分批写）；第 1 步骨架预留
  verification/gates；第 5 步新增 verification 三元组嵌入、gates 嵌入、数字回证回填
  三个动作；校验器抓错清单补 3 类；全文件压缩到 150 行（frontmatter 仍合法）。
- check_result.py：新增 ①norm()/num_str() 辅助；②reported 数字格逐字回证（unbacked
  列表同时进 problems 与 report.unbacked_numbers）；③gates 机检（缺失/state 非法/
  非 enforced 缺 note 均 FAIL）；④verification 机检（缺失/缺键/applied=false/
  match=false 均 FAIL）；保留 r3 全部 8 类检查与三级容错（load_json 捕获、逐条 try、
  顶层 except 降级）；PASS 输出新增数字回证与 gates/verification 通过信息。
- example-result.json：新增 verification（7 条三元组）+ gates（4 闸门）+
  uncertainties.unbacked 键 + changelog。
- README.md：更新为 r4 说明，正例自测命令 + 反例验证结论。
- 资源仍 6 个文件（≤8）、流程线性 5 步、Python 3 纯标准库、无外部 CDN、
  不硬编码平台路径（/skills/weekly-skill、/input、/app 运行时约定）。

## 双测证据
- 正例：`python3 scripts/check_result.py --result resources/example-result.json
  --workorder resources/example-workorder.json --out …` →
  `PASS（10 格 = 2 文档 × 5 字段；reported 10 / not_reported 0 / not_comparable 0；
  pairwise 6 条（双引文 5）；冲突 1；claims 2；数字回证 2 处全通过；
  gates/verification 机检通过）`，退出码 0。
- 反例（注入 6 类脏数据）：删 1 格 / value 改 999.9 与 quote 不符 / 删 pairwise[3]
  evidence / 删 gates / verification[0].match=false / coverage.cells=99 →
  FAIL（7 处，其中数字回证失败 1 处），逐条命中全部注入项，退出码 1。全过。

## 自检
- SKILL.md 150 行 ✓（≤150）；frontmatter name/description 合法 ✓；协议 7 条置顶 ✓；
  流程线性 5 步 ✓；资源文件 6 个 ≤8 ✓；纯标准库 ✓。
- example-result.json 通过正例校验 ✓；示例标注"非正式答案" ✓；无预制正式答案 ✓；
  不硬编码平台路径 ✓。

---

# worklog — doc-compare-r5（第 2 轮：题面对齐 + 同输入增益取证 + 生态贡献）

## 0. 本轮背景与输入研读
- 团队派单：本轮不只补「实际效果 40 分」，必须重读题面，补齐 **使用增益 25 + 创新增益 15 +
  生态贡献 10** 共 50 分，核心要求是**同输入对照的真实运行证据**与**文档/资源可复用性**。
- 读 task.md（challenge-95061011）全文，重点重读第 2 节评分维度表与第 3 节
  「Skill 运行后的输出要求」表（这是本轮题面对齐的唯一权威依据）。
- 读 FORMULA-83.md：83 公式六要素 + 硬约束（SKILL.md ≤150 行、资源 ≤8 文件、线性 ≤5 步、
  纯标准库、不预置正式答案）。
- 读 r4 包全部文件 + 上一轮 worklog 差距分析（当前 68 分，平台第 1 名 83 分）。

## 1. 五维差距清单（r4 逐维自评 + 缺口）

| 评分维度 | 分值 | r4 现状 | 缺口判定 | 本轮补强点 |
|---|---|---|---|---|
| 实际效果 | 40 | 已较强（逐格双文档溯源、数字回证、冲突归因） | 小缺：**result.json 未逐项对齐题面「输出要求」表**（缺 status_reason / sources，uncertainties 分区未机检） | 新增顶层契约键 `status_reason`、`sources`；uncertainties 六分区机检；status 四级枚举机检 |
| 使用增益 | 25 | **最大缺口**：只有文字自述「比基础 Agent 更可信」，**无任何同输入对照证据**；效率无计数 | 需可运行退化模式 + 同输入两遍真实数字 | 新增 `compare_matrix.py`（带 `--ablate` 退化开关）+ `gain_probe.py`（同输入三遍对照）+ `efficiency_probe.py`（效率计数落盘） |
| 创新增益 | 15 | 字段字典/两级对齐/冲突归因有，但**未证明相对基础 Agent 与已有工具的边界** | 需机制→指标的因果映射与边界声明 | `mechanism_map`（机制→指标→映射规则→方向）+ `boundary` + `failure_conditions` + `delivered_vs_rule_crosscheck`（与已有工具边界） |
| 可靠体验 | 10 | 已较强（闸门四态 / 异常表 / 逐字回证） | 小缺：**校验脚本失败会 exit 1**，可能中断交付链路 | 全部脚本失败路径改 exit 0，verdict 照实写 report；新增 `run_pipeline.py` 一键入口 |
| 生态贡献 | 10 | README 只有文件清单 + 快速使用 | 大缺：缺依赖/版本、安装运行、输入输出解释、目标用户场景、验收方式、FAQ、已知限制、失败处理、复用建议、版本维护 | README 重写为 10 节完整生态贡献文档 + 文件清单与维护约定 |

## 2. 本轮设计动作（增量，保留 r4 全部 83 要素）

### 2.1 题面对齐（实际效果 + 可靠体验）
- 顶层契约键由 6 个扩到 **8 个**：新增 `status_reason`（运行状态须附原因，对应题面
  「运行状态：成功、部分完成、无法判断或拒答及原因」）与 `sources`（对应 Harbor 契约
  "Include honest status, sources, uncertainty and change records" 的 sources）。
- `uncertainties` 强制六分区机检（unreported/unverifiable/unbacked/conflicts/human_review/summary）
  —— 对应题面「证据与边界：未报告和不确定项」。
- `status` 合法值机检：answered / partial / insufficient_evidence / input_error（诚实四级）。
- 不删任何既有契约键；既有 83 要素（嵌入完整性 / 闸门四态 / status 四级 / 逐字回证 /
  冲突归因 / verification 三元组）全部保留。

### 2.2 gain_evidence（使用增益 + 创新增益 —— 本轮核心）
- **可运行的退化/基线模式**：`compare_matrix.py --ablate no_pairwise`（关闭两两跨文档比对）
  与 `--ablate no_attribution`（关闭冲突归因），另有正常模式（缺省 `--ablate`）。
- **同输入对照**：三遍共用**同一份已交付产物**（`result.matrix` / `result.pairwise` /
  `result.synthesis.conflicts`）与同一份工单；唯一变量 = 被消融的机制。
  `input_fingerprint.matrix_sha256` 三遍相同 → 同输入凭据机检。
- **逐项对照六指标**（题面「使用增益」点名维度）：维度覆盖数 / 一致判定率 / 冲突发现数 /
  需人工核对条目数 / 步骤数 / 追问轮次；每遍 `metrics` + 逐项 `deltas`。
- **机制→指标映射**：`mechanism_map` 每行 {mechanism, metric, mapping_rule, full_value,
  ablate_value, delta, metric_polarity, direction}；效益型指标越大越好、成本型越小越好，
  方向由脚本判定，方向不符则 verdict 自动降级为 `gain_demonstrated_with_caveat`。
- **边界与失效条件**：`boundary`（5 条）+ `failure_conditions`（5 条）明确写出对照成立的前提
  与指标不可用的情形。
- **与已有工具的边界**：`delivered_vs_rule_crosscheck` 记录 Agent 交付 pairwise 与规则
  对照器的一致率，并说明「一致率低不必然是错误」的成因。
- **不冒充平台对照**：boundary 明写「平台层面的『不加载 Skill vs 加载 Skill』对照由平台执行，
  本包不冒充该对照」。

### 2.3 efficiency（效率增益）
- `efficiency_probe.py` 落盘 `result.efficiency`：`counts`（19 项复算计数：matrix_cells /
  pairwise_judged / comparison_rounds / conflict_records / manual_review_items /
  human_review_items / pipeline_steps / manual_completion_steps / steps / followup_rounds …）
  + `agent_reported`（model_requests / tool_calls / rework_rounds 等自报值，**分区存放不混用**）。
- `collection_method` 写明采集口径，`reproduce` 写明复现命令。
- `followup_rounds` 与 `gain_probe` **同公式**（`efficiency_probe` 直接 import
  `gain_probe.compute_metrics`），校验器交叉机检两处数值一致（不一致 = FAIL）。

### 2.4 退出码契约（可靠体验）
- `check_result.py`：**所有失败路径恒 exit 0**（含文件缺失/非法 JSON/空文件/路径是目录/
  顶层异常），判定写入 `check_report.json` 的 `ok`/`verdict`/`problems`。
  另加 `--strict` 供 CI 需要非 0 时使用（默认仍恒 0）。
  → **后续并发改动已移除 `--strict`**：本包统一由 `scripts/cli_guard.py` 提供「退出码恒 0」
  契约（参数错误/异常/内容级失败一律 exit 0），门禁语义统一由 report.verdict 承担。
  本条为历史设计记录，**当前实现无 `--strict` 参数**（传入会被当作未知参数按失败处理并 exit 0）。
- `gain_probe.py` / `efficiency_probe.py` / `compare_matrix.py` / `run_pipeline.py` 同样恒 exit 0。
- SKILL.md 协议第 8 条显式写明「校验失败不中断」。
- **修掉一个自指循环**：原先 `--embed` 会读到上一轮遗留的 `match=false` → 误判 FAIL；
  改为「先用结构性结论重算并回填三元组，再校验 verification」，且回填只用结构性
  problems（不含 verification 自身失败），避免污染。

### 2.5 生态贡献（README 重写为 10 节）
依赖与版本 / 安装运行 / 输入输出解释（逐块对应题面哪一问）/ 目标用户与场景 /
验收方式 / 常见问题 FAQ / 已知限制 / 失败处理 / 复用建议 / 文件清单与维护约定。

## 3. 双测证据（真实数字，全部由脚本实际执行产生）

### 3.1 正例：同输入三遍对照（`resources/example-result.json`，2 文档 × 5 字段 × 6 维）

`python3 scripts/gain_probe.py --result resources/example-result.json --workorder resources/example-workorder.json --embed`
→ `[gain_probe] verdict=gain_demonstrated matrix=09aa1694972447ee slots=6`

| 模式 | 维度覆盖数 | 一致判定率 | 冲突发现数 | 需人工核对条目 | 步骤数 | 追问轮次 |
|---|---|---|---|---|---|---|
| **full**（正常模式） | **5**/6 | **0.8** | **1** | **1** | **6** | **3** |
| ablate_no_pairwise（关闭两两比对） | 0/6 | 0.0 | 0 | 6 | 9 | 8 |
| ablate_no_attribution（关闭冲突归因） | 5/6 | 0.8 | 1 | 2 | 6 | 4 |

逐项 delta（full − ablate）：
- `ablate_no_pairwise`：dimension_coverage **+5**、agreement_rate **+0.8**、conflicts_found **+1**、
  manual_review_items **−5**（成本型，越小越好）、steps **−3**、followup_rounds **−5** → 6 项方向全部一致。
- `ablate_no_attribution`：dimension_coverage 0、agreement_rate 0、conflicts_found 0、
  manual_review_items **−1**、steps 0、followup_rounds **−1** → 归因关闭只影响归因与人工量，
  不影响发现数（与机制预期一致）。

`verdict_note`：所有被消融机制的效益型指标下降、成本型指标上升，方向一致，增益成立。
`delivered_vs_rule_crosscheck`：delivered 6 条 / 与规则对照器一致 3 条 / 分歧 3 条 / 一致率 0.5
（已注明「一致率低不必然是错误：Agent 判定含语义推理」）。

### 3.2 效率计数（同一次运行落盘）

`python3 scripts/efficiency_probe.py --result … --embed`
→ `[efficiency_probe] ok=True cells=10 pairwise=6(judged=5) rounds=6 conflicts=1 manual=1 steps=6(5 auto+1 manual) followup=3`

counts 实测：`matrix_cells=10, pairwise_records=6, pairwise_judged=5, pairwise_not_judged=1,
document_count=2, dimension_count=6, document_pairs=1, comparison_rounds=6,
conflict_records=1, attributable_conflicts=1, manual_review_items=1, human_review_items=0,
pipeline_steps=5, manual_completion_steps=1, steps=6, followup_rounds=3,
verification_items=8, gates_total=4, fields_in_dictionary=5`。
`gain_evidence(full).followup_rounds=3` 与 `efficiency.counts.followup_rounds=3` 一致（校验器机检）。

### 3.3 全链路正例

`python3 scripts/run_pipeline.py --result resources/example-result.json --workorder resources/example-workorder.json --embed`
→ `[check_result] PASS（10 格 = 2 文档 × 5 字段；reported 10 / not_reported 0 / not_comparable 0；
pairwise 6 条（双引文 5）；冲突 1；claims 2；数字回证 2 处全通过；gates/verification 机检通过；
gain_evidence 3 遍（verdict=gain_demonstrated）；efficiency 已落盘）`，退出码 0。

### 3.4 反例（污染数据确认校验器抓到且退出码恒 0）

`python3 scripts/selftest_r5.py` → **共 38 项，失败 0 项**。逐项实测：

| 类别 | 用例 | 实测结果 |
|---|---|---|
| 正例 | 完整流水线 | exit=0 verdict=pass problems=0 |
| 正例 | 幂等：同输入连跑两遍 | fingerprint_equal=True metrics_equal=True runs=3 |
| 反例 | 删一格 | exit=0 verdict=**fail** problems=6 |
| 反例 | 数字与引文不符 | exit=0 verdict=**fail** problems=2 |
| 反例 | 删 pairwise 双引文 | exit=0 verdict=**fail** problems=2 |
| 反例 | 删 gates | exit=0 verdict=**fail** problems=1 |
| 反例 | coverage 数字改错 | exit=0 verdict=**fail** problems=4 |
| 反例 | 删 status_reason | exit=0 verdict=**fail** problems=1 |
| 反例 | 删 sources | exit=0 verdict=**fail** problems=1 |
| 反例 | 删 uncertainties 分区 | exit=0 verdict=**fail** problems=1 |
| 反例 | 冲突缺归因 | exit=0 verdict=**fail** problems=1 |
| 反例 | 删顶层 changelog | exit=0 verdict=**fail** problems=2 |
| 反例 | 逐字回证失败（数字造假） | exit=0 verdict=**fail** problems=2 |
| 反例(校验器单独) | 删 gain_evidence / 删 efficiency | exit=0 verdict=**fail** problems=1 |
| 反例(校验器单独) | verification match=false / 缺 template_value | exit=0 verdict=**fail** problems=1 |
| 反例(校验器单独) | gates 状态非法 / 非 enforced 缺 note | exit=0 verdict=**fail** problems=1 |
| 反例(校验器单独) | gain_evidence 只剩 1 遍 / 缺 full 遍 / 缺 deltas / 缺 mechanism_map / 缺 verdict | exit=0 verdict=**fail** problems=1~3 |
| 反例(校验器单独) | gain_evidence 指纹非同输入 / 缺边界 / 缺失效条件 | exit=0 verdict=**fail** problems=1 |
| 反例(校验器单独) | efficiency 缺复现方式 / 缺采集口径 | exit=0 verdict=**fail** problems=1 |
| 契约 | 文件缺失 / 非法 JSON / 空文件 / 路径是目录 | **exit=0** |
| 契约 | gain_probe / efficiency_probe / compare_matrix / run_pipeline 失败路径 | **exit=0** |
| 反例 | 污染输入后指纹必须变化 | fp=d880bace1f92（≠ 09aa1694972447ee） |

注：删 gain_evidence / 删 efficiency / verification match=false 三类若走完整流水线会被
流水线按设计重建（gain_evidence 与 efficiency 本就是流水线产物），因此**另设「校验器单独」
取证组**对校验器自身的抓错能力取证，确保不靠流水线掩盖。

### 3.5 与已有工具的边界（创新增益）
`compare_matrix.py` 是规则化对照器（归一化后逐字段比对，不理解语义）：它产出草稿与退化基线，
最终判定仍以 Agent 按原文语义给出的 `result.pairwise` 为准，两者一致率记录在
`delivered_vs_rule_crosscheck`（本例 0.5），并注明成因。这一条同时写进 README「已知限制」
与 SKILL.md「已知限制」，避免把规则基线包装成语义能力。

## 4. 硬约束自检
- SKILL.md **119 行**（≤150）✓；frontmatter name/description 合法 ✓；协议 8 条置顶 ✓
- 流程线性 5 步 ✓（增益取证与效率计数并入第 5 步，不新增步骤）
- 脚本 **6 个**（≤8）✓；资源 3 个 + 文档 3 个 = 12 个文本文件（≤50）✓；包 **约 200 KB**（<2MB）✓
- 零外部依赖（Python 3 纯标准库）✓；无 CDN / 网络 / 外部模型 ✓
- 不预置正式答案 ✓（示例全部标注「合成示例 / 非正式答案」，且 gain_evidence 与 efficiency
  由脚本真实执行生成、数值可复算）
- 不改题面 ✓；未提交 ✓（就地改包，未 git commit）
- 所有校验脚本失败路径 exit 0 ✓（38 项自测逐项实测）

## 5. 遗留与下一步
- `followup_rounds` 目前是按缺口结构复算的投影值（与 Agent 自报实测值分区存放）。
  平台运行时的真实模型请求数由平台遥测记录，Skill 侧不再重复计数以免与平台口径冲突。
- `compare_matrix.py` 的 `DIM_KEYWORDS` 目前覆盖水处理/吸附场景常用词；换领域时需按
  README 第 9 节登记新维度关键词（已在维护约定中写明）。
- 增益对照是机制消融投影，不是独立第二次推理；若后续要证明「相对基础 Agent」的增益，
  需平台在固定案例上做双跑对照，本包只提供 Skill 内的机制级证据。
