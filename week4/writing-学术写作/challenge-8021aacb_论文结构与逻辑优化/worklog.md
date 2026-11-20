# worklog — acwrite-structure 重做（challenge-8021aacb）

日期：2026-11-13 ｜ 执行：redo-w6-structure

## 目标

历史提交卡在 65 档（71940: 65.00 / 72499: 64.67）。诊断差距主要在**可核验性**：评分者需要不打开原稿就能逐条核对诊断与修改。本次重做围绕这一点。

## 相对旧版（skills/acwrite-structure）的改动

1. **协议置顶（新增第 0 节）**：抄契约（字段逐字一个不缺）→ 立即落骨架 result.json → 写盘自检 → 广度优先（六类问题先各扫一遍再深化）→ 48 请求/700 秒熔断（平台 64/900 留余量）→ 失败也交付。旧版流程有 7 个阶段但无强制协议，熔断与骨架落盘没有硬性约束。
2. **线性 5 阶段**：Stage 0 契约骨架 / 1 论断链 / 2 诊断 / 3 修订+逐字留痕 / 4 校验嵌入交付。渲染降为 Stage 4 内可选步骤（失败不阻塞）。
3. **逐字前后对照留痕（核心新增）**：`edits_before_after.jsonl` —— 每处修改登记 `original(≤40 字逐字，可在原稿检索) / revised(已落地修订稿) / reason / basis(指向 Sxx/Axx) / 段落定位`。旧版只有 issue 级建议，无句子级可检索对照。
4. **主产物完整嵌入 result.json（核心新增）**：build_result.py 新增 `--embed-diagnosis / --embed-chain / --embed-edits / --embed-revised`，把 diagnosis.issues、claim_chain、edits_before_after、revised_text(修订全文) 全量嵌入 result.json；骨架模式（--scaffold）保证契约字段一个不缺且回填不覆盖；输出 contract_missing 清单。
5. **verify.py（新增）**：机器校验三件事 —— original 可在原稿定位（located_ratio）、revised 已落进修订稿（landed_ratio）、修订稿无未授权改动（段落级比对）→ verdict pass/fail/skipped，结果随 result.json 交付。
6. **脚本精简 7→5**：合并 consistency_check/fact_ledger（结构题不需要事实台账）、edits_verify 并入新 verify.py；全部三级容错、exit 0 不阻塞、路径可参数化（--input/--outdir/--out，默认值兼容平台约定但非硬编码）。
7. **异常处置补强**：稿件截断/缺章节 → gaps 登记 + 只诊断实际存在部分；刻意呼应不合并；风格冲突 → 语句级标 needs_author。
8. **文档**：README 给出完整调用步骤、最小示例（含逐字对照 JSON 示意与本地实测输出）、嵌入字段说明、依赖与限制；examples/example_input.json 为示意输入。

## 本地双测记录（Windows / Python 3.x）

- 测 1（骨架+抽取）：extract_materials 正常抽取 paper.md → materials.md+manifest（gaps=[]）；build_result --scaffold 产出契约 4 字段(null)+status=pending，写盘自检通过。
- 测 2（全流程）：docx_build 出 docx+md（python-docx 可用）；verify → located/landed=1.0、unauthorized=0、verdict=pass；build_result 嵌入后 result.json 含 issues=1(high=1)、edits=1、revised_text=True、verify_report。
- Bug 修复：单行 jsonl 被 json.load 解析为 dict 导致嵌入计数错乱 → build_result 增加 as_records 归一化，复测通过。
- 容错测：edits/revised 缺失 → verdict=skipped+reasons，exit 0；input 目录不存在 → gaps 登记，exit 0；soffice/docx2pdf 不可用 → render_log 如实 rendered=false，不阻塞。
- 测试夹具（input_demo/work/output）已清理。

## 遗留与说明

- render_preview 在无 Office/soffice 的平台只产 PDF 失败日志 —— 属预期降级，交付不受影响（md+docx+嵌入全文已足够核验）。
- output_contract 的字段值由模型在 Stage 4 经嵌入字段/--set 回填；无法回填时保持 null 并由 uncertainty 说明（契约字段名始终齐全）。
- 未提交平台（按指示）。
