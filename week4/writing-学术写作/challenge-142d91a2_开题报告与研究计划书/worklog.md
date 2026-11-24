# worklog — acwrite-proposal v3 重做（challenge-142d91a2）

日期：2026-11-13　目标：聚合分 ≥70（当前最高 62.00：71292:62 / 72142:59.67，另有多轮 0 分）

## 一、旧版失分点分析（逐条核对旧提交 acwrite-proposal v2 + 脚本）

| # | 失分点 | 证据 | 严重度 |
|---|---|---|---|
| 1 | **最后一步组装必挂**：SKILL.md Step 4 调用 build_result.py 时传 `--embed-file /app/output/proposal.md --embed-key deliverable_content`，但该脚本根本没有定义这两个参数 → argparse 报 "unrecognized arguments" 退出，result.json 停留在 Step 0 骨架（status=partial，主产物缺位）。70 分标杆 acwrite-transfer 的 SKILL.md 恰好没传这个参数，所以它没踩坑。 | 旧 SKILL.md L55 与 scripts/build_result.py argparse 定义对比 | 致命：直接丢"实际效果 40 分"大半与"结果完整性" |
| 2 | **主产物嵌入路径断裂**：协议第 3 条要求全文内嵌 deliverable_content，但唯一入口（build_result.py）不支持嵌入，模型若手工拼全文 JSON 又会被 16384 token/响应截断 → 两头落空。 | 同上 | 致命 |
| 3 | **fact_check 对开题稿必然误报**：fact_ledger.py check 把草稿里所有数字都要求出现在来源台账，而开题报告天然含计划数字（"第1-6月""30例""3年"）→ fact_check 恒 fail、误报几十条"疑似幻觉"，浪费预算修复或带病交付。 | 旧 fact_ledger.py cmd_check 无白名单机制 | 高：丢"结果可核验性"分数并诱发错误改稿 |
| 4 | **脚本对脏输入会崩**：fact_ledger.py `_load_ledger`/check、plan_check.py 对 jsonl 逐行 `json.loads` 无 try；constraints 缺失即崩；崩一次中间产物链断裂。 | 旧 plan_check.py L17-20、fact_ledger.py L80-86 | 高：丢"运行稳定性/异常处理" |
| 5 | **SKILL.md 缺最小调用示例**（题目交付要求明确列了这一项），且 README 示例无示意输出标注。 | 旧 SKILL.md 无示例节；对照 71 分 acwrite-transfer 有 §3 示例 | 中：生态贡献分 |
| 6 | **契约键提取覆盖面窄**：build_result.py 只认 `contract.fields/required` 列表，dict 形态（字段名→schema）会提取失败 → 骨架缺键。 | 旧 build_result.py L55 | 中 |
| 7 | 无 worklog；README 无适用边界/自查方法细节。 | — | 低 |

## 二、关键改进（v3）

1. **build_result.py 支持 --embed-file/--embed-key**：脚本读文件回填字符串，绕开模型响应 token 截断；末尾输出自检 JSON（contract_keys_empty / embed_chars / case_id），协议第 6 条有据可依；status 收敛四级、越界自动降级 partial 并登记。
2. **契约键提取全形态兼容**：list[str]、list[dict(name/key/field/id)]、dict(fields/required/keys/properties)、dict 顶层键。
3. **分片写作防截断**：draft_p1/p2/p3.json 分片产出，docx_build.py 接受多位置参数依序合并（sections 串联、references 去重、meta 合并），脏分片跳过登记，全部无效时仍产出占位可编辑稿并写明原因——不产空结果。
4. **计划数字白名单**：fact_ledger.py check 增 `--allow plan.jsonl milestones.jsonl risk_table.jsonl`，计划声明的数字放行；来源数字仍逐条回溯；台账缺失时 verdict=skipped（不误判 fail）。
5. **全脚本三级容错**：逐行 try、缺文件降级、缺 constraints 跳周期检查、退出码恒 0（结论看 verdict JSON）；本地正例+反例双测。
6. **补齐交付面**：SKILL.md 增最小调用示例（示意输出标注）、README 增边界/自查/维护、新增 worklog.md。
7. 保持已验证有效框架：协议 7 条置顶（含 48 请求/700 秒熔断）、5 步线性、`find /skills` 动态定位（无硬编码平台路径）、资源 6 脚本 ≤8 文件。

## 三、本地双测记录

- 正例：合成 case.json（含 output_contract dict 形态）+ 3 分片 draft + 三表 → docx/md 生成、plan_check pass、build_result 契约键全齐、embed_chars>0。
- 反例：脏 jsonl / 缺 constraints / 缺 draft 分片 / 空 ledger / 非 JSON case → 全部不崩溃，verdict=error/skipped 或占位稿，退出码 0。

## 四、遗留风险

- output_contract 真实形态未知（datasets/ 为空），v3 已做全形态兼容兜底。
- render_preview 依赖环境 soffice；无渲染器时如实记 no_renderer（评分项要求 PDF/PNG 预览，已尽力而为并留日志）。
