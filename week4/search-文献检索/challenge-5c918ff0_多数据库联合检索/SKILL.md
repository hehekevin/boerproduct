---
name: multi-db-merge-dedup
description: Multi-database federated search merge skill (focused). Standardizes cross-database fields (author/journal/year/identifier), then deduplicates merged records using identifier-exact plus title+author+year fuzzy matching, with a per-cluster rationale and human-arbitration flag for uncertain pairs. Only field-standardization and dedup are in scope; multi-source query orchestration and failure-degradation are one-line notes. Use when the task asks to merge and deduplicate results from multiple scholarly databases.
---
## 强制执行协议（最高优先级）
以下 4 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 result.json。此后 result.json 必须存在且可解析。
2. **去重用脚本机械做**：标识符精确匹配 + 标题作者年份模糊，重复判定可解释，不确定的交人工仲裁（标 pending）。
3. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
4. **预算保护**：超 32 次请求或 450 秒停止，用现有结果定稿。

## 定位与约定
锁定子场景：给定多个数据库的响应记录（responses[]，7 条含 records），完成「跨库字段标准化 → 去重 → 来源回溯」。只做字段标准化和去重；多源查询编排/失败降级是一句话兜底。缺失与未知区分登记，不脑补。
- 输入：`/input/case.json`（research_question + databases + responses[] + output_contract）、`task.md`。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 线性 3 步。脚本定位以 skill_marker.json 校验。

## 三步流程

### Step 0 — 落骨架
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 字段标准化 + 去重（核心，1 脚本 + 1 次响应）
```bash
python3 /skills/weekly-skill/scripts/dedup_merge.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/dedup.json --emit-into
```
- `field_mapping`：跨库字段映射（author→authors、journal→journal、identifier→doi/pmid 等），标明 map 来源
- 脚本机械去重：DOI 精确 → 合并；标题+作者+年份归一化相同 → 合并；标题相似但非同一 → 标 pending 人工仲裁
- `duplicates[]`：每个 cluster 给 cluster_id + 保留记录 + 重复记录 + 判定方式（doi_exact/title_match）+ reasons；不确定的 preserve_status=pending
- 每条合并结果保留来源库（source_ref）

### Step 2 — 汇总 + 自检
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
- `result.summary`：原始记录数 / 去重后 / 聚类数；`run_status` + `verdict` 如实。
- verify_check 判据看 validator_verdict；FAIL 则逐条修复重跑直到 PASS。

## 输出 schema（result.json 顶层 6 契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "research_question":"…",
    "field_mapping":[{"source_field":"author","target_field":"authors","db":"crossref"}],
    "duplicates":[{"cluster_id":"C1","kept_record":"…","duplicate_records":["…"],"match":"doi_exact|title_match|pending","basis":"…"}],
    "summary":{"raw_total":"7+","deduped_total":"…","clusters":"…","note":"…"},
    "run_status":{"state":"success","reason":null},
    "verdict":"merged|partially_merged|cannot_verify","verdict_basis":"…"
  },
  "claims":[{"claim_id":"c-01","text":"…","kind":"reported","source_id":"C1","location":"responses[0].records[0]","evidence":[{"quote":"…"}]}],
  "uncertainties":{"summary":"…","human_review":[]},
  "changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. duplicates 无 basis；match 枚举非法。
2. 记录未做字段标准化就归并（无 field_mapping 来源）。
3. 去重前后计数矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 某库无记录/缺字段 | missing_metadata 区分"缺失"vs"未知"，不脑补 |
| 标题相似但无法确认 | preserve_status=pending 交人工仲裁 |
| 响应为空 | verdict=cannot_verify |
| 校验失败 | 退出码恒 0，结论记 verdict |

## 已知限制
- 只做字段标准化+去重，不做查询编排/限流降级；匹配为给定响应快照内判定。
- examples/ 为合成示意非正式答案。