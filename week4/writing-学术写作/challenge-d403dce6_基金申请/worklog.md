# worklog — acwrite-grant 重做（challenge-d403dce6）

日期：2026-11-13 ｜ 目标：从 63.67 分重做到 ≥70

## 旧版问题诊断（对照 71 分标杆 acwrite-transfer）

| # | 问题 | 证据 | 后果 |
|---|---|---|---|
| 1 | **SKILL.md 调用 build_result.py --embed-file，但脚本 argparse 无该参数** | 旧 SKILL.md L56 vs 旧 build_result.py 参数表 | 命令必然报 argparse error，主产物内嵌失败/流程中断 |
| 2 | **全稿 1-2 次响应写完** | 旧 SKILL.md Step 2「体裁化写作（1-2 次响应）」 | 申请书全文远超 16384 token，截断风险高，产出残稿 |
| 3 | 预算只有一句「不编造金额」，无机器可核对的机制 | 旧 SKILL.md 异常表 | 预算数字编造无法检出 |
| 4 | build_result --status 无条件覆盖 | 旧脚本 L101 | 骨架期 status=complete 覆盖早期诚实状态 |
| 5 | 脚本定位只搜 /skills | 旧 SKILL.md Step 0 | 安装目录不同则脚本全挂 |

## 本次改动

1. **修复 build_result.py**：新增 `--embed-file/--embed-key/--append`（逐章回填）；`--status` 缺省时保留已有状态；自身崩溃兜底写 failed result.json（三级容错）。
2. **逐章分批写作**：SKILL.md 协议第 3 条禁止单响应全稿；7 章每章 1 响应、落盘 chapters/chNN.md、立即 --append 回填（防 16384 截断，中断可交付半成品）。新增 merge_chapters.py 合稿（json/md 两种片段格式，容错解析）。
3. **预算数字-来源核对表**：budget_ledger.jsonl（item/amount/source_locator/status=sourced|assumed|missing）；align_check_grant.py 新增 --budget 机检（金额非数字/状态非法/标 sourced 无 locator/有金额无状态=疑似编造 → fail）。
4. **对齐检查**：四向对齐（孤儿目标/不可考核指标/未引用路线/步骤缺 IO）+ 禁用修辞词（首次/国际领先/填补空白裸用）保留并加强。
5. 脚本定位扩为 `find /skills /app`；SKILL.md ≤250 行、5 步线性、7 脚本+1 示例 ≤8 资源文件。
6. 新增 protocol 第 5 条「数字-来源核对」为强制纪律（预算+研究内容数字双管）。

## 本地双测（Windows Git Bash，模拟平台路径约束）

- T1 正常路径：merge_chapters 合并 2 章 → docx_build 出 docx+md（python-docx 可用）→ fact_ledger build/check pass → build_result 骨架→逐章 append→终组装，JSON 可解析、嵌入齐全。
- T1b 机检：好账本 {"verdict":"pass","budget":2}；坏账本（有金额无状态）→ budget_unsourced fail；"国际领先"裸用 → banned_claims fail；missing 空金额合法不误杀。
- T2 异常路径：chapters 无 ch* → 警告不崩；embed 文件缺失 → uncertainty 记录 embed_missing 不中断；case.json 缺失 → unknown_case 回退；output_contract 字段（fact_sources/human_review_items）骨架期以 null 保留不丢；--status 缺省保留已有 partial。
- 双测全部通过（Windows Git Bash + Python，模拟平台路径约束，用相对/绝对路径混合验证脚本定位）。

## 提交物清单

- SKILL.md（约 130 行，5 步线性）
- README.md（含标注示意的最小示例）
- scripts/：extract_materials.py, fact_ledger.py, docx_build.py, render_preview.py（复用自 71 分标杆同源）；build_result.py（修复+回填）；merge_chapters.py（新增）；align_check_grant.py（增强+预算核对）
- examples/example_input.json（结构示意，含预算核对示意行）
- 未提交正式案例答案（平台固定 3 案例，遵守题面）
