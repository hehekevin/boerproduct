# worklog — lit-classify（challenge-666fefb0 文献与资料自动分类）

记录日期：2026-11-19。本文件为真实开发记录，含实测对照数字与诚实边界。

## 1. 开发过程

1. **读题面与骨架**：读 `week4-dl/challenge-666fefb0/task.md`，确认赛道为科研资料管理
   （文献分类/标签生成/自动命名/去重/批量整理五个突破方向中锁定「文献分类 + 同键去重
   + 边界登记」最小闭环）；参照第 4 期已交付的 challenge-2dd1f64c 包结构。
2. **设计领域 schema**：taxonomy（事前声明多级体系）→ items[]（逐条 primary_path/tags/
   confidence/evidence_quote/boundary）→ consistency（key_signature 同键分组）→
   pending_review（未判定 + 边界条目）→ coverage/conflicts/steps/run_status/verdict。
3. **编写 5 个脚本**：build_skeleton（骨架+体系模板）、classify_engine（关键词机械归类
   建议 + 同键分组）、verify_check（四组机械校验）、schema_guard（结构守卫）、
   gain_probe（消融双跑 + 污染注入 + 效率计数）。
4. **合成示例**：8 条虚构资料，覆盖同 DOI 预印本、同题重复下载、跨主题边界、无文本层
   扫描件四类情形；example-result 与 example-case 配套且通过全部校验器。
5. **全链路实测**：见下节真实数字。

## 2. 实测对照数字（2026-11-19 实跑，Python 3.13，Windows）

### 2.1 干净输入（examples/example-case.json + example-result.json）

| 校验器 | 结果 |
|--------|------|
| build_skeleton | 提取 contract 字段 6 个、文献条目 8 条，骨架落盘成功 |
| classify_engine | 体系 9 节点（3 维）；8 条全部产出建议与 key_signature；同键组 6 组（其中 2 组多成员：doi:10.1000/demo-001 → F01/F02、title:hippocampal…@2019 → F03/F08） |
| verify_check | **PASS**（ablate=none，检查项 31 条全部 applied，problems=0） |
| schema_guard | **PASS**（结构完整，case_id=demo-litclassify-001） |

gain_probe 干净输入双跑（同输入、同文件内容深拷贝）：

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| taxonomy_missed | 0 | 0 | 0 |
| evidence_missed | 0 | 0 | 0 |
| consistency_missed | 0 | 0 | 0 |
| pending_missed | 0 | 0 | 0 |
| manual_review_items | 1 | 1 | 0 |
| steps_count | 37 | 6 | **+31** |
| clarification_rounds | 1 | 1 | 0 |

干净输入四类漏检均为 0：说明示例本身无违规；机制价值体现在 steps_count 差（normal
执行 31 项检查 vs degraded 0 项）与下节污染对照。

### 2.2 污染反例副本（--inject-pollution，注入 5 项，原 result.json 未被改动）

注入内容：F01 清空 evidence_quote 并改体系外路径 T-FAKE-99；F02（与 F01 同键）改判
T-OTHER-01（同类不同判）；清空 pending_review；清空 conflicts；清空 claims。

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| verdict | **FAIL**（13 处问题） | **PASS**（0 处） | −13 |
| taxonomy_missed | 0 | 2 | **+2** |
| evidence_missed | 0 | 7 | **+7** |
| consistency_missed | 0 | 1 | **+1** |
| pending_missed | 0 | 2 | **+2** |
| 四类漏检合计 | 0 | 12 | **+12** |

`caught_by_normal_mode=true`：同一校验器、同一污染输入，正常模式把 13 处问题全部报出
（漏检 0），退化模式 12 处客观违规全部漏掉且 verdict 从 FAIL 翻成 PASS。客观违规真值由
gain_probe 独立复算（与 verify_check 分开实现），口径一致。

### 2.3 效率计数（gain_probe 自动采集）

- 两次 analyze 墙钟合计 ≈ 0.011 秒（本机参考值，受负载影响）。
- checker_runs=2；normal 已执行检查项 31 / degraded 0；条目总数 8。
- model_requests 保持 null（脚本不可采集，由 Agent 侧按实际回填）。

## 3. 开发中发现并修复的问题

1. **关键词空格陷阱**：初版 classify_engine 直接用 `kw.lower() in text.lower()` 比较，
   带空格的英文词组（deep learning / sea surface temperature）在文本归一化后永不命中，
   导致 F01 只命中 1 处。修复为两侧都先 `norm()`（去空白）再比较。
2. **duplicate 边界误报**：初版把 boundary=duplicate（已 merged 处置）也强制登记
   pending_review，与「确定性动作无需人工复核」矛盾，F02/F08 误报。修复为仅
   multi_domain/ambiguous/missing_fields/unreadable 四类强制登记。
3. **isalpha 汉字陷阱**：全包不做 `isalpha` 字符类别判断（中文子串原样匹配），
   key_signature 归一化用 `[^\w\u4e00-\u9fff]` 白名单替换，中文标题键稳定。

## 4. 诚实边界

- 增益对照是**本校验层**正常 vs 退化两模式对照，不是平台"基础 Agent vs 参赛 Skill"的
  白板对照；平台对照由平台生成，本包不代替、不冒充。
- 干净输入下四类漏检 delta=0：说明机制在本示例上无漏检区分度（输入本身干净），
  机制价值由污染对照与 steps_count 差体现；换个脏输入漏检差会不同。
- mechanical 建议与 Agent 最终判定允许不一致；示例中两者一致是构造结果，
  实际运行中 Agent 须对低分差建议登记边界而非盲从。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；wall_clock 受机器负载影响，
  仅作同次对照参考。
- examples 全部为合成案例（标题/摘要/DOI 虚构）并标注"示意"，非正式答案；
  平台 3 个固定案例未接触、不预置答案。

## 5. 硬约束自检清单

| 约束 | 结果 |
|------|------|
| SKILL.md ≤150 行 | 143 行（wc -l 实测） |
| 脚本 ≤8 | 5 个 |
| 包 <2MB、≤50 文件 | 9 个文本文件，约 90 KB（实测见下） |
| 零外部依赖 | 仅标准库（json/os/re/sys/argparse/copy/time/math） |
| 命令一律 python3 | 是 |
| 挂载 /skills/weekly-skill；输入 /input/case.json + task.md；产出 /app/output/result.json | 是（SKILL.md 与全部脚本默认参数一致） |
| 所有失败路径 exit 0 | 实测：result.json 不存在时 verify_check/schema_guard/classify_engine/gain_probe 均 exit 0 |
| 不预置正式答案 | examples 标注示意、虚构 |
| 多脚本禁写同一键 | verify_check 只写 self_check/gates/unbacked_numbers/validator_verdict；gain_probe 只写 result.gain_evidence/efficiency；classify_engine 只写 result.consistency/items[].mechanical |
