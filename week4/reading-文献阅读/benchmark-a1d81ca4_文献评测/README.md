# benchkit — 文献阅读最小评测包（v2 增强版）

把 benchmark-DRAFT 工单建成可判分、可复跑、可溯源、可迭代的评测工具：
**判得动**（题卡字段齐备 + 0/1/2 判分线 + 判分口径机械可观察拦截）、
**跑得一致**（确定性技术检查 + score_suggest + check_sha 复跑比对）、
**查得回**（每个分数顺 item_id 追到原始输出与评分行）、
**改得动**（item 级快照 + diff 定向重算）、**说得清**（report.md 逐题报告）。

## 快速开始

```bash
# SK = 本仓库目录（含 SKILL.md）
python3 "$SK/scripts/benchkit.py" init      --case <case.json> --outdir /app/output
python3 "$SK/scripts/benchkit.py" diff      --outdir /app/output        # 改题后运行
python3 "$SK/scripts/benchkit.py" techcheck --outdir /app/output
python3 "$SK/scripts/benchkit.py" report    --outdir /app/output        # 评分后运行
python3 "$SK/scripts/benchkit.py" embed     --outdir /app/output
python3 "$SK/scripts/benchkit.py" verify    --outdir /app/output [--case <case.json>]
```

依赖：仅 Python 3.8+ 标准库，无第三方包、无网络。人工介入点只有两处：作答（第 3 步，
写入 run_results.json）与语义评分（第 4 步，写入 scores.csv）。

## 产物（七件 + diff，全量嵌入 result.json）

| 文件 | 内容 |
|-|-|
| items.json | 题卡：item_id / task / input_ref / conditioning / reference_answer / scoring_rule（0/1/2 判定线）/ difficulty / source_text_snapshot / extra |
| run_results.json | 统一运行原始输出：answer_raw 全文 + answer_struct + evidence（原文片段与定位）+ technical_check（含 score_suggest）+ run_config + stability.check_sha |
| scores.csv | 逐题 0/1/2 + rationale 判分依据 + disputed + failure_type |
| failure_samples.json | 失败样例库：8 类归因（no_answer/text_mismatch/missing_condition/overclaim/format_error/file_unreadable/permission_denied/disputed） |
| version.json | 快照：v1 起，item_shas 逐题哈希；改题后 diff 递增版本、标记 rescore_only 与 comparable |
| diff.json | 版本对比：changed/added/removed；只有 rescore_only 内题目需重算，comparable 题目历史分数仍可比 |
| report.md | 逐题报告（机械生成）：得分/判分依据/确定性建议分/条件/证据摘录/失败类型/改进建议 + 失败归因表 + 分歧裁定 |
| result.json | 平台契约输出：case_id / status（四级诚实）/ result（评测包全量嵌入，含 report_md 全文 / gates 闸门四态 / verify_checks 逐条校验三元组）/ claims / uncertainties |

result.json 的 `result` 字段完整嵌入题卡、原始输出全文、逐题分数、失败样例、版本快照、
**report.md 全文**、**gates 闸门状态**（enforced/skipped_not_provided/not_found/unreadable
四态枚举，非 enforced 必带 gate_note）与 **verify_checks 逐条机械校验三元组**
{item, template_value, applied, match}，不依赖外部文件即可复核。分数复算路径：
scores 行 → 题卡 conditioning/scoring_rule → run_results 原文输出全文。

## status 四级

`answered`（全部完成且 claims 非空）/ `partial`（部分完成，缺口写明）/
`insufficient_evidence`（材料不足以判断）/ `input_error`（输入损坏且无法修复）。

## 最小示意示例（示意数据，非正式案例、非正式答案）

以 `examples/example-case.json`（合成电池循环工单，4 条）演示一轮完整流程：

```bash
python3 "$SK/scripts/benchkit.py" init --case examples/example-case.json --outdir /tmp/bench
# → items=4, contract_keys=[case_id,status,result,claims,uncertainties], result.json 骨架已落盘
# 人工作答（示意）：run_results.json 中 b-1 的 answer_raw 填
#   "1C 下循环 200 次后放电容量保持率为 84.3%（条件：1C、200 cycles，可回溯 p02）"
# 人工评分（示意）：scores.csv 中 b-1 行 score=2，
#   rationale="主结论 84.3% 与参考答案逐字一致，条件 1C/200 cycles 完整体现，可回溯 p02"
python3 "$SK/scripts/benchkit.py" diff --outdir /tmp/bench
python3 "$SK/scripts/benchkit.py" techcheck --outdir /tmp/bench
# → techcheck：ran=4，b-1 数值/条件覆盖检查通过、score_suggest=2；check_sha 已记录供复跑比对
python3 "$SK/scripts/benchkit.py" report --outdir /tmp/bench
# → report.md：4 题逐题得分/判分依据/建议分/失败类型/改进建议 + 失败归因表 + 分歧裁定
python3 "$SK/scripts/benchkit.py" embed --outdir /tmp/bench
python3 "$SK/scripts/benchkit.py" verify --outdir /tmp/bench --case examples/example-case.json
# → verify PASS（items=4 ran=4 scored=4）
```

示意输出仅说明接口与流程；正式案例结果以平台实际运行为准。

## 异常与降级

所有命令全捕获：输入损坏、结构未知、缺字段时打印警告、写 warn.log、仍产出全套文件
（结构未知时合成兜底题卡），不抛裸异常、不产出空结果、退出码恒 0。verify 发现缺口
如实报 FAIL（含判分口径不可观察拦截），修复后重跑直到 PASS。常见处置见 SKILL.md
「异常处置」表。

## 复用与维护

- 题卡字段即题集规范；换领域只需替换 case.json 工单，脚本零改动。
- version.json 的 item_shas 支持任意题集演进的定向重算；diff.json 即版本对比报告；
  report.md 由命令机械再生成，不手写。
- 已知限制：技术检查与 score_suggest≠语义验证；来源为段落/表格文本而非 PDF 像素金标；
  跨 Agent 对照由平台白板负责。维护信息与历史决策见 worklog.md。


## 生态贡献：依赖、安装运行、目标用户与验收

| 项目 | 说明 |
|---|---|
| 依赖与版本 | Python 3（评测沙箱 3.12；本 Skill 脚本仅用标准库，无需 pip 安装）；所有命令用 `python3` 调用。 |
| 安装与运行 | 平台把提交目录装入 `/skills/weekly-skill`；输入 `/input/case.json`（+ 材料），产物写 `/app/output/result.json`。 |
| 输入 / 输出解释 | 输入=案例标识与来源材料；输出=result.json（契约全字段 + 逐条证据 + 闸门状态 + gain_evidence + efficiency + exceptions）。 |
| 目标用户与场景 | 需「产出可直接用、且每条结论都能回到原文核对」的作者与审阅者；用于成稿前的自检与交付留痕。 |
| 验收方式 | ①契约键一个不缺且 JSON 可解析；②每条论断带可回证的 evidence 与来源位置；③闸门状态显式、非 enforced 有 gate_note；④gain_evidence 含基线与当前两套指标及削减量。 |
| 常见问题 | 证据回证失败→换原文短引文而非改写；材料缺失→按题面要求登记缺口而非补零；机检不过→修一轮并如实登记结论。 |
| 已知限制 | 增益对照为同输入自比，量化的是核对工作量与漏检率，不等同于跨模型横向评测。 |
| 失败处理 | 任一步异常：写盘已有产出、status 如实降级、exceptions 记录失败点与已尝试回退链；机检结论照实记录且退出码恒 0。 |
| 复用建议 | 直接复用 scripts/；证据与闸门的字段结构可套用到同类「产出+核对」任务。 |
| 版本与维护 | 见 worklog.md 版本小节；结构变更时同步本表与 SKILL.md 输出字段说明。 |

## 最小可运行自检清单（复制即跑）

```bash
python3 -c "import sys;print(sys.version)"   # 1) 解释器可用
ls scripts/                                   # 2) 脚本在位
python3 scripts/gain_evidence.py --help       # 3) 增益脚本可执行
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"  # 4) 产物可解析且键齐全
```
