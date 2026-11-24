# acwrite-format 使用说明（学术格式与模板适配）

## 用途
把一份真实稿件按目标模板（学位论文模板/投稿模板/学校规定）改到可交付：
规格来自**真实探查**模板文件而非经验猜测；每条格式规则生成**逐项映射**
（模板原值 → 成品落点 → 理由 → 状态），探查原值与映射表**逐字嵌入 result.json**，
复核者无需打开文档即可逐条核对；内容单元（章节/图表/公式/脚注/文献）零丢失对账。

## 适用条件
- 输入含：稿件（docx/pdf/md/txt）+ 模板或格式要求（docx/txt/pdf 均可）。
- 仅 Python 标准库即可运行；python-docx 存在则样式绑定更完整（自动增强，缺失自动降级）。
- 渲染预览需要 libreoffice/soffice，缺失时跳过并如实记录，不阻断主流程。

## 调用方式（完整流程，5 步）
```bash
# 变量按环境设置，不硬编码路径
INPUT=${INPUT_DIR:-/input}; WORK=${WORK_DIR:-/app/work}; OUT=${OUTPUT_DIR:-/app/output}
mkdir -p "$WORK" "$OUT"

# Step 1 提取+探查+盘点
python scripts/extract_materials.py --input "$INPUT" --outdir "$WORK/extracted" --modes extract,probe,inventory

# Step 2（模型）写 $WORK/format_mapping.jsonl —— 每条格式要求一行，覆盖页面/标题/正文/图表/文献/导出六类
# Step 3（模型）写 $WORK/draft.json（内容逐字保留 + style_spec 取自映射表 applied 值），然后构建
python scripts/docx_build.py "$WORK/draft.json" --out-docx "$OUT/draft.docx" --out-md "$OUT/draft.md" --render-dir "$OUT/previews"

# Step 4 逐项核对
python scripts/format_check.py --mapping "$WORK/format_mapping.jsonl" --inventory "$WORK/extracted/content_inventory.jsonl" --draft "$OUT/draft.md" --out "$OUT/format_check.json"

# Step 5 收尾：探查原值 + 映射表强制嵌入 result.json
python scripts/build_result.py --case "$INPUT/case.json" --out "$OUT/result.json" \
  --probe "$WORK/extracted/probe_report.json" --mapping "$WORK/format_mapping.jsonl" \
  --inventory "$WORK/extracted/content_inventory.jsonl" --check "$OUT/format_check.json" \
  --artifact draft.docx --artifact-md draft.md --status complete
```

## 输入 / 输出
- 输入：case.json（含 output_contract 契约字段）+ 稿件 + 模板/格式要求。
- 输出（$OUT）：`draft.docx`/`draft.md`（可编辑成品）、`format_check.json`（核对结果）、
  `result.json`（含 case_id、契约字段、format_spec 探查原值、format_mapping 逐项映射、
  format_check、content_audit、uncertainty、changelog、status）。

## 最小示例（标注为示意，非正式案例结果）
`examples/example_input.json` 是最小输入示意。将一份模板 docx 与稿件 md 放入同一目录后
按上面 5 步运行即可复现完整流程。result.json 中的映射示意（一行）：
```json
{"item":"heading_level_1","template_value":"黑体 三号(16pt) 居中","source":"probe:M02|style:Heading 1",
 "applied":"draft.docx Heading 1 样式绑定: 黑体16pt居中","rationale":"observed 原值直接套用","status":"applied"}
```

## 关键方法
1. **真实探查**：probe 模式直接读模板 docx 的 styles.xml 与 sectPr（python-docx → zipfile+XML
   两级），observed 输出的是文件里的原值；文本类要求按行号定位。没有读到的一律 unspecified。
2. **映射先行**：排版动作开始前先写完映射表，六类规格（页面/标题/正文/图表/文献/导出）逐类登记；
   冲突规定并列记录 status=conflict，不静默取舍。
3. **零丢失对账**：inventory 模式把稿件每个内容单元登记成底册，成品中任一单元找不到即 fail。
4. **强制嵌入**：build_result.py 把探查原值与映射表 verbatim 写入 result.json，评分可逐条回溯。

## 限制
- 模板为扫描图片时只能按可视规格人工抽取，读不出的项标 unspecified。
- 目录域、字体嵌入等 Word 运行时行为以 notes_for_human 提示（如 F9 刷新），不伪造已嵌入状态。
- 不改写正文内容：错别字/表述问题只记建议清单，不混入格式动作。

## 失败处理与自查
- 每个脚本输出 JSON 自检（ok/self_check/verdict）；format_check verdict=fail 必须修复重跑。
- 库缺失 → 脚本自动降级（python-docx→zipfile XML→stdlib 兜底 docx），engine 字段如实记录。
- 收尾时契约字段仍为 null 的，build_result.py 自动写入 uncertainty——失败也交付，状态诚实。
