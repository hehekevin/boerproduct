# worklog.md — argchain-review 开发记录（challenge-16d4414d）

日期：2026-11-19 ｜ 作者：w7-review4 ｜ 状态：v1 保底版 + 增益层完成

## 1. 开发时间线

1. 读题面 `task.md`：锁定"论证链追踪 + 六类问题 + 强度匹配 + 反驳覆盖"四个机检点
   （论证链节点完备、问题类型分类口径一致、位置可回证、强度匹配判定登记）。
2. 参考第 4 期已交付同类包 `challenge-0999879e`（六分面审查）的骨架与脚本架构，
   保留已验证的工程纪律（退出码恒 0 / 键归属分区 / 闸门四态 / 三元组自检），
   业务层整体重写为本题专有 schema。
3. 领域 schema 设计（与 0999879e 的关键差异）：
   - 新增 `argument_chains[]`：节点角色 hypothesis/premise/reasoning/conclusion，
     逐节点 quote+location，`chain_audit.py` 机械审计节点完备。
   - 新增 `issue_taxonomy`：六类逻辑问题口径判定前声明，findings 带 issue_type，
     校验器做枚举 + 严重度映射 + issue_type×facet 交叉三重口径检查。
   - 新增 `strength_scale`（证据 E3-E0 / 主张 C3-C1 双侧标尺）+ `strength_matches[]`
     逐条判定登记，机械规则 C3须E3。
   - facets 从"六分面通用审查"改为本题四分面（argument_chain / strength_match /
     rebuttal_coverage / cross_section）+ fact_check / integrity_norms。
4. 脚本 5 个（≤8 上限）：build_skeleton / chain_audit / verify_check / gain_probe /
   schema_guard，全部标准库、退出码恒 0。
5. examples 合成案例专门埋设四类考点：断链（F04/F07/F11）、循环论证（F05）、
   因果相关混淆（F01）、外推超界（F02）、强度不匹配（F06/F08/F12）、反驳缺失
   （F03）；并埋设三个误报抑制正例（对照组式假设 F10、转述他人观点 F09、
   作者自陈局限）。**不预置正式答案，文件头标注示意。**

## 2. 开发中发现并修复的问题（真实过程记录）

1. **pending 检查不可达缺陷**：初版 verify_check 把 pending/suppressed 登记检查
   放在 `if status != "confirmed": continue` 的循环内，pending/suppressed 永远
   查不到。重构为同一循环内按 status 分支。
2. **零分面检查与 clearances 口径不一致**：verify_check 判"零发现分面"时未考虑
   clearances 豁免，示例的 integrity_norms 豁免被误报 FAIL；与 chain_audit 对齐
   （clearance 命中则豁免）。
3. **双向交叉规则过严误伤**：曾实现"facet=strength_match ⇔ issue_type 必为
   strength_mismatch"双向规则，会把合法组合（F01 correlation_causation + 
   strength_match 分面）误判违规；回退为单向（strength_mismatch ⇒ 强度分面）。
4. **污染注入的可检性设计**：issue_type"合法值漂移"（strength_mismatch→broken_chain）
   机械层无法区分语义，注入无对照意义；非法枚举篡改由始终开启的基础层两模式都
   抓到（delta=0 属实）；消融组内的 taxonomy delta 改由 severity 抬升污染承载
   （suggestion⇒major，退化模式漏检）。
5. **漏检计数口径对齐**：claims 缺失计入 pending 真值但未计入捕获数，导致正常
   模式显示 pending_missed=10（假漏检）；把 claim_backed 捕获计入 pend_c，并对
   真值列表去重（同一 fid 的 reason 空 + 未登记只计一次）。

## 3. 实测对照数字（2026-11-19 本机实跑，Python 3.13 / Windows 11）

### 3.1 全链路自检（合成案例）

| 检查 | 结果 |
|------|------|
| build_skeleton（案例 5 章节 3 引文 6 契约字段） | 骨架落盘，标志文件命中=True，exit 0 |
| chain_audit | 12 findings（9/1/2），2 链 7 节点完备，5/5 章节有发现，unchecked=0，exit 0 |
| verify_check（ablate=none） | **PASS，71 条检查项全部 applied**，exit 0 |
| schema_guard | **PASS**（业务 22 键 + findings 16 子字段 + 链/强度子 schema），exit 0 |
| gain_probe（含 --inject-pollution --emit-into） | exit 0，证据落盘 |
| SKILL.md 行数 | **142 行**（≤150） |
| 包体积 | 约 118 KB / 10 文件（<2MB、≤50 文件） |

### 3.2 干净输入双跑（无假阳性验证）

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| verdict | PASS | PASS | 0 |
| location/taxonomy/strength/chain/pending 漏检 | 全 0 | 全 0 | 0 |
| manual_review_items | 0 | 0 | 0 |
| steps_count | 78 | 7 | +71 |

### 3.3 污染副本双跑（9 项领域化注入：清空引文定位 / 非法枚举篡改 / 清空对照依据 /
清空 pending_reason / 删链 conclusion 节点 / 清空 strength_matches / suggestion
severity 抬升 major / 清空 pending_review / 清空 claims）

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| verdict（problems 数） | FAIL（21） | FAIL（3） | −18 |
| location_missed | 0 | 1 | +1 |
| taxonomy_missed | 0 | 1 | +1 |
| strength_missed | 0 | 1 | +1 |
| chain_missed | 0 | 1 | +1 |
| pending_missed | 0 | 10 | +10 |
| caught_by_normal_mode | **true** | — | — |

结论：同一校验器、同一污染输入，正常模式五类漏检全 0，退化模式 14 处客观违规
漏掉、verdict 由 21 处 FAIL 退到 3 处 FAIL——五组机制各自的增益被逐一实测。
（注入的非法枚举项由基础层两模式都抓到，不参与消融 delta，已在 README 注明。）

## 4. 诚实边界（不冒充、不夸大）

1. 增益对照是**本校验层**正常 vs 退化两模式，**不等于**平台"基础 Agent vs 
   参赛 Skill"白板对照；平台对照由平台生成。
2. examples 是合成示意案例（文件头标注"非正式答案"），用于自测链路与说明接口，
   不预置三个正式案例的任何答案。
3. 引文回证是"逐字出现于稿件原文"的机械下界；论证链抽取靠语义判断，机械审计
   只保证节点完备与引文可回证，语义断链由发现条目承载。
4. 三口径（severity/issue_taxonomy/strength_scale）为本技能事前声明的设定，
   题面未给定时按量级保守设定并写明，不冒充期刊官方标准。
5. 追问轮次按每轮 3 条折算，非实测交互次数；efficiency.model_requests 由 Agent
   侧回填，脚本不可采集，缺失保持 null。
6. 对照实验的输入是合成案例；正式三案例上的漏检/增益分布要等平台实跑，本包
   不预填任何正式案例数字。
7. 交叉校验为单向（issue_type=strength_mismatch ⇒ facet 落强度分面）；合法枚举
   内的语义漂移（如 broken_chain 改填 circular_reasoning）机械层不可区分，
   属诚实能力边界，依赖口径映射与人工复核兜底。

## 5. 剩余风险

1. 正式案例的稿件结构可能与常见键（manuscript/sections）不同——build_skeleton
   已做键名兼容与降级兜底，但 sections 提取失败时需 Agent 手工抄结构。
2. 若题面正式口径与本题默认六类/标尺有出入，Agent 需在 Step 1 按题面重声明
   （机制上已支持：口径判定前声明即可，校验器不锁死具体文案）。
3. 双侧标尺的 E/C 定级在边界情形（如大样本横断+纵向子研究）依赖 Agent 判断，
   机械校验只拦 C3配E2以下判 supported 这类明确违规。
