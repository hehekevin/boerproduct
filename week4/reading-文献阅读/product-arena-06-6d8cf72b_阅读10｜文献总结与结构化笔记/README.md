# structured-paper-notes：文献总结与结构化笔记 Skill

## 一、这是什么

一个可被 Agent 加载的 Skill。输入一篇科研论文（PDF 或文本），输出一份固定字段的结构化阅读笔记与平台要求的 result.json。核心保证：每条事实性结论都带证据锚点（页码、章节、段落、图表编号），可回链原文核对；阅读者的评价与论文事实分栏；未报告、无法判断、材料冲突项显式列出。

## 二、适用条件

- 输入为单篇科研论文，PDF（含文字层）或纯文本。
- 需要产出可复核、可检索、可跨论文对比的阅读笔记。
- 论文超过 40 页、为扫描件、为图片图表、为非中文时仍可运行，走对应异常分支，状态如实降级。
- 加密或无权限文档、完全无文字层且无 OCR 工具时会失败或部分完成，不会伪造内容。

## 三、调用方式

平台自动加载时：Agent 读取 /input/case.json 与 task.md，按 SKILL.md 流程执行，产物写入 /app/output/。

用户手动调用时：

1. 将论文文件放入工作目录。
2. 对 Agent 说："给这篇论文做结构化笔记"或"读这篇论文并给出依据"。
3. 等待输出 notes/case-{case_id}.md 与 result.json。
4. 按 self-check-list.md 抽查锚点即可验收。

## 四、输入输出

| 方向 | 内容 |
|---|---|
| 输入 | 论文文件（PDF/文本）、case.json（含 case_id 与 output_contract 字段）、task.md |
| 中间产物 | /app/work/plan.md、skeleton.md（章节骨架）、excerpts.md（定位摘录） |
| 输出 | /app/output/notes/case-{case_id}.md、/app/output/result.json |

result.json 必含：case_id、status（成功/部分完成/无法判断/失败）、笔记六类字段、anchors 锚点清单、number_checks 数字核对记录、unreported/uncertain/conflicts 三类清单、output_contract_fields、change_log。

## 五、工作流程概览

1. 输入识别：读 case.json 抄下 output_contract 字段清单；判断论文类型与篇幅。
2. 章节对齐：提取章节标题与页码范围，形成骨架，笔记按论文自身章节顺序组织。
3. 定位摘录：逐类字段（研究问题、数据、方法、结果、局限、结论）先定位后摘录，先写锚点再写内容。
4. 字段填写：按固定模板填写，事实栏与评价栏分栏；图表数字只从文字层逐字抄录。
5. 数字核对：摘要数字与正文表格逐一比对，结果标 [数字已核对] / [数字冲突] / [数字无表格来源]。
6. 未报告清单：显式列出未报告、无法判断、材料冲突三类条目。
7. 输出自检：写 result.json，跑 self-check-list.md 全部 22 项，status 如实标注。

## 六、异常处理

| 情况 | 处置 |
|---|---|
| 扫描件无文字层 | 尝试 OCR；无工具则输出元数据级笔记，status=部分完成 |
| 图表为图片 | 标 [图表数字不可读]，改用正文文字描述并附正文锚点 |
| 超长论文（40 页以上） | 按章节分批处理并即时落盘，最后合并 |
| 双栏错序 | 启发式重排，存疑处标 [?] 并入无法判断清单 |
| 非中文论文 | 术语保留原文加中文对照，摘录注明"译" |
| 加密或权限受限 | status=失败，写明原因，不伪造 |
| 领域陌生 | 先提取术语表再摘录，不做领域外推 |
| 材料缺失 | 列缺失清单，能做部分照常输出，status=部分完成 |

## 七、最小调用示例（示意输出，非正式案例结果）

输入示意：

```
case.json: { "case_id": "demo-001", "paper": "demo-paper.pdf",
             "output_contract": { "fields": ["summary", "key_findings", "status"] } }
```

调用：给 demo-paper.pdf 做结构化笔记。

示意输出（节选，仅演示格式，内容为虚构示例）：

```
notes/case-demo-001.md（节选）

## 1 研究问题
| 论文事实 | 锚点 | 阅读者评价 |
| 探究预训练语言模型在低资源语言上的迁移上限 | p.1 §Abstract ¶1 | 动机成立，但未界定"低资源"阈值 |
| 声称贡献：提出轻量适配器迁移方法 | p.1 §Abstract ¶2 | 方法与既有工作关系需查引用 |

## 4 主要发现（节选）
| 论文事实 | 锚点 | 阅读者评价 |
| 平均准确率 82.4 | p.6 §5.1 ¶2 Table 2 | 提升幅度随语言家族差异大 |

### 数字核对记录
| 指标 | 摘要值 | 表格值 | 结果 |
| 平均准确率 | 82.4 (p.1 §Abstract ¶2) | 82.4 (p.6 Table 2) | [数字已核对] |

## 8 未报告与无法判断清单
- 未报告：数据划分比例，论文未提及（§4 Data 范围内未出现）。
- 无法判断：Fig.3 曲线具体数值，图表为图片 [图表数字不可读]。
```

result.json 示意（节选，仅演示格式）：

```json
{
  "case_id": "demo-001",
  "status": "成功",
  "note_fields": {
    "research_question": "低资源语言迁移上限与轻量适配方法",
    "key_findings": ["平均准确率 82.4 (p.6 §5.1 Table 2)"]
  },
  "anchors": [
    { "claim": "平均准确率 82.4", "page": "p.6", "section": "5.1 Results",
      "paragraph": "¶2", "figure_table": "Table 2" }
  ],
  "number_checks": [
    { "metric": "平均准确率", "abstract_value": "82.4", "body_value": "82.4", "result": "已核对" }
  ],
  "unreported": ["数据划分比例"],
  "uncertain": ["Fig.3 曲线数值不可读"],
  "conflicts": [],
  "output_contract_fields": {
    "summary": "见 note_fields",
    "key_findings": ["平均准确率 82.4 (p.6 §5.1 Table 2)"],
    "status": "成功"
  }
}
```

再次强调：以上内容为示意输出，仅说明格式，非正式案例结果。

## 八、多篇合并对比

对多篇论文分别运行本 Skill 后，按 templates/compare-template.md 合并：字段为行、论文为列，单元格沿用原锚点，未报告项照抄，指标口径不同的数字不直接比较，写入横向观察。

## 九、依赖与文件清单

- 无第三方脚本依赖，纯提示词与模板驱动，任何能读文件写文件的 Agent 均可执行。
- 文件清单：
  - SKILL.md：Skill 本体与流程定义。
  - templates/note-template.md：结构化笔记模板（事实/评价双栏）。
  - templates/result-json-template.json：result.json 输出模板。
  - templates/compare-template.md：多篇合并对比模板。
  - references/evidence-anchor-spec.md：证据锚点格式规范。
  - references/field-dictionary.md：字段字典与人工/机器判定边界。
  - references/self-check-list.md：22 项自检清单。
- 资源规模：7 个 UTF-8 文本文件，远小于 50 文件、500KB 单文件、2MB 总量限制。

## 十、限制与维护

- OCR 依赖运行环境，环境无 OCR 时扫描件只能部分完成。
- 锚点段落计数依赖文字抽取质量，双栏复杂版面可能存疑（已标 [?]）。
- 本 Skill 不做全文翻译、不生成综述，聚焦单篇结构化笔记；综述场景建议先逐篇出笔记再合并对比。
- 维护信息：字段与模板如需扩展，保持字段名稳定并在 field-dictionary.md 同步登记。
