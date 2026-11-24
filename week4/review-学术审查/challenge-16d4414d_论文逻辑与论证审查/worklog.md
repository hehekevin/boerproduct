# worklog.md — evidence-support-review 开发记录（challenge-16d4414d，v2 极简重构）

日期：2026-11-22 ｜ 作者：r2-16d4414d ｜ 状态：极简单点重构完成

## 1. 砍了什么（v1 → v2 的关键取舍）

v1（argchain-review）做四个方向、5 个脚本、约 118KB；v2 按"极简单点"策略收敛到
**一个方向 + 3 个脚本**，最大幅度降低重放 Agent 的误判面与执行成本：

| 维度 | v1 保留 | v2 砍掉 |
|------|---------|---------|
| 突破方向 | 证据支撑核查（方向2） | 论证链完整性（方向3）、章节衔接一致性（方向4）、严重度分级建议（方向5） |
| 脚本 | build_skeleton / evidence_check / schema_guard | chain_audit.py（节点完备审计）、gain_probe.py（增益双跑） |
| 增益层 | gain_evidence 双跑 + 污染反例 | **available=false**（预算过半即跳过，不编数字） |
| 问题类型 | 六类（含 broken_chain/circular_reasoning/missing_rebuttal） | 五类证据支撑问题（no_evidence/insufficient_evidence/strength_mismatch/citation_unsupported/overgeneralization） |
| 论证链 | argument_chains[] 节点角色追踪 | 删除，改为 claims[] 主张强度匹配 |

**砍依据**：题面"可选择的突破方向"明说"参赛者只需要选择一个明确问题，形成最小成果"。
原 v1 四方向并行 + 逐句通读全文，正是题面列的"长文截断仍宣称完成全文审查""定位只到章节名"
"误读对照/假设/转述"的高发区。v2 只做证据支撑核查，并把重放范围缩到"摘要+结果的核心主张
（5-10 条）"，宁少勿滥。

## 2. 规模上限（硬约束对照）

| 约束 | 上限 | 本包实际 | 达标 |
|------|------|---------|------|
| SKILL.md 行数 | ≤150 | 112 | ✅ |
| 脚本数 | ≤8 | 3 | ✅ |
| 文件总数 | ≤50 | 8 | ✅ |
| 总大小 | <2MB | 约 115KB | ✅ |
| 单文件 | ≤500KB | 最大约 27KB | ✅ |
| 依赖 | 零依赖 | 纯标准库 | ✅ |
| 挂载路径 | /skills/weekly-skill | 标志文件定位 | ✅ |
| 预置答案 | 禁止 | examples 全部标注示意 | ✅ |

## 3. 脚本职责（3 个）

| 脚本 | 职责 | 退出码 |
|------|------|--------|
| `build_skeleton.py` | Step 0 落骨架 + 稿件结构提取 + 口径模板（evidence_scale/severity_rubric/issue_taxonomy）+ 标志文件校验 | 恒 0 |
| `evidence_check.py` | 机械校验三组（定位回证/口径一致/登记一致）+ coverage/unchecked 计数回填 | 恒 0 |
| `schema_guard.py` | output_contract 全字段 + 业务 schema 结构守卫 | 恒 0 |

三者都遵守"退出码恒 0、判据看 verdict、失败也交付"；evidence_check 承担了原
verify_check + chain_audit 两个脚本的职责（回证 + 计数合并到一处，减少脚本间键归属耦合）。

## 4. 实测对照数字（2026-11-22 本机实跑，Python 3.13 / Windows 11）

### 4.1 全链路自检（合成案例）

| 检查 | 结果 |
|------|------|
| build_skeleton（案例 5 章节 2 引文 5 契约字段） | 骨架落盘，标志文件命中=True，exit 0 |
| evidence_check（ablate=none） | **PASS，54 条检查项全部 applied**，exit 0 |
| schema_guard | **PASS**，exit 0 |
| SKILL.md 行数 | **112 行**（≤150） |
| 包体积 | 约 115KB / 8 文件 |

### 4.2 污染副本反例自测（4 项注入：清空 quote / issue_type 非法 / C3配E1判supported / pending不登记）

| 校验 | 结果 |
|------|------|
| evidence_check verdict | **FAIL（7 处）**，exit 0 |
| 抓到的违规 | issue_type 非法、quote 无法回证、C3须E3 违规、overstated 无发现举证、pending 未登记、coverage 2 处不符 |

结论：校验器既能对干净输入 PASS（54 项全 applied），又能对污染输入 FAIL（7 处全抓），
FAIL 判据真实生效，非"恒 PASS"摆设。

## 5. 诚实边界（不冒充、不夸大）

1. 本技能是**单方向**（证据支撑核查），不宣称覆盖论证链/章节衔接/严重度建议，
   这是**明确的能力边界**，不是缺陷。
2. examples 是合成示意案例（文件头标注"非正式答案"），不预置三个正式案例的任何答案。
3. 引文回证是"逐字出现于稿件原文"的机械下界；主张抽取与强度定级靠语义判断，
   机械校验只保证回证、枚举与登记一致。
4. 增益层 available=false（预算过半跳过），**不编造**对照数字；平台白板对照由平台生成。
5. 三口径（证据标尺/严重度/问题类型）为本技能事前声明的设定，不冒充期刊官方标准。
6. pending 是题面要求的"无法确认标记待复核"，不是偷懒：必须写 reason + needed_action。

## 6. 剩余风险

1. 正式案例的稿件结构若与常见键（manuscript/sections）不同，build_skeleton 已做键名
   兼容 + 降级兜底，但 sections 提取失败时需 Agent 手工抄结构。
2. 若题面正式口径与本题默认五类/标尺有出入，Agent 需在 Step 1 按题面重声明
   （机制已支持：口径判定前声明即可，校验器不锁死具体文案）。
3. 只聚焦摘要+结果意味着引言承诺未交付、讨论反驳缺失等**跨章节问题不在本方向覆盖**，
   这是"选一个方向"的代价——已在 SKILL.md 已知限制明示。