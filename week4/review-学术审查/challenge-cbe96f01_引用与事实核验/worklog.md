# worklog — cite-support-check（challenge-cbe96f01）

## 2026-11-22 v2 重构记录（极简单点：从六分面砍到单一"引用支持判定"）

### 砍了什么（对照 v1）
| 项 | v1（0 分） | v2（重构后） |
|----|-----------|-------------|
| 方向 | 六分面：引用支持 + 编造引用 + 事实比对 + 数值一致 + 来源可靠 + 证据定位 | **单一**：引用支持判定 |
| 脚本 | 7 个 | **4 个** |
| SKILL.md | 150 行 | 107 行（≤150 ✓） |
| 判定对象 | 全部稿件全部发现 | 仅正文带引用标号的结论句（8-12 条） |
| 增益层 | gain_probe 双跑 + 污染反例 | 降级跳过（available=false） |

### 保留的核心机制
- 引用支持四档判定：fully_supported / partially_supported / unsupported / cannot_determine。
- 过度推断识别（over_inference），对应"引用存在 ≠ 引用支持"的核心考点。
- 读不到被引原文 → cannot_determine + source_accessible=false，不脑补。
- quote 逐字回证原文 + cite_markers 回证参考文献表（机械校验）。
- 4 条保命铁纪律：第 0 步落骨架 / 失败也交付 / 退出码恒 0 看 verdict / 预算过半即定稿。

### 脚本职责
| 脚本 | 职责 | 键归属 |
|------|------|--------|
| build_skeleton.py | Step 0 落骨架 + 稿件结构 + skill_marker.json 标志文件 | result 骨架全键 |
| citation_scan.py | 机械提取带引用标号结论句候选 + 引用标记底账 | result.citation_scan |
| verify_check.py | 四档枚举 / quote 回证 / cite_markers 回证 / cannot_determine 诚实性 / 过度推断一致性 / coverage 汇总 / 契约字段 | 顶层 self_check / gates / validator_verdict + result.coverage |
| schema_guard.py | output_contract + 业务 schema 结构守卫 | 报告 |

### 自我校验数字（2026-11-22 实跑）
- 合成案例（examples/example-case.json，虚构论文）候选结论句 5 条，判定 4 条。
- build_skeleton：case_id=demo-citesup-001，章节 5，参考文献 4，退出码 0。
- citation_scan：候选 5 条 / 正文标记 4 / 表外标记 [9] / 未引用 [3]，退出码 0。
- verify_check：PASS（citation_checks=4 judged=4），退出码 0，幂等（回写后仍 PASS）。
- schema_guard：PASS，退出码 0。
- 三脚本对缺失 result.json 全部退出码 0，不中断交付。

### 规模上限核对
- 文件数：SKILL.md + 4 脚本 + README + worklog + 2 examples = **9 个**（≤50 ✓），无 GITHUB_URL.txt（不预置答案）。
- SKILL.md 107 行（≤150 ✓）；零依赖；python3 标准库；标志文件定位 skill_marker.json。
- 不装 pip，不联网，不预置正式案例答案（examples 全为合成示意）。

### 诚实边界
- 引用支持判定是被引文献在材料内可读摘要/主张文本的语义对照；原文不可读一律 cannot_determine。
- gain_evidence 降级：极简单点策略把增益层放在预算 50% 之后，本包固定 available=false 并写明 reason，不编造对照数字。
- 平台白板对照由平台生成，本包不冒充。