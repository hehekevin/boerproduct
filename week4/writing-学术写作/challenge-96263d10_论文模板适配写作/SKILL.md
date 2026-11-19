---
name: acfmt-template
description: 学术格式与模板适配技能：从模板/格式要求文件抽取可逐项核对的规格清单（页边距/栏数/字号/行距/题注/文献样式，条条带来源锚点），把稿件按清单机械适配为可编辑成品（标题重编号、题注前缀重编号、交叉引用同步、docx 落页边距/栏数/字号/行距），再由同一机检器逐项复验三元组 {item,template_value,applied,match}，并做内容单元保真对比（转得全）与同输入双臂消融取证。Use when the case asks to adapt a manuscript to a target academic template, extract format specs from template files, check heading/caption/reference format, or verify conversion fidelity and export readiness.
---

# acfmt-template — 模板适配（认得准 · 排得对 · 转得全 · 交得出）

核心思想：适配是**受规格约束的改写**——目标模板的每条规格先变成可机器核对的清单条目（带来源锚点），成品再被同一机检器逐项复验。交付四件套：① 可编辑成品 adapted.docx + adapted.md；② 规格-来源映射 spec_claims（每条规格可回溯模板原文）；③ 机检报告 format_report（逐项三元组 + 闸门状态）；④ 保真报告 fidelity_report（内容单元不丢不改）+ result.json（status/uncertainty/changelog 如实）。

### 增益证据与效率计数（回填 result.json）
必须是**本次运行真跑出来的数字**，不是文字声明：
```bash
python3 scripts/gain_evidence.py --result /app/output/result.json --draft /app/output/adapted.md \
  --checklist /app/work/checklist.json --docx /app/output/adapted.docx --write
python3 scripts/gain_evidence.py --selftest
```
- 第一条内部做三件事（同输入、同一校验器）：① normal/ablate 双臂各跑一遍，FAIL 数差即被关闭机制的机器判定增量；② 把污染反例（重复标题编号/题注跳号/孤立引用/必需章节改名）注入**副本**复跑，验证 normal 臂抓错；③ baseline（无规格无机检，全人工）vs 当前模式的人工核对条目削减量。结果写 `result.json.gain_evidence`（含 mechanism_metric_map + boundary + failure_conditions）。
- 第二条自检最小用例，结论照实输出；**FAIL 也 exit 0**，修一轮后如实登记。
- 机检/闸门失败一律 verdict 照实记录、退出码恒 0：修一轮，仍不过则如实登记并继续交付。

## ⚠️ 强制执行协议（每次运行先读完本节再动手，顺序不可调换）

1. **抄契约**：第一动作 `cat /input/case.json`，逐字抄下 `output_contract` 全部字段名与 `case_id`。result.json 必须含全部字段，一个不缺（无值先置 null）。
2. **立即落骨架**：读完契约立刻用 build_result.py 写骨架 result.json（status="in_progress"）。此后任何时刻中断都完整可解析。
3. **读真实文件**：模板、原稿一律读文件本体（docx 用脚本解包），不按文件名/标签猜内容；材料不足/冲突照实登记，不补造规格。
4. **广度优先**：先让全部必需章节有一版适配结果，再逐项打磨；禁止把预算耗在单章排版而让其他章节缺失。
5. **熔断**：累计约 48 次模型请求或 700 秒即停止新增工作，直接执行收尾（合并→机检→保真→gain_evidence→build_result），status 如实。
6. **写盘自检**：每次写 JSON/文本后自检可解析；失败重写一次，再失败改纯文本兜底并记 uncertainty。
7. **失败也交付**：任何异常不允许空手退出。partial/failed/blocked 也要有 result.json + 已完成的可编辑稿件。

## 线性流程（5 步，按序执行）

### Step 1 — 契约与骨架
```bash
ls -la /input/ && cat /input/case.json
cat /input/task.md 2>/dev/null || true
python3 scripts/extract_template.py --input /input --out /app/work/checklist.json
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --status in_progress
```
- 打开 checklist.json **逐条人工复核**：规则抽取可能漏抓/误抓（如"小四"漏抓、两条来源冲突）。补抓/修正直接编辑 items，每条保留 source 锚点；无法裁决的冲突记 uncertainty，不擅自取舍。
- 模板文件缺失：以 task.md 中的格式要求为准；再无则 checklist 只含 defaulted 通用项并如实标注，**下游不得宣称规格已核对**。

### Step 2 — 原稿清单与适配准备
```bash
python3 scripts/inventory.py scan --doc <原稿> --out /app/work/inv_source.json
```
- 通读原稿与 checklist，产出 `/app/work/sections/S##.json`（每文件一个章节，结构见 examples/example_input.json）：段落照抄原稿文字（不删不改写事实），题注/编号/文献先保持原样——重编号交给 adapt_build 机械完成。
- 材料里没有的内容不新增；需要模板明文但模板没写的地方，[待确认] 并写 notes_for_human。

### Step 3 — 按清单适配组稿
```bash
python3 scripts/adapt_build.py --sections-dir /app/work/sections --checklist /app/work/checklist.json \
  --out-docx /app/output/adapted.docx --out-md /app/output/adapted.md --adapt-log /app/work/adapt_log.json
```
- 机械应用：标题按层级连续重编号（1/1.1/2…）；题注按模板前缀重编号（图1/表1…），正文交叉引用同号唯一时自动同步（歧义留痕到 crossref_ambiguous）；docx 落页边距/栏数/字号/行距（sectPr+styles）。
- 对照 checklist 检查 adapt_log.applied_specs：**清单有、脚本没应用的规格**（如三线表、页眉页脚）由 Agent 手工改 S##.json 后重跑本步，或如实记 uncertainty「本项未适配，需人工」。

### Step 4 — 双校验（fail 必须修复一轮）
```bash
python3 scripts/format_check.py --draft /app/output/adapted.md --checklist /app/work/checklist.json \
  --docx /app/output/adapted.docx --out /app/output/format_report.json
python3 scripts/inventory.py scan --doc /app/output/adapted.md --out /app/work/inv_adapted.json
python3 scripts/inventory.py compare --a /app/work/inv_source.json --b /app/work/inv_adapted.json --out /app/output/fidelity_report.json
```
- format_report 逐项三元组 {item, template_value, applied, match}：fail 项回 S##.json 修复后重跑（只改对应文件）；warn/skipped 项如实登记，gate_note「未运行不得宣称已核对」。
- fidelity_report：missing=内容单元丢失、changed=被改写、citations_dropped/formulas_lost=引用公式未保留。**正文、图表、公式、脚注、文献一个都不能丢**；有意删改（如题注重编号产生的 changed）在 changelog 说明，其余必须还原。
- 回填骨架：`build_result.py --format-report … --fidelity … --status partial`。

### Step 5 — 增益对照与收尾（主产物全量嵌入 result.json）
```bash
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact /app/output/adapted.docx --artifact-md /app/output/adapted.md \
  --checklist /app/work/checklist.json --format-report /app/output/format_report.json \
  --fidelity /app/output/fidelity_report.json --adapt-log /app/work/adapt_log.json \
  --sections-dir /app/work/sections --status complete \
  --changelog '关键决策; 降级事实; 模板冲突裁决'
python3 scripts/render_preview.py --src /app/output/adapted.docx --outdir /app/output/previews
python3 scripts/gain_evidence.py --result /app/output/result.json --draft /app/output/adapted.md \
  --checklist /app/work/checklist.json --docx /app/output/adapted.docx --write
```
- **顺序**：先 build_result 产出 result.json（骨架/回填全部产物），再 gain_evidence `--write` 追加 gain_evidence 键（该键唯一写入方是 gain_evidence.py；build_result 不写也不删它）。
- **嵌入要求**：result.json 必须含 `sections`（结构化章节）+ `adapted_text`（全文）+ `spec_claims`（每条规格 kind/template_value/evidence≤40字逐字/location）+ `format_check.results`（逐项三元组）+ `fidelity_check` + `section_check`——评分器不开附件即可核对。
- status 四级：complete（全链路）/ partial（部分失败，写明环节）/ failed（无法产出）/ blocked（模板或原稿缺失无法开工，写明缺什么）。
- uncertainty 必含：模板缺口与冲突、未适配规格、保真 changed 清单、渲染/导出限制、[待人工确认] 条目。
- 熔断触发时跳过消融复跑，直接本步收尾（gain_evidence 仍可用 --selftest 快速取证）。

## 异常处置表

| 情形 | 处置 |
|---|---|
| 模板文件缺失/不可读 | gates 如实记 not_found/unreadable；以 task.md 为准抽规格；再无则 defaulted 并记 uncertainty |
| 两条模板规格冲突 | 不擅自取舍；取任务指定口径，否则并列记录 conflicts + uncertainty，成品按所选口径交付并在 changelog 说明 |
| 题注交叉引用歧义（同号多处） | adapt_build 留痕 crossref_ambiguous，不机械替换；人工逐一核对后改 S##.json 重跑 |
| 修复后机检仍 fail | 如实登记 fail 计数与条目，status=partial；禁止以非零退出码结束 |
| fidelity missing/changed | 逐条核对：无意的还原重跑；有意的（题注重编号）changelog 说明；丢失的单元必须找回 |
| python-docx 缺失 | adapt_build 走 stdlib 精确 XML（本就零依赖），无需降级动作 |
| sections JSON 写坏 | adapt_build 跳过坏文件留痕 skipped；重写一次，再失败改纯文本兜底 |
| 原稿含扫描件/图片 | inventory 如实按文本层登记；图片单元缺失记 fidelity 限制，不伪造 |
| 预算将尽（≥48 次或 ≥700 秒） | 立即 Step 5 收尾，status 如实 |

## 最小调用示例（示意，非正式案例结果）

```bash
python3 scripts/extract_template.py --input /input --out /app/work/checklist.json
# → {"ok":true,"items":9,"conflicts":1,"required_sections":["摘要","方法","结果","结论","参考文献"]}
python3 scripts/inventory.py scan --doc /input/manuscript.md --out /app/work/inv_source.json
# → {"ok":true,"cmd":"scan","total":14,"verdict":null}
python3 scripts/adapt_build.py --sections-dir /app/work/sections --checklist /app/work/checklist.json --out-docx /app/output/adapted.docx --out-md /app/output/adapted.md
# → {"ok":true,"builder":"stdlib-spec-docx","sections_merged":5,"spec_applied":{"margin_cm":2.54,...}}
python3 scripts/format_check.py --draft /app/output/adapted.md --checklist /app/work/checklist.json --docx /app/output/adapted.docx
# → {"verdict":"pass","fail":0,"items":["sections_complete:pass","heading_numbering:pass",...]}
python3 scripts/gain_evidence.py --selftest
# → {"selftest":"PASS","detail":{...}}
```

## 交付自查清单

- [ ] result.json 含 case_id 与 output_contract 全部字段；任何时刻可解析（先骨架后回填）
- [ ] checklist 每条规格带来源锚点；冲突未擅自取舍并列入 conflicts/uncertainty
- [ ] adapted.docx/adapted.md 章节层级完整、可继续编辑；adapt_log 可复核每条机械适配
- [ ] format_report 逐项三元组齐全；fail 已修一轮或如实登记；skipped 带 gate_note
- [ ] fidelity 无 missing/意外 changed；引用、公式、脚注全部保留
- [ ] gain_evidence 为真跑数字：双臂 fail 差 + 污染捕获 + 基线削减量
- [ ] status/uncertainty/changelog 如实；未编造规格、渲染或导出状态
