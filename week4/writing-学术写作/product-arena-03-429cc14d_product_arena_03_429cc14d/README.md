# citation-consistency-audit 使用说明

面向学术稿件与文献库的参考文献与引用管理 Skill。适用于 Bohrium 产品赛运行环境，也可在任何支持 Skill 加载的 Agent 环境中使用。

## 一、功能概览

输入一份稿件与一份文献信息源，完成：
1. 引用抽取：逐章节提取正文引用标记与文献条目，全部带可回溯定位锚点。
2. 一致性校验：构建引用-条目双向映射矩阵，产出孤儿引用、未引用条目、编号问题三个清单。
3. 去重归并：按 DOI/标识符/作者+年份+题名等判据合并重复条目，每个合并决策可解释、可回溯。
4. 编号重排：顺序编码制下按首次出现顺序重排，同步图表注与附录交叉引用。
5. 元数据分级：每条目标注完整/可疑/缺失三级，DOI 只做格式与材料内交叉核验，核实不了的诚实标注。
6. 格式规范化：按 GB/T 7714-2015、APA 7 或 BibTeX 逐字段转换，保留 DOI、卷期页、类型标识。
7. 结构化交付：result.json 含全部核对结果与改动记录，修订稿可继续编辑。

## 二、文件清单

| 文件 | 作用 |
|---|---|
| SKILL.md | Skill 本体，含完整工作流程、输入输出约定、异常分支、自检清单 |
| references/workflow-checklists.md | 各阶段核查清单与 16 类异常分支详表 |
| references/format-mapping.md | BibTeX/RIS/CNKI/EndNote 到三种目标格式的逐字段映射 |
| references/dedup-rules.md | 去重合并判据（J1 到 J7）、禁止合并条款、对账公式 |
| references/result-json-template.md | result.json 字段模板与填写规范 |
| references/common-errors.md | 25 条常见错误清单与预防方法 |

无外部依赖，无需安装脚本，全部为文本规则文件。运行环境为 Harbor 契约描述的 DeepSeek Harness：输入 /input/case.json 与 task.md，工作目录 /app/work，产物写 /app/output。

## 三、调用步骤

1. 将 SKILL.md 与 references/ 目录一并安装为 Skill（平台侧安装到 /skills/weekly-skill）。
2. 向 Agent 提交案例：Agent 读取 /input/case.json 与 task.md，自动进入 SKILL.md 阶段 0。
3. Agent 按六阶段流水线执行（0 读契约、1 抽取、2 去重、3 双向校验、4 元数据分级、5 格式化、6 写出与自检），正常 8 到 14 次模型请求完成。
4. 从 /app/output 取回 result.json、修订稿、最终文献表、audit_report.md。

用户无需手动干预；若结果含 manual_review_list，按清单逐项人工确认即可。

## 四、最小调用示例（示意输出，非正式案例结果）

输入示例（/app/work/main.md）：

```
近年图神经网络在材料性质预测中表现突出[1,2]。
Wang 等提出的 CGCNN 是该方向代表性方法[3]。
【参考文献】
[1] Zhou G. et al. Nature, 2021.
[2] Zhou G. et al. Nature, 2021. (同一文献重复导出)
[4] 李明. 材料导报, 2020. (编号跳过 3)
```

调用方式：加载 Skill 后向 Agent 提交"请按 Skill 流程完成引用一致性整理，目标格式 GB/T 7714-2015"。

示意输出（节选自 result.json，仅演示格式）：

```json
{
  "case_id": "demo-case-001",
  "status": "complete",
  "counts": {"citation_points": 2, "unique_markers": 2, "reference_entries_raw": 3, "reference_entries_final": 2, "orphan_citations": 0, "uncited_entries": 0, "numbering_issues": 1, "merged_groups": 1},
  "dedup_records": [{"kept": "zhou2021nature", "merged": "zhou2021nature_dup", "criterion": "J1", "risk": "low", "evidence": "DOI 相同"}],
  "numbering_issues": [{"type": "gap", "detail": "正文首现编号为 [1,2,3]，列表编号 [1][2][4]，缺 3", "anchor": "main.md 参考文献 行4"}],
  "change_records": [{"anchor": "main.md 参考文献 行4", "before": "[4] 李明. 材料导报, 2020.", "after": "[3] 李明. 材料导报, 2020.", "basis": "编号按首现顺序重排"}]
}
```

以上数值与条目均为演示编造，不代表任何正式案例的运行结果。

## 五、适用范围与限制

- 适用：Markdown、LaTeX、纯文本、PDF（经平台 pdf-text-tool 提取）稿件；.bib/.ris/CSV 或稿件内嵌参考文献列表。
- 限制：不做正文润色与翻译；不自行补充新文献来源；不假设联网，DOI 只做格式与材料内核验，联网反查仅在环境具备工具时进行；超长稿件按分块规则处理，预算耗尽时输出 partial 并明确标注未完成范围。
- 已知边界：扫描件 OCR 质量差时上标引用可能漏抽，会在 uncertainty 中说明。

## 六、失败处理与自查

- 运行失败或部分完成时 result.json 的 status 与 limits 字段会如实说明。
- 人工自查方法：打开 audit_report.md 查看双向矩阵与三个清单；核对 result.json 的 counts 能否对账（去重后条目数 = 原始条目数 - 合并被并数）；抽查任意 change_record 的锚点能否在原稿定位。
- 维护信息：规则文件均为独立文本，可按需修订 format-mapping.md 扩展目标格式、修订 dedup-rules.md 调整合并阈值。
