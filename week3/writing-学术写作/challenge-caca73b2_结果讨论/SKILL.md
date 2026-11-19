---
name: acwrite-results
description: 结果与讨论章节写作技能：从数据表/图/图注/统计输出可靠读数，按图序写"只陈述观察"的结果段，讨论段每条论断带【依据】内联标注绑定本研究数据或具体文献，因果/相关边界受控、局限写到方法样本测量层面；交付数字-来源逐条核对表与图表交叉引用完整性校验，全部数值回溯到图表，同输入双跑产出增益证据与效率计数。Use when the case asks to write Results & Discussion sections from data tables, figures, captions and statistical outputs, with per-number source tables, cross-reference validation, causal boundaries controlled and same-input ablation gain evidence.
---

# acwrite-results — 结果与讨论（读数不猜 · 描述解释分离 · 逐条可溯）

## ⚡ 强制执行协议（任何情况下先做完本节再进入 Stage 0）
1. **抄契约**：读完 `/input/case.json` 立即逐字抄下 `output_contract` 全部字段名与 case_id。
2. **立即落骨架**：第 1 次响应内写出含全部契约字段（值可 null）+ case_id 的骨架 result.json 到 `/app/output`。
3. **字段一个不缺**：最终 result.json 必须含契约每个字段（无法填写保持 null 并在 uncertainty 说明）。
4. **广度优先**：先让全部图表/全部章节都有低保真覆盖（骨架稿），再回头深化；禁止在单个图表上精雕导致整章残缺。
5. **熔断线**：模型请求达 **48 次**或运行达 **700 秒**即停止写作，转入收尾（校验→构建→result.json→自查），为收尾预留预算。
6. **写盘自检**：每阶段结束 `ls`+读回关键文件确认已落盘；未落盘视为未完成。
7. **失败也交付**：任何脚本/阶段失败，降级处理并如实记录，仍交付骨架+已有内容的 result.json，status 如实标 partial/failed，绝不伪造成功。
8. **校验失败不中断**：所有脚本（校验/构建/组装）的**全部失败路径退出码恒为 0**——内容级校验 fail、输入缺失或损坏、argparse 用法错误、内部未捕获异常，均如实落 verdict/error 到 stdout 与报告，不得因非零退出码放弃交付。需要 CI 语义时显式加 `--strict-exit`（仅校验类脚本支持）。

数据已在手、图表已画好，写作纪律：**结果段只陈述观察到的事实，讨论段才做解释与对照；每个数值能回溯到某张图/表/统计输出**。交付三件套：

1. **章节稿**：results_discussion.docx + .md（结果、讨论分节，图注保留原文）——**全文同时嵌入 result.json**
2. **逐条溯源**：number_source_table.json（每个数值→来源单元格/图表编号的逐条核对表）+ readings.jsonl + fact_ledger.jsonl + dclaims.jsonl（讨论结论→数据/文献位置）
3. **版本与边界**：trace_audit / fact_check / boundary_check / consistency_check 四份报告 + 待核清单 + changelog

硬规则：**图表上读不到的数值不写**；结果与讨论不互相顶替；"相关/趋势"与"因果/决定"用词受机检；讨论段每条结论句末带【依据：…】标注。

## 0. 运行环境与预算
- 输入：`/input/case.json` + `/input/task.md` + 数据表/图/图注/统计输出。读真实文件；图用视觉读取（环境 vision/PDF 渲染），不按图名猜内容。
- 工作区 `/app/work`，交付 `/app/output`。平台预算 64 请求 / 900 秒 / 16384 token；自设熔断 48 次 / 700 秒；线性 5 阶段，第 1 次响应先落骨架 result.json。

## 1. 五阶段线性流程

### Stage 1 — 定契约 + 落骨架（1 次响应内完成）
```bash
ls -la /input/ && cat /input/case.json
python3 scripts/extract_materials.py --input /input --outdir /app/work/extracted
```
- 抄 output_contract；写 constraints.json（图表清单：编号/类型/数据来源文件、目标章节：只 Results 还是 R&D、引用样式、字数范围、required_sections）。
- **同一响应内**写骨架 result.json：全部契约字段（null）+ case_id + status:"partial" + uncertainty:["skeleton"]。

### Stage 2 — 读数登记（1 次脚本 + 1-2 次响应）
```bash
python3 scripts/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
```
逐图逐表产出 `/app/work/readings.jsonl`：
`{"ref":"图1","panels":["a","b"],"values":[{"series":"对照组","point":"24h","value":"12.3±1.1","unit":"mg/L"}],"errorbar_meaning":"SD|SE|95%CI（按图注原文）","caption_quote":"图注逐字","locator":"M03:p5"}`
- 数值从数据表/图注/统计输出**逐字抄录**；从图中读数（无数据表）时注明 "estimated from figure" 并给出估读依据；误差棒含义、显著性标记（*/ns）、坐标单位按图注原文。
- 读不到/看不清的值：不猜，列入 reading_gaps；多面板图分别登记。
- 统计口径冲突（正文提及数≠表内数）：记 conflict，正文引用时注明口径。
- 同时产出 `/app/work/dclaims.jsonl` 空文件头（讨论溯源表，Stage 3 回填）。

### Stage 3 — 结果段 + 讨论段写作（1-2 次响应，产出 draft.json）
**结果段**：
- 按图序或按研究问题组织（任务指定优先）；每个图表一段或一组段落，段落主句=该图/表的核心观察。
- **只写观察**：数值+方向+幅度+显著性，来自 readings.jsonl；单位、有效数字与来源逐字一致。
- 描述与解释分离：解释性句子（"这表明…"）一律不进结果段，移到讨论。
- 趋势表述带边界："趋势一致但未达显著（p=0.09）""仅在高剂量组出现"；小波动不写成大结论。
- **每段末尾显式引用图表**（如"（图1A-C）"），无图的数值段引用数据表——保证交叉引用完整。
- 图注沿用原文（含误差棒说明）；正文不重复图注全文，只取关键。

**讨论段**：
- 结构：主要发现（一两句，对应结果）→ 与文献对照（一致/不一致+可能原因）→ 机制解释（明确标"推测"）→ 局限 → 小结。
- **每条结论句末内联标注**：`……与文献[4]报道一致【依据：本研究图2；文献[4] M05:p12】。`；机制推测句必带"可能/提示/有待"且标注【依据：推测——待补数据】。
- 同步回填 `/app/work/dclaims.jsonl`：`{"did":"D01","claim":…,"basis":"本研究图2|文献[4] M05:p12","locator":…,"strength":"数据直接支持|文献支持|推测"}`。
- **因果边界机检词表**：仅当有干预设计/统计因果检验时可用"导致/因果/决定"；观察性数据用"相关/伴随/提示"。文献对照不堆引用：每条引用写明一致或不一致及关系。
- 局限写实：方法层面（如未盲法）、样本层面（如单中心 n=32）、测量层面（如自报问卷）、统计层面（如多重比较未校正）——从材料找依据，不写空话。

### Stage 4 — 三重校验 + 同输入双跑（3+1 次脚本，fail 必修但不中断）
```bash
python3 scripts/fact_ledger.py check --draft /app/output/results_discussion.md --ledger /app/work/fact_ledger.jsonl --out /app/output/fact_check.json
python3 scripts/boundary_check.py --draft /app/output/results_discussion.md --readings /app/work/readings.jsonl --out /app/output/boundary_check.json
python3 scripts/trace_audit.py --draft /app/output/results_discussion.md --readings /app/work/readings.jsonl --ledger /app/work/fact_ledger.jsonl --dclaims /app/work/dclaims.jsonl --out-table /app/work/number_source_table.json --out /app/output/trace_audit.json
# 同输入第二遍（退化基线）：关闭护栏，用于产出可核验的增益对照
python3 scripts/trace_audit.py --draft /app/output/results_discussion.md --readings /app/work/readings.jsonl --ledger /app/work/fact_ledger.jsonl --dclaims /app/work/dclaims.jsonl --ablate stat_verify,strength_audit,claim_evidence,crossref,separation --out /app/output/trace_audit_baseline.json
```
- fact_check：正文数值是否都能在源文台账找到 → unmatched 数值回材料核对或标[待核]。
- boundary_check：① 结果段解释性词 ② 讨论因果越界 ③ 数值溯源 ④ 显著性用词（p≥0.05 不得称显著）。
- trace_audit 四合一：
  - **数字-来源逐条核对表**（number_source_table.json）：每个数值 → source_ref（图表编号）+ source_locator（来源单元格/页码）+ verbatim（逐字原文）+ status（matched/ledger/unmatched）。
  - **交叉引用完整性**：readings 登记的每张图/表必须在结果段被引用；结果段引用的编号必须已登记。双向缺一即 fail。
  - **讨论结论溯源 + 限定强度机检**：每条结论句必须有【依据：…】标注；逐条输出 claims 五元组 {kind, evidence(≤40字逐字), source_id, location, strength}；**限定强度机检**：强断言词（证明/证实/表明/导致/归因于）的依据必须定位到本研究图/表，推测句（可能/提示/有待）不得配强断言词——每条输出 {item, template_value, applied, match} 三元组。
  - **描述/解释分离**：结果段句子同时含实测数值与推断词 → 推断-实测混淆数。
  - **闸门状态显式枚举**：gates 字段输出 enforced / skipped_not_provided / not_found / unreadable / not_enforced_ablate；未运行的检查项 gate_note 写明「下游不得宣称已核对」。
- **双跑对照**：第二遍用 `--ablate` 关闭全部护栏，与第一遍**同一输入**（同一 md/readings/ledger/dclaims）比。关闭护栏 ≠ 通过：基线计数归零属统计假象，真实缺陷数看固定评估器口径。报告内 `gain_metrics` 给出 fixed_evaluator（两遍应完全一致）、detected、detection_coverage、delivered（人工负担）、step_list、input_fingerprint（sha1）。`gain_evidence.metrics` 分两层口径：**fixed_evaluator**（同一输入恒定 → 证明对照公平）与 **delivered**（随护栏开关变化 → 增益真实落点：有据率 / 强断言违规数 / 推断-实测混淆数 / 复核者人工负担 / 残留缺陷率 / 步骤数）。
- 需要时补跑 `python3 scripts/consistency_check.py --draft <md> --constraints /app/work/constraints.json --out /app/output/check_report.json`（章节完整性/引用对应/术语统一/字数/图表顺序）。

### Stage 5 — 构建 + 渲染 + result.json（收尾，熔断后必做）
```bash
python3 scripts/docx_build.py /app/work/draft.json --out-docx /app/output/results_discussion.docx --out-md /app/output/results_discussion.md
python3 scripts/render_preview.py --src /app/output/results_discussion.docx --outdir /app/output/previews
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact results_discussion.docx --artifact-md results_discussion.md \
  --embed-md /app/output/results_discussion.md \
  --evidence /app/work/evidence_map.jsonl --fact-check /app/output/fact_check.json \
  --boundary-check /app/output/boundary_check.json \
  --trace-audit /app/output/trace_audit.json --gain-baseline /app/output/trace_audit_baseline.json \
  --source-table /app/work/number_source_table.json \
  --dclaims /app/work/dclaims.jsonl --readings /app/work/readings.jsonl \
  --consistency /app/output/check_report.json \
  --render /app/output/previews/render_log.json --status complete --notes '...'
```
- **主产物全文嵌入** result.json（main_text_markdown）：单文件即可独立复核完整章节。
- **数字-来源核对表**（number_source_table）、**读数登记**（readings）与**讨论结论溯源**（discussion_claims）整表嵌入 result.json。
- **gain_evidence**：完整模式 vs 退化基线逐项对照（真实数字来自本案例两遍真实运行），含机制→指标映射与边界声明。
- **efficiency**：步骤数 / 自动回证条数 / 仍需人工核对条数 / 复核者负担，来源可回溯。
- **output_semantics**：题面输出要求表逐项语义映射（结果表述/统计量/交叉引用/限定强度/解释与推断分离 + 目标产物/事实与来源映射/版本与边界）。
- uncertainty 必含：reading_gaps、估读项、conflicts、推测句清单、[待核] 条目。
- 最后写盘自检：`ls /app/output` + 抽读 result.json 确认字段齐全、status 如实。

## 2. 异常处置表

| 情形 | 处置 |
|---|---|
| 图是位图无数据表 | 视觉估读 + 标 estimated_from_figure；关键数值建议作者以原始数据复核 |
| 图注未说明误差棒含义 | 不臆断；正文写"图中误差棒（含义未注明）"并列入 reading_gaps |
| 图注与图面数值不一致 | 记 conflict；正文以数据表为准；uncertainty 说明 |
| 统计输出缺失 p 值 | 不编显著性；写"差异未报告显著性检验" |
| 材料只有数据无图 | 按数据表写结果；建议作图列入 uncertainty |
| 任务要求合并写 R&D | 保持描述/解释分句纪律，段落角色分明 |
| 中英数据口径（万/亿 vs million） | 按材料原口径；换算时记录换算式于 evidence_map |
| 脚本报错/依赖缺失 | 三级容错（重试→降级→如实记录）；不阻塞交付，status 如实 |
| 校验脚本报 fail | 记录 fail 计数→修稿件→重跑；退出码恒 0，不因此放弃交付 |
| 熔断触发 | 立即收尾：现有内容过 Stage 5，缺项写 uncertainty |

## 3. 最小调用示例（示意）
```bash
python3 scripts/extract_materials.py --input /input --outdir /app/work/extracted
# （模型响应：readings.jsonl —— 图1-图5+表1-2 全部数值登记，2 项 estimated_from_figure）
python3 scripts/docx_build.py /app/work/draft.json --out-docx /app/output/results_discussion.docx --out-md /app/output/results_discussion.md
python3 scripts/trace_audit.py --draft /app/output/results_discussion.md --readings /app/work/readings.jsonl --ledger /app/work/fact_ledger.jsonl --dclaims /app/work/dclaims.jsonl --out-table /app/work/number_source_table.json --out /app/output/trace_audit.json
# → {"verdict":"pass","checked":88,"unmatched":0,"crossref":"pass","claims":"14/14","detection_coverage":1.0}
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --artifact results_discussion.docx --embed-md /app/output/results_discussion.md --source-table /app/work/number_source_table.json --trace-audit /app/output/trace_audit.json --gain-baseline /app/output/trace_audit_baseline.json --status complete
# → {"ok":true,"embedded_main_text":true,"number_source_rows":88,"gain_evidence":true,"efficiency":true}
```
示意（number_source_table 逐条形态，非正式案例结果）：
`{"line":3,"value":"12.3±1.1","context":"对照组24h为12.3±1.1 mg/L（图1A）","source_ref":"图1","source_locator":"M03:p5","verbatim":"12.3±1.1","status":"matched"}`

## 4. 交付自查清单
- [ ] result.json 字段一个不缺（含全部契约字段+case_id）；主产物全文已嵌入；status 如实
- [ ] 每个图表有 readings 登记；正文数值全部能在 number_source_table 找到 matched/ledger 来源
- [ ] 误差棒/显著性/单位与图注原文一致；估读项显式标注
- [ ] 交叉引用双向完整：登记的图/表全被结果段引用，引用编号全已登记
- [ ] 结果段零解释性用词（推断-实测混淆数=0）；讨论段每条结论句带【依据：…】（含 evidence 逐字≤40字定位）；限定强度机检 fail=0（强断言词↔本研究数据、推测句带限定语）
- [ ] trace_audit gates 全部 enforced（退化对照遍为 not_enforced_ablate 并附 gate_note）
- [ ] gain_evidence 含两遍真实记录：same_input_verified=true、fixed_evaluator 两遍一致、逐项对照有数值、机制→指标映射与边界齐备；delivered 口径 5 项核心指标（统计表述有据率/强断言违规数/推断-实测混淆数/复核者人工负担/残留缺陷率）在两遍间确有差异
- [ ] efficiency 有 steps/auto_verified/manual_review_items/delivered_evidence_rate，且注明不等于模型请求数
- [ ] output_semantics 五项（结果表述/统计量/交叉引用/限定强度/解释与推断分离）逐项有 status 与来源字段
- [ ] 因果/相关用词与设计匹配；局限写到方法/样本/测量/统计层面，非空话
- [ ] fact_check + boundary_check + trace_audit verdict=pass（或降级项已如实记录）；失败路径退出码为 0
- [ ] uncertainty/changelog 如实；写盘自检通过
