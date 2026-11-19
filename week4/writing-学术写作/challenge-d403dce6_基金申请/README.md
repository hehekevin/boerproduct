# acwrite-grant — 基金申请书写作

「学术写作」赛道 · 基金申请书写作（challenge-d403dce6）参赛 Skill。

## 用途
从申报指南/前期成果/文献材料逐章生成基金申请书各节：立项依据、科学问题与研究目标、研究内容、技术路线、创新点、研究基础与可行性、预算。四向对齐表（目标↔内容↔路线↔考核指标）保证逐条对应；创新点用 vs_existing 对照写实；预算用数字-来源核对表管住编造；关键论断带来源映射，材料不足标缺口不编造；同输入双跑（正常档 vs 退化档）产出可核验的**使用增益证据**。

## 快速开始（Harness 执行环境）
1. 读取 `/input/case.json` 与 `task.md`，抄下 `output_contract` 全部字段名，立即写 `/app/output/result.json` 骨架。
2. 按 `SKILL.md` Step 0–5 顺序执行；脚本目录用**校验式**定位（命中必须同时含 `build_result.py` 与 `gain_evidence.py`，避免多个 skills 挂载时选错目录）：
   ```bash
   SD=""
   # ① 平台约定挂载点（题面：evaluator 把 Skill 装入 /skills/weekly-skill）
   if [ -f "/skills/weekly-skill/scripts/align_check_grant.py" ]; then SD="/skills/weekly-skill/scripts"; fi
   # ② 兜底扫描：命中条件是本技能独有的标志文件 + 增益脚本，避免选到别的包的 scripts
   if [ -z "$SD" ]; then
SCRIPT_DIR=""
for d in /skills/weekly-skill/scripts ./scripts scripts; do
  if [ -f "$d/align_check_grant.py" ]; then SCRIPT_DIR="$d"; break; fi
done
if [ -z "$SCRIPT_DIR" ]; then
  SCRIPT_DIR=$(find /skills /app -type d -name scripts 2>/dev/null | while read -r d; do [ -f "$d/align_check_grant.py" ] && echo "$d" && break; done)
fi
[ -n "$SCRIPT_DIR" ] || SCRIPT_DIR="./scripts"   # 兜底：相对路径 + 如实登记，不臆造路径

       if [ -f "$d/align_check_grant.py" ] && [ -f "$d/gain_evidence.py" ]; then SD="$d"; break; fi
     done
   fi
   # ③ 按标志文件反查目录
   if [ -z "$SD" ]; then
     SD=$(dirname "$(find /skills /app /opt . -name align_check_grant.py 2>/dev/null | head -1)")
     if [ ! -f "$SD/align_check_grant.py" ]; then SD=""; fi
   fi
   # ④ 相对路径兜底；仍找不到则按协议第 7 条如实登记，不臆造路径
   if [ -z "$SD" ] && [ -f "./scripts/align_check_grant.py" ]; then SD="./scripts"; fi
   if [ -z "$SD" ]; then SD="scripts"; fi
python3 $SD/merge_chapters.py --chapters-dir /app/work/chapters --out /app/work/draft.json
python3 $SD/docx_build.py /app/work/draft.json --out-docx /app/output/grant.docx --out-md /app/output/grant.md
python3 $SD/align_check_grant.py --alignment /app/work/alignment.jsonl --routes /app/work/routes.jsonl \
  --draft /app/output/grant.md --budget /app/work/budget_ledger.jsonl --out /app/output/align_check.json
# → {"verdict":"pass","goals":3,"budget":6,"types":[],"checks":[{item,template_value,applied,match}…],"gates":[…]}
python3 $SD/gain_evidence.py --work /app/work --out /app/output/gain_evidence.json \
  --efficiency-out /app/output/efficiency.json --case /input/case.json --draft /app/output/grant.md
# → {"normal":{"chapter_completeness_rate":1.0,"innovation_vs_existing_covered":3,…},
#    "degraded":{"chapter_completeness_rate":1.0,"innovation_vs_existing_covered":0,…}}
```

## 依赖
- Python 3.8+，**零外部依赖**（全部脚本仅用标准库）。
- 可选增强：python-docx（docx 构建质量更好）、PyMuPDF（PDF 提取）、openpyxl（xlsx）、soffice（渲染预览）。
- 任一可选库缺失时脚本自动降级（stdlib 兜底），降级事实写入 changelog/uncertainty，不阻塞交付。

## 文件清单

### 核心
| 文件 | 作用 |
|---|---|
| `SKILL.md` | 完整工作流（5 步线性）、强制执行协议 7 条、异常处置表、最小调用示例、交付自查清单（142 行） |
| `README.md` | 本文件：用途/调用/依赖/清单/方法/边界/生态贡献/维护 |

### 脚本（8 个，纯标准库，失败路径退出码恒 0）
| 脚本 | 作用 |
|---|---|
| `scripts/extract_materials.py` | 材料提取（docx/pdf/txt/md/csv/tsv/xlsx/json/html/rtf/bib/tex/pptx），产出带 `[SRC:mid:loc]` 锚点的纯文本 + manifest |
| `scripts/fact_ledger.py` | 事实台账 `build` / 稿件数字回证 `check` / 前期基础抽取 `prior`（三个子命令） |
| `scripts/merge_chapters.py` | 逐章合稿 → draft.json（.md/.json 片段均支持） |
| `scripts/docx_build.py` | draft.json → 可编辑 .docx（python-docx 优先，缺库走 stdlib 最小 docx）+ 同源 .md |
| `scripts/align_check_grant.py` | 四向对齐 + 禁用修辞 + 创新点对照 + 预算核对；输出逐条 checks 三元组与 gates 状态；支持 `--ablate` 退化档 |
| `scripts/build_result.py` | result.json 组装与逐章回填；7 章 embed_gate；题面输出要求字段语义映射 `output_contract_map` |
| `scripts/gain_evidence.py` | **同输入双跑**（正常档 vs 退化档）增益证据 + 效率计数 + 机制→指标映射 + 边界声明 |
| `scripts/render_preview.py` | docx/md → PDF/PNG 渲染预览，无渲染器时如实标 `no_renderer` |

### 可复用资源（供他人直接用于自己的申请）
| 文件 | 对应生态贡献点 |
|---|---|
| `resources/grant_toolkit.md` | **要素清单**（七要素写什么/不写什么）+ **一致性检查表**（四向对齐逐格核对）+ evidence_map / budget_ledger / innovation_vs_existing 三张表的落盘格式与字段纪律 + 禁用修辞词表 + 12 项自查评分表 |
| `resources/score_sheet.md` | **评分表**（五维度自评 + 增益指标填写表 + 异常场景逐条处置表 + 交付前十问），评审人视角自检 |
| `resources/practice_set.md` | **题集**（3 道自拟练习题：材料残缺型/数字诱导型/一致性陷阱型）+ 自出题建议表；**不含任何预制答案** |
| `examples/example_input.json` | **示例材料**（draft.json 结构示意，标注"示意"，非正式案例结果） |

## 方法要点
- **逐章分批防截断**：申请书全文禁止单响应写完；每章落盘即回填 result.json（--append），中断也有半成品可交付。
- **7 章全量嵌入 + embed_gate**：终稿组装把 7 章逐章以独立键全文嵌入 result.json（结构化优先），embed_gate 逐章记录 embedded/not_found/unreadable；缺章自动写入 uncertainty，下游不得宣称全稿已核对。
- **机械校验逐条可复核**：align_check 输出逐条 {item, template_value, applied, match} 三元组与 gates 状态（enforced/skipped_not_provided/not_found/unreadable），未运行的检查显式写 gate_note，未跑 ≠ 通过；全部嵌入 result.json。
- **创新点 vs_existing 对照表**：innovation_vs_existing.jsonl（claim/vs_existing_who/difference/why_can_win/evidence_locator）随正文嵌入 result.json，缺对照机检即 fail。
- **研究基础逐条摘录**：每条前期成果以 kind=prior_work 逐字摘录（≤40字）+ location 进 evidence_map，正文挂 source_id；已完成/拟开展二态分清。
- **数字-来源核对**：预算金额、样本量等数字落稿前先入 budget_ledger/evidence_map；无来源金额只写占位符；机检不过必须删或降级为假设。
- **四向对齐**：每个 goal 必须在 contents/routes/metrics 有对应项；指标可考核；路线含输入输出与风险备选。
- **同输入双跑增益证据**：`gain_evidence.py` 对同一份产物跑两遍——正常档（全机制）与退化档（移除对照表/预算台账/逐字台账，并 `--ablate innovation,budget` 关闭强制检查），输出逐项对照指标（章节完整率／创新点 vs_existing 覆盖数／预算可溯源率／需人工核对条目数／步骤数）+ 两遍真实运行记录（cmd/returncode/stdout/report）+ 机制→指标映射 + 边界声明。**数字必须由脚本实跑产生，禁止手写。**
- **效率可数**：`efficiency.json` 记录 pipeline 阶段数、模型写步数、往返轮次、待人工核对条目数与复现命令；不编造秒数（耗时由平台记录）。
- **题面对齐字段语义**：`build_result.py` 产出 `output_contract_map`，把题面输出要求表三行（目标产物／事实与来源映射／版本与边界）与 5 个点名要素（各章正文／创新点对照／前期基础／预算／待确认项）逐条对照字段承载情况与 filled 状态；未 filled 的契约字段自动写入 uncertainty。
- **诚实降级**：渲染器/解析库缺失如实记录，不伪造状态；status 四级（complete/partial/failed/blocked）只反映实际完成度；**所有脚本失败路径退出码恒 0**，判定一律看报告里的 verdict/fail/problems，脚本不得中断交付链。

## 适用边界
- 聚焦从给定材料到申请书章节稿与溯源，不做文献检索（只用材料内文献）、不做科研绘图算法。
- 材料外的事实一律不新增；学科惯例改动记 changelog。
- 退化档是**同产物的结构退化模拟**，不是平台的 base-agent 对照实验；平台官方对照由平台另行提供，本技能不冒充。

## 生态贡献
| 贡献点 | 落点 | 说明 |
|---|---|---|
| 文档完整性 | `SKILL.md` + `README.md` + `resources/` | SKILL.md 142 行含强制协议/流程/异常表/示例/自查清单；README 含用途/调用/依赖/全清单/方法/边界/维护 |
| 输入材料清单 | `SKILL.md` Step 1 + `scripts/extract_materials.py` manifest | 支持 14 种格式，逐材料登记 id/路径/类型/字符数/sha1/是否提取成功 |
| 模板映射 | `resources/grant_toolkit.md` 第四~七节 | 要素→章节→台账字段→result.json 键 的完整映射表 |
| 示例 | `examples/example_input.json` + `SKILL.md` 最小调用示例 | 全部标注"示意，非正式案例结果" |
| 适用范围与限制 | 本文"适用边界" + `SKILL.md` 异常处置表 | 含 8 类异常场景的处置方式 |
| 维护信息 | 本文"维护"节 + `resources/grant_toolkit.md` 第十节 | 版本、扩展点（新增格式/预算科目/新检查项）、退出码契约 |
| 要素清单 | `resources/grant_toolkit.md` 第一节 | 七要素写什么/不写什么/自检问题，可直接套用 |
| 一致性检查表 | `resources/grant_toolkit.md` 第二~五节 + 脚本 | 四向对齐逐格表 + 三张台账落盘格式，可直接套用 |
| 题集 | `resources/practice_set.md` | 3 道自拟练习题 + 自出题建议表，无预制答案 |
| 评分表 | `resources/score_sheet.md` | 五维度自评 + 增益指标填写 + 异常处置 + 前十问 |
| 示例材料 | `examples/example_input.json` | draft.json 结构示意 |
| 案例与 Benchmark | `gain_evidence.py` 同输入双跑对照 | 正常档/退化档逐项指标可复现；复现命令写在 `gain_evidence.json` 的 `reproduce` 字段 |
| 写作方法沉淀 | `SKILL.md` 各章写法要点 + `resources/grant_toolkit.md` | "别人做到哪→还差什么→为什么是申请人→为什么是现在" 等可迁移写法 |
| 真实应用价值 | 字段语义对照 + 待确认项机制 | 交付物可被申请人直接接手改，缺口显式列出而非猜测 |

## 维护
- 版本 2.2（使用增益 + 创新增益 + 生态贡献补强版）。
- 新增材料格式时扩展 `scripts/extract_materials.py` 的解析函数；预算科目变化只影响 budget_ledger 内容，脚本无需改动。
- 新增检查项：在 `scripts/align_check_grant.py` 的 `checks` 列表追加 `{item, template_value, applied, match}`，并同步 `resources/grant_toolkit.md` 第八节。
- 退出码契约：所有脚本失败路径返回 0，判定看 `verdict`/`fail`/`problems`；勿用退出码判断成败。
