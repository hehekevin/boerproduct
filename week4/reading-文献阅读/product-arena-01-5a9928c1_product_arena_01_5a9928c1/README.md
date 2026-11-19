# 学术文献翻译 Skill 使用说明

本 Skill 面向科研论文的中英翻译任务，输出段落级双语对照、锁定术语表、核验报告和结构化结果。设计目标是术语稳、段落全、关系准、可核验。

## 1. 文件清单

| 路径 | 作用 |
|---|---|
| `SKILL.md` | Skill 本体，含完整工作流程、异常分支与自检清单 |
| `resources/terminology-template.csv` | 术语表模板，锁定译名与禁用变体 |
| `resources/segment-map-template.csv` | 段落切分对照模板，段号与原文定位 |
| `resources/result-template.json` | result.json 输出模板 |
| `resources/checklist.md` | 译文核验清单与人工确认清单 |
| `scripts/verify_alignment.py` | 核验脚本，纯 Python 标准库，无第三方依赖 |
| `README.md` | 本说明 |
| `worklog.md` | 开发过程记录 |

## 2. 环境要求

- Python 3.6 及以上，无任何第三方依赖。
- 运行平台需提供 PDF 文字提取与 OCR 能力（如 pdf-text-tool、ocr-tool）；输入为纯文本时不需要。

## 3. 调用步骤

1. 平台将 Skill 安装到 Agent 后，把案例材料放入 `/input/case.json` 与 `task.md`。
2. Agent 按 SKILL.md 第 4 节流程执行：输入识别、文本获取、分段编号、术语表锁定、分批翻译、装配、脚本核验、结果输出。
3. 中间产物在 `/app/work`，最终产物写入 `/app/output`，包括 `result.json`、`bilingual.md`、`glossary.csv`、`verification.md`。

## 4. 核验脚本用法

```bash
# 完整核验（分段对齐、术语一致性、数字单位、占位符残留、result.json 字段）
python scripts/verify_alignment.py \
  --bilingual /app/output/bilingual.md \
  --glossary /app/work/glossary.csv \
  --result /app/output/result.json

# 单项核验
python scripts/verify_alignment.py --bilingual OUT/bilingual.md --mode placeholders
python scripts/verify_alignment.py --bilingual OUT/bilingual.md --mode numbers

# JSON 格式报告
python scripts/verify_alignment.py --bilingual OUT/bilingual.md --json
```

退出码 0 表示全部通过，1 表示存在未通过项，需按报告修复后重跑。

## 5. 双语对照文件格式约定

```
### P001 | p1c1p1 | title
SRC: 原文...
TGT: 译文...
NOTE: 译法依据
```

- 首列为单元号：正文段落 P001 起，图注 F01、表格 T01、公式 E01、参考文献 R001。
- 第二列为原文定位：页码 p、栏 c、段序 n，跨页段使用区间如 `p2c2p6-p3c1p1`。
- 第三列为单元类型：title、abstract、section、paragraph、figure_caption、table、equation、reference。
- 译文中的标注：`[!UNCLEAR: 原因]` 表示译不准；`[!UNTRANSLATED: 原因]` 表示未译；`[指代: xxx]` 表示补出的指代对象。
- 占位符：翻译期间公式、文献引用、图表编号、数字加单位以 `⟪...⟫` 保护，译文输出后原样回填。

## 6. 术语表格式

CSV 列：`term_en,term_zh,variant,category,first_location,status,note`。

- `status` 为 locked 表示全篇强制使用 `term_zh`；为 pending 表示无把握，译文保留英文并登记不确定性。
- `variant` 登记禁用的备选译法，核验脚本会扫描译文是否出现变体。
- 术语表可直接复用于同学科其他文献，新文献先增量更新再翻译。

## 7. 最小调用示例

以下为示意输出，非正式案例结果。

输入 `case.json`（节选）：

```json
{
  "case_id": "demo-case-001",
  "material": "demo.pdf",
  "output_contract": {"required_fields": ["case_id", "status", "outputs"]}
}
```

调用后 `/app/output/bilingual.md`（节选）：

```
### P002 | p1c1p2 | abstract
SRC: We propose a novel framework that improves accuracy by 12.5 percent on three benchmark datasets using gradient descent.
TGT: 我们提出一个新框架，使用梯度下降在三个基准数据集上将准确率提升 12.5 percent。
NOTE: 数字与单位按占位符回填；gradient descent 按锁定术语表译为梯度下降。
```

调用后 `/app/output/glossary.csv`（节选）：

```
term_en,term_zh,variant,category,first_location,status,note
gradient descent,梯度下降,梯度下降法,method,p2c1p1,locked,全文统一
```

调用后 `result.json`（节选，完整结构见 `resources/result-template.json`）：

```json
{
  "case_id": "demo-case-001",
  "status": "success",
  "stats": {"total_units": 86, "translated_units": 86, "flagged_units": 2}
}
```

核验输出：

```
双语核验报告
单元总数: 3
[alignment] 通过
[terminology] 通过
[numbers] 通过
[placeholders] 未通过, 1 项问题: 占位符残留 段 F01: ⟪E01⟫
```

## 8. 适用与限制

- 适用：单篇 PDF 或文本论文的全文或指定区间翻译，英文为主。
- 限制：扫描件质量极差时部分段落只能标记未译；图片公式不猜测内容，保留位置；译文质量依赖底层模型，本 Skill 通过术语锁定与脚本核验保障一致性与可核验性，不保证风格完美。
- 维护：术语表按学科沉淀后可直接复用；核验脚本可按需增加检查项，修改时同步更新 SKILL.md 与本说明。

## 9. 失败处理

- 材料不可读：`result.json` 的 `status` 写 failed，`status_reason` 说明原因。
- 部分完成：`status` 写 partial，`status_reason` 列出未完成单元号与原因。
- 核验未通过且无法修复：如实登记到 `verification.issues` 与 `uncertainty`，不隐藏。
