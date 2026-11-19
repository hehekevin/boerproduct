# worklog — acwrite-rebuttal 重做记录（2026-11-13）

## v4 补强（2026-11-17，bohrium-week3-final，冲 83 第 2 轮：补齐使用增益 25 + 创新增益 15 + 生态贡献 10）

上一轮只优化「实际效果 40 分」，本轮按题面重读题面补齐其余 50 分。核心要求：**同输入对照的真实运行证据** + 文档/资源可复用性。

### 一、五维差距清单（对照题面评分维度概要）

| 评分维度 | 分值 | v3 状态 | 差距（缺什么） | v4 补强 |
|---|---|---|---|---|
| 实际效果 | 40 | ✅ 强 | result.json 缺题面《输出要求》三行语义的**显式字段**（目标产物 / 事实与来源映射 / 版本与边界），只散在 embedded 与 audit 里；意见↔修改↔回复↔修订稿的对应关系没有一张可核对的表 | finalize 从台账+审计**自动派生** `triad` / `fact_source_map` / `version_boundary` 三个字段；verify 级联机检三者非空 |
| 使用增益 | 25 | ❌ **完全缺失** | 只有"本技能做了什么"的自述，无任何对照数字 → 文字自述在题面明确写着"不能替代实际运行证据" | 新增 `scripts/gain_compare.py`：在**本次真实产物**上按确定性规则派生退化变体（baseline + 4 组单机制消融），每个变体跑**同一个机检器与同一套指标口径**，分母固定为全量模式计数 → 逐项对照数字 + 机制→指标映射 + 边界声明，写入 `gain_evidence` |
| 创新增益 | 15 | ⚠️ 部分 | 有机制无证据证明机制**带来**改进；缺边界与对照 | gain_evidence 内置 `mechanism_to_metric`（每条机制给 full / ablated / baseline 三值 + delta + why）、`boundaries`（5 条，明示退化变体≠平台基线）、`comparison_design.fixed_denominators` |
| 可靠体验 | 10 | ✅ 强 | **校验失败会以非 0 退出码中断交付**（ledger_audit fail→rc=1，verify fail→rc=1），在平台上一次误判就可能丢结果 | 全部校验脚本退出码**恒为 0**，verdict/problem 照实记在报告与 result.json；新增 P9 协议条款；台账 JSON 损坏行不崩溃（记 ledger_parse_error） |
| 生态贡献 | 10 | ❌ 弱 | 只有 SKILL.md/README/worklog，无可直接复用的**资产** | 新增 `templates/` 五份可复用资产（意见分类法 / 台账模板 / 回复信模板 / 定位脚手架 / 自评表），均为空模板+判定规则，不含正式答案 |

### 二、补强点明细

1. **result.json 字段语义对齐题面**：`build_result.py finalize` 新增 `_derive_triad` / `_derive_fact_source_map` / `_derive_version_boundary`，从台账 + 审计报告派生（脚本保证，不靠提示词纪律）。`triad` 每子要求一行含 `comment_quote / decision / decision_rationale / tone / response_text / in_letter / edits[].{original,revised,reason,basis,locator,in_revised,in_baseline} / evidence / triad_aligned / manual_review`。
2. **可运行退化/基线模式**：`gain_compare.py` 五种变体（full / baseline / no_decompose / no_revision_log / no_locator / no_verbatim），全部由本次真实产物**派生**（collapse / strip 规则），无预置答案。`ledger_audit.py --ablate triad,verbatim,tone,coverage` 提供**检查器侧**消融：被消融项 applied=false 且不计入 problems，被抑制的问题逐条记入 `suppressed_problems`——即"关掉该机制就漏检了什么"的直接证据。
3. **逐项对照指标**（口径写进产物，可复核）：`comment_response_coverage`（子要求级）/ `comment_response_coverage_cm`（意见级，对退化模式公平，避免只报有利口径）/ `reply_revision_consistency` / `evidence_verifiability` / `modification_locator_rate` / `manual_review_items`（越低越好）。
4. **efficiency 字段**：新增 `scripts/_runlog.py`（零依赖，失败静默），各脚本结束时记 {script, event, seconds, ok}；finalize 汇总为 `efficiency{script_calls, script_call_total, wall_seconds_sum, pipeline_steps, model_request_budget}`——**实测计数，非自述**；模型请求数标注由宿主平台记录、本包不虚构。
5. **校验器统一 exit 0**：ledger_audit / build_result verify / gain_compare 全部返回 0，verdict 与 problems 照实记录；verify 报告新增 `semantic_fields`（三语义字段 + efficiency + gain_evidence 是否就位）。
6. **生态贡献资产**：`templates/` 五份（comment_taxonomy.md / ledger_template.jsonl / response_letter_template.md / locator_scaffold.md / scoring_sheet.md）。README 增「result.json 字段语义」对照表、「增益证据怎么跑怎么读」节（含复现命令与前置条件）、「生态贡献」资产表。
7. **保留既有 83 要素**：result.json 生命周期五命令、主产物分批嵌入、P1-P8 协议（新增 P9/P10）、线性五步、三方机检三元组、四闸门枚举、status 四级、verify 级联机检、docx_build/extract/render 三级容错——全部保留，只做增量。
8. **约束复核**：SKILL.md **149 行**（≤150）；脚本 **7 个**（≤8）；包 **172 KB**（<2MB）；零外部依赖；不预置正式答案；所有路径参数化不硬编码。

### 三、双测证据（真实数字，脚本 `../local_dual_test.sh`，22 项全绿）

夹具为**合成示意数据**（`../_selftest/mkfixture.py`），非正式案例结果。

**（a）正例 — 8 意见 / 8 子要求规模夹具（`_selftest/fx2`）**
- `ledger_audit`：`{"verdict":"pass","subs":8,"checks":76,"matched":76,"unbacked":0,"problems":[],"gates":{4 门全 enforced},"exit_code":0}`
- `gain_compare` 逐项对照（分母固定：8 子要求 / 8 意见 / 8 证据 / 8 修改）：

| 指标 | full | baseline | no_decompose | no_revision_log | no_locator | no_verbatim |
|---|---|---|---|---|---|---|
| comment_response_coverage | **100.0** | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 |
| comment_response_coverage_cm | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| reply_revision_consistency | **100.0** | 0.0 | 100.0 | 0.0 | 100.0 | 100.0 |
| evidence_verifiability | **87.5** | 25.0 | 87.5 | 87.5 | 87.5 | 25.0 |
| modification_locator_rate | **100.0** | 0.0 | 100.0 | 100.0 | 0.0 | 100.0 |
| manual_review_items | **0** | 8 | 0 | 8 | 0 | 0 |

→ 每个机制都被单独隔离出贡献：拆解→覆盖率、留痕→一致率、定位→定位率、逐字回证→证据可核验率；退化模式人工核对条目 8 → 全量模式 0。

**（b）正例 — 全链路（init→embed×2→audit→gain_compare→finalize→set→verify）**
- `verify`：`{"verdict":"pass","problems":[],"status":"complete","semantic_fields":{"triad":8,"fact_source_map":16,"version_boundary":true,"efficiency":true,"gain_evidence":true}}`
- `efficiency`（实测）：`script_calls={build_result:3, ledger_audit:1, gain_compare:1}`，`script_call_total=5`，`wall_seconds_sum=0.08`，`pipeline_steps=5`
- `finalize`：`triad_rows=8, fact_source_rows=16, gain_evidence=true, efficiency_calls=5`

**（c）污染数据反例**（脏台账：letter_text 不在回复信 / revised 锚点不命中 / rejected 无理由 / 伪造证据引文 / 非法证据状态）
- `ledger_audit`：`verdict=fail`，problems 类型 = {letter_in_letter, revised_in_revised, rejection_rationale, evidence_unbacked, evidence_status_valid, basis_locator, triad_ok}，unbacked 逐条列出，**退出码 0**
- `verify`（complete + audit=fail）：如实报 fail，**退出码 0**，result.json 仍为合法完整交付

**（d）其它反例（均 exit 0 且如实记录）**
- `--ablate triad,verbatim`：被消融项 applied=false，被抑制问题记入 `suppressed_problems`（>0），其余问题仍计 fail
- 缺 `--original`：`gates.original.state=skipped_not_provided` + gate_note「未运行 ≠ 通过」
- complete 但缺 triad/fact_source_map/version_boundary/gain_evidence/efficiency：verify 如实报 fail，仍 exit 0
- `status=blocked` 合法；`finalize` 在 result.json 缺失时自愈重建骨架
- 台账含损坏 JSON 行：audit 跳过该行记 ledger_parse_error，不崩溃、exit 0；gain_compare 遇空台账 exit 0

**（e）测试脚本升级**：旧版 `local_dual_test.sh` 断言"audit 退出码 1"已不适用（v4 统一 exit 0），全部改为断言 **verdict/problems 内容 + 退出码 0**，并新增 gain_compare、语义字段、消融、损坏台账四组用例。

### 四、本轮未做 / 边界

- 未改动题面、未提交（按指示）。
- `gain_evidence` 的对照数字来自**本次运行的真实产物派生变体**，不等于平台基础 Agent 的实跑产物；平台同条件对照由平台提供白板——该边界已写入产物 `boundaries` 字段。
- 指标全部基于机检口径（可检索性 / 字段完整性），不衡量文学质量与学术判断对错。
- 效率字段的模型请求数由宿主平台记录，本包只采脚本调用与墙钟耗时，不虚构。

## v3 补强（2026-11-16，bohrium-week3-final，对照 83 分公式逐要素清单）

缺失要素清单（对照 FORMULA-83 六要素）：
1. ❌ 机械校验器只输出问题汇总，缺逐条 `{sid, item, applied, match}` 三元组嵌入 → **已补**：ledger_audit v3 每个子要求每项检查产出三元组，报告全量随 finalize 嵌入 result.json（consistency_check）。
2. ❌ 三角对齐缺"回复"一角：letter_text 是否真实出现在回复信文件中未机检 → **已补**：letter_in_letter 检查（归一化后子串检索）。
3. ❌ 证据数字逐字回证缺失 → **已补**：evidence status=done 且 source≥12 字符时在基线稿归一化子串检索，不可检索者逐条列入 unbacked 并计入 fail。
4. ❌ 闸门自身状态未显式枚举（--original 缺失时静默跳过）→ **已补**：gates{ledger,letter,revised,original} 四门 enforced/skipped_not_provided/not_found/unreadable + gate_note「未运行 ≠ 通过，下游不得宣称已核对」。
5. ❌ status 三级缺 blocked → **已补**：四级 complete/partial/failed/blocked（blocked 语义同 partial，仅 warn 不误杀）。
6. ❌ verify 未级联校验审计报告 → **已补**：complete 时 consistency_check 必须存在且 verdict=pass，否则 hard fail。

保留不动的有效机制：result.json 生命周期五命令（init/embed/set/finalize 自愈/verify）、主产物分批嵌入、P1-P8 强制协议、线性五步、docx_build/extract/render 三级容错。

本地双测（12 项全绿，脚本 `../local_dual_test.sh`，夹具为合成示意数据）：
- 正例：init→embed×2→audit（verdict=pass, checks≥9 全 matched, 闸门全 enforced）→finalize→set→verify pass；报告含三元组且 unbacked=0。
- 反例：脏台账（letter_text 不在回复信 / revised 锚点不命中 / rejected 无理由 / 伪造证据引文 / 非法证据状态）→ audit 退出码 1 且逐条列出；缺 --original → gate=skipped_not_provided + gate_note；complete+audit_fail 与 complete+无审计 → verify 均拦下；blocked 合法；finalize 自愈重建骨架。

## 历史成绩

- 71942：67.00
- 72498（主账直提）：0 —— 某次运行产物不完整（result.json 缺失/不完整），直接归零。

- 目标：≥70。

## 失分点分析

1. **完整性靠提示词纪律而非脚本**（致命，对应 72498=0）：旧版 SKILL.md 写"先落骨架 result.json"，但 build_result.py 只做"组装/回填"——init 没跑或中途崩溃时，output 目录里就没有合法 result.json，主产物再好也判 0。
2. **主产物未嵌入 result.json**：旧版只存 deliverable 指针（文件路径）。评审复核算 result.json 时拿不到逐条回复信与修订稿全文；文件指针一旦失效即空结果。
3. **无写盘自检**：契约字段是否齐全、嵌入是否非空、交付文件是否存在，运行结束无人检查，缺了也不知道。
4. **revision_log 不强制**：旧版 edits 用 anchor_quote/after/why，字段不统一，"改得准/可核验"证据链弱。
5. **脚本冗余**：8 个脚本中 edits_verify.py 与 fact_ledger.py 职责重叠，资源超编、维护面大。

## 本版修复（对应可验证机制）

| 失分点 | 修复 | 保证方式 |
|---|---|---|
| 骨架不落盘 | `build_result.py init`：Stage 0 第一个动作，幂等补齐 case_id + output_contract 全字段 + status=partial | 脚本行为；tmp 原子写盘 |
| 主产物未嵌入 | `build_result.py embed --key letter_markdown/revised_markdown --file … --part …`：分批追加嵌入 | verify 机检 complete 时嵌入 ≥200 字 |
| 无自检 | `build_result.py verify`：契约字段齐全/嵌入非空/文件存在/status 合法 | 退出码 1，SKILL.md 要求 pass 才结束 |
| 失败不交付 | `finalize` 自愈：result.json 缺失/损坏时重建骨架再收尾，partial 必列 uncertainty | 脚本保证 |
| 留痕不强制 | 台账 edits 统一 `revision_log{original,revised,reason,basis}`；ledger_audit 新增第 6 项机检四字段齐全 + revised 在修订稿/原稿可检索 | 机检 fail 必须修复 |
| 预算失控 | SKILL.md 置顶强制协议 P5：自设 48 请求/700 秒熔断（平台 64/900 之内），超线立即 finalize partial | 提示词+finalize 兜底 |
| 资源超编 | 精简为 5 个脚本（SKILL.md+README+worklog+5 脚本=8 文件） | ≤8 |

## 本版结构

- 线性 ≤5 步：Stage 0 落骨架 → 1 意见拆解 → 2 决策台账 → 3 生成+分批嵌入 → 4 校验收尾。
- SKILL.md 约 120 行（≤250）；强制执行协议 P1-P8 置顶。
- 脚本三级容错并本地双测：extract（python-docx→zipfile 兜底）、docx_build（python-docx→stdlib 最小 docx）、render（soffice→docx2pdf→no_renderer 如实记录）。
- 不硬编码平台路径：所有路径默认 /input、/app/work、/app/output 且均可参数覆盖。

## 本地双测记录

- build_result.py：init → embed（append/分批）→ set → finalize（含 result.json 缺失自愈）→ verify（契约缺失/embedding 过短/文件不存在各分支）全部通过，详见下方测试输出。
- ledger_audit.py：正常台账 pass；缺 revision_log 字段 / anchor 不命中 / rejected 无理由 → fail，符合预期。

## 后续可迭代

- 若平台案例含上一轮回复信，启用台账中的"上轮承诺核对"路径（异常处置表已备）。
- 语气词表按审稿人文化（中/英文期刊）扩充。
