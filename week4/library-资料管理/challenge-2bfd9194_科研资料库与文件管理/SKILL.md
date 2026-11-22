---
name: library-metadata-organize
description: Research library file management skill (focused). For each file, extracts 4-6 metadata fields (title/author/year/type/topic) with field source, and proposes a directory tree (project / year / data-type) with a per-file target path. Only metadata extraction and directory organization are in scope; upload/resume, versioning and long-term archiving are one-line notes. Use when the task asks to organize a document library with structured metadata and directory planning.
---
## 强制执行协议（最高优先级）
以下 4 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 result.json。此后 result.json 必须存在且可解析。
2. **元数据要有出处**：每字段标 source（文件名/内容/伴随表），内容里盘不到的登记缺失，不脑补。
3. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
4. **预算保护**：超 32 次请求或 450 秒停止，用现有结果定稿。

## 定位与约定
锁定子场景：给定 8 个文件（path + content），完成「逐文件元数据抽取 → 目录树规划 + 归位」。只做元数据维护与目录组织；版本管理/归档是一句话兜底。字段保留出处。
- 输入：`/input/case.json`（files[] + output_contract）、`task.md`。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 线性 3 步。脚本定位以 skill_marker.json 校验。

## 三步流程

### Step 0 — 落骨架
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 元数据抽取 + 目录归位（核心，1-2 次响应）
- `dir_tree`：按 项目/年份/数据类型 三级生成目录树（规则事前声明）
- 对每个 file：`metadata`（4-6 字段：title/author/year/type/topic，每字段带 source 出处）+ `target_dir`（归位到 dir_tree 哪一级）+ `basis`
- 内容里盘不到的字段登记 missing，不脑补

### Step 2 — 汇总 + 自检
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
- `result.summary`：文件数/元数据覆盖率；`run_status` + `verdict` 如实。
- verify_check 判据看 validator_verdict；FAIL 则逐条修复重跑直到 PASS。

## 输出 schema（result.json 顶层 6 契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "dir_tree":{"rule":"项目/年份/数据类型","declared_at":"…","tree":["projectA/2023/paper/…"]},
    "metadata_records":[{"file_id":"F01","path":"…","metadata":{"title":{"value":"…","source":"filename"},"year":{"value":2023,"source":"content"},"type":{"value":"paper","source":"filename"}},"target_dir":"projectA/2023/paper","basis":"…"}],
    "summary":{"files":"8","metadata_coverage":"…","note":"…"},
    "run_status":{"state":"success","reason":null},
    "verdict":"organized|partially_organized|cannot_verify","verdict_basis":"…"
  },
  "claims":[{"claim_id":"c-01","text":"…","kind":"reported","source_id":"F01","location":"files[0].content","evidence":[{"quote":"…"}]}],
  "uncertainties":{"summary":"…","human_review":[]},
  "changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. metadata_records 未覆盖全部 files。
2. metadata 字段无 source；target_dir 不符合 dir_tree 规则。
3. dir_tree 缺 declared_at。
4. verdict 与进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 内容缺失字段 | metadata 标 missing，不脑补 |
| 跨主题文件 | 归到主主题 + 注明边界 |
| 文件列表为空 | verdict=cannot_verify |
| 校验失败 | 退出码恒 0，结论记 verdict |

## 已知限制
- 只做元数据抽取与目录规划，不做真实移动/改名/版本链；为内容静态快照分析。
- examples/ 为合成示意非正式答案。