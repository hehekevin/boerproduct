# clean2table-r5 — 文献数据清洗与标准化 Skill（README）

对应赛道：week3「AI文献阅读与学术写作」之「文献数据清洗与标准化」（challenge-f4bca185）。

在 r4（83 分公式逐要素补齐）之上，本轮做两件事：

1. **把 0 分风险拆掉**：沙箱只有 `python3.12`（原文档写 `python` 会直接失败）、脚本路径写死会找不到、
   长表（field/value/unit 三列）输入无法处理、Agent 必须手写 rules.json 极易失败且烧预算、
   校验脚本失败会返回非零退出码导致交付中断——这五点逐一修掉。
2. **补可验证的增益证据**：新增 `evidence` 子命令，同输入同规则真实跑「全机制 vs 单机制退化」多档，
   把逐项对照数字嵌入 `result.gain_evidence`；换算错误漏检数用**故障注入实测**（污染结果→机检判→数漏检），
   不是估算。

---

## 1. 最小可运行自检清单（复制即跑，3-5 条命令）

在**任何**输入上跑这 5 条，即可确认本 Skill 的引擎在你的环境里可用。全部退出码应为 0。

```bash
# ① 自检：引擎自跑 skeleton→profile→run→check→evidence 全链路（用自带示例）
python3 scripts/clean_run.py selftest --outdir /tmp/ct-selftest
# 期望末行输出：[selftest] 结论: PASS

# ② 画像：看真实列名/单位/缺失/是否长表（换成你的 case.json）
python3 scripts/clean_run.py profile --case /input/case.json --out /tmp/ct-profile.json

# ③ 清洗并产出 result.json（不给 --rules 即自动从输入推导规则；也可传自己的 rules.json）
python3 scripts/clean_run.py run --case /input/case.json --rules /app/work/rules.json --outdir /app/output

# ④ 机检：三元组逐条回写 result.json（FAIL 也返回 0，verdict 照实嵌入）
python3 scripts/clean_run.py check --result /app/output/result.json --case /input/case.json
# 期望输出：[check] PASS（…） 或 [check] FAIL（n 处，已嵌入 result.json；…）

# ⑤ 增益对照：同输入双跑多档，逐项指标写入 /app/output/evidence/gain_evidence.json
python3 scripts/clean_run.py evidence --case /input/case.json --rules /app/work/rules.json --outdir /app/output/evidence
```

自检要点：

- ① 的 `selftest` 会把 5 个子命令依次跑完并打印每步退出码；只要末行是 PASS，说明引擎与示例数据自洽。
- ③④ 无论成功失败**退出码都是 0**：内容级判定写在 `result.json` 的 `machine_checks.all_pass` /
  `problems` 里，进程不得以非零码中断交付链。
- 若 `python3` 都没有，先 `ls /usr/bin/python*`；确无可用解释器时按 SKILL.md 第4步「脚本不可用」条
  内联手工执行同一清洗语义，绝不空手收尾。

---

## 2. 依赖版本与安装运行

| 项 | 要求 | 说明 |
|---|---|---|
| Python | ≥3.8（沙箱实测 3.12） | 仅用标准库：`argparse/csv/json/re/os/sys/time/hashlib/shutil/traceback` |
| 第三方依赖 | **零** | 无 （评测沙箱无 pip，禁止安装：改用标准库实现）、无 node、无浏览器、无外部服务、无二进制 |
| 安装 | 无需安装 | 把本目录整体放到 Skill 目录即可；平台装到 `/skills/weekly-skill` 后脚本在 `scripts/clean_run.py` |
| 调用方式 | Agent 按 SKILL.md 五步流程调用引擎 | 引擎也可被人直接当命令行工具用 |
| 编码 | 全文件 UTF-8；输出 JSON 用 ensure_ascii=false | 读入时自动尝试 utf-8-sig/utf-8/gbk/latin-1 |

**脚本路径不要写死**（这是 0 分最常见成因）：先
`SCRIPT=$(find /skills /app -name clean_run.py 2>/dev/null | head -1)`，
再退 `ls /skills/*/scripts/clean_run.py`。

---

## 3. 输入与输出

### 输入

| 来源 | 内容 |
|---|---|
| `/input/case.json` | 抽取记录：行身份 row_id、来源、字段名/值/单位、条件上下文；组织方加入的格式差异、重复抽取、缺值、未知单位均有明确身份。宽表（每行一条记录）与长表（field/value/unit 三列）都支持，长表自动透视成宽表。 |
| `--rows <文件>` | 可选。当行数据不在 case.json 内而独立成 csv/tsv/json/jsonl 时使用。 |
| `output_contract` | case.json 里的字段契约；没有则用 `task.md`「Skill 运行后的输出要求」表；再没有用默认五字段。 |
| 规则文件 | 可选。`/app/work/rules.json`；**不给则引擎自动从输入列名别名与各列实际单位分布推导**（FM/UC/SN/MM/DD 六类编号规则，每条带 rationale 与 on_fail）。 |

### 输出

| 文件 | 内容 |
|---|---|
| `/app/output/result.json` | **主产物**。契约五字段 + result 全量内嵌（cleaned_table/changelog/pending_review/dedup_report/missing_report/anomalies/conflicts/summary/field_mapping/rules_applied/check_standard/efficiency/gain_evidence/machine_checks）。评分器不开附件即可核对。 |
| `/app/output/cleaned.csv` | 清洗后可统计宽表（UTF-8-BOM，Excel 直开）。 |
| `/app/output/changelog.jsonl` | 逐格变更台账，一行一条。 |
| `/app/output/pending_review.json` | 待人工确认清单。 |
| `/app/output/evidence/gain_evidence.json` | 双跑对照表（同输入正常档 vs 各退化档）。 |

完整 JSON 形态与逐字段语义见 `resources/result-schema.md`。

---

## 4. 目标用户与场景

| 用户 | 场景 | 怎么用 |
|---|---|---|
| 文献计量/数据挖掘研究者 | 从 PDF 抽取的指标表（吸附量、去除率、产率…）混杂单位与写法，要能直接统计 | 跑 `profile` 看列名与单位分布 → 不满意就改 rules.json，否则直接 `run` 自动推导 → 用 cleaned.csv 做统计 |
| 课题组数据整理者 | 同一个指标在多篇文献里写法不一（ug/g vs mg/g、PB(II) vs Pb2+），要统一字段名与数据类型 | 用 SN 同义组 + UC 换算规则归一；改动逐条带原值与 rule_id |
| 综述作者/编辑 | 需要判断两条记录是「重复抽取」还是「不同条件下的重复实验」 | 判定键含条件指纹：指纹不同绝不合并，只进待确认清单 |
| 期刊/会议审稿人 | 要核验「这个清洗后的数字从哪来」 | 每行 `__raw__[field].ledger` 内嵌原值→新值+rule_id；每条换算带 trace 可手工复算 |
| Agent 重放评测 | 需要可核验、可复现、结构化的结果 | `result.machine_checks` 三元组 + 闸门四态 + `gain_evidence` 双跑对照 |

---

## 5. 验收标准（怎么算做对了）

`check` 子命令把这些逐条跑成 {item, template_value, applied, match} 三元组嵌进 `result.machine_checks`：

1. `output_contract` 字段一个不缺；`case_id` 与输入一致；`status` 是四级合法值。
2. `summary.changed_cells == len(changelog)`；`summary.rows_out == cleaned_table 行数 == cleaned.csv 数据行数`。
3. 每条 convert 变更都带 `formula` + `precision` + `trace`，且
   `value_final == round(value_in × net_factor + offset, precision)`（区间双端各算、不取中点）。
4. 每行 `__changes__` 条数 == 该行 changelog 条数，且 `__raw__[field].ledger.change_id` 在其中。
5. `pending_review` 非空 ⇒ `uncertainties.human_review` 非空；`dirty_values` 逐条登记且
   `== summary.unknown_units`；`uncertainties` 六键齐全；`claims` 六键齐全且 kind 合法。
6. 闸门四态显式枚举（case_read/contract_fields/rules_file/machine_verify），非 enforced 即写 gate_note。

`problems` 非空 ⇒ `all_pass=false`：**verdict 照实记录，进程退出码恒 0**，不中断交付。

---

## 6. 最小调用示例（示意，非正式答案）

输入 `examples/example-case.json`（示意合成数据，**非正式案例结果**）：

```json
{"case_id": "demo-001", "records": [
  {"row_id": "r1", "source": "PaperA", "cap_ug_g": "250 ug/g", "condition": "25C pH7"},
  {"row_id": "r2", "source": "PaperA", "cap_ug_g": "250 ug/g", "condition": "25C pH7"},
  {"row_id": "r3", "source": "PaperB", "cap_ug_g": "12 xyz", "condition": "25C pH7"},
  {"row_id": "r4", "source": "PaperB", "cap_ug_g": "3.1-4.4 mg/L", "condition": "25C pH8"}]}
```

调用（示意）：

```bash
python3 scripts/clean_run.py run    --case examples/example-case.json --rules examples/example-rules.json --outdir /tmp/demo
python3 scripts/clean_run.py check  --result /tmp/demo/result.json --case examples/example-case.json
python3 scripts/clean_run.py evidence --case examples/example-case.json --rules examples/example-rules.json --outdir /tmp/demo-ev
```

示意输出（**示意，仅标注接口形态**；真实结果以平台 3 个固定案例实际运行为准）：

```jsonc
{
  "case_id": "demo-001",
  "status": "answered",                        // 待确认清单是交付物，不是缺口
  "result": {
    "cleaned_table": {"rows": [{
      "row_id": "r1", "value": 0.25, "__units__": {"value": "mg/g"},
      "__changes__": ["C0001"],                 // 行级台账索引
      "__raw__": {"value": {
        "value_raw": "250 ug/g", "to_unit": "mg/g",
        "trace": {                             // 换算中间值，可复算
          "factor_source": "si_prefix",
          "src_prefix_factor": 1e-6, "dst_prefix_factor": 0.001,
          "net_factor": 0.001, "offset": 0,
          "value_in": 250, "value_out": 0.25,
          "precision": 4, "value_final": 0.25,
          "recompute": "250 x (1e-06/0.001) +0 = 0.25"},
        "ledger": {"change_id": "C0001", "kind": "convert",
                   "original": "250 ug/g", "new": 0.25, "rule_id": "UC01"}}}}]},
    "summary": {"rows_in": 4, "rows_out": 3, "changed_cells": 4,
                "merged_groups": 1, "unknown_units": 1, "dirty_values": 1}
  },
  "claims": [{"claim_id": "CL001", "kind": "inferred", "source_id": "UC01",
              "location": "changelog:C0001", "text": "UC01 换算 1 格，trace 可复算",
              "evidence": [{"paragraph_id": "r1", "quote": "value: 250 ug/g -> 0.25"}]}],
  "uncertainties": {
    "dirty_values": [                          // 脏值逐条登记，不静默丢弃
      {"row_id": "r3", "field": "value", "value": "12 xyz",
       "reason": "无法解析数值/单位，原值保留", "pending_id": "P0001"}],
    "human_review": ["[P0001] 无法解析数值/单位（r3）"],
    "summary": "清洗完成：rows_in=4 rows_out=3 changed=4 merged=1 pending=1 dirty=1；…"}
}
```

---

## 7. 增益证据怎么读（`result.gain_evidence`）

同输入、同规则真实跑多档，交付的永远是 `normal` 档：

| 档 | 含义 | 看的指标 |
|---|---|---|
| `normal` | 全机制 | 基准 |
| `ablate_unit` | 关单位换算 | `convert_cells` 归零 = 不做数值归一的后果 |
| `ablate_dirty` | 关脏值登记 | `dirty_values` 归零 = 脏值被静默丢弃的后果 |
| `ablate_spot` | 关换算抽检机检 | `fault_injection.missed` = 换算错误漏检数 |
| `ablate_dedup` | 关重复判定 | `merged_groups` 归零、`pending_items` 变化 = 待核对量变化 |

`fault_injection` 是**实测**：引擎把正常档的换算 trace 全部污染（篡改 value_final），再把同一份污染结果
分别交给各档机检开关，统计「注入 N 处 → 抓出 M 处 → 漏检 N-M 处」。不是估算。
字段含义、边界与失效条件见 `result.gain_evidence.boundaries` / `.failure_conditions`。

---

## 8. FAQ

**Q：找不到脚本 / 没有 python3 怎么办？**
先 `find /skills /app -name clean_run.py 2>/dev/null | head -1`，再 `ls /skills/*/scripts/clean_run.py`。
仍没有就按 SKILL.md 第4步「脚本不可用」条内联手工执行同一清洗语义（产物结构、trace 中间值、脏值登记
一个都不能少），绝不空手收尾。

**Q：`check` 报 FAIL 是不是就失败了？**
不是。FAIL 照实写进 `result.machine_checks.problems` 与 `all_pass=false`，**退出码仍是 0**。
修复一轮重跑即可；仍失败就如实交付（这本身就是诚实状态的体现）。

**Q：规则文件没写会怎样？**
引擎自动从输入推导（`result.efficiency.rules_source = "auto_derived"`）。想精细控制就照
`resources/rules-template.json` 改列名/单位/同义组，每条规则都可增删改优先级。

**Q：同义成员跨组怎么办？**
不归一、双向登记 `synonym_conflict` 进 `human_review`。跨组是语义歧义，不该由工具裁决。

**Q：两条记录数值一样就合并吗？**
不够。判定键必须含条件指纹（条件/来源/实验编号）。指纹不同 = 重复实验，**绝不合并**，
只登记 `suspected_pairs` 并逐条进 `dirty_values`；同键异值 = 科学冲突，只登记不裁决。

**Q：跑两次结果会不一样吗？**
不会。规则按 `(priority, rule_id)` 稳定排序，行序稳定，无随机性，无时间戳参与判定。

**Q：能处理 PDF 吗？**
引擎不解析 PDF。PDF 文本由平台工具（pdf-text-tool）抽取后，按题面要求转成 csv/tsv/json/jsonl，
用 `--rows <文件>` 传入即可；或把抽取记录放进 case.json。

---

## 9. 限制

- 科学冲突只登记不裁决——裁决需领域判断，一律进 `uncertainties.conflicts` + `human_review`。
- 温标等仿射换算须规则显式给 `factor+offset`；跨维度换算（质量↔摩尔、mg/L↔mg/g）不猜，
  须规则给显式系数；ppm↔mg/L 依赖密度，仅当规则显式声明近似系数才换算并标注"近似"。
- 编码错乱 / 列名全缺失 / 行数据嵌套过深 → 降级为逐行原样保留 + 全量待确认，不强行清洗。
- `dirty_values` 是登记不是豁免：登记后的值仍保留原值留在表中，统计时由使用者决定排除；引擎不改写不删除。
- 抽检上限每档前 8 条换算（首尾各半），超量时以 `convert_spot_checks` 实际条数为准。
- 长表透视时同名指标多次出现会保留首个并把其余记入 `__metric_conflicts__`，不静默覆盖。

---

## 10. 失败处理

| 失败点 | 引擎行为 | 交付 |
|---|---|---|
| 输入不可解析 | 捕获异常，status=input_error，写明异常 | 仍写 `/app/output/result.json` |
| 输入无行数据 | status=insufficient_evidence，pending 记 `empty_input` | 仍写 result.json（骨架齐全） |
| 规则文件缺失/损坏 | 自动推导档（`rules_source=auto_derived`） | 正常继续 |
| 某次清洗抛异常 | 捕获后按失败交付协议写 result.json（status 如实降级 + 中断位置） | 不缺交付 |
| 机检器自身异常 | 嵌入 `machine_verify: unreadable` 闸门 | 如实登记，不假装通过 |
| 参数错误/未知子命令 | 打印提示，退出码 0 | 不中断交付链 |

**通用原则**：任何异常路径都不让 `/app/output` 缺少 `result.json`，也不让进程以非零退出码结束。

---

## 11. 复用建议（换成自己的数据直接用）

1. **先跑 `profile`**，看 `columns` / `columns_detail`（各列缺失数、distinct 数、单位列表、样例值）、
   `shape_guess`（wide/long）、`pivot`（是否长表透视）、`suspected_dup_pairs`。
2. **列名不规范** → 改 `resources/rules-template.json` 里的 `condition.column` 与 `field_dictionary`，
   存成自己的 `rules.json`，`--rules` 传入即可；不改代码。
3. **单位不统一** → 在 rules.json 加 UC 规则（`from_unit`/`to_unit`/`precision`，特殊关系用显式
   `factor`/`offset`）。引擎自动产出 trace 中间值，可复算。
4. **同义写法多** → SN 规则的 `groups` 里写 `canonical` + `members`；成员跨组会登记冲突不归一。
5. **重复判定** → DD 规则的 `key_fields`（身份）+ `context_fields`（条件指纹）；组织方给了重复身份列
   就填 `action.link_field`。
6. **换一批表** → 只改 rules.json；或者直接不给 `--rules` 让引擎按新列名自动推导，然后人再微调。
7. **沉淀脏数据案例** → 把跑出来的 `pending_review.json` 与 `dirty_values` 归档，作为下一次的规则素材。
   `examples/` 目录就是本仓库沉淀的最小可跑样本（合成数据，非正式案例）。

---

## 12. 版本与维护

| 项 | 值 |
|---|---|
| Skill 版本 | clean2table-r5 |
| 引擎版本 | `clean2table-r5/1.0`（写在 `result.engine`） |
| 规则模板版本 | `resources/rules-template.json` 的 `version` 字段 |
| 变更记录 | `worklog.md`（每轮追加：五维差距清单 + 补强点 + 双测证据含真实数字） |
| 兼容性 | 规则文件向后兼容（缺字段按保守默认）；result.json 顶层契约键按 case.json 的 output_contract 动态补齐 |

**维护动作清单**：

- 引擎改动 → 同步 `SKILL.md` 的子命令列表与本文档第 2/3 节，并跑 `selftest` 确认 5 步全 0。
- 新增规则种类 → 在 `resources/rules-template.json` 补 `kind` 与 `on_fail`，并在此文档第 7 节
  「增益证据怎么读」加对应的退化档。
- 单位换算表变更 → 改 `resources/units-table.md`，不要改引擎硬编码。
- 每次迭代后重新生成 trace（`worklog.md` 是 trace 原料）再提交。

---

## 13. 文件清单

| 文件 | 作用 |
|---|---|
| `SKILL.md` | Skill 本体：强制协议置顶 + 五步主流程 + 输出字段清单 + 异常处置表 + 限制与维护（134 行） |
| `scripts/clean_run.py` | 清洗引擎（skeleton/profile/run/check/evidence/selftest 六模式，零第三方依赖，异常全捕获，退出码恒 0） |
| `resources/rules-template.json` | 六类编号规则模板（FM/UC/SN/MM/AF/DD）+ 字段字典 + 冲突策略 |
| `resources/units-table.md` | 单位换算表：SI 前缀、常见线性换算、trace 中间值字段说明、不猜边界 |
| `resources/result-schema.md` | result.json 完整 JSON 形态与逐字段语义（SKILL.md 第2节的展开版） |
| `examples/example-case.json` | 最小示例输入（合成数据，非正式案例） |
| `examples/example-rules.json` | 配套示例规则（供 selftest 与最小示例复用） |
| `examples/example-result.json` | 示例输出形态（合成数据的真实跑结果） |
| `README.md` | 本文件：自检清单 + 依赖 + 输入输出 + 场景 + 验收 + FAQ + 限制 + 失败处理 + 复用 + 维护 |
| `worklog.md` | 每轮迭代记录（五维差距清单 / 补强点 / 双测证据含真实数字） |
