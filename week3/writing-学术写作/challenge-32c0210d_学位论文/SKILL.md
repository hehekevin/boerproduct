---
name: weekly-skill
description: 学位论文与长文档写作技能：章节规划带字数预算与论证任务，跨章节登记簿（术语/符号/定义/结论）保持数万字一致，广度优先全章最小合格版先行再加深，逐章分批写并写完即回填，主产物内嵌 result.json，并附可运行的双臂对照实验台产出增益证据。Use when the case asks to plan or draft a thesis / long multi-chapter academic document, maintain cross-chapter consistency (terms, symbols, definitions, conclusions), and deliver an editable full draft with verifiable evidence.
---

# weekly-skill — 学位论文长文档（广度优先 · 登记簿制 · 主产物内嵌 · 增益可证）

### 增益证据与效率计数（回填 result.json）
必须是**本次运行真跑出来的数字**，不是文字声明：
```bash
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --baseline
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --write
```
- 第一条：基础模式对照——模拟「不做证据登记/不做逐条回证」的路径，统计源材料里有多少实体与数值会变成不可核对项（需人工逐条核对的规模）。
- 第二条：当前模式实测——证据登记数、证据逐字回证率、三元组 match 通过率、需人工核对条目数，并计算相对基线的削减量；`--write` 写入 `result.json.registry_evidence`（含 `baseline_comparison.reduction` 与 `efficiency` 计数；若本包另有脚本写 `gain_evidence`，两者互补不覆盖）。
- 机检/闸门失败**一律 verdict 照实记录、退出码恒 0**：修一轮，仍不过则如实登记并继续交付，禁止以非零退出码结束会话。

## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 8 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。

0. 每步一个写盘动作：协议（骨架落盘）、规划（chapter_plan.jsonl）、每写完一章（draft_all.json 增量更新 + 立即回填 result.json）、每次机检（check json）、组装（最终 result.json）——每个执行步骤必须伴随至少一次真实写盘，禁止连续多步只读不写。

1. 第0步先落盘骨架：读完 /input/case.json 与题面后，第一个写盘动作就是在 /app/output/result.json 写入骨架：case_id 取自 case.json；键名严格按 case.json 或 task.md 中 output_contract 声明的每个字段生成（列表或 {name:desc} 两种形态都要识别；当前无法完成的字段值填 null，绝不省略键）；status 填 "partial"。此后任何时刻 /app/output/result.json 必须存在且 JSON 可解析。

2. 字段一个不缺：最终 result.json 必须包含 output_contract 的全部键。某项确实无法产出时，保留键并填 null，同时把原因写入 uncertainty，不得删除键、不得编造数据。

3. 主产物嵌入 result.json：论文全文（Markdown）必须完整写入 result.json 的 deliverable_content 键（--embed-file），同时另存 thesis.docx/thesis.md。result.json 里只有文件指针而无正文内容 = 不完整交付。

3a. **逐章分批写 + 写完即回填（本题生命线）**：加深阶段每章每次响应只写 ≤1500 字，写完一章立即用该章内容更新 draft_all.json 并回填 result.json 的 deliverable_content，再写下一章。禁止把全文攒到最后一次响应一次性写（16384 token 截断=全文丢失）。

4. **广度优先 + 预算保护（本题生死线）**：先让**全部章节以最小合格版本存在**（每章 300-500 字骨架成文），再对高价值章节加深。禁止在单一章节耗尽预算。模型请求已用超过 48 次或运行时间超过 700 秒时，立即停止新增处理，用现有中间结果完成 result.json 并收尾。每次写 result.json 都覆盖为当前最新完整状态。

5. 最终写盘前自检：JSON 可解析、output_contract 字段一个不缺、case_id 与输入一致、status 如实、论文全文已嵌入 deliverable_content。自检不过先修复再交付。

6. 失败也要交付：处理中断或失败时，仍写 result.json（status="failed" 或 "partial"，写明中断位置与已完成章节），绝不让 /app/output 缺少 result.json。

7. **所有脚本失败路径退出码恒为 0**：校验脚本发现问题只写进报告的 verdict/fail 字段并照实记录，绝不中断交付链。本地 CI 需要非零码时加 `--strict`。同理，脚本内部所有异常一律捕获后写报告，不得抛栈终止。

## 流程（5 步线性执行）

脚本定位（优先本 Skill 自己的目录，避免抓到同一 /skills 下别的技能的 scripts）：
```bash
SD=$(find /skills -maxdepth 4 -type d -path '*/weekly-skill/scripts' 2>/dev/null | head -1)
SCRIPT_DIR=""
for d in /skills/weekly-skill/scripts ./scripts scripts; do
  if [ -f "$d/build_result.py" ]; then SCRIPT_DIR="$d"; break; fi
done
if [ -z "$SCRIPT_DIR" ]; then
  SCRIPT_DIR=$(find /skills /app -type d -name scripts 2>/dev/null | while read -r d; do [ -f "$d/build_result.py" ] && echo "$d" && break; done)
fi
[ -n "$SCRIPT_DIR" ] || SCRIPT_DIR="./scripts"   # 兜底：相对路径 + 如实登记，不臆造路径

[ -z "$SD" ] && SD=./scripts
```
下文 `$SD/xxx.py` 均指此目录，绝不假设具体安装路径。

### Step 0 读契约、落骨架（最先做）
`cat /input/case.json` 与题面 → 抄下 output_contract 全部键名与 case_id → **立即写 /app/output/result.json 骨架**（全部键+case_id，未完成字段填 null，status="partial"）。

### Step 1 材料盘点与登记簿初始化（2 次脚本）
```bash
python3 $SD/extract_materials.py --input /input --outdir /app/work/extracted
python3 $SD/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
```
constraints.json 记：总字数与各章比例、模板章节、术语表。登记簿 /app/work/registers.jsonl 初始化：`{"kind":"term|symbol|definition|conclusion","key":...,"canonical":...,"basis":"M01:p3"}`（已有提纲/摘要时先抽取已有项）。

### Step 2 章节规划 + 全章最小版（1-2 次响应，产出 /app/work/chapter_plan.jsonl + /app/work/draft_all.json）
- chapter_plan.jsonl：`{"ch":"3","title":...,"role":"回答研究问题Q2","word_budget":8000,"evidence":["M03"],"outputs":"结论C3.1"}`；字数预算合计=总字数。
- **第一轮：全部章节最小合格版**——每章标题+300-500 字成文（含该章核心论断与证据引用），一次性写进 draft_all.json。绪论-文献综述-方法-结果-讨论-结论骨架齐全。
- **第二轮（预算允许时）**：按 word_budget 加深高价值章节（方法、结果、结论优先），术语/符号/结论先查登记簿再入册。
- 每章论断挂 evidence_map（locator+逐字摘录≤30字）；图表编号按章（图3-1）并在正文引用；材料不够的章节留标题+缺口说明，不编造。

### Step 3 构建与机检（3-4 次脚本）
```bash
python3 $SD/docx_build.py /app/work/draft_all.json --out-docx /app/output/thesis.docx --out-md /app/output/thesis.md
python3 $SD/fact_ledger.py check --draft /app/output/thesis.md --ledger /app/work/fact_ledger.jsonl --sources /app/work/extracted --out /app/output/fact_check.json
python3 $SD/cross_check.py --registers /app/work/registers.jsonl --draft /app/output/thesis.md --out /app/output/cross_check.json
python3 $SD/completeness_check.py --draft /app/output/thesis.md --plan /app/work/chapter_plan.jsonl --out /app/output/completeness_check.json
```
fail 项修复一轮后重跑；仍 fail 的项如实写入 uncertainty（术语别名/符号冲突/结论失配必须修）。fact_ledger check 会抓三类：材料中查不到的数值、材料中不存在的 DOI、正文引用了材料里没有的文献编号（[n] 不在材料参考文献索引内）。
completeness_check 输出逐条 {item, template_value, applied, match} 三元组：摘要/目录/计划各章/参考文献/致谢一个不缺，图x-y/表x-y 编号有序且正文有引用。闸门状态只有四种：enforced（已运行且有据）/ skipped_not_provided（输入未提供，如实跳过）/ not_found（应存在但缺失）/ unreadable（读取失败）——没跑 ≠ 通过；任何 skipped/not_found/unreadable 的闸门必须在 result.json 的 uncertainty 写 gate_note「下游不得宣称已核对」。

### Step 4 渲染、组装、自检（2 次脚本 + 自检）
```bash
python3 $SD/render_preview.py --src /app/output/thesis.docx --outdir /app/output/previews
python3 $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact thesis.docx --artifact-md thesis.md \
  --evidence /app/work/registers.jsonl --fact-check /app/output/fact_check.json \
  --consistency /app/output/cross_check.json --structure-check /app/output/completeness_check.json \
  --render /app/output/previews/render_log.json --gain-evidence /app/output/gain_evidence.json \
  --status complete --embed-file /app/output/thesis.md --embed-key deliverable_content \
  --changelog '取舍记录' --needs-human '待确认项' --gaps '材料缺口'
```
build_result 按题面三段语义装配：目标产物（deliverable / deliverable_content / structure 逐项给出摘要·目录·各章·图表目录·参考文献·致谢的 present 状态）/ 事实与来源映射（evidence_map / fact_check / consistency_check / structure_check / source_mapping）/ 版本与边界（version_boundary{changelog, uncertainty, needs_human, material_gaps} / status / gate_notes）。自检（协议第5条）：JSON 可解析 / 契约键不缺 / case_id 一致 / thesis.md 全文已嵌入 deliverable_content / status 如实。

### Step 5 增益证据（可选但强烈建议，成本 1 次脚本）
```bash
python3 $SD/gain_ablation.py --case /app/work/gain_case --both --out /app/output/gain_evidence.json
```
把本次真实产物整理成 /app/work/gain_case/（case.json + materials.txt + chapter_plan.jsonl + registers.jsonl + chapters/NN.md + references.md + acknowledgments.md，见 README），跑完整臂与退化臂两遍，得到同输入对照：章节完整率 / 跨章编号一致率 / 参考文献覆盖 / 需人工核对条目数 / 步骤数，并附机制→指标映射与边界声明。gain_evidence 同时提供 efficiency 计数（steps / write_events / elapsed_seconds）。用 --gain-evidence 传入 build_result 即嵌入 result.json。

## 异常处置

| 情形 | 处置 |
|---|---|
| 材料只够写部分章 | 规划全骨架，全章最小版仍要写全（可写为缺口说明+材料需求），有据章节加深 |
| 前章结论在后章被推翻 | 按材料更强证据取新口径，两处联动改；conflict 记录 |
| 术语多版本 | 选学科规范写法入册，aliases 记录变体 |
| 导师意见与材料冲突 | needs_supervisor；不改数据事实 |
| 脚本缺失/报错 | 全部异常捕获、如实登记；用现有中间结果继续走协议第4/6条 |
| 接近预算上限 | 立即收尾：已有章节组装 result.json，未完成章节在 chapter_plan 标注 |
| 校验脚本报 fail | 不中断：读报告的 fail 列表 → 修一轮 → 重跑 → 仍 fail 写 uncertainty |

## 交付自查清单

- [ ] result.json 含 case_id 与 output_contract 全部键；deliverable_content 为论文全文
- [ ] 全部章节有最小合格版（无空标题）；高价值章节已加深；摘要/目录/参考文献/致谢齐全（completeness_check 三元组全 match）
- [ ] structure 段六项（摘要·目录·各章·图表目录·参考文献·致谢）present 状态如实
- [ ] registers 四类登记齐全；cross_check 与 completeness_check pass 或 fail 项已入 uncertainty
- [ ] 每章论断挂 evidence_map；图表编号跨章有序且正文有引用
- [ ] fact_check pass；thesis.docx/md 可编辑
- [ ] gain_evidence 已嵌入（含两臂对照真实数字、机制映射、边界）；efficiency 计数已给
- [ ] status/uncertainty/changelog/needs_human/material_gaps 如实
