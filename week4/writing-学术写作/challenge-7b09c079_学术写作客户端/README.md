# acwrite-client — 使用与方法说明

按修改指令对学术稿件做**外科手术式修订**：每处改动可定位（锚点）、可追溯（原文/改后/依据）、可逐条接受或拒绝，引用编号联动同步，导出可编辑的 docx/md。

## 依赖
- Python 3.8+，仅标准库即可运行（python-docx 可选：可用时生成真 docx，缺失时 stdlib 兜底产出合法最小 docx，运行状态如实记录）。
- 所有脚本无第三方强制依赖，无网络访问。

## 目录结构
```
SKILL.md                  # Skill 本体（执行协议 + 5 步主流程）
scripts/extract_materials.py   # 输入材料抽取（case.json/task.md/稿件/指令）
scripts/docx_build.py          # draft.json → revised.docx + revised.md
scripts/edits_verify.py        # 修订台账校验（锚点/落地/未授权改动/引用编号）
scripts/consistency_check.py   # 约束一致性检查
scripts/render_preview.py      # docx 渲染预览（PDF/PNG，环境可用时）
scripts/build_result.py        # result.json 组装/回填（output_contract 全键）
scripts/fact_ledger.py         # 事实台账构建与核对
examples/example_input.json    # 最小示意输入（示意，非正式案例）
```

## 调用流程（5 步）
```bash
# Step 0 定契约：读 /input/case.json + task.md，先落 result.json 骨架
python scripts/extract_materials.py --input /input --outdir /app/work/extracted
python scripts/build_result.py --case /input/case.json --out /app/output/result.json --status partial
# Step 1 结构快照+指令拆解（模型产出 structure.json / instructions.jsonl）
# Step 2 修订台账（模型逐条产出 edits.jsonl：锚点/原文/改后/依据/影响面）
# Step 3 应用与构建
python scripts/docx_build.py /app/work/revised_draft.json --out-docx /app/output/revised.docx --out-md /app/output/revised.md
# Step 4 校验与收尾
python scripts/edits_verify.py --edits /app/work/edits.jsonl --original /app/work/extracted --revised /app/output/revised.md --out /app/output/edits_verify.json
python scripts/consistency_check.py --draft /app/output/revised.md --constraints /app/work/constraints.json --out /app/output/check_report.json
python scripts/build_result.py --case /input/case.json --out /app/output/result.json --artifact revised.docx --artifact-md revised.md --evidence /app/work/edits.jsonl --status complete
```

## 输入 / 输出
- 输入：`/input/case.json`（含 case_id 与 output_contract）、task.md、原稿、修改指令清单。读取真实文件，不按标签猜内容。
- 输出（/app/output）：`result.json`（含全部契约字段，主产物嵌入字符串）、`revised.docx`、`revised.md`、`edits_verify.json`、`check_report.json`、`previews/`（渲染可用时）。
- 工作中间件（/app/work）：structure.json、instructions.jsonl、edits.jsonl、revised_draft.json、constraints.json。

## 最小示意示例（示意，非正式案例结果）
输入（examples/example_input.json）：一节 4 段稿件 + 3 条指令（术语统一、口语化措辞改写、删一句并同步引用编号）。
示意输出：
- edits.jsonl 5 条（2 处术语、2 处措辞、1 处删除+引用联动），每条含 pid 锚点与逐字 anchor_quote；
- `edits_verify → {"edits_total":5,"anchor_fail":0,"apply_fail":0,"unauthorized_changes":0,"verdict":"pass"}`；
- revised.docx/md 中指令未涉及的段落逐字未动。

## 适用范围与限制
- 适用：按明确指令修订 Markdown/docx/PDF 转出的学术稿件；引用编号联动；逐条可受拒修订。
- 限制：原稿为扫描 PDF 时依赖 OCR 质量；样式极复杂的 docx 保留正文与层级、不完全保真复杂表格样式；引用库缺失时只做编号连续性校验，不做外部文献核对。

## 失败处理与自查
- 任一脚本对脏输入不崩溃：输出 `{"ok":false,...,"verdict":"error"}` 报告并继续流程。
- 失败也写 result.json：status 四级（complete/partial/failed/blocked）如实，已有部分结果保留。
- 自查方法：SKILL.md 第 4 节清单逐项核对；`python -c "import json;json.load(open('result.json'))"` 验证 JSON 合法。

## 维护
- 脚本仅标准库，版本随 SKILL.md 一起发布；修改 SKILL.md 流程时同步检查脚本 CLI 参数一致。
