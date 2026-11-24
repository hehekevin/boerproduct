---
name: 139745c7
description: Multi-aspect skill (5 aspects) with itemized findings and prose report embedded.
---

## 强制执行协议（最高优先级，冲突时以本节为准）
1. **第 0 步先落骨架**：读完 `/input/case.json` 第一个动作运行 `build_skeleton.py`，写含 output_contract 全字段 + case_id 的 result.json。此后 result.json 必须存在且可解析。
2. **5方面必覆盖**：semantic_search / section_location / filter / evidence_traceback / file_organization 都要逐面查过并记录，不得静默跳过。
3. **成文报告必嵌入**：除 findings 外，必须写 `result.report`（Markdown 全文，≥200 字）。
4. **失败也交付**：任何中断仍写 result.json。脚本退出码恒 0，判据看 verdict。
5. **预算保护**：模型请求超 40 次或 600 秒即停止，用现有结果写 report 收尾。

## 定位与约定
锁定子场景：给定 文件库、查询，完成**5方面完整任务**。逐条问题带逐字 quote + 位置 + 严重度 + 修改建议；拿不准标待复核，不脑补。材料缺失、无法判断照实登记。
- 输入：`/input/case.json`（文件库、查询 + output_contract）、`task.md`。以实际文件为准。
- 工作区：`/app/work`；产物：`/app/output/result.json`。预算 64 请求/900 秒；仅标准库。
- 脚本定位以 skill_marker.json 校验。

## 5方面定义（每面必查）
1. `semantic_search` 跨文件语义检索。
2. `section_location` 章节定位。
3. `filter` 过滤条件。
4. `evidence_traceback` 证据回链。
5. `file_organization` 文件组织与版本。

## 五步流程

### Step 0 — 落骨架（1 次脚本，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```

### Step 1 — 严重度口径声明（1 次响应，判定前必做）
critical=动摇核心结论；major=局部问题可修正；minor=表述/建议。写 result.severity_rubric。

### Step 2 — 5方面逐面产出（2-4 次响应，广度优先）
逐面处理，每条问题写 `result.findings[]`：`aspect` ∈ 5面之一 + `quote` 逐字 + `location` + `severity` + `evidence` + `revision_suggestion`。**每面都要产出**：有问题记 finding；没问题的面在 `result.aspect_coverage` 记 `{aspect, status:"checked_no_issue"}`。

### Step 3 — 写成文报告（1 次响应，必做）
写 `result.report`（≥200 字）：①总体结论 ②5方面逐面小结 ③主要问题清单 ④待复核项。

### Step 4 — 自检与交付（1 次脚本，必做）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
```
判据看 validator_verdict；FAIL 则修复→重跑直到 PASS。

## 输出 schema（result.json 顶层契约字段 + result 核心键）
```json
{
  "case_id":"…","status":"answered|partial|input_error",
  "result":{
    "severity_rubric":{"levels":{"critical":"…","major":"…","minor":"…"},"declared_at":"step1"},
    "findings":[{"finding_id":"F01","aspect":"semantic_search","category":"insufficient_evidence","severity":"major","quote":"逐字","location":"…","evidence":"…","revision_suggestion":"…","status":"confirmed"}],
    "aspect_coverage":[{"aspect":"semantic_search","status":"checked_findings","count":1}],
    "report":"## 总体结论\n……（≥200字）",
    "run_status":{"state":"success","reason":null},
    "verdict":"…","verdict_basis":"…"
  },
  "claims":[],"uncertainties":{"summary":"…"},"changelog":[]
}
```

## 校验器会抓的错（verify_check.py）
1. 5方面有任一面在 aspect_coverage 缺失。
2. findings 里 aspect/category/severity 枚举非法；confirmed 缺 quote/location。
3. report 缺失或 <200 字。
4. severity_rubric 未声明；suggestion≠minor；fact_error 标 minor。
5. verdict 与进度矛盾；缺 output_contract 字段。

## 异常处置
| 场景 | 处置 |
|---|---|
| 某方面材料缺失 | 该面记 checked_no_issue + 注明"材料缺失无法核验"，不编造 |
| 无法判断 | 标待复核，不脑补 |
| 材料超长/预算不足 | 未处理范围记 unchecked + status=partial |
| 校验 FAIL | 修复后重跑；修不了如实登记，绝不中断交付 |

## 已知限制
- 只处理输入材料本身，不做外部检索/真实执行；结果为材料快照的整理。
- examples/ 为合成示意（虚构），非正式答案。
