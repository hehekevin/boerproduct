# claim-audit — 使用与方法说明

文献证据溯源与事实核验 Skill：把待核科研论断拆成可独立判定的子判断，
逐条给出四级判定，并把每条判定钉在原文的逐字证据上。对应题目
`challenge-e5e3be30`（文献阅读 · 证据溯源与事实核查）。

## 1. 适用范围

- 输入是 `/input/case.json`（带段落编号的论文材料）与 `/input/claims-to-verify.json`
  （待核论断清单，论断是提问不是权威事实）的场景。
- 聚焦"论断 → 证据片段 → 原文定位 → 支持度判定 → 判定理由"这一条链；
  不联网核对文献元数据，材料外的转引正确性超出边界（按 insufficient_evidence 报告）。

## 2. 调用方式

Agent 加载本 Skill 后，按 `SKILL.md` 第 1 节的线性五步执行；用户侧只需说
"帮我核验这段话里的论断"并给出材料与论断文件。脚本依赖仅为 Python 3.8+ 标准库，
无第三方安装项。

```bash
python /skills/weekly-skill/scripts/claim_check.py --result /app/work/result.json \
  --case /input/case.json --claims /input/claims-to-verify.json --out /app/output/claim_check.json
python /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json --case /input/case.json
```

## 3. 输入 / 输出字段

输入（字段名以实际文件为准）：
- `case.paragraphs[]`：`{paragraph_id, text}`，用于摘录核验与定位。
- `claims[]`（或 `items[]`）：`{claim_id, text}` 待核论断。

输出 `/app/output/result.json`（顶层五字段契约）：
- `case_id`、`status`（answered/partial/insufficient_evidence/input_error）、
- `result.verdicts[]`：逐条论断判定，含 `subclaims[]`（fact/comparison/causal/scope 四类子判断、
  四级判定、逐字证据、判定理由）与 `qualified_conclusion`；
- `claims[]`：关键核查结论汇总（kind + evidence + source_id + location）；
- `uncertainties`：`uncovered`（未覆盖论断逐条登记：claim_id + 原因）、`unreported`、
  `unverifiable`、`conflicts`（冲突双方原话并列）、`human_review`、`summary`。

## 4. 四级判定定义

| 判定 | 定义 | 反例（不要这样判） |
|-|-|-|
| supported | 原文明确陈述该子判断，数值/比较/方向全部吻合 | 段落主题相关就判 supported |
| partially_supported | 方向/结论支持，但数值、条件或范围不完全吻合 | 原文只证部分样本却判全称 supported |
| contradicted | 原文明确陈述相反结果，且有可定位的反向证据引文 | 只因"没找到"就判 contradicted |
| insufficient_evidence | 原文未报告，或仅主题相关而未陈述论断本身 | 外推未被原文提及 ≠ 被实验证伪 |

复合论断的总体判定 = 子判断的最弱一致结论；冲突来源双方引文并列，判定加限定词。

## 5. 关键方法：摘录防改写核验

每条 evidence 的 `quote` 经空白归一化（删除全部空白字符）后，必须是其所在段落
原文的子串。脚本 `claim_check.py` 对所有 supported/partially_supported/contradicted
证据执行该匹配：改写、默写、缩写、跨段拼贴都会在核验中暴露并要求换成原文字符。
空白差异（换行、连续空格）允许，措辞差异不允许。

## 6. 最小调用示例（示意输出，非正式答案）

输入 `examples/example-input.json`（三段合成材料）+ `examples/example-claims.json`（三条论断）：

```json
{"claim_id": "cl-1", "text": "该处理使疲劳寿命提升 12.4%，且提升显著。"}
```

示意输出（节选自 `examples/example-result.json`）：

```json
{"claim_id": "cl-1", "verdict": "supported",
 "subclaims": [
   {"type": "comparison", "verdict": "supported",
    "evidence": [{"paragraph_id": "p02", "quote": "a 12.4% higher fatigue life than the control"}],
    "rationale": "数值与比较方向逐字吻合"}]}
```

自测命令：
```bash
python scripts/claim_check.py --result examples/example-result.json \
  --case examples/example-input.json --claims examples/example-claims.json --out /tmp/x.json
python scripts/schema_guard.py --result examples/example-result.json
```

## 7. 异常处理与自查

- 材料缺失 / 论断清单为空 → 整体 `input_error`，uncertainties 说明缺失项。
- 部分论断无法解析或材料不含对应主题 → 该条登记 `uncertainties.uncovered`，其余照常交付（`partial`）。
- PDF 无文本层 / 段落表解析不出 → 摘录核验自动降级为 WARNING，但需人工核对，`human_review` 登记。
- 自查三问：每条论断都有归属吗？每条摘录能在原文原位找到吗？不确定项都进 uncertainties 了吗？

## 8. 已知限制与维护

- 判定质量依赖段落文本完整性；跨页断裂、表格文字化程度低时定位精度下降。
- OCR 字符噪声会造成摘录匹配失败——按校验提示以原文字符修正摘录即可。
- 脚本三级容错（L1 输入缺失降级 / L2 解析异常捕获 / L3 业务规则 FAIL），本地双测通过。
