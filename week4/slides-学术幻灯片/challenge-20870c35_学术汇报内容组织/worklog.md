# worklog — talk-organizer（challenge-20870c35，slides 学术汇报赛道）

日期：2026-11-19 · 作者：w10-s2 · 版本 v1.0

## 1. 题面差距分析（vs 第3周冠军骨架 paper2deck）

题面五个突破方向：报告目标 / 听众 / 叙事顺序 / 重点信息 / 问答准备。第3周骨架已覆盖
「提取→构建→证据回证→模板继承→渲染」，但对**听众适配、叙事取舍、问答预演**是文字层描述、
无机械闸门。本包改动：

1. 新增「页级唯一主张」闸门（claim ≤40 字、恰一个）+ 备注强制含 `Q:` 预判追问闸门——把问答准备从「建议写」变成「不写就 FAIL」。
2. 新增叙事骨架闸门（title 开头、conclusion/closing 收尾、conclusion 不得先于 result）+ 时长软预算（讲稿字数/240≈分钟 vs 约束分钟）。
3. 新增 `probe_contract.py`：契约抄录、材料**校验式命中**探查（禁 find|head -1）、听众/时长/页数关键词约束提取。
4. 新增 `ablate.py` 三臂消融：skill / ablated（删证据映射+删问答+删主张，模拟搬运式基础路径）/ polluted（副本注入捏造主张+数字+引文），同一校验器判定，机制→指标映射带边界与失效条件。
5. 构建器与渲染全部纯标准库（zip+xml pptx；手写 SVG 预览），删除 python-pptx 依赖路径，符合「零外部依赖」硬约束。

## 2. 真实对照数字（本次实测，testrun 示意案例 demo-case-001）

全部数字由脚本真实输出（见 testrun/work/*.json），非文字声明：

| 指标 | A skill 臂 | B ablated 臂 | 差值 |
|---|---|---|---|
| verdict | pass | fail | — |
| quote_verifiable_rate | 1.0 | null（证据被删） | — |
| numeric_backed_rate | 1.0 | 0.0 | +1.0 |
| evidence_coverage_rate | 1.0 | 0.0 | +1.0 |
| notes_qa_rate | 1.0 | 0.0 | +1.0 |
| claim_single_rate | 1.0 | 0.0 | +1.0 |
| fails_total | 0 | 18 | -18 |
| 人工需核对条目 | 0 | 18 | 削减 18 |

- 污染反例：P 臂（A 副本注入「准确率提升37.2%」捏造数字+捏造引文）被 quote/numeric 闸门
  捕获 fails_total=3、quote_numeric_fail=3 → `validator_sensitivity.machine_verdict=true`（机器判定）。
- 效率计数：pages_built=6，mechanical_checks_run=81（3 臂 × checks_total 27），arms_validated=3。
- 构建实测：deck.pptx 31 parts / 6 slides / 5 notes，三关键 XML（presentation/slide4/notesSlide4）
  minidom 解析通过；SVG 预览 6 页 + index.html。
- probe 实测：contract_fields 4 个、source_chars 323、constraints 提取 audience=课题组组会成员 /
  duration_min=12 / slide_limit=10。

## 3. 诚实边界（不做超额宣称）

1. B 臂是同一计划的**结构化改写**（删机制），代表「有/无证据映射机制」的机制差，
   不是基础 Agent 的端到端复跑——平台白板对照才是端到端差。
2. 闸门机械可判：quote 逐字性、数字有据性、claim 唯一性、Q: 存在性、骨架顺序；
   **不可判**：问答质量、叙事文学性、排版美观——这些依赖评审与平台对照。
3. source_text 为空时 quote/数字闸门 skipped_not_provided，增益差不可机器判定，
   ablate 只登记不宣称。
4. PDF 文本依赖平台 pdf-text-tool；本包不自带 OCR/解析，缺工具时登记 needs_platform_pdf_tool。
5. 时长预算按 240 字/分钟估算，仅为软 warn。
6. 示例（examples/example_plan.json、SKILL.md 第 4 节、testrun）均为示意，非正式案例结果。

## 4. 硬约束自查

- SKILL.md 117 行（≤150），frontmatter 合法 YAML。
- 脚本 5 个（≤8）、包文件 9 个（≤50）、总体积 <100KB（<2MB）、全部 python3 标准库、零外部依赖。
- result.json 键归属：probe_contract=骨架+contract_fields+probe；ablate=gain_evidence+efficiency；
  verify_gate/build_deck/render_preview 只写独立报告文件，不写 result.json——无同键冲突。
- 全脚本失败路径 exit 0（含 argparse error→SystemExit 捕获）。
- 未使用 isalpha 判断汉字文本（数字/引文判定全用正则与归一化包含）。
- examples 与所有示例输出均标注「示意，非正式案例」。

## 5. 版本

- v1.0（2026-11-19）：首版保底+增益层全量交付。
