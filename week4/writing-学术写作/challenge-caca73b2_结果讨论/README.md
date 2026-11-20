# acwrite-results — 结果与讨论章节写作（重做版）

「学术效率」比赛 · 学术写作赛道 · 结果与讨论章节写作（challenge-caca73b2）参赛 Skill。

## 用途
从数据表/图/图注/统计输出可靠读数，按图序写"只陈述观察"的结果段，讨论段每条论断带【依据】内联标注绑定本研究数据或具体文献，因果/相关边界受控、局限写到方法样本测量层面。交付**数字-来源逐条核对表**与**图表交叉引用完整性校验**，全部数值回溯到图表。

## 快速开始（Harness 执行环境）
1. 读取 `/input/case.json` 与 `task.md`，抄下 `output_contract` 全部字段名；第 1 次响应内落骨架 result.json。
2. 按 `SKILL.md` 的 Stage 1-5 线性执行；脚本调用统一为 `python scripts/<脚本>.py ...`。
3. 交付到 `/app/output`：results_discussion.docx/.md + result.json（含全部契约字段、case_id、嵌入全文、number_source_table、discussion_claims、四份检查报告、uncertainty/changelog）。

## 新增机制（相对上一版）
| 机制 | 实现 | 交付位置 |
|---|---|---|
| 数字-来源逐条核对表 | `scripts/trace_audit.py` 子检查 A：每个数值→source_ref+source_locator+verbatim+status | result.json `number_source_table` 字段整表嵌入 |
| 结果段↔图表交叉引用完整性 | `scripts/trace_audit.py` 子检查 B：登记↔引用双向核对，缺一 fail | result.json `trace_audit.crossref` |
| 讨论结论逐条溯源 | 写作时句末【依据：…】内联标注 + `trace_audit.py` 子检查 C 机检 | result.json `discussion_claims` |
| 主产物全文嵌入 | `build_result.py --embed-md` | result.json `main_text_markdown` |

## 最小示例（标注示意，非正式案例结果）
输入 draft.json（见 `examples/example_input.json`）→ 调用：
```bash
python scripts/trace_audit.py --draft results_discussion.md --readings readings.jsonl \
  --ledger fact_ledger.jsonl --dclaims dclaims.jsonl \
  --out-table number_source_table.json --out trace_audit.json
# → {"verdict":"pass","checked":88,"unmatched":0,"crossref":"pass","claims":"14/14"}
python scripts/build_result.py --case /input/case.json --out result.json \
  --artifact results_discussion.docx --embed-md results_discussion.md \
  --source-table number_source_table.json --trace-audit trace_audit.json --status complete
# → {"ok":true,"embedded_main_text":true,"number_source_rows":88}
```
核对表逐条形态：`{"value":"12.3±1.1","source_ref":"图1","source_locator":"M03:p5","verbatim":"12.3±1.1","status":"matched"}`

## 依赖
- Python 3.8+，仅使用环境预装库。
- 可选增强：python-docx、PyMuPDF、openpyxl；任一缺失时脚本自动降级（stdlib 兜底），降级事实写入 changelog，不阻塞交付。

## 文件清单
- `SKILL.md` — 强制执行协议 + 5 阶段线性工作流 + 异常处置表 + 最小示例 + 自查清单
- `scripts/`（8 个）— extract_materials / fact_ledger / boundary_check / consistency_check / trace_audit / docx_build / render_preview / build_result
- `examples/example_input.json` — draft.json 结构示意（含【依据】标注示例）

## 适用边界
- 仅处理给定材料支撑的写作任务；材料外的学科惯例改动记录在 changelog。
- 不做科研绘图算法本身；聚焦从材料到成稿与逐条溯源。

## 维护
- 版本 2.0（保底增强版：旧版全部机制保留，新增 trace_audit 三合一审计与 result.json 嵌入）。
- 如遇新格式材料，扩展 `scripts/extract_materials.py` 的 ext_map 与对应解析函数。
