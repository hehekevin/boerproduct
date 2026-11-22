---
name: doc-classify-tag
description: Document classification and tagging skill (focused). For each file in the library, extracts 3-5 controlled tags (research object / method / material) and assigns a category (subject / doc_type / year-band), with a one-line basis citing the source title/abstract. Handles cross-topic and missing-metadata by explicit registration, not guessing. Only tagging and classification are in scope; file renaming and dedup/versioning are out-of-scope notes. Use when the task asks to classify or tag a mixed scientific document library.
---
## 强制执行协议（最高优先级）
以下 4 条优先级高于本文档其余内容；冲突时以本节为准。
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 result.json。此后 result.json 必须存在且可解析。
2. **只打标签归类**：用受控词表，同义合并、上下位归一，避免标签爆炸；元数据缺失照实登记，不脑补。
3. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
4. **预算保护**：超 32 次请求或 450 秒停止，用现有结果定稿。

## 定位与约定
锁定子场景：给定 8 个混杂文档（期刊论文/预印本/数据集说明/扫描件）+ 分类目标（学科主题/文献类型/年份段三级分类），完成「逐文件打标签 + 归类 + 登记边界情形」。只做标签生成与归属；自动命名、去重版本区分、批量移动不在范围（各一句话兜底）。跨主题多标签、元数据缺失照实登记。
- 输入：`/input/case.json`（classification_goal + files[] + output_contract）、`task.md`。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 线性 3 步。脚本定位以 skill_marker.json 校验。

## 三步流程

### Step 0 — 落骨架
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 逐文件打标签与归类（核心，1-2 次响应）
- `tag_registry`：受控词表（研究对象/方法/材料 三组，同义合并到上位词）
- 对每个 file：`labels[]`（3-5 个标签，从 title/abstract/keywords 抽）+ `category`（按 classification_goal 的三级：subject/doc_type/year_band）+ `basis`（一句话引用 title/abstract 依据）+ `boundary_note`（跨主题/多标签/元数据缺失时登记）
- 元数据缺失的文件：labels 尽量抽可得部分，缺失字段登记 boundary_note，不脑补

### Step 2 — 汇总 + 自检
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
- `result.summary`：分类覆盖 + 边界情形计数；`run_status` + `verdict` 如实。
- verify_check 判据看 validator_verdict；FAIL 则逐条修复重跑直到 PASS。

## 输出 schema（result.json 顶层 6 契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "classification_goal":"…",
    "tag_registry":{"object":["…"],"method":["…"],"material":["…"]},
    "classifications":[{"file_id":"F01","labels":["…"],"category":{"subject":"…","doc_type":"…","year_band":"…"},"basis":"…","boundary_note":null}],
    "summary":{"classified":"8","boundary_cases":"…","note":"…"},
    "run_status":{"state":"success","reason":null},
    "verdict":"classified|partially_classified|cannot_verify","verdict_basis":"…"
  },
  "claims":[{"claim_id":"c-01","text":"…","kind":"reported","source_id":"F01","location":"files[0].abstract","evidence":[{"quote":"…"}]}],
  "uncertainties":{"summary":"…","human_review":[]},
  "changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. classifications 未覆盖全部 files。
2. labels 空 + 无 boundary_note；category 缺三级之一。
3. 元数据缺失但 label 编造（无 basis）。
4. verdict 与分类进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 元数据缺失 | labels 抽可得部分 + boundary_note 登记，不脑补 |
| 跨主题多标签 | 多标签 + boundary_note 说明归属依据 |
| 文件列表为空 | verdict=cannot_verify，不补造 |
| 校验失败 | 退出码恒 0，结论记 verdict |

## 已知限制
- 只做标签与归类，不做文件重命名/移动/去重；标签粒度用受控词表控制。
- examples/ 为合成示意非正式答案。