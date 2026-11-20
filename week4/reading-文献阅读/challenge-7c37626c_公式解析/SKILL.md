---
name: formula-parse
description: 公式解析与数学推理技能：从出版商 XML 的 MathML 节点/公式图像/纯文本还原 LaTeX（mathml2latex.py 五级容错，任何畸形输入都有非空产物），建变量表（定义位置/单位/取值范围，区分原文定义与推断），推导分步并标注假设边界；数值代入核验可算公式；材料无公式表示时按真实缺失分支报 partial/insufficient_evidence，不反推公式不补零。Use when the task asks to parse formulas in a supplied paper into LaTeX with variable tables, stepwise derivations and numeric verification.
---

# formula-parse — 公式解析（产物非空 · 变量可溯 · 推导分步 · 核验留痕）

公式解析不是"贴一段 LaTeX"。本技能的顺序是：**机器还原优先**（出版商 XML 里的 MathML 节点
是最忠实的来源，先转换再人工校对）；变量逐个落到原文定义；推导拆步并标注假设；
能代入的做数值核验；**材料里真没有公式对象的，按缺失分支如实报告**。

## 0. 运行契约（置顶，任何情况下不违反）

- **产物非空是生命线**：`result.json` 的 `result` 字段、每条公式 `latex`、`claims`、
  `verification` 数组——任何分支（解析成功/部分失败/材料缺失）都不得为空串、null 或空数组。
  兜底由 `result_scaffold.py` 强制：骨架先行 + 结束前 ensure 修补。
- **status 诚实四级**：`answered`（完整）/`partial`（部分完成，说明缺什么）/
  `insufficient_evidence`（材料无法判断）/`input_error`（输入不可读）。不许用完整状态
  掩盖缺失，也不许因局部缺失直接弃答。
- **不编造**：推导结果、核验数值、benchmark 分数一律来自计算或原文；缺失就登记缺失。
- **路径约定**：平台运行时提供输入文件（含 `case.json` 与材料）与输出目录；下文
  `$IN` = 输入目录，`$WORK` = 工作目录，`$OUT` = 输出目录，`$SKILL` = 本 Skill 安装根目录
  （脚本在其 `scripts/` 子目录）。以平台运行说明为准替换为实际路径。
- 预算：64 次模型请求 / 900 秒 / 单响应 16384 token。按下面 5 步线性推进，不回跳。

## 1. 线性五步（每步产出都立即落盘）

### Step 1 — 读题盘点，落骨架
```bash
ls "$IN"; head -c 2000 "$IN/case.json"
python "$SKILL/scripts/result_scaffold.py" scaffold --case "$IN/case.json" --out "$WORK/result.json"
```
- 识别案例类型：C01/C03 类（提供 `publisher-source.xml` 原样副本与
  `source-formulas.xml` 公式节点子集）→ 走完整公式还原；C02 类（确无公式表示、
  逐条预测与可复算原始数据）→ 真实缺失分支，仍完整写全字段并报
  `partial` 或 `insufficient_evidence`，不反推公式、不把未知填 0。
- 骨架此时已含非空 verification 占位（status=not_recomputable + missing 说明），
  后续每步完成一个对象就回填一个对象。公式目录不是线性化答案——目录只是起点。

### Step 2 — 公式对象还原（MathML 优先，三级输入通道）
```bash
# 通道 A：XML 公式节点（主通道；0 节点自动回退 publisher-source.xml）
python "$SKILL/scripts/mathml2latex.py" --convert "$IN/artifacts/source-formulas.xml" \
    --fallback "$IN/artifacts/publisher-source.xml" --out "$WORK/formulas_latex.json"
# 通道 B：没有 XML 时，对 OCR/PDF 提取的纯文本公式行
python "$SKILL/scripts/mathml2latex.py" --text-file "$WORK/formulas_raw.txt" --out "$WORK/formulas_text.json"
```
- 脚本五级容错链保证**任何输入都有非空产物**：标准解析 → DOCTYPE 剥离+命名实体
  （&eta; &Delta; &plusmn; 等）解码 → 正则提取 math 块（含自闭合与未闭合截断块）→
  块级解析失败降级文本提取 → 结构转换为空回退 itertext 文本拼接。降级产物一律标
  `conversion:"partial"` + `ambiguity_notes`，绝不静默丢项。
- **人工校对**（与转换同一响应内完成）：对照上下标层级、括号配对、希腊字母映射
  （ρ vs p）、单位正体（\mathrm）、多字母下标。发现歧义改 `partial` 并写 `ambiguity_notes`。
- 校对完**立即回填 result.json 的 formulas 数组**并覆盖到 `$WORK/result.json`。

### Step 3 — 变量表与推导分步
- **变量表**：每个符号一行 `{symbol, latex, definition, units, range,
  first_defined_at(段落/公式号), provenance}`；`provenance` ∈
  `原文定义 | 上下文推断 | 常识补充`——常识补充必须显式标注，不得混入原文定义。
- **推导分步**：`{step_no, expression, using(假设/近似/边界), depends_on(跨公式引用),
  why_valid, gap}`。读者应能判断每步为什么成立；原文跳步标 `gap:true` 并列入
  uncertainties，不脑补。
- 回填 `variables` 与 `derivations`。

### Step 4 — 数值核验（必做交付）
- 对**每个**可计算公式代入核验：`{formula_id, inputs(带单位与来源), expected(原文值),
  computed(复算值), within_tolerance, status, missing, notes}`。
- 能算的算；缺一项输入就逐项写进 `missing` 并标 `not_recomputable`——verification
  数组整体不许空。数量级不对时先怀疑读数与单位而不是改公式。
- C02 类案例放一条 `{formula_id:"n/a", status:"not_recomputable",
  missing:[…], notes:"该案例无公式表示与可复算数据，按题面保留真实缺失分支"}`。
```bash
python "$SKILL/scripts/formula_check.py" --result "$WORK/result.json" --case "$IN/case.json" --out "$WORK/formula_check.json"
```

### Step 5 — 非空兜底 + 结构校验 + 最终落盘
```bash
cp "$WORK/result.json" "$OUT/result.json"
python "$SKILL/scripts/result_scaffold.py" ensure --result "$OUT/result.json" \
    --case "$IN/case.json" --out "$OUT/result.json"
python "$SKILL/scripts/schema_guard.py" --result "$OUT/result.json" --case "$IN/case.json"
```
- `ensure` 自动修补：result 为空 → 重建结构；verification 空 → 补 not_recomputable
  占位；claims 空 → 补说明性 claim；status 非法 → partial。修补清单会打印，人工复核
  占位是否已替换为真实内容。
- 哪怕后续校验失败，已落盘的部分结果也是可评交付。

## 2. 输出 schema（result.json）

```json
{
  "case_id": "…",
  "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "formulas": [
      {"formula_id": "…", "source_locator": "publisher-source.xml#f2 / Eq.(3) §3.1",
       "latex": "…", "conversion": "full | partial | failed", "ambiguity_notes": null,
       "mathml_raw_present": true}
    ],
    "variables": [
      {"symbol": "…", "latex": "…", "definition": "…", "units": "…", "range": "…",
       "first_defined_at": "…", "provenance": "原文定义 | 上下文推断 | 常识补充"}
    ],
    "derivations": [
      {"step_no": 1, "expression": "…", "using": ["假设/近似"], "depends_on": ["Eq.(1)"],
       "why_valid": "…", "gap": false}
    ],
    "verification": [
      {"formula_id": "…", "inputs": [{"symbol": "…", "value": 0, "units": "…", "source": "原文位置"}],
       "expected": null, "computed": null, "within_tolerance": null, "notes": "…",
       "status": "verified | not_recomputable", "missing": ["缺失输入，逐项列出"]}
    ],
    "coverage": {"formulas_total": 0, "converted_full": 0, "variables_defined": 0,
                 "derivation_steps": 0, "verified": 0, "not_recomputable": false}
  },
  "claims": [{"claim_id": "…", "text": "…", "kind": "reported | inferred",
              "source_id": "…", "location": "…",
              "evidence": [{"paragraph_id": "…", "quote": "…"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [],
                    "human_review": [], "summary": "…"},
  "changelog": [{"step": "…", "change": "…"}]
}
```

## 3. 校验器会抓的错（formula_check.py）

1. `result` 字段为空/非对象 → FAIL（主产物生命线）。
2. conversion=full 但 latex 为空；conversion≠failed 但 latex 为空串 → FAIL。
3. conversion=partial 缺 ambiguity_notes。
4. 变量表 provenance 非法；原文定义的变量缺 first_defined_at。
5. verification 数组为空 → FAIL；expected/computed 只填一个；within_tolerance=true
   但相对误差>5%。
6. claims 为空，或单条 claim 缺 evidence → FAIL。
7. 推导步 gap=true 未列入 uncertainties。
8. coverage.not_recomputable=true 但 verification 有 computed（编造检测）。

## 4. 最小调用示例

见 README.md「最小示意示例」一节（合成输入 + 示意输出，标注为示例，非正式答案）。

## 5. 已知限制

- MathML 转换覆盖常见结构（mfrac/msup/msub/msubsup/msqrt/mroot/mfenced/希腊字母/
  常用运算符）；mtable 大矩阵可能 partial（显式标注歧义，不硬编）。
- 五级容错覆盖 DOCTYPE、命名/数字实体、裸 &/<、自闭合与截断 math 块；极端畸形输入
  走文本拼接通道，产物非空但标 partial 待人工校对。
- 数值核验只在原文给出足够输入时逐项执行；缺输入的逐条登记 missing，不反推未提供的公式。
- 公式图像输入需先经平台 OCR/PDF 工具转为文本或 MathML，再走通道 B。
