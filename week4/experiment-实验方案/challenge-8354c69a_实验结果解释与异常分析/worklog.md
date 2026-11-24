# worklog — challenge-8354c69a（exp-result-anomaly 重构记录）

日期：2026-11-22。本题：实验结果解释与异常分析。策略：从"五段解释"（46 分）重构为**极简单点——只做异常点定位一个方向**。

## 一、砍了什么（相对旧 46 分包）

| 方向 | 处置 |
|------|------|
| 结果趋势（趋势拟合/拐点/平台期判断） | 砍掉，fallbacks.trend 给一句话兜底 |
| 可能原因清单（按证据强度排序+支持/排除证据） | 砍掉，每个异常只配 possible_cause 一句话，不排序不断因果 |
| 复核步骤（可执行四要素清单） | 砍掉，fallbacks.recheck 一句话兜底 |
| 后续实验建议 | 砍掉，fallbacks.followup 一句话兜底 |
| explain_rollup.py（配对/回证/可执行汇总） | 删除脚本 |
| gain_probe.py（正常 vs 退化消融+污染注入） | 删除脚本，gain_evidence.available=false（预算过 50% 降级） |
| trend_anomaly_check.py | 删除，替换为 anomaly_detect.py |

**保留并强化的单一方向**：异常点定位——离群检测脚本机械完成，定位到维度，给阈值与偏离幅度。

## 二、异常检测脚本怎么做（anomaly_detect.py）

1. **阈值事前声明**：result.thresholds = {outlier_z:3.0, jump_rel:0.5, plateau_min_points:3, plateau_tol_rel:0.05}，声明后禁改。
2. **机械检出两类异常**：
   - outlier：|z|>3.0（z 用样本 sd）；对照基线用**中位数**（避免离群点污染基线），偏离幅度 = (值-中位数)/|中位数|。
   - jump：相邻读数 |相对变化|>50%，基线 = 相邻前一读数。
3. **platform 只进背景统计不进 anomalies**：避免把正常平台期当异常（题面明确警告"正常波动被当成异常"会扣分）。
4. **维度定位**：值点带 sample/batch/channel/well/time 键则用键值；否则退回 dataset.dimension + 数组索引。
5. **封顶**：每案例至多 8 个异常，按类型强度（outlier>jump）排序。
6. **模型只配一句话**：possible_cause 由模型填一句话（未定因果），不逐点人工判读、不新增删减。

## 三、交付文件清单

| 文件 | 说明 |
|------|------|
| SKILL.md | 106 行（限额 150），合法 YAML frontmatter，五步流程 |
| scripts/build_skeleton.py | Step 0 落骨架 + skill_marker.json 标志 |
| scripts/anomaly_detect.py | Step 2 离群机械检测（核心） |
| scripts/verify_check.py | Step 4 主校验器（enum/anomaly/detection/contract/structure） |
| scripts/schema_guard.py | 契约守卫 |
| examples/example-case.json | 示意案例（虚构，标注非正式） |
| examples/example-result.json | 示意输出（脚本真实跑出后固化） |
| README.md | 生态 + 最小自检清单 |

合规数字：脚本 4/8，文件 9/50，总体积约 84KB / 2MB，零外部依赖，命令一律 python3，无 symlink。

## 四、真实对照数字（2026-11-22 本机实测，Python 3.13）

| 指标 | 数值 |
|------|------|
| anomaly_detect | 扫描 2 组，检出 3 异常（1 outlier + 2 jump），上报 3 |
| 离群点 AN-01 | values[5]=90.1 MPa，z=3.16 > 3.0，偏差 +76.3%（对照中位数 51.0） |
| 跳变 AN-02 | values[5] 相对前值 52.8 跳升 +70.6% > 50% |
| 跳变 AN-03 | values[7] 相对前值 10.5 跳升 +50.5% > 50% |
| verify_check | verdict=PASS（0 问题） |
| schema_guard | verdict=PASS |
| 四命令退出码 | 全部 0 |

## 五、保命铁纪律落实情况

1. 第 0 步落骨架：build_skeleton.py 首选动作，失败仍有骨架。
2. 失败也交付：脚本全捕获，绝不 crash。
3. 退出码恒 0 看 verdict：verify_check/schema_guard 判据是报告 verdict 非退出码。
4. 预算过半即定稿：增益层降级 available=false，不额外消耗请求。

## 六、诚实边界（不夸大）

- 阈值是保守默认，不冒充 Grubbs/ISO 标准；z 分数小样本偏保守。
- 平台段不作异常上报（只有 outlier/jump 进 anomalies），这是有意取舍，避免误报。
- possible_cause 只有一句话、未定因果；趋势/原因清单/复核/后续只一句话兜底。
- gain_evidence.available=false，不声称有消融对照数字（真实平台白板对照由平台生成）。
- 数值提取用正则/\d，不用 .isalpha() 判汉字。