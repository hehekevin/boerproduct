# acwrite-revision-client — 学术写作修订客户端 Skill（v2）

> Bohrium 产品赛第 3 周「学术写作」赛道 `challenge-7b09c079` 参赛 Skill。
> 一句话价值：把「接收稿件—按指令修改—保留修订—导出可编辑文档」做成一个**可被 Agent 调用、
> 可被他人逐条复核**的闭环，并把「加载 Skill 到底带来多少增益」变成脚本实测出来的数字。

## 1. 用途与适用条件

给定**原稿 + 修改指令清单**，产出逐条可追溯、可逐条接受/拒绝、可继续编辑的修订稿与交互客户端。

| 能力 | 落地方式 | 对应题面关切 |
|---|---|---|
| **改得准** | 段落锚点索引（pid 全程不重编）+ 外科手术式改动，只替换目标单元 | AI 修改 |
| **改得可追溯** | 每处改动 = `pid + locator + before 逐字 + after + rationale + level`，机械挂成 claim 证据链 | 修订追踪 |
| **格式不塌** | 引用编号联动重排、标题层级/表格/题注保真、导出前机械计数格式塌陷 | 引用协作 / 文档导出 |
| **交付可用** | revised.docx + revised.md + diff.md + versions.jsonl + 单文件交互客户端（逐条裁决 + 按裁决导出） | 富文本编辑 / 版本管理 |

**不适用**：从零生成论文（无原稿）、纯排版模板任务、需要真实投稿系统回写的场景。

## 2. 目标用户与典型场景

| 角色 | 场景 | 得到什么 |
|---|---|---|
| 论文作者 / 合作者 | 导师给一份逐条修改意见，要知道自己改了哪里、依据是什么 | 修订稿 + 逐条 diff + 依据 + 可裁决的客户端 |
| 期刊编辑 / 审稿人 | 拿到作者改稿，要核对改动是否落在指定位置、是否越权 | pid 锚点 + before/after 逐字对照 + claims 证据链 |
| 科研工程师 / 工具开发者 | 搭自己的"稿件修订代理"，需要一套可复用的锚点-台账-导出骨架 | 8 个纯标准库脚本 + 结构化台账契约 |
| 教学 / 培训 | 演示"外科手术式修订 vs 整段重写"的差别 | gain_evidence 同输入 A/B 对照数字 |

## 3. 依赖与版本

| 项 | 要求 |
|---|---|
| Python | **3.8+**，只用标准库（`json/os/re/sys/argparse/difflib/subprocess/zipfile`） |
| 第三方依赖 | **零**。无 pip install、无 CDN、无外链；客户端 HTML 全内联，浏览器直接打开即用 |
| 操作系统 | Linux / macOS / Windows 均可（路径全部 argparse 参数化） |
| 体积 | 整包 < 400 KB；8 个脚本 + 4 个文档 + 5 个合成夹具文件（远低于 50 文件 / 2 MB 上限） |
| 可选外部工具 | `python-docx`（缺失时自动降级为 stdlib 最小 docx 写入器）；`soffice/libreoffice`（缺失时如实记 `no_renderer`，**不伪造预览**） |

## 4. 安装与运行

**安装**：把 `submission/` 挂到平台约定的技能路径（本赛题约定 `/skills/weekly-skill`），无需任何安装步骤。

```bash
S=$(ls -d /skills/weekly-skill/scripts ./scripts 2>/dev/null | head -1)

# 第 1 步：抄契约 + 落骨架（第一个写盘动作）
python "$S/extract_materials.py" --input /input --outdir /app/work/extracted
python "$S/build_result.py" --init --case /input/case.json --out /app/output/result.json
# 第 2-4 步（模型调用）：structure.json → instructions.jsonl → edits.jsonl，详见 SKILL.md
# 第 5 步：导出修订稿 + 渲染预览 + 机械生成 diff/versions
python "$S/docx_build.py" /app/work/revised_draft.json --out-docx /app/output/revised.docx --out-md /app/output/revised.md
python "$S/render_preview.py" --src /app/output/revised.docx --outdir /app/output/previews
python "$S/build_result.py" --diff-from-edits --edits /app/work/edits.jsonl --out-diff /app/output/diff.md --out-versions /app/output/versions.jsonl
# 第 6 步：claims 机械挂链 + 生成并嵌入交互客户端
python "$S/build_result.py" --claims-from-edits --edits /app/work/edits.jsonl --result /app/output/result.json
python "$S/export_client.py" --case /input/case.json --structure /app/work/structure.json --edits /app/work/edits.jsonl --result /app/output/result.json --out /app/output/revision_client.html --embed-result
# 第 7 步：增益对照（真实数字回填）+ 终局机械自检
python "$S/gain_eval.py" --structure /app/work/structure.json --edits /app/work/edits.jsonl --draft /app/work/revised_draft.json --revised /app/output/revised.md --result /app/output/result.json --out /app/output/gain_evidence.json --write-back
python "$S/check_all.py" --result /app/output/result.json --case /input/case.json --edits /app/work/edits.jsonl --structure /app/work/structure.json --revised /app/output/revised.md --client /app/output/revision_client.html --write-back
```

**退出码契约**：所有脚本在任何路径（通过 / 失败 / 缺料 / 异常 / 参数错误）都**退出 0**，结论一律由
报告里的 `verdict` 字段照实记录。校验失败**不中断交付**——按 `checks[]` 逐条修复再跑。
这是刻意设计：评分看的是产物与记录，不是脚本有没有"卡住"。

## 5. 输入与输出解释

**输入**（以实际文件为准，不凭标签猜内容）
- `/input/case.json`：含 `case_id` 与 `output_contract`（决定 result.json 必须有哪些键）。
- `/input/task.md` + 原始材料：docx / pdf / md / txt 等，`extract_materials.py` 负责抽取与登记。

**输出**（`/app/output`）

| 产物 | 格式 | 说明 |
|---|---|---|
| `revised.docx` | docx | 可继续编辑的修订稿（Word）；`python-docx` 缺失时自动降级为 stdlib 最小 docx |
| `revised.md` | markdown | 同一修订稿的 Markdown 版，保留标题层级 / 编号 / 表格 / 题注 / 参考文献 |
| `edits.jsonl`（台账，Agent 写 `/app/work`） | jsonl | 每行一处改动：`eid/iid/pid/locator/before/after/rationale/level/side_effects/status/decision` |
| `diff.md` | markdown | 逐条改动对照（原句/改后/依据/层面/建议裁决），**脚本机械生成** |
| `versions.jsonl` | jsonl | 版本谱系 v1→v2（`based_on` / `edits_applied` / `diff`） |
| `revision_client.html` | html | 自包含交互客户端，浏览器直接打开；全量嵌入 result.json |
| `result.json` | json | 结构化结果（见下） |
| `edits_verify.json` / `check_report.json` | json | 机械自检报告（锚点/落地/未授权改动/引用连续 + 25 条契约校验） |
| `gain_evidence.json` | json | 同输入 full vs degraded 对照证据 |
| `previews/` | pdf/png | 渲染预览；无渲染器时如实记 `no_renderer` |

**result.json 顶层键**
`case_id` / `status`(complete·partial·failed·blocked) / `result` / `claims` / `uncertainties` /
`changelog[]` / `gain_evidence` / `efficiency` / `checks[]` / `gates` / `gate_note` / `verdict`。
`result` 内含 `target_artifact`、`client`（含 `embedded_html` 与 8 条 features）、
`revision_records`（逐条四元组）、`adjudication`（裁决面）、`exports`、`version_and_boundary`。

## 6. 修订客户端用法与导出格式（可复用化）

**用法**：浏览器打开 `revision_client.html` → 左侧台账逐条 **接受 / 拒绝 / 需确认** → 右侧 v1/v2
对照实时合成 → 按裁决导出。裁决存浏览器 `localStorage`（跨会话），交接以**导出裁决 JSON**为准。

**客户端八项功能**

| # | 功能 |
|---|---|
| 1 | 修订逐条裁决：每处改动可单独 接受/拒绝/标记需确认，localStorage 持久跨会话，杜绝整段覆盖不可控 |
| 2 | 修订回看与锚点跳转：修订卡显示 指令号/段落锚点/原文/改后/依据/层面/影响面，一键回到原稿位置 |
| 3 | 版本对照：v1 原稿 / v2 修订稿（按当前裁决实时合成）一键切换，逐条改动可对比 |
| 4 | 导出可编辑稿：按当前裁决一键导出 已接受修订 Markdown + 裁决 JSON，可回填可继续编辑 |
| 5 | 修订筛选：按指令号/层面(措辞\|结构\|术语\|引用\|格式)/裁决状态过滤修订列表 |
| 6 | 关键词搜索：全文命中计数 + 上一个/下一个导航，重渲染保留修订高亮 |
| 7 | 引用与格式哨兵：引用编号缺口、未授权改动、校验结果直接显示在客户端侧栏 |
| 8 | 边界与人工确认：需作者确认项、材料缺口、未执行指令在侧栏如实展示 |

**导出格式（三种，均可被下游工具消费）**

| 导出物 | 内容 | 典型消费方 |
|---|---|---|
| 已接受修订 Markdown | 按裁决过滤后的最终稿（可回填进原稿） | Git / Word / 投稿系统 |
| 裁决 JSON | `{"decisions": {"E001":"accept", ...}}` | Agent 端回填 `result.result.adjudication` |
| 修订台账 JSONL | 逐条改动 + 依据 + 锚点 | 差异审阅工具 / 自建流水线 |

**可复用性**：`export_client.py --structure/--edits/--result --out --embed-result` 可脱离本 Skill
单独使用——任何能产出 `structure.json`（段落锚点）+ `edits.jsonl`（改动台账）的上游，都能直接
复用同一套客户端 HTML 渲染与裁决导出逻辑。

## 7. 使用增益证据（真实对照数字，非自述）

`gain_eval.py` 在**同一份输入**上跑两个条件，由**同一套测量函数**当场算出数字：

- **条件 A full**：加载本 Skill 的完整管线（锚点索引 + 逐条裁决 + 导出校验全开）。
- **条件 B degraded**：同输入、关掉上述机制的**确定性基线重建**（全文首次匹配落点 + 无锚点台账 +
  平铺导出），由脚本当场生成，非预置答案。

`--write-back` 把 `gain_evidence`（comparison + mechanism_to_metric + boundaries）与 `efficiency`
回填 `result.json` 顶层。**边界声明**：这是同输入机制级 A/B，**不是**平台"基础 Agent vs 加载
Skill 的 Agent"对照——后者由平台生成，本 Skill 不冒充、不改写。

**包内合成夹具实测（`examples/demo/`，7 段材料 / 5 条指令 / 4 处改动，含锚点歧义）**：

| 指标 | full | degraded | delta |
|---|---|---|---|
| 修订可追溯率 | **1.0** | 0.0 | +1.0 |
| 改准率 | **1.0** | 0.75 | +0.25 |
| 落地逐字率 | 1.0 | 1.0 | 0.0 |
| 错落改动数 | **0** | 1 | −1 |
| 误改段落数 | **0** | 1 | −1 |
| 需人工核对条目数 | **1** | 4 | −3 |
| 需人工核对字符量 | **14** | 91 | −77 |
| 格式塌陷数 | **0** | 16 | −16 |
| 步骤数 | 8 | 3 | +5（代价如实呈现） |
| 工具调用数 | 5 | 0 | +5（代价如实呈现） |

复现：`python "$S/gain_eval.py" --selfcheck`（见第 9 节）。夹具是**合成示例**，非正式案例答案。

## 8. 验收方式

1. **机械自检**：`check_all.py` 25 条校验 + 5 项闸门（edits_verify / render_preview /
   structure_index / revised_md / gain_evidence）全 `enforced`，`verdict=pass`。
   闸门未 enforced 时 `gate_note` 写明"下游不得宣称已核对"。
2. **逐字回证**：每条 claim 的 `evidence[].quote` 必须逐字出现在原稿或修订稿中。
3. **零未授权改动**：`edits_verify.py` 报告 `unauthorized_changes=0`，引用编号无缺口。
4. **主产物自足**：`result.result.client.embedded_html` 与磁盘上的 HTML 归一化后**完全一致**，
   复核者不开附件即可核对交互能力。
5. **增益可验证**：`gain_evidence.comparison` 非空，`revision_traceability_rate` 等指标有
   full/degraded 两个实数；`efficiency.reproduce` 给出复现命令。

## 9. 最小可运行自检清单（复制即跑）

```bash
python "$S/gain_eval.py" --selftest     # ① 脚本容错双测：正例必过、反例必被抓住、退出码恒 0
python "$S/gain_eval.py" --selfcheck    # ② 合成夹具全链路：七步 + 对照 + 终局自检
```

| # | 自检项 | 通过判据 |
|---|---|---|
| 1 | 5 个带 `--selftest` 的脚本自测 | 末行 `SELFTEST PASS`，退出码 0 |
| 2 | `edits_verify.py --selftest` | 正例 `verdict=pass`；锚点错位反例 `verdict=fail` 且退出码仍 0 |
| 3 | 全链路 `--selfcheck` | 末行 `SELFCHECK PASS`；gates 5 项全 enforced |
| 4 | 产物齐备 | result.json / revised.docx / revised.md / diff.md / versions.jsonl / revision_client.html / edits_verify.json / gain_evidence.json 八件落盘 |
| 5 | 增益字段 | `result.json.gain_evidence.metrics` 与 `result.json.efficiency` 非空且有实数 |
| 6 | 污染反例 | 二进制乱码/缺文件输入下所有脚本仍退出 0，缺料如实记 `missing_inputs` |

## 10. 常见问题（FAQ）

| 现象 | 原因 | 处理 |
|---|---|---|
| `check_all` 报 `client_embedded_in_result` FAIL | 客户端 HTML 生成后又被改动/未重新嵌入 | 重跑 `export_client.py --embed-result` 再跑 check_all |
| `edits_verify` 报 `anchor_fail` | `before` 未逐字出现在原稿 | 回到第 4 步修 pid / quote，或标 `unresolvable` |
| `edits_verify` 报 `unauthorized_changes` | 修订稿里有台账未覆盖的改写 | 补台账条目或恢复原文；不要改校验器 |
| `citation_numbering_continuous` FAIL | 引用编号有跳号 | 补一条联动 edit 完成参考文献重排 |
| `gain_evidence` 指标全为 0 | 输入缺 structure/edits/revised | 检查路径；脚本已把缺料写进 `missing_inputs`，不要手填数字 |
| 预览目录为空 | 环境无 soffice/libreoffice | 正常：`gates.render_preview` 记 `no_renderer`，如实登记即可 |
| 平台沙箱无 `/app/output` 写权限 | 路径不可写 | 全部路径可参数化，改用可写目录 |

## 11. 已知限制

- 客户端是**单文件静态交互页**，不承载多人在线协作；本机裁决以导出 JSON 为持久化形式。
- v2 视图是按裁决**实时合成**的预览，正式回填以 revised.docx / revised.md 与导出 Markdown 为准。
- 定位为**精确子串匹配**（忽略空白差异）；PDF 原稿先转文本层，转换损耗如实登记。
- 渲染失败如实登记，不伪造预览。
- gain_evidence 是同输入机制级 A/B，不是平台对照（见第 7 节边界声明）。

## 12. 复用建议

1. **换领域复用**：把 `structure.json` 的段落抽取换成任意文档格式（journal 模板、学位论文、
   基金申请书），台账-锚点-导出的骨架不变。
2. **接入现有流水线**：上游产出 `structure.json` + `edits.jsonl` 即可复用 `export_client.py`
   单独生成客户端，不必引入本 Skill 全流程。
3. **扩展层面类型**：`level` 字段与客户端筛选器按取值分发，新增层面只需扩展取值集合。
4. **接入 CI**：把 `check_all.py --write-back` 作为稿件发布前的门禁，`verdict != pass` 即阻断。
5. **扩充夹具**：`examples/demo/` 是最小可扩展夹具，复制目录改 `case.json` + `structure.json` +
   `edits.jsonl` + `revised_draft.json` 即可造新用例，跑 `gain_eval.py --selfcheck` 验证。

## 13. 版本维护

| 版本 | 内容 | 兼容性 |
|---|---|---|
| v2（本版） | 8 脚本；`--diff-from-edits` 机械生成 diff/versions；`gain_eval.py --write-back` 落 gain_evidence + efficiency；`--selfcheck` 一命令全链路自检；全部失败路径退出码恒 0 | result.json 顶层新增 `gain_evidence` / `efficiency`，**向后兼容**（旧消费者忽略即可） |
| v1 | 7 脚本；无增益对照；diff/versions 由模型手写；校验失败可能返回非零退出码 | — |

**维护约定**：`scripts/` 固定 ≤8 个；新增能力优先并入现有脚本而非新增文件；任何脚本改动都必须
保持"退出码恒 0 + verdict 照实"契约；改动后必须跑 `gain_eval.py --selftest` 与 `--selfcheck` 双通过。

## 14. 文件清单

```
SKILL.md                Skill 主体（150 行）：协议 + 七步流程 + 异常处置 + 结果契约
README.md               本文件：生态贡献全套
worklog.md              开发日志：v1 差距分析 + v2 增强 + 双测证据
scripts/                8 个纯标准库脚本（见第 4 节命令）
  extract_materials.py  材料抽取与清单登记
  build_result.py       result.json 骨架/合并/claims 挂链/diff+versions 机械生成
  docx_build.py         draft.json → revised.docx + revised.md（python-docx 缺失自动降级）
  render_preview.py     docx → PDF/PNG 预览（无渲染器如实记 no_renderer）
  export_client.py      交互客户端 HTML 生成 + 嵌入 result.json + 裁决回填
  edits_verify.py       台账校验：锚点 / 落地 / 未授权改动 / 引用连续
  gain_eval.py          同输入 full vs degraded 对照 + efficiency 采集 + --selfcheck
  check_all.py          25 条终局机械自检 + 闸门枚举 + 写回 result.json
examples/demo/          合成夹具（case.json / manuscript.md / structure.json / edits.jsonl / revised_draft.json）
```
