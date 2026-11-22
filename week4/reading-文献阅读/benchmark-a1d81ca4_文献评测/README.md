# benchkit — 文献阅读最小评测包（v3）

把 benchmark-DRAFT 工单建成可判分、可复跑、可溯源、可迭代的评测工具：
**判得动**（题卡字段齐备 + 0/1/2 判分线）、**跑得一致**（确定性技术检查 + check_sha 复跑比对）、
**查得回**（每个分数顺 item_id 追到原始输出与评分行）、**改得动**（item 级快照 + diff 定向重算）。

## 快速开始

```bash
# SK = 本仓库目录（含 SKILL.md）
python "$SK/scripts/benchkit.py" init     --case <case.json> --outdir /app/output
python "$SK/scripts/benchkit.py" diff     --outdir /app/output        # 改题后运行
python "$SK/scripts/benchkit.py" techcheck --outdir /app/output
python "$SK/scripts/benchkit.py" embed    --outdir /app/output
python "$SK/scripts/benchkit.py" verify   --outdir /app/output [--case <case.json>]
```

依赖：仅 Python 3.8+ 标准库，无第三方包、无网络。人工介入点只有两处：作答（第 3 步，
写入 run_results.json）与语义评分（第 4 步，写入 scores.csv）。

## 产物（六件 + diff，全量嵌入 result.json）

| 文件 | 内容 |
|-|-|
| items.json | 题卡：item_id / task / input_ref / conditioning / reference_answer / scoring_rule / difficulty / source_text_snapshot / extra |
| run_results.json | 统一运行原始输出：answer_raw 全文 + answer_struct + evidence（原文片段与定位）+ technical_check + run_config + stability.check_sha |
| scores.csv | 逐题 0/1/2 + rationale 判分依据 + disputed + failure_type |
| failure_samples.json | 失败样例库：归因到题型（no_answer/text_mismatch/missing_condition/overclaim/format_error/file_unreadable/permission_denied） |
| version.json | 快照：v1 起，item_shas 逐题哈希；改题后 diff 递增版本、标记 rescore_only 与 comparable |
| diff.json | 版本对比：changed/added/removed；只有 rescore_only 内题目需重算，comparable 题目历史分数仍可比 |
| result.json | 平台契约输出：case_id / status（四级诚实）/ result（评测包全量嵌入）/ claims / uncertainties |

result.json 的 `result` 字段完整嵌入题卡、原始输出全文、逐题分数、失败样例、版本快照、
材料清单与汇总，不依赖外部文件即可复核。

## status 四级

`answered`（全部完成且 claims 非空）/ `partial`（部分完成，缺口写明）/
`insufficient_evidence`（材料不足以判断）/ `input_error`（输入损坏且无法修复）。

## 最小示意示例（示意数据，非正式案例、非正式答案）

以 `examples/example-case.json`（合成电池循环工单，4 条）演示一轮完整流程：

```bash
python "$SK/scripts/benchkit.py" init --case examples/example-case.json --outdir /tmp/bench
# → items=4, contract_keys=[case_id,status,result,claims,uncertainties], result.json 骨架已落盘
# 人工作答（示意）：run_results.json 中 b-1 的 answer_raw 填
#   "1C 下循环 200 次后放电容量保持率为 84.3%（条件：1C、200 cycles，可回溯 p02）"
# 人工评分（示意）：scores.csv 中 b-1 行 score=2，
#   rationale="主结论 84.3% 与参考答案逐字一致，条件 1C/200 cycles 完整体现，可回溯 p02"
python "$SK/scripts/benchkit.py" diff --outdir /tmp/bench
python "$SK/scripts/benchkit.py" techcheck --outdir /tmp/bench
# → techcheck：ran=4，b-1 数值/条件覆盖检查通过；check_sha 已记录供复跑比对
python "$SK/scripts/benchkit.py" embed --outdir /tmp/bench
python "$SK/scripts/benchkit.py" verify --outdir /tmp/bench --case examples/example-case.json
# → verify PASS（items=4 ran=4 scored=4）
```

示意输出仅说明接口与流程；正式案例结果以平台实际运行为准。

## 异常与降级

所有命令全捕获：输入损坏、结构未知、缺字段时打印警告、写 warn.log、仍产出全套文件
（结构未知时合成兜底题卡），不抛裸异常、不产出空结果。常见处置见 SKILL.md「异常处置」表。

## 复用与维护

- 题卡字段即题集规范；换领域只需替换 case.json 工单，脚本零改动。
- version.json 的 item_shas 支持任意题集演进的定向重算；diff.json 即版本对比报告。
- 已知限制：技术检查≠语义验证；来源为段落/表格文本而非 PDF 像素金标；跨 Agent 对照
  由平台白板负责。维护信息与历史决策见 worklog.md。
