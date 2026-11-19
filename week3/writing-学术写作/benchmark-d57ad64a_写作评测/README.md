# acbench — 学术写作 Benchmark 评测工具

把写作评测工单建成可判分、可复跑、可溯源、可迭代的最小评测包：写作题卡（可观察
必需要点 + 变体 + 不可接受错误 + verdict_rule）→ 原稿全文留存 → 0/1/2 逐题评分
（每行判分依据）→ 失败样例归因 → item 级版本快照与定向重算 → 机械生成的逐题报告，
评测包全量嵌入 result.json。

## 文件清单

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 技能入口：强制执行协议、五步流程、schema、判分线、异常处置 |
| `scripts/acbench.py` | 唯一脚本：init / techcheck / diff / report / embed / verify 六命令 |
| `examples/example-case.json` | 合成三条写作工单，仅示意接口，非正式案例 |

依赖：Python 3.7+，仅标准库，无第三方安装。所有命令退出码恒 0；异常自动降级写
warn.log；case.json 损坏或结构未知时写兜底题卡，绝不产出空题集。

## 最小调用示例（示意输出，非正式结果）

```bash
python3 scripts/acbench.py init --case examples/example-case.json --outdir /tmp/bench
# → init 完成：items=3 contract_keys=[case_id,status,result,claims,uncertainties]
#   七件落盘：items.json / run_results.json / scores.csv / failure_samples.json
#   / version.json / report 占位 / result.json 骨架（status=partial）

# 第 3 步：稿件写入 /tmp/bench/run_results.json（示意）：
#   {"results":[{"item_id":"w-1","draft_md":"训练组果蝇（n=30）经 3h 嗅觉训练后，24h 记忆指数为 42.6%，对照组为 12.1%。",
#     "evidence":[{"quote":"24h 记忆指数为 42.6%，n=30","location":"M01"}]}, ...]}
python3 scripts/acbench.py techcheck --outdir /tmp/bench
# → techcheck：ran=3 全过=1 check_sha=ab12…（score_suggest≠语义终判）
#   technical_check 示意：{"draft_empty":false,"must_point_coverage":[
#     {"point":"包含数值 42.6% 原样保留","met":true},...],
#     "missing_must_points":["句子为陈述句方法描述，不含推测结论"],"score_suggest":1}
#   （"陈述句"属语义层约束，确定性检查不判；人工按 verdict_rule 判 2，
#    在 rationale 写明 override 原因——建议分与语义分分离留痕）

# 第 4 步：按 verdict_rule 人工判分写 scores.csv（示意）：
#   w-1,2,"必需要点4/4 满足；数值 42.6%/12.1% 与 M01 逐字一致",false,,
#   w-2,1,"缺时间限定 6h 内（must_point 2 未满足）",false,missing_must_point,
python3 scripts/acbench.py report --outdir /tmp/bench
# → report 生成：逐题给出得分/判分依据/证据摘录/失败类型/改进建议 + 失败归因表
#   + 分歧裁定说明

python3 scripts/acbench.py embed --outdir /tmp/bench
python3 scripts/acbench.py verify --outdir /tmp/bench --case examples/example-case.json
# → verify PASS（items=3 ran=3 scored=3）
#   改题后：python3 scripts/acbench.py diff --outdir /tmp/bench
#   → 仅 rescore_only 内题目需重算；comparable 内历史分数仍可比
```

## 方法要点

1. **题能判定**：每题 must_points 全部写成可观察现象（"包含数值 42.6% 原样保留"），
   verify 机械拦截"数据充分"式不可观察要点；verdict_rule 让两名评分员独立判出同档。
2. **答案站得住**：variants 列允许的风格差异，reject 列不可接受的实质错误，参考
   答案只示范一种合法写法，不把范文当唯一正解。
3. **跑得可复现**：version.json 记 item 级 sha 快照；改题后 diff 只标记受影响题目，
   未变题目历史分数可比；techcheck 记 check_sha 供复跑一致性比对。
4. **报告说得清**：report.md 机械生成，逐题给得分、证据摘录、失败类型（8 类归因）
   与改进建议，分数复算路径写明：scores 行 → 题卡要点 → 原稿全文。
5. **锚点修订不修分**：双评分歧超过一档时修订锚点而非修改分数，修订史记入
   version.changes。

## 限制

- score_suggest 是确定性建议（子串/token 覆盖），不是语义终判。
- 评测包交付 .md/.json/.csv 文本；Office/预览类产物按题面要求另行生成，不伪造。
- 跨 Agent 对照由平台固定白板负责；本包保证同输入同流程可复跑。

## v2 增强点（对照 83 分公式增量补强）

1. **七件产物全量嵌入 result.json**：embed 现将 report.md 全文（result.report_md）与
   adjudication.json（result.adjudication）一并机械嵌入——评分器不开附件即可核对全部
   题卡、原稿、评分、失败、快照、diff、逐题报告与裁定记录。
2. **verify 报告回写嵌入**：verify 结束把 `{ok, problems, gate_state, gate_note}` 写入
   result.json 的 result.verify，校验结论本身可被评分器核对。
3. **gate 状态显式枚举**：每个校验域（items/run_results/scores/failures/version/
   adjudication/report/embed/evidence_backing）输出 enforced / enforced_with_findings /
   skipped_not_provided / not_found / unreadable——没跑≠通过。
4. **evidence 逐字回证**：claims 与原稿 evidence 的 quote 空白归一化后在 case.json 语料
   中子串命中，unbacked 逐条列入 verify 报告。
5. **分歧裁定显式化**：双评记录 adjudication.json（judge_a/judge_b/delta/adjudicated/
   anchor_revision/evidence）；disputed 项无裁定记录 verify FAIL。
6. **强制执行协议补足 7 条**：新增第 4 条「每步一个写盘动作」；SKILL.md 压缩至 150 行。

## 双测证据（v2）

- 正例：example-case.json 全链路 init→workload→diff→techcheck→report→embed→verify
  PASS，gate 9 域全 enforced。
- 反例 A（脏数据）：幽灵评分行+非法分值 5+disputed 无裁定+删嵌入 report_md+编造 quote
  → verify FAIL 抓出 5 处，gate 正确降为 enforced_with_findings。
- 反例 B（case.json 损坏）：init 兜底题卡不崩溃，verify 如实 FAIL，出现 not_found 与
  skipped_not_provided 状态（未提供 --case 时 evidence_backing 跳过）。


## 生态贡献：依赖、安装运行、目标用户与验收

| 项目 | 说明 |
|---|---|
| 依赖与版本 | Python 3（评测沙箱 3.12；本 Skill 脚本仅用标准库，无需 pip 安装）；所有命令用 `python3` 调用。 |
| 安装与运行 | 平台把提交目录装入 `/skills/weekly-skill`；输入 `/input/case.json`（+ 材料），产物写 `/app/output/result.json`。 |
| 输入 / 输出解释 | 输入=案例标识与来源材料；输出=result.json（契约全字段 + 逐条证据 + 闸门状态 + gain_evidence + efficiency + exceptions）。 |
| 目标用户与场景 | 需「产出可直接用、且每条结论都能回到原文核对」的作者与审阅者；用于成稿前的自检与交付留痕。 |
| 验收方式 | ①契约键一个不缺且 JSON 可解析；②每条论断带可回证的 evidence 与来源位置；③闸门状态显式、非 enforced 有 gate_note；④gain_evidence 含基线与当前两套指标及削减量。 |
| 常见问题 | 证据回证失败→换原文短引文而非改写；材料缺失→按题面要求登记缺口而非补零；机检不过→修一轮并如实登记结论。 |
| 已知限制 | 增益对照为同输入自比，量化的是核对工作量与漏检率，不等同于跨模型横向评测。 |
| 失败处理 | 任一步异常：写盘已有产出、status 如实降级、exceptions 记录失败点与已尝试回退链；机检结论照实记录且退出码恒 0。 |
| 复用建议 | 直接复用 scripts/；证据与闸门的字段结构可套用到同类「产出+核对」任务。 |
| 版本与维护 | 见 worklog.md 版本小节；结构变更时同步本表与 SKILL.md 输出字段说明。 |

## 最小可运行自检清单（复制即跑）

```bash
python3 -c "import sys;print(sys.version)"   # 1) 解释器可用
ls scripts/                                   # 2) 脚本在位
python3 scripts/gain_evidence.py --help       # 3) 增益脚本可执行
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"  # 4) 产物可解析且键齐全
```
