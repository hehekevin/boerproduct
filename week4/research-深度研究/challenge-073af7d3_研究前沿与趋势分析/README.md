# trend-frontier-analyst — 研究前沿与趋势分析 Skill（challenge-073af7d3 · research 赛道）

围绕固定研究问题组织文献记录，交付**可复算**的主题聚类、年度趋势、新兴/成熟/衰退分级与证据绑定的研究空白识别。核心立场：趋势不是关键词热度自述，而是按事前声明口径机械复算、逐字回证的年度分布。

## 1. 用途与定位
把「研究前沿与趋势分析」做成五件可检查的事：主题归属机械可复算、年度计数与增速回证数字、分级只看事前阈值、每个趋势结论绑定逐字证据、空白须有排除证据且趋势不外推。

## 2. 适用条件
- 输入为固定记录集（case.json 提供文献记录 + output_contract），字段为标题/摘要/年份/发表日期/引用数等常规元数据。
- 适合 8–12 年观测窗口、10–200 条记录规模；记录可含缺字段/歧义关键词夹具。
- 不适用：需要数据库实时检索、全文精读、引文图谱（共引/耦合）聚类的场景（见 §9）。

## 3. 调用方式
按 SKILL.md 七步流程线性执行，两个必做脚本动作 + 三个校验脚本动作：
```
Step 0  build_skeleton.py  落骨架 + 记录清单 + 口径模板
Step 1  Agent 事前声明 clustering_policy / trend_policy / extrapolation
Step 2  Agent 逐条判定 items[]
Step 3  trend_engine.py    机械落定 topics/yearly_counts/growth_rate/stage/coverage
Step 4  Agent 写 claims（数字回证）与 gaps（排除证据）
Step 5  gain_probe.py      消融双跑 + 污染反例 → gain_evidence/efficiency
Step 6  verify_check.py + schema_guard.py → 按 verdict 修复至 PASS
```
全部命令使用 `python3`，挂载路径 `/skills/weekly-skill`，产物落 `/app/output/result.json`。

## 4. 依赖与安装
- Python ≥3.8，**仅标准库**（json/os/re/argparse/copy/time/math），零 pip 依赖。
- 无需安装：随 Skill 挂载于 `/skills/weekly-skill/scripts/` 即可运行。
- 本地自测：克隆后直接 `python3 scripts/<脚本>.py --help`。

## 5. 配置与口径声明（事前，禁止事后调整）
所有判定口径集中在两处，判定前写定并同步 `/app/work/trend_policy.json`：
- `result.clustering_policy`：关键词簇（topic_id/label/keywords/representative_seed）、标题归一化（casefold+非字母数字折叠，`\w` 含 CJK，**不用 isalpha**）、匹配顺序（簇声明顺序首个命中）。
- `result.trend_policy`：观测窗口 start_year/end_year、增速公式 `growth_rate=(late_avg-early_avg)/early_avg`（early=[S..mid]，late=[mid+1..E]，mid=(S+E)//2）、分级阈值（默认 emerging≥0.5、declining≤-0.34）。
- `result.extrapolation`：外推边界（默认禁止外推，须登记 rule）。

## 6. 输入输出
- 输入：`/input/case.json` + `task.md`。
- 输出：`/app/output/result.json` = 平台契约五字段（case_id/status/result/claims/uncertainties…）+ 本题业务键（items/topics/gaps/clustering_policy/trend_policy/extrapolation/coverage/…）+ 增益证据（gain_evidence/efficiency/self_check/gates/unbacked_numbers/validator_verdict）。
- 失败路径全部 `exit 0`，结论看报告 `verdict`（PASS/FAIL）而非退出码。

## 7. 示例（示意，非正式答案）
`examples/example-case.json`（19 条虚构文献：忆阻器件 T1、脉冲神经网络 T2、存内计算 T3，2016–2026）与 `examples/example-result.json`（示意输出）。实测链路见 §10。

## 8. 时间窗约定
- 年份口径：优先 `year` 字段，缺则取 `published_date` 前 4 位；年份缺失的条目不进计数并登记 missing_metadata。
- 窗口切片：mid=(S+E)//2，early=[S..mid]，late=[mid+1..E]；边界年（恰为起止年）按 `start_year<=year<=end_year` 判入。
- 引用数不参与趋势判定（只作代表作辅助线索），避免引用刷高干扰趋势口径。

## 9. 边界与不适用
- 不做实时检索与全文精读；结论限于输入记录集。
- 簇词表是先验设定非官方分类：术语漂移依赖词表覆盖度，覆盖不足按未归属登记待复核。
- growth_rate 是窗口两端均值对比，不识别拐点年份；拐点须人工结合 yearly_counts 判断。
- 阈值 0.5/-0.34 为本技能保守设定（非外部标准），调整须事前声明。
- gain_probe 的对照是本校验层正常 vs 退化模式，不冒充平台基础 Agent 白板对照。

## 10. 维护与最小自检清单（本地实测数字）
```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/wk/skel.json --work-dir /tmp/wk   # exit 0，19 条记录
python3 scripts/trend_engine.py --result examples/example-result.json   # exit 0：T1 -0.4 declining / T2 2.0 emerging / T3 -0.2 mature
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --emit-into   # exit 0，PASS，62 检查项
python3 scripts/schema_guard.py --result examples/example-result.json --case examples/example-case.json   # exit 0，PASS
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into --inject-pollution   # exit 0
python3 scripts/verify_check.py --result /nonexistent.json   # exit 0（FAIL 报告，不中断交付）
```
自检实测：污染副本注入 5 项（篡改 growth_rate / 错标 stage / 清空证据 / 拆除空白排除证据 / 清空 claims）→ 正常模式 FAIL 26 处全抓到，退化模式 PASS 0 处（漏检下界）；同输入消融双跑 steps_count 69 vs 7（delta 62）。
维护约定：改阈值/簇词表须同步改 SKILL.md、trend_engine 与 verify_check（三者共用同一实现，口径不一致会被复算抓出）；版本记录写 worklog.md。
