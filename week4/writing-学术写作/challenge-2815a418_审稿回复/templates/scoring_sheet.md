# 返修交付自评表（Scoring Sheet）— 可复用

供作者/审阅人在交付前自查，或供他人复用本工作流时做质量对照。每项给出**可观察的判定条件**，
判定只依据交付物本身，不依据自述。

## A. 答得全（覆盖度）

| # | 判定条件 | 通过 | 未通过的表现 |
|---|---|---|---|
| A1 | 每条意见都有对应段落 | 意见数 = 回复信中意见段数 | 有意见只在致谢段被笼统带过 |
| A2 | 一条意见内的多个子要求各自有结论 | 子要求数 = 台账行数 | 一条多问意见只有一条回复 |
| A3 | 交叉意见口径一致 | 同一问题在两处回复的结论不冲突 | 一处说已改、另一处说不能改 |
| A4 | 无遗漏的子要求 | 机检 `coverage` 通过（`uncovered` 为空） | 台账有行但无决策或无回复文字 |

## B. 改得准（定位与留痕）

| # | 判定条件 | 通过 | 未通过的表现 |
|---|---|---|---|
| B1 | 每处修改带四字段留痕 | `revision_log{original,revised,reason,basis}` 齐全 | 只有"已修改"没有前后对照 |
| B2 | 新句在修订稿可检索 | 机检 `revised_in_revised` 全 match | 回复信说改了，稿里找不到 |
| B3 | 原句在基线稿可检索 | 机检 `original_in_baseline` 全 match | 声称的原句在基线稿里不存在 |
| B4 | 每处修改有定位串 | 机检 `locator_present` 全通过 | 只有"见第X节"这类模糊指向 |
| B5 | 联动改动同步 | 摘要/表格/图号/参考文献编号已逐项核对 | 摘要数字与正文不一致 |

## C. 证得住（证据）

| # | 判定条件 | 通过 | 未通过的表现 |
|---|---|---|---|
| C1 | 补做项有出处 | `evidence.source` 可在基线稿逐字回证 | 引文在基线稿中检索不到 |
| C2 | 不能补的如实标注 | status=not_possible 且有替代方案 | 声称"已补充"但无任何内容 |
| C3 | 证据状态合法 | `evidence_status_valid` 全通过 | 出现自造状态值 |
| C4 | 无未回证引文 | `unbacked` 为空 | `unbacked` 非空却未处理 |

## D. 对得上（三方一致）

| # | 判定条件 | 通过 | 未通过的表现 |
|---|---|---|---|
| D1 | 回复文字在回复信中可检索 | 机检 `letter_in_letter` 全 match | 台账写了回复但信里没有 |
| D2 | 三角对齐成立 | 机检 `triad_ok` 全通过 | 回复↔修改↔基线三者对不上 |
| D3 | 语气受控 | 机检 `tone_clean` 通过 | 冒犯/过度承诺/无原则顺从 |
| D4 | 闸门状态如实 | `gates` 全 enforced 或有 gate_note | 未核对的项宣称已核对 |

## E. 交付形态

| # | 判定条件 | 通过 | 未通过的表现 |
|---|---|---|---|
| E1 | result.json 字段齐全 | `verify` verdict=pass | 契约字段缺失或为 null |
| E2 | 主产物已嵌入 | `letter_markdown`/`revised_markdown` ≥200 字 | 只有文件路径没有正文 |
| E3 | 语义字段齐全 | `triad`/`fact_source_map`/`version_boundary` 非空 | 缺题面《输出要求》任一行 |
| E4 | 可编辑产物存在 | revised + response_letter 均为可编辑文件 | 只有 PDF/截图 |
| E5 | status 诚实 | complete 仅当全齐；否则 partial + uncertainty 列缺口 | 缺件却报 complete |

## F. 增益与效率（对照真实运行）

| # | 判定条件 | 通过 | 未通过的表现 |
|---|---|---|---|
| F1 | 同输入对照真实跑过 | `gain_evidence.comparison_design.same_input=true` 且含 full vs baseline 逐项数字 | 只有文字自述"效果更好" |
| F2 | 机制→指标可归因 | `mechanism_to_metric` 每条含 full/ablated/baseline 三值 | 只有"有提升"无归因 |
| F3 | 效率计数实测 | `efficiency.script_call_total` > 0 且来源为 run_log | 手工填写步数 |
| F4 | 边界如实 | `boundaries` 明示退化变体不等于平台基线 | 把派生变体冒充真实基础 Agent 输出 |

## 判定汇总

- **A+B+C+D 全通过** → 可交付编辑部。
- **E/F 有未通过项** → 先修产物或补齐证据字段，再 finalize。
- **任一机检 verdict=fail** → 报告与 result.json 会如实记录问题，**但仍须完成交付**
  （退出码恒为 0，失败不中断交付；修复后重跑即可改判）。

## 复跑命令

```bash
python3 scripts/ledger_audit.py --ledger <台账> --letter <回复信> --revised <修订稿> \
  --original <基线稿提取目录> --out <审计报告>
python3 scripts/gain_compare.py --ledger <台账> --letter <回复信> --revised <修订稿> \
  --original <基线稿提取目录> --out <增益证据.json> --runlog <run_log.jsonl>
python3 scripts/build_result.py verify --case <case.json> --out <result.json> --report <自检报告.json>
```
