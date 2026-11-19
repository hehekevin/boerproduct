---
name: acwrite-translate
description: 学术翻译与双语写作技能：先建锁定术语表（含禁用变体清单）再做句段级双语对齐翻译，数字/单位/量级原样落地（万-亿 ↔ million-billion 换算留痕），引用标记/公式/题注/脚注原位保留，否定范围与模糊限制语强度不漂移；主产物（段落级双语对照+术语表+保真核对表）完整嵌入 result.json，逐段可回溯。Use when the case asks to translate academic text (CN↔EN) with segment alignment, locked terminology, preserved numbers/citations/hedges, or produce bilingual parallel manuscripts.
---

# acwrite-translate — 双语对齐翻译（术语锁定 · 禁用变体 · 段级可回溯）

### 增益证据与效率计数（回填 result.json）
必须是**本次运行真跑出来的数字**，不是文字声明：
```bash
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --baseline
python3 scripts/gain_evidence.py --result /app/output/result.json --source <来源材料目录> --write
```
- 第一条：基础模式对照——模拟「不做证据登记/不做逐条回证」的路径，统计源材料里有多少实体与数值会变成不可核对项（需人工逐条核对的规模）。
- 第二条：当前模式实测——证据登记数、证据逐字回证率、三元组 match 通过率、需人工核对条目数，并计算相对基线的削减量；`--write` 写入 `result.json.registry_evidence`（含 `baseline_comparison.reduction` 与 `efficiency` 计数；若本包另有脚本写 `gain_evidence`，两者互补不覆盖）。
- 机检/闸门失败**一律 verdict 照实记录、退出码恒 0**：修一轮，仍不过则如实登记并继续交付，禁止以非零退出码结束会话。

## 0. 强制执行协议（先读，任何情况下不得跳过）

1. **Step 0 必须立即完成三件事**：① 读取 `/input/case.json` 抄下 output_contract 全部字段；② 落骨架 result.json（所有契约字段先写 null）；③ 建 `/app/work` 目录。之后才允许做其他事。
2. **字段一个不缺**：最终 result.json 必须含 output_contract 的每个原始字段 + case_id + status + sources/uncertainty/changelog。字段填不了就填 null 并在 uncertainty 说明，不许删字段。
3. **广度优先**：先让整篇翻译完整走通一遍（所有段都有译文），再回头打磨个别句。禁止把前 3 段打磨完美而后文空白。
4. **预算熔断**：平台预算 64 请求 / 900 秒。自设熔断线 **48 次请求 / 700 秒**：到达任一条，立即停止打磨，跑 Stage 5 收尾脚本，落盘交付。
5. **写盘自检**：每次脚本执行后确认输出文件已生成（`ls` 或脚本回执），失败立即换方案重试一次；连续 2 次失败改用模型直接写文件。
6. **失败也交付**：即使校验 fail / 预算熔断 / 材料缺失，也必须交付已有内容（status 如实标 partial + gap 说明），绝不空手返回。

翻译纪律：**同一术语全篇一个译法，数字一个不错，边界语不漂移，段号一一对应**。硬规则：先建术语表（含禁用变体）再开译，锁定后全篇（含图表题注）不得换译；每个数字落地后与原文核对；增译/省译逐条登记。

## 1. 线性流程（5 步，顺序执行不跳步）

### Step 1 — 定契约与抽材料（1 脚本 + 1 响应）
```bash
ls -la /input/ && cat /input/case.json
python3 scripts/extract_materials.py --input /input --outdir /app/work/extracted
python3 scripts/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
```
- **立即落骨架 result.json**：`python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json`（此时 status=partial）。
- constraints.json 记：源语/目标语、领域、文体、目标读者、既有术语表（有则继承其译法，不另起炉灶）。
- 材料缺失的项：constraints.json 记 `gaps` 列表，不编造。

### Step 2 — 术语表锁定（1 响应，产出 /app/work/terminology.jsonl）
```json
{"src":"tumor microenvironment","tgt":"肿瘤微环境","first_locator":"M01:p1|line5","status":"locked","forbidden":["肿瘤环境","瘤周微环境"]}
{"src":"LASSO","tgt":"最小绝对收缩与选择算子（LASSO）","first_locator":"M01:p1|line8","status":"locked","forbidden":["拉索回归"]}
```
- 抽取：领域术语、缩写（首次展开）、上下位词、机构名/人名/地名；学科惯用译法优先。
- **每条术语必须给 forbidden 禁用变体清单**（常见误译/旧译/口语变体），供 Step 4 机械扫描。
- 同形异义词按语境分条登记；无把握译法标 `status:"pending"`，成稿用直译+括注原文，列入 uncertainty。

### Step 3 — 句段切分与翻译（2-3 响应，产出 segments.jsonl + translation.jsonl）
segments.jsonl：`{"seg":"S001","locator":"M01:p2|para3","src_text":"原句逐字","role":"title|body|figure_caption|table_note|footnote|reference|formula"}` ——保持段落顺序，公式/表格/题注/脚注/文献各自成段，一个不漏。
translation.jsonl：`{"seg":"S001","tgt_text":"译文","number_check":true,"hedge_check":true,"note":…}`
- **术语**：查 terminology.jsonl 用锁定译法；新术语即时补表（带 forbidden）。
- **数字**：数值/单位/量级/范围/年份/样本量原样落地；万/亿 ↔ million/billion 换算在 note 记换算式；有效位数不变。
- **引用**：[n] / (Author, Year) / 上标原位保留；参考文献条目"等"↔"et al." 字段映射，文献名不译。
- **边界语**：否定辖域、模糊限制语（may/suggest/likely ↔ 可能/提示/大概率）不升不降；associated with ↔ 与…相关，不得译成"由…引起"。
- **风格**：目标语学术语域，避免直译腔；不口语化、不宣传化。
- **增译/省译**：逐条写进 note（kind: omission|addition|explicitation + why）——删的是冗余不是证据。

### Step 4 — 组稿与三重校验（1 响应组稿 + 3 脚本校验）
```bash
python3 scripts/docx_build.py /app/work/aligned_draft.json --out-docx /app/output/translation.docx --out-md /app/output/translation_aligned.md
python3 scripts/fact_ledger.py check --draft /app/output/translation_aligned.md --ledger /app/work/fact_ledger.jsonl --out /app/output/number_check.json
python3 scripts/align_check.py --segments /app/work/segments.jsonl --translation /app/work/translation.jsonl --aligned /app/output/translation_aligned.md --terminology /app/work/terminology.jsonl --out /app/output/align_check.json
```
align_check 检查：① 段对齐（段数/段号/role 一一对应）② 数字+单位序列一致 ③ **禁用变体扫描**（terminology.forbidden 在译文出现即 fail）④ 原文术语残留检测 ⑤ 引用标记序列一致。fail → 修 translation.jsonl 对应段后重跑。
number_check：译文中数字必须能在源文台账找到，疑似编造逐条列出。

### Step 5 — 嵌入主产物、渲染、收尾（2 脚本）
```bash
python3 scripts/render_preview.py --src /app/output/translation.docx --outdir /app/output/previews
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact translation.docx --artifact-md translation_aligned.md \
  --embed-pairs /app/work/translation.jsonl --embed-segments /app/work/segments.jsonl \
  --embed-terms /app/work/terminology.jsonl \
  --fact-check /app/output/number_check.json --consistency /app/output/align_check.json \
  --status complete --notes 'pending术语列表;材料缺口' --changelog '关键处理决策'
```
**主产物完整嵌入 result.json**：`bilingual_pairs`（段号/locator/原句/译文/role，与原文一一对应）+ `glossary`（术语/译法/首现位置）+ `fidelity_table`（数字·单位·公式·引用编号核对结果）。result.json 自含可复核，不依赖读者打开其他文件。

## 2. 异常处置表

| 情形 | 处置 |
|---|---|
| 原文含扫描图片文字 | OCR 后按流程；uncertainty 注明 OCR 来源 |
| 公式 | 原样保留（LaTeX/图片），不翻译符号；role=formula 登记 |
| 原文数字本身可疑 | 照译 + note 登记 suspicion，不改原文 |
| 目标语无对应术语 | 直译+括注原文，pending + uncertainty |
| 引用格式与目标期刊不符 | 保留原格式优先；任务明确要求重排时逐条登记 |
| 术语表互相冲突 | 以任务指定/领域权威为准，冲突项列 uncertainty |
| 超长文本逼近熔断 | 分批翻译并即时落盘 segments/translation.jsonl；熔断时已有内容照样交付 |
| 语向/编码异常 | 检测后仍按可读部分交付 + status=partial + gap 说明 |

## 3. 最小调用示例（示意输出，非正式案例结果）

```bash
python3 scripts/extract_materials.py --input /input --outdir /app/work/extracted
# （模型响应：terminology.jsonl 34 条锁定含 forbidden / segments.jsonl 86 段 / translation.jsonl 86 段）
python3 scripts/docx_build.py /app/work/aligned_draft.json --out-docx /app/output/translation.docx --out-md /app/output/translation_aligned.md
python3 scripts/align_check.py --segments /app/work/segments.jsonl --translation /app/work/translation.jsonl --aligned /app/output/translation_aligned.md --terminology /app/work/terminology.jsonl --out /app/output/align_check.json
# → {"verdict":"pass","segments":86,"translated":86,"num_bad":0,"cite_bad":0,"term_viol":0}
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json \
  --embed-pairs /app/work/translation.jsonl --embed-segments /app/work/segments.jsonl \
  --embed-terms /app/work/terminology.jsonl --fact-check /app/output/number_check.json \
  --consistency /app/output/align_check.json --status complete
# → {"ok":true,"pairs":86,"terms":34,"keys":["case_id","bilingual_pairs","glossary","fidelity_table","status",...]}
```

## 4. 交付自查清单
- [ ] result.json 契约字段一个不缺 + case_id + status；骨架在 Step 1 已落
- [ ] bilingual_pairs / glossary / fidelity_table 已嵌入 result.json；段号与原文一一对应
- [ ] terminology 全部 locked（含 forbidden 禁用变体）；pending 项列 uncertainty
- [ ] align_check verdict=pass（段对齐/数字/引用/禁用变体零违规）
- [ ] 数字保真：单位、量级、有效位、年份零改动；换算留痕
- [ ] 边界语强度不漂移；增译/省译逐条登记
- [ ] 公式/表格/题注/脚注/文献原位保留
- [ ] 预算熔断未触发 → status=complete；触发 → status=partial + 已有内容全部落盘
