# paper-fact-citation-audit — 论文事实一致性与引用支持审查 Skill

针对 Bohrium 产品赛第 4 周「学术审查」赛道「论文质量审查」(challenge-0999879e)
的参赛 Skill。**精简版**：只做两个分面——`fact_check`（事实一致性与数字自洽）+
`citation_support`（引用支持），砍掉方法设计/统计报告/论证链/学术规范四分面，
广度让位于深度，换取这两个分面的查全率与低误报。

## 1. 用途与适用条件

给定一篇固定稿件与审查要求，**只精读摘要 + 结果章节 + 参考文献列表扫编号**，
产出可定位到句的问题清单，聚焦两类缺陷：

1. **数字前后矛盾**（fact_check）：摘要 vs 结果 vs 图表（或方法句）对同一量给出
   不同值，或术语/结论前后漂移。
2. **引用不支持论断**（citation_support）：正文引用某文献佐证的论断，与该文献
   在参考文献列表里的主站错配或对象错位。

每条 finding 带：`quote` 逐字摘录 + `location` 章节句位 + `severity` 三级
（critical/major/minor，判定前声明）+ `category`（fact_error/citation_mismatch/
insufficient_evidence/suggestion）+ 修改建议。**宁少勿滥**：只报证据最强的
高置信问题，findings 规模 6-15 条，超过 15 条即停。

**明确不查**：方法设计、统计报告、论证链、学术规范四类问题（有意取舍，换取
目标分面深度）。不查重、不润色改写、不做外部文献检索。

## 2. 输入 / 输出

- 输入：`/input/case.json`（稿件 + 审查要求 + output_contract）、`task.md`。
- 输出：`/app/output/result.json`，顶层含 output_contract 全部字段 + 业务键；
  `result.findings[]` 为问题清单；`verdict` ∈ audited/partially_audited/
  not_audited/cannot_verify；`run_status`/`uncertainties` 如实记录。

## 3. 调用方式（按 Step 线性推进）

```bash
# Step 0 落骨架（必做，退出码恒 0）
python3 /skills/weekly-skill/scripts/build_skeleton.py --case /input/case.json \
  --input-root /input --out /app/output/result.json --work-dir /app/work
# Step 1-2 由 Agent 精读摘要+结果，回填 severity_rubric 与 findings（6-15 条）
# Step 3 自检（必做，退出码恒 0，判据看 verdict）
python3 /skills/weekly-skill/scripts/verify_check.py --result /app/output/result.json \
  --case /input/case.json --out /app/work/verify_check.json --emit-into
# Step 4 增益对照（可选：累计请求 ≥32 即跳过）
python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json \
  --case /input/case.json --work-dir /app/work --emit-into
```

**脚本定位**：以技能根 `SKILL.md` 为标志文件做校验式命中（build_skeleton 落盘）。
挂载路径 `/skills/weekly-skill`。零外部依赖，命令一律 `python3`。

## 4. 关键方法

- **两分面深度审查**：审查范围收敛到摘要+结果+参考文献，减少通读与漏查一半。
- **引文逐字回证**：`verify_check.py` 将每条 confirmed 的 quote 做空白归一化后
  子串回证于稿件原文（引文不在原文 = 定位失据 = FAIL）。
- **严重度口径事前声明**：三级判据在首次判定前写定并禁止调整；机械映射
  suggestion⇒minor、fact_error⇒critical/major。
- **预算保护**：协议第 4 条——模型请求超 32 次（50%）或运行超 450 秒即用现有
  结果定稿；gain_probe 的 --used-requests 超阈值直接写 available=false 跳过。
- **失败也交付**：所有脚本退出码恒 0，失败以 verdict/problems 表示，骨架先落盘。

## 5. 适用场景 / 限制

- 适用：投稿前自查、审稿助理，把"摘要、结果、引用哪里有硬伤"变成可交办条目。
- 限制：只审两分面，四类结构/方法/统计/规范问题有意不查；引用支持仅对照稿件
  自带参考文献的标题/摘要主张，不做外部检索，读不到文献主张标 pending；
  引文回证是"逐字出现"的机械下界，不等于被引文献实际主张的语义核对。

## 6. 失败处理与自查

- 失败/中断：仍写可解析 result.json（status=partial，注明中断点）。
- 异常场景处置见 SKILL.md「异常处置」表（稿件解析失败→cannot_verify；图表不可读→
  clearances 豁免；文献缺失→pending + uncertainties；超长→unchecked 登记）。

## 7. 依赖与安装

零第三方依赖，仅 Python 3 标准库（argparse/json/os/re/sys/time/copy/math）。
无需 pip install。本仓库文件数为：`SKILL.md` + 3 个脚本 + `README.md` +
`worklog.md` + `examples/`（2 个合成示例）。

## 8. 示例（示意，非正式答案）

```bash
python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk
python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json
python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into
```

## 9. 维护信息

版本 v1（2026-11-22）。范围收敛、findings 规模上限、脚本职责与真实对照数字见
`worklog.md`。正式测试案例、白板与测评结果由平台提供，本仓库不预置答案。

## 10. 最小自检清单

在本地对合成案例逐条实测，全部应 exit 0（脚本退出码恒 0，判据看报告 verdict）：

| # | 检查项 | 命令（预期 exit 0） |
|---|--------|---------------------|
| 1 | 三脚本语法通过 | `python3 -m py_compile scripts/*.py` |
| 2 | 骨架落盘 + 标志命中 | `python3 scripts/build_skeleton.py --case examples/example-case.json --input-root examples --out /tmp/skel.json --work-dir /tmp/wk` |
| 3 | 校验器对示意结果 PASS | `python3 scripts/verify_check.py --result examples/example-result.json --case examples/example-case.json --out /tmp/vc.json` |
| 4 | 增益探针跑通 | `python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --emit-into` |
| 5 | 污染反例正常模式抓到 | `python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --inject-pollution`（stdout 显示 pollution_caught=True） |
| 6 | 预算过半跳过增益 | `python3 scripts/gain_probe.py --result examples/example-result.json --case examples/example-case.json --work-dir /tmp/wk --used-requests 40`（stdout 显示 available=false） |
| 7 | 失败也交付 | 删除 /tmp/skel.json 后重跑 `verify_check.py --result /tmp/skel.json ...`，应打印 FAIL 且 exit 0 |

注：命令一次性跑通后 stdout 出现 `[verify_check] PASS` 与 `[gain_probe] ... pollution_caught=True` 即为自检通过。