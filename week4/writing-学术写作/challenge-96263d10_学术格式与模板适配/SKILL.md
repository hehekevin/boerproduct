---
name: acwrite-format
description: 学术格式与模板适配技能：先真实探查模板文件抄出规格原值（栏数/字号/行距/页边距/标题样式），再产出逐项格式规则映射表（template_value/applied/rationale/出处）并与探查原值一起强制嵌入 result.json，评分者无需打开文档即可逐项核验；内容单元零丢失对账。Use when the case asks to adapt a manuscript to a journal/school/thesis template, fix heading levels, captions, cross-references, or reference styles (GB/T 7714, APA, Vancouver).
---

# acwrite-format — 模板适配（真实探查 · 逐项映射 · 零丢失）

核心主张：**规格来自探查不来自记忆，映射逐条可核验**。探查脚本读到的模板原值一字不改进
result.json；每条格式规则的"模板原值→成品落点→理由"各占一行映射，评分者按行核对。

## 强制执行协议（置顶，任何情况下先做）

1. **抄契约**：读 `$INPUT/case.json`，逐字抄下 `output_contract` 全部字段名与 `case_id`。
2. **立即落骨架**：执行协议第 1 步的同时写 `/app/output/result.json` 骨架——含 case_id、
   全部契约字段（值先 null）、status="in_progress"、uncertainty=[]。先写盘再干活。
3. **字段一个不缺**：收尾时契约字段必须都有值（可 fill 则填；填不了保持 null 并在
   uncertainty 写明原因）。缺字段 = 交付不完整。
4. **广度优先**：先让全部产物有最小完整版（稿件 docx+md、映射表、result.json 各字段），
   再回头打磨任何单项。禁止在某一格式细节上耗尽预算。
5. **熔断**：模型请求 ≤48 次、耗时 ≤700 秒（预算 64 次/900 秒，留 16 次/200 秒余量）。
   到达 48 次或 700 秒：立即跳到收尾步，交付已有成果。
6. **写盘自检**：每步产物写盘后用脚本输出验证（文件存在、size>0、JSON 可解析）。
7. **失败也交付**：任何一步失败（库缺失、模板读不出、渲染失败）不中断——降级路径继续，
   result.json 照写，status 如实标 partial，失败原因进 uncertainty。

## 0. 路径与变量（不硬编码平台路径）
```bash
INPUT=${INPUT_DIR:-/input}; WORK=${WORK_DIR:-/app/work}; OUT=${OUTPUT_DIR:-/app/output}
mkdir -p "$WORK" "$OUT"
ls -la "$INPUT" && cat "$INPUT/case.json"   # 抄 output_contract 与 case_id
```
依赖：仅 Python 标准库即可运行；python-docx/PyMuPDF 存在则自动增强。

## Step 1 — 提取 + 真实探查 + 盘点（1 次脚本，三级容错）
```bash
python scripts/extract_materials.py --input "$INPUT" --outdir "$WORK/extracted" \
    --modes extract,probe,inventory
```
- **extract**：全部材料 → `$WORK/extracted/Mxx.txt`（锚点行 `[SRC:Mxx:<loc>]`）。
- **probe**：模板 docx 真实读取 → `probe_report.json`。observed 里是**原值**：样式字体/字号/
  加粗/对齐/行距、页宽高/四边距(cm)、栏数、分节属性；文本类格式要求记条款行号。
  **禁止凭经验补规范——observed 没有的项就是 unspecified，不许编。**
- **inventory**：稿件全部内容单元 → `content_inventory.jsonl`（每段/表/题注/文献一行+locator），
  这是零丢失对账底册。
- 自检：脚本输出 summary.extracted>0、probe_engines 非 error；否则把失败逐条记 uncertainty 继续。

## Step 2 — 逐项格式映射表（1 次响应，产出 `$WORK/format_mapping.jsonl`）
对照 probe_report 的 observed 原值与 extracted 文本条款，**每条格式要求一行 JSON**：
```json
{"item":"heading_level_1","template_value":"黑体 三号(16pt) 居中","source":"probe:M02|style:Heading 1",
 "applied":"draft.docx Heading 1 样式绑定: 黑体16pt居中","rationale":"observed 原值直接套用","status":"applied"}
```
- 覆盖面必查（每类至少一条，模板没有则 status=unspecified+rationale"模板未规定"）：
  页面（纸张/边距/栏数/行距/页眉页脚/页码）、标题（层级数/各级样式/编号规则/目录）、
  正文（字体字号/缩进）、图表（题注位置与字号/编号规则/三线表/交叉引用/分辨率）、
  参考文献（样式/字段顺序/作者截断/et al/文献类型标识/中英混排）、导出（PDF/字体嵌入/目录刷新）。
- 冲突项两条并列各一行 status=conflict，取高优先级者写 applied，rationale 说明取舍依据。
- status ∈ applied/partial/unspecified/conflict/degraded；applied 必须与 Step 3 实际动作一致。
- 映射先行于改稿：没有映射表不允许开始排版（先想清楚再动手）。

## Step 3 — 套用排版（1 次响应 + 1 次脚本）
- 写 `$WORK/draft.json`：内容**逐字保留**（错别字也不改，改处记 notes_for_human），
  `style_spec` 从映射表 applied 值转录；标题绑定真实样式（不是加粗模拟）；图题注在下、
  表题注在上；图表编号按模板规则重排且正文交叉引用同步；参考文献整表重排为目标样式。
```bash
python scripts/docx_build.py "$WORK/draft.json" --out-docx "$OUT/draft.docx" \
    --out-md "$OUT/draft.md" --render-dir "$OUT/previews"
```
- 脚本按 style_spec 真实改样式（python-docx→stdlib 兜底均写 styles.xml）；渲染可选，
  soffice 缺失时如实记"未渲染"不阻断。自检：self_check.docx_exists=true 且 size>0。

## Step 4 — 逐项核对（1 次脚本，fail 必须修复重跑）
```bash
python scripts/format_check.py --mapping "$WORK/format_mapping.jsonl" \
    --inventory "$WORK/extracted/content_inventory.jsonl" --draft "$OUT/draft.md" \
    --mids M01   # 稿件材料 id（按 Step 1 manifest 识别；只对账稿件，模板/要求文件不算）
    --out "$OUT/format_check.json"
```
- 审计：映射表字段完整性、内容单元零丢失（清单任一单元在成品中找不到=fail）、
  图表编号连续性。verdict=fail → 回 Step 3 修复重跑；unspecified 属如实标注不算 fail。

## Step 5 — 收尾：result.json 强制嵌入（1 次脚本）
```bash
python scripts/build_result.py --case "$INPUT/case.json" --out "$OUT/result.json" \
    --probe "$WORK/extracted/probe_report.json" --mapping "$WORK/format_mapping.jsonl" \
    --inventory "$WORK/extracted/content_inventory.jsonl" --check "$OUT/format_check.json" \
    --artifact draft.docx --artifact-md draft.md \
    --status complete --notes '["..."]' --changelog '["参考文献N条重排为GB/T 7714..."]'
```
- 强制嵌入：`format_spec`=探查原值、`format_mapping`=逐项映射、`format_check`=核对结果、
  `content_audit`=对账摘要。契约字段仍 null 的由脚本自动记入 uncertainty。
- 自检：脚本输出 mapping_items>0、spec_probes>0；随后 `cat` result.json 确认契约字段齐全。
- 写盘终检后即使部分失败也交付：status 如实（complete/partial），失败链路写进 uncertainty。

## 异常处置表

| 情形 | 处置 |
|---|---|
| 模板是 PDF/图片 | 按可视规格抽取，source 记页码；读不出的一律 unspecified |
| 规格冲突（学校规定 vs 期刊模板） | 两条 conflict 并列，取高优先级，rationale+uncertainty |
| python-docx 缺失 | 自动降级 zipfile+XML；再降 stdlib 兜底 docx；engine 如实记录 |
| 字体缺失渲染方框 | 换环境可用字体重建，映射表加 degraded 行记录替换 |
| 公式为图片/域代码丢失 | 原样保留，映射表加行说明替代方案，status=partial |
| 内容单元对账发现丢失 | 回 Step 3 补回；补不回的列 lost 明细 + uncertainty，不静默 |
| 目录域需 Word 刷新 | draft.json notes_for_human 写明"Word 中 F9 刷新"；映射表记 unspecified/applied |
| 模板文件缺失 | 全部规格 unspecified + rationale"无模板文件"；按通用学术规范给建议值并标 degraded |

## 最小调用示例（示意，非正式案例结果）
```bash
python scripts/extract_materials.py --input ./examples --outdir /tmp/w/extracted --modes extract,probe,inventory
# → {"ok":true,"summary":{"total":2,"extracted":2},"probe_engines":["python-docx","text-lines"],"inventory_units":17}
# （模型响应：format_mapping.jsonl —— 23 行，每行含 template_value/source/applied/rationale/status）
python scripts/docx_build.py /tmp/w/draft.json --out-docx /tmp/out/draft.docx --out-md /tmp/out/draft.md
# → {"ok":true,"builder":"python-docx","self_check":{"docx_exists":true,"docx_size":9312,"md_exists":true}}
python scripts/format_check.py --mapping /tmp/w/format_mapping.jsonl --inventory /tmp/w/extracted/content_inventory.jsonl --draft /tmp/out/draft.md --out /tmp/out/format_check.json
# → {"ok":true,"verdict":"pass","mapping":23,"content_lost":0,"issues":0}
python scripts/build_result.py --case ./examples/example_input.json --out /tmp/out/result.json \
    --probe /tmp/w/extracted/probe_report.json --mapping /tmp/w/format_mapping.jsonl \
    --inventory /tmp/w/extracted/content_inventory.jsonl --check /tmp/out/format_check.json --status complete
# → {"ok":true,"mapping_items":23,"spec_probes":2,"contract_nulls":[]}
# result.json 内 format_spec/format_mapping 逐字嵌入，评分者可按行核验每条映射。
```

## 交付自查清单
- [ ] result.json 骨架在 Step 1 前落盘；契约字段一个不缺（null 必有 uncertainty 说明）
- [ ] probe_report 的 observed 原值一字不改进 result.json.format_spec；无编造规范
- [ ] format_mapping 覆盖六类规格，每行含 template_value/source/applied/rationale/status
- [ ] 内容单元零丢失（format_check.content_lost=[]）；图表编号连续、交叉引用同步
- [ ] 标题绑定真实样式；参考文献整表符合目标样式且正文引用同步
- [ ] draft.docx + draft.md 可编辑；渲染/降级情况如实记录
- [ ] status 诚实；uncertainty 含 unspecified 项、冲突取舍、降级与失败链路
