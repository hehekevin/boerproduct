# acwrite-proposal — 开题报告与研究计划书（v4 增强版）

「学术写作」赛道 · challenge-142d91a2「开题报告与研究计划书」参赛 Skill。

## 用途与适用边界
- **用途**：依据课题指南、前期数据、文献等给定科研材料，产出七要素齐全（研究背景、问题定义、目标、技术路线、阶段计划、风险、预期成果）、里程碑落在给定周期与资源内、风险带触发信号与备选方案的可编辑开题报告/研究计划书。
- **适用**：Harbor 运行环境（/input/case.json + task.md，/app/work 工作区，/app/output 交付），学科不限。
- **不适用/边界**：不代查文献（只用材料内来源）；不编造数据；材料不可提取时如实登记缺口而非猜测。

## 快速开始（Harness 执行环境）
1. 读 /input/case.json 与 task.md，逐字抄下 output_contract 全部键名与 case_id，**立即写 result.json 骨架**。
SCRIPT_DIR=""
for d in /skills/weekly-skill/scripts ./scripts scripts; do
  if [ -f "$d/build_result.py" ]; then SCRIPT_DIR="$d"; break; fi
done
if [ -z "$SCRIPT_DIR" ]; then
  SCRIPT_DIR=$(find /skills /app -type d -name scripts 2>/dev/null | while read -r d; do [ -f "$d/build_result.py" ] && echo "$d" && break; done)
fi
[ -n "$SCRIPT_DIR" ] || SCRIPT_DIR="./scripts"   # 兜底：相对路径 + 如实登记，不臆造路径

3. 交付 /app/output/：proposal.docx + proposal.md（可编辑主产物）+ result.json（契约全键 + case_id + deliverable_content 内嵌全文）+ previews/。

## 关键方法（创新点）
1. **强制执行协议置顶**：7 条硬纪律保证任何中断时刻 /app/output/result.json 可解析、可评分——骨架先行、字段一个不缺、失败也交付、status 四级诚实（complete/partial/failed/blocked）。
2. **主产物全文内嵌防截断**：正文分片写作（draft_p1/p2/p3.json），docx_build.py 合并成稿，build_result.py --embed-file 由脚本把全文读入 result.json——绕开单次响应 16384 token 截断。
3. **问题-目标-里程碑-风险四表机检**：plan_check.py 校验孤儿目标、不可考核标准、里程碑超期、风险四件套（触发信号/影响/备选/决策时点）与四类覆盖。
4. **计划数字白名单的事实校验**：fact_ledger.py check --allow 把里程碑/计划声明数字计入白名单，开题稿里"第1-6月、30例、3年"不再被误报为幻觉；来源数字仍逐条回溯。
5. **三项完整性机检（seven_check.py）**：A 七要素章节完整性（逐项 {item, expected, applied, match} 三元组）、B 技术路线可执行性（route.jsonl 每步 input/output/depends/resources 齐全、依赖真实、归属里程碑）、C 时间表-内容一致性（里程碑周期/交付物正文逐字回证、正文计划区间必有里程碑条目、不超给定周期）。闸门状态显式枚举 enforced/skipped_not_provided/not_found/unreadable——未运行≠通过，skipped 必须写 gate_note 且下游不得宣称已核对。报告经 build_result.py --seven-check 整体嵌入 result.json。

## 最小调用示例（示意输出，非正式案例结果）
```bash
SCRIPT_DIR=""
for d in /skills/weekly-skill/scripts ./scripts scripts; do
  if [ -f "$d/build_result.py" ]; then SCRIPT_DIR="$d"; break; fi
done
if [ -z "$SCRIPT_DIR" ]; then
  SCRIPT_DIR=$(find /skills /app -type d -name scripts 2>/dev/null | while read -r d; do [ -f "$d/build_result.py" ] && echo "$d" && break; done)
fi
[ -n "$SCRIPT_DIR" ] || SCRIPT_DIR="./scripts"   # 兜底：相对路径 + 如实登记，不臆造路径

python3 $SD/extract_materials.py --input /input --outdir /app/work/extracted
# → {"ok":true,"summary":{"total":3,"extracted":3}}                      ← 示意
python3 $SD/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
# → {"ok":true,"facts":142,"by_type":{"number":118,"doi":9,"statistic":15}} ← 示意
# （模型分片写 draft_p1/p2/p3.json 与 plan/route/milestones/risk 四表）
python3 $SD/docx_build.py /app/work/draft_p1.json /app/work/draft_p2.json /app/work/draft_p3.json \
  --out-docx /app/output/proposal.docx --out-md /app/output/proposal.md
# → {"ok":true,"builder":"python-docx","sections":9}                     ← 示意
python3 $SD/seven_check.py --draft /app/output/proposal.md --route /app/work/route.jsonl \
  --milestones /app/work/milestones.jsonl --constraints /app/work/constraints.json \
  --out /app/output/seven_check.json
# → {"verdict":"pass","fail":0,"checks_total":19,"checks_matched":19}    ← 示意
python3 $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact proposal.docx --artifact-md proposal.md \
  --embed-file /app/output/proposal.md --embed-key deliverable_content \
  --seven-check /app/output/seven_check.json --status complete
# → {"ok":true,"contract_keys_total":8,"contract_keys_empty":[],"embed_chars":12480,
#    "seven_check_verdict":"pass"}                                       ← 示意
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
| scripts/seven_check.py | 三项机检：章节完整性 / 路线可执行性 / 时间表-内容一致性（闸门状态枚举） |
| scripts/docx_build.py | 分片合并 → 可编辑 docx + markdown（stdlib 兜底最小 docx） |
| scripts/render_preview.py | docx → PDF/PNG 预览（如实记录渲染引擎或 no_renderer） |
| scripts/build_result.py | result.json 组装（契约键提取 / --embed-file 内嵌 / 自检输出） |
| examples/example_input.json | 示意输入结构（非正式案例结果） |

## 失败处理与自查
- 全部脚本三级容错：脏输入/缺文件不崩溃，输出 verdict=error/skipped 而非空结果。
- 自查方法：跑完 Step 4 后核对 SKILL.md「交付自查清单」；build_result 自检 JSON 的 contract_keys_empty 必须为空、embed_chars 必须 > 0、seven_check_verdict 须为 pass 或已登记说明。

## 维护
- v4（2026-11-16）：补 83 公式缺失要素——新增 seven_check.py 三项机检（七要素章节完整性 / route.jsonl 技术路线可执行性 / 时间表-内容一致性），闸门状态显式枚举，报告嵌入 result.json；SKILL.md 增 route.jsonl 写作规则与机检调用。详见 worklog.md。
- v3（2026-11-13）：修复 v2 最后一步组装必挂的 --embed-file 参数缺失 bug；分片防截断；计划数字白名单；脚本全容错；补最小示例与 worklog。详见 worklog.md。


## 生态贡献：依赖、安装运行、目标用户与验收

| 项目 | 说明 |
|---|---|
| 依赖与版本 | Python 3（评测沙箱 3.12；本 Skill 脚本仅用标准库，无需 pip 安装）；所有命令用 `python3` 调用。 |
| 安装与运行 | 平台把提交目录装入 `/skills/weekly-skill`；输入 `/input/case.json`（+ 材料），产物写 `/app/output/result.json`。 |
| 输入 / 输出解释 | 输入=案例标识与来源材料；输出=result.json（契约全字段 + 逐条证据 + 闸门状态 + gain_evidence + efficiency + exceptions）。 |
| 目标用户与场景 | 需「产出可直接用、且每条结论都能回到原文核对」的作者与审阅者；用于成稿前的自检与交付留痕。 |
| 验收方式 | ①契约键一个不缺且 JSON 可解析；②每条论断带可回证的 evidence 与来源位置；③闸门状态显式、非 enforced 有 gate_note；④gain_evidence 含基线与当前两套指标及削减量。 |
| 常见问题 | 证据回证失败→换原文短引文而非改写；材料缺失→按题面要求登记缺口而非补零；机检不过→修一轮并如实登记结论。 |
| 已知限制 | 增益对照为同输入自比，量化的是核对工作量与漏检率，不等同于跨模型横向评测。 |
| 失败处理 | 任一步异常：写盘已有产出、status 如实降级、exceptions 记录失败点与已尝试回退链；机检结论照实记录且退出码恒 0。 |
| 复用建议 | 直接复用 scripts/；证据与闸门的字段结构可套用到同类「产出+核对」任务。 |
| 版本与维护 | 见 worklog.md 版本小节；结构变更时同步本表与 SKILL.md 输出字段说明。 |

## 最小可运行自检清单（复制即跑）

```bash
python3 -c "import sys;print(sys.version)"   # 1) 解释器可用
ls scripts/                                   # 2) 脚本在位
python3 scripts/gain_evidence.py --help       # 3) 增益脚本可执行
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"  # 4) 产物可解析且键齐全
```
