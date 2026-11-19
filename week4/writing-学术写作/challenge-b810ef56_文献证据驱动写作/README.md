# eviwrite-claimbind — 文献证据驱动写作 Skill

把成稿拆成可判定论断单元，逐条绑定来源与逐字引文（定位到章节/页码/段落），按 A–D 证据等级审计措辞相称性，统一校验器机检逐项可回查，消融双跑 + 污染反例机器判定增益。对应题面四个问题：**找得到**（claims 切分）、**对得上**（evidence_table 逐字回证）、**说得准**（strength_gate 双向把关）、**复得现**（verify_check 逐条机检 + reproduction 命令）。

## 一、用途

从带文献来源的科研材料完成证据驱动写作任务：论断清单—证据表—成稿三段交付，每句有依据的话都能指出依据在哪、依据多强，未确认内容明确标注。

## 二、适用条件

- 输入：`/input/case.json`（含 case_id 与 output_contract）+ `/input/task.md` + 组织方提供的科研材料。
- 材料可为 txt/md/jsonl；PDF 需能读取文本（读不了如实记 uncertainty，不伪造页码）。
- 运行环境：Python 3.8+，仅标准库，零外部依赖。

## 三、调用方式

按 SKILL.md 的 5 步线性流程；核心命令：

```bash
python3 scripts/build_skeleton.py --case /input/case.json --out /app/output/result.json --status in_progress
python3 scripts/claim_split.py --draft /app/output/draft.md --out /app/work/claims.jsonl
python3 scripts/evidence_bind.py --claims /app/work/claims.jsonl --sources /app/work/sources --out /app/work/evidence_table.jsonl
python3 scripts/strength_gate.py --claims /app/work/claims.jsonl --evidence-table /app/work/evidence_table.jsonl --out /app/output/strength_report.json
python3 scripts/verify_check.py --claims /app/work/claims.jsonl --evidence-table /app/work/evidence_table.jsonl --sources /app/work/sources --draft /app/output/draft.md --out /app/output/verify_report.json
python3 scripts/gain_probe.py --result /app/output/result.json --claims /app/work/claims.jsonl --evidence-table /app/work/evidence_table.jsonl --sources /app/work/sources --draft /app/output/draft.md --ablate --write
python3 scripts/build_skeleton.py --case /input/case.json --out /app/output/result.json --assemble ... --status complete
python3 scripts/schema_guard.py --result /app/output/result.json --case /input/case.json --out /app/output/guard_report.json
```

挂载位置：`/skills/weekly-skill`；工作目录 `/app/work`；产出 `/app/output`（主结果 `result.json`）。

## 四、输入输出

| 项 | 内容 |
|---|---|
| 输入 | case.json（case_id + output_contract 全字段）、task.md、来源材料目录 `/app/work/sources`（M01.txt… + manifest.jsonl） |
| 中间产物 | claims.jsonl（论断清单）、evidence_table.jsonl（证据表）、strength_report.json、verify_report.json、guard_report.json |
| 主输出 | `/app/output/result.json`：含 case_id、契约全字段、draft_text、claims、evidence_table、strength_report、verify_report、gain_evidence、efficiency、uncertainty、changelog、status |

## 五、依赖与版本

仅 Python 3.8+ 标准库（argparse/json/os/re/sys/copy/time）。无第三方包、无网络、无 symlinks。

## 六、配置

无必填配置。来源类型经 `/app/work/sources/manifest.jsonl` 声明（原始研究/综述/指南/预印本），未声明默认按原始研究 B 级处理并在不确定性中注明。

## 七、示例

见 `examples/`：example_case.json（合成案例）、example_claims.jsonl、example_evidence_table.jsonl、example_verify_report.json、example_gain_result.json。**全部为示意，非正式案例结果。**

## 八、强度分级口径

| 等级 | 判据 | 正文措辞 |
|---|---|---|
| A | 多篇一致 / 指南共识支撑 | 可用「证实/确立」 |
| B | 单项原始研究 | 「结果表明/显示」，不得「证实」 |
| C | 综述转述 / 二手证据 | 「有综述提示」 |
| D | 预印本、仅摘要、证据缺失 | 必带限定语，禁强断言 |

措辞审计 5 规则：R1 强断言×C/D=overclaim；R2 相关×因果词=causal_overreach；R3 全称词=overgeneralization；R4 未限定=needs_hedge；R5 强证据过度弱化=underclaim（双向把关）。

## 九、限制与失效条件

- 增益以同一校验器 fail_count 差为准，仅在本包规则（5 项机检 + 5 条措辞规则）范围内判定。
- claims 为空 / sources 为空 / 校验器异常时 gain_confirmed=False，不编造增益。
- 来源材料缺失时 verbatim 两臂同 FAIL，差值不构成增益。
- claim_split 依赖句读规范；无标点长段可能整段算一条论断（可手工补切）。
- PDF 无法读取文本时 locator 记 p?（校验器 FAIL 如实），不伪造页码。
- 模型请求数/工具调用数由 Harness 记录，本包 efficiency 只统计可机械复核项。

## 十、维护信息

- 异常处置表与失败兜底见 SKILL.md；所有脚本退出码恒 0，结论照实写 JSON。
- 键归属：build_skeleton 独占契约/主产物键，gain_probe 只写 gain_evidence 与 efficiency，互不覆盖。
- 复现命令内嵌于 result.json 的 reproduction 字段；自检命令见下节。

## 最小可运行自检清单（逐条实测，均 exit 0）

在包根目录（scripts/ 的上一级）执行，`<ST>` 为任一空工作目录、`<IN>` 为含 case.json 的目录、`<SRC>` 为含 M*.txt + manifest.jsonl 的目录、`<DRAFT>` 为成稿文件：

| # | 命令 | 实测结果 |
|---|---|---|
| 1 | `python3 scripts/schema_guard.py --selftest --pkg .` | `selftest=PASS`，exit 0 |
| 2 | `python3 scripts/claim_split.py --selftest` | `selftest=PASS`，exit 0 |
| 3 | `python3 scripts/build_skeleton.py --case <IN>/case.json --out <ST>/result.json --status in_progress` | `mode=skeleton, contract_fields=N`，exit 0 |
| 4 | `python3 scripts/claim_split.py --draft <DRAFT> --out <ST>/claims.jsonl` | `claims_total=4`，exit 0 |
| 5 | `python3 scripts/evidence_bind.py --claims <ST>/claims.jsonl --sources <SRC> --out <ST>/evidence_table.jsonl` | `bound_exact=4`，exit 0 |
| 6 | `python3 scripts/strength_gate.py --claims ... --evidence-table ... --out <ST>/strength_report.json` | `verdict=pass`，exit 0 |
| 7 | `python3 scripts/verify_check.py --claims ... --evidence-table ... --sources <SRC> --draft <DRAFT> --out <ST>/verify_report.json` | `verdict=PASS, fail_count=0`，exit 0 |
| 8 | `python3 scripts/gain_probe.py --result <ST>/result.json --claims ... --evidence-table ... --sources <SRC> --draft <DRAFT> --ablate --write` | `diff=15, sensitivity_check=PASS, gain_confirmed=True`，exit 0 |
| 9 | `python3 scripts/build_skeleton.py --case <IN>/case.json --out <ST>/result.json --assemble ... --status complete` | `contract_filled=8/8`，exit 0 |
| 10 | `python3 scripts/schema_guard.py --result <ST>/result.json --case <IN>/case.json --out <ST>/guard_report.json` | `verdict=PASS`，exit 0 |
| 11 | 任一脚本 `--bogus-flag`（参数错误） | 打印 JSON，exit 0 |
| 12 | 输入文件缺失路径重跑 #4–#7 | 打印 `ok:false` + 说明，exit 0 |

以上 12 条均在提交前实测通过（真实对照数字见 worklog.md）。
