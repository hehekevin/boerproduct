# formula-parse v3（challenge-7c37626c 解读深度增强版）— 使用说明

围绕「公式解析与数学推理」的 Skill。v3 在五级容错（产物非空生命线）之上，把交付重心放在**解读深度**：每条公式还原后必须过三层——**语义层**（逐符号含义/量纲/典型取值/定义位置，区分原文定义与推断）、**推导层**（可复算步中间值留痕 + 论文参数逐字摘录）、**核验层**（代入数带单位与出处）。不可复算项逐条登记 `not_recomputable + missing`。附**同输入双跑消融对照**（`gain_evidence`）与**效率计数**（`efficiency`）。

> 本包**不预置任何正式案例答案或分数**。`examples/` 内为合成示意输入，非平台正式案例。

## 1. 依赖与版本

| 项 | 要求 | 说明 |
|---|---|---|
| 运行时 | Python **3.8+**（沙箱保证 3.12；本地实测 3.13） | 只用标准库：`argparse/json/re/os/re/subprocess/sys/time/xml.etree` |
| 第三方依赖 | **零** | 无 pip install，无网络请求，无二进制依赖 |
| Shell | POSIX `sh` / `bash` | SKILL.md 中只用 `mkdir -p`/`cat`/`find`/`head` 等基础命令 |
| 编码 | UTF-8 | 全部文件 UTF-8，无 BOM |
| 路径约定 | 平台运行时 `/input` `/app/work` `/app/output`；脚本目录 `/skills/weekly-skill/scripts/` | 脚本自身**无硬编码路径**，全部走 `--` 参数 |
| 资源上限 | 脚本 6 个（≤8）、包 <2MB、文本文件 10 个（≤50） | 无符号链接 |

## 2. 安装与运行

无需安装。克隆/解压后直接调用：

```bash
# Step 1 盘点落骨架（第一个写盘动作）
python3 scripts/result_scaffold.py scaffold --case "$IN/case.json" --out "$WORK/result.json"
# Step 2 公式还原（XML 主通道；无 XML 用 --text-file 纯文本通道）
python3 scripts/mathml2latex.py --convert "$IN/artifacts/source-formulas.xml" \
    --fallback "$IN/artifacts/publisher-source.xml" --out "$WORK/formulas_latex.json"
# Step 3/4 由 Agent 按 SKILL.md 回填语义块、推导链、数值核验（人工解读环节）
# Step 5 兜底 + 校验 + 增益取证 + 落盘
python3 scripts/result_scaffold.py ensure --result "$OUT/result.json" \
    --case "$IN/case.json" --out "$OUT/result.json"
python3 scripts/formula_check.py --result "$OUT/result.json" --case "$IN/case.json" \
    --out "$WORK/formula_check.json"
python3 scripts/semantic_check.py --result "$OUT/result.json" --case "$IN/case.json" \
    --out "$WORK/semantic_check.json"
python3 scripts/schema_guard.py --result "$OUT/result.json" --case "$IN/case.json"
python3 scripts/gain_probe.py --result "$OUT/result.json" --case "$IN/case.json" \
    --source-xml "$IN/artifacts/source-formulas.xml" \
    --out "$WORK/gain_evidence.json" --embed "$OUT/result.json"
```

**退出码策略（重要）**：所有脚本**退出码恒 0**，包括参数错误、文件缺失、JSON 损坏、输出目录不可写。内容级 FAIL 只写进报告与 `result.json` 的 `uncertainties`，**绝不中断交付**——平台侧会把非零退出判为整跑 failed（直接 0 分）。verdict 照实记录在报告 `ok`/`problems`/`fails` 字段。

## 3. 输入输出解释

**输入**：`case.json`（含 `case_id` 与 `output_contract`）+ 材料。
- C01/C03 类：给 `publisher-source.xml`（原样出版商 XML，含 DOCTYPE + 命名实体）与 `source-formulas.xml`（公式节点子集，保留 MathML 分式/上下标/来源 ID）。
- C02 类：**无**公式表示、逐条预测或可复算原始数据 → 走真实缺失分支，照常写全字段并报 `partial`/`insufficient_evidence`，**不反推公式、不把未知填 0**。
- 无 XML（仅 OCR/PDF 文本）→ `mathml2latex.py --text-file`。

**输出**：`result.json`（顶层）
| 字段 | 内容 |
|---|---|
| `case_id` | 取自 `case.json` |
| `status` | `answered` / `partial` / `insufficient_evidence` / `input_error`（诚实四级） |
| `result.formulas[]` | `formula_id` `source_locator` `latex` `conversion` `ambiguity_notes` `semantics[]` |
| `result.variables[]` | `symbol` `latex` `definition` `units` `range` `first_defined_at` `provenance` |
| `result.derivations[]` | `step_no` `expression` `recomputable` `using` `depends_on` `why_valid` `gap` `intermediate_value` `evidence[]` |
| `result.verification[]` | `formula_id` `inputs[{symbol,value,units,source}]` `expected` `computed` `within_tolerance` `status` `missing[]` |
| `result.coverage` / `result.gates` | 覆盖统计 / 闸门四态 |
| `claims[]` | `claim_id` `text` `kind` `source_id` `location` `evidence[{paragraph_id,quote}]` |
| `uncertainties` | `unreported` `unverifiable` `conflicts` `human_review` `summary` |
| `changelog[]` | `step` `change` |
| `gain_evidence` | 两臂对照数字 + 校验器实测 FAIL 数差（见 §6） |
| `efficiency` | 脚本调用数、墙钟耗时、产物条目数、吞吐量 |

完整逐字段规格见 `references/result-schema.md`。

## 4. 目标用户与场景

- **科研阅读 Agent**：给定论文 XML/PDF 片段，需要「公式 → LaTeX + 变量表 + 推导说明 + 数值核验」的可复核结构化产物。
- **论文评审/复核人**：需要把公式还原结果逐条对回原文位置（`source_locator` / `source_location` / `evidence.quote`）。
- **数值复算者**：需要按 `verification.inputs` 的 `value`+`units`+`source` 独立重跑复算。
- **教学/组会**：需要「可检查步骤 + 中间值 + 假设与边界条件」的推导链。
- **不适用**：纯符号演算求解、无公式的纯文本问答、需要 LaTeX 编译渲染的场景（本包只出结构化 LaTeX 文本）。

## 5. 验收方式

三层自校验，任一层 FAIL 都需修复或如实登记后仍照常交付：

| 层 | 脚本 | 通过标准 |
|---|---|---|
| 结构/非空 | `formula_check.py` | `ok=true`，0 处 problems（9 类检查） |
| 解读深度 | `semantic_check.py` | `ok=true`，0 处 fails（F1-F7；W1-W4 为警告，可交付） |
| 契约字段 | `schema_guard.py` | 无「缺少 output_contract 字段」 |
| 增益取证 | `gain_probe.py` | `gain_evidence.comparison` 有非空两臂数字；`validator_dual_run.available=true` |

**外部验收**（提交材料层面）：按题面「结果可核验性」逐条抽查——每个符号定义能否指回原文位置、每步推导与数值代入能否按记录复跑。

## 6. 增益取证怎么读（`gain_evidence`）

`comparison` 里每个指标带 `source` 标签，**三种口径不可混为一谈**：

| source | 含义 | 可信度 |
|---|---|---|
| `real_double_run` | 同一份源 XML，完整模式 vs `--ablate` 消融模式**各跑一次真实子进程**，差异直接来自转换器 | 最高（真实运行，转换器确定性） |
| `real_validator_dual_run` | 两臂产物交给**同一套校验器各跑一次**，得到机器判定的 FAIL 数差 | 高（机器判定，非文字自述） |
| `declared_projection` | 确定性消融投影（关掉 M2/M3/M4 机制后的**下界**） | 中（是下界，不是平台实测值） |

`gain_probe` 的 baseline 是**本 Skill 机制消融基线**，**不是**平台「基础 Agent 不加载 Skill」白板；平台对照由平台生成，本包不预置、不编造任何正式分数（`official_score: null`）。

## 7. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `formula_check` 报「缺 output_contract 字段」 | `case.json` 的 `output_contract` 含 `gain_evidence`/`efficiency` 等顶层键，而 result.json 尚未跑 Step 5 | 跑 `gain_probe.py --embed` 后重跑校验 |
| `semantic_check` 报 F1「缺 semantics」 | 公式已还原但没做逐符号解读 | 按 SKILL.md Step 3 回填语义块 |
| `semantic_check` 报 F6「missing 为空」 | 标了 `not_recomputable` 却没列缺失输入 | 逐项列出缺哪个量/单位/出处 |
| `formula_check` 报「coverage.not_recomputable=true 但有 computed」 | 编造检测命中 | 口径二选一：要么填真实复算值，要么声明不可复算 |
| `mathml2latex` 输出全 `partial` | 走了文本降级通道（源不是合法 MathML） | 确认源文件路径正确；必要时用 `--text-file` 并人工校对 |
| `gain_probe` 报「未提供或不存在公式源 XML」 | 输入确实无公式源（C02 类） | 正常：公式层指标为 `null`（真实缺失），不冒充 0 |
| 平台跑完 `result.json` 不存在 | 未做 Step 1 | Step 1 是第一个写盘动作，务必先落骨架 |

## 8. 已知限制

- MathML 转换覆盖常见结构（mfrac/msup/msub/msubsup/msqrt/mroot/mfenced/希腊字母/常用运算符）；**mtable 大矩阵可能 partial**（显式标注，不硬编）。
- 五级容错覆盖 DOCTYPE、命名/数字实体、裸 `&`/`<`、自闭合与截断 math 块；极端畸形输入走文本拼接通道，产物非空但标 `partial` 待人工校对。
- `typical_value` 只抄论文给出的值，论文未给的一律 `null` **不猜**；数值核验只在原文给出足够输入时逐项执行，缺输入逐条登记 `missing`。
- 公式图像输入需先经平台 OCR/PDF 工具转文本或 MathML，再走通道 B（本包不含 OCR 依赖）。
- 变量表完整率用启发式符号抽取（规则见 `gain_probe.latex_symbols`，公开可复核）；希腊字母已归一（`\eta`→`η`），多字母下标按 `X_sub` 形态对齐，人工复核可能微调。
- 真实双跑每臂只跑一次，不做多次重复取均值；脚本耗时受沙箱负载影响，只作数量级参考不作性能承诺。
- 校验器与对照臂是**同源规则**（同一套检查逻辑），存在「用自己尺子量自己」的固有局限；外部复核仍需人眼看 `evidence.quote` 是否真出自原文。

## 9. 失败处理

- **脚本崩溃/报错** → 退出码恒 0，流程不中断；按 `references/result-schema.md` 手写等价 JSON 继续，降级写入 `uncertainties.summary`。
- **脚本文件缺失** → 同上，手写 JSON 兜底。
- **输入缺失/损坏** → `status: input_error` + `uncertainties.summary` 写明原因，**仍产出 result.json**。
- **预算超限**（>48 次请求或 >700 秒）→ 立即停止新增处理，用现有中间结果补齐收尾；广度优先（先全部公式有非空 LaTeX，再加深解读）。
- **平台把整跑判 failed 的唯一硬原因是非零退出** → 本包已把所有退出路径锁死为 0。

## 10. 复用建议

- **换案例**：不改脚本，只需换 `--case` 与 `--source-xml`；`gain_probe` 会自动重新取对照数字。
- **换符号约定**：`gain_probe.GREEK_UNI` / `OPERATORS` / `STOP_WORDS` 三个表可扩；`latex_symbols` 规则公开，评审可自行复算。
- **做基准**：直接复用 `gain_probe.py` 的 `real_double_run` + `real_validator_dual_run` 两段逻辑，套自己的公式集即可得到两臂对照。
- **做模板**：`examples/demo-result.json` 的三层结构（formulas[].semantics / derivations[] / verification[]）可直接当 result.json 的填写模板。
- **接入 CI**：`formula_check.py` 与 `semantic_check.py` 输出 JSON 报告，可直接被 CI 消费（注意退出码恒 0，须读报告里的 `ok` 字段判定，不能靠退出码）。
- **符号约定**：本包对 `provenance` 采用三级枚举（原文定义/上下文推断/常识补充），接手方建议沿用，保证「讲得清」可被机器判定。

## 11. 版本维护

| 版本 | 变更 | 兼容 |
|---|---|---|
| v3 | 三层解读（语义/推导/核验）；`gain_probe` 增校验器实测对照 + 逐公式结构保真率 + 绝对计数口径；符号口径改「公式侧候选 × 变量侧展开」；**全部脚本退出码锁死为 0**；SKILL.md 压至 ≤150 行 | result.json 顶层新增 `gain_evidence`/`efficiency`；旧 `result.json` 缺这两键时 `ensure` 自动补 |
| v2 | 新增 `semantic_check.py`（F1-F7 深度校验）、`examples/` 合成示例 | v4→v2 四脚本零改动，产物结构兼容 |
| v4 | 五级容错链（堵死「产物为空」这条 0 分路径） | — |

维护约定：改动任何脚本后**必须**跑一遍「§12 最小可运行自检清单」；`SKILL.md` 保持 ≤150 行；改动机制时同步更新 `gain_probe.MECH_MAP` 与 `PROJECTION_RULES`，否则对照数字的来源标签会与实现脱节。

## 12. 最小可运行自检清单

在包目录下执行（5 条命令，无需任何输入文件，全部用 `examples/` 自带合成输入）。
所有中间产物写到 `$TMP`（不污染包目录）：

```bash
TMP=$(mktemp -d)   # 或 mkdir -p /tmp/formula-selftest
# ① 转换器：合成 MathML → LaTeX（应 PASS，1 个公式对象，failed=0）
python3 scripts/mathml2latex.py --convert examples/demo.xml --out $TMP/fl.json
# ② 结构校验：示例 result 应 PASS（ok=true, 0 problems）
python3 scripts/formula_check.py --result examples/demo-result.json --out $TMP/fc.json
# ③ 深度校验：示例 result 应 PASS（ok=true, 0 fails）
python3 scripts/semantic_check.py --result examples/demo-result.json --out $TMP/sc.json
# ④ 退出码恒 0 自检：故意指向不存在的文件仍须 rc=0（不能是 2）
python3 scripts/formula_check.py --result ./no_such_file.json --out $TMP/fc2.json; echo "rc=$?"
# ⑤ 增益取证：对示例 XML 跑双跑，应产出两臂对照数字且退出码 0
python3 scripts/gain_probe.py --result examples/demo-result.json \
    --source-xml examples/demo.xml --out $TMP/ge.json; echo "rc=$?"
```

验收标准：①③④⑤ 的 `rc=0`；②③ 报告里 `ok=true`；⑤ 打印出 `full=… ablate=… delta=…` 的对照行，且 `gain_evidence.json` 里 `validator_dual_run.available=true`。

## 13. 文件清单（13 个，≤50 上限内）

| 文件 | 作用 |
|---|---|
| `SKILL.md` | Skill 本体：运行契约置顶 + 三层解读纪律 + 线性 5 步 + 输出 schema + 校验器分工 + 限制（123 行，≤150） |
| `scripts/mathml2latex.py` | MathML→LaTeX 转换（五级容错，`--ablate` 为消融开关，零依赖） |
| `scripts/result_scaffold.py` | result.json 骨架生成 + 非空兜底修补 + 闸门四态派生 |
| `scripts/formula_check.py` | 结构校验器：产物非空/verification 非空/claims 带证据/编造检测等 9 类 |
| `scripts/semantic_check.py` | 解读深度校验器 F1-F7（讲得清/推得顺/算得回）+ W1-W4 警告 |
| `scripts/schema_guard.py` | 契约守卫：output_contract 全字段结构校验 |
| `scripts/gain_probe.py` | 增益取证：同输入双跑 + 消融对照 + **校验器实测双跑** + 效率计数（19 项对照指标） |
| `references/result-schema.md` | result.json 逐字段规格（按需查阅） |
| `examples/demo.xml` | 合成示意输入（含命名实体 MathML），非正式案例 |
| `examples/demo-result.json` | 合成示意输出（含完整三层解读），非正式答案 |
| `examples/ablation-demo.json` | 消融对照示意产物（真实本地双跑数字，标注为示例） |
| `README.md` | 本文件 |
| `worklog.md` | 变更与测试记录（v3.1 / v3 / v2 三节） |
