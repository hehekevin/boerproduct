# worklog — challenge-caca73b2 结果与讨论写作 Skill（83公式对齐增强）

日期：2026-11-16　|　执行者：r83-12-results　|　基线：69.33（redo 版），目标对齐 83 公式
产出目录：`bohrium-week3-final/challenge-caca73b2/submission/`（未提交，按指令）

## 对照 FORMULA-83 逐要素查缺清单（相对 redo 版）

| 83公式要素 | redo 版状态 | 本次处置 |
|---|---|---|
| 1 强制执行协议置顶 | ✅ 已有 | 不动 |
| 2 主产物全量嵌入 result.json | ⚠️ 全文嵌入有，readings.jsonl 未嵌入 | build_result.py 新增 `--readings` 整表嵌入 |
| 3 每条检查 {item, template_value, applied, match} 三元组 | ❌ 无 | 新增限定强度机检逐条三元组；unmatched 本就逐条列出 |
| 3' 每条统计表述带 evidence 逐字 | ⚠️ claims 只有 support 文字，无逐字摘录 | claims 升级五元组 {kind, evidence≤40字逐字, source_id, location, strength}，evidence 从 readings.caption_quote/locator 定位摘录 |
| 3'' 统计表述机械覆盖度 | ❌ **真 bug**：NUM_RE 尾 `?` 使整组可选回退空匹配 + 单位组必选 → 裸数/p=/n=/CI 全漏检；`(?<![\w.])` 的 `\w` 吞 CJK 致中文后数值整体漏检 | NUM_RE 重写为统计量必选 token 替代（p=/n=/CI/带±数/带单位数），lookbehind 收窄为 `[\dA-Za-z_.]`；宽松匹配 core 去掉 "=" |
| 4 闸门状态显式枚举 | ⚠️ 只有笼统 skipped | gates 显式枚举 enforced/skipped_not_provided/not_found/unreadable + gate_note「下游不得宣称已核对」 |
| 4' 限定强度机检 | ❌ disc_claims 只分类不校验 | 强断言词（证明/证实/表明/导致/归因于）↔依据必须本研究数据；推测句须带限定语；fail 冒泡退出码 |
| 5 证据逐字+定位 | ✅ number_source_table 已有 | claims 五元组补齐同类能力 |
| 6 status 诚实四级 | ✅ 已有 | 不动 |

## 改动清单（增量，不推翻）
1. `scripts/trace_audit.py`：NUM_RE 重写（修复漏检真 bug）；disc_claims 五元组+强度机检；gates 闸门枚举；输出加 strength_fail/gates。
2. `scripts/build_result.py`：新增 `--readings`（读数登记全量嵌入）+ 输出 readings_rows。
3. `SKILL.md`：Stage 4 补强度机检/闸门枚举说明、Stage 5 命令加 `--readings`、自查清单补两条。135 行 ≤150。
4. `README.md`：新增机制对照表扩充（6 行）。
5. 其余 6 脚本与示例未动（保留 redo 版全部有效机制）。

## 本地双测证据（_selftest/，夹具为合成示意，非正式案例）
| 场景 | 结果 |
|---|---|
| 正例（3 统计 token 全 matched / 2 结论句全标注 / 强度合规） | verdict=pass，checked=3 unmatched=0 crossref=pass claims=2/2 strength_fail=0，exit=0 |
| 反例1：强断言「证明…」配文献依据 | strength_fail=1（strong_claim_backed_by_data applied=文献 match=false 逐条列出），verdict=fail exit=1 |
| 反例2：篡改数值 18.7±1.3→19.9±1.3 | unmatched=1 逐条列出，verdict=fail exit=1（修复前漏检，现必抓） |
| 反例3：readings 文件不存在 | gates=readings:not_found 如实枚举+gate_note，不崩溃，crossref=skipped |
| 反例4：--readings 未提供 | gates=readings:skipped_not_provided，gate_note「下游不得宣称已核对」 |
| build_result 嵌入 | embedded_main_text=true，readings_rows=2，trace_audit.discussion_claims.strength_check 与 gates 均随行嵌入 |
| 逐条核对表抽查 | draft.md 3 token（12.3±1.1 / 18.7±1.3 / n=32）全 matched，来源 ref=图1 locator=M03:p5 |

## 未做 / 边界
- 未提交（按指令）；未改 docx_build/render_preview/extract_materials/fact_ledger/boundary_check/consistency_check。
- boundary_check.py 未接入 gates 枚举（其核心 fail 项已冒泡退出码；如需可在下轮统一）。

---

# 第 2 轮（冲83优化）：使用增益25 + 创新增益15 + 生态贡献10 补强

日期：2026-11-17　|　执行者：w2-12-results　|　基线：69.33（redo+83对齐版）　|　目标：补齐 50 分的「真实运行证据 + 可复用性」
产出目录：`bohrium-week3-final/challenge-caca73b2/submission/`（**未提交**，按指令）

## 0. 题面重读后的五维差距清单（对照 task.md 评分表逐维）

| 评分维度 | 分值 | 上一轮实况 | 差距诊断 | 本轮补强点 |
|---|---|---|---|---|
| 实际效果 | 40 | 已有四合一审计、逐条核对表、闸门四态 | **题面「Skill 运行后的输出要求」表三项内容（目标产物/事实与来源映射/版本与边界）未在 result.json 里显式落字段**；结果表述/统计量/交叉引用/限定强度/解释推断分离 5 项语义无显式 status | ①新增 `output_semantics`：题面输出要求表逐项语义映射，5 项各带 status + 来源字段 + 计数明细 |
| 使用增益 | 25 | 仅 SKILL.md 自述「本 Skill 更好」，**无同输入对照的真实数字** | 缺「增益可验证性」要求的公平对照；缺效率增益的可计量证据 | ②新增 `gain_evidence`：**同输入双跑真跑**（完整模式 vs `--ablate` 退化基线），16 项逐项对照 + 机制→指标映射 + 5 条边界；③新增 `efficiency` 字段 |
| 创新增益 | 15 | 有限定强度机检、闸门枚举等 | 缺「方法改进」的**可运行消融**——机制无法单独开关，贡献不可归因 | ④`trace_audit.py --ablate` 可运行退化/基线模式：5 个护栏可独立开关，固定评估器保证两遍输入一致，sha1 指纹自证 |
| 可靠体验 | 10 | 有异常处置表、闸门降级 | **校验脚本失败时退出码非 0 → 会中断交付链**（与「失败也交付」协议冲突） | ⑤所有校验脚本失败路径**退出码恒 0**（verdict/fail 计数照实落报告与 stdout），另加 `--strict-exit` 供 CI；每脚本加顶层安全网 |
| 生态贡献 | 10 | README 只有「新增机制对照表」 | 缺文档完整性清单（依赖/配置/适用范围/限制/维护）、缺可复用资源清单、缺评分表自评对照、缺最小自检清单 | ⑥README 重写：用途/快速开始/机制清单/增益证据(含复现命令与边界)/依赖配置/资源可复用性/评分表自评对照/文件清单/适用边界/维护版本；新增 `examples/gain_evidence_example.json` |

## 1. 改动清单（增量，不推翻；83 要素全部保留）

| 文件 | 改动 | 保留的 83 要素 |
|---|---|---|
| `scripts/trace_audit.py` | ①新增 `--ablate` 退化/基线模式（可关 5 个护栏：stat_verify/strength_audit/claim_evidence/crossref/separation）；②新增子检查 D「描述-解释分离」（推断-实测混淆数）；③新增 `extract_result_statements`（结果表述逐句抽取）；④新增 `gain_metrics`：固定评估器 + delivered（交付口径人工负担）+ step_list + input_fingerprint(sha1)；⑤新增 `--strict-exit`；⑥顶层安全网；⑦**修 crossref 真 bug**：`ref.match(REF_RE,ref)` → `REF_RE.search(ref)`（原写法必抛 AttributeError，上一轮未被发现） | 嵌入/闸门四态(+ablate态)/status 诚实四级/逐字回证/三元组/五元组 全部保留 |
| `scripts/build_result.py` | ①新增 `build_gain_evidence()`：两遍逐项对照 + 机制→指标映射 + 边界 + 复现命令；②新增 `build_efficiency()`；③新增 `build_semantics()`：题面输出要求表 → result.json 字段语义映射；④新增 `--gain-baseline` / `--boundary-check` / `--efficiency-notes`；⑤顶层安全网 | 同上 |
| `scripts/boundary_check.py` | 失败路径 exit 0；新增 `--strict-exit`；readings 缺失/损坏如实降级 + gates 枚举；顶层安全网 | — |
| `scripts/fact_ledger.py` | `check` 子命令失败路径 exit 0；新增 `--strict-exit`；draft/ledger 读失败如实降级 | — |
| `scripts/consistency_check.py` | 失败路径 exit 0；新增 `--strict-exit`；draft/constraints 读失败如实降级 | — |
| `SKILL.md` | 135 → **149 行**（≤150）：Stage 4 增「同输入双跑」段、Stage 5 增 `--gain-baseline`/`--boundary-check`、协议增第 8 条「校验失败不中断」、异常表增 1 行、自查清单增 3 条 | 强制协议置顶/全文嵌入/三元组/闸门枚举/逐字回证/status 四级 全保留 |
| `README.md` | 全文重写：新增增益证据节(含复现命令与 4 条边界)、依赖与配置、资源可复用性表(6 类)、评分表自评对照表(15 行映射到 result.json 字段)、维护与版本 | — |
| `examples/gain_evidence_example.json` | 新增：gain_evidence 目标结构示例（标注示意，非正式案例结果） | — |
| 未动 | `docx_build.py` / `render_preview.py` / `extract_materials.py`（已验证降级行为正常） | — |

## 2. 双测证据（真实运行数字，夹具为合成示意，非正式案例）

夹具：`_selftest/draft.md`（合规）+ `_selftest/draft_polluted.md`（注入 5 类污染）
污染项：① 数值篡改 18.7±1.3→19.9±1.3 ② 强断言「证明」配文献依据 ③ 结果段「这说明…」推断-实测混写 ④ 引用未登记图「图3」 ⑤ 讨论段 2 句无【依据】标注
执行：`_selftest/run.sh`（10 组用例全跑，退出码全部记录）

### 2.1 正常模式 vs 退化模式（污染稿，同一输入两遍真实运行）

| 对照指标 | 完整模式 | 退化基线模式 | 说明 |
|---|---|---|---|
| 统计表述有据率 | 0.5 | 0.5 | 固定评估器口径，两遍一致 |
| 统计表述总数（分母） | 4 | 4 | 同输入证明对照公平 |
| 未回证数值数 | 2 | 2 | 真实缺陷数不随护栏开关变化 |
| 强断言违规数 | 1 | 1 | 同上 |
| 推断-实测混淆数 | 1 | 1 | 同上 |
| 需人工核对条目数 | 7 | 7 | 同上 |
| **本模式检出缺陷数** | **7** | **0** | ← 护栏的实际贡献 |
| **缺陷检出覆盖率** | **1.0** | **0.0** | 检出数 ÷ 真实缺陷总数 |
| 自动完成逐字回证的统计表述数 | 2 | 0 | 免去的人工核对工作量 |
| 仍需人工回材料核对的统计表述数 | 2 | 4 | 基线需人工核全部 4 条 |
| 对复核者可见的缺陷数 | 7 | 0 | 基线的 0 是**统计假象** |
| 对复核者不可见的缺陷数 | 0 | 7 | 基线的返工/漏发风险 |
| **复核者总人工核对负担** | **2** | **11** | 待核表述数 + 未暴露缺陷数 |
| 流程步骤数 | 16 | 11 | 基线少跑 5 步 = 省掉的护栏动作 |

**关键结论**：退化基线 `verdict=pass` / `fail_count=0`，但真实缺陷 7 项全部对它不可见（`defects_hidden_from_reviewer=7`，人工负担 11 vs 2）。这正是「关闭护栏 ≠ 通过」的真实证据，也是「增益可验证性」的可核验记录。
**输入一致性自证**：`same_input_verified=true`；两遍 `fixed_evaluator` 字典逐字段相等（实测 `SAME fixed? True`）；draft sha1 `c063bd193f6a58f2`、readings sha1 `d8745661b7977173` 两遍相同。

### 2.2 干净稿（合规稿）双跑
完整模式 verdict=pass / checked=3 / unmatched=0 / crossref=pass / claims=2/2 / separation_confusion=0 / fail_count=0；
`output_semantics` 5 项**全部 status=pass**；efficiency：自动回证 3 条、待人工核对 0 条、复核者负担 0。

### 2.3 污染数据反例（校验器必须抓到，且退出码为 0）
- `trace_audit.py` 完整模式：verdict=**fail**、fail_count=**7**、unmatched=2、crossref=fail、strength_fail=1、separation_confusion=1 → **exit=0** ✅（verdict 照实记录，未中断交付）
- `trace_audit.py` 退化模式：verdict=pass、fail_count=0 → exit=0（护栏未生效，如实以 `not_enforced_ablate` 闸门暴露）
- `boundary_check.py` 污染稿：verdict=fail、fail=1、types=[explanatory_in_results, reading_trace_note] → **exit=0** ✅
- `consistency_check.py`：verdict=fail（citations:fail / figures_order:warn）→ **exit=0** ✅
- `fact_ledger.py check`：checked=5、unmatched=1、verdict=fail → **exit=0** ✅
- 缺失 readings：`gates.readings=not_found`、crossref=skipped、如实枚举 → **exit=0** ✅
- `--strict-exit` 污染稿 → **exit=1**（CI 用，非零码能力保留）

### 2.4 未修改脚本回归
`extract_materials.py`（空输入 → total=0 如实）exit=0；`docx_build.py`（无 python-docx → stdlib 兜底 min-docx）exit=0；`render_preview.py`（无渲染器 → status=no_renderer，不伪造）exit=0。

## 3. 硬约束核对
| 约束 | 实测 | 结论 |
|---|---|---|
| SKILL.md ≤150 行 | 149 行 | ✅ |
| 零外部依赖 | 8 脚本全部 stdlib；docx/fitz/openpyxl 缺失时自动降级 | ✅ |
| 脚本 ≤8 | 8 个 | ✅ |
| 包 <2MB | 156K | ✅ |
| 不预置正式答案 | 全部示例标注「示意/非正式案例结果」 | ✅ |
| 不改题面 | task.md 未改 | ✅ |
| 不提交 | 未执行提交动作 | ✅ |

## 4. 未做 / 边界
- 未做「基础 Agent vs Skill Agent」的**模型输出对照**：那需要平台在固定案例上跑两个条件，本包无法代跑，亦不得预置其结果。gain_evidence 只声明「同一草稿的机制开关对照」，证明护栏检出能力，不冒充平台对照。
- 效率以步骤数与人工负担为代理指标；真实模型请求数/耗时由平台记录，本包不虚构。
- 退化基线计数归零属统计假象，已在 result.json `gain_evidence.boundaries` 明示，避免被误读为「基线质量更好」。
- `dclaims.jsonl` 与 `readings.jsonl` 的联动（did ↔ claim 文本）目前只做条数绑定（`dclaims_file_bound`），未做语义级对齐；留待下一轮。
- boundary_check 的 `reading_trace_note` 项仍为提示性（完整数值核查以 fact_ledger 为准），未升级为硬 fail。

---

# 第 3 轮（w4-results）：退出码恒 0 + 增益双口径 + 生态贡献全套

日期：2026-11-17　|　执行者：w4-results　|　基线：69.33（第 2 轮 83 对齐 + gain_evidence 版）
产出目录：`bohrium-week3-final/challenge-caca73b2/submission/`（**未提交**，按指令）
接续上一轮被中断的工作，**不推倒重来**：83 公式全部要素与第 2 轮新增机制全部保留，本轮只补 4 处缺口。

## 0. 现状复核（接续前先看现状，不重做）

| 项 | 复核结论 |
|---|---|
| SKILL.md | 149 行，已 ≤150 ✅ |
| 脚本数 | 8 个 ✅；零外部依赖（全部 stdlib）✅ |
| 包体积 | 388K < 2MB ✅（本轮清理了 `scripts/__pycache__`） |
| gain_evidence / 消融 / efficiency | 字段已在，但**对照口径有缺陷**（见 §1.2） |
| 退出码 | 上一轮仅覆盖「校验类脚本的 verdict=fail 路径」；**argparse 用法错误、输入缺失/损坏、未捕获异常共 4 处仍返回非 0** ❌ |
| README | 缺输入输出解释、目标用户、验收方式、FAQ、已知限制、失败处理、复用建议、最小可运行自检清单 ❌ |

## 1. 对照题面五维评分的差距清单（task.md 评分表逐维）

| 评分维度 | 分值 | 上一轮实况 | 差距诊断 | 本轮补强点 |
|---|---|---|---|---|
| 实际效果 | 40 | 四合一审计、逐条核对表、闸门四态齐全 | 无新增差距 | 保持（**修 bug 优先**：build_result 崩溃会导致 result.json 根本不落盘，等于丢分） |
| 使用增益 | 25 | gain_evidence 有 16 项对照，但**5 项核心指标两遍数值完全相同**（有据率 0.5/0.5、强断言违规数 1/1、混淆数 1/1、待核条目数 7/7） | **真缺陷**：这些指标全部取自 fixed_evaluator（同一输入恒定），评审看到「两遍一样」= 读不出增益；「质量增益 15 分」拿不到 | ①新增 **delivered 口径**（随护栏开关变化）：有据率 0.5/0.0、强断言违规数 1/0、混淆数 1/0、复核者人工负担 2/11、残留缺陷率 0.0/1.0；fixed_evaluator 保留为「对照公平性证据」，两层各司其职 |
| 创新增益 | 15 | `--ablate` 可运行消融 + 机制→指标映射 | 机制可归因，但缺「同一批缺陷在两模式下被看见/看不见」的量化落点 | ②`gain_metrics.delivered` 新增 `delivered_evidence_rate` / `residual_defect_rate`；`gain_evidence.metrics` 21 行，每行带 `caliber` 标签 |
| 可靠体验 | 10 | 校验脚本失败路径 exit 0 | **4 处非零退出点仍在**（argparse 用法错误 exit=2、docx_build 读不到 draft.json 抛 FileNotFoundError exit=1 等）→ 交付链会被打断，与「失败也交付」协议直接冲突 | ③**8 个脚本全部失败路径 exit 0**：内容级 fail / 输入缺失 / 输入损坏 / argparse 用法错误 / 未捕获异常，全部如实落 verdict+error 到 stdout 与报告；`--strict-exit` 保留 CI 非 0 能力 |
| 生态贡献 | 10 | README 有机制表/增益证据/依赖/可复用/评分对照 | 缺文档完整性清单要求的 8 项中的 8 项：输入输出解释、目标用户与场景、验收方式、常见问题、已知限制、失败处理、复用建议、最小可运行自检清单 | ④README 重写为 16 节完整生态包：依赖与版本表 / 安装与运行 / 输入输出解释 / 机制清单 / 增益证据（双口径）/ **最小可运行自检清单（5 条命令）** / 验收方式 / FAQ（9 问）/ 已知限制 / 失败处理 / 复用建议 / 评分自评对照 / 文件清单 / 维护与版本 |

## 2. 改动清单（增量，不推翻）

| 文件 | 改动 | 保留的既有要素 |
|---|---|---|
| `scripts/trace_audit.py` | ①`gain_metrics.delivered` 新增 `delivered_evidence_rate`、`residual_defects`、`residual_defect_rate`；②草稿不可读时**也枚举 gates**（原先直接 return，看不到闸门状态） | 全文嵌入/闸门四态(+ablate 态)/status 四级/逐字回证/五元组 全保留 |
| `scripts/build_result.py` | ①**修真 bug**：契约回填把 `uncertainty`/`changelog` 置为 `None` → 后续 `.append()` 抛 `AttributeError: 'NoneType' object has no attribute 'append'` → **result.json 根本不落盘**（复现：`--gain-baseline` 单独传入、或 `--set` 传入时必崩）。新增 `_ensure_list()` / `_add_note()` 统一修复；②`--notes`/`--changelog` 由**覆盖**改为**追加**（原先会覆盖掉刚写入的 gain_evidence 缺口说明）；③`gain_evidence` 改为**双口径**（fixed_evaluator + delivered），21 行对照，每行带 `caliber`；④新增 `calibers` 说明块与 6 条边界 | 同上 + 原有 16 项对照全部保留 |
| `scripts/boundary_check.py` | argparse 改用 `_Parser`（`error()` 抛 `_Usage` 而非 exit 2）；统一 `_fail()` 输出；顶层 `_safe_main()` 安全网 | gates 枚举/四类检查 全保留 |
| `scripts/consistency_check.py` | 同上 | 五项一致性检查 全保留 |
| `scripts/fact_ledger.py` | 同上（含 `build`/`check` 两个子命令） | 台账构建 + 数值/DOI 校验 全保留 |
| `scripts/docx_build.py` | 补 argparse 用法错误处理 + draft.json 读不到的兜底（原为裸 FileNotFoundError → exit 1）+ 顶层安全网 | python-docx → stdlib 兜底 全保留 |
| `scripts/render_preview.py` | 同上 | no_renderer 降级不伪造 全保留 |
| `SKILL.md` | 149 行（**未超**）：协议第 8 条扩写为「全部失败路径 exit 0（含 argparse 用法错误/未捕获异常）」；Stage 4 补双口径说明；自查清单补 delivered 口径 5 指标条目。**命令统一 `python3`**（原本已全部是 python3，本轮复核确认） | 强制协议置顶/全文嵌入/三元组/五元组/闸门枚举 全保留 |
| `README.md` | 全文重写为 16 节生态包（见 §1 生态贡献行） | 机制清单 17 行、评分自评对照 16 行、增益证据边界全保留 |
| `examples/gain_evidence_example.json` | 用**本轮真实双跑**的 21 行对照刷新；加 `_fixture` 说明数字来源 | 字段名与 `build_gain_evidence()` 严格一致 |
| 未动 | `extract_materials.py`（已验证空输入 total=0、exit 0）；`task.md`（题面不改） | — |

## 3. 双测证据（真实运行数字，夹具为合成示意，非正式案例）

夹具：`_selftest/draft.md`（合规稿）、`_selftest/draft_polluted.md`（注入 5 类污染：数值篡改 18.7±1.3→19.9±1.3、强断言「证明」配文献依据、结果段「这说明…」推断-实测混写、引用未登记图「图3」、讨论段 2 句无【依据】标注）。

### 3.1 污染稿：完整模式 vs 退化基线（同输入两遍真实运行）

| 对照指标 | 口径 | 完整模式 | 退化基线 | 说明 |
|---|---|---|---|---|
| 统计表述总数（分母） | fixed | 4 | 4 | 同输入证明对照公平 |
| 统计表述有据率 | fixed | 0.5 | 0.5 | 同一草稿恒定 = 对照公平性证据 |
| 强断言违规数 | fixed | 1 | 1 | 真实缺陷数不随护栏开关变化 |
| 推断-实测混淆数 | fixed | 1 | 1 | 同上 |
| 需人工核对条目数（真实缺陷） | fixed | 7 | 7 | 同上 |
| **统计表述有据率** | **delivered** | **0.5** | **0.0** | ← 护栏关闭后无人回证 |
| **强断言违规数（已检出）** | **delivered** | **1** | **0** | ← 缺陷对复核者不可见 |
| **推断-实测混淆数（已检出）** | **delivered** | **1** | **0** | ← 同上 |
| **复核者人工核对负担** | **delivered** | **2** | **11** | 待核表述数 + 未暴露缺陷数 |
| **残留缺陷率** | **delivered** | **0.0** | **1.0** | 基线全部缺陷静默通过 |
| 本模式检出缺陷数 | delivered | 7 | 0 | 护栏的实际贡献 |
| 缺陷检出覆盖率 | delivered | 1.0 | 0.0 | 检出数 ÷ 真实缺陷总数 |
| 自动回证条数 | delivered | 2 | 0 | 免去的人工核对量 |
| 流程步骤数 | delivered | 16 | 11 | 基线省掉的 5 步 = 省掉的护栏动作 |

**关键结论**：退化基线 `verdict=pass` / `fail_count=0`，但 7 项真实缺陷对它全部不可见（`defects_hidden_from_reviewer=7`），复核者人工负担 11 vs 2，残留缺陷率 1.0 vs 0.0。这就是「关闭护栏 ≠ 通过」与「增益可验证性」的真实落点。
**输入一致性自证**：`same_input_verified=true`；两遍 `fixed_evaluator` 逐字段相等；draft/readings sha1 两遍相同。

### 3.2 干净稿（合规稿）双跑
`stat_statements_total=3`；**统计表述有据率（delivered）1.0 vs 0.0**；自动回证 3 vs 0；仍需人工回材料核对 0 vs 3；**复核者人工负担 0 vs 3**；步骤数 16 vs 11；完整模式 `verdict=pass`、fail_count=0。
`efficiency` 实测：`workflow_steps_executed=16`、`auto_verified_statements=3`、`delivered_evidence_rate=1.0`、`manual_review_items=0`、`reviewer_manual_burden=0`。

### 3.3 退出码契约：24 条失败路径全量实测（全部 exit=0）

| 类别 | 用例 | 实测 |
|---|---|---|
| argparse 用法错误（10 条） | 8 脚本无参数 + `fact_ledger build/check` 无参数 | **全部 exit=0** |
| 输入缺失/损坏（14 条） | trace_audit 草稿缺失/ledger 损坏；boundary 草稿缺失/readings 损坏；consistency 草稿缺失/constraints 缺失；fact_ledger 草稿缺失/ledger 缺失/源目录缺失；docx_build 草稿缺失；build_result trace 损坏/case 损坏/输出路径不可写；render_preview 源缺失 | **全部 exit=0** |
| `--strict-exit` 保留能力 | 4 个校验脚本在污染稿上 | **exit=1** ✅（CI 语义未被削弱） |
| 合规稿 `--strict-exit` | trace_audit 在 draft.md 上 | exit=0 ✅ |

### 3.4 build_result 真 bug 修复前后对照
| 场景 | 修复前 | 修复后 |
|---|---|---|
| `--gain-baseline` 单独传入（无 `--trace-audit`） | `AttributeError: 'NoneType' object has no attribute 'append'` → **result.json 不落盘**，exit 0 但交付物丢失 | `ok=true`，result.json 落盘，`uncertainty` 如实记「gain_evidence 未生成：缺少 --gain-baseline」 |
| `--set foo=bar` 传入 | 同上崩溃 | `ok=true`，`foo`/`bar` 正确回填 |
| `--notes` 传入 | 覆盖掉刚写入的 gain_evidence 缺口说明 | 追加不覆盖，缺口说明与用户 notes 并存（实测 `uncertainty` 3 条齐全） |

### 3.5 未修改脚本回归
`extract_materials.py`（空输入 → `total=0` 如实，exit 0）；`docx_build.py`（无 python-docx → stdlib 兜底 min-docx，exit 0）；`render_preview.py`（无渲染器 → `status=no_renderer`，不伪造，exit 0）。

## 4. README 最小可运行自检清单实测（5 条命令全 exit=0）
| # | 命令 | 实测 | 通过标准 |
|---|---|---|---|
| 1 | `extract_materials.py --input /input --outdir _acw/ext` | exit=0，`total=0` 如实 | ✅ |
| 2 | `fact_ledger.py build --sources _acw/ext --out _acw/ledger.jsonl` | exit=0，`facts=0` 如实 | ✅ |
| 3 | `trace_audit.py --draft _acw/missing.md --readings _acw/missing.jsonl` | exit=0，stdout 含 `gates`：`readings=not_found` / `ledger=skipped_not_provided` / `dclaims=skipped_not_provided` + `gate_notes` | ✅ |
| 4 | `build_result.py --case _acw/missing.json --out _acw/result.json` | exit=0，合法 JSON，`status=partial` 如实 | ✅ |
| 5 | `boundary_check.py --draft _acw/missing.md` | exit=0（`echo exit=$?` 显示 0） | ✅ |

## 5. 硬约束核对
| 约束 | 实测 | 结论 |
|---|---|---|
| SKILL.md ≤150 行 | **149 行** | ✅ |
| 零外部依赖 | 8 脚本全部 stdlib；docx/fitz/openpyxl 缺失时自动降级 | ✅ |
| 脚本 ≤8 | 8 个 | ✅ |
| 包 <2MB | 388K（已清理 `__pycache__`） | ✅ |
| 不预置正式答案 | `examples/` 两份均标「示意/非正式案例结果」；`gain_evidence_example.json` 加 `_fixture` 说明数字来自合成夹具 | ✅ |
| 不改题面 | `task.md` 未改 | ✅ |
| **不提交** | 未执行任何提交动作 | ✅ |

## 6. 未做 / 边界（沿用并强化诚实声明）
- 未做「基础 Agent vs Skill Agent」的模型输出对照：那需平台在固定案例上跑两个条件，本包无法代跑，亦不得预置其结果。gain_evidence 只声明「同一草稿的机制开关对照」，证明护栏检出能力，不冒充平台对照。
- 效率以步骤数与人工负担为代理指标；真实模型请求数/耗时由平台记录，本包不虚构。
- 退化基线计数归零属统计假象，已在 `gain_evidence.boundaries`（6 条）明示，避免被误读为「基线质量更好」。
- `dclaims.jsonl` 与 `readings.jsonl` 的联动仍是条数绑定，未做语义级对齐。
- boundary_check 的 `reading_trace_note` 仍为提示性，完整数值核查以 fact_ledger check 为准。
- 本轮未加新脚本（保持 ≤8），全部增强在既有 8 个脚本内增量完成。
