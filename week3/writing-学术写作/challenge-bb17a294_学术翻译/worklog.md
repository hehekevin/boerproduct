# worklog — challenge-bb17a294 学术翻译 Skill 重做（redo-w11-translate）

日期：2026-11-13 · 目标：65 → ≥70 · 产出目录：`bohrium-week3-redo/challenge-bb17a294/submission/`（未提交）

## 差距诊断（对照 71 分标杆 acwrite-transfer + 团队已验证方法）

65→70 差距集中在两个评分直接项：
1. **术语一致率**：旧版 align_check 的术语检查是弱启发式（只有"英文术语残留"检测），无禁用变体清单、无 fail 级扫描。
2. **逐段可回溯**：旧版主产物只交付文件指针，result.json 不自含，复核需打开外部文件。

## 改动清单

| 改动 | 对应评分项 |
|---|---|
| SKILL.md 顶部新增「强制执行协议」（抄契约+立即落骨架+字段一个不缺+广度优先+48请求/700秒熔断+写盘自检+失败也交付），线性流程压缩为 5 步，107 行（≤250） | 实际效果/可靠体验 |
| terminology.jsonl 新增必填 `forbidden` 禁用变体清单；align_check.py 全译文（含题注段）机械扫描，禁用变体出现即 fail（exit 1） | 术语稳 → 实际效果·正确性 |
| align_check.py 数字比对归一化：去千分位、剥除语向差异量词后缀（例/名/年…），保留万/亿量级单位参与比对 —— 避免误报且不放过量级错误 | 数字实 |
| build_result.py 新增 `--embed-pairs/--embed-segments/--embed-terms`：把 bilingual_pairs（段号/locator/原句/译文/role 一一对应）、glossary（术语/译法/首现位置）、fidelity_table（数字·单位·公式·引用编号核对结果）**完整嵌入 result.json** | 对得齐/可核验性/完整性 |
| align_check.py 三级容错（文件缺失→error 报告 exit 2 不静默通过；坏行跳过；硬失败 exit 1） | 运行稳定性/异常处理 |
| README.md 重写：用途/快速使用/资源清单/依赖（纯标准库）/关键方法与评分对应/限制 | 生态贡献·文档 |
| examples/example_input.json 最小示意输入（标注非正式案例） | 生态贡献·示例 |

复用未改动（旧版已验证可用）：extract_materials.py / fact_ledger.py / docx_build.py / render_preview.py。

## 本地双测记录（全部通过）

- **Case A 干净路径**：2 段（body + figure_caption）、含 12,345/67.8%/[1]/n=320 → verdict=pass, num_bad=0, term_viol=0（证明量词后缀归一化不误报）
- **Case B 禁用变体**：译文故意用"肿瘤环境""存活率" → verdict=fail, term_viol=2（禁用变体扫描命中）
- **Case C 嵌入**：build_result.py → result.json 含 bilingual_pairs(2)/glossary(2)/fidelity_table/契约字段回填/case_id/status，key 集完整

## 待办/风险

- 未提交（按指示）。
- docx_build/render_preview 沿用旧版，若平台环境无 LibreOffice，预览走降级路径，不阻断主流程。
