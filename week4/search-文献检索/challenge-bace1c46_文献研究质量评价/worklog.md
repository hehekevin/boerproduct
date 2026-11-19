# worklog — lit-quality-appraise（challenge-bace1c46）

开发记录：2026-11-19。所有数字均为本机实跑结果，非估算。

## 1. 交付物

| 文件 | 说明 |
|------|------|
| SKILL.md | 141 行（≤150 合规），8 条强制协议 + 七步流程 + 输出 schema + 校验说明 |
| scripts/ 5 个脚本 | build_skeleton / grade_rollup / verify_check / schema_guard / gain_probe |
| examples/ 2 个文件 | 合成案例 + 示意输出（全部标注示意，非正式答案） |
| README.md / worklog.md | 说明与开发记录 |

合计 10 个文本文件、零第三方依赖、全脚本退出码恒 0。

## 2. 关键设计决策

1. **判断 → 分级用声明映射机械导出**（grade_map / category_map），而不是让模型自由
   打分——这是"分级口径一致"机检点的直接对应物：verify_check 独立复算每条
   grade/category，漂移即 FAIL。
2. **证据双闸回证**：引文必须在 claims 证据链逐字命中，且必须在 case.json 实际
   来源文本中逐字存在（空白归一化子串匹配）。第二道闸直接对应题面"引用的证据
   片段是否真实存在于所标位置"。
3. **缺陷/报告不全硬区分**：category_map 强制 inadequate⇒design_flaw、
   unreported⇒reporting_gap，互换判 FAIL——题面明确要求区分两者，且这是基础
   Agent 最容易混的维度。
4. **弃权不罚分**：unassessable → penalty 0 但必须登记 pending_review；弃权且
   penalty 落在 low 档时整篇降为 uncertain（abstain_rule 事前声明）——防止
   "漏评被当成好评"。
5. **键归属纪律**：grade_rollup 只写 risk_summary；verify_check 只写顶层四键；
   gain_probe 只写 gain_evidence/efficiency——多脚本禁写同一键。
6. **防汉字陷阱**：token 校验用显式正则（\w 字符类含 CJK），全程不做
   isalpha/isalnum 判定；引文匹配只做空白归一化。
7. **定位标志**：脚本校验自身与 SKILL.md 同包（marker_hit），未命中照常落盘但
   WARN，不阻断交付。

## 3. 实测对照数字（2026-11-19，Python 3.13，Windows）

合成示例（2 篇 × 6 维度 = 12 条评价）：

- grade_rollup 复算：Q01 penalty=5 → risk=high、direction=against_conclusion；
  Q02 penalty=1、弃权 1 → risk=uncertain、direction=unclear。
- gain_probe 双模式（干净输入）：normal verdict=PASS、degraded verdict=PASS，
  五类漏检均 0（干净输入无违规，delta=0 属实）；steps_count 59 vs 18（delta=41，
  来自五组检查项在退化模式被关闭）。
- gain_probe 污染反例（--inject-pollution 注入 7 项：缺陷混淆、分级漂移、编造
  引文、删 appraisal、篡改 risk_summary、清空 pending_review、清空 claims）：
  - normal：verdict=FAIL，21 处问题，五类漏检全 0；
  - degraded：仅剩 1 处通用结构问题，五类漏检 = coverage 1 / grading 2 /
    evidence 8 / defect 1 / pending 1，合计 13 处客观违规被漏掉；
  - caught_by_normal_mode=true。
- verify_check（clean）：53 条检查项全部 applied，verdict=PASS；
  unbacked_numbers 与 unbacked_evidence 均空。
- schema_guard：PASS（output_contract 6 字段 + 业务 schema 全字段齐）。
- 全部 5 条自测命令退出码 0。

## 4. 迭代中修过的问题

1. build_skeleton 提取 paper_id 时 doc_id 误占 paper_id（did 优先级写成
   doc_id→id→paper_id），修正为 paper_id 优先。
2. verify_check docstring 含 `\w` 触发 SyntaxWarning，改写措辞规避。
3. 污染注入「删除 appraisal」后，退化模式仍被始终开启的 coverage 汇总检查抓到
   （items_total 不符），导致 coverage 漏检 delta=0、机制区分度不清——把该汇总
   检查的问题串改标 [structure]（它本质是通用结构一致性），domain 覆盖机制的
   漏检 delta 恢复为 1，机制→指标映射更精确。

## 5. 诚实边界

- 本包全部对照数字基于**合成示例**（虚构文献文本），不是平台正式案例结果；
  正式案例由平台固定 3 个案例运行。
- 增益对照是本校验层"正常 vs 退化"两模式，**不等于**平台"基础 Agent vs 参赛
  Skill"白板对照；后者由平台生成。
- 干净输入上 normal/degraded 漏检均为 0：无违规可漏不代表机制无效，机制区分度
  来自污染反例（上表后五行）。
- steps_count 的 delta=41 主要是"检查项被关闭"的计数效应，与漏检指标含义不同，
  已在 mechanism_to_metric_map 中分别标注 higher_is_better。
- grading_rules 的 penalty/thresholds 是本技能保守设定（题面未给定数值口径），
  已事前声明并落台账，不冒充外部标准。
- 追问轮次按每轮 3 条折算，非实测交互次数；efficiency.model_requests 由 Agent
  侧回填，脚本无法采集，缺失保持 null。
- examples/example-result.json 中的 self_check/gates/risk_summary 等键为本地
  实跑回填结果，但案例本身是合成的，仅作接口示意。

## 6. 剩余风险

- 正式案例若把全文以图片/非 UTF-8 编码提供，证据回证第二道闸（来源文本逐字
  存在）会自动降级为 claims 链回证并跳过来源比对（doc_index 为空时 in_src=True），
  会在 material_gaps 登记——机检点"证据定位可回证"仍然由第一道闸保证。
- 正式案例若文献数量大（几十篇），Agent 需在 900 秒预算内广度优先逐条评价；
  SKILL.md 协议 6 条已写明预算保护与 partial 交付路径。
- 若 case.json 文献键不在 PAPER_KEYS 列表内，build_skeleton 会 WARN 并要求人工
  填充（骨架仍落盘），不阻断流程。
