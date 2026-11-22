# acwrite-grant — 基金申请书写作

「学术写作」赛道 · 基金申请书写作（challenge-d403dce6）参赛 Skill。

## 用途
从申报指南/前期成果/文献材料逐章生成基金申请书各节：立项依据、科学问题与研究目标、研究内容、技术路线、创新点、研究基础与可行性、预算。四向对齐表（目标↔内容↔路线↔考核指标）保证逐条对应；创新点用 vs_existing 对照写实；预算用数字-来源核对表管住编造；关键论断带来源映射，材料不足标缺口不编造。

## 快速开始（Harness 执行环境）
1. 读取 `/input/case.json` 与 `task.md`，抄下 `output_contract` 全部字段名，立即写 `/app/output/result.json` 骨架。
2. 按 `SKILL.md` Step 0-4 顺序执行；脚本调用统一为 `python scripts/<脚本>.py ...`（脚本目录用 `find /skills /app -type d -name scripts` 定位）。
3. 逐章写作：每章一次响应写 `/app/work/chapters/chNN_*.md` → 立即 `build_result.py --embed-file … --append` 回填。
4. 最终交付 `/app/output`：grant.docx + grant.md + result.json（含全部 output_contract 字段与 case_id，主产物全文内嵌）+ 证据/对齐/预算核对/渲染记录。

## 最小示例（示意，非正式案例结果）
输入 `examples/example_input.json` 为 draft.json 结构示意，含预算数字-来源核对表示意行（sourced / missing 两态）。
```bash
SD=$(find /skills /app -type d -name scripts 2>/dev/null | head -1)
python $SD/merge_chapters.py --chapters-dir /app/work/chapters --out /app/work/draft.json
python $SD/docx_build.py /app/work/draft.json --out-docx /app/output/grant.docx --out-md /app/output/grant.md
python $SD/align_check_grant.py --alignment /app/work/alignment.jsonl --routes /app/work/routes.jsonl \
  --draft /app/output/grant.md --budget /app/work/budget_ledger.jsonl --out /app/output/align_check.json
# → {"verdict":"pass","goals":3,"budget":6,"types":[]}
```

## 依赖
- Python 3.8+，仅使用环境预装库。
- 可选增强：python-docx（docx 构建质量更好）、PyMuPDF（PDF 提取）、openpyxl（xlsx）。
- 任一可选库缺失时脚本自动降级（stdlib 兜底），降级事实写入 changelog，不阻塞交付。

## 文件清单
- `SKILL.md` — 完整工作流（5 步线性）、强制执行协议、异常处置表、最小调用示例、交付自查清单
- `scripts/` — 7 个脚本：extract_materials（材料提取）/ fact_ledger（事实台账）/ merge_chapters（逐章合稿）/ docx_build（文档构建）/ align_check_grant（四向对齐+预算核对）/ build_result（result.json 组装与逐章回填）/ render_preview（渲染预览）
- `examples/example_input.json` — draft.json 最小结构示意（仅示意，非正式案例结果）

## 方法要点
- **逐章分批防截断**：申请书全文禁止单响应写完；每章落盘即回填 result.json（--append），中断也有半成品可交付。
- **数字-来源核对**：预算金额、样本量等数字落稿前先入 budget_ledger/evidence_map；无来源金额只写占位符；机检（align_check_grant --budget）不过必须删或降级为假设。
- **四向对齐**：每个 goal 必须在 contents/routes/metrics 有对应项；指标可考核；路线含输入输出与风险备选。
- **诚实降级**：渲染器/解析库缺失如实记录，不伪造状态；status 只反映实际完成度。

## 适用边界
- 聚焦从给定材料到申请书章节稿与溯源，不做文献检索（只用材料内文献）、不做科研绘图算法。
- 材料外的事实一律不新增；学科惯例改动记 changelog。

## 维护
- 版本 2.0（重做版）；新增材料格式时扩展 `scripts/extract_materials.py` 的解析函数；预算科目变化只影响 budget_ledger 内容，脚本无需改动。
