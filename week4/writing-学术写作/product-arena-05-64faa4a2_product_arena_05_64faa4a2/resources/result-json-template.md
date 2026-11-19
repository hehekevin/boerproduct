# result.json 输出模板

用途：每个案例运行结束后写入 `/app/output/result.json`。字段分两组：基础字段固定提供；契约字段以案例 `case.json` 中 `output_contract` 要求为准，全部字段必须出现。运行早期先写入骨架（status 为 in_progress），结束时覆盖为最终版。

## 基础结构

```json
{
  "case_id": "从 case.json 原样读取",
  "task_type": "methods_experiments_writing",
  "status": "complete | partial | failed",
  "status_reason": "一句话说明为何是该状态",
  "deliverables": [
    {
      "path": "/app/output/methods_and_experiments.md",
      "kind": "draft_section",
      "description": "Methods 与 Experiments 章节成稿"
    },
    {
      "path": "/app/output/fact_source_map.md",
      "kind": "evidence_map",
      "description": "事实与来源映射表，含参数表、符号表、缺口与冲突清单"
    }
  ],
  "main_result": {
    "summary": "成稿内容两三句概述：覆盖的章节与小节",
    "sections_covered": ["data", "method", "procedure", "setup", "metrics", "baselines", "reproducibility", "limitations"],
    "word_count": 0
  },
  "fact_source_map_summary": {
    "source_count": 0,
    "fact_count": 0,
    "verified_count": 0,
    "conflict_count": 0,
    "todo_count": 0,
    "reproducibility": {"available": 0, "todo": 0},
    "coverage": {
      "procedure": "covered | partial | missing",
      "setup": "covered | partial | missing",
      "parameters": "covered | partial | missing",
      "datasets": "covered | partial | missing",
      "baselines": "covered | partial | missing",
      "repro_limitations": "covered | partial | missing"
    }
  },
  "gaps": [
    {"id": "G1", "description": "缺少随机种子列表", "needed_from": "实验执行者", "marked_in_draft": true}
  ],
  "conflicts": [
    {"id": "G2", "description": "测试集规模在 S3 与 S4 中不一致", "resolution": "取结果表值并标注待确认", "marked_in_draft": true}
  ],
  "changes": [
    {"location": "2.Z 第 1 段", "change": "将 learning rate 从正文误写的 0.01 改为配置文件中的 3e-4", "reason": "与 S1 一致"}
  ],
  "uncertainties": [
    "单位缺失的参数已在正文标注，待作者确认"
  ],
  "notes": "其他需要说明的信息，例如某材料无法解析"
}
```

## 字段说明

1. `case_id`：必填，从 case.json 原样复制，不得改写。
2. `status`：三值之一。
   - complete：六类要素覆盖且无未决冲突，gaps 为空或全部已确认。
   - partial：成稿可用但存在缺口、冲突或无法解析的材料，已在 gaps、conflicts、uncertainties 中逐条列明。
   - failed：无法产出成稿（如材料为空、全部文件无法读取），status_reason 写明原因，不输出虚构成稿。
3. `deliverables`：列出全部输出文件及用途，路径为绝对路径。
4. `changes`：改写类任务必填，记录对原稿的关键修改及依据；撰写类任务可为空数组。
5. `gaps` 与 `conflicts`：与 fact_source_map.md 中第四部分逐条对应，编号一致。
6. 契约字段：case.json 的 output_contract 若要求本模板之外的字段（如指定小节文本、指定格式），把这些字段加在同一层，值按契约填写；材料不足以满足契约字段时填 "unknown" 并在 notes 说明，不得编造。
7. JSON 必须可解析：写入前自查引号、逗号、编码，使用 UTF-8。
