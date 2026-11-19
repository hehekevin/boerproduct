# worklog — challenge-b810ef56（w9-wr2）

日期：2026-11-19。包名：eviwrite-claimbind。方向：文献证据驱动写作（论断—来源关联 + 证据强度 + 不确定性表达）。

## 改动文件清单（submission/ 内共 15 个文件）

| 文件 | 说明 |
|---|---|
| SKILL.md | 137 行（≤150），合法 frontmatter（name/description） |
| README.md | 生态十项 + 12 条最小自检清单（逐条实测 exit 0） |
| worklog.md | 本文件：真实对照数字 + 诚实边界 |
| scripts/ 共 7 个 | build_skeleton / claim_split / evidence_bind / strength_gate / verify_check / schema_guard / gain_probe（≤8 上限内，全标准库） |
| examples/ 共 5 个 | example_case / example_claims / example_evidence_table / example_verify_report / example_gain_result（均标注「示意，非正式案例」） |

## 真实对照数字（2026-11-19 本地实跑，Python 3.13.14）

合成自测案例：3 份来源（M01 RCT 120 人 / M02 队列 80 人 / M03 综述），draft.md 4 句成稿。

| 环节 | 实测值 |
|---|---|
| claim_split | claims_total=4（numeric 2 / factual 1 / interpretive 1） |
| evidence_bind | bound_exact=4 / bound_none=0 |
| strength_gate | violations=0, verdict=pass；grade_counts B=3 C=1 |
| verify_check（技能臂） | fail_count=0, verdict=PASS（bound/verbatim/locator/in_draft/wording 全过） |
| gain_probe 消融 | **arm_skill FAIL=0 vs arm_base FAIL=15，diff=15**（bound 4 / verbatim 4 / locator 4 / wording 3）；gain_confirmed=True |
| 污染反例（副本注入 2 条：编造 quote+假定位 M99、相关写因果） | arm_polluted FAIL=6, verdict=FAIL → **sensitivity_check=PASS**（判据灵敏，非逢检必过） |
| schema_guard | verdict=PASS（8/8 契约字段、case_id、三桶、uncertainty 齐备） |
| --selftest | PASS（7 脚本 + frontmatter + ≤150 行 + examples 免责声明） |

## 失败路径 exit 0 实测（硬约束 4）

| 场景 | 结果 |
|---|---|
| 7 个脚本各传 `--bogus-flag` | 全部打印 JSON、exit=0 |
| draft/claims/sources/result 缺失 | `ok:false` + 说明，exit=0 |
| schema_guard --selftest 指向无 SKILL.md 目录 | `selftest=FAIL`（结论照实），exit=0 |
| gain_probe 材料缺失 | `gain_confirmed=False` 照实写入，exit=0 |

## 过程中修掉的 bug

1. claim_split 句界正则：中文句号后无空格未切句（claims_total 1→4）。
2. 定位标记（M01:p3）被 NUM_RE 误提为论断数值（分类污染）；分类前剥离定位标记。
3. build_skeleton：契约字段名与 uncertainty/changelog 撞名时 setdefault([]) 不生效导致骨架阶段 uncertainty=None——改为判 None 后置 []。
4. argparse 错误退出码 2 → 全部 7 脚本注入 _ArgParser.error() 打印 JSON 后 exit 0。

## 诚实边界

- 上述数字来自**合成自测案例**（本地 _selftest/），非组织方正式案例；正式运行数字以平台 trace 为准。
- 增益判定只在包内规则范围（5 项机检 + 5 条措辞规则）内成立；措辞本已合规的稿子 wording 维度两臂差为 0。
- evidence_bind 匹配是数字一致 + 字面覆盖的机械策略，语序大改的同义转写可能 match=none——此时按流程回读来源改稿或标 [待核]，不会静默编造。
- efficiency 只统计可机械复核项（manual_review 削减量）；模型请求数/工具调用数留给 Harness 记录，不冒充。
- PDF 直读、OCR、docx 渲染不在本包范围内（题面允许聚焦一个具体问题）；locator 锚点依赖材料 txt 化时保留 [SRC:...] 标注。
