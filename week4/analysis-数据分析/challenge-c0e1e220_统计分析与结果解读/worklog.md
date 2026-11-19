# worklog — stat-analysis-audit（challenge-c0e1e220）

开发记录：2026-11-19，作者 w7-ana2（week4 参赛包制作）。所有数字为本地实跑
实测（Windows 11 / Python 3.13 / Git Bash），非臆造。

## 1. 交付内容

```
submission/
├── SKILL.md                     （148 行，≤150 达标）
├── README.md                    （生态十项 + 自检清单 C1–C10）
├── worklog.md                   （本文件）
├── scripts/
│   ├── build_skeleton.py        Step 0 落骨架/数据集清单/claim_rules 模板
│   ├── stat_recompute.py        描述统计复算 + 检验期望（新增领域引擎）
│   ├── interpret_rollup.py      解读强度机械汇总（新增，对标 grade_rollup）
│   ├── verify_check.py          七组业务校验（覆盖/分级/证据/缺陷/复算/因果/弃权）
│   ├── schema_guard.py          output_contract + 业务 schema 守卫
│   └── gain_probe.py            正常 vs 退化双跑 + 9 类污染注入 + 效率计数
└── examples/
    ├── example-case.json        合成案例（2 组虚构数据集，标注示意）
    └── example-result.json      示意输出（非正式答案）
```

包规模：11 个文本文件，约 100 KB（<2MB、<50 文件达标）；零第三方依赖
（statistics/math/json/os/re/sys/argparse/copy/time）。

## 2. 与骨架（challenge-bace1c46）的领域化改造对照

| 骨架件 | 本题改造 |
|--------|---------|
| grade_rollup.py（罚分/偏倚汇总） | 改造为 interpret_rollup.py：新增 strength_map（设计类型→允许结论强度）、causal_verbs 因果动词扫描、overclaim 过强结论降级；输出键改为 interpret_summary |
| verify_check.py（五组校验） | 扩为七组：+ [recompute] 统计量复算一致（含 stat_live_diff 现场比对）+ [causal] 因果表述约束；judgment 枚举改为 supported 族；defect 组改为 method_error≠reporting_gap |
| gain_probe.py（5 类污染注入） | 扩为 9 类领域污染：+ 统计量篡改（mean_claimed 改值）+ 结论强度夸大（claim_strength→causal）+ 因果越界表述（claim.text 换因果动词句）；ablate 组扩为 7 组 |
| build_skeleton.py（文献清单） | 数据集清单（datasets/records/data/tables…）+ 六分面清单模板 + claim_rules 模板（含 strength_map/causal_verbs） |
| 新增 stat_recompute.py | 从原始数值复算 n/mean/variance/stdev/分位数（样本方差 n-1、线性插值分位数），缺失跳过计数绝不按 0；检验期望按组数/配对/正态性/方差齐性/test_type 机械推导（Welch/Mann-Whitney/ANOVA/Kruskal/配对 t/Wilcoxon/Pearson/Spearman） |

## 3. 真实对照数字（2026-11-19 实跑）

**干净链路（examples/example-case.json + example-result.json，/tmp 副本）**

| 步骤 | 结果 |
|------|------|
| build_skeleton | exit 0，提取 2 组数据集、6 个 contract 字段、claim_rules 模板落台账 |
| stat_recompute | exit 0，A01/A02 match=true、test_mismatch=false、all_match=true（A01 mean=53.65833333333333 / sd=4.740053381619881 / p25=50.25 / p50=53.5 / p75=57.775…；A02 mean=5.59 / sd=1.3973282777463116） |
| interpret_rollup | exit 0，A01 penalty=2→overall=medium（experimental，allowed=causal，overclaim=false）；A02 penalty=1+1 弃权→overall=uncertain（observational，allowed=associative） |
| verify_check | exit 0，verdict=PASS，61 条检查项 |
| schema_guard | exit 0，verdict=PASS |
| gain_probe（--emit-into --inject-pollution） | exit 0，正常=退化=PASS，steps_count 68 vs 19（delta=49），七组漏检全 0 |

**污染反例（同一校验器，注入 9 项领域污染的副本）**

| 指标 | normal | degraded | delta |
|------|--------|----------|-------|
| problems 总数 | 25 | 1 | −24 |
| coverage 漏检 | 0 | 1 | +1 |
| grading 漏检 | 0 | 3 | +3 |
| evidence 漏检 | 0 | 8 | +8 |
| defect 漏检 | 0 | 1 | +1 |
| recompute 漏检 | 0 | 1 | +1 |
| causal 漏检 | 0 | 1 | +1 |
| pending 漏检 | 0 | 1 | +1 |
| 漏检合计 | **0** | **16** | +16 |

注入的 9 项（全部注入副本，原文件不被改动）：A02 mean_claimed 5.59→22.89（统计量
篡改）、A02 claim_strength→causal（结论强度夸大）、DE-01 换编造引文、EC-01
unreported 改归 method_error（缺陷混淆）、删一条 appraisal（清单漏覆盖）、
claim.text 换因果动词句（因果越界）、interpret_summary[A01] 篡改 penalty=0/overall=low
（解读汇总失据）、清空 pending_review、清空 claims。正常模式 25 处全抓
（caught_by_normal_mode=true），退化模式只剩 1 处通用结构问题、漏检 16。

**失败路径退出码（实测）**：六脚本对 /nonexistent.json / case 缺失全部 exit 0。

**硬约束自检**：SKILL.md 148 行（≤150）；frontmatter 合法（name/description）；
命令一律 python3；统计复算仅标准库 statistics/math（未装 numpy）；examples 标注
"示意，非正式答案"；定位标志（../SKILL.md 同包）命中后 marker_hit=True（示例链路
在提交目录外跑时 WARN 提示，属预期设计）。

## 4. 开发中发现并修复的 3 个真实 bug

1. **claimed 键名映射缺失**：stat_recompute 初版把 `descriptive` 直接当 claimed
   传入 compare，而字段名是 `mean_claimed`/`sd_claimed`/`quantiles_claimed`——
   复算比对全部空转（match=true 但什么都没比）。修复：归一化映射
   （mean_claimed→mean 等）后再比对。
2. **外层变量泄漏**：verify_check 数字回证的 `cnorm` 拼接写成
   `" ".join([norm(c.get("text"))] + [... for c in claim_idx.get(aid)...])`，第一个
   元素用了早前循环残留的 `c`（取到 A02 的文本），A01 的 claim 文本根本没进回证
   索引，5 个数字全部误判 unbacked。修复：先取 `_cl = claim_idx.get(aid)+["*"]`
   再两次推导。
3. **复算后篡改盲区**：污染注入改了 claimed 统计量，但 stat_recompute.per_dataset
   里的旧 match=true 不会失效，[recompute] 组抓不到（首版 recompute delta=0）。
   修复：verify_check 增加 stat_live_diff（claimed vs 落盘复算值现场比对），
   gain_probe 真值侧独立实现同口径比对；修复后 recompute 漏检 delta=1。

## 5. 诚实边界

- 增益对照是本校验层"正常 vs 退化"两模式，**不等于**平台"基础 Agent vs 参赛
  Skill"的白板对照；平台对照结论由平台生成，本探针不代替、不冒充。
- 因果动词扫描是子串匹配的保守设计：可能误报否定句式（"未导致"），宁误报不
  漏报，命中后须人工复核并如实登记（写进 SKILL.md 已知限制）。
- 复算口径固定为样本方差（n-1）+ 线性插值分位数；claimed 若是总体方差（n）口径
  会在 diffs 中显示，需按口径人工核对——不是脚本错，是口径差异。
- 追问轮次按每轮 3 条折算的估计量，非实测交互次数；model_requests 由 Agent 回填，
  本地未跑模型，保持 null。
- 实测环境是 Windows 11 / Git Bash / Python 3.13（命令用 python 别名）；平台运行
  时按 SKILL.md 约定用 python3，路径全部参数化，已尽量消除平台差异，但未在
  Linux 容器里复跑过——这是剩余风险。
- 正式 3 个固定案例的原始数据形态（UCI Concrete/Iris/Wine 快照 + SQLite）未见过
  实件，stat_recompute 的取数路径（values/rows/列式三类）是按常见形态做的防御性
  兼容；若平台数据形态超出这三类，复算会如实记 unavailable 而不是硬算。

## 6. 剩余风险与建议

- 风险 1：平台 case.json 的数据集键名若不在 DATA_KEYS 兼容列表内，Step 0 会降级
  为手工兜底（有 WARN 提示，不致命）。
- 风险 2：SQLite 数据库文件作为输入时，标准库 sqlite3 可读但本包脚本未集成
  （题面环境 resources.yaml 未确认是否提供）；届时 Agent 需先导出数值列再走
  Step 2 登记。
- 建议：若时间允许，把 stat_recompute 的容差与方差口径做成 CLI 参数已在
  --tolerance 支持（方差口径暂固定 n-1，见 SKILL.md 已知限制）。
