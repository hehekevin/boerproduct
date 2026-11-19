# result.json 输出模板

## 1. 字段优先级

1. case.json 的 `output_contract` 字段：必须全部出现，名称与结构照抄契约。
2. 本模板的基础字段：output_contract 未覆盖时照此输出。
3. 两者冲突时以 output_contract 为准，多余信息保留在本模板字段中。

## 2. 基础模板

```json
{
  "case_id": "{case.json 中的 case_id，原样复制}",
  "status": "success",
  "status_reason": "全部 N 条断言通过两阶段校验并输出",
  "output_contract": {"contract_fields_used": ["字段名列表，或 null 若 case.json 未提供"]},
  "source_paper": {
    "title": "",
    "authors": [],
    "year": "",
    "doi_or_identifier": "",
    "page_basis": "paper",
    "material_type": "pdf|text|inline"
  },
  "assertions": [
    {
      "id": "NP001",
      "statement": "断言全文，保留 hedging 与限定词",
      "subject": "",
      "predicate": "npex:increases",
      "object": "",
      "qualifiers": ["in mice"],
      "assertion_strength": "definitive",
      "hedging_markers": ["none"],
      "numeric_items": ["p = 0.01", "40%"],
      "evidence_quote": "逐字引文",
      "evidence_location": {
        "page": "4",
        "page_basis": "paper",
        "section": "3.2 Results",
        "paragraph": 2,
        "sentence": 1,
        "figure": ""
      },
      "evidence_type": "direct",
      "inference_note": "",
      "verification": "pass",
      "np_uri": "https://w3id.org/np/LOCAL/{case_id}/NP001"
    }
  ],
  "outputs": {
    "trig_file": "nanopubs.trig",
    "comparison_table": "assertion-source-table.md",
    "nanopub_count": 12
  },
  "relation_map": [
    {"original_wording": "significantly reduced", "predicate": "npex:decreases", "note": ""}
  ],
  "uncertainties": [
    {"ref": "NP003", "quote": "原文片段", "issue": "量词不明，无法单义化", "disposition": "未输出为断言"}
  ],
  "unreported": [
    {"candidate": "候选句", "reason": "证据缺失，疑似引用他人结果", "location_hint": ""}
  ],
  "limits": ["无文本层页面范围", "无 DOI，标识仅凭题名"],
  "nanopub_uri_note": "占位 URI（https://w3id.org/np/LOCAL/...），未签名未注册",
  "statistics": {
    "candidates_extracted": 15,
    "assertions_passed": 12,
    "assertions_degraded": 1,
    "assertions_dropped": 2,
    "model_requests_used": 9
  },
  "change_log": [
    {"time": "ISO8601", "action": "写入 nanopubs.trig（12 np）", "affected": "NP001-NP012"}
  ]
}
```

## 3. status 取值与判据

| 取值 | 判据 | 必写内容 |
|-|-|-|
| success | 全部输出齐全，断言全 pass，自检全过 | status_reason 概述 |
| partial | 存在 degraded/dropped，或部分材料不可读，或降级分支触发 | 哪些条目、原因、人工接管位置（limits 与 status_reason） |
| failed | 材料不可读、路径无效、运行中断 | 缺失项、已检查路径、已保存的部分结果 |
| refused | 材料无任何可用断言或任务超出适用范围 | 判定依据 |

部分完成时 result.json 仍必须完整写出（含已成功部分），不得只写错误信息。

## 4. 写入要求

1. 位置 /app/output/result.json，UTF-8，无 BOM，合法 JSON。
2. 先于 nanopubs.trig 之前或同时写入均可，但收尾必须保证最终版本包含全部字段。
3. uncertainties、unreported、limits 即使为空也要写成空数组，不得省略字段。
4. change_log 至少记录：candidates 写入、verified 写入、trig 写入、校验结果、最终写入五类动作。
