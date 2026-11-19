# pdf-paper-parse 使用说明

本 Skill 把科研论文 PDF 解析为可复核的结构化 `result.json`（章节树、段落、图表题注、公式、参考文献，均带页码定位），适用于 Harbor 平台第 08 题「文献文档解析」的 3 个固定案例运行。

## 调用方式

Agent 加载本 Skill 后，在运行时按 `SKILL.md` 的 5 步线性流程执行：

1. 读 `/input/case.json`，抄下 `case_id` 与 `output_contract` 全部键名。
2. 立即写 `/app/output/result.json` 骨架（全键 + case_id + status=partial）。
3. 用平台 `pdf-text-tool` 逐页提取文本（带页码）；无文字层的页用 `pdf-render-tool` + `ocr-tool` 识别。
4. 按 output_contract 填充章节/段落/图表/公式/参考文献字段，全部写入 result.json。
5. 自检（字段完整性、JSON 可解析、页码抽样），如实写 status。

## 输入 / 输出

- 输入：`/input/case.json`（任务契约）、task.md、论文 PDF。
- 输出：
  - `/app/output/result.json` — 主结果（评分器主要读取；解析结果完整内嵌）。
  - `/app/output/parse_result.json` / `parse_result.md` — 同内容的外部副本，便于人工查看。

## 最小示意示例（示意输出，非正式案例结果）

输入 `/input/case.json`：

```json
{
  "case_id": "demo-001",
  "output_contract": {
    "section_tree": "章节层级树，每节点含 page",
    "paragraphs": "段落列表，每段含 page",
    "figures_tables": "图表题注清单",
    "references": "参考文献清单"
  }
}
```

示意输出（节选，`/app/output/result.json`）：

```json
{
  "case_id": "demo-001",
  "status": "success",
  "result": {
    "section_tree": [
      {"title": "1 Introduction", "level": 1, "page": 1}
    ],
    "paragraphs": [
      {"order": 1, "page": 1, "text": "We propose ..."}
    ],
    "figures_tables": [
      {"figure_id": "Figure 1", "caption": "Figure 1: Overview of ...", "page": 2, "cited_at": {"page": 1, "snippet": "as shown in Figure 1"}}
    ],
    "references": [
      {"index": 1, "text": "A. Author, \"Title\", ..., 2020.", "page": 8}
    ]
  },
  "evidence": {"pages": [1, 2, 8]},
  "uncertainty": [],
  "changes": [{"step": "final", "note": "全部字段填充完成"}]
}
```

## 适用范围与限制

- 适用：文字层 PDF、扫描版 PDF（OCR 兜底）、单栏与双栏论文。
- 限制：加密 PDF 无法处理；复杂表格仅按结构元素识别行列归属，不解释科学含义；公式按原始字符序列保留，不重建 LaTeX。
- 失败处理：见 SKILL.md「异常处置」；无法解析的字段保留键名填 `unknown` 并登记 uncertainty，不编造。

## 文件清单

| 文件 | 说明 |
|---|---|
| SKILL.md | 主流程（5 步线性 + 异常处置） |
| parsing-rules.md | 跨页合并 / 题注配对 / 双栏顺序 / 页眉剥离细则 |
| result-template.json | result.json 骨架模板 |
| README.md | 本说明 |
| worklog.md | 设计与变更时间线 |
