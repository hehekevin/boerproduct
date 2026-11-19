# intro-related-work-writer

引言与相关工作写作 Skill。依据给定科研材料撰写论文的 Introduction 与 Related Work，所有事实可回溯到来源，材料不足处显式标注，最终结果嵌入 result.json。

## 核心设计（针对 Harbor 重放环境）

- **线性 5 步流程**：读契约 → 落盘骨架 → 论断-来源映射 → 撰写正文 → 嵌入收尾。每步一个明确写盘动作，适配 64 请求/900 秒/单响应 16384 tokens 的执行预算。
- **骨架先行**：读完 case.json 立即写 result.json 骨架（全契约键 + case_id + status=partial），保证任何中断时刻评分器都能拿到可解析的结构化结果。
- **嵌入优先**：正文全文作为字符串嵌入 result.json 对应字段（不是只写外部文件），同时另存 .md 文件；字段名严格按 output_contract，契约缺失时用默认键并以 `output_contract_fields` 透传。
- **事实纪律**：每条关键论断带来源定位（如 `[S1 §2]`）；研究空白只由已引文献的缺口推出；贡献逐条对齐正文证据；不足处写 `[材料缺口]`，绝不编造。

## 调用方式

平台运行时输入 `/input/case.json` 与 `task.md`，工作目录 `/app/work`，产物写入 `/app/output`。Skill 由 Agent 按以下指令触发，触发后按 SKILL.md 的 5 步流程执行：

- "写引言" / "整理相关工作" / "推导研究空白" / "列贡献并核对证据"

## 最小示例（示意，非正式案例结果）

**输入**（case.json 摘要）：

```json
{
  "case_id": "case-demo-001",
  "task_brief": "为论文撰写引言与相关工作章节",
  "materials": ["paper_main.md", "notes.md"],
  "output_contract": {"introduction": "string", "related_work": "string", "claim_source_map": "array", "status": "string"}
}
```

**输出**（/app/output/result.json，示意）：

```json
{
  "case_id": "case-demo-001",
  "introduction": "……本文针对 X 问题……[S1 §2]",
  "related_work": "……按方法路线分为两组……[S3 §4]",
  "claim_source_map": [
    {"claim": "C1", "text": "基线方法在 Y 上下降 3.2%", "source": "S1 §4 表2", "kind": "直接引用"}
  ],
  "gaps": ["材料缺少实验章节，贡献 CT3 无法对齐证据"],
  "status": "partial"
}
```

同时另存 `/app/output/introduction.md` 与 `/app/output/related_work.md`。

## 适用范围与限制

- 支持中英学术写作、数字编号与作者-年份引用格式；不依赖联网检索，事实仅来自输入材料。
- 目标期刊格式未知时，默认四段式漏斗引言与分组建段相关工作。
- 文献库为空、引用查不到原文、语言切换、材料冲突等异常处置见 SKILL.md「异常处置」表。

## 文件清单

| 文件 | 说明 |
|-|-|
| SKILL.md | Skill 本体，5 步线性流程 |
| resources/claim-map-template.md | 论断-来源映射表格式（可选参考） |
| README.md | 本说明 |
| worklog.md | 开发时间线 |
