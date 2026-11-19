# worklog — lit-track-incremental（challenge-1e85736f）

制作时间：2026-11-19（第 4 期参赛包，当日完成保底版 + 增益层）
题面：week4-dl/challenge-1e85736f/task.md（最新文献发现与追踪）
骨架参考：bohrium-week4-final/challenge-2dd1f64c/submission（第 4 期已交付同类包）

## 1. 与题面机检点的逐条对应

| 题面考察点 | 本包落点 |
|-----------|---------|
| 时间窗口径一致 | `result.window`（start/end/timezone 事前声明）+ verify_check B 组机械校验 start<=end、ISO、时区非空；边界条目按 start<=date<=end 判入 |
| 新旧关系有据 | `track_engine.py` 版本链（同 dedup_key **或同 title_norm** 归并，覆盖预印本→正式版跨 DOI/arXiv 键）；duplicate/backfill/out_of_window 三分（延迟入库按 indexed_date>=窗口起点区分）；retraction 单成员链登记 |
| 时效排序可复算 | rubric 权重（relevance/recency/confidence 合计=1.0）机械复算 track_score；平局 track_score 降序→published_date 降序→item_id 升序；verify_check 逐位对照 ordered_ids 与 rank 连续性 |
| 来源可追溯 | `result.source_registry[]`（来源/查询式/抓取时间/条数/状态）+ 每条目 source_ref；verify_check D 组校验登记完整性 |
| 增量可回放 | watermark（上次快照引用+水位+窗口序号）+ dedup_policy + track_policy.json 口径台账全量落盘 |

## 2. 关键设计决策

1. **isalpha 汉字陷阱**：标题归一化用 `re.sub(r"[^\w]+","",s.casefold())`（`\w` 在 Unicode 下含 CJK），
   全程不使用 `isalpha()`（汉字 `isalpha()=True` 会破坏 ASCII/汉字区分逻辑）。校验器对每条记录
   独立复算 dedup_key 与存储值对照（items[].dedup_recompute，8/8 applied）。
2. **跨键版本链**：预印本（arXiv:2604.01234v1）→ 正式版（DOI 10.8888/sad）标识不同，纯 dedup_key
   分组归并不了；引擎用并查集按"同 dedup_key 或同 title_norm"归并，链上记 alt_keys 与归并依据。
3. **撤稿不推送**：event=retraction 由标题/版本标签/显式标记机械识别，登记单成员版本链；verify_check
   A 组强制 retraction 不得标 push（更正走人工通道）。
4. **backfill vs out_of_window**：发表日早于窗口起点时，按 indexed_date 是否 >= 窗口起点二分——
   延迟入库（可推送，解决"整段漏检"）与旧条目重复投喂（必须排除，解决"重复覆盖"）。
5. **多脚本禁写同一键**：track_engine 只写 items[].dedup_key/in_window/event/related_to/track_score/rank
   + ranking + version_chains；verify_check 只写 self_check/gates/unbacked_numbers/validator_verdict；
   gain_probe 只写 gain_evidence/efficiency。骨架与 Agent 判定字段归 build_skeleton+Agent。

## 3. 真实对照数字（本机实测，2026-11-19）

合成示例 examples/example-case.json（8 条记录）全链路实跑：

- **build_skeleton**：case_id=example-case-track-01，contract 字段 6 个，记录 8 条，上次快照键 2 个。
- **track_engine**：窗口 2026-05-01→2026-05-31，版本链 3 条（R1/R4 同 DOI 转载、R2/R3 跨键预印本→正式版、R6 独立撤稿），复算 6 条（R4/R7 无因子不参与排序）；事件分布 new=2, backfill=1, version_update=1, duplicate=1, retraction=1, out_of_window=1；R8 缺日期记 WARN 转 Agent 人工判定。
- **verify_check**：PASS，检查项 31 条全部 applied（含 8 条 dedup_key 复算、6 条 track_score 复算、顺序逐位对照、数字回证）。
- **schema_guard**：PASS，结构完整。
- **gain_probe 正常 vs 退化（--ablate all，同一输入双跑）**：
  - steps_count 38 vs 9（delta=+29，正常模式多执行 29 项机械检查）
  - 干净结果上五项漏检指标均为 0（delta=0，该输入上无客观违规可检——按 interpretation_rule 属"无区分度"，非"无增益"）
  - **污染反例注入（副本注入 5 项：push 清证据+降级 relevance、篡改 track_score=9.9999、duplicate 抹 related_to、hold 清 pending_reason、清空 pending_review+claims）**：
    - 正常模式 verdict=FAIL，抓出 **16 处**问题（样例：「R1 标 push 但 relevance='indirect'」「track_score 复算不符 期望 0.7864 实际 9.9999」「R4 event=duplicate 但 related_to 为空」）；caught_by_normal_mode=true
    - 退化模式 verdict=PASS，0 处——16 处违规全部漏检
    - 漏检 delta：consistency +1 / order +1 / evidence +6 / registry +4 / problems −16
- **efficiency**：双跑墙钟 <0.1s 量级；checker_runs=2；manual_review_items normal=0 / degraded=0；model_requests 留 null（由 Agent 按实际请求数回填，不臆造）。
- **失败路径实测（逐个脚本喂 /nonexistent.json）**：verify_check / schema_guard / gain_probe /
  track_engine / build_skeleton 全部打印 FAIL/WARN 并 **exit=0**，不中断交付。

## 4. 诚实边界

- 增益对照是**本校验层** normal vs degraded 双跑，不是平台基础 Agent 与参赛 Agent 的白板对照；
  平台对照由平台生成，本包不代替、不冒充。
- 干净示例上五项漏检 delta=0：增益主要由污染反例证明（正常 16 处全抓 vs 退化 0 处）；
  指标在"输入本身违规"的正式案例上才有直接区分度。
- 改题换封面（同一论文换标题再投）无法机械归并，只能 escalated 待复核兜底；
  已写入 gain_evidence.failure_conditions 与 SKILL.md 已知限制。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；原始计数落盘。
- examples 为合成数据（标题/摘要/DOI/arXiv 编号均虚构），文件头 `_note` 已标注示意，
  不冒充正式案例结果；正式案例不预置答案。
- 运行时脚本路径以 `/skills/weekly-skill/scripts/` 为准；examples 内绝对路径为制作机临时目录
  （C:\Users\hzm\AppData\Local\Temp\wk4b），正式运行以 /app/output 为准。

## 5. 交付自查记录

- SKILL.md：150 行（≤150 达标），YAML frontmatter 合法（name/description），协议 8 条置顶。
- 脚本 5 个（≤8），全部 `python3` 调用、标准库、退出码恒 0。
- 包内文本文件 8 个（SKILL/README/worklog + 5 脚本 + 2 示例），总体积 <2MB、单文件 <500KB（见自检输出）。
- 无 symlink；多脚本键归属无交叉；失败路径 exit 0 实测通过。
