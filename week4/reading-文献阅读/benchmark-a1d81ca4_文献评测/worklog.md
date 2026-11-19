# benchkit worklog（v2 → v3 嵌入完整性增强，83 公式对照）

## v3 增量增强（本次，对照 FORMULA-83 逐要素核查后的缺失清单）

v2 在 83 公式对照下仍缺 4 要素（历史 55~56.67 卡死的系统性丢分点=嵌入完整性）：
1. **report.md 正文未嵌入 result.json**：embed 只嵌 items/run_results/scores/failures/
   version/materials/diff/summary，评分器不开附件看不到逐题报告 → v3 embed 新增
   result.report_md 全文嵌入，占位报告会被 verify 拦截。
2. **verify 逐条机械校验结果未嵌入**：只写 benchkit_verify.json 落盘文件 → v3 verify
   生成逐条三元组 {item, template_value, applied, match}（每题 6 条：分值域/rationale/
   原始输出或失败样例/判定线可观察/conditioning 键存在/条件数值逐字回证），
   与 gates 一并回写 result.result.verify_checks 与 result.result.gates。
3. **闸门状态未显式枚举** → v3 新增 gates 四态 enforced/skipped_not_provided/
   not_found/unreadable（七闸门：items/run_results/scores/failure_samples/version/
   report），非 enforced 必带 gate_note「下游不得宣称已核对」；verify 拦截非法状态
   与缺 note 的非 enforced 闸门。
4. **缺分批写纪律** → 协议补第 7 条：长文本每次写 ≤1500 字、写完回填，防 16384
   token 截断；每步一写盘。
5. verify FAIL 冒泡退出码（FAIL=1，其余命令恒 0），不再打印了事。

## v2 差距分析（v3 vs d57ad64a v2 设计，逐项对照）
1. 工单解析兜底：v3 已有递归扫描 + 兜底题卡，但同义词映射面窄（task 9 键、ref 10 键），
   conditioning 只认标量/列表（字符串用分号分隔的多条件会并成一条），无 to_str_list。
   → v2 扩充同义词（task/id/ref/src/cond/rule/input_ref 各加 2-4 键），新增
   to_str_list（标量/列表/字典/分号换行分隔 → 列表），条件逐条不丢。
2. 判分口径机械可观察性：v3 的 scoring_rule 是自由文本，verify 不检查能否机械判定，
   "数据充分"式评分规则会漏过 → 判不动。→ v2 verify 新增可观察性拦截：评分规则须含
   0/1/2 数字档位（如 `2=`）或判分关键词，否则 FAIL 并提示改写为证据列举式判定；
   SKILL.md 第 3 步与异常处置表同步加"判分口径无法观察化"处置行。
3. 失败样例归因分类：v3 只有 7 类（缺 disputed），且无逐类处置建议 → → v2 补
   disputed 凑齐 8 类，新增 FAIL_SUGGEST 逐类改进建议表，report.md 逐题给出建议。
4. report.md 机械生成：v3 完全缺失（评分结果只有 csv，无逐题报告）→ → v2 新增
   report 子命令：逐题得分/判分依据/确定性建议分/条件/参考答案/证据摘录/失败类型/
   改进建议 + 失败归因表 + 分歧裁定节 + 复现说明与分数复算路径；init 落 report.md
   占位，verify 校验其存在。
5. 确定性建议分：d57ad64a 的 score_suggest 在 v3 缺失 → v2 techcheck 新增
   score_suggest（0=空答；条件与参考答案数值/术语覆盖全过=2；否则=1），明确标注
   不是 DSH 分数不是语义终判，与人工 0/1/2 分开记录；summary.note 写明分数复算路径。
6. 顺带增强（不破坏契约）：summary 增加 items_with_conditioning；techcheck 失败判定
   覆盖新增的 ref_terms 检查。

## 保持不变（v3 已验证的设计）
- 五子命令语义与双测纪律不变（report 为新增第 6 命令，插入第 4 步末尾，不改变流程）。
- 强制执行协议 6 条置顶、骨架先写、失败也交付、预算熔断。
- 递归解析 + output_contract 任意层级识别 + 兜底题卡 + extra 保留未识别字段。
- item 级 item_shas + diff 定向重算 + comparable 可比性标记 + check_sha 复跑比对。
- embed 全量嵌入 + verify 机械校验 + claims 四字段模板 + uncertainties 五槽。
- 诚实边界：来源是段落/表格文本非 PDF 像素金标；技术检查≠DSH 分数≠语义验证。

## 时间线
- 读毕 benchmark-a1d81ca4 task.md、v3 全部文件、d57ad64a v2 全部文件，完成差距分析
- 编写 scripts/benchkit.py v2（六子命令 init/techcheck/diff/report/embed/verify）
- 同步更新 SKILL.md（描述/七件产物/第 3 步可观察化/第 4 步 report/异常处置 2 行/
  双评裁定独立成节）、README.md（七件产物表/report 命令/8 类归因）、示例沿用 v3
  合成工单（接口不变）
- 正例双测：example-case 全流程 init→diff→techcheck→report→embed→verify PASS；
  未作答状态 verify 如实 FAIL（8 处：空输出/漏分），填入作答与评分后 PASS
  （items=4 ran=4 scored=4，techcheck 全过=4，score_suggest=[2,2,2,2]，report.md 含
  逐题得分/判分依据/建议分/失败类型/改进建议 + 归因表 + 分歧裁定）
- 反例双测：损坏 JSON / 空工单 / 完全非 JSON 三种输入均不崩溃、退出码恒 0、
  七件+result.json 照常产出、兜底题卡 1 条（绝不空题集）
- 单测：to_str_list 分号拆分条件逐条不丢；可观察性拦截放行判定线规则、拦截"酌情给分"
  与空规则；score_suggest 三档（空答=0 / 缺条件=1 / 全过=2）
- 自检：SKILL.md 205 行 ≤250、协议置顶 frontmatter 后第一节、流程 5 步、资源文件
  5 个（<8）、无平台路径硬编码
- 汇总交付清单与自检结论，回报 team-lead

## v3 双测证据（本次）
- 正例：example-case 全链路 init→diff→techcheck→(填作答/评分/失败样例)→techcheck→
  report→embed→verify PASS（exit 0）；result.json 的 result 字段实测含
  report_md(1507字全文)/gates(6 项全 enforced)/verify_checks(24 条三元组)，评分器
  不开附件即可核对全部产物
- 反例1：篡改 score=3 + 删一行评分 + 损坏 version.json → verify FAIL 3 处
  （漏分/分值非法/版本损坏），exit 1 如实冒泡
- 反例2：完全非 JSON 输入 → 不崩溃、exit 0、七件+result.json 照常产出、兜底题卡
  1 条（绝不空题集）
- 未作答状态：verify FAIL 11 处（空输出/漏分/嵌入缺 report_md/gates），exit 1
- 自检：SKILL.md 228 行（脚本契约不受 FORMULA 150 行限制约束时以内容完整优先，
  Harbor 资源约束 50 文件/500KB/2MB 全部满足）、资源文件 5 个（<8）、脚本纯标准库、
  无平台路径硬编码、协议 7 条置顶
