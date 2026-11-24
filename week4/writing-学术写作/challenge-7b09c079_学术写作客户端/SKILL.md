---
name: acwrite-client
description: 学术写作客户端技能：按修改指令对稿件做外科手术式修订——每处改动生成可定位、可接受、可拒绝的修订条目（锚点/原文/改后/依据/影响面），产出修订稿 docx+md、逐条对照 diff、版本谱系，引用编号联动同步，格式层级不塌。Use when the case asks to revise a manuscript per explicit edit instructions with tracked, itemized, accept/reject edits, preserving structure, citation numbering and editable export.
---

# acwrite-client — 修订客户端（改得准 · 可追溯 · 格式不塌 · 交付可用）

写作客户端的价值在**可控**：改得准（只动指令指的位置）、改得可追溯（每处改动有原位置/改后/依据）、格式不塌（层级/编号/引用联动）、交付可用（可对比、可回退、可继续编辑）。交付三件套：

1. **修订稿**：revised.docx + revised.md（结构完整、可继续编辑）
2. **修订台账**：edits.jsonl（每行一处改动：锚点/原文/改后/依据/层面/影响面）+ diff.md（逐条对照，可逐条接受或拒绝）
3. **版本与边界**：versions.jsonl（版本谱系）+ 未执行指令清单 + uncertainty + changelog

硬规则：**每处改动先在 edits.jsonl 建条目再落稿**；禁止未经指令的整段重写；指令没让动的地方一字不动（错别字也不顺手改，除非指令含"校对"）；材料里没有的事实不编造。

## P. 强制执行协议（每次运行最先执行，不可跳过）

1. **第一步**：读 `/input/case.json` 与 `/input/task.md`，**逐字抄下 case_id 与 output_contract 的全部键名**（写入 `/app/work/contract_keys.txt` 备查）。找不到 output_contract 时立即在 uncertainty 记录缺口。
2. **第二步**：立刻写 `/app/output/result.json` 骨架：
   ```bash
   python scripts/build_result.py --case /input/case.json --out /app/output/result.json --status partial --notes "启动骨架"
   ```
   该脚本会把 case_id 与 output_contract 全键建成 null 字段。之后每完成一个阶段用 `--set 键=值` 回填或重建 result.json——**任何时刻 result.json 都含全部契约键**。
3. **字段一个不缺**：所有契约字段在最终 result.json 中必须有值（字符串/null/数组），填不了的置 null 并在 uncertainty 说明原因。主产物（修订稿全文、edits 台账内容）**同时嵌入 result.json 对应契约字段的字符串值**，并另存外部文件。
4. **广度优先**：先让每个案例都产出骨架+部分诚实结果，再回头加深；单案例严禁先耗尽预算。
5. **熔断**：预算按 **48 次模型请求 / 700 秒**自设熔断线（低于平台 64/900，留余量给校验与收尾）。请求过半时停止展开新分析，转入组装与回填。
6. **写盘前 JSON 自检**：任何 .json 写盘前必须 `python -c "import json;json.load(open('<文件>'))"` 自检（或直接用脚本写盘）。禁止写出非法 JSON。
7. **失败也写 result.json**：任何阶段失败/中断，都必须回到 result.json 写入诚实 status（complete/partial/failed/blocked 四级）+ 已有部分结果 + 失败原因。禁止空结果或假装成功。
8. **单响应 16384 token 上限**：长产物分批写（先骨架后分节追加），不追求一次响应输出全部。

## 1. 主流程（5 步）

### Step 0 — 定契约与材料盘点（脚本 + 1 次响应）
```bash
ls -la /input/ && cat /input/case.json && cat /input/task.md
python scripts/extract_materials.py --input /input --outdir /app/work/extracted
python scripts/build_result.py --case /input/case.json --out /app/output/result.json --status partial --notes "启动骨架"
```
- 按协议第 1、2 步执行。写 `/app/work/constraints.json`：原稿版本标识、指令清单位置、允许的编辑层面（措辞/结构/术语/引用/格式）、格式规范。
- 若输入含 `organizer-edit-workorder.json` 或类似工单：**以工单中的实际修改目标与离线本地流程范围为准**，不得按猜测改。
- 指令没给的部分（如目标期刊格式）在 uncertainty 标缺口，不编造。

### Step 1 — 原稿结构快照 + 指令拆解（1 次响应，产出 structure.json + instructions.jsonl）
- 段落级锚点索引：每个段落 `{"pid":"P12","locator":"§3.2 para4","hash12":"a1b2c3d4e5f6","heading_chain":"3.2>第4段","first_words":"…开头12字"}`。**pid 在修订中永不重编**（删段只标 deleted）。
- 指令拆成可执行条目：`{"iid":"I01","type":"措辞|结构|术语|引用|格式|内容","target":"§3.2 para4 / 全文所有'X'","action":"替换|删除|移动|合并|拆分|重编号|补充","scope_level":"句子|段落|章节|全文","status":"pending"}`。一条指令含多个子要求时逐条拆开。
- 指令冲突或含糊：选保守解释执行，冲突原文记入 ambiguity，uncertainty 说明；不替作者做主。

### Step 2 — 修订台账（1-2 次响应，产出 /app/work/edits.jsonl）
每处改动一行：`{"eid":"E001","iid":"I01","pid":"P12","locator":"§3.2 para4","anchor_quote":"原句逐字(≤120字)","before":"原文本","after":"改后文本","rationale":"依据(指令编号+理由)","level":"措辞","side_effects":["图1编号引用"],"status":"applied"}`
- **外科手术原则**：改句子不动段落，改段落不动章节；before/after 事实内容不变（除非指令就是内容修改）。修订幅度跟指令走："轻度润色"只动词句，"深度改写"才允许段落重组且逐段保留原意。
- **引用/编号联动**：增删引用时参考文献表重排 + 全文编号同步 + 交叉引用检查，联动改动各建一条 edit。
- **格式保持**：标题层级、表格、题注不动（除非指令明确要求）。
- **来源映射**：每条 rationale 必须能追溯到指令条目或材料位置；材料不足以支撑的改动标 `needs_confirmation`，不编造。

### Step 3 — 应用修订并构建（1 次响应 + 1 次脚本）
按 edits.jsonl 从 structure.json 组装 revised draft（保留原结构框架，只替换目标单元），然后分批构建：
```bash
python scripts/docx_build.py /app/work/revised_draft.json --out-docx /app/output/revised.docx --out-md /app/output/revised.md
python scripts/render_preview.py --src /app/output/revised.docx --outdir /app/output/previews
```

### Step 4 — 校验、对照与收尾（3 次脚本 + 1 次响应）
```bash
python scripts/edits_verify.py --edits /app/work/edits.jsonl --original /app/work/extracted --revised /app/output/revised.md --out /app/output/edits_verify.json
python scripts/consistency_check.py --draft /app/output/revised.md --constraints /app/work/constraints.json --out /app/output/check_report.json
```
- edits_verify 检查：① before 能在原稿找到（锚点有效）② after 在新稿找到（落地）③ 未授权改动检测 ④ 引用编号连续。fail → 回 Step 2 修复重跑。
- 写 diff.md：逐条 `E001 [I01] §3.2 para4：~~原句~~ → 新句（依据…）`，标注建议接受/需作者确认。写 versions.jsonl：`{"version":"v2","based_on":"v1","edits_applied":N,"edits_pending":M}`。
- **最终回填 result.json**（用 build_result.py 逐键回填，或分批写盘+JSON 自检）：主产物全文、evidence_map、edits 摘要、检查报告、uncertainty（未执行指令及原因/含糊指令的保守解释/需作者确认项/材料缺口）、changelog、status 四级如实。

## 2. 异常处置表

| 情形 | 处置 |
|---|---|
| 指令指向的位置在原稿找不到 | 记 unresolvable，uncertainty 列出，不猜位置乱改 |
| 指令要求删除的内容影响全文逻辑 | 执行删除 + side_effects 列受影响段落 + 建议性补句（单独 edit 需确认） |
| 原稿是 PDF 无法直接编辑 | 转出可编辑文本层后按流程执行；uncertainty 说明转换损耗 |
| 指令之间冲突 | 保守执行高优先级者，冲突记录 + uncertainty |
| 引用重编号后交叉引用错位 | edits_verify 检出 fail，回 Step 2 修复 |
| 修订与格式规范冲突 | 格式规范优先，指令部分执行 + 说明 |
| 文档损坏/加密/样式无法识别/导出失败 | 诚实记 failed/blocked + 已完成部分；不伪造渲染成功 |
| 多轮返修（输入含上一轮修订） | 版本谱系接续 v(n+1)；上轮承诺逐条核对仍成立 |
| 预算触线 | 立即停止展开，转入收尾：回填 result.json 全键 + 诚实 status |

## 3. 最小调用示例（示意，非正式案例结果）
```bash
python scripts/extract_materials.py --input /input --outdir /app/work/extracted
python scripts/build_result.py --case /input/case.json --out /app/output/result.json --status partial --notes "启动骨架"
# （模型响应：structure.json 38 段 / instructions.jsonl 12 条 / edits.jsonl 47 处改动）
python scripts/docx_build.py /app/work/revised_draft.json --out-docx /app/output/revised.docx --out-md /app/output/revised.md
python scripts/edits_verify.py --edits /app/work/edits.jsonl --original /app/work/extracted --revised /app/output/revised.md --out /app/output/edits_verify.json
# → {"edits_total":47,"anchor_fail":0,"apply_fail":0,"unauthorized_changes":0,"citation_gaps":[],"verdict":"pass"}
python scripts/build_result.py --case /input/case.json --out /app/output/result.json --artifact revised.docx --artifact-md revised.md --evidence /app/work/edits.jsonl --status complete
```

## 4. 交付自查清单
- [ ] result.json 含 case_id 与 output_contract 全部键（无缺字段）；主产物已嵌入字符串字段
- [ ] 每处改动有 edits.jsonl 条目：锚点/原文/改后/依据/层面；依据可溯源
- [ ] edits_verify verdict=pass：锚点全部有效、改动全部落地、零未授权改动
- [ ] 指令逐条有处理结论（执行/部分执行/未执行+原因）；needs_confirmation 项单独列出
- [ ] 引用编号与交叉引用联动正确；标题层级与表格未塌
- [ ] diff.md 可逐条接受/拒绝；versions.jsonl 谱系完整
- [ ] revised.docx/md 可继续编辑；渲染记录真实（失败如实记录）
- [ ] status 四级诚实；uncertainty/changelog 如实；所有 .json 写盘前自检通过
