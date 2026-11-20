# formula-parse（challenge-7c37626c 重做版）— 使用说明

围绕「公式解析与数学推理」的 Skill：从真实出版商 XML / 纯文本公式还原 LaTeX，
建可溯源变量表，推导分步标注假设，并对可计算公式做数值代入核验。
**设计生命线：产物非空**——任何畸形输入都输出可用结果，绝不静默返回空串。

## 文件清单（7 个，≤8 上限）

| 文件 | 作用 |
|---|---|
| `SKILL.md` | Skill 本体：运行契约置顶 + 线性 5 步流程 + 输出 schema |
| `scripts/mathml2latex.py` | MathML→LaTeX 转换与公式目录扫描（五级容错，零依赖，Python 3.8+） |
| `scripts/result_scaffold.py` | result.json 骨架生成 + 非空兜底修补（scaffold / ensure 两模式） |
| `scripts/formula_check.py` | 业务校验器：latex 非空、verification 非空、claims 带证据等 8 类错误 |
| `scripts/schema_guard.py` | 契约守卫：case.json 的 output_contract 全字段结构校验 |
| `README.md` | 本文件 |
| `worklog.md` | 三轮 0 分根因时间线与本次加固点 |

所有脚本零第三方依赖，UTF-8，无平台硬编码路径（SKILL.md 中 `$IN/$WORK/$OUT/$SKILL`
为路径占位符，按运行环境替换）。

## 调用方式（完整五步）

```bash
# Step 1 盘点落骨架
python "$SKILL/scripts/result_scaffold.py" scaffold --case "$IN/case.json" --out "$WORK/result.json"
# Step 2 公式还原（XML 主通道；无 XML 用 --text-file 纯文本通道）
python "$SKILL/scripts/mathml2latex.py" --convert "$IN/artifacts/source-formulas.xml" \
    --fallback "$IN/artifacts/publisher-source.xml" --out "$WORK/formulas_latex.json"
# Step 3-4 变量表/推导/核验由 Agent 按流程回填 result.json（见 SKILL.md）
# Step 5 非空兜底 + 双校验
python "$SKILL/scripts/result_scaffold.py" ensure --result "$OUT/result.json" \
    --case "$IN/case.json" --out "$OUT/result.json"
python "$SKILL/scripts/formula_check.py" --result "$OUT/result.json" --case "$IN/case.json"
python "$SKILL/scripts/schema_guard.py" --result "$OUT/result.json" --case "$IN/case.json"
```

## 输入输出

- **输入**：`case.json` + 材料。C01/C03 类案例给 `artifacts/publisher-source.xml`
  （原样出版商 XML，含 DOCTYPE/命名实体）与 `artifacts/source-formulas.xml`（公式节点子集）；
  C02 类案例无公式表示——走真实缺失分支，照常写全字段并报
  `partial`/`insufficient_evidence`，不反推公式、不补零。
- **输出**：`result.json`，顶层 `case_id / status / result / claims / uncertainties / changelog`；
  `result` 内含 `formulas（LaTeX+conversion） / variables / derivations / verification / coverage`。

## 异常处理与自查

- 五级容错链：标准解析 → DOCTYPE 剥离+实体解码 → 正则提取 math 块（含自闭合/截断）→
  块级失败降级文本提取 → 结构转换为空回退文本拼接。降级产物标 `partial`+`ambiguity_notes`。
- `formula_check.py` 抓 8 类错（含 result 为空、latex 空串、verification 空、claims 缺证据、
  编造检测）；`result_scaffold.py ensure` 在收尾自动修补空缺并打印修补清单。
- 运行失败自查：先看脚本 stdout 的 notes/warnings，再跑 formula_check 看具体 FAIL 项，
  回填后重跑校验。

## 最小示意示例（合成输入，示意输出，非正式案例答案）

输入 `demo.xml`（含命名实体）：

```xml
<article xmlns:m="http://www.w3.org/1998/Math/MathML">
  <para id="p03">The efficiency is &eta; = P_out/P_in &times; 100%:
    <m:math id="f1"><m:mrow><m:mi>&eta;</m:mi><m:mo>=</m:mo>
      <m:mfrac><m:msub><m:mi>P</m:mi><m:mi>out</m:mi></m:msub>
      <m:msub><m:mi>P</m:mi><m:mi>in</m:mi></m:msub></m:mfrac>
    </m:mrow></m:math>
  </para>
</article>
```

调用与示意输出（**示意**，实际以运行结果为准）：

```bash
$ python scripts/mathml2latex.py --convert demo.xml --out fl.json
[mathml2latex] 1 个公式对象（failed=0） → fl.json
$ cat fl.json
{"math_nodes": 1, "items": [
  {"formula_id": "f1", "latex": "\\eta = \\frac{P_{out}}{P_{in}}", "conversion": "full"}]}
```

对应 result.json 中 formulas 数组示意片段：`{"formula_id":"f1", "latex":"\\eta =
\\frac{P_{out}}{P_{in}} \\times 100 \\%", "conversion":"full"}`；变量表、推导与
核验行格式见 SKILL.md §2。

## 适用范围与限制

- 适用：论文 XML（含 MathML）公式还原、纯文本公式规范化、变量溯源、数值复算。
- 限制：mtable 大矩阵可能 partial；公式图像需先经平台 OCR/PDF 工具转文本再走
  `--text-file`；数值核验只在原文给出足够输入时逐项执行，缺输入登记 missing。
