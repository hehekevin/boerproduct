# result.json 输出模板

运行时必须先读取 case.json 中的 output_contract 字段约定，把其要求的全部字段纳入 result.json，并保证 case_id 正确。以下模板为默认契约（case.json 未给出 output_contract 时使用）。

## 模板结构

```json
{
  "case_id": "<从 case.json 读取的实际 ID>",
  "task_type": "citation_consistency_audit",
  "status": "complete | partial | failed",
  "target_format": "gbt7714 | apa7 | bibtex | keep_original",
  "deliverables": {
    "manuscript_revised": "<文件名>",
    "references_final": "<文件名>",
    "audit_report": "audit_report.md"
  },
  "counts": {
    "citation_points": 0,
    "unique_markers": 0,
    "reference_entries_raw": 0,
    "reference_entries_final": 0,
    "orphan_citations": 0,
    "uncited_entries": 0,
    "numbering_issues": 0,
    "merged_groups": 0
  },
  "citation_matrix_summary": {
    "matrix_file": "audit_report.md#双向映射矩阵",
    "matched_pairs": 0,
    "unresolved_markers": []
  },
  "orphan_citations": [
    {"marker": "[9]", "anchor": "main.md 第3章 段2 行14", "sentence": "<原文片段>"}
  ],
  "uncited_entries": [
    {"key": "li2019survey", "anchor": "refs.bib 条目12", "suggestion": "delete_or_cite"}
  ],
  "numbering_issues": [
    {"type": "order_mismatch | gap | duplicate_id | style_mixed", "detail": "<说明>", "anchor": "<定位>"}
  ],
  "dedup_records": [
    {"kept": "k1", "merged": "k2", "criterion": "J1", "risk": "low", "evidence": "<原始串或差异说明>"}
  ],
  "metadata_grades": [
    {"key": "k1", "grade": "complete | suspicious | missing", "reason": "<原因>", "verified": "verified_by_material | verified_by_doi_lookup | unverified"}
  ],
  "manual_review_list": [
    {"item": "<待确认事项>", "anchor": "<定位>", "reason": "<为什么需要人工>"}
  ],
  "change_records": [
    {"anchor": "<文件+章节+段落+行>", "before": "<原文>", "after": "<改后>", "basis": "<依据>"}
  ],
  "sources": [
    {"claim_or_field": "<事实点>", "anchor": "<文件+章节+段落+行或原文片段>", "excerpt": "<逐字摘录>"}
  ],
  "uncertainty": ["<不确定项，如目标格式推断依据、DOI 存在性未核实>"],
  "limits": ["<未完成范围，partial 或 failed 时必填>"],
  "self_check": {
    "json_valid": true,
    "contract_fields_complete": true,
    "all_changes_anchored": true,
    "no_fabricated_entries": true,
    "status_honest": true
  }
}
```

## 填写规范

1. case_id 必须来自 case.json 原值，不得改写。
2. status 判定：全链路（抽取、去重、校验、分级、格式化、修订稿）完成且产物齐全为 complete；任一阶段因预算或材料受限未完成为 partial 并填 limits；稿件与文献库均无法读取为 failed，此时 result.json 也要写（counts 可为 0，limits 写明失败原因）。
3. 所有 anchor 三层结构：文件名 + 章节或位置 + 行号或段落序号，附原文片段（excerpt 字段逐字摘录，不加改写）。
4. verified 只允许三个值；无证据时一律 unverified，禁止填 verified_by_doi_lookup。
5. 若 case.json 的 output_contract 还要求本模板之外的字段，逐字段补充；若 output_contract 与本模板字段名不同，以 output_contract 命名为准，内容规范沿用本文。
6. 数值型字段一律填实际统计值，不允许留空或写"约"。
