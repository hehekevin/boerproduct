# worklog — multi-db-merge（challenge-5c918ff0）开发记录

日期：2026-11-19　作者：w5-search5　骨架参照：第 3 周冠军包（challenge-da62e8d4，机制照搬、领域逻辑全新）

## 1. 本周领域与锁定子场景

题面：多数据库联合检索（3 固定案例，本地化 Crossref/EuropePMC/publisher 响应）。
基础 Agent 病灶：同一条查询机械复制到所有库、响应直接拼接、重复无法归并、
字段冲突被静默吞掉、覆盖盲区说不清。

锁定子场景（题面六方向收敛）：**库选择 → 检索式适配 → 合并去重 → 冲突登记 → 覆盖矩阵**，
机检四件套：检索式合规（adapted≠original）、去重复算一致、冲突发现数、来源可追溯率。

## 2. 从第 3 周骨架继承的机制（照搬）

| 机制 | 继承方式 |
|------|---------|
| Step 0 落骨架 + 三级容错 | build_skeleton.py 结构同构，材料扫描改为**内容签名命中**（FIELD_ALIASES + 库签名） |
| 事前容差声明 | 同构为 `dedup_policy`（阈值/容差/优先级 + basis + declared_at，匹配前写定） |
| 退出码恒 0 + verdict 判据 | 全部 5 个脚本保持 |
| 三元组自检 + 闸门四态 + unbacked 回证 | verify_check 保持，数值位换成计数/相似度/年份 |
| gain_probe 双模式对照 + 污染反例 | 保持，退化模式改为"关归一/关模糊/关冲突检测" |
| 脚本写键分工 | 固化进 SKILL.md：4 个写者各写各键，无交集 |

## 3. 领域引擎设计（dedup_core.py，全新）

- 归一：DOI 去前缀转小写；标题分词 `[a-z0-9]+|[\u4e00-\u9fff]`（**防 isalpha 汉字陷阱**：
  汉字 isalpha=True 会整句连词，引擎自含回归自测 `dedup_core.py` 无参数运行即验证）；
  作者词元化（丢单字母缩写噪音、保留 CJK 单字）；年份 `(19|20)\d{2}` 截取。
- 去重：并查集；DOI 精确匹配 + 标题 Jaccard≥事前阈值 且年份差≤容差 且作者词元有交集。
- 合并：字段按 field_priority 逐字段取首个非空来源；冲突检测比较归一值。
- 覆盖矩阵：库 × 5 字段 covered/missing（按归一后非空计）。

## 4. 实测对照数字（全部真实运行，机器 3.13.14 / Windows）

### 4.1 同一校验器双跑 FAIL 差（verify_check，同一份正确交付 example-result.json）

| ablate | verdict | partition_agree | checks_disabled | 退出码 |
|--------|---------|-----------------|-----------------|--------|
| none（交付自检口径） | **PASS** | 5/5 | 0 | 0 |
| normalize（关归一） | FAIL | 3/5 | 0 | 0 |
| fuzzy（关模糊匹配） | FAIL | 4/5 | 0 | 0 |
| conflict（关冲突检测） | PASS | 5/5 | 1 | 0 |
| all（全关） | FAIL | 3/5 | 8 | 0 |

读法：关闭归一 → DOI 前缀/大小写陷阱发作，R001/R002 两条跨库合并被退化引擎拆开（误报）；
关闭模糊匹配 → 无共享 DOI 的 CJK 标题重复对 R002 被拆。每条误报都需人工复核——
这就是归一 + 模糊匹配机制的量化价值。conflict 消融只影响冲突检查（跳过 1 项）。

### 4.2 apply 级消融（dedup_core --apply，同 8 条 raw_hits）

| ablate | merged | duplicates_merged | conflicts_detected |
|--------|--------|-------------------|--------------------|
| none | 5 | 3 | 5 |
| normalize | 7 | 1 | 1 |
| fuzzy | 6 | 2 | 2 |
| conflict | 5 | 3 | 0 |
| all | 7 | 1 | 0 |

### 4.3 gain_probe 五项指标（normal vs degraded，同输入两遍实跑）

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| machine_adjudicated_ratio | 100% | 0% | +1.0 |
| engine_agreement_ratio | 1.0 | 0.6 | +0.4 |
| dup_missed | 0 | 0 | 0 |
| conflict_missed | 0 | 0 | 0 |
| manual_review_items | 0 | 12 | −12 |
| steps_count | 71 | 62 | +9 |
| clarification_rounds | 0 | 4 | −4 |

污染反例自测（副本注入 6 类污染：静默拆分/删冲突/断来源链/计数+5/清空 claims/静默失败）：
normal 抓到 10 处 problems（caught_by_normal_mode=true）；degraded 漏掉冲突登记检查
（conflict_missed=1）。dup_missed 在干净交付上无区分度（客观真值=0），其区分度体现在污染
副本的"静默拆分被抓"上，已在 mechanism_map 注明。

## 5. 诚实边界

- 3 个模拟库 + 8 条合成响应：数字是机制对照证据，**不是**平台基础 Agent 对照；
  平台白板对照由平台生成。
- dup_missed/conflict_missed 在干净输入上恒 0：真值由探针用正常引擎独立复算，
  与被测模式无关；这两个指标的区分度靠污染反例体现。
- machine_adjudicated_ratio 的分母只含 dedup_metrics 计数(4) + title_fuzzy 相似度(1)
  + 合并记录年份(5)；doi_exact 相似度恒 1 不计入。
- 追问轮次=ceil(人工条目/3) 是折算估计量；model_requests 保持 null 待 Agent 回填。
- 真实案例的 case.json 结构未知：build_skeleton 用签名扫描自适应，但字段别名表
  可能需要现场补充（已在 SKILL.md Step 0 留手工兜底路径）。

## 6. 版本记录

| 版本 | 增量 |
|------|------|
| v1 | 初版：5 脚本 + 2 示例 + SKILL.md 135 行 + README 生态十项；全链路自测 PASS（见第 4 节） |

## 7. 遗留风险与待办

- 正式案例若含 PDF/非 JSON 材料：签名扫描目前只覆盖 JSON（题面资源含 pdf-text-tool，
  Agent 需先抽取文本再手工填 raw_hits，SKILL.md 已留兜底）。
- 字段别名表 FIELD_ALIASES 若不覆盖案例实际键名，需现场扩充（改一处常量即可）。
- GITHUB_URL.txt 待主控统一提交时放置（本次不提交）。
