# acwrite-structure — 论文结构与逻辑优化 Skill（可核验性增强版）

针对 Bohrium 第3周学术写作赛道「论文结构与逻辑优化」(challenge-8021aacb) 重做的提交包。

## 一句话方法

把稿件拆成**论断-论据链**做结构诊断（定位到章节/段落/句子，分 8 类结构问题），输出**可执行编辑动作**（move/merge/split/narrow）+ 修订后全文；**每处修改登记逐字前后对照**（original≤40 字逐字 / revised / reason / basis / 段落定位），诊断 issues、论断链、逐字对照、修订全文**全部完整嵌入 result.json** —— 复核者无需打开原稿即可逐条核对。

## 文件清单

| 文件 | 用途 |
|---|---|
| SKILL.md | Skill 本体（强制执行协议置顶 + 线性 5 阶段流程 + 异常处置） |
| scripts/extract_materials.py | 抽取 /input 材料 → 带来源标记的 materials.md + manifest（含 gaps） |
| scripts/docx_build.py | draft.json → 可编辑 revised.docx + revised.md |
| scripts/verify.py | 校验逐字留痕：original 可定位 / revised 已落地 / 无未授权改动 → verdict |
| scripts/build_result.py | 组装 result.json：契约字段一个不缺 + 主产物完整嵌入 |
| scripts/render_preview.py | docx → PDF/PNG 预览（可选，失败不阻塞） |
| examples/example_input.json | 最小调用示例输入（示意） |

## 调用方式（完整流程见 SKILL.md）

```bash
# Stage 0 契约与骨架
python scripts/extract_materials.py --input /input --outdir /app/work/extracted
python scripts/build_result.py --case /input/case.json --out /app/output/result.json --scaffold
# Stage 1-3（模型响应）：claim_chain.jsonl → structure_issues.jsonl → revised 全文 + edits_before_after.jsonl
# Stage 4 校验与交付
python scripts/verify.py --edits /app/work/edits_before_after.jsonl --original /app/work/extracted --revised /app/output/revised.md --out /app/output/verify_report.json
python scripts/build_result.py --case /input/case.json --out /app/output/result.json --embed-diagnosis /app/work/structure_issues.jsonl --embed-edits /app/work/edits_before_after.jsonl --embed-revised /app/output/revised.md --artifact /app/output/revised.docx --verify /app/output/verify_report.json --status complete
```

## 最小示例（标注示意，非正式案例结果）

输入稿件含句子：`实验证明该方法能彻底解决该问题`（实际仅有小数据集 + 3 个百分点提升）。

诊断条目（structure_issues.jsonl，逐条指回原文）：
```json
{"sid":"S01","location":"§3 para1","quote":"实验证明该方法能彻底解决该问题","type":"conclusion_overreach","severity":"high","why":"数据仅小数据集+3pp，支撑不足","fix":"收窄表述","fix_ops":[{"op":"narrow","target":"§3 para1","to":"原位","detail":"收窄为限定条件下结论"}]}
```

逐字前后对照（edits_before_after.jsonl，评分者可直接检索 original 核对）：
```json
{"sid":"S01","location":"§3 para1","original":"实验证明该方法能彻底解决该问题","revised":"在小数据集条件下，该方法较基线提升3个百分点，能否推广到更大规模有待验证","reason":"结论超出数据支持范围","basis":"依据 S01：结论仅由小数据集+3pp支撑"}
```

校验输出（verify_report.json）：`{"edits_total":1,"located_ratio":1.0,"landed_ratio":1.0,"unauthorized_changes":0,"verdict":"pass"}`

以上示例已本地实测通过（docx/md 构建、逐字定位、未授权改动检查、result.json 嵌入）。

## result.json 嵌入字段（65→70 的关键差异）

| 字段 | 内容 |
|---|---|
| `diagnosis.issues` | 全部结构问题（locator/quote/类型/severity/fix_ops） |
| `diagnosis.summary` | 总数 + high 数 |
| `claim_chain` | 论断-论据链全文抽取 |
| `edits_before_after` | 每处修改的逐字前后对照 |
| `revised_text` | 修订后全文（Markdown 字符串） |
| `verify_report` | 动作落地自检结果 |

## 适用范围与限制

- 适用：完整论文/报告/摘要的结构与逻辑诊断；跨学科通用（诊断规则与学科无关）。
- 限制：语句级修复只针对 high 级问题，其余逐字保留；需作者决策的删改标 needs_author 不擅自执行；PDF 解析失败时依赖平台 pdf-text-tool 并登记 gaps。
- 异常处置（截断/缺章节/无研究问题/风格冲突等）见 SKILL.md 第 2 节。
- 依赖：Python 3.8+；python-docx（可选，缺则仅出 md）；pdfminer/PyPDF2（可选）；soffice/docx2pdf（可选，预览用）。全部可选依赖缺失时仍可交付文本产物，状态如实标注。

## 维护

- 脚本均为三级容错（正常 → 替代解析 → 降级登记 gap），exit 0 不阻塞流水线；路径全部可参数化，无平台硬编码。
- 修改 SKILL.md 阶段定义时，同步核对第 4 节自查清单与 build_result.py 的嵌入字段名。
