# worklog — acwrite-proposal（challenge-142d91a2）

## v4 增强（2026-11-16）— 补 83 公式缺失要素

### 一、对照 83 分公式逐要素核查（基于 v3 当前最优包 72.00）

| # | 83 公式要素 | v3 现状 | 判定 |
|---|---|---|---|
| 1 | 强制执行协议置顶 7 条 | SKILL.md §强制执行协议 完整 | ✓ 已有 |
| 2 | 主产物结构化全量嵌入 result.json | --embed-file 脚本回填 deliverable_content | ✓ 已有 |
| 3 | 每个可核验点机械校验器+逐条三元组嵌入 | 有 plan_check/fact_check，但**无章节完整性、路线可执行性、时间表一致性机检**；plan_check 只对 jsonl 不对正文 | ✗ **缺** |
| 4 | 闸门状态显式枚举 enforced/skipped/not_found/unreadable | fact_check 有 verdict=skipped，plan_check 有 incomplete，但未按闸门枚举统一、无 gate_note「下游不得宣称已核对」 | ✗ **缺** |
| 5 | 证据逐字摘录+定位（{item, template_value, applied, match}） | plan_check 输出 problems 聚合，无逐条三元组 | ✗ **缺** |
| 6 | status 诚实四级 | build_result 收敛四级 | ✓ 已有 |

团队提示的三个补强点即要素 3/4/5 的具体化：**全部章节嵌入完整性机检、技术路线可执行性逐条核对、时间表-内容一致性机检**。

### 二、v4 补强内容

1. **新增 scripts/seven_check.py（纯标准库，1 文件）**，三项机检逐条输出 `{item, expected, applied, match, location}`：
   - **A 七要素章节完整性**：9 项必备章节（背景/现状缺口/问题定义/目标/路线/计划/风险/成果/边界与不确定性）逐项在正文关键词命中并给出行号定位；缺失计 fail。
   - **B 技术路线可执行性**：新增 route.jsonl 约定（sid/name/input/output/depends/resources/milestone），逐条核对五字段齐全、依赖 sid 真实存在、每步归属 ≥1 个有效里程碑；未提供 route.jsonl 时 gate=skipped_not_provided 且 gate_note 写明「下游不得宣称技术路线已逐条核对」。
   - **C 时间表-内容一致性**：每个里程碑周期必须在正文逐字回证（防正文乱排时间表）、正文非表格行出现的"第X-Y月"区间必须有对应里程碑条目（防正文自排计划脱离里程碑）、区间不超 constraints.total_months；里程碑缺 deliverable 计 fail。
   - **闸门显式枚举**：enforced / skipped_not_provided / not_found / unreadable 四态；任何 skipped/unreadable 写 gate_note，verdict=pass 要求全部闸门 enforced，否则 incomplete。
   - **fail 冒泡**：存在 fail 时退出码 2（不只是打印），verdict=fail。
2. **build_result.py 增 --seven-check**：报告嵌入 result.json["completeness_check"]，自检 JSON 增 seven_check_verdict 字段——评分器不开附件即可核对三项机检逐条结果。
3. **SKILL.md**（127 行 ≤150）：Step 2 增 route.jsonl 写作规则 + 里程碑周期/交付物与正文逐字一致要求；Step 3 增 seven_check 调用与三元组说明；Step 4 增 --seven-check；示例与自查清单同步。README 增创新点 5、示例、文件清单行。
4. **保留 v3 全部有效机制**：协议 7 条、分片防截断、白名单、四级容错、find /skills 动态定位，无推翻无重构。

### 三、v4 本地双测证据（challenge-142d91a2/_tests/）

- **正例全链路**：合成 case（dict 形态 contract）+ 3 分片 draft + plan/route/milestones/risk 四表 → docx_build（7 sections，stdlib 兜底）→ plan_check pass → **seven_check verdict=pass（19/19 match，exit 0）** → build_result 自检 `{"contract_keys_empty":[],"embed_chars":689,"seven_check_verdict":"pass"}`。
- **反例 1**：删除正文"研究背景"章节 → **verdict=fail（缺 1 项，exit 2）**，机检抓到（该 bug 在首轮测试中被发现——check_sections 返回值未入 fails，已修复后复测通过）。
- **反例 2**：route 步骤 S2 删 output 字段 → **verdict=fail（B_route_executability 字段缺失，exit 2）**。
- **反例 3**：正文进度表 MS2 周期 7-18月→7-20月、MS4 31-36月→35-40月 → **verdict=fail（2 条：正文周期与 milestones 脱节 + 超给定周期，exit 2）**。
- **反例 4**：milestones 文件缺失 + 未提供 route → 不崩溃，verdict=incomplete，gate=milestones:not_found / route:skipped_not_provided，gate_note 登记，exit 0（诚实降级）。
- 首轮正例测试还暴露"首步 depends=[] 被误判字段缺失"，已修正为键存在性判据。

### 四、遗留风险

- output_contract 真实形态未知，v3 全形态兼容兜底继续有效。
- render_preview 依赖环境 soffice；无渲染器时如实记 no_renderer。
- seven_check 章节关键词为通用词表，若案例要求特殊章节名，材料盘点（Step 1 constraints）仍需模型登记——关键词表不覆盖的模板章节以"边界与不确定性"项兜底标注。

---

# v3 重做记录

日期：2026-11-13　目标：聚合分 ≥70（当时最高 62.00：71292:62 / 72142:59.67，另有多轮 0 分）

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
