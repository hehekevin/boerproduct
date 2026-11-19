# worklog.md — challenge-8021aacb 开发记录（真实对照数字，全部来自本地自检实测）

## 版本

- v1.0（2026-11-19）：初版。六类结构机检校验器 + 模型语义诊断合并层 + 消融两臂增益证据 + 污染反例注入。

## 本地自检环境

- 平台 Windows 11 / Python 3（Git Bash）；模拟 Harness：`_selftest/input`（case.json + 示意稿件
  + task.md）、`_selftest/work`、`_selftest/output` 分别对应 /input、/app/work、/app/output。
- 测试稿件 = examples/example_input.json 的 _text（故意植入：绝对化结论句、相关说成因果、
  跨章节重复段、无证据论断、缺局限性说明），**该稿件为示意夹具，非正式案例**。

## 真实对照数字（本次实测，非文字声明）

全流水线（extract → claim → structure_check 两臂 → edit_plan → gain_evidence → build_result）：

| 指标 | 完整臂（skill_full） | 消融臂（ablated_generic） | 差值 |
|---|---|---|---|
| FAIL 数（finding 总数） | 10 | 0 | **10**（机器判定） |
| 章节结构 | 2 | 0 | 2 |
| 研究问题对齐 | 0 | 0 | 0 |
| 论证链 | 3 | 0 | 3 |
| 段落关系 | 0 | 0 | 0 |
| 重复内容 | 1 | 0 | 1 |
| 结论边界 | 4 | 0 | 4 |
| 六类覆盖数（非零类） | 4 | 0 | 4 |

- 论点—论据映射：claims_total=8；same_sentence=3 / same_paragraph=2 / none=3。
- 污染反例注入：植入 3 处（跨章节重复段 / 绝对化结论句 / 无证据论断），完整臂命中 **3/3**，
  命中类别 {claim_boundary, claim_evidence, repetition}，verdict=pass。
- 契约回填：output_contract 6 字段全部填充（6/6）；result.json 22 键可解析。
- 全部命令退出码 0（含 5 条失败路径实测：坏参数 / 缺输入目录 / 坏 JSON 稿件 / 坏 result.json /
  不可写输出路径，均 exit 0 且状态如实写 JSON）。

## 开发过程中修掉的问题（对齐硬约束）

1. `_norm` 正则引号拼接引发 SyntaxWarning（非 raw 分段）→ 改为三引号 raw 字符串。
2. 方法名跨章对齐检查对纯描述性短语误报（截 14 字在别章搜不到）→ 改为仅对 ASCII 标识符/
   引号内专名做机械对齐，描述性表述留给模型语义层（误报 F004 消除，skill_full 11→10）。
3. edit_plan 去重键缺位置 → 「结果」与「结论」两处同文重复被误并一条；键改为 类别+引文+位置，
   两条各留（10 条 finding 全保留）。
4. structure_check run_arm 误弹 suggested_action.instruction 当 basis → 修复，动作说明完整保留。

## 诚实边界

- 增益对照是**同输入自比**（完整臂 vs 同一校验器消融臂），量化的是机检可发现的结构问题数，
  不等同跨模型横向评测；不宣称评分提升。
- 消融臂按设计六类全关，FAIL 数恒低；差值证明的是「结构级检测能力的机检证据」，语义正确性
  仍依赖模型诊断层与作者复核（report.md 裁决栏）。
- 六类中「研究问题对齐」「段落关系」在示意稿上检出 0 条：示意稿方法名跨章一致、段落长度
  正常，属正常无缺陷而非检测器失效（检测器非空转由污染反例 3/3 命中证明）。
- 重复检测对大改写同义表述会漏检（归一化全等/包含/Jaccard≥0.85 的边界）；结论边界词表有限。
- 正式案例的表现（3 案例 × 基础/Skill 对照）由平台运行产生，本包不含、不预置正式答案。
