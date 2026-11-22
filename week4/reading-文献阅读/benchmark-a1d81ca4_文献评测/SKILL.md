---
name: benchkit
description: 文献阅读 Benchmark 与评测工具技能：把 benchmark-DRAFT 工单（source-conditioned 条目，来源为段落/表格文本）建成可判分、可复跑、可溯源、可迭代的最小评测包——题卡、统一运行原始输出、0/1/2 逐题评分（每行判分依据）、失败样例库、item 级版本快照与定向重算。评测包全量嵌入 result.json，每个分数顺 item_id 可追到原始输出与评分行。技术合成检查日志不是 DSH 分数也不是独立语义验证。Use when asked to build/run/score/version/audit a literature-reading benchmark, 题集, 评测工具, 评分表, 失败分析, benchmark workorder.
---

## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 6 条是硬性纪律，优先级高于本文档其余内容；冲突时以本节为准。

1. 第 1 步先抄契约：读完 /input/case.json 与题面后，把 output_contract 的**每个键名**
   原样抄成清单（在任意层级出现即算，含嵌套；contract 为键名列表时逐个抄），并抄下
   case_id。键一个不漏，抄完再动手。
2. 第 2 步立即落骨架：第一个写盘动作就是在 /app/output/result.json 写入骨架——
   包含契约全部键 + case_id/status/result/claims/uncertainties；无法完成的字段填
   unknown 或空数组，绝不省略键；status 填 partial。此后任何时刻 result.json 必须存在
   且 JSON 可解析。
3. 字段一个不缺：最终 result.json 必须包含契约全部键。某项确实无法产出时保留键并填
   unknown/空数组，把原因写进 uncertainties，不得删键、不得编造数据。
4. 广度优先：先让全部产物以最小合格版本存在，再对高价值部分加深；禁止在单一产物上
   耗尽预算。
5. 预算熔断：模型请求已用超过 48 次或运行超过 700 秒时（平台预算 64 请求/900 秒），
   立即停止新增处理，用现有中间结果完成 result.json 并收尾。每次写 result.json 都
   覆盖为当前最新完整状态。
6. 失败也要交付：处理中断或失败时仍写 result.json（status 用题面约定的失败值，写明
   中断位置与已完成部分），绝不让 /app/output 缺少 result.json。

最终写盘前自检：JSON 可解析、契约键一个不缺、case_id 与输入一致、status 如实、
每个关键论断有 claims 证据。自检不过先修复再交付。

## 目标与边界

把 /input/case.json 的 benchmark-DRAFT 工单建成**最小评测包**，六件全部落盘且全量
嵌入 result.json：

```
items.json（题卡）→ run_results.json（原始输出+技术检查）→ scores.csv（0/1/2+判分依据）
→ failure_samples.json（失败样例）→ version.json（item 级快照）→ diff.json（版本对比）
→ result.json（全量嵌入 + claims + uncertainties）
```

六方面覆盖：任务定义=题卡 task/scoring_rule；数据与答案管理=source_text_snapshot+
reference_answer+version 快照；评分维度=0/1/2 判分线+scores；原始输出留存=run_results
全文嵌入；误差分析=failure_samples 归因到题型；版本迭代=diff 定向重算+可比性标记。

诚实边界（必须如实声明，不得越过）：
- 工单条目是 source-conditioned；来源是段落/表格文本，不是 PDF 像素金标。
- 技术合成检查日志不是 DSH 分数也不是独立语义验证；只做确定性校验（数值逐字覆盖、
  条件词覆盖），语义正确性只由 0/1/2 评分规则判定，两者分开记录。
- 无参考答案的题如实标『仅规则评分』；不编造分数或数据，推断不当事实。

## 调用脚本

脚本位于本 SKILL.md 同目录的 `scripts/benchkit.py`（记为 `$SK/scripts/benchkit.py`，
$SK 为本文件所在目录；找不到时用 `find / -name benchkit.py -path '*scripts*' 2>/dev/null | head -1` 定位）。
任何一步脚本缺失或报错：按本文档 schema 手写等价 JSON 继续，流程不中断，并把降级写入
uncertainties.summary。

## 五步流程

### 第 1 步 抄契约（工单条目全清单）
读 /input/case.json 与题面。按协议第 1 条抄下 output_contract 全键与 case_id。
把工单条目（revision2 为四条）逐条抄成清单，一条不漏：task、input_ref、conditioning、
source_text、reference_answer、scoring_rule、difficulty。conditioning 逐条保留——
出题条件丢了的题不算 source-conditioned。数值逐字照抄，不改写、不换算。
同时列出 /input/ 下全部材料文件名（脚本会记入 materials）。

### 第 2 步 落骨架（每 item 一条待评记录）
```bash
python "$SK/scripts/benchkit.py" init --case /input/case.json --outdir /app/output
```
一次性落六件最小版本：items.json（每 item 一张八字段题卡：item_id/task/input_ref/
conditioning/reference_answer/scoring_rule/difficulty/source_text_snapshot）、
run_results.json（每 item 一条空记录）、scores.csv（表头+每 item 一行）、
failure_samples.json、version.json（v1 + item 级 sha 快照）、result.json 骨架
（契约全键，status=partial）。case.json 损坏或结构未知时脚本自动降级仍产出全套文件
并写兜底题卡；此时人工核对题卡内容后再继续。

### 第 3 步 题卡定稿 + 统一作答
逐题定稿：task 可判定（输出与评分规则一一对应）；reference_answer 与
source_text_snapshot 逐字一致；无参考答案填『仅规则评分』；scoring_rule 明确到能写出
0/1/2 判定线；difficulty 如实。
逐题作答：读 source_text_snapshot 原文真实推导答案，**不得凭领域标签编造**。把答案写
入 run_results.json 对应条目：answer_raw（答案全文）、answer_struct（结构化要点）、
evidence（每条 {quote: 原文片段, location: 段落/表格定位}）。改过题卡的题运行：
```bash
python "$SK/scripts/benchkit.py" diff --outdir /app/output
python "$SK/scripts/benchkit.py" techcheck --outdir /app/output
```
diff 递增快照并标记 rescore_only（只需重算的题目）与 comparable（历史分数仍可比的
题目）；techcheck 做确定性检查并记录 check_sha 供复跑一致性比对。

### 第 4 步 评分与失败归因
按 0/1/2 判分线逐题评分写 scores.csv，每行必带 rationale；score=2 必有判分依据
（引参考答案/评分规则 + 原文定位）；只需重算 diff 标出的 rescore_only 题目。
disputed=true 标存疑。典型失败写 failure_samples.json：
`{item_id, answer_raw_excerpt, failure_type, why}`，failure_type 归到题型
（no_answer/text_mismatch/missing_condition/overclaim/format_error/file_unreadable/
permission_denied），作为下一版专项题来源。

### 第 5 步 嵌入 + 自检收尾（先修复再交付）
```bash
python "$SK/scripts/benchkit.py" embed --outdir /app/output
python "$SK/scripts/benchkit.py" verify --outdir /app/output --case /input/case.json
```
embed 把题卡全量、run_results 全文、逐题分数（含 answer_raw_excerpt）、失败样例、
版本快照、materials、summary 机械嵌入 result.json 的 result 字段。verify 校验：题卡
字段齐、scores 与 items 无漏分多分、score∈{0,1,2} 且每行有 rationale、每 item 有原始
输出（空输出须有失败样例）、item_shas 一致、result 契约键齐、claims 结构齐。FAIL 时
逐条修复后重跑直到 PASS。
最后手工补 claims 与 uncertainties（embed 不覆盖已有内容）：
- claims 每条：`{"claim_id":"c-1","text":"评测结论","kind":"reported|inferred",
  "source_id":"<item_id 或材料文件名>","location":"scores.csv 行 N / run_results.results[M]",
  "evidence":[{"quote":"原文片段","location":"段落/表格定位"}]}`。关键结论（哪类题弱、
  哪个分数可疑）必须有 claim；不编造分数。
- uncertainties：unreported（无参考答案题）/unverifiable（需人工复核语义分）/conflicts
  （材料冲突）/human_review（disputed 项）/summary（缺口与降级记录）。

## result.json schema（键以 case.json/task.md 的 output_contract 为准，一个不缺）

```json
{
  "case_id": "取自 case.json",
  "status": "answered | partial | insufficient_evidence | input_error",
  "result": {
    "items": [{"item_id":"","task":"","input_ref":"","conditioning":[],
               "reference_answer":"原值或 仅规则评分","scoring_rule":"","difficulty":"",
               "source_text_snapshot":"","extra":{}}],
    "run_results": [{"item_id":"","answer_raw":"","answer_struct":{},
                     "evidence":[{"quote":"","location":""}],"technical_check":{}}],
    "scores": [{"item_id":"","score":0,"rationale":"","disputed":false,
                "failure_type":"","answer_raw_excerpt":""}],
    "failures": [{"item_id":"","answer_raw_excerpt":"","failure_type":"","why":""}],
    "version": {"snapshot":"v1","items_sha":"","item_shas":{},"changes":[],"comparable_with":[]},
    "materials": [{"file":"","bytes":0}],
    "diff": {"changed":[],"added":[],"removed":[],"rescore_only":[],"comparable":[]},
    "summary": {"items_total":0,"items_with_reference":0,"items_rule_only":0,
                "score_dist":{"0":0,"1":0,"2":0},"avg":null,
                "note":"技术合成检查日志不是 DSH 分数也不是独立语义验证"}
  },
  "claims": [{"claim_id":"","text":"","kind":"reported|inferred","source_id":"",
              "location":"","evidence":[{"quote":"","location":""}]}],
  "uncertainties": {"unreported":[],"unverifiable":[],"conflicts":[],"human_review":[],"summary":""}
}
```
契约多出的键照抄生成并填 unknown 或空数组。

## 0/1/2 判分线

- 2 = 正确且条件完整：主结论与参考答案/评分规则一致，conditioning 条件全部体现，
  关键结论可回溯 source_text 定位。rationale 必须写明判分依据。
- 1 = 部分正确：主结论方向对，但缺条件、缺定位或缺边界说明。rationale 写明缺什么。
- 0 = 错误或未回答：与来源矛盾、编造未报告数据、把推断当事实、或空答。

## 异常处置

| 情形 | 处置 |
|-|-|
| 题目缺参考答案 | reference_answer 填『仅规则评分』，按 scoring_rule 判分，写入 uncertainties.human_review |
| 输出为空 | score=0，failure_type=no_answer 并留失败样例，评分行不删 |
| 输出超长 | run_results.json 存全文；result 嵌入 answer_raw_excerpt（首 300 字+尾 100 字），不丢分 |
| JSON 格式不合规 | 修复到可解析；修不好则 status=input_error 并写明问题字段，保留全部已产出键 |
| 文件损坏/读失败 | 跳过该项记 failure_type=file_unreadable，其余照常，绝不中断交付 |
| 权限不足 | status=partial，原因写入 uncertainties.unreported，不编造替代数据 |
| case.json 结构未知 | 脚本写兜底题卡；人工核对后继续，降级记录写入 uncertainties.summary |
| 预算触顶 | 按协议第 5 条：停止新增，用现有中间结果完成 result.json 收尾 |

## 最小调用示例（示意，非正式案例、非正式答案）

examples/example-case.json 为合成四条工单（电池循环数据，仅示意接口，不冒充正式结果）：
```bash
python "$SK/scripts/benchkit.py" init --case examples/example-case.json --outdir /tmp/bench
# 第 3-4 步：定稿题卡、作答写入 run_results.json、逐题评分写 scores.csv（示意见 README.md）
python "$SK/scripts/benchkit.py" diff --outdir /tmp/bench
python "$SK/scripts/benchkit.py" techcheck --outdir /tmp/bench
python "$SK/scripts/benchkit.py" embed --outdir /tmp/bench
python "$SK/scripts/benchkit.py" verify --outdir /tmp/bench --case examples/example-case.json
```
产出六件 + diff.json + result.json。脚本任何一步失败自动写 warn.log 降级，按 schema
手写 JSON 继续，流程不中断。

## 已知限制

- 技术合成检查日志不是 DSH 分数也不是独立语义验证；语义 0/1/2 依赖评分规则质量，
  存疑标 disputed 交人工复核。
- 来源是段落/表格文本，不是 PDF 像素金标；不含 PDF 解析与像素级金标比对。
- 单评测对象、单轮流程；重复运行稳定性以 check_sha 记录差异，跨 Agent 对照由平台
  固定白板负责，本包保证同输入同流程可复跑、分数可溯源。
- 不改写来源数据；Public16scoring 与原始科学来源字节保持不变。
