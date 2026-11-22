---
name: cite-support-check
description: Citation-support verification skill (极简单点：单一方向). 只做「引用支持判定」：把正文中带引用标号的结论句拆成可判定单元，逐条判定完整支持/部分支持/不支持/无法判定四档，识别「结论超出引文范围」的过度推断。每条结论给出原文位置（章节/句位）与其引用的引文编号，读不到被引原文的标「无法判定」，不脑补、不冒充已核对。citation_scan.py 机械提取正文中带引用标号的结论句候选清单（[n] 与 Author-Year），verify_check.py 对每条判定的四档枚举、quote 逐字回证原文、cite_marker 回证参考文献表做机械校验。Use when the task asks to judge whether each cited conclusion in a manuscript is fully/partially/not supported by its cited references, or to flag over-inference beyond cited scope.
---

## 强制执行协议（最高优先级）
1. **第 0 步先落骨架**：读完 /input/case.json 与题面后，第一个动作是运行 `build_skeleton.py`（Step 0）在 /app/output/result.json 写入骨架；此后任何时刻 result.json 必须存在且 JSON 可解析，每次更新都覆盖为当前最新完整状态。
2. **失败也要交付**：中断或失败时仍写 result.json（status=partial，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。
3. **退出码恒 0 看 verdict**：所有校验脚本退出码恒为 0，失败不中断交付；判据是报告里的 `verdict`（PASS/FAIL）与 `problems` 列表。
4. **预算过半即定稿**：模型请求已用超 32 次或运行超 450 秒时，停止新增判定，用现有中间结果完成 result.json 并收尾（status 如实填 partial）。

## 定位与约定
- **只做一件事**：引用支持判定。把正文结论拆成可判定单元，逐条判「完整支持/部分支持/不支持/无法判定」四档，识别「结论超出引文范围」的过度推断。
- **不做的**：事实来源可靠性分级、数值统计一致性、论证链完整性、学术规范核查、外部文献检索、查重、润色改写。这些方向一律不展开。
- **判定对象**：只处理正文中**带引用标号的结论句**（每案例 8-12 条）；不带引用标号的句子不判。
- 输入：`/input/case.json`（稿件 + 要求 + output_contract）、`task.md`。**以实际文件为准，不依据标签假设内容。**
- 工作区：`/app/work`；最终产物：`/app/output/result.json`。预算：64 次模型请求 / 900 秒 / 单响应 16384 token；只用标准库，不装 pip 依赖。
- 脚本定位以 `/app/work/skill_marker.json` 标志文件校验为准（Step 0 落盘）。

## 三步流程

### Step 0 — 落骨架（1 次脚本调用，必做）
```bash
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
```
- 自动：提取 output_contract 全部字段 + case_id + 稿件结构 → 写骨架；生成 `/app/work/skill_marker.json` 标志文件。
- 脚本失败时手工兜底：读 case.json 抄 case_id 与 output_contract 字段名，手写骨架（键一个不缺）。

### Step 1 — 提取带引用结论句并逐条判定（1-2 次响应）
- 先运行 `citation_scan.py` 机械提取带引用标号的结论句候选清单（回写 `result.citation_scan`）：
```bash
python3 /skills/weekly-skill/scripts/citation_scan.py --result /app/output/result.json --case /input/case.json --emit-into
```
- 再逐条判定：把每条候选结论句写进 `result.citation_checks[]`，每案例 8-12 条。
  - `claim`：该句的结论主张（用一句话概括）。
  - `support_state` 四档：`fully_supported`（被引主张与本句结论一致）/ `partially_supported`（只支持部分，结论有超出）/ `unsupported`（被引主张不支持该结论）/ `cannot_determine`（读不到被引原文，无法判断）。
  - `over_inference`：结论超出引文范围即 `true`（部分支持或过度外推）；完整支持或无法判定为 `false` 或 `null`。
  - **读不到被引原文 → support_state=cannot_determine，不脑补**；source_accessible=false 并登记 uncertainties。
  - `cite_markers`：该句实际引用的引文编号（如 `["[2]"]`），须命中 citation_scan 机械清单在参考文献表内的标记。

### Step 2 — 自检与交付（校验脚本退出码恒 0，看 verdict 不看退出码）
```bash
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
python3 /skills/weekly-skill/scripts/schema_guard.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/schema_guard.json
```
- 判据是报告 `verdict`（PASS/FAIL）：FAIL 则按 `problems` 逐条修复 → 覆盖写 result.json → 重跑，直到 PASS（或确认无法修复并如实记录）。
- 自查三问：每条判定的 quote 都能回原文逐字命中吗？读不到的被引文献都标 cannot_determine 并登记了吗？cite_markers 都回证参考文献表了吗？

## 输出 schema（result.json — case_id + output_contract 全字段 + 业务键）
```json
{
  "case_id": "取自 case.json", "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "material_gaps": [], "environment": {"python_version": "…", "packages": "stdlib-only", "seed": null, "hardware_note": "照实"},
    "manuscript_overview": {"title": "…", "sections": [{"section_id": "S1", "name": "…", "source_ref": "…"}], "reference_count": 4},
    "citation_scan": {"candidate_sentences": [], "markers_in_text": [], "reference_ids": [], "scan_note": "citation_scan.py 回填"},
    "citation_checks": [{"check_id": "C01", "source_ref": "…", "section_id": "S2", "location": "S2 引言 第 2 句", "quote": "逐字摘录", "claim": "结论主张", "cite_markers": ["[2]"], "support_state": "fully_supported | partially_supported | unsupported | cannot_determine", "over_inference": true, "source_accessible": true, "reason": "对照被引主张说明", "revision_suggestion": "…", "judged": true}],
    "coverage": {"total_checks": 8, "judged": 8, "state_counts": {}, "over_inference_count": 0},
    "steps": [], "run_status": {"state": "success | partial | unable_to_determine | refused", "reason": null, "manual_takeover": []},
    "verdict": "audited | partially_audited | not_audited | cannot_verify", "verdict_basis": "…",
    "gain_evidence": {"available": false, "reason": "极简单点策略：单一引用支持判定方向，增益层在预算 50% 跳过"},
    "efficiency": {"checker_runs": 2, "reproduce": "python3 …"}
  },
  "claims": [{"claim_id": "c-01", "text": "…", "kind": "reported | inferred", "source_id": "C01", "location": "citation_checks[0]", "evidence": [{"paragraph_id": "…", "quote": "稿件原句"}]}],
  "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": "…"},
  "changelog": [], "self_check": [{"item": "…", "template_value": "…", "applied": true, "match": true}],
  "validator_verdict": "PASS | FAIL",
  "gates": [{"gate": "case_contract", "state": "enforced | skipped_not_provided | not_found | unreadable", "note": ""}]
}
```

## 校验器会抓的错（verify_check.py）
1. support_state 枚举非法；status / run_status.state / verdict 枚举非法。
2. quote 空白归一化后不在稿件原文中（逐字回证失败）或 location 为空。
3. source_accessible=true 但 support_state=cannot_determine（冒充已核对）；source_accessible=false 但 support_state≠cannot_determine（读不到却强判）。
4. cite_markers 为空，或标记不在 citation_scan.reference_ids（引文编号回证失败）。
5. 过度推断：over_inference=true 但 support_state 不是 partially_supported/unsupported。
6. judged=true 但缺 reason 或 revision_suggestion。
7. coverage 汇总与实际不符；citation_checks 为空却判 audited；unchecked 非空仍判 audited。
8. output_contract 全字段缺失；闸门 case_contract 非 enforced 时 warn + note「下游不得宣称已核对」。

## 最小调用示例
`examples/` 有合成案例与示意输出（**非正式答案**，论文/数据/文献均为虚构）：
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/citation_scan.py --result examples/example-result.json --case examples/example-case.json --emit-into
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json
```

## 异常处置
| 异常场景 | 处置 |
|---------|------|
| 稿件解析失败 / 输入不可读 | material_gaps 登记、status=input_error 或 insufficient_evidence、verdict=cannot_verify，绝不编造结论 |
| 被引文献全文读不到 | support_state=cannot_determine + source_accessible=false + uncertainties 登记，不脑补 |
| 正文无带引用标号的结论句 | citation_checks 空 + verdict=not_audited + reason 写明，绝不硬凑 |
| 引用标记样式异常（脚注式等） | citation_scan 闸门记 not_found，退化为 Agent 人工分句并在 steps 注明 |
| 稿件超长/预算不足 | 保留已审部分，status=partial，changelog 注明截断位置，预算过半即定稿 |
| 校验脚本报 FAIL | 按 problems 逐条修复后覆盖写 result.json 再重跑；修不了就如实登记 uncertainties，绝不中断交付 |
| 运行中断 | 按协议第 2 条写 result.json，status=partial，注明中断点 |

## 已知限制
- 仅做「引用支持判定」单一方向：不做事实来源可靠性分级、数值统计一致性、论证链、学术规范核查。
- 判定依据是被引文献在材料内可读的摘要/主张文本；被引原文不可读时一律 cannot_determine，不冒充核对。
- quote 逐字回证是"逐字命中原文"的机械下界，不能替代被引主张的语义核对（读不到标 cannot_determine）。