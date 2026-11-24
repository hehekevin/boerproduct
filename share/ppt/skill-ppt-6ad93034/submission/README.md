# deck-edit — 学术 PPT 生成与定点编辑（使用与方法说明）

把论文/科研材料组织成**可编辑、证据可溯、可复核**的学术汇报稿；或对已有 deck 做**source-preserving 定点编辑**（只改指令点名页，其余页与母版不动）。全程产出页级证据映射、逐页 diff、版本留痕与渲染件。

## 1. 适用 / 不适用

- **适用**：论文→学术汇报（组会/开题/中期/答辩/评审）；按指令改某页文字或数字、压缩/扩写、换受众、换语言、换图、改备注；多轮迭代需版本比对与回退；模板约束下成稿并要求导出不塌版。
- **不适用**：论文精读与文献综述；科研绘图的数据可视化算法本身；学术写作文字润色；PPT 软件本体开发。

## 2. 文件清单（资源 8 脚本 + 1 示意示例）

| 文件 | 职责 | 关键参数 |
|---|---|---|
| `SKILL.md` | 执行协议 + 五步主流程 + 异常处置 + 自查清单 | — |
| `scripts/extract_pdf.py` | PDF→`paper_text.txt`（PAGE 锚点）+ 嵌图 + 缺图整页渲染 | `--outdir` `--page-render` `--min-size` |
| `scripts/layout_budget.py` | 版面预算：按 16:9 版心算字数/行数，字号阶梯收缩 | 被 build/verify 导入 |
| `scripts/pptx_build.py` | deck.json→pptx；模板继承；预算告警；兜底降级 | `--log` 第 4 位可选模板 |
| `scripts/pptx_minimal.py` | 纯 stdlib 兜底构建器（无 python-pptx 时仍可编辑） | 被 build 调用 |
| `scripts/pptx_edit.py` | 定点编辑 6 类 op，母版安全，自动写 versions.jsonl | `--slide` `--find` `--text` `--versions` |
| `scripts/pptx_verify.py` | 结构/备注/图/几何校验；`diff` 模式做逐页字段 diff | `--evidence` `--out` |
| `scripts/evidence_check.py` | quote 逐字命中 + **页级覆盖** + **数字对账** | `--paper` `--map` `--deck` `--out` |
| `scripts/render_preview.py` | pptx→pdf→png，三级渲染降级，如实写 render_log | `--outdir` `--log` |
| `examples/example-deck.json` | deck.json/页级结构**示意**（虚构内容，非案例结果） | — |

## 3. 依赖、版本与安装

| 依赖 | 实测版本 | 必需性 | 缺失时的行为 |
|---|---|---|---|
| Python | 3.13.14（兼容 ≥3.8，仅用 stdlib 语法） | 必需 | — |
| python-pptx | 1.0.2 | 推荐 | build 自动降级 `pptx_minimal`（可编辑，但模板继承失效，layout_log 标注）；定点编辑不可用，status 记 `partial` |
| PyMuPDF | 2.x（`import fitz`） | 推荐 | 退 `pdftotext`（有则用），无嵌图；仍写 PAGE 锚点 |
| Pillow | 13.0.0 | 可选 | 图片按固定尺寸放入，可能非等比 |
| LibreOffice / office-renderer | 环境提供 | 可选 | `render.status` 依次降级 `pdf_only_no_png` → `no_renderer`，如实记录 |

安装（有网环境）：`pip install python-pptx pymupdf pillow`。无网环境不需要额外安装：缺依赖时全部走兜底路径，脚本不中断。

## 4. 输入 / 输出

- **输入**：`/input/case.json`（`case_id`、`output_contract`、材料路径、约束）+ `task.md` + 论文/材料文件 +（编辑任务）起点 pptx。
- **输出**（`/app/output`）：
  - `result.json`：契约全字段 + `slides` 逐页内嵌（标题/要点/图表/备注/证据）+ `evidence_map` + `edit_log` + `render` + `verification` + `gain` + `status`/`uncertainty`/`changelog`；
  - `deck.pptx`、`deck.vK.json` 快照、`evidence_map.jsonl`、`versions.jsonl`、`diff_v*.json`；
  - `layout_log.json`、`verify_report.json`、`evidence_check.json`、`deck.pdf`、`previews/*.png`。
- **页数/导出要求**：页数不超过 case.json 声明上限（超限先砍方法细节页，不砍结果页与限制页）；每页要点 ≤5 条、每条 ≤40 字；导出件必须与 pptx 同源，渲染失败要如实标 `no_renderer` 而不是伪造。

## 5. 调用步骤

```bash
# 0) 抄契约 + 落 result.json 骨架（SKILL.md §0）
cat /input/case.json
# 1) 提取
python scripts/extract_pdf.py /input/materials/paper.pdf --outdir /app/work/extracted --page-render
# 2) 写 /app/work/deck.json + /app/work/evidence_map.jsonl（结构见 examples/example-deck.json）
# 3) 构建
python scripts/pptx_build.py /app/work/deck.json /app/output/deck.pptx --log /app/output/layout_log.json
# 4) 编辑（可选，可多轮）
python scripts/pptx_edit.py /app/output/deck.pptx replace-text --slide 3 --find "38.2" --text "41.7" --versions /app/output/versions.jsonl
# 5) 校验 + 证据 + diff + 渲染
python scripts/pptx_verify.py /app/output/deck.pptx /app/work/deck.json --evidence /app/work/evidence_map.jsonl --out /app/output/verify_report.json
python scripts/evidence_check.py --paper /app/work/extracted/paper_text.txt --map /app/work/evidence_map.jsonl --deck /app/work/deck.json --out /app/output/evidence_check.json
python scripts/pptx_verify.py diff /app/output/deck.v1.json /app/output/deck.v2.json --out /app/output/diff_v1_v2.json
python scripts/render_preview.py /app/output/deck.pptx --outdir /app/output/previews
```

## 6. 最小调用示例（示意，非正式案例结果）

以下输出为**本地实测的示意**（3 页合成夹具，虚构数据），仅说明接口形态：

```bash
$ python scripts/pptx_build.py t/work/deck.json t/out/deck.pptx --log t/out/layout_log.json
pptx: t/out/deck.pptx
builder: python-pptx | warnings: 0        # 退出码 0

$ python scripts/evidence_check.py --paper t/work/paper_text.txt --map t/work/evidence_map.jsonl --deck t/work/deck.json --out t/out/evidence_check.json
evidence: {'rows': 5, 'fail': 0, 'verdict': 'pass', 'coverage_gate': 'enforced', 'warn': 0,
           'slides_checked': 3, 'slides_without_evidence': [], 'coverage_fail_slides': [],
           'numeric_unbacked': {}}

$ python scripts/pptx_verify.py t/out/deck.pptx t/work/deck.json --evidence t/work/evidence_map.jsonl
verify: {'fail': 0, 'warn': 0, 'verdict': 'pass'}

$ python scripts/render_preview.py t/out/deck.pptx --outdir t/out/previews
{"status": "no_renderer", "pdf": null, "pngs": 0, "log": "t/out/previews/render_log.json"}   # 退出码 3，如实降级
```

**负例（数字对账生效）**：把页面上的 `41.7%` 手改成 `42%`，该页 quote 未变 →

```json
{"summary": {"rows": 5, "fail": 0, "verdict": "pass",
  "numeric_unbacked": {"3": ["42%"]}},
 "slide_coverage": [{"slide_no": 3, "evidence_rows": 2, "numeric_tokens": ["42%","38.2%","12.4"],
   "numeric_unbacked": ["42%"], "verdict": "warn"}]}
```

说明：quote 仍能逐字命中原文（所以 fail=0），但页面数字与本页证据对不上，被 `numeric_unbacked` 抓出，必须回原文改正或写入 uncertainty。这是本技能"改数字不靠印象"的机器闸门。

**闸门三态（重要）**：`summary.coverage_gate` 明确区分"跑了"与"没跑"——`enforced`（正常执行，页级 fail 会让 `verdict:"fail"` 且 rc=1）、`skipped_no_deck`（未传 `--deck`）、`deck_not_found`（传了路径但不存在）。后两种会强制 `warn:1` 并输出 `gate_note` 要求登 uncertainty，**绝不伪装成通过**；若交付里 `coverage_gate` 不是 `enforced`，说明页级覆盖与数字对账根本没执行。

`verify_report.json` 里对应的键叫 `evidence_gate`（刻意与 `coverage_gate` 区分：前者管结构校验里的证据覆盖，后者管页级证据与数字对账）：`enforced` / `not_provided`（未传 `--evidence`）/ `not_found`（路径错）/ `coverage_incomplete`（证据未覆盖全页）。非 `enforced` 一律计 warn 并写 note。此外 notes 缺失、短于 40 字或与页面正文雷同会计入 `fail`（不只是打印），因为讲稿是交付物的一部分。

`examples/example-deck.json` 为 6 页完整结构示意（含 role/layout/figure/notes/evidence 五类字段），其中的图片路径与数字均为虚构占位，**不可直接当答案**。

## 7. 关键方法（为什么比"把段落切进文本框"好）

1. **一页一主张 + 叙事角色**：每页必须声明 `role`（hook/problem/method/result/limitation/conclusion/backup）与一句 `claim`，页序按论文贡献排，不按章节顺序搬运。
2. **证据先于页面**：任何数字/单位/图号上页前，evidence_map 必须有逐字 `quote`；`evidence_check` 做三重校验（逐字命中、页级覆盖、数字对账）。
3. **source-preserving 编辑**：定点 op 只改目标字段，`versions.jsonl` 逐条记录前后值与文件哈希，`diff` 模式给逐页字段 diff，`preserved_slides`/`edited_slides` 显式声明。
4. **版面预算而非硬塞**：字号阶梯 18→16→14→12→11→10，缩到 10 仍溢出则要求删内容，避免"字小到看不见"的伪完成。
5. **渲染诚实**：office-renderer → soffice → PowerPoint COM → 无渲染器四段降级，每段结果写进 render_log，不伪造成功。
6. **模板真实继承**：有模板时若 deck_meta 未显式指定 `font_latin`/`font_ea`，build 不向 run 写入字体，交给主题字体继承；`layout_log.slides[i]` 的 `inheritance:"real"` + `placeholders_used` 非空即为继承生效的证据（实测：模板构建后 slide XML 内 `<a:latin typeface="...">` 出现 0 次，未被 Arial 覆盖）。

## 8. 已知问题与限制

- 定点编辑依赖 python-pptx；缺失时只能走 deck.json 重建（母版继承与"未改页字节不变"无法保证，此时 result.json 必须记 `partial` 并说明）。
- 矢量图/裁剪图无法取像素数据，只能整页渲染后引用（`figure_mode:"page_render"`）；**不还原图内数值**。
- 扫描件文本依赖 OCR，locator 只能给页码，OCR 误差写入 uncertainty。
- 模板母版槽位不足时用独立文本框替代，可能在极端模板上与原版式有视觉差异（layout_log 记 `template_slot_insufficient`）。
- 数字对账的取样面是页面上所有可读文本（title / bullets / 双栏 columns / 表格单元格 / 图注），不含 notes；仍无法覆盖**图片内嵌的数字**（图里的数值只能靠图注与 line item 引用），中文数字（如"三成"）与区间写法（如"3–5"）也会漏检，需人工确认。
- 归一化后是子串匹配：`12.4` 可能命中 `12.45`。token 设计成带单位/百分号优先只是压低误报，不等于零误报；要更严需按 token 边界切分比对，代价是误报上升（当前判定：误报成本 > 漏检成本）。
- 表格单元格若是数字类型（如 `0.92` 而非字符串 `"92%"`），会被当作独立 token 判为未回证。这是有意的取舍——不做 `0.92→92%` 的换算，才不会放过"页面写 0.92、quote 写 92%"这类真脱钩；代价是要求**内容侧统一写成带 % 的字符串**，而不是让闸门去猜。
- 本地无 soffice 时渲染只能报 `no_renderer`，PNG 复核需在平台 office-renderer 环境中完成。

## 9. 复用与扩展

- 换模板：`pptx_build.py <deck.json> <out.pptx> <模板.pptx>`，脚本按 layout 名匹配模板版式（title/bullets/figure/table/bullets+figure），不改母版配色与页脚。
- 加页型：在 deck.json 的 `layout` 里用已有四类之一即可；新增版式需在 `pptx_build.py` 的 layout 映射表补一行。
- 接别的字段契约：result.json 的扩展字段（slides/evidence_map/edit_log/render/verification/gain）与 `output_contract` 解耦，契约字段原样保留即可直接复用。
