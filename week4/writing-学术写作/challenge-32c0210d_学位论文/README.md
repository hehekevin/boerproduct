# weekly-skill — 学位论文与长文档写作

「AI文献阅读与学术写作」比赛 · 学术写作赛道 · 学位论文与长文档写作 参赛 Skill（v4 增益可证版）。

把长文档写作的四问——**立得住 / 连得上 / 改得动 / 查得清**——落成机器可核验的产物：
章节规划带论证任务与字数预算、跨章节登记簿（术语·符号·定义·结论）、逐章分批写并写完即回填、
三机检逐条三元组、以及**同输入双臂对照的真实增益证据**。

## 版本说明

- v1 首版评测 55.33（outcome=partial）。诊断：缺强制执行协议、主产物未内嵌 result.json、流程偏重。
- v2（平台 73）：协议置顶（7 条）+ 主产物全文内嵌 + 5 步线性 + 脚本动态定位。
- v3：每步写盘 + 逐章≤1500 字回填 + completeness_check 三元组 + 闸门状态四态枚举。
- **v4（本版）**：①修正挂载路径（`/skills/weekly-skill`，脚本定位用 `find` 稳健写法）②`build_result.py`
  按题面三段语义装配 result.json（目标产物 / 事实与来源映射 / 版本与边界），并输出 `structure` 六项
  （摘要·目录·各章·图表目录·参考文献·致谢）逐项在位状态 ③新增 `gain_ablation.py` 可运行双臂对照实验台，
  产出**真实跑出来的**增益证据 ④`fact_ledger check` 新增「引用了材料中不存在的文献」检测 ⑤**所有校验脚本
  失败路径退出码恒为 0**，发现问题只进报告的 verdict/fail 字段，不中断交付 ⑥README 补齐生态贡献全套。

## 用途与适用条件

- 适用：学位论文、期刊长文、技术报告等**多章节、数万字、需要跨章一致性与可追溯性**的写作任务；
  分批改稿（导师/评审意见逐条落实）；术语与引用统一。
- 不适用：单段短文润色（无跨章结构，机检无对象）；纯公式推导或数据分析（属另一赛道）；材料完全缺失时的内容创作。
- 输入：`/input/case.json`（case_id、output_contract、材料与约束）+ `task.md` + 材料文件（docx/pdf/txt/md/xlsx/…）。
- 输出：`/app/output/` 下 `result.json`（契约全键 + 主产物全文内嵌 + 三机检报告 + gain_evidence + efficiency）、
  `thesis.docx`（可编辑）、`thesis.md`、`previews/`（渲染预览，无渲染器时如实记 no_renderer）。

## 完整调用流程（5 步线性）

0. **读契约落骨架**：读 `/input/case.json` 与题面，抄下 output_contract 全部键名与 case_id，
   **立即**写 `/app/output/result.json` 骨架（全部键 + case_id，未完成填 null，status="partial"）。
1. **材料与台账**：`extract_materials.py --input /input --outdir /app/work/extracted` →
   `fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl`。
2. **规划与写作**：产出 `chapter_plan.jsonl`（每章 ch/title/role/word_budget/evidence/outputs）；
   **全部章节先写最小合格版**，再按字数预算加深高价值章节；每章写完立即回填 `draft_all.json` 与
   `result.json` 的 `deliverable_content`（每章每次响应 ≤1500 字）。
3. **构建与机检**：`docx_build.py` → `fact_ledger.py check` → `cross_check.py` → `completeness_check.py`。
4. **渲染与组装**：`render_preview.py` → `build_result.py`（含 `--gain-evidence`）。
5. **增益证据（建议）**：`gain_ablation.py --case /app/work/gain_case --both --out /app/output/gain_evidence.json`。

脚本定位（优先本 Skill 自己的目录，避免抓到同一 `/skills` 下别的技能的 scripts）：
```bash
SD=$(find /skills -maxdepth 4 -type d -path '*/weekly-skill/scripts' 2>/dev/null | head -1)
SCRIPT_DIR=""
for d in /skills/weekly-skill/scripts ./scripts scripts; do
  if [ -f "$d/build_result.py" ]; then SCRIPT_DIR="$d"; break; fi
done
if [ -z "$SCRIPT_DIR" ]; then
  SCRIPT_DIR=$(find /skills /app -type d -name scripts 2>/dev/null | while read -r d; do [ -f "$d/build_result.py" ] && echo "$d" && break; done)
fi
[ -n "$SCRIPT_DIR" ] || SCRIPT_DIR="./scripts"   # 兜底：相对路径 + 如实登记，不臆造路径

[ -z "$SD" ] && SD=./scripts
```
本 Skill 安装目录为 `/skills/weekly-skill`，包内**不含任何写死安装路径**。

## 关键方法

- **广度优先 + 预算保护**：全部章节先以 300-500 字骨架成文，再加深高价值章。48 次模型请求 / 700 秒即熔断收口。
- **逐章分批写 + 写完即回填**：单次响应 ≤1500 字，写完一章立刻落盘并回填 result.json。规避 16384 token
  截断导致全文丢失（长文档赛道最常见的 0 分原因）。
- **跨章节登记簿**：`registers.jsonl` 四类（term/symbol/definition/conclusion），首次定义即入册，
  `cross_check.py` 检术语别名违规、同符号多义、定义重复、结论失配、图表编号错位。
- **三机检逐条三元组**：`{item, template_value, applied, match}`。`applied` 由脚本从真实产物读出，
  不经模型转述，故不可编造。
- **闸门四态显式**：`enforced / skipped_not_provided / not_found / unreadable`。没跑 ≠ 通过；
  非 `enforced` 的闸门必须在 result.json 写 gate_note「下游不得宣称已核对」。
- **事实台账回证**：`fact_ledger.py check` 抓三类——材料中查不到的数值、材料中不存在的 DOI、
  **正文引用了材料里没有的文献编号**（题面「术语与引用」方向明确列出的失败模式）。
- **失败路径 exit 0**：所有脚本任何异常都被捕获并写入报告，退出码恒 0（`--strict` 仅供本地 CI）。
  交付链永不因校验失败而中断，问题以可枚举清单形式冒泡到 `uncertainty`。
- **增益可证**：`gain_ablation.py` 在**同一份输入**上跑「完整臂」（逐章分批写 + 写完即回填 + 前置件齐备 +
  机检全跑）与「退化臂」（一次性合并成稿 + 无前置件 + 不跑机检 + 受单次响应预算截断），
  用**同一套指标函数**算逐项对照——见下节真实数字。

## 增益证据（本地自建回归用例的真实运行记录）

对照用例：`examples/selftest_case/`（合成材料，明确标注「本地自检用合成数据，非平台正式案例结果」）。
命令：`python3 scripts/gain_ablation.py --case examples/selftest_case --both --out gain_evidence.json --response-chars 900`

| 指标 | 完整臂 skill_full | 退化臂 baseline_ablate | 差值 | 方向 |
|---|---|---|---|---|
| 章节完整率 | **1.0** | 0.4 | +0.6 | 越高越好 |
| 跨章编号一致率 | **1.0** | 1.0 | 0.0 | 越高越好 |
| 参考文献覆盖 | **1.0** | 0.0 | +1.0 | 越高越好 |
| 需人工核对条目数 | **0** | 4 | −4 | 越低越好 |
| 步骤数（成本项） | 12 | 3 | +9 | 成本单列 |

质量总分（三个比率之和 − 待人工核对条目）：full **3.0** vs ablate **−2.6**，差 **+5.6**。
效率侧：full 12 步 / 12 次写盘事件，ablate 3 步 / 3 次写盘事件——多出的步骤换来了上述质量差。

**机制 → 指标映射**（写在 gain_evidence.json 的 `mechanism_to_metric` 字段里，逐条可查）：

| 机制 | 影响的指标 | 为什么 |
|---|---|---|
| 逐章分批写 + 写完即回填 | 章节完整率 | 单次响应预算写不完全文；分批保证每章真实落盘，尾部章节不因截断丢失 |
| 前置件齐备（摘要/目录/参考文献/致谢） | 需人工核对条目数、参考文献覆盖 | 前置件缺失时评审无法定位章节、引用无出处，只能转人工逐项核对 |
| 章节完整性机检 | 需人工核对条目数 | 把缺件/死引用/未回证数值在交付前变成可枚举清单 |
| 图表编号按章 + 正文交叉引用 | 跨章编号一致率 | 编号唯一且被引用，读者可直接定位；无引用编号等价于死引用 |
| 事实台账回证 | 需人工核对条目数 | 未回证数值是最贵的返工来源 |

**边界声明**（`boundaries` 字段）：①本对照只隔离**流程机制**，不隔离模型能力——两臂用同一份输入材料、
同一套指标函数；②指标是离线结构/可核验性度量，**不等于文本语义质量评分**；③退化臂预算由
`--response-chars` 给出（默认 6000），模拟一次性出稿时的截断；④未提供的材料按 `skipped_not_provided`
处理，不按通过计；⑤本记录是**本地自建回归用例**的对照结果，非平台正式案例结果——正式案例用平台固定输入
重跑同一命令即可复现。

## 最小调用示例（示意，非正式案例结果）

```bash
SD=$(find /skills -maxdepth 4 -type d -path '*/weekly-skill/scripts' 2>/dev/null | head -1)
SCRIPT_DIR=""
for d in /skills/weekly-skill/scripts ./scripts scripts; do
  if [ -f "$d/build_result.py" ]; then SCRIPT_DIR="$d"; break; fi
done
if [ -z "$SCRIPT_DIR" ]; then
  SCRIPT_DIR=$(find /skills /app -type d -name scripts 2>/dev/null | while read -r d; do [ -f "$d/build_result.py" ] && echo "$d" && break; done)
fi
[ -n "$SCRIPT_DIR" ] || SCRIPT_DIR="./scripts"   # 兜底：相对路径 + 如实登记，不臆造路径

[ -z "$SD" ] && SD=./scripts
python3 $SD/extract_materials.py --input /input --outdir /app/work/extracted
# → 示意：{"ok":true,"summary":{"total":3,"extracted":3}}
python3 $SD/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
# → 示意：{"ok":true,"facts":214,"by_type":{"number":180,"doi":24,"statistic":10}}
python3 $SD/docx_build.py /app/work/draft_all.json --out-docx /app/output/thesis.docx --out-md /app/output/thesis.md
# → 示意：{"ok":true,"builder":"python-docx","markdown":"/app/output/thesis.md"}
python3 $SD/completeness_check.py --draft /app/output/thesis.md --plan /app/work/chapter_plan.jsonl --out /app/output/completeness_check.json
# → 示意：{"total":27,"fail":0,"verdict":"pass"}
python3 $SD/gain_ablation.py --case /app/work/gain_case --both --out /app/output/gain_evidence.json
# → 示意：{"chapter_completeness_rate":{"full":1.0,"ablate":0.4,"delta":0.6,"better":"full"}}
python3 $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact thesis.docx --artifact-md thesis.md --embed-file /app/output/thesis.md --embed-key deliverable_content \
  --gain-evidence /app/output/gain_evidence.json --status complete
# → 示意：{"ok":true,"contract_fields":7,"missing":[],"keys":24}
```

## 资源清单与复用方式

| 文件 | 用途 | 依赖 |
|---|---|---|
| `SKILL.md` | 执行协议 8 条 + 5 步流程 + 异常处置 + 交付自查清单 | — |
| `scripts/extract_materials.py` | 材料抽取为带 `[SRC:材料号:位置]` 锚点的纯文本 | 纯 stdlib（docx/pdf/xlsx 有预装库则用，无则逐格式降级） |
| `scripts/fact_ledger.py` | build=抽取硬事实台账；check=数值/DOI/引用编号三重回证 | 纯 stdlib |
| `scripts/cross_check.py` | 跨章一致性：术语别名/符号冲突/定义重复/结论失配/编号错位 | 纯 stdlib |
| `scripts/completeness_check.py` | 嵌入完整性与图表交叉引用，逐条三元组 + 闸门四态 | 纯 stdlib |
| `scripts/docx_build.py` | 稿件 JSON → 可编辑 docx + Markdown（两形态输入自动归一） | python-docx → 缺失时 stdlib 兜底 |
| `scripts/render_preview.py` | docx → PDF/PNG 预览，无渲染器如实记 no_renderer | soffice/libreoffice（可选） |
| `scripts/build_result.py` | 按题面三段语义装配 result.json | 纯 stdlib |
| `scripts/gain_ablation.py` | 双臂对照实验台：同输入两臂 + 逐项指标 + 机制映射 + 边界 | 纯 stdlib |
| `templates/checklist.md` | 章节级/交付级/改稿级检查清单（A–F 六组 34 项） | — |
| `templates/registers_template.jsonl` | 术语/符号/定义/结论 登记簿模板（四类字段齐全） | — |
| `templates/references_template.md` | 引用表模板 + evidence_map 建议格式 | — |
| `examples/example_input.json` | 稿件 JSON 形态示意（标注「示意」） | — |
| `examples/selftest_case/` | **可复用测试题集**：合成材料 + 章节草稿 + 登记簿，双臂对照直接跑 | — |

复用方式：整目录拷入技能目录即可（无平台硬编码路径，全部参数化）。`fact_ledger.py` 与
`cross_check.py` 可独立用于任意长文档的事实回证与一致性复核；`completeness_check.py` 可独立用于
任何多章节文档的嵌入完整性检查；`gain_ablation.py` 可独立用于任何「有/无某流程机制」对照实验。
测试题集 `examples/selftest_case/` 可直接改造成新题：换掉 `materials.txt` / `chapters/*.md` /
`registers.jsonl` 即可，`case.json` 的 `required_sections` 控制必需件清单。

## 依赖与配置

- Python 3.8+，**零外部依赖**（全部脚本仅用标准库）；python-docx / PyMuPDF / openpyxl / soffice 若存在则用，
  缺失时逐级降级并**如实记录**（`engine` 字段写清降级路径）。
- 无配置文件、无环境变量、无网络请求、无 CDN 依赖。
- 运行时契约路径：`/input`（输入）、`/app/work`（中间产物）、`/app/output`（交付），均为题面规定，不可改。

## 篇幅上限与已知失败模式

- 篇幅上限：单章每次响应 ≤1500 字；全文建议 ≤12 章 / ≤3 万字（超出时按 `chapter_plan` 拆批并用
  登记簿维持跨章一致，而非加长单章）。
- 已知失败模式与处置：
  | 失败模式 | 检测方式 | 处置 |
  |---|---|---|
  | 单次响应写完全文被截断 | `gain_ablation` 退化臂复现；章节完整率下降 | 协议 3a 分批写 + 写完即回填 |
  | 材料缺失 | 提取清单 `extracted:false` | 该章留缺口说明，登记 material_gaps |
  | 引用了不存在的文献 | `fact_ledger check` 的 `missing_reference_numbers` | 移除引用或列入待人工确认 |
  | 数值无出处 | `fact_ledger check` 的 `unmatched_detail` | 回材料核对或标 [待核]，禁止凭印象保留 |
  | 术语/符号冲突 | `cross_check` 的 term_violations / symbol_conflicts | 选规范写法入册，联动改正文 |
  | 结论前后矛盾 | `cross_check` 的 conclusion_mismatch + 人工比对 | 取更强证据口径，两处联动改，记 conflict |
  | 图表编号错位/死引用 | `completeness_check` B 组 | 重排编号并在正文补引用句 |
  | 扫描件 PDF 无法提取 | `materials_manifest` 的 `extracted:false` | 标记不可提取，转 OCR 或如实报缺口 |
  | 无渲染器 | `render_log.status=no_renderer` | 如实记录，不伪造 PDF/PNG |
  | 文档格式不支持 | `docx_build` 捕获异常并走 stdlib 兜底 | 产出仍可编辑的最小 docx，并记降级原因 |

## 维护信息

- 版本 v4（2026-11-17）；维护者：`bohrium-week3-final / challenge-32c0210d`。
- 上一版 v3（2026-11-16）引入逐章回填与完整性三元组；v4 修挂载路径、补三段语义装配、
  新增双臂对照实验台、统一失败路径 exit 0。
- 回归基线（改动校验口径后必须重跑，期望值不得变）：
  ①正例 `examples/selftest_case` → `completeness_check` total=27/fail=0/verdict=pass，
  `fact_ledger check` unmatched=0/verdict=pass，`cross_check` verdict=pass/types=[];
  ②污染反例（删摘要·目录·参考文献·致谢、删 2 个计划章、注入 99.9 mg/L、引用不存在的 [9]、
  术语别名违规、图表编号错位）→ `completeness_check` fail=8 且逐条报出缺失项，
  `fact_ledger check` unmatched=2 且 `missing_reference_numbers=[9]`，`cross_check` 报出
  term_violations + figure_numbering，**三者退出码均为 0**。
