---
name: pdf-paper-parse
description: Parse scholarly paper PDFs into a structured, evidence-backed result.json with section tree, paragraphs, figure/table captions, formulas and references, each block located back to page numbers. Use when the task asks to parse, extract, structure, or answer questions from an academic PDF (typically /input/case.json plus a PDF in a Harbor-style runtime). Handles text-layer extraction first and OCR fallback for scanned pages, merges cross-page paragraphs, pairs captions with in-text citations, and honestly marks unreadable content as unknown instead of guessing.
---

# PDF 文献解析（pdf-paper-parse）

把一份科研 PDF 解析成可复核的结构化结果，全部写进 `/app/output/result.json`（评分器主要读它），同时另存外部 JSON/MD 副本。核心纪律：**确定性工作交给工具和脚本，模型只做判断；解析结果必须完整嵌入 result.json；读不出的内容填 `unknown`，绝不编造。**

## 主流程（严格按 1→5 执行，不要分支发散）

### 第 1 步：读契约，抄键名

1. 读 `/input/case.json` 和 `task.md`。
2. 抄下 `case_id` 和 `output_contract` 的**全部键名**（逐个列出，一个不漏）。这是后面所有步骤的字段清单。
3. 找到 PDF 文件路径（材料按题目给的位置，读实际文件，不要凭标签猜内容）。

### 第 2 步：立即写 result.json 骨架

先写 `/app/output/result.json` 骨架，保证即使中途失败也有可评分产物：

```json
{
  "case_id": "<从 case.json 抄>",
  "status": "partial",
  "result": { "<output_contract 的每个键，全部列出，值暂为 null>" },
  "evidence": { "pages": [], "coverage": {} },
  "uncertainty": [],
  "changes": [ { "step": "skeleton", "note": "骨架已建" } ]
}
```

骨架中 `result` 的键必须与 `output_contract` 键名一一对应。之后每完成一块就回填，不要攒到最后一次写。

### 第 3 步：提取全文文本（带页码），确定单一路径

1. 用平台 `pdf-text-tool` 逐页提取文本，**保留页码**，存 `/app/work/pages/`（如 `p001.txt`）。
2. 判定路径（只选一条，不要为多条路径各跑一套）：
   - 前几页文字层字符数正常（如每页 ≥200 字符）→ **文字层路径**，直接用提取文本。
   - 文字层为空或近乎为空（扫描版）→ **OCR 路径**：用 `pdf-render-tool` 渲染页面图像，`ocr-tool` 识别，标注 `source=ocr`。
   - 仅个别页无文字层 → 对那几页单独 OCR，其余用文字层。
3. 剥离页眉页脚：对比多页首尾行，重复出现的行（页码行、期刊名行）标记为 `header_footer`，不混入正文。

### 第 4 步：按 output_contract 填充解析结果

逐个检查第 1 步抄下的键，把内容填进 `result.json` 对应字段，并同步写入外部文件（`/app/output/parse_result.json` 与 `parse_result.md`，便于人工查看）。按 case.json 实际声明的结构组织，常见的有：

- **章节树**：多级标题，每个节点带 `page`。
- **段落列表**：每段带 `page`、阅读顺序序号。
- **图表清单**：编号、题注逐字原文、`page`、正文首次引用位置。
- **公式**：编号与原始字符序列，上下标/希腊字母按提取原文保留。
- **参考文献**：逐条编号、逐字文本、`page`。

执行规则（详见 `parsing-rules.md`）：

- **跨页段落合并**：若某段在页 N 结尾被截断且页 N+1 开头以小写字母/接续词开头、且不属于新标题或列表项，则合并，并在 `changes` 记一条 `merged_pages: [N, N+1]`。
- **题注-引用配对**：题注 "Figure 3: ..." 与正文 "as shown in Figure 3" 按 `figure_id` 配对，各自记页码；找不到引用或找不到题注的，单侧保留并标 `pairing: "unmatched"`。
- **双栏顺序**：先判断是否双栏（同一页文本行按 x 坐标分两簇）。双栏页先左栏后右栏；通栏标题/题注按 y 坐标插到正确位置。
- **不确定处理**：解析不出或模糊的字段**保留键名**，值填 `"unknown"`，并在 `uncertainty` 数组登记 `{field, page, reason}`。不要猜测、不要留空缺键。

### 第 5 步：完整性自检与收尾

1. **字段完整性**：对照第 1 步抄的键清单逐个核对 result.json，一个不缺。
2. **JSON 可解析**：运行 `python -c "import json; json.load(open('/app/output/result.json'))"`（或等价方式）确认合法。
3. **页码抽样**：随机抽 2-3 个区块，回到原文页面文本核对该页码和内容确实存在。
4. **状态收尾**：如实更新 `status`：全部完成 → `success`；有 unknown/部分缺失 → `partial`（并在 uncertainty 说明边界）；工具失败无产出 → `failed_with_cause` 写明原因和可人工接管位置。
5. 在 `changes` 追加一条收尾记录。

## 异常处置

- **加密/打不开的 PDF**：status=`failed_with_cause`，写明"PDF 无法读取"，报告工具报错原文。
- **无文字层且 OCR 工具失败**：保留全部键填 unknown，uncertainty 写 "OCR unavailable, scanned pages unreadable"。
- **output_contract 缺失或格式异常**：按本文件"常见的有"结构填充，status=`partial`，uncertainty 写明 "output_contract not found in case.json"。
- **预算紧张**（接近请求上限）：优先保证 result.json 键完整、每个键有值（哪怕是 unknown），细节精简。

## 资源

- `parsing-rules.md`：跨页合并、题注配对、双栏顺序、页眉剥离的执行细则。
- `result-template.json`：result.json 骨架模板（复制后填 case.json 的实际键名）。
