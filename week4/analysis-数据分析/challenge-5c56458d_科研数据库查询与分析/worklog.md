# worklog — challenge-5c56458d 科研数据库查询与分析 Skill 包

日期：2026-11-19　作者：w7-ana5　状态：保底版 + 增益层完成，全部自检 PASS

## 1. 交付内容

- SKILL.md（145 行，合法 frontmatter，标志 `sci-db-query-analyze-v1`）
- scripts/ 6 个：build_skeleton / query_engine / stat_recompute / verify_check /
  schema_guard / gain_probe（全部 stdlib-only、退出码恒 0、键归属分键写入）
- examples/ 2 个：合成案例（2 数据集 4 问题 5 查询，虚构数据已标注）+ 全链路实跑示意输出
- README.md（生态十项 + 最小自检清单 + FAQ）+ 本 worklog

领域设计对应题面五方向：查询语句（问题→结构化查询+SQL 形留痕）、结果抽取
（结构化 query_results+复算）、字段解释（field_dictionary+编码型字段不当数值聚合）、
跨表分析（两步显式传键控制膨胀）、数据库连接（不连真实库，对授权快照内存查询——
题面案例已改为 SQLite/CSV 快照，load_rows 即可替换为授权连接）。

## 2. 硬约束自检（逐条）

| 约束 | 结果 |
|------|------|
| SKILL.md ≤150 行合法 frontmatter | 146 行，name/description 齐全 |
| 脚本 ≤8、包 <2MB、≤50 文件、零外部依赖 | 脚本 6、文件 11、约 60KB、stdlib-only |
| python3 一律命令 | 全部命令 python3 开头 |
| 挂载 /skills/weekly-skill；输入 /input/case.json | SKILL.md 命令均按此路径 |
| 产出 /app/output/result.json 含 case_id + output_contract 全字段 | schema_guard 校验 [contract] 组 |
| 所有失败路径 exit 0 | 6 脚本全部 try/except 包裹，exit 恒 0；verdict 照实写 JSON |
| 不预置正式答案 | examples 数据虚构且标注"非正式案例答案" |
| 定位标志校验 | 各脚本 marker_hit() 校验 SKILL.md 含 `sci-db-query-analyze-v1`，实测 True |
| 多脚本禁写同一键 | queries/query_results/query_log/boundary_registry←engine；recompute←recompute；self_check/gates/unbacked_*/validator_verdict←verify；gain_evidence/efficiency←probe |
| 防 isalpha 汉字陷阱 | build_skeleton.IDENT_RE 用显式字符集（ASCII+汉字+._-，禁空白/控制符），SKILL.md 协议 6 明文禁用 isalpha() |

## 3. 真实对照数字（2026-11-19 实跑）

全链路（examples 合成案例）：
- build_skeleton：exit 0，marker_hit=True，datasets=2，questions=4
- query_engine：exit 0，执行 5 条查询，行数 12/6/6/2/0，errors=0；
  QA-04 空结果自动登记 boundary；coverage answered_questions=4/4，ratio=1.0
- stat_recompute：exit 0，13 项检查（row_count×5 + aggregate×6 + 守恒×2）全 ok
- gain_probe：exit 0，clean_normal=0 / clean_degraded=0（干净输入零漏检）；
  污染副本 normal 抓 10 处 / degraded 抓 0 处，注入 8 项，caught_by_normal_mode=True
- verify_check：exit 0，verdict=PASS，problems=[]
- schema_guard：exit 0，verdict=PASS，problems=[]

增益分组明细（污染副本）：

| 组 | normal | degraded | delta |
|----|--------|----------|-------|
| mapping | 2 | 0 | +2 |
| recompute | 5 | 0 | +5 |
| boundary | 1 | 0 | +1 |
| log | 1 | 0 | +1 |
| conservation | 1 | 0 | +1 |
| 合计 | 10 | 0 | +10 |

recompute 组 5 处 = 数字篡改独立抽查 2 处（QA-01 row_count/聚合）+ 条件遗漏引发的
行数/聚合抽查不一致 2 处（QA-02a）+ 绕开机械复算 1 处。

**平台形态模拟**（临时目录按 /input→/app/output 流程另跑一遍）：全链 exit 0，
verify_check/schema_guard 均 PASS，数字与上表一致（normal 10 / degraded 0）；
另验证空骨架状态（未填 queries/steps）被 verify_check 正确判 FAIL（"没跑≠通过"），
`--ablate mapping,boundary` 部分消融参数化正常（2 vs 1、3 vs 2）。

## 4. 开发过程中的真实修正

1. **marker 未命中**：首版 SKILL.md 没有标志字符串，脚本报 marker_hit=False；
   在"定位与约定"节补 `sci-db-query-analyze-v1` 后命中。
2. **条件遗漏抓不到**：初版污染"删除过滤条件"不产生任何违规（复算基于改后定义，
   结果与日志一致）。修复：verify_check [mapping] 增加"查询定义与 query_log.issued
   记录一致性"检查；条件遗漏被删后定义与日志不符即 FAIL。
3. **复算段清空掩盖数字篡改**：recompute_drop 注入清空 checks 后，聚合/行数篡改失去
   比对基础（8 项只抓 5）。修复：注入改为 computed_by='agent-manual'（绕开复算而非
   清空），且 verify_check 增加独立抽查——不信任已有 checks，直接对原始数据重算
   row_count 与各聚合。捕获从 5 升至 10。
4. **coverage 计数漏手工登记**：query_engine 覆盖 boundary_registry 时把 Agent 手工
   登记丢掉导致 coverage 计数偏差；修复为保留 kind 以 manual_ 开头的条目并计入总数。
5. **schema_guard 条件表达式可读性差**：嵌套三元表达式重构为显式分支。

## 5. 诚实边界

- 增益对照是**本校验层** normal vs degraded 两模式，不是平台"基础 Agent vs Skill"
  白板对照；白板由平台生成。
- 污染注入 8 类只覆盖客观违规（数字篡改/条件遗漏/留痕删除/绕开复算/悬空映射），
  不能证明查询语义正确；语义正确性靠映射纪律 + 独立复算 + 人工复核 pending_review。
- 不连真实数据库：查询是内存模拟（题面约定如此）；真实库需外接授权连接读快照。
- efficiency.model_requests 由 Agent 回填，脚本侧保持 null（无法采集）。
- 干净输入 normal=degraded=0：消融差异只在污染副本上显现——这符合预期（两模式对
  合规输入都该零误报），也意味着增益证据的说服力依赖污染反例的真实性（副本注入
  可在 /app/work/gain_probe_polluted.json 逐条核对）。
- 缺失值口径固定为"剔除后聚合"并在 boundary 登记；若题目要求其它口径需在
  query_convention 显式改声明。

## 6. 剩余风险

- 正式 case.json 的数据集键名/行结构若与探测键（datasets/tables/snapshots/data、
  rows/records/data/samples、矩阵或 dict 行）不同，build_skeleton 会给出 WARN，
  需 Agent 按 SKILL.md 手工兜底——已写进异常处置表。
- SQLite 案例若以 .db 文件而非 JSON 行提供，当前 load_rows 不读二进制；届时需
  Agent 用环境自带 sqlite3 CLI 导出后按 rows 粘入 result（不违反零依赖约定）。
