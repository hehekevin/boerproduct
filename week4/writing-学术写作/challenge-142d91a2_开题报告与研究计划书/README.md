# acwrite-proposal — 开题报告与研究计划书（v3 重做版）

「学术写作」赛道 · challenge-142d91a2「开题报告与研究计划书」参赛 Skill。

## 用途与适用边界
- **用途**：依据课题指南、前期数据、文献等给定科研材料，产出七要素齐全（研究背景、问题定义、目标、技术路线、阶段计划、风险、预期成果）、里程碑落在给定周期与资源内、风险带触发信号与备选方案的可编辑开题报告/研究计划书。
- **适用**：Harbor 运行环境（/input/case.json + task.md，/app/work 工作区，/app/output 交付），学科不限。
- **不适用/边界**：不代查文献（只用材料内来源）；不编造数据；材料不可提取时如实登记缺口而非猜测。

## 快速开始（Harness 执行环境）
1. 读 /input/case.json 与 task.md，逐字抄下 output_contract 全部键名与 case_id，**立即写 result.json 骨架**。
2. 按 SKILL.md 的 5 步流程执行；脚本先 `find /skills -type d -name scripts` 动态定位后调用。
3. 交付 /app/output/：proposal.docx + proposal.md（可编辑主产物）+ result.json（契约全键 + case_id + deliverable_content 内嵌全文）+ previews/。

## 关键方法（创新点）
1. **强制执行协议置顶**：7 条硬纪律保证任何中断时刻 /app/output/result.json 可解析、可评分——骨架先行、字段一个不缺、失败也交付、status 四级诚实（complete/partial/failed/blocked）。
2. **主产物全文内嵌防截断**：正文分片写作（draft_p1/p2/p3.json），docx_build.py 合并成稿，build_result.py --embed-file 由脚本把全文读入 result.json——绕开单次响应 16384 token 截断。
3. **问题-目标-里程碑-风险四表机检**：plan_check.py 校验孤儿目标、不可考核标准、里程碑超期、风险四件套（触发信号/影响/备选/决策时点）与四类覆盖。
4. **计划数字白名单的事实校验**：fact_ledger.py check --allow 把里程碑/计划声明数字计入白名单，开题稿里"第1-6月、30例、3年"不再被误报为幻觉；来源数字仍逐条回溯。

## 最小调用示例（示意输出，非正式案例结果）
```bash
SD=$(find /skills -type d -name scripts | head -1)
python $SD/extract_materials.py --input /input --outdir /app/work/extracted
# → {"ok":true,"summary":{"total":3,"extracted":3}}                      ← 示意
python $SD/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
# → {"ok":true,"facts":142,"by_type":{"number":118,"doi":9,"statistic":15}} ← 示意
# （模型分片写 draft_p1/p2/p3.json 与 plan/milestones/risk 三表）
python $SD/docx_build.py /app/work/draft_p1.json /app/work/draft_p2.json /app/work/draft_p3.json \
  --out-docx /app/output/proposal.docx --out-md /app/output/proposal.md
# → {"ok":true,"builder":"python-docx","sections":9}                     ← 示意
python $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact proposal.docx --artifact-md proposal.md \
  --embed-file /app/output/proposal.md --embed-key deliverable_content --status complete
# → {"ok":true,"contract_keys_total":8,"contract_keys_empty":[],"embed_chars":12480} ← 示意
```

## 依赖
- Python 3.8+，仅环境预装库；python-docx / PyMuPDF / openpyxl 缺失时自动 stdlib 降级并如实记录引擎名。
- 无网络依赖、无个人路径依赖；渲染预览尽力而为（soffice 缺失时记 no_renderer，不伪造）。

## 文件清单
| 文件 | 说明 |
|---|---|
| SKILL.md | 强制执行协议（7 条）+ 5 步线性流程 + 异常处置表 + 示例 + 自查清单 |
| scripts/extract_materials.py | 材料提取（docx/pdf/xlsx/txt/md/json/html → 带锚点纯文本 + manifest） |
| scripts/fact_ledger.py | 事实台账 build/check；check 支持 --allow 计划数字白名单 |
| scripts/plan_check.py | 问题-目标对齐 / 周期合规 / 风险四件套机检（容错版） |
| scripts/docx_build.py | 分片合并 → 可编辑 docx + markdown（stdlib 兜底最小 docx） |
| scripts/render_preview.py | docx → PDF/PNG 预览（如实记录渲染引擎或 no_renderer） |
| scripts/build_result.py | result.json 组装（契约键提取 / --embed-file 内嵌 / 自检输出） |
| examples/example_input.json | 示意输入结构（非正式案例结果） |

## 失败处理与自查
- 全部脚本三级容错：脏输入/缺文件不崩溃，输出 verdict=error/skipped 而非空结果。
- 自查方法：跑完 Step 4 后核对 SKILL.md「交付自查清单」9 项；build_result 自检 JSON 的 contract_keys_empty 必须为空、embed_chars 必须 > 0。

## 维护
- v3（2026-11-13）：修复 v2 最后一步组装必挂的 --embed-file 参数缺失 bug；分片防截断；计划数字白名单；脚本全容错；补最小示例与 worklog。详见 worklog.md。
