# struct-diag-paper — 论文结构与逻辑诊断 Skill（challenge-8021aacb）

「学术效率」产品赛 · 学术写作赛道 · 论文结构与逻辑优化 参赛 Skill。

## 用途

对一篇完整稿件做六类结构诊断（章节结构/研究问题对齐/论证链/段落关系/重复内容/结论边界），
每条问题定位到章节/段落并附逐字引文，输出作者可直接执行的修改动作清单（move/merge/split/
narrow/insert/delete）与可编辑诊断报告（含采纳/部分采纳/驳回裁决栏）。

## 快速开始（Harness 执行环境）

1. 读 `/input/case.json` 与 `task.md`，逐字抄下 output_contract 全部字段名与 case_id。
2. `build_result.py --status in_progress` 落骨架，此后只回填不覆盖、不删键。
3. 按 SKILL.md 线性 7 步执行：extract_input → claim_extractor → 模型语义诊断（model_findings.json）
   → structure_check → edit_plan 合并 → gain_evidence → build_result 收尾。

## 依赖

- Python 3.8+，仅标准库即可运行全部脚本；所有命令用 `python3` 调用。
- 可选增强：PyMuPDF（PDF 稿件提取）、python-docx（docx 稿件提取）。缺失时脚本自动降级并在
  notes 记录（此时按 SKILL.md 异常处置表借助 Harness 的 pdf-text-tool），不阻塞交付。

## 文件清单（7 个脚本 + 文档，符合 ≤8 脚本 / ≤50 文件 / <2MB 限制）

| 文件 | 作用 |
|---|---|
| `scripts/extract_input.py` | 定位稿件（case.json 内嵌文本 > 最大文本文件；PDF/docx 可选库提取）、切章节 → manuscript.json + constraints.json |
| `scripts/claim_extractor.py` | 论点—论据映射：论断句×证据标记（数值/引用[n]/图表）→ claim_evidence_map.jsonl |
| `scripts/structure_check.py` | 六类结构机检校验器（完整臂）；`--ablate` 消融臂仅表层规则，供同输入对照 |
| `scripts/edit_plan.py` | 机检+模型 findings 合并（类别+引文+位置去重）→ edit_actions.jsonl + findings.json + report.md |
| `scripts/gain_evidence.py` | 同输入消融两臂真跑 + 污染反例注入验证 → result.json 的 gain_evidence/efficiency（独占键） |
| `scripts/build_result.py` | result.json 骨架/回填/收尾（契约全字段 + 三桶语义 + contract_coverage；不写 gain_evidence/efficiency） |
| `scripts/_rlog.py` | 运行日志：各脚本调用自动计数（efficiency 的 tool_calls 来源） |
| `examples/example_input.json` | 示意输入（**示意，非正式案例**）：含故意植入缺陷的示例稿件，可复跑全流程 |

## 方法要点

- **诊得准**：机检定位到 章节/段落/句子 三级位置 + 逐字引文；模型语义层补充机检盲区
  （循环论证、跨章节呼应断裂等），两层合并去重。
- **改得动**：动作类型限定六种可执行编辑操作，每条带 instruction 与位置锚点；report.md
  逐条给作者裁决栏（采纳/部分采纳/驳回）。
- **链得通**：claim_evidence_map 逐句建立论断—证据映射，support=none 即论证链断点候选。
- **说得清**：每条 finding 带 basis（机检规则口径 / 模型语义判断）与逐字引文，可独立复核。
- **键不冲突**：gain_evidence/efficiency 两键由 gain_evidence.py 独占；build_result.py 只回填其余键。
- **退出码恒 0**：校验失败/参数错误/输入缺失全部如实写 JSON，不以退出码表达成败。

## 最小调用示例（示意，非正式案例结果）

输入示意见 `examples/example_input.json`（含 `_notice` 标注）。示意输出：

```bash
python3 scripts/extract_input.py --input /input --outdir /app/work
# → {"ok":true,"case_id":"...","source":"file:manuscript.txt(text)","sections":6}
python3 scripts/structure_check.py --manuscript /app/work/manuscript.json --out /app/work/findings_machine.json
# → {"ok":true,"arm":"skill_full","fail_count":10}
python3 scripts/edit_plan.py --machine /app/work/findings_machine.json --out-report /app/output/report.md
# → {"ok":true,"actions":10,"report_written":true}
python3 scripts/gain_evidence.py --manuscript /app/work/manuscript.json --result /app/output/result.json
# → {"ok":true,"written":true,"fail_diff":10,"pollution":"pass"}
```

## 生态贡献：依赖、安装运行、目标用户与验收

| 项目 | 说明 |
|---|---|
| 依赖与版本 | Python 3（评测沙箱 3.12；脚本仅用标准库，无需 pip 安装）；PyMuPDF/python-docx 为可选增强，缺失自动降级。 |
| 安装与运行 | 平台把提交目录装入 `/skills/weekly-skill`；输入 `/input/case.json` + task.md + 稿件，产物写 `/app/output/result.json`（+ findings.json + report.md）。 |
| 输入 / 输出解释 | 输入=案例标识与稿件（case.json 内嵌文本或文件）；输出=result.json（契约全字段 + findings_merged + edit_actions + report_text + claim_evidence_map + gain_evidence + efficiency + uncertainty）。 |
| 目标用户与场景 | 需要结构级修改意见（而非润色）的论文作者；成稿后定稿前的结构自检与协作修改留痕。 |
| 验收方式 | ①契约键一个不缺且 JSON 可解析；②每条 finding 有位置+逐字引文+动作类型；③gain_evidence 含两臂差与污染反例命中数；④report.md 可编辑且有裁决栏。 |
| 常见问题 | PDF 无法提取→用 Harness pdf-text-tool 转文本后重跑 extract_input；机检误报→修一轮并 changelog 记录口径；模型诊断缺失→仅机检结论并在 gaps 登记局限。 |
| 已知限制 | 增益对照为同输入自比（完整臂 vs 消融臂），量化的是机检可发现的结构问题数，不等同跨模型横向评测；重复检测对大改写的同义表述会漏检；结论边界词表覆盖有限，委婉超边界表述需模型语义层补充。 |
| 失败处理 | 任一步异常：已产出文件保留、status 如实降级（complete/partial/failed/blocked）、error 写入对应 JSON 键；机检结论照实记录且退出码恒 0。 |
| 复用建议 | 六类 finding schema、两臂消融+污染反例的增益证据法、裁决栏报告格式可直接套用到同类「诊断+修改建议」任务。 |
| 版本与维护 | v1.0；见 worklog.md；新增稿件格式时扩展 extract_input.read_text 的 ext 分支与检测规则。 |

## 最小可运行自检清单（复制即跑；本地已在 _selftest 环境以相对路径等价实测，全部 exit 0）

```bash
python3 -c "import sys;print(sys.version)"                                        # 1) 解释器可用
ls scripts/                                                                        # 2) 脚本在位
python3 scripts/extract_input.py --input /input --outdir /app/work                 # 3) 提取+切章（无输入时也 exit 0 并如实登记）
python3 scripts/structure_check.py --manuscript /app/work/manuscript.json --out /app/work/fm.json   # 4) 完整臂机检
python3 scripts/structure_check.py --manuscript /app/work/manuscript.json --out /app/work/fa.json --ablate  # 5) 消融臂
python3 scripts/gain_evidence.py --manuscript /app/work/manuscript.json --result /app/output/result.json    # 6) 增益双跑+污染反例
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"  # 7) 产物可解析且含 gain_evidence/efficiency
python3 scripts/structure_check.py --bad-flag x                                    # 8) 参数错误仍 exit 0
```
