# reading-client-loop — 阅读客户端 MVP Skill（week3 文献阅读赛道 · challenge-f730fc37）

## 用途

在**同一处**走完科研阅读闭环：打开文献 → 定位段落 → 选中文本提问 → 保存批注 → 回看复核。
所有答案绑定逐字原文锚点（paragraph_id + 逐字引文 + offsets），批注与阅读位置落盘可回看可导出，
最终产出一个自包含交互式阅读客户端页面（reading_client.html）作为主产物。

## 安装与依赖

- 无第三方依赖：脚本仅用 Python 3.8+ 标准库。PDF 解析优先用 PyMuPDF（fitz），缺失时自动退化到
  pypdf，两者都没有则按无文本层降级为页码级定位（不崩溃）。
- 无需安装步骤：把本目录（SKILL.md + scripts/）整体放进 Skill 安装位置即可
  （平台评测时位于 /skills/weekly-skill）。
- 脚本自测：`python scripts/make_result.py --selftest && python scripts/build_locator.py --selftest
  && python scripts/export_client.py --selftest && python scripts/check_all.py --selftest`
  （4 组合成正例+反例，全部应 PASS）。

## 调用方式（完整流程五步）

输入：`/input/case.json`（含 case_id / task_instruction / output_contract / 材料）+ task.md；
产物：`/app/output/` 下 result.json、annotations.json、reading_log.jsonl、reading_client.html。

```bash
S=$(ls -d /skills/weekly-skill/scripts ./scripts 2>/dev/null | head -1)
# 1. 抄契约+落骨架（保证 output_contract 字段一个不缺）
python "$S/make_result.py" --init --case /input/case.json --out /app/output/result.json
# 2. 建段落定位索引（paragraph-json/txt/md/pdf；扫描件降级页码级）
python "$S/build_locator.py" --case /input/case.json --out /app/work/locator.json --input-root /input
#    关键词定位（不耗模型请求）：加 --find "关键词"
# 3. 逐问选区问答（上下文=选中文本+所在段落；答案+逐字证据锚点；逐问 --merge 落盘）
python "$S/make_result.py" --merge --case /input/case.json --result /app/output/result.json --patch /app/work/qa1.json
# 4. 批注落盘 + 生成交互客户端（选区/证据高亮、问答一键跳回原文、搜索、段落跳转）
python "$S/export_client.py" --result /app/output/result.json --annotations /app/output/annotations.json --locator /app/work/locator.json --out /app/output/reading_client.html --embed-result
# 5. 机械自检（契约字段/锚点逐字/offsets/产物存在/嵌入一致/claims 结构），PASS 才算完成
python "$S/check_all.py" --result /app/output/result.json --annotations /app/output/annotations.json --case /input/case.json --locator /app/work/locator.json
```

## 输入输出

- 输入材料形态：paragraph-json / txt / md / pdf（含扫描件）。
- `result.json` 顶层 = output_contract 全部字段（默认 case_id / status / result / claims /
  uncertainties）；status 四级诚实取值 answered / partial / insufficient_evidence / input_error。
- 主产物客户端整份 HTML 同时嵌入 `result.result.client.embedded_html`（字符串）并另存外部文件。
- 每条关键结论在 claims 中带 kind / source_id / location / evidence（逐字引文）；
  无法判断的写进 uncertainties，不编造。

## 最小调用示例（示意输出，非正式案例结果）

合成输入（2 段材料，问"Alpha 方法提升多少？"）的示意产物：

- result.json（节选）：`{"case_id":"T1","status":"answered","result":{"qa":[{"question_id":"q1",
  "answer":"recall 提升 12%","selection":{"paragraph_id":"p01","quote":"Alpha improves","offsets":[0,14]},
  "evidence":[{"paragraph_id":"p01","quote":"recall by 12%","page":1}],"status":"answered"}],
  "client":{"kind":"self-contained-html","embedded_html":"<!DOCTYPE html>…"}},"claims":[{"kind":"reported",
  "source_id":"T1","location":"p01","evidence":[{"quote":"recall by 12%"}]}],"uncertainties":{"summary":"无"}}`
- reading_client.html：p01 内选区黄色高亮、证据绿色高亮；右栏问答卡片带"回看选区 p01"链接，
  点击平滑滚动到原文段落并闪烁提示；顶部有关键词搜索与段落号跳转。

以上为**示意**，冒充正式案例结果是不允许的；实际运行以平台固定案例输入为准。

## 适用范围与限制

- 适用：单篇/少量科研材料的定位、选区问答、锚定批注、阅读记录导出。不要求覆盖完整阅读客户端系统。
- 限制：PDF 物理页与印刷页不一致时以物理页为准；扫描件无文本层时定位降级为页码级并如实标注；
  `--find` 为精确子串匹配（忽略空白差异），不做语义检索；客户端为静态单文件交互页，不含在线协作。

## 维护

- 自检与降级内建于脚本（全 except Exception、失败也写盘）；改动脚本后重跑 4 组 --selftest。
- 设计与重做记录见 worklog.md。
