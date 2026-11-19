# worklog — challenge-a0e888fa 科研数据清洗与处理（sciclean-r1）

## 本轮（week4 首版：保底版 + 增益层，2026-11-19）

### 起点与策略

- 骨架沿用 week3 同域冠军包 clean2table-r5（challenge-f4bca185）的引擎机制与文档结构，按本题领域做领域化改造，品牌升级为 sciclean-r1。
- 本题组织方说明：案例为「已发表聚合表转录 + 显式注入的存储/编码故障 + 数据字典 + 逐指标单位/QC 规则 + 显式清洗工单」，不是原始实验数据；明令**不做总体统计推断、不填补缺失/无效源值**。SKILL.md 已把该纪律写进协议与异常处置表。

### 引擎改动清单（scripts/clean_run.py，相对 week3 版）

1. 新增数据完整性守恒机检：行数守恒（rows_in == rows_out + 合并行数）与换算汇总守恒（sum(new) == sum(trace.value_final)，仅计双端数值型条目），逐条三元组嵌入 machine_checks；可用 `--ablate conserve` 关闭做对照。
2. 新增审计链完整性机检：换算/归一/缺失格必须在行内嵌 ledger，缺失即 FAIL（week3 只验已有 ledger 的编号一致性，不验「该有而没有」）。
3. 故障注入器从单型（篡改 value_final）扩为三型：篡改换算值 / 静默删行（至多 2 行未改动行）/ 剥离审计台账（至多 2 格 ledger）；`_count_caught` 按问题关键词归类统计抓出数。
4. 消融档从 4 个扩为 7 个：unit / dirty / dedup / **anomaly（新增）** / **audit（新增）** / spot / **conserve（新增）**；metrics 新增 anomalies 维度。
5. 修复 week3 遗留 bug：`--ablate dedup` 时默认去重规则被自动回补导致消融失效（dedup 消融档指标与 normal 完全相同）；修复后 merged 1→0、rows_out 5→6，消融口径成立。
6. 领域字典扩充：sample/site（样品/采样点/批次）等聚合表常见列别名纳入自动规则推导。
7. check_standard 与 frontmatter description 同步新增守恒/审计链校验点。

### 文档改动清单

- SKILL.md 重写（112 行 ≤ 150）：规则事前声明流程（工单→rules.json 逐条翻译）、不填补纪律、守恒机检、脚本定位校验式命中（find 后 grep sciclean-r1 标志）。
- resources/rules-template.json 重写：按「工单条目→规则实例」组织，含 field_dictionary 转录位与 conflict_policy（register_not_resolve / register_not_guess / keep_empty_not_impute）。
- resources/result-schema.md 重写：完整 JSON 形态 + 7 条机检复核式（评分器可逐条验算）。
- README.md 重写：五类处理机制表、十项生态（自检清单/依赖/输入输出/场景/验收/示例/增益解读/FAQ/限制/失败处理/复用/维护/文件清单）、真实对照数字表。
- examples/example-case.json 新写（聚合表风格：字典+工单+6 行，含未知单位/超限/空白缺失/区间值/重复对各一）；example-result.json 为真实跑结果（非手写）。

### 真实对照数字（本机实测：python3 3.13，Windows；示例合成案例 demo-clean-001）

- selftest 全链路：skeleton/profile/run/check/evidence 退出码全 0；check 三元组 30/30 match（checks=16 spots=14 gates=5），all_pass=true，结论 PASS。
- 正常档 run：rows_in=6 rows_out=5 changed=11 merged=1 pending=3 dirty=1 anomalies=2。
- 消融对照（同输入同规则，engine 单趟 wall_seconds 毫秒级，见 gain_evidence.json）：
  - ablate_unit：convert 9→0，dirty 1→0，merged 1→0（无归一导致去重失效），rows_out 5→6，pending 3→4
  - ablate_dirty：dirty_values 1→0（静默丢弃），机检 problems 0→2，all_pass=false
  - ablate_dedup：merged 1→0，rows_out 5→6
  - ablate_anomaly：anomalies 2→0，pending 3→1
  - ablate_audit：机检 problems 0→7（审计链缺失逐条抓出），all_pass=false
  - ablate_spot：污染注入 caught 15→4，missed 1→12
  - ablate_conserve：污染 caught 15→14，missed 1→2
- 三型污染注入（injected=16：篡改换算值 13 / 静默删行 1 / 剥离审计台账 2）：正常档机检 caught=15 missed=1；关抽检后 missed 升至 12；关守恒后 missed 升至 2（守恒与抽检互为冗余防线，boundaries 已注明）。

### 硬约束自检（逐条）

| 约束 | 状态 |
|---|---|
| SKILL.md ≤150 行、合法 frontmatter | 112 行，name/description 合法 |
| 脚本 ≤8 / 文件 ≤50 / <2MB / 零外部依赖 | 1 脚本 / 10 文件 / 约 150KB / 仅标准库 |
| 命令一律 python3；挂载 /skills/weekly-skill；输入 /input/case.json + task.md；产出 /app/output/result.json | SKILL.md/README 全部按此写；契约键按 output_contract 动态补 |
| 所有失败路径 exit 0 | 自测 skeleton/profile/run/check/evidence/selftest 全 0；异常全捕获 |
| 不预置正式答案；examples 标注示意 | examples 为合成数据并标注「示意/非正式案例」；example-result 为该合成数据的真实跑结果 |
| 脚本定位标志文件校验式命中 | find + grep -q sciclean-r1 校验，SKILL.md 第 0/4 节与 README 第 1 节 |
| 多脚本禁写同一键 | 仅 1 个脚本，无多写者；防 isalpha 汉字陷阱——引擎不用 isalpha 判字段（正则+白名单记号表） |

### 诚实边界

- 对照数字来自自带合成示例（demo-clean-001），证明机制方向与机检有效性；3 个固定案例的真实增益以平台实跑为准，本包不预置答案。
- caught 按 problems 关键词归类计数：13 处值篡改在正常档由抽检逐条抓出（受每档 8 条上限影响实际抓出条数以 convert_spot_checks 为准），守恒校验作为聚合级冗余兜底；单一机制关闭后另一机制仍可能抓出同类污染，missed 反映兜底后的剩余漏检。
- 效率增益：引擎单趟毫秒级，模型请求数由平台统计，引擎只报自身 wall_seconds，不臆造请求数。
- 本机 Python 3.13 实测（沙箱为 3.12）：引擎仅用标准库，兼容 ≥3.8，风险低但非同一解释器版本。
