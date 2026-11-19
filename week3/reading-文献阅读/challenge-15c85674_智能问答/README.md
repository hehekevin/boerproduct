# literature-qa — 文献智能问答 Skill（v5）

回答带段落编号论文的中文问题清单，**每个事实性子句独立挂 claim**（kind + evidence 逐字引文 + source_id + location），输出五字段契约 `result.json`（顶层 `case_id / status / result / claims / uncertainties`，答案全量嵌入 `result.answers[]`，机检闸门 `verification`、同输入增益对照 `gain_evidence`、效率计数 `efficiency` 均由脚本回写嵌入）。

## 1. 依赖与版本

| 项 | 说明 |
|---|---|
| 运行时 | Python **3.12+**（开发/自测于 3.13；兼容 3.12.1 官方镜像） |
| 外部依赖 | **无**。全部脚本只用标准库（json / re / hashlib / math / argparse / datetime / os / sys），评测阶段无需 pip install |
| 平台 | DSH 0.1.1-rc.2 固定镜像；模型 deepseek-v4.1-flash-1017；预算 64 次模型请求 / 单次 16384 输出 token / 900 秒 |
| 路径约定 | Skill 装入 `/skills/literature-qa`；输入 `/input/case.json`；产物 `/app/output/result.json`；运行日志 `/app/output/run_log.jsonl` |
| 资源体积 | 提交包 < 100 KB，脚本 2 个（硬约束 ≤8），远低于 2 MB 上限 |
| 许可 | 无外部代码/数据依赖，可直接复制使用 |

## 2. 安装与运行方式

无需安装（纯标准库）。把整个目录放到 `/skills/literature-qa`，然后按 SKILL.md 的 6 步流程执行；校验与取证用三条命令：

```bash
# ① 机检闸门（结构/引文逐字/数值回证/题面字段语义）→ 回写 result.verification
python3 /skills/literature-qa/scripts/check_result.py \
  --result /app/output/result.json --case /input/case.json

# ② 同输入「完整机制 vs 退化重放」双跑 + 效率计数 → 回写 result.gain_evidence / result.efficiency
python3 /skills/literature-qa/scripts/measure_gain.py \
  --case /input/case.json --result /app/output/result.json --mode compare --embed

# ③ 证据登记口径（互补，不覆盖 ②）→ 回写 result.registry_evidence
python3 /skills/literature-qa/scripts/gain_evidence.py \
  --result /app/output/result.json --source /input/case.json --write
```

三条命令**退出码恒为 0**（失败也不中断交付链），结论一律读回写的 JSON 字段：
`result.verification.verdict`（PASS/FAIL）、`.problems[]`、`.checks[]`、`.gates[]`。
**请勿用退出码判断成败。**

可选参数：

```bash
# 退化档：关闭检查组做对照（被关闭的检查记 applied=false、match=null，并在 gates 记 skipped）
python3 scripts/check_result.py --result R --case C --ablate evidence,numeric
#   可选组：evidence（引文逐字+claim四要素）、numeric（数值逐字回证）、structure（结构/覆盖/状态）
```

## 3. 输入与输出解释

**输入** `/input/case.json`：`case_id`、`paper_id`、`material_version`、带 `paragraph_id` 的段落清单
（字段名可能是 `paragraphs`/`passages`/`sections`，以实际文件为准）、`questions[]`（`question_id` + 文本）、
可选 `output_contract`（有则键名以其为准）。

**输出** `/app/output/result.json`：

| 字段 | 含义 | 题面对应 |
|---|---|---|
| `case_id` / `paper_id` / `material_version` | 输入标识，原样回填 | 输入标识 |
| `answers[]` | 每问一条：`question_id` / `answer` / `conditions[]` / `status` / `claims[]` / `unanswered_parts[]` | 逐题回答、回答状态、论断与证据、未完成部分 |
| `claims[]` | `claim_id` / `text` / `kind`(reported\|inferred) / `source_id` / `location` / `evidence[paragraph_id, quote]` | 论断与证据 |
| `coverage` | `read_paragraphs` / `unread_sections`（含原因）/ `note` | 阅读范围 |
| `result` | 上述业务字段的容器（同一真源，校验器会把同名字段逐字重述到顶层） | — |
| `uncertainties` | `unreported` / `unverifiable` / `conflicts` / `human_review` / `summary` | — |
| `verification` | 机检闸门：`state` / `verdict` / `mode` / `checks[]` / `gates[]` / `problems[]` / `normalization` | — |
| `gain_evidence` | 同输入双跑对照：`runs.full` / `runs.ablated` / `delta_full_minus_ablated` / `mechanism_to_metric` / `applicability` / `failure_conditions` | — |
| `efficiency` | 自动采集计数 `counters` + 每项 `sources` + `not_collected` + `reproduce` | — |
| `registry_evidence` | 证据登记口径：证据登记数、逐字回证率、相对基线的人工核对削减量（与 `gain_evidence` **互补**，两脚本谁先跑都不互相覆盖） | — |

`status` 四态：`answered`（子问完整回答）、`partial`（部分回答，缺口入 `unanswered_parts`）、
`insufficient_evidence`（材料无依据，"材料未报告"是有效回答）、`input_error`（输入读取失败）。

## 4. 目标用户与应用场景

| 角色 | 场景 | 收益 |
|---|---|---|
| 科研读者 | 读一篇带编号的论文，回答「这个数是多少 / 和谁比 / 什么条件」 | 答案每句可点回原文段落核对，不必自己翻 |
| 研究生 / 审稿人 | 快速核验某条结论的原文出处 | 引文逐字锚定 + 数值回证，可回原文复核 |
| 技术写作 / 科普 | 从论文抽取带证据的事实与条件 | 结构化 claims 可直接转成带引用的段落 |
| 文献综述作者 | 批量核验「论文是否报告了 X」 | `insufficient_evidence` + 检索范围显式给出，不硬答 |
| Agent / 工作流开发者 | 需要"带证据的 QA"能力 | schema 稳定、纯标准库、可插拔校验器 |

## 5. 验收方式（自查）

```bash
# A. 校验器内置正反例自测
python3 scripts/check_result.py --selftest
#   正例必须 PASS(0 problems)；反例必须抓到 case_id 不一致 / quote 改写 / 漏答 / unbacked 数值 四类错

# B. 增益测量器自测（双跑 + 机制映射 + 失效条件）
python3 scripts/measure_gain.py --selftest
#   必须 ALL PASS：4 项核心指标 full > ablated，delta 含 6 项指标

# C. 对示例产物跑全链路（合成材料，示意输出）
python3 scripts/check_result.py --result examples/example-result.json --case examples/example-input.json
python3 scripts/measure_gain.py --case examples/example-input.json --result examples/example-result.json --mode compare
```

交付前逐条核对：`result.verification.verdict == "PASS"`；`result.verification.state == "enforced"`；
`gain_evidence.verdict.has_comparable_pair == true`；`efficiency.not_collected` 中的项已在
`uncertainties.human_review` 说明原因。

## 6. 常见问题（FAQ）

**Q：`verification.verdict` 是 FAIL，但交付还能继续吗？**
能，且这是设计意图。退出码恒 0，不中断交付；请读 `verification.problems[]` 逐条回原文修复，
修完重跑第 4 步。`gates[].gate_note` 会写明哪些检查未执行（「下游不得宣称已核对」）。

**Q：`verification.state` 是 `skipped_not_provided` 说明什么？**
`case.json` 不可读或段落清单字段名未识别，引文逐字性未能机检。此时**不得**声称引文已核对，
需人工确认或用 `--case` 指向正确的输入文件。

**Q：段落清单字段名不是 `paragraphs` 怎么办？**
校验器依次尝试 `paragraphs`/`passages`/`paper_paragraphs`/`sections`，以实际文件为准；
都不匹配时降级为仅结构校验并在 `gates` 记录，不阻塞交付。

**Q：数值回证把段落号 `p01` 当成数值 01 误报了？**
v5 已修：标识符（`p01`/`q1`/`c-01`/`T1-23`）与引用标签编号（`表 12`/`图 23`/`第 3.2 节`/`Fig. 23`）
不计入答案数值。但**中文紧邻的数值必须计入**——"保持率为84.3%" 里的 84.3 要回证，
区间 `1.2-3.4` 的两端都要回证（两端是真实数据值，不能一刀切排除）。
数值口径已固化为校验器自测的 13 组回归用例。旧版产物需重跑校验器。

**Q：校验器和增益测量器的数值口径会不一致吗？**
不会。`measure_gain.py` 直接复用 `check_result.py` 的 `numbers()` 实现（同一份代码），
避免出现"校验器判失败、审计器判通过"的自相矛盾。

**Q：`gain_evidence` 能当平台白板对照用吗？**
不能。它是**同输入机制消融**（完整机制 vs 退化重放），证明机制对证据结构与核验指标的影响；
平台白板由平台侧按"不加载参赛 Skill"生成，本包不对白板数值做主张。

**Q：本地没有 `/input/case.json` 怎么测？**
用 `examples/example-input.json`（合成材料，示意输入）替代 `--case` 参数即可。

## 7. 已知限制

- 依据完全依赖给定段落文本：段落编号错位或文本截断会直接降低定位质量，属输入缺陷。
- 不读 PDF / 图像 / 补充附件 / 联网检索——此类内容一律按"材料未提供"处理。
- `inferred` 论断的**语义**正确性无法机械校验；脚本只校验结构、引文逐字性、数值回证与密度。
- 子问拆解用标点与并列词启发式（非分词模型）：无标点的长句可能拆得过粗，此项已在
  `gain_evidence.applicability.not_applicable_to` 中声明为对照失效条件。
- `gain_evidence` 的数字由**规则式审计器**对产物计算，可比较机制对证据结构的影响，
  不能据此推断最终答案的措辞质量（见 `applicability.measurement_limits`）。
- 效率计数依赖运行时写 `/app/output/run_log.jsonl`；缺失时相应项记 `null` 并列入
  `efficiency.not_collected`，不臆造数字。

## 8. 失败处理

| 失败点 | 处理 | 是否阻塞交付 |
|---|---|---|
| case.json 缺失/乱码 | 全部 `status=input_error`，`unanswered_parts` 写明原因，仍输出合法 result.json | 否 |
| 段落清单未识别 | 闸门置 `skipped_not_provided`，降级为结构校验，`gate_note` 声明未核对 | 否 |
| 校验器不通过 | `verdict=FAIL` + `problems[]` 逐条记录，回原文修复后重跑 | 否（退出码 0） |
| 校验器/测量器脚本异常 | 脚本内 `try/except` 兜底，降级打印并 `exit 0` | 否 |
| 增益取证缺失 | `gain_evidence`/`efficiency` 缺失只记 warn，不阻塞 | 否 |
| 预算逼近上限 | 按 SKILL.md 协议第 4 条停止新增，用现有中间结果收尾 | 否 |

**任何失败路径都不会让 `/app/output/result.json` 缺失或不可解析。**

## 9. 复用建议

- **换领域**：只需替换段落清单与问题清单，schema 与 7 条协议完全不变（材料 / 机械 / 计算机 / 环境工程通用）。
- **换语言**：`split_subquestions` 与 token 化按中英文混排设计；纯英文问题可把问号切分直接用。
- **接到别的 Agent**：SKILL.md 的 6 步流程 + 两条命令即可，无需改脚本。
- **扩展检查**：在 `check_result.py` 的 `check()` 里加检查项即可自动进入 `verification.checks[]`
  与 `gain_evidence` 的对照口径；新增可消融检查组时同步 `ABLATE_GROUPS`。
- **接入 CI**：读 `result.verification.verdict`（不要读退出码）。
- **可复用的工程实践**（详见 worklog.md）：① 证据逐字锚定 + 数值回证机检；② 子句级 claim 拆解；
  ③ 诚实四级状态 + 缺口显式化；④ 同输入机制消融做增益取证；⑤ 校验失败不中断交付、结论读字段。

## 10. 版本维护信息

| 版本 | 日期 | 主要变更 |
|---|---|---|
| v5 | 2026-11-17 | 新增 `gain_evidence`（同输入完整机制 vs 退化重放双跑、6 项指标 delta、机制→指标映射、适用边界、失效条件）与 `efficiency`（自动采集计数 + 来源 + 复现命令）；校验器新增题面《输出要求》表逐项字段语义核对、顶层字段归一、`--ablate` 退化档（applied=false/match=null）；**所有校验失败路径退出码改为恒 0**，结论改读 `verification.verdict`；修正标识符内嵌数字被误判为未回证数值的缺陷 |
| v4 | 2026-11-16 | 机检闸门逐条四元组嵌入 result.json；闸门四态显式枚举；数值逐字回证升级为 fail；claim 四要素强制；SKILL.md 压至 150 行 |
| v3 | 2026-11-15 | 子句级证据密度；校验器 v3；协议 7 条置顶 |

维护约定：修改产物结构时**同步**更新 `SKILL.md` 的 schema 段、`check_result.py` 的
`check_spec_alignment()` 与 `examples/example-result.json`；`SKILL.md` 硬约束 ≤150 行、
脚本 ≤8 个、纯标准库、包 <2 MB。改完必须跑完第 5 节的 A/B/C 三项自测并把真实输出贴进 worklog.md。

## 最小调用示例（示意，非正式）

输入（`examples/example-input.json`，合成材料）：单段 p01（84.3% vs 71.0% 保持率）+ 两问。

输出关键片段（`examples/example-result.json`，示意）——演示"答案子句 ↔ claim ↔ 逐字引文"一一对应：

```
answers[q1].answer   = "...保持率为 84.3%，未涂层电极为 71.0%；据材料推断...约 13.3 个百分点。"
answers[q1].claims   = 4 条：c-01/c-02/c-03 (reported, 各带逐字 quote) + c-04 (inferred, 13.3 在其 claim 文本中)
answers[q2].status   = "insufficient_evidence"，answer 写明已检索范围（材料未报告热稳定性）
```

校验器对示意输出 PASS：13.3 是计算推断值，出现在 inferred claim 文本中，符合"数值逐字回证"的推断豁免规则。
此为**示意输出，不作为正式效果证明**；正式案例的隐藏论文与九问由平台保管，本仓库不预置任何正式答案。

## 关键改进（相对白板与 v4）

1. **同输入增益对照落盘**（`gain_evidence`）：完整机制 vs 退化重放双跑，6 项指标逐项 delta，
   附机制→指标映射、适用边界与失效条件；数字由脚本运行时算出并随输入/产物指纹留痕，可复算。
2. **效率计数落盘**（`efficiency`）：请求数/工具调用/证据定位次数/返工轮次等自动采集计数，
   每项标注来源与复现命令，明确不是人工计时。
3. **题面字段语义逐项核对**：新增 `check_spec_alignment()`，按题面《输出要求》表逐行核对
   输入标识、逐题回答、回答状态、论断与证据、未完成部分、阅读范围，缺失即 fail。
4. **校验失败路径退出码恒为 0**：verdict 照实写入 `verification.verdict`，不中断交付链。
5. **顶层字段归一**：`result` 内的业务字段逐字重述到顶层（`paper_id`/`material_version`/`answers`/`coverage`），
   满足题面"与 case_id 同层"的要求，且只搬运不生成，搬运事实记入 `verification.normalization`。
6. 沿用 v4 已验证机制不回退：协议置顶 7 条、骨架先行、子句级证据密度、诚实四级状态、
   quote 逐字子串校验、脚本三级容错。


## 生态贡献：依赖、安装运行、目标用户与验收

| 项目 | 说明 |
|---|---|
| 依赖与版本 | Python 3（评测沙箱 3.12；本 Skill 脚本仅用标准库，无需 pip 安装）；所有命令用 `python3` 调用。 |
| 安装与运行 | 平台把提交目录装入 `/skills/literature-qa`；输入 `/input/case.json`（含段落清单与问题清单），产物写 `/app/output/result.json`。 |
| 输入 / 输出解释 | 输入=case_id/paper_id/material_version + 带 paragraph_id 的段落清单 + questions[]；输出=result.json（契约全字段 + 逐条证据 + verification 闸门 + gain_evidence + efficiency + registry_evidence + uncertainties）。 |
| 目标用户与场景 | 需「产出可直接用、且每条结论都能回到原文核对」的作者与审阅者；用于成稿前的自检与交付留痕。 |
| 验收方式 | ①契约键一个不缺且 JSON 可解析；②每条论断带可回证的 evidence 与来源位置；③闸门状态显式、非 enforced 有 gate_note；④gain_evidence 含基线与当前两套指标及削减量。 |
| 常见问题 | 证据回证失败→换原文短引文而非改写；材料缺失→按题面要求登记缺口而非补零；机检不过→修一轮并如实登记结论。 |
| 已知限制 | 增益对照为同输入自比，量化的是核对工作量与漏检率，不等同于跨模型横向评测。 |
| 失败处理 | 任一步异常：写盘已有产出、status 如实降级、uncertainties 记录失败点与缺口；机检结论照实记录（verification.verdict）且退出码恒 0。 |
| 复用建议 | 直接复用 scripts/；证据与闸门的字段结构可套用到同类「产出+核对」任务。 |
| 版本与维护 | 见 worklog.md 版本小节；结构变更时同步本表与 SKILL.md 输出字段说明。 |

## 最小可运行自检清单（复制即跑）

```bash
python3 -c "import sys;print(sys.version)"   # 1) 解释器可用
ls scripts/                                   # 2) 脚本在位
python3 scripts/check_result.py --selftest   # 3) 校验器正反例自测
python3 scripts/measure_gain.py --selftest    # 4) 增益双跑自测
python3 scripts/gain_evidence.py --help       # 5) 证据登记脚本可执行
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"  # 4) 产物可解析且键齐全
```
