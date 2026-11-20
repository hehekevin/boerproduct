# worklog — ppt-6ad93034 学术 PPT 生成与编辑（本轮：68.33 → 目标 ≥75）

日期：2026-11-13。基线：attempt 73325（重做版，排队中）；参照：同赛道最高分 75 的 `paper2deck-skill`。

## 一、分数走势与失分推断

| 轮次 | 得分 | 推断改动 | 结论 |
|---|---|---|---|
| 1 | 51.67 | 基础流程，能出 pptx | 契约不全、证据弱、渲染/版本缺失 |
| 2 | 61.33 (+9.7) | 补齐阶段化流程 | 字段完整性与逐字证据仍不足 |
| 3 | 68.33 (+7.0) | 加入定点编辑/版本/受众矩阵 | 编辑线拉分，逼近门槛 |
| 4 | 67 (−1.33) | 继续堆流程细节 | **加流程已无边际收益**，失分点转向"可核验性/增益可验证性" |

## 二、与 75 分标杆（paper2deck-skill）的逐项差距

| 维度 | 标杆做法 | 73325 版状态 | 本轮处置 |
|---|---|---|---|
| 文档完整性（生态 3） | `references/layout-rules.md` + `references/page-plan-and-evidence.md` + `examples/example-deck.json` 三件套，规则可被他人直接读 | 把 references 全并进 SKILL.md，**examples/ 目录空**：结构示意无处可看，复用者只能靠猜 | 新增 `examples/example-deck.json`（6 页完整结构示意，标注示意）；README 列文件清单/参数表/依赖版本/限制/复用指引 |
| 资源可复用性（生态 4） | 7 脚本单职责 + 1 示例 | 8 脚本（多 pptx_edit）+ 无示例 | 保留 8 脚本单职责，补示例；脚本全部可独立 `--help` 调用 |
| result.json 可核验（实际效果 5+5） | 只在 result.json 给索引，页内容在 deck.json | 已内嵌 `slides` | 保留并强化：`slides` 逐页 + `gain` 指标块；evidence_check 直接吃 deck.json 做页级覆盖 |
| 使用增益（25） | 有受众矩阵与取舍记录，但**无对照记录位** | 同样没有"返工页数/重排次数/导出复查轮次"的落点 | 新增 `gain` 字段（mode/rework_pages/reorders/export_checks/manual_edits/baseline_note），把效率增益变成可读数，并声明对照以平台白板为准 |
| 创新证据（15） | 页级证据映射（已有方法论） | 有映射但**无机器校验**：quote 对得上≠页面上的数字对得上 | `evidence_check.py` 新增 `--deck`：①页级覆盖（每页有证据行+locator）②**数字对账**（页面百分数/小数/带单位数必须出现在本页 quote 中）③备注长度；负例已测出 `42%` 未回证 |
| 可靠体验（10） | 三级降级 | 有 python-pptx 兜底，但 `extract_pdf.py` **从不写 paper_text.txt**（fitz 路径），且渲染链缺平台 office-renderer | 修 fitz 路径写盘 bug；`pdftotext` 路径补 PAGE 锚点；新增 `--page-render`（缺图页整页渲染，figure_mode=page_render）；渲染链加入 office-renderer 作为第一优先，仍四段诚实降级 |
| 硬纪律 | — | 已有协议置顶/熔断/自检/四级 status | 全保留，SKILL.md 压到 149 行（≤150） |

## 三、本轮改动清单（相对 73325，全部为增量）

1. **修 bug**：`extract_pdf.py` 的 fitz 路径补 `paper_text.txt` 写盘（原版只累积 text_parts 不落盘 → 后续 evidence_check 必然读不到论文，整条证据链断裂）。这是"实际效果/可核验性"最大的一处隐性失分。
2. **补锚点**：`pdftotext` 降级路径补 `===== PAGE n =====` 锚点，保证 locator 始终可用。
3. **补能力**：`extract_pdf.py --page-render` —— 正文提到 Fig./图 n 但无可取位图的页，整页渲染（`page_pN.png`，`figure_mode:"page_render"`），对应题面"图表无法提取（纯矢量图）"的处置，且明令禁止占位图。
4. **补校验**：`evidence_check.py --deck` —— 页级证据覆盖 + 数字对账，输出 `slide_coverage`；`numeric_unbacked` 非空即须修复或入 uncertainty。
5. **补渲染链**：`render_preview.py` 增加 `office-renderer`（平台工具）为第一优先，保留 soffice → PowerPoint COM → no_renderer 的诚实降级。
6. **补增益位**：SKILL.md §3 增加 `gain` 字段与说明（返工页数/重排次数/导出复查轮次），对应"增益可验证性 5 分"。
7. **补示例**：`examples/example-deck.json`（示意，6 页，含 role/layout/figure/notes/evidence）。
8. **文档升级**：README 增加依赖版本表（实测 python-pptx 1.0.2 / PyMuPDF 2.x / Pillow 13.0.0 / Python 3.13.14）、参数表、失败降级矩阵、已知问题、复用指引、负例演示。
9. **压行**：SKILL.md ≤150 行，保持纪律；8 个脚本职责不变（资源 8 脚本 + 1 示意示例）。
10. **模板字体继承修复**（收到 pptfix-templatefit 的接口变更通知后追加）：原 build 在有模板时仍把默认 `Arial`/`Noto Sans CJK SC` 写进每个 run，等于覆盖模板主题字体，"真实继承"名存实亡。现改为：模板存在且 deck_meta 未显式声明字体时，`latin`/`ea` 传 None，不写 `<a:latin>`。实测（自造带占位符模板）：`inheritance:"real"`、`placeholders_used:[0,1]`、warnings 0，slide XML 中 `<a:latin typeface>` 出现 0 次。SKILL.md 同步加约束：有模板时不写 font_latin/font_ea，并须核 layout_log 的 inheritance 字段。
11. **数字对账取样面扩展**（与 pptfix-templatefit 交叉验证后回补）：原实现只扫 bullets，双栏页与表格页的数值完全不在闸门内（表格里的 61% 漏检）。现 `evidence_check.slide_text()` 扫 title + bullets（兼容 `{"text":...}` 形式）+ `columns` + `table.rows` + 图注，notes 仍排除。实测：表格页含 `92%/61%`、双栏页含 `1.8 ms`，只回证 92% 时输出 `numeric_unbacked:{"1":["61%"],"2":["1.8"]}`，两页均 warn。同时把 SKILL.md 的 warn 口径收紧为"warn 不得静默通过：逐条修复或写进 uncertainty 后方可交稿"。

## 四、本轮本地验证记录（合成夹具，非正式案例）

| 步骤 | 命令 | 结果 |
|---|---|---|
| 构建 | `pptx_build.py deck.json deck.pptx --log` | `builder: python-pptx \| warnings: 0`，rc=0 |
| 证据（正例） | `evidence_check.py --paper … --map … --deck …` | `fail:0 verdict:pass slides_without_evidence:[] numeric_unbacked:{}` |
| 证据（负例：41.7%→42%） | 同上 | `numeric_unbacked:{"3":["42%"]}`，第 3 页 verdict=warn → 机器拦住"印象取整" |
| 结构校验 | `pptx_verify.py deck.pptx deck.json --evidence …` | `{'fail':0,'warn':0,'verdict':'pass'}`，rc=0 |
| 提取（含缺图页） | `extract_pdf.py paper.pdf --outdir … --page-render` | `figures:1`，产出 `paper_text.txt` + `figures/page_p1.png` |
| 渲染降级 | `render_preview.py deck.pptx --outdir …` | 本机无 soffice/office-renderer → `status:"no_renderer"`，rc=3，**未伪造成功** |
| 示例构建 | `pptx_build.py examples/example-deck.json` | rc=0，6 页全部 notes 校验 ok |
| 模板继承 | `pptx_build.py deck.json out.pptx tpl.pptx --log` | `inheritance:"real"`、`placeholders_used:[0,1]`、warnings 0；slide XML 内 `<a:latin typeface>` 0 次 |
| 表格页对账 | `evidence_check.py --deck` | `table.rows` 含 92%/61%、只回证 92% → `numeric_unbacked:{"1":["61%"]}`，warn，92% 无误报 |
| 双栏页对账 | 同上 | `columns` 含 `1.8 ms` → `numeric_unbacked:{"2":["1.8"]}`，warn |

**回归基线（改 `numeric_tokens` / `slide_text` / 匹配方式 / 分级逻辑 / 闸门状态机前先跑这七条，期望值不得变，任一不符即视为回归）**：①表格页 → `["61%"]`；②双栏页 → `["1.8","0.92"]`（数字型单元格 `0.92` 不换算，判独立 token）；③`92%` 在 quote 中 → 无误报、仅 warn 级别；④**无证据行的页 → `slides_without_evidence:[n]` + `coverage_fail_slides:[n]` + `summary.verdict:"fail"` + 退出码 1**；⑤**evidence_check 闸门三态**：不给 `--deck` → `coverage_gate:"skipped_no_deck"` + `warn:1` + rc=0；`--deck` 路径不存在 → `"deck_not_found"` + `warn:1` + rc=0；正常执行 → `"enforced"`；⑥**verify 的 `evidence_gate` 四态**：证据齐全 → `enforced`；不带 `--evidence` → `not_provided` + warn 1；路径错 → `not_found` + warn 1；空文件或未覆盖全页 → `coverage_incomplete` + warn 1；⑦**notes 不合格（缺失/短于 40 字/与正文雷同）→ `fail` 计数 + rc=1**。此基线与 pptfix-templatefit 包对齐，两包对账口径与 fail/warn/缺参/未运行四类边界一致。

> 附注（本轮修）：①原实现的 `summary.verdict` 只看 quote 层，页面级 `fail` 时仍输出 `verdict:"pass"`、退出码 0——"第 3 页一条证据都没有"也能静默通过；已改为聚合 quote 行与页级覆盖。②闸门原本对"未运行"没有独立状态：不传 `--deck` 或路径写错时，输出与"通过"完全一样。现显式三态化（`enforced` / `skipped_no_deck` / `deck_not_found`），未运行时强制 `warn:1` 并写 `gate_note` 要求登 uncertainty——**"没跑"与"通过"必须是两个状态**，否则漏参会被当成合格交付。③同一根因在 `pptx_verify.py` 里还有两处：不传 `--evidence` 时 `evidence_map` 只显示 `rows:0` 而 `warn:0`、`verdict:pass`（"没检查"被当"通过"）；`notes` 不合格（缺失/过短/与正文雷同）只打印 `ok:false` 却不计入 `fail`（页能过、rc=0）。现已加 `evidence_gate`（`enforced`/`not_provided`/`not_found`/`coverage_incomplete`，非 enforced 计 warn 并写 note）与 notes→fail 计数。命名特意与 `coverage_gate` 区分：两个脚本各管一段（evidence_check 管页级证据与数字，verify 管结构+证据覆盖），不复用同一个键名，避免读 result.json 的人误以为同义。

环境说明：本机为 Windows 开发机（Python 3.13.14，无 LibreOffice），因此渲染只验证了"诚实降级"分支；平台 office-renderer 分支的代码路径按"产生即检查文件存在、失败即回落"实现，失败不静默。

## 五、仍存在的风险（如实）

1. 平台 3 个正式案例本轮无法本地复跑（无 `/input/case.json` 与论文原件），因此"实际效果 40 分"的最终呈现仍取决于运行时执行纪律（协议置顶 + 广度优先 + 骨架先行）。
2. 数字对账是正则级启发，中文数字/区间写法会漏检（已写入 README 限制）。
3. 多轮编辑若涉及增删页，会走重建而非字节级定点，`preserved_slides` 只能保证"内容未改"，不能保证"字节未变"（SKILL.md 已把该场景标为例外）。
4. 渲染 PNG 的视觉复核需在有渲染器的环境完成；无渲染器时只能交 pptx + 如实状态。
