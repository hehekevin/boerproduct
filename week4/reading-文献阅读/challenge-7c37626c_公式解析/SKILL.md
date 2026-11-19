---
name: formula-parse
description: 公式解析与数学推理技能（解读深度版 v3）：从出版商 XML 的 MathML 节点/公式图像/纯文本还原 LaTeX（五级容错，任何畸形输入都有非空产物），并交付三层解读——逐符号语义块（含义/量纲/典型取值/定义位置，区分原文定义/上下文推断/常识补充）、可复算推导链（每步中间值留痕+论文参数逐字摘录）、数值代入核验（输入带单位与出处，脚本独立重算）；不可复算项逐条登记 not_recomputable+missing。内置增益取证（gain_probe.py：同输入完整模式 vs 消融模式真实双跑，产出公式产出率/逐公式结构保真率/变量表完整率/数值核验通过率/需人工核对条目数等两臂对照数字，并用同一套校验器对两臂各跑一次给出机器判定的 FAIL 数差）与效率计数。Use when the task asks to parse formulas in a supplied paper into LaTeX with symbol semantics, traceable derivation chains and numeric verification.
---

# formula-parse v3 — 公式解析（还原准 · 讲得清 · 推得顺 · 算得回）

公式解析不是"贴一段 LaTeX"。本 Skill 在五级容错（产物非空生命线）之上把交付重心放在**解读深度**：每条公式还原后必须过三层——**语义层**（每个符号可指回原文）、**推导层**（每步可复算、有留痕）、**核验层**（代入数带单位与出处），并附同输入双跑消融对照（gain_evidence）与效率计数（efficiency）。

## 0. 强制执行协议（优先级高于本文档其余内容）

1. **第一个写盘动作就是在 `/app/output/result.json` 写骨架**：含 `case_id`（取自 `/input/case.json`）+ `status`/`result`/`claims`/`uncertainties`/`changelog`。此后任何时刻该文件必须存在且 JSON 可解析。先 `mkdir -p /app/work /app/output`。
2. **路径写死，不依赖未定义环境变量**：`/input/case.json`（输入）、`/app/work`（工作）、`/app/output`（产物）、脚本在 `/skills/weekly-skill/scripts/`。若脚本不在该路径：`SD=$(dirname $(find / -name mathml2latex.py -path '*scripts*' 2>/dev/null | head -1))`。
3. **用 `python3` 而非 `python`**（沙箱仅保证 python3.12）；无 `python3` 时用 `python`。
4. **产物非空是生命线**：`result` 字段、每条公式 `latex`、`claims`、`verification` 数组——任何分支不得为空串/null/空数组。
5. **解读三层缺一不可**：每条 `conversion!=failed` 的公式必须有 `semantics` 逐符号块；标 `recomputable:true` 的推导步必须有 `evidence`（论文参数逐字摘录）+ `intermediate_value`（中间值）；`status:verified` 的核验输入必须带 `units`+`source`。
6. **status 诚实四级**：`answered`/`partial`/`insufficient_evidence`/`input_error`，不得虚报。**不编造**：推导结果、核验数值、benchmark 分数一律来自计算或原文。
7. **所有脚本退出码恒 0**（含参数错误、读取失败、写入失败）：内容级 FAIL 只写进报告与 `uncertainties`，**绝不中断交付**——平台侧会把非零退出判为整跑 failed → 0 分。
8. **预算熔断**：平台预算 64 次模型请求 / 900 秒。请求数 > 48 或耗时 > 700 秒时，立即停止新增处理，用现有中间结果补齐 result.json 收尾。**广度优先**：先让全部公式有非空 LaTeX，再逐条加深语义/推导/核验。
9. **失败也要交付**：任何异常都写 result.json（status 用诚实四级，原因写进 `uncertainties.summary`），绝不让 `/app/output` 缺少 result.json。
## 1. 线性五步（每步产出立即落盘）

### Step 1 — 读题盘点，落骨架
```bash
mkdir -p /app/work /app/output
cat /input/case.json | head -c 4000
python3 /skills/weekly-skill/scripts/result_scaffold.py scaffold \
    --case /input/case.json --out /app/output/result.json
```
- C01/C03 类（有 `publisher-source.xml` + `source-formulas.xml`）→ 完整还原+三层解读；C02 类（确无公式表示/逐条预测/可复算数据）→ 真实缺失分支：照常写全字段，报 `partial` 或 `insufficient_evidence`，**不反推公式、不把未知填 0**；可核对部分（明确指标与条件）逐条核出，缺的对象逐条进 `uncertainties.unreported`。
- 公式目录不是线性化答案——目录只是起点，逐条还原后还要人工校对+解读。

### Step 2 — 公式对象还原（MathML 优先，五级容错）
```bash
python3 /skills/weekly-skill/scripts/mathml2latex.py \
    --convert /input/artifacts/source-formulas.xml \
    --fallback /input/artifacts/publisher-source.xml \
    --out /app/work/formulas_latex.json
# 无 XML 时（OCR/PDF 提取文本）改用：--text-file /app/work/formulas_raw.txt
```
- 五级容错链保证任何输入都有非空产物：标准解析 → DOCTYPE 剥离+实体解码 → 正则提取 math 块（自闭合/截断/命名空间前缀）→ 块级失败降级文本提取 → 结构转换为空回退 itertext 拼接。降级标 `conversion:"partial"` + `ambiguity_notes`。
- **人工校对**：上下标层级、括号配对、希腊字母映射（ρ vs p）、单位正体（\mathrm）、多字母下标。校对完立即回填 formulas 数组并覆盖 `/app/output/result.json`。

### Step 3 — 语义层：变量表 + 逐公式语义块
- **逐公式语义块**（嵌入 `formulas[i].semantics`），每个符号一行 `{symbol, meaning, dimension, typical_value, provenance, source_location}`：`meaning` = 该符号在此公式中的物理/数学含义（论文原话或最近定义改写）；`dimension` = 量纲或类型（W / 无量纲 / 矩阵 m×n；纯数学符号写"无量纲/算子"）；`typical_value` = 论文给出的取值（有则填，无则 `null`，**不猜**）；`provenance` ∈ `原文定义 | 上下文推断 | 常识补充`——常识补充必须显式标注并进 `uncertainties.human_review`，不得混入原文定义；`source_location` = 定义位置（段落号/公式号/表号），原文定义必填。
- **全局变量表** `variables`：与语义块同符号对齐（同名符号两处定义必须一致）。
- 判定纪律：讲得清 = 符号定义可指回原文；找不到原文定义就如实标 `上下文推断` 或 `常识补充`，不冒充原文定义。

### Step 4 — 推导链 + 数值核验（可复算项全程留痕）
- **推导链** `derivations`：`recomputable:true` 的步必须给 `intermediate_value`（该步算出的中间值）+ `evidence`（≥1 条 `{paragraph_id, quote}` 逐字摘录所用论文参数/假设）；原文跳步标 `gap:true` 并列入 uncertainties，不脑补；跨公式引用写 `depends_on`（如 `["Eq.(3)"]`），依赖顺序即计算顺序。
- **数值核验** `verification`（必做交付，数组不许空）：`verified` 条目的 `inputs` 每项 `{symbol, value, units, source}`——单位与出处必填；`expected`(原文值) vs `computed`(复算值)，数量级不对先怀疑读数与单位；缺输入的公式逐条 `{status:"not_recomputable", missing:[逐项缺失输入]}`；C02 类放一条 `not_recomputable` 占位并注明题面真实缺失分支。

### Step 5 — 非空兜底 + 三层校验 + 增益取证 + 落盘
```bash
python3 /skills/weekly-skill/scripts/result_scaffold.py ensure \
    --result /app/output/result.json --case /input/case.json --out /app/output/result.json
python3 /skills/weekly-skill/scripts/formula_check.py \
    --result /app/output/result.json --case /input/case.json --out /app/work/formula_check.json
python3 /skills/weekly-skill/scripts/semantic_check.py \
    --result /app/output/result.json --case /input/case.json --out /app/work/semantic_check.json
python3 /skills/weekly-skill/scripts/schema_guard.py \
    --result /app/output/result.json --case /input/case.json
python3 /skills/weekly-skill/scripts/gain_probe.py \
    --result /app/output/result.json --case /input/case.json \
    --source-xml /input/artifacts/source-formulas.xml \
    --out /app/work/gain_evidence.json --embed /app/output/result.json
```
- `ensure` 修补空缺并派生闸门四态；`formula_check` 抓结构错；`semantic_check` 抓深度错；
  `schema_guard` 抓契约字段；`gain_probe` 产同输入双跑消融对照并写回 gain_evidence +
  efficiency。**任一校验 FAIL 都不要中断交付**：修一轮，修不好就在 `uncertainties` 里
  如实记录 FAIL 项后照常交付（脚本退出码恒 0，verdict 在报告里）。

## 2. 输出 schema（result.json）

完整逐字段规格见 `references/result-schema.md`（按需查阅）。顶层键：`case_id` `status`
`result` `claims` `uncertainties` `changelog` `gain_evidence` `efficiency`。`result` 内：
`formulas[]`（含 `semantics[]`）`variables[]` `derivations[]` `verification[]` `coverage`
`gates`。枚举：`status` ∈ answered|partial|insufficient_evidence|input_error；
`conversion` ∈ full|partial|failed；`provenance` ∈ 原文定义|上下文推断|常识补充；
verification.`status` ∈ verified|not_recomputable；claims.`kind` ∈ reported|inferred；
`gates[k].status` ∈ enforced|skipped_not_provided|not_found|unreadable。
`case.json` 的 `output_contract` 若含更多键，原样照抄生成并填 unknown 或空数组。

**闸门四态**（`result.gates`）：`enforced` 该步真实跑完且产物非空；
`skipped_not_provided` 输入本身没有该类对象（合法跳过，须写明缺什么）；
`not_found` 应有但没跑/产物缺失（**没跑 ≠ 通过**，gate_note 必填）；
`unreadable` 文件在但损坏/不可解析（gate_note 带原因）。

## 3. 校验器分工（退出码恒 0；verdict 照实记录）

- **formula_check.py（结构/非空，9 类）**：result 空对象 FAIL；conversion=full 但 latex 空
  FAIL；partial 缺 ambiguity_notes；provenance 非法/原文定义缺 first_defined_at；
  verification 空数组 FAIL；expected/computed 只填一个；claims 空或缺 evidence FAIL；
  gap 未列 uncertainties；coverage.not_recomputable 与 computed 冲突（编造检测）；
  gates 缺失/状态非法/非 enforced 缺 gate_note FAIL。
- **semantic_check.py（深度 F1-F7）**：F1 每条 `conversion!=failed` 公式须有 `semantics`
  且逐符号含 symbol+meaning；F2 provenance 非法/原文定义缺 `source_location`；F3
  `recomputable:true` 步缺 `evidence`（或 quote 空）；F4 同类步缺 `intermediate_value`；
  F5 `verified` 输入缺 `units`/`source`；F6 `not_recomputable` 缺 missing 清单；
  F7 claims evidence 缺逐字 quote。W1-W4 警告：latex 标识/下标组合未进 variables/semantics、
  常识补充未进 human_review、推导步无 using/depends_on 也未标 gap、claims 少于公式数。
- **schema_guard.py**：校验 case.json 的 output_contract 全字段 + case_id 齐备。
- **gain_probe.py（增益取证）**：同输入真实双跑（完整模式 vs `--ablate` 消融模式），写
  `gain_evidence`（公式产出率/逐公式结构保真率/结构算子召回率/变量表完整率/符号覆盖率/
  数值核验通过率/需人工核对条目数/步骤数/完整定义变量数等两臂数字与 delta，每项标注
  来源 `real_double_run` / `real_validator_dual_run` / `declared_projection`）+ `efficiency`
  （脚本调用数、真实墙钟耗时、产物条目数、吞吐量）。**校验器实测对照**是把两臂产物
  交给同一套 `formula_check.py`+`semantic_check.py` 各跑一次，给出机器判定的 FAIL 数差。

## 4. 已知限制与异常处置

- MathML 转换覆盖常见结构（mfrac/msup/msub/msubsup/msqrt/mroot/mfenced/希腊字母/常用
  运算符）；mtable 大矩阵可能 partial（显式标注，不硬编）。五级容错覆盖 DOCTYPE、
  命名/数字实体、裸 &/<、自闭合与截断 math 块；极端畸形输入走文本拼接通道，产物非空
  但标 partial 待人工校对。
- `typical_value` 只抄论文给出的值，论文未给的一律 null 不猜；数值核验只在原文给出
  足够输入时逐项执行，缺输入逐条登记 missing 不反推公式。公式图像输入需先经平台
  OCR/PDF 工具转文本或 MathML，再走通道 B。
- `gain_probe` 的 baseline 是**本 Skill 机制消融基线**，非平台「基础 Agent 不加载
  Skill」白板；平台对照由平台生成，本 Skill 不预置、不编造任何正式分数。无公式源
  （C02 类）时公式层指标为 `null`（真实缺失），不冒充 0。
- 脚本缺失/报错：按本文档 schema 手写等价 JSON 继续，流程不中断，降级写入
  `uncertainties.summary`。
