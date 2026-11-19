# acwrite-rebuttal — 审稿回复与论文修改 Skill

面向「审稿回复与论文修改」场景（Bohrium 产品赛 · 学术写作赛道 challenge-2815a418）：把审稿意见清单 + 指定基线稿处理成**逐条回复信 + 修订稿**，每处修改带 revision_log 留痕、定位可机检、result.json 完整性由脚本保证，并给出**同输入对照的真实增益证据**。

## 核心方法

1. **意见拆解**：每条意见拆到子要求（一条意见多问必拆净），交叉意见关联。
2. **逐条决策**：adopted / partially_adopted / rejected + 理由；语气四档（accept/clarify/polite_pushback/appeal）。
3. **修改留痕**：每处改动带 `revision_log{original, revised, reason, basis}`，外科手术式 before/after。
4. **三方机检**：`ledger_audit.py` 对每个子要求逐条输出 `{sid, item, applied, match}` 三元组——① letter_text 在回复信可检索（回复↔回复信）② revision_log.revised 在修订稿可检索（修改↔修订稿）③ original 在基线稿可检索（修改↔原稿）④ revision_log 四字段齐全 + basis 带定位 ⑤ 决策合法/rejected 有理由 ⑥ 证据状态合法且 done 项 source 引文逐字回证（不可回证者逐条列入 unbacked 并计 fail）⑦ locator 非空 ⑧ triad_ok 三角对齐总判定；闸门状态显式枚举 enforced/skipped_not_provided/not_found/unreadable，缺输入记 gate_note（未运行 ≠ 通过）。
5. **脚本保证交付**：`build_result.py` 五个子命令管理 result.json 全生命周期——骨架先行、主产物分批嵌入、失败自愈、写盘自检。**完整性靠脚本，不靠提示词纪律。**
6. **增益可证**：`gain_compare.py` 在**本次真实产物**上按确定性规则派生退化变体，每个变体跑**同一个机检器与同一套指标口径**，产出逐项对照数字 + 机制→指标映射 + 效率计数 + 边界声明。数字是跑出来的，不是写出来的。
7. **失败不中断**：所有校验脚本退出码恒为 0，问题记录在报告与 `verdict` 里；失败被如实记录，但绝不阻断交付。

## 文件清单

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 技能本体：P1-P10 强制执行协议 + 线性五步流程 + 异常处置 + 自查清单（149 行） |
| `scripts/build_result.py` | result.json 生命周期：init / embed / set / finalize / verify；派生 triad / fact_source_map / version_boundary / efficiency |
| `scripts/ledger_audit.py` | 三方一致性机检 + 逐项指标 + `--ablate` 消融对照模式 |
| `scripts/gain_compare.py` | 同输入对照：全量模式 vs 退化模式（baseline + 4 组单机制消融），产出 gain_evidence |
| `scripts/extract_materials.py` | 输入材料抽取（docx/pdf/txt/md/xlsx…→带锚点纯文本 + manifest） |
| `scripts/docx_build.py` | 结构化 draft.json → 可编辑 docx + md（python-docx 缺失时 stdlib 兜底） |
| `scripts/render_preview.py` | docx→PDF/PNG 预览（无渲染器时如实记 no_renderer，不伪造） |
| `scripts/_runlog.py` | 运行事件采集（脚本调用数/耗时），efficiency 计数的真实来源 |
| `templates/comment_taxonomy.md` | **可复用**：意见分类法（类型/严重度/拆解规则/决策-语气映射/字段字典） |
| `templates/ledger_template.jsonl` | **可复用**：意见-改动台账模板（字段齐全的示例行） |
| `templates/response_letter_template.md` | **可复用**：回复信模板骨架（含机检约束与占位说明） |
| `templates/locator_scaffold.md` | **可复用**：定位脚手架（locator 格式表/五步法/联动检查表/不可定位处置） |
| `templates/scoring_sheet.md` | **可复用**：返修交付自评表（答得全/改得准/证得住/对得上/交付形态/增益效率 六组可观察判定） |

依赖：仅 Python 3.8+ 标准库；可选 python-docx / PyMuPDF / pypdf / openpyxl / LibreOffice（缺失自动降级并在 manifest/render_log 如实记录）。无网络依赖、无平台专有路径（所有路径均可 `--input/--out/--case` 参数化，默认 `/input`、`/app/work`、`/app/output`）。

## 调用方式

由 Agent 按 `SKILL.md` 的线性五步执行（Stage 0 读输入+落骨架 → 1 意见拆解 → 2 决策台账 → 3 生成修订稿/回复信+分批嵌入 → 4 机检+增益对照+收尾），关键命令见下例。

## 最小示例（示意，非正式案例结果）

输入：`/input/case.json`（含 output_contract）、`manuscript-baseline.md`、`reviewer-comments.md`

```bash
python3 scripts/extract_materials.py --input /input --outdir /app/work/extracted
# → {"ok":true,"summary":{"total":3,"extracted":3}}
python3 scripts/build_result.py init --case /input/case.json --out /app/output/result.json
# → 立即产出含全部契约字段的骨架 result.json（status=partial）

# ……模型按 SKILL.md 产出 comments.jsonl / response_ledger.jsonl / 两份 draft.json ……

python3 scripts/build_result.py embed --out /app/output/result.json --key letter_markdown --file /app/output/response_letter.md --part full
# → {"ok":true,"cmd":"embed","key":"letter_markdown","chars":4120}
python3 scripts/ledger_audit.py --ledger /app/work/response_ledger.jsonl --letter /app/output/response_letter.md --revised /app/output/revised.md --original /app/work/extracted --out /app/output/ledger_audit.json
# → {"verdict":"pass","subs":19,"checks":95,"matched":95,"unbacked":0,"gates":{...enforced}}
python3 scripts/gain_compare.py --ledger /app/work/response_ledger.jsonl --letter /app/output/response_letter.md --revised /app/output/revised.md --original /app/work/extracted --out /app/output/gain_evidence.json --runlog /app/work/run_log.jsonl
# → {"ok":true,"modes":{"full":{...},"baseline":{...}},"manual_review_saved":7}
python3 scripts/build_result.py finalize --case /input/case.json --out /app/output/result.json --status complete --artifact /app/output/response_letter.docx --evidence /app/work/response_ledger.jsonl --audit /app/output/ledger_audit.json --gain /app/output/gain_evidence.json --runlog /app/work/run_log.jsonl
python3 scripts/build_result.py verify --case /input/case.json --out /app/output/result.json
# → {"verdict":"pass","status":"complete","semantic_fields":{"triad":19,"fact_source_map":50,...}}
```

## result.json 字段语义（对齐题面《输出要求》三行）

| 题面要求 | result.json 字段 | 内容 | 来源 |
|---|---|---|---|
| 目标产物 | `deliverable` + `embedded.letter_markdown` / `embedded.revised_markdown` | 可编辑修订稿与回复信（docx 路径 + 正文全文） | embed 嵌入 |
| 事实与来源映射 | `fact_source_map` | 每个数字/术语/引用/关键论断 → 出处 + 修改记录 + 定位 | finalize 从台账+审计派生 |
| 版本与边界 | `version_boundary` | 基线版本标识 / 修改差异清单 / 需人工确认项 / 材料缺口 / 异常 | finalize 从台账+审计派生 |
| 意见逐条回应 ↔ 修改点 ↔ 回复信 ↔ 修订稿 三角对应 | `triad` | 每子要求一行：意见原文、决策+理由、语气、回复文字、`in_letter`、每处修改的 original/revised/locator/`in_revised`/`in_baseline`、证据状态、`triad_aligned`、`manual_review` | finalize 从台账+审计派生 |
| 使用增益 | `gain_evidence` | 同输入对照逐项数字 + 机制→指标映射 + 边界声明 | gain_compare.py |
| 效率 | `efficiency` | 脚本调用数（按脚本分组）、墙钟耗时、流程步数 | `_runlog.py` 实测，非自述 |
| 运行状态/不确定性 | `status` / `uncertainty` / `changelog` | 四级 status；缺口如实列出 | finalize |

`verify` 会级联机检：`consistency_check.verdict` 必须为 pass；`triad` / `fact_source_map` / `version_boundary` 三个语义字段必须非空——否则如实报 fail。

## 增益证据：同输入对照怎么跑、怎么读

### 设计

`gain_compare.py` 不使用任何预置答案。它**在同一次运行的真实产物**上按确定性规则派生退化变体，对每个变体跑**同一个机检器**（`ledger_audit.run_audit`）与**同一套指标口径**，且**分母固定为全量模式的计数**（子要求数 / 证据条数 / 修改条数），因此两遍数字严格可比。

| 变体 | 派生规则 | 抽掉的机制 |
|---|---|---|
| `full` | 本次真实产物 | — |
| `baseline` | 意见级合并回应 + 删留痕 + 删定位 + 删证据出处 | 全部（模拟无本技能的基础产出） |
| `no_decompose` | 子要求合并到意见级，留痕/定位/证据保留 | 只抽「子要求拆解」 |
| `no_revision_log` | 编辑条目去掉 `revision_log` | 只抽「修改留痕」 |
| `no_locator` | 编辑条目去掉 `locator`/`pid` | 只抽「修改定位」 |
| `no_verbatim` | 证据 `source` 退化为指针 | 只抽「证据逐字回证」 |

### 指标口径

| 指标 | 定义 | 分母 |
|---|---|---|
| `comment_response_coverage` | 子要求级：有专属决策行且其回复文字在回复信中可检索 | 子要求数 |
| `comment_response_coverage_cm` | 意见级：同上按意见聚合（对退化模式公平，避免只报有利口径） | 意见数 |
| `reply_revision_consistency` | 同时具备可核验留痕（原句可回溯 + 新句可检索）与可检索回复文字 | 子要求数 |
| `evidence_verifiability` | 证据条目中状态合法且出处可逐字回证 / 状态明确说明 | 证据条数 |
| `modification_locator_rate` | 修改条目中带可检索定位的占比 | 修改条数 |
| `manual_review_items` | 机器无法确认、必须人工核对的子要求数（**越低越好**） | 子要求数 |

### 复现方式

```bash
# 与正式运行完全相同的四条命令，产物落在同一处
python3 scripts/ledger_audit.py  --ledger <台账> --letter <回复信> --revised <修订稿> --original <基线稿目录> --out <审计.json>
python3 scripts/gain_compare.py --ledger <台账> --letter <回复信> --revised <修订稿> --original <基线稿目录> \
        --out <gain_evidence.json> --runlog <run_log.jsonl>
```

复现前置条件：台账为 JSONL（每行一个子要求）、回复信与修订稿为纯文本、基线稿为 `extract_materials.py` 产出的带锚点 `.txt` 目录。同输入同脚本必得同数字；`gain_evidence.json` 内含 `comparison_design.fixed_denominators`，可直接核对分母。

### 边界（写在产物 `boundaries` 里，不靠口头声明）

- 对照数字来自本次运行的真实产物与真实派生变体，**不是预置答案**；平台与基础 Agent 的对照由平台提供。
- 退化变体由规则派生，**不等同于平台基础 Agent 的实跑产物**，只用于机制归因，不能当作基线能力评测。
- 指标全部基于机检口径（可检索性、字段完整性），**不衡量文学质量与学术判断对错**。
- 样本为单个案例的一次运行，结论**不外推**到其他稿件长度/意见规模。
- 证据可核验率依赖基线稿可提取；基线稿缺失时该项按未回证计，并在 `audit.gates` 标注。

## 生态贡献（可直接复用的资产）

`templates/` 下五份资产可被他人直接拿去用（均为空模板 + 判定规则，不含正式案例答案）：

| 资产 | 复用场景 |
|---|---|
| `comment_taxonomy.md` | 意见分类法：6 类意见类型、major/minor 判定、必拆/不拆信号、决策-语气映射、字段字典 |
| `ledger_template.jsonl` | 台账模板：字段齐全的示例行，含 `revision_log`/证据/人工确认标记 |
| `response_letter_template.md` | 回复信模板骨架：版本说明 + 按审稿人分组逐条 + 批量格式明细表 + 待确认事项段 |
| `locator_scaffold.md` | 定位脚手架：6 种稿件形态的 locator 格式、写台账五步法、7 项联动改动检查表、不可定位处置 |
| `scoring_sheet.md` | 自评表：六组 24 项可观察判定条件 + 判定汇总规则 + 复跑命令 |

本工作流自身沉淀的可分享经验：意见拆净的判定信号、"三角对齐"的机检口径（回复↔修改↔原稿）、"未运行 ≠ 通过"的闸门枚举、失败不中断的交付纪律，以及同输入派生变体做机制归因的方法。

## 适用范围与边界

- 适用：基于意见摘要 + 指定基线稿的受控返修演练与真实逐条回复起草；意见类型覆盖方法/数据/写作/格式/伦理。
- 不适用：需联网核验原评审全文、补做真实实验、多文档库全文重写。材料不足时给替代说明并标注缺口，不伪造。
- 失败处理：任何阶段中断，result.json 始终合法；finalize 自愈重建骨架；partial 必须在 uncertainty 列缺口；所有脚本退出码 0，失败不被吞掉也不阻断交付。

## 维护

- 脚本均为单文件、无状态、幂等；`ledger_audit.py` 的语气词表、`comment_taxonomy.md` 的类型表与 `build_result.py` 的嵌入键名可按期刊惯例扩展。
- 版本：2026-11-17 v4（新增 gain_compare 同输入增益对照 + triad/fact_source_map/version_boundary 语义字段 + efficiency 实测计数 + 校验器统一 exit 0 + templates/ 五份可复用资产），变更记录见 `worklog.md`。
