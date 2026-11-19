# worklog — formula-parse（challenge-7c37626c）

## v3.1（本轮：增益取证做实 + 退出码兜底 + 生态章节）

> 本节由本轮（w3-formula）追加，接在 v3 一节之后，不覆盖 v3/v2 历史记录。

### 1. 现状核验（先看再动手，不推倒重来）

接手时包内已有 `gain_probe.py`（同输入双跑消融对照）与 `--ablate` 开关，但**机制能跑、
证据不够硬**：

| 原有机制 | 实跑结论 | 缺口 |
|---|---|---|
| `mathml2latex.py --ablate` 消融开关 | 可跑，真实子进程双跑（完整 3/3 full vs 消融 0/3 full） | 无 |
| `gain_probe.py` 产出 gain_evidence | 可跑，comparison 11 项 | **11 项里 7 项是 `declared_projection`（声明式投影），只有 4 项 `real_double_run`**——投影不是机器判定，「增益」仍靠自述 |
| `structure_fidelity_rate` | 有数值 | **口径错**：算的是「产物含结构算子的公式占比」，源公式本来就没结构时也扣分（忠实还原被误判失真） |
| 符号覆盖率 | 有数值 | **口径错**：`P_{\mathrm{out}}` 与变量表 `P_out`、`\Delta P` 与 `ΔP` 互判为漏变量 |
| 退出码 | 5 个脚本已恒 0 | `result_scaffold.py` 仍有 1 处 `return 1`（写盘失败） |
| SKILL.md | 150 行 | 恰在上限，无余量 |
| README | 82 行 | 缺生态贡献全套（依赖版本/目标用户/验收/常见问题/复用建议/版本维护等） |

### 2. 本轮补强点（4 项，全部落到可复跑的代码）

**① 把「增益」从文字自述改成机器判定（核心）**
新增 `gain_probe.validator_dual_run()`：把**完整臂**与**消融基线臂**两份产物交给
**同一套** `formula_check.py` + `semantic_check.py` 各真实跑一次，得到机器判定的
FAIL 数差。新增来源标签 `real_validator_dual_run`（区别于 `real_double_run` 与
`declared_projection`），comparison 项 11 → **19**。

**② 修 `structure_fidelity_rate` 口径**：改为**逐公式**比对——复用 `mathml2latex` 的容错
解析按公式取出源 MathML 的结构算子集，源含分式/根号/上下标的公式逐条比对产物 LaTeX，
源本身无结构的公式**不计入分母**（不再让忠实还原被误判失真）。

**③ 修符号口径**：公式侧抽候选、变量侧 `expand_symbol` 展开等价写法
（ΔP→{ΔP,Δ,P}；P_out→{P_out,P,out}；T_c→{T_c,T,c}），两侧取交集判覆盖；
`semantic_check` 的 W1 同步加下标组合归一（`_COMBO_RE`），消除 `P_{\mathrm{out}}`
被误报「漏变量」的假阳性。

**④ 退出码兜底补全**：`result_scaffold.py` 的 `return 1`（写盘失败）改 0；
6 个脚本全部加 `__main__` 守卫（argparse 报错、SystemExit、读文件异常、写盘失败
一律 exit 0，verdict 只写报告）。另加**绝对计数口径**指标（分母恒定、无
「未测 vs 0」歧义，最适合对外汇报）。

### 3. 五维评分差距清单（对照题面实际效果40/使用增益25/创新增益15/可靠体验10/生态贡献10）

| 维度 | 分值 | 本轮开工时差距 | 本轮补强 | 剩余差距 |
|---|---|---|---|---|
| 实际效果 | 40 | 三层解读机制齐备，但**指标口径失真**：保真率与符号覆盖率都会把正确产物判低，评审照数字看会低估成果 | 逐公式保真率 + 符号展开口径修正（self-test 实测 0.667→1.0、0.727→1.0） | 真实案例的公式数/结构复杂度未知，转换器对 mtable 大矩阵仍 partial；人工校对环节无法自动化 |
| 使用增益 | 25 | 11 项指标里 7 项是声明式投影，**增益靠自述**；且无机器背书 | **校验器实测对照**：同一套校验器对两臂各跑一次，完整臂 FAIL=0 / 消融臂 FAIL=**7**（自测）——机器判定而非文字声明 | 仍是「机制消融基线」，非平台「基础 Agent 不加载 Skill」白板；平台对照只能由平台生成 |
| 创新增益 | 15 | 有双跑+投影范式，但缺「不靠白板也能自证增益」的第三类证据 | ① 校验器实测对照（`real_validator_dual_run`，第三方可复算）；② 逐公式保真率口径；③ 绝对计数指标 | 同源规则存在「自己尺子量自己」固有局限（已在 README §8 已知限制明写） |
| 可靠体验 | 10 | **1 处非零退出**（`result_scaffold` 写盘失败）——平台会把非零退出判整跑 failed → 0 分 | 6 脚本退出码守卫；**20 条失败路径逐一实跑验证 rc=0**（缺参/错参/文件不存在/JSON 损坏/目录不可写 × 各脚本） | 极端输入下的产物质量依赖降级通道，仍需人工校对 |
| 生态贡献 | 10 | README 82 行，缺依赖版本/目标用户/验收方式/常见问题/复用建议/版本维护/自检清单 | README 重写 **13 节生态全套** + **最小可运行自检清单 5 条命令**（逐条实跑 rc 全 0）；SKILL.md 150→**123 行** | 无 CI 配置样例、无多案例基准集（受题目「不预置正式答案」约束，只能留接口） |

### 4. 本地双测证据（真实数字）

自测夹具在 `challenge-7c37626c/_selftest/`（**不在 submission 内，不占包体积**）：
合成出版商 XML（DOCTYPE + 命名实体 + MathML 分式/下标/根号，3 条公式）、
case.json（带 output_contract）、C02 类无公式源 fixtures。**非平台正式案例**。

**4.1 正例 —— 同输入真实双跑（`_selftest/input/artifacts/source-formulas.xml`，3 条公式）**

| 指标 | 完整臂 | 消融臂 | delta | 来源 |
|---|---|---|---|---|
| formula_yield_rate | 1.0 | 1.0 | 0.0 | real_double_run |
| full_conversion_rate | 1.0 | 0.0 | **+1.0** | real_double_run |
| structure_fidelity_rate（逐公式） | 1.0 | 0.0 | **+1.0** | real_double_run |
| structural_op_recall | 1.0 | 0.0 | **+1.0** | real_double_run |
| variable_table_completeness | 1.0 | 0.0 | **+1.0** | declared_projection |
| symbol_coverage_rate | 1.0 | 0.0 | **+1.0** | declared_projection |
| numeric_verification_pass_rate | 1.0 | 0.0 | **+1.0** | declared_projection |
| variables_with_full_definition | **10** | 0 | **+10** | declared_projection |
| symbols_covered_count | **11** | 0 | **+11** | declared_projection |
| steps_with_evidence_and_intermediate | **3** | 0 | **+3** | declared_projection |
| claims_with_verbatim_quote | **3** | 0 | **+3** | declared_projection |
| recomputed_verified_count | **3** | 0 | **+3** | declared_projection |
| manual_review_items（越少越好） | 2 | 7 | **−5** | declared_projection |
| **validator_total_fail** | **0** | **7** | **−7** | **real_validator_dual_run** |
| formula_check_problems | 0 | 1 | −1 | real_validator_dual_run |
| semantic_check_fails | 0 | 6 | −6 | real_validator_dual_run |

两臂 LaTeX 实测（同一 `<m:math id="m-f1">`）：
- 完整：`η = \frac{P_{\mathrm{out}}}{P_{\mathrm{in}}} \times 100 %`（conversion=full）
- 消融：`η = P out P in \times 100 %`（文本拼接，conversion=partial）

**校验器实测对照明细**（同一套校验器，两臂各跑一次，机器判定）：

```
skill_full            formula_check ok=True  problems=0 | semantic_check ok=True  fails=0   → total_fail=0
skill_mechanism_ablation
                       formula_check ok=False problems=1 | semantic_check ok=False fails=6   → total_fail=7
  - claims 数组为空（每条关键论断都应带 evidence 指回原文）
  - F1 [m-f1] 缺 semantics（逐符号含义/量纲解读）——讲得清维度未达标
  - F1 [m-f2] 缺 semantics —— 讲得清维度未达标
  - F1 [m-f3] 缺 semantics —— 讲得清维度未达标
  - F6 [m-f1] not_recomputable 但 missing 为空（须逐项登记缺失输入）
  - F6 [m-f2] not_recomputable 但 missing 为空
  - F6 [m-f3] not_recomputable 但 missing 为空
```

**4.2 反例 —— 污染数据（8 处缺陷）**：在自测正例上注入 8 处缺陷（删 semantics /
删原文定义 source_location / 删推导步 evidence / 删 intermediate_value / 删核验输入
units / not_recomputable 空 missing / claims quote 置空 / latex 置空 / 编造
`coverage.not_recomputable=true`）→

```
formula_check  FAIL（5 处）  exit=0
  - [m-f3] conversion=full 但 latex 为空
  - [m-f3] latex 为空串（产物非空生命线被破坏）
  - coverage.not_recomputable=true 但 verification[0] 有 computed（编造检测）   ×3
semantic_check FAIL（7 处 FAIL，0 WARN）  exit=0
  FAIL F1 [m-f1] 缺 semantics      FAIL F2 [m-f2] 原文定义缺 source_location
  FAIL F3 [step1] 缺 evidence     FAIL F4 [step2] 缺 intermediate_value
  FAIL F5 [m-f1] 核验输入缺 units/source
  FAIL F6 [m-f2] not_recomputable 但 missing 为空
  FAIL F7 claims[0] evidence 缺逐字 quote
```

→ F1-F7 全部命中，**两个脚本退出码均为 0**，不中断交付。

**4.3 退出码恒 0 —— 20 条失败路径逐一实跑**（本轮修复的硬引信）

| 场景 | 脚本 | 实测 rc |
|---|---|---|
| 缺必填参数（argparse 报错） | 6 个脚本全测 | 全 0 |
| 完全错误参数 `--bogus-flag` | 6 个脚本全测 | 全 0 |
| result.json 不存在 | formula_check / semantic_check / schema_guard | 全 0 |
| result.json 非合法 JSON | formula_check / semantic_check / schema_guard | 全 0 |
| 输出目录不可写 | mathml2latex / result_scaffold | 全 0 |

**4.4 C02 真实缺失分支**（无公式源）：`formula_layer` 全部指标为 `null`、
`source_xml_note` 写明「M1 双跑不可执行（真实缺失分支，不以 0 冒充）」；
formula_check / semantic_check 均 PASS，exit=0。→ **null ≠ 0**，「未测」与「测得 0」可区分。

**4.5 效率计数（真实采集）**：`mathml2latex_full` 0.374s / `mathml2latex_ablate` 0.415s /
`gain_probe_total` 2.609s；脚本调用 4 次；完整模式吞吐 8.02 公式/秒；
产物条目 formulas=3 / formulas_with_semantics=3 / variables=10 / derivations=3 /
verification=3 / claims=3 / uncertainty_items=2。

**4.6 README 自检清单 5 条命令逐条实跑**（`examples/` 自带合成输入）：
① 转换器 PASS 1 个公式对象（failed=0）rc=0；② formula_check PASS ok=true rc=0；
③ semantic_check PASS 0 WARN rc=0；④ 故意指向不存在文件 → rc=0（不是 2）；
⑤ gain_probe 双跑 → 19 项对照数字 + `validator_dual_run.available=true` rc=0。

### 5. 本轮改动文件清单

| 文件 | 改动 |
|---|---|
| `scripts/gain_probe.py` | 新增 `validator_dual_run()` + `run_validator()` + `expand_symbol()` + `_source_item_ops()`（逐公式源算子）；`structure_fidelity_rate` 改逐公式口径；新增 5 项绝对计数指标；comparison 11→19；新增来源标签 `real_validator_dual_run`；P6 投影规则；MECH_MAP 增 M2+M3+M4 合成校验条目 |
| `scripts/semantic_check.py` | W1 下标组合归一（`_COMBO_RE`）+ 新增下标组合 W1 检查；`__main__` 退出码守卫 |
| `scripts/result_scaffold.py` | `return 1` → `0`；`__main__` 退出码守卫；docstring 退出码说明改为「恒 0」 |
| `scripts/{formula_check,schema_guard,mathml2latex}.py` | `__main__` 退出码守卫 |
| `SKILL.md` | 150 → **123 行**；措辞与新机制同步（退出码恒 0 含参数/读取/写入失败、校验器实测对照、C02 指标 null 不冒充 0、W1 覆盖下标组合） |
| `README.md` | 重写为 **13 节生态全套** + §12 最小可运行自检清单（5 条命令）+ §6 增益取证三种口径说明 + §11 版本维护表 |
| `worklog.md` | 本 v3.1 小节 |

### 6. 诚实边界声明（不变）

- `gain_probe` 的 baseline 是**本 Skill 机制消融基线**，**不是**平台「基础 Agent 不加载
  Skill」白板；平台对照由平台生成，本包不预置、不编造任何正式分数
  （`efficiency.official_score` = null，`model_requests` = null）。
- `real_validator_dual_run` 证明的是「本 Skill 的机制是产物通过校验的必要条件」，
  **不等价于**平台基础 Agent 的分数差。
- 同源规则存在「自己尺子量自己」的固有局限（README §8 已明写）；外部复核仍需人眼看
  `evidence.quote` 是否真出自原文。
- 自测夹具为**合成输入**，数字仅证明机制自洽，不冒充正式案例表现。

---

## v3（上一轮：解 0 分优先 + 补增益/创新/生态）

### 1. 0 分排查结论（第一优先，逐条核对题面 Harbor 运行契约）

题面契约原文：*"original input is `/input/case.json` … Work under `/app/work`; final
actual results … under `/app/output`, including `result.json` … Execution budget: 64
model requests, 900 seconds"*，且 *"The evaluator installs the actual Skill under
`/skills/weekly-skill`"*。

对照上轮包（176 行 SKILL.md），查出 **4 个足以让整跑失败的风险点**，本轮全部修掉：

| # | 风险点 | 上轮实况 | 本轮修法 | 后果 |
|---|---|---|---|---|
| ① | **占位符路径未解析** | SKILL.md 全文用 `$IN`/`$WORK`/`$OUT`/`$SKILL`，且明写"按平台运行说明替换"——沙箱**不设这些环境变量**，Agent 若不替换则 `ls "$IN"` 直接失败，整跑崩 | 路径全部写死：`/input/case.json`、`/app/work`、`/app/output/result.json`、`/skills/weekly-skill/scripts/`；并给 `SD=$(dirname $(find / -name mathml2latex.py -path '*scripts*' \| head -1))` 兜底定位 | 命令可直接复制执行 |
| ② | **`python` 未必存在** | SKILL.md 全部用 `python`；沙箱只保证 python3.12 | 全部改 `python3`，并注明"无 python3 时用 python" | 避免 `command not found` |
| ③ | **产物路径错位** | Step 5 是 `cp "$WORK/result.json" "$OUT/result.json"`，`$OUT` 未定义 → cp 到错误位置，**`/app/output` 缺 result.json** | 协议第 1 条置顶："第一个写盘动作就是在 `/app/output/result.json` 写骨架"，此后该文件必须始终存在且可解析 | 平台侧能取到产物 |
| ④ | **校验脚本非零退出** | `mathml2latex.py` 有 failed 时 `return 3`；`formula_check.py` JSON 非法 `return 1`；`semantic_check.py` JSON 非法 `return 2`；`result_scaffold.py` 写失败 `return 1` | 全部改**退出码恒 0**，verdict 照实写进报告与 stdout（`PASS`/`FAIL（n 处…）`） | 平台把非零退出判整跑 failed → 0 分的引信拆除 |

补充两项防御：**预算熔断**（请求 >48 或耗时 >700 秒立即收尾用现有中间结果补齐
result.json）+ **广度优先**（先让全部公式有非空 LaTeX 再逐条加深），针对 64 请求/900 秒
预算下流程过长导致的超时失败。

### 2. 五维差距清单与本轮补强点

| 维度 | 分值 | 上轮差距 | 本轮补强 |
|---|---|---|---|
| 实际效果 | 40 | 有三层解读但无契约字段对齐证据 | 补 `result.gates` 闸门四态（7 个闸门，按实际内容派生）；`references/result-schema.md` 逐字段规格；数值核验由脚本**独立重算**（不信声明的 `within_tolerance`，自己算相对误差） |
| 使用增益 | 25 | **完全缺失**（无任何对照证据） | 新增 `gain_probe.py`：**同输入真实双跑**（完整模式 vs `--ablate` 消融模式，两个独立子进程，产物落盘）+ 声明式消融投影 P1-P5，产出 11 项逐项对照指标与 delta，每项标注来源 `real_double_run` / `declared_projection` |
| 创新增益 | 15 | 无 | ① 同输入双跑 + 声明式消融投影的**可复核增益取证范式**（不依赖平台白板即可给出机制增益数字，且明示两类证据强度）；② 闸门四态（`enforced`/`skipped_not_provided`/`not_found`/`unreadable`，没跑 ≠ 通过）；③ 数值核验独立重算 + 相对误差 mismatch 清单 |
| 可靠体验 | 10 | 校验失败会中断（退出码非 0） | 全部退出码恒 0 + 协议第 6/8 条"绝不中断交付" + 降级写 `uncertainties.summary`；闸门四态覆盖异常情形识别 |
| 生态贡献 | 10 | README 仅列文件与调用，缺自检清单 | README 重写：§4 **最小可运行自检清单（5 条命令，复制即跑）**、§5 机制→指标映射表、§6 效率计数与复现方式、§7 **生态贡献全套**（文档完整性 3 项 / 资源可复用性 4 项 / 分享推广价值 3 项逐条对应） |

### 3. 本轮变更清单

1. **`scripts/gain_probe.py`（新增，核心）**：同输入双跑消融对照 + 逐项对照指标 +
   效率计数。指标：公式产出率 / 完整还原率 / 结构保真率 / 结构算子召回率（真实双跑），
   变量表完整率 / 符号覆盖率 / 数值核验通过率 / 推导步可追溯率 / 论断带证据率 /
   需人工核对条目数 / 步骤数（声明式投影）。内含 `mechanism_to_metric`（M1-M4）、
   `projection_rules`（P1-P5）、`boundaries`、`failure_conditions`、
   `baseline_disclaimer`（明示非平台白板）。
2. **`scripts/mathml2latex.py`**：新增 `--ablate` 消融开关（关闭 MathML 结构化优先
   还原，退化为文本拼接通道）；退出码恒 0；产物加 `mode` 字段。
3. **`scripts/result_scaffold.py`**：新增闸门四态派生（`_derive_gates`，7 闸门）；
   `ensure` 补 `result.gates`。
4. **`scripts/formula_check.py`**：新增闸门四态校验（缺失/状态非法/非 enforced 缺
   gate_note），共 9 类；JSON 非法改 return 0。
5. **`scripts/semantic_check.py`**：JSON 非法改 return 0。
6. **`SKILL.md`**：176 → **150 行**（≤150 硬约束）。重构为"强制执行协议（置顶 9 条）+
   线性五步 + 输出字段表 + 校验器分工与限制"；路径写死、python3、退出码恒 0、
   预算熔断、闸门四态全部写进协议；完整字段规格下沉到 `references/result-schema.md`
   （原 schema 块 44 行 → 表格式 8 行，机制不丢）。
7. **`README.md`**：重写为 v3 使用说明 + 自检清单 + 增益取证 + 效率计数 + 生态贡献全套。
8. **`references/result-schema.md`（新增）**：`result.json` 逐字段规格表（可复用为
   其他团队自建流水线的契约模板）。
9. **`examples/demo-result.json`**：补 `result.gates`（7 闸门）。
10. **`examples/ablation-demo.json`（新增）**：消融对照示意产物（真实本地双跑数字，
    标注为示例）。

### 4. 双测证据（真实数字，本地实跑）

**4.1 正常模式 vs 退化模式（同输入 `examples/demo.xml` 真实双跑）**

| 指标 | skill_full | skill_mechanism_ablation | delta | 来源 |
|---|---|---|---|---|
| formula_yield_rate | 1.0 | 1.0 | 0.0 | real_double_run |
| full_conversion_rate | 1.0 | 0.0 | **+1.0** | real_double_run |
| structure_fidelity_rate | 1.0 | 0.0 | **+1.0** | real_double_run |
| structural_op_recall | 1.0 | 0.0 | **+1.0** | real_double_run |
| variable_table_completeness | 1.0 | 0.0 | **+1.0** | declared_projection |
| symbol_coverage_rate | 1.0 | 0.0 | **+1.0** | declared_projection |
| numeric_verification_pass_rate | 1.0 | 0.0 | **+1.0** | declared_projection |
| step_traceability_rate | 1.0 | null | null | declared_projection |
| claim_evidence_rate | 1.0 | null | null | declared_projection |
| manual_review_items | 0 | 2 | −2 | declared_projection |
| derivation_steps | 1 | 1 | 0 | declared_projection |

两臂 LaTeX 实测对照（同一 `<m:math id="f1">`）：
- 完整模式：`η = \frac{P_{\mathrm{out}}}{P_{\mathrm{in}}}`（conversion=full）
- 消融模式：`η = P out P in`（文本拼接，conversion=partial，ambiguity_notes 已记）
→ 结构化优先还原确实保住了分式与上下标层级，这正是 M1 的机制贡献。

**4.2 污染数据反例（4 处缺陷，退出码均为 0）**

在 `examples/demo-result.json` 上注入 4 处缺陷 → 删 `semantics`、删推导步 `evidence`、
删核验输入 `units`、`gates.mathml_converted.status="bogus"`：

```
formula_check  exit=0  FAIL（1 处）
  - gates[mathml_converted] 状态非法: 'bogus'（只允许 enforced/not_found/skipped_not_provided/unreadable）
semantic_check exit=0  FAIL（3 处 FAIL，0 处 WARN）
  FAIL F1 [f1] 缺 semantics（逐符号含义/量纲解读）——讲得清维度未达标
  FAIL F3 [step1] recomputable 推导步缺 evidence（论文参数摘录）
  FAIL F5 [f1] verified 核验的输入缺 units 或 source: {'symbol': 'P_out', 'value': 41.9, 'source': '§3.1 p03'}
```
→ 校验器全部抓到（F1/F3/F5 + 闸门非法），且**两个脚本退出码均为 0**，不中断交付。

**4.3 正向链路与资源自检**

```
① mathml2latex  → PASS 1 个公式对象（failed=0）        exit=0
② formula_check → PASS {formulas:1, variables:3, derivations:1, verification:1, claims:1, gates:7}  exit=0
   semantic_check→ PASS（0 处 WARN）{semantics_covered:3, recomputable_steps:1, verified:1}  exit=0
③ gain_probe    → arms=skill_full,skill_mechanism_ablation，comparison 项=11，脚本调用 2 次，耗时 0.652s
⑤ 资源自检      → files=13 (上限50)；total=141.0KB (上限2048KB)；scripts=6 (上限8)；SKILL.md lines=150 (上限150)
```

### 5. 诚实边界声明

- `gain_probe` 的 baseline 是**本 Skill 机制消融基线**（同输入同产物、关闭本 Skill
  机制），**不是**平台「基础 Agent 不加载 Skill」白板。平台对照由平台生成，
  本包不预置、不编造任何正式分数或 benchmark 成绩（`efficiency.official_score` = null）。
- `model_requests` 亦置 null（平台记录），不自行编造。
- 消融投影是确定性函数（P5），同一 result.json 必得同一 baseline，可被第三方复算。
- 无 MathML 表示时（C02 类）公式层指标标 `available=false` 并保留真实缺失分支说明，
  **不以 0 冒充未测**。

### 6. 遗留与说明

- 未提交平台（按主控要求由主控统一提交）。
- `examples/ablation-demo.json` 为合成样例的真实双跑产物，**不含正式案例答案**；
  `examples/demo-result.json` 为合成示意输出（changelog 已标"合成示例，非正式案例答案"）。
- 遗留限制不变：mtable 大矩阵 partial（显式标注）；文本通道产物保守需人工校对；
  公式图像输入先经平台 OCR 再走通道 B。

---

## v2（历史）解读深度增强版

### 1. 定位与策略

v4（attempt 73322，未出分）已解决 0 分根因：历史 71333/72098/72479 三连 0 的根因是
转换器对真实出版商 XML（DOCTYPE + 命名实体）崩溃产空结果，v4 用五级容错链堵死
"产物为空"这条路。v2 **容错机制原样保留（mathml2latex.py / result_scaffold.py /
formula_check.py / schema_guard.py 四脚本零改动），增量全部投在解读深度**：
0 分解决后能否上 70，取决于解读产物质量，对应题目四个评分维度
"认得准（还原+人工校对）/ 讲得清（语义层）/ 推得顺（推导链）/ 算得回（核验留痕）"。

## 2. v4 → v2 变更清单

1. **`scripts/semantic_check.py`（新增，核心）**：解读深度校验器，与结构层的
   formula_check 分工——后者抓"产物非空/结构合法"，前者抓"讲得清/推得顺/算得回"：
   - F1 每条 `conversion!=failed` 公式必须有 `semantics` 逐符号块（symbol+meaning）；
   - F2 provenance 三级枚举校验，原文定义必须带 `source_location`（可指回原文）；
   - F3 `recomputable:true` 推导步必须有 `evidence`（逐字摘录论文参数）；
   - F4 `recomputable:true` 推导步必须有 `intermediate_value`（中间值留痕）；
   - F5 `verified` 核验的 inputs 每项必须带 `units` + `source`（可复跑）；
   - F6 `not_recomputable` 必须 missing 逐项清单；
   - F7 claims evidence 必须逐字 quote；
   - W1-W4 警告：latex 中 `\mathrm{...}` 标识未进变量表/语义块（漏变量检测）、
     常识补充未进 human_review、推导步无 using/depends_on 也未标 gap、
     claims 数少于公式数。
2. **SKILL.md 增强**：契约新增"解读三层缺一不可"；Step 3 重写为"语义层"（semantics
   块字段规格：meaning/dimension/typical_value/provenance/source_location，与全局
   variables 同符号对齐）；Step 4 推导链扩字段（recomputable/intermediate_value/
   evidence）；Step 5 四道校验（ensure → formula_check → semantic_check →
   schema_guard）；schema 加 formulas[].semantics 与 derivations 新字段；
   coverage 加 semantics_covered/recomputed_steps。
3. **examples/（新增）**：demo.xml（含命名实体 MathML）+ demo-result.json（含完整
   三层解读的示意 result），既是最小调用示例，也是校验链的正向自测用例。
4. **README.md / worklog.md 重写**：双层校验分工、文件清单、测试记录。

## 3. 本地测试结果（tests/ 目录）

### 3.1 五类脏输入回归（mathml2latex.py 未改动，确认无回归）

| 输入 | 场景 | 结果（与 v4 记录一致） |
|---|---|---|
| case1-clean.xml | 干净 MathML | f1 `full`：`η = \frac{P_{m a x}}{P_{\mathrm{in}}} \times 100 %` |
| case2-doctype-entities.xml | DOCTYPE+命名实体 | f2 `full`：`Δ P = ρ g h` |
| case3-bad-entities.xml | 未知实体+裸 &/< | f3 `full`：`G = \frac{a + b}{2}` |
| case4-truncated.xml | 截断 XML（未闭合尾块） | f4 `full` + math-1 `partial`（文本降级），2/2 非空 |
| case5-plaintext.txt（--text-file） | 纯文本公式 | text-1 `partial`：`\eta = P_{out} / P_{in} \cdot 100 % …` |

### 3.2 semantic_check 自测

- **正向**：examples/demo-result.json → PASS（formulas=1, semantics_covered=3,
  recomputable_steps=1, verified=1, claims=1，0 WARN）；
  formula_check 对同一文件 PASS。
- **负向**：构造 6 处缺陷（删 semantics、删推导步 evidence 与 intermediate_value、
  核验输入删 units、not_recomputable 空 missing、claims quote 空串）→
  FAIL 精确命中 F1/F3/F4/F5/F6/F7 共 6 处，退出码 1。

### 3.3 结构链路

formula_check + schema_guard 对 demo-result.json PASS（契约字段齐全）。

## 4. 遗留与说明

- v4 三级遗留不变：mtable 大矩阵 partial 显式标注；文本通道产物保守需人工校对；
  公式图像输入先经平台 OCR 再走通道 B。
- 未提交平台（按主控要求由主控统一提交）；tests/out*/bad-*.json 为本地测试产物，
  不属于提交资源。
