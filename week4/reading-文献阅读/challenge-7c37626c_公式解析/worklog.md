# worklog — formula-parse 重做（challenge-7c37626c）

## 1. 三轮 0 分根因时间线

| Attempt | 结果 | 根因 |
|---|---|---|
| 71333 | 0 分 | mathml2latex.py 用标准 XML 解析器直接读真实出版商 XML：DOCTYPE 声明 + 命名实体（&eta; &Delta; &plusmn;）导致解析抛异常 → 全部公式转换失败 → 转换产物为空 → grader 无解可判，整卷 0 分。 |
| 72098 | 0 分 | 同一解析根因未修复（提交未包含容错改动），相同输入仍然解析失败、产物为空。 |
| 72479 | 排队中 | 同事定位根因后加了三级容错（内置实体占位 + html.unescape 解命名/数字实体 + DOCTYPE 剥离 + 正则回退提取 math 块 + --fallback 备用文件），预期摆脱空产物；本重做在其基础上进一步加固（见下）。 |

共同根因一句话：**转换链条上任何一环对畸形输入直接失败且不降级，导致 result 字段空，
grader 无从评起**。教训：产物非空是生命线，每个环节必须有"输入畸形也输出可用结果"的兜底。

## 2. 本次加固点（相对已排队版本）

1. **五级容错链**（原三级 → 五级）：标准解析 → DOCTYPE 剥离+实体解码 → 正则提取
   math 块 → **块级解析失败降级为剥标签文本提取**（截断/畸形块也有产物）→
   **结构转换为空回退 itertext 文本拼接**（xml2latex 内部空结果也有产物）。
   降级一律标 `conversion:"partial"` + `ambiguity_notes`，不静默。
2. **正则回退支持命名空间前缀**：`<m:math>`/`<mathml:math>` 均可提取（原正则只匹配
   `<math`，截断 XML 回退路径下漏抓全部块——本地测试 case4 抓到并修复）。
3. **未闭合尾块提取**：截断文件的最后一个 `<math ...>` 开标签也能定位（取至文件尾），
   修复了"截断 XML 只产出 1/2 个公式"的漏抓。
4. **纯文本公式通道** `--text-file`：无 XML 输入（OCR/PDF 提取文本）时规范化为
   LaTeX（希腊字母名、Unicode 运算符、多字符上下标加花括号），产物非空。
5. **result_scaffold.py（新增）**：
   - `scaffold`：Stage 0 立即生成骨架 result.json（含 output_contract 全字段），
     先落盘再逐段回填——中途崩溃也有可评交付；
   - `ensure`：收尾兜底修补——result 空/非对象重建、verification 空补
     `not_recomputable`+missing 占位、claims 空补说明性 claim、status 非法落回
     partial、坏 JSON 整体重建。修补只补结构不造内容。
6. **formula_check.py 加两道检查**：result 字段空/非对象 FAIL；conversion≠failed 但
   latex 为空串 FAIL（生命线显式入法）；claims 缺 evidence FAIL。
7. **SKILL.md 重写**（148 行 ≤250）：运行契约置顶（产物非空/status 诚实四级/不编造/
   路径占位符化不硬编码平台路径）+ 线性 5 步（盘点落骨架 → 公式还原 → 变量推导 →
   核验 → 兜底校验落盘），每步完成即回填落盘。

## 3. 本地五类输入测试结果（tests/ 目录，全部非空）

| 输入 | 场景 | 结果 |
|---|---|---|
| case1-clean.xml | 干净 MathML | f1 `full`：`η = \frac{P_{m a x}}{P_{\mathrm{in}}} \times 100 %` |
| case2-doctype-entities.xml | DOCTYPE+命名实体（&Delta; &rho; &plusmn;） | f2 `full`：`Δ P = ρ g h` |
| case3-bad-entities.xml | 未知实体 &weirdent; + 裸 & + 裸 `<`（P < 0.05） | f3 `full`：`G = \frac{a + b}{2}` |
| case4-truncated.xml | 畸形截断 XML（第二个 math 块未闭合） | f4 `full` + math-1 `partial`（文本降级 `c d x d t`），2/2 块非空 |
| case5-plaintext.txt | 纯文本公式 | text-1 `partial`：`\eta = P_{out} / P_{in} \cdot 100 % …` |

链路测试：scaffold 生成骨架 PASS；清空 result/claims/status 后 ensure 自动修补 4 处；
坏 JSON ensure 重建 13 处；formula_check 骨架 PASS；schema_guard PASS；
负向用例（full+空 latex）正确 FAIL 2 处。

## 4. 遗留与说明

- mtable 大矩阵转换仍 partial（显式标注，不硬编）；文本通道产物保守，需 Stage 2 人工校对。
- 未提交平台（按主控要求由主控统一提交）；本地测试产物在 tests/（不属于提交资源）。
