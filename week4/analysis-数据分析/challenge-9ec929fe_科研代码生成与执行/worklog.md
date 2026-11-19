# worklog — sci-code-exec（challenge-9ec929fe）

开发记录：2026-11-19。所有数字均为本机实跑结果，非估算。

## 1. 交付物

| 文件 | 说明 |
|------|------|
| SKILL.md | 145 行（≤150 合规），8 条强制协议 + 七步流程 + 输出 schema + 校验说明 |
| scripts/ 6 个脚本 | build_skeleton / run_trace / recompute / verify_check / schema_guard / gain_probe |
| examples/ 3 个文件 | 合成案例 + 示意输出 + 演示分析脚本（全部标注示意，非正式答案） |
| README.md / worklog.md | 说明与开发记录 |

合计 12 个文本文件、零第三方依赖、全脚本退出码恒 0。

## 2. 关键设计决策

1. **需求-代码覆盖映射**（requirements + coverage_map + code_artifacts 三件套）：
   题面机检点"需求-代码覆盖映射"的直接对应物；uncovered/partial 必须登记
   pending_review，映射到不存在的 artifact_id 判 FAIL。
2. **清洗口径事前声明**（cleaning_rules 台账 + declared_at）：任何计算之前声明
   dropna/dedup/filter/clip/impute，之后禁止调整；stats.rule_refs 引用不存在
   规则判 FAIL——防口径漂移与事后凑数。
3. **数值独立复算**（recompute.py 与分析代码分开实现）：从原始数据按声明口径
   重算每条统计再比对——专抓"跑通了但算错了"的静默错误（题面点名的最危险
   一类失败）；复算不符判 FAIL 且明令"修代码重跑，不得改数凑数"。
4. **执行留痕**（run_trace.py 包装 subprocess）：命令/python 版本/退出码/日志
   路径/墙钟全部落盘，失败现场保留；命令必须 python3 前缀——题面"过程与失败
   原因可被他人复核"的落点。
5. **异常登记不静默**：dropped/imputed/clipped/filtered 必须有 rule_ref 指向
   声明口径 + rows_affected + evidence_location；GHOST-RULE 类引用判 FAIL。
6. **键归属纪律**：execution_traces 只归 run_trace；recompute 只归 recompute；
   self_check/gates/unbacked_*/validator_verdict 只归 verify_check；
   gain_evidence/efficiency 只归 gain_probe——多脚本禁写同一键。
7. **防汉字陷阱**：全程不做 isalpha/isalnum 判定；ID/表名校验用显式正则
   （\w 字符类含 CJK）；数字比对只做数值与空白归一化。
8. **定位标志**：每个脚本校验自身与 SKILL.md 同包（marker_hit），未命中照常
   落盘但 WARN，不阻断交付。

## 3. 实测对照数字（2026-11-19，Python 3.13.14，Windows）

合成示例（7 行仪器数据：1 缺失 / 1 重复主键 / 1 超量程 / 1 范围外批次）：

- demo_analysis（分析代码）：n_score_missing_raw=1，n_after_clean=4，
  mean_score_A=10.6，mean_score_B=54.2（250 超量程截断为 100 后 (8.4+100)/2）。
- run_trace 双留痕：run_001 失败（exit_code=1，字段名笔误，日志 343 字节保留），
  run_002 成功（exit_code=0，日志 215 字节）——失败现场不删、修复可追溯。
- recompute 独立复算：S1=4 / S2=10.6 / S3=54.2 / S4=1，4/4 PASS，
  mismatches=0，verdict=PASS（与生成的分析代码互为独立实现）。
- verify_check：PASS，22 条检查项全部 applied；unbacked_numbers 与
  unbacked_evidence 均空。
- schema_guard：PASS，45 条检查项（output_contract 6 字段 + 业务 schema 21 键 +
  environment/run_status 子字段 + 契约字段）。
- gain_probe 双模式（干净输入）：normal verdict=PASS、degraded verdict=PASS，
  四类漏检均 0（干净输入无违规，delta=0 属实）；steps_count 26 vs 4（delta=22，
  来自四组检查项在退化模式被关闭）。
- gain_probe 污染反例（--inject-pollution 注入 8 项：删覆盖映射、artifact 失据、
  篡改统计值 4→5、rule_refs→GHOST-RULE、删 exit_code、清 log_ref、
  python_version 置空、anomaly rule_ref→GHOST-RULE）：
  - normal：verdict=FAIL，9 处问题，四类漏检全 0（8 处注入违规全部捕获，
    另有 1 处 coverage 汇总连带被抓）；
  - degraded：仅剩 1 处通用结构问题，四类漏检 = coverage 2 / trace 3 /
    recompute 1 / anomaly 2，合计 8 处客观违规被漏掉；
  - caught_by_normal_mode=true。
- 六脚本失败路径（case/脚本/result 全缺失）：全部 exit 0，骨架/痕迹照常落盘。
- 全部自测命令退出码 0。

## 4. 迭代中修过的问题

1. 合成数据集初版把重复行写成 record_id=3/4（测量值相同但主键不同），按
   record_id 去重规则去不掉——修正为真正的重复主键 3/3，与 CR-02 语义一致。
2. recompute.py 数据源解析残留一处死代码（`data.keys()[0] if False else ""`），
   清理为直接读 stat.source。
3. run_trace 打印 wall 时 None 值拼出 "wall=Nones"，改为 "n/a"。
4. verify_check stats.rule_refs 检查初版把 add() 放进循环导致每条引用都记
   match=False——改为整条统计一次性判定。

## 5. 诚实边界

- 本包全部对照数字基于**合成示例**（虚构仪器数据），不是平台正式案例结果；
  正式案例由平台固定 3 个案例运行。
- 增益对照是本校验层"正常 vs 退化"两模式，**不等于**平台"基础 Agent vs 参赛
  Skill"白板对照；后者由平台生成。
- 干净输入上 normal/degraded 漏检均为 0：无违规可漏不代表机制无效，机制区分度
  来自污染反例（上节后四行）。
- steps_count 的 delta=22 主要是"检查项被关闭"的计数效应，与漏检指标含义不同，
  已在 mechanism_to_metric_map 中分别标注 higher_is_better。
- cleaning_rules 的 clip 边界 [0,100] 等阈值是本技能保守设定（题面未给定数值
  口径），已事前声明并落台账，不冒充外部标准。
- recompute.py 覆盖八类基础统计；回归系数、检验 p 值等模型类结果不在独立复算
  闸内，靠分析脚本留痕 + claims 回证兜底。
- 追问轮次按每轮 3 条折算，非实测交互次数；efficiency.model_requests 由 Agent
  侧回填，脚本无法采集，缺失保持 null。
- examples/example-result.json 中的 execution_traces 是本机实跑回填（含真实
  时间戳/墙钟/日志字节），recompute/gain_evidence/self_check 为实跑回填，但
  案例本身是合成的，仅作接口示意；steps 中的 /app/... 路径为平台约定示意路径。
- 本机测试经 Git Bash 调用，MSYS 会把 /tmp 参数转换成 Windows 临时目录路径，
  痕迹里记录的是转换后路径；平台 Linux 环境无此转换。

## 6. 剩余风险

- 正式案例若以 SQLite/CSV 文件之外形态提供数据（如 Excel、Parquet），recompute
  的数据读取闸记 UNABLE 并要求登记 material_gaps——数值防漂移闸对该部分降级
  为 claims 回证。
- 若 case.json 数据集键不在 DATASET_KEYS 列表内，build_skeleton 会 WARN 并要求
  人工填充（骨架仍落盘），不阻断流程。
- 分析脚本若真需要第三方库（题面环境未预装时），run_trace 会留下
  ModuleNotFoundError 现场；SKILL.md 已写明降级路径（登记 + 标准库重写），但
  900 秒预算内能否完成重写取决于任务复杂度。
- 正式案例数据量大（数万行）时 recompute 的纯 Python 行级处理在 900 秒预算内
  可能吃紧；届时由 Agent 在 result.recompute.note 标注并降级为抽样复算，诚实
  登记而非假装全量复算。
