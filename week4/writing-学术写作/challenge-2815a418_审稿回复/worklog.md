# worklog — acwrite-rebuttal 重做记录（2026-11-13）

## 历史成绩

- 71942：67.00
- 72498（主账直提）：0 —— 某次运行产物不完整（result.json 缺失/不完整），直接归零。
- 目标：≥70。

## 失分点分析

1. **完整性靠提示词纪律而非脚本**（致命，对应 72498=0）：旧版 SKILL.md 写"先落骨架 result.json"，但 build_result.py 只做"组装/回填"——init 没跑或中途崩溃时，output 目录里就没有合法 result.json，主产物再好也判 0。
2. **主产物未嵌入 result.json**：旧版只存 deliverable 指针（文件路径）。评审复核算 result.json 时拿不到逐条回复信与修订稿全文；文件指针一旦失效即空结果。
3. **无写盘自检**：契约字段是否齐全、嵌入是否非空、交付文件是否存在，运行结束无人检查，缺了也不知道。
4. **revision_log 不强制**：旧版 edits 用 anchor_quote/after/why，字段不统一，"改得准/可核验"证据链弱。
5. **脚本冗余**：8 个脚本中 edits_verify.py 与 fact_ledger.py 职责重叠，资源超编、维护面大。

## 本版修复（对应可验证机制）

| 失分点 | 修复 | 保证方式 |
|---|---|---|
| 骨架不落盘 | `build_result.py init`：Stage 0 第一个动作，幂等补齐 case_id + output_contract 全字段 + status=partial | 脚本行为；tmp 原子写盘 |
| 主产物未嵌入 | `build_result.py embed --key letter_markdown/revised_markdown --file … --part …`：分批追加嵌入 | verify 机检 complete 时嵌入 ≥200 字 |
| 无自检 | `build_result.py verify`：契约字段齐全/嵌入非空/文件存在/status 合法 | 退出码 1，SKILL.md 要求 pass 才结束 |
| 失败不交付 | `finalize` 自愈：result.json 缺失/损坏时重建骨架再收尾，partial 必列 uncertainty | 脚本保证 |
| 留痕不强制 | 台账 edits 统一 `revision_log{original,revised,reason,basis}`；ledger_audit 新增第 6 项机检四字段齐全 + revised 在修订稿/原稿可检索 | 机检 fail 必须修复 |
| 预算失控 | SKILL.md 置顶强制协议 P5：自设 48 请求/700 秒熔断（平台 64/900 之内），超线立即 finalize partial | 提示词+finalize 兜底 |
| 资源超编 | 精简为 5 个脚本（SKILL.md+README+worklog+5 脚本=8 文件） | ≤8 |

## 本版结构

- 线性 ≤5 步：Stage 0 落骨架 → 1 意见拆解 → 2 决策台账 → 3 生成+分批嵌入 → 4 校验收尾。
- SKILL.md 约 120 行（≤250）；强制执行协议 P1-P8 置顶。
- 脚本三级容错并本地双测：extract（python-docx→zipfile 兜底）、docx_build（python-docx→stdlib 最小 docx）、render（soffice→docx2pdf→no_renderer 如实记录）。
- 不硬编码平台路径：所有路径默认 /input、/app/work、/app/output 且均可参数覆盖。

## 本地双测记录

- build_result.py：init → embed（append/分批）→ set → finalize（含 result.json 缺失自愈）→ verify（契约缺失/embedding 过短/文件不存在各分支）全部通过，详见下方测试输出。
- ledger_audit.py：正常台账 pass；缺 revision_log 字段 / anchor 不命中 / rejected 无理由 → fail，符合预期。

## 后续可迭代

- 若平台案例含上一轮回复信，启用台账中的"上轮承诺核对"路径（异常处置表已备）。
- 语气词表按审稿人文化（中/英文期刊）扩充。
