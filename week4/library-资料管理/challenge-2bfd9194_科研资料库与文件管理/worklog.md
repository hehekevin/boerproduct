# worklog — lib-file-organizer（challenge-2bfd9194）

开发与实测记录。所有数字均为 2026-11-19 在本机（Windows 11 / Python 3.13.12）对
`examples/example-case.json`（合成案例）实际运行流水线所得，可按 README 第 7 节命令复跑。

## 1. 交付内容

| 文件 | 说明 |
|------|------|
| SKILL.md | 技能本体，140 行（≤150 合规），合法 YAML frontmatter |
| scripts/ × 7 | build_skeleton / classify_files / duplicate_check / audit_ops / verify_check / schema_guard / gain_probe（≤8 合规，全标准库，退出码恒 0） |
| examples/ × 3 | 合成案例（8 个虚构文件）+ 示例规则 + 示意输出（流水线真实产出，非正式答案） |
| README.md | 生态十项 + 最小自检清单（C1–C8 实测 exit 0） |
| worklog.md | 本文件 |

## 2. 流水线实测记录（examples 合成案例）

| 步骤 | 命令 | 结果 |
|------|------|------|
| Step 0 | build_skeleton.py | 8 文件入清单，7 个计算 sha256（F08 无内容 → no_content），contract 6 字段全落骨架 |
| Step 1-2 | 声明规则 + 逐文件登记 | 5 条规则事前声明（declared_at=step1）；F08 文件缺失 → skip_reason + skipped_conflicts |
| Step 3 | classify_files.py | 8/8 归类（raw_data×3、reports×2、documents×2、scans×1），rename 建议 8 条，action 分布 move_rename×7、skip×1 |
| Step 4 | duplicate_check.py | 重复组 1（F01/F02 同哈希，保留 F01）、版本链 1（F03/F04 主干相同哈希互异，F04 为 current） |
| Step 5 | audit_ops.py + gain_probe.py | ops 8 条链式哈希完整（尾 27e1…/08f7… 两轮实测）；五遍消融对照 + 污染反例 |
| Step 6 | verify_check.py + schema_guard.py | 双 PASS：problems=0，业务 verdict=organized，status=answered |

## 3. 增益对照真实数字（同输入五遍 + 污染副本两遍）

干净输入（无违规）五遍对照——机制漏检全为 0，符合预期（无违规可抓）：

| 模式 | problems | 机制漏检合计 |
|------|----------|-------------|
| normal（五组全开） | 0 | 0 |
| ablate:rules | 0 | 0 |
| ablate:duplicates | 0 | 0 |
| ablate:audit | 0 | 0 |
| ablate:all（仅覆盖底线） | 0 | 0 |

污染副本（同一校验器、同一污染输入，注入 4 类违规：改错归类/篡改重复组哈希/断审计链/清空跳过理由）：

| 指标 | normal | ablate:all | 差值 |
|------|--------|-----------|------|
| problems 合计 | **10** | **1** | **+9** |
| 机制漏检合计（rules/dup/version/audit/evidence） | **8** | **0** | **+8** |
| 分组明细 | rules 2 + judged 1 + duplicates 2 + audit 4 + evidence 1 | judged 1 | — |
| caught_by_normal_mode | true（注入 4/4 全部被抓） | — | — |

结论：全消融模式对 8 处机制违规全部漏检（只抓到 1 处覆盖底线违规）——消融数字证明
"规则重放 / 哈希判重复算 / 审计链哈希重算 / 证据回证"四组机制各有独立贡献，写入
`result.gain_evidence.delta_normal_minus_degraded` 与 `mechanism_to_metric_map`。

## 4. 效率计数（实测）

| 指标 | 值 |
|------|-----|
| 五遍消融 + 两遍污染 analyze 总墙钟 | ~0.008 秒（8 文件合成案例） |
| checker_runs | 7（5 runs + 2 pollution） |
| 全链路脚本运行次数 | 7 次脚本调用（Step 0/3/4/5×2/6×2） |
| 需人工修改条目 | 1（F08 文件缺失，登记后跳过） |

## 5. 迭代与修复记录

1. **审计链哈希顺序缺陷**：初版 audit_ops 先算 chain_hash 再补 prev_op_id，导致校验器
   重算必不符 → 修复为 prev_op_id 先入、哈希后算，全链 PASS。
2. **verdict 枚举检查的先有鸡还是先有蛋**：骨架态 verdict=None 被 verify 判枚举非法
   （而 verdict 本身由 verify 回写）→ 修复为 None（待填态）不报错，非 None 才查枚举。
3. **死代码清理**：移除 audit_ops 占位函数、verify_check 冗余 fmap、gain_probe 未用导入。

## 6. 诚实边界

- 所有示例数字来自**合成案例**（8 个虚构文件），用于证明机制运转与可复现性；平台 3 个
  固定案例的真实表现由平台实测，本包不预置正式答案。
- 增益对照是本校验层"正常 vs 消融"对照，**不等于**平台"基础 Agent vs Skill Agent"
  白板对照；后者由平台生成。
- 干净输入上消融 delta 全为 0——增益证据来自污染反例（把违规注入副本再对照），这正是
  "机制抓错能力"的可测形式；对完全无违规的输入，任何校验器都不会产生 delta。
- 版本链依赖「归一化文件名主干」，主干相同但实为不同文档的极端情况会误并入链（哈希互异
  约束可缓解，不能根除）；重复检测在无文件内容可读（全部 no_content/unreadable）时退化
  为登记，不产出判重结论。
- 脚本只产出整理计划与审计链（op.status=planned），真实落库动作由调用方执行后回填
  done——不冒充"已移动文件"。
- `efficiency.model_requests` 由 Agent 侧按实际请求数回填，脚本不可采集，缺失保持 null。

## 7. 硬约束自查（提交前逐条过）

| 约束 | 状态 |
|------|------|
| SKILL.md ≤150 行、合法 frontmatter | 140 行 ✓ |
| 脚本 ≤8、≤50 文件、<2MB、零外部依赖 | 7 脚本 / 11 文件 / 约 90KB ✓ |
| 命令一律 python3 | ✓（SKILL/README 全部 python3） |
| 挂载 /skills/weekly-skill；输入 /input/case.json + task.md；产出 /app/output/result.json | ✓ |
| 所有失败路径 exit 0，verdict 照实写 JSON | ✓（C8 实测不存在路径也 exit 0） |
| 不预置正式答案，examples 标注示意 | ✓（内联内容全虚构 + _note 标注） |
| 脚本定位标志文件校验式命中 | ✓（以 result.json/规则文件为唯一定位依据，无硬编码绝对路径） |
| 多脚本禁写同一键 | ✓（SKILL.md「脚本分工」逐键归属） |
| 防 isalpha 汉字陷阱 | ✓（全子串/正则匹配，规则模板与 SKILL 双重提示） |
| --ablate 同输入消融两遍以上 + 逐项指标差入 gain_evidence/efficiency | ✓（normal+4 组消融+污染双跑） |
| 同一校验器双跑 FAIL 差 + 污染反例注入副本 | ✓（10 vs 1，caught=true） |
| README 生态十项 + 最小自检清单实测 exit 0 | ✓（C1–C8） |
