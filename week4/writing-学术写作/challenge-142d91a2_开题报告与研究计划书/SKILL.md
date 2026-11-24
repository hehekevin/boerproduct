---
name: acwrite-proposal
description: 开题报告与研究计划书技能：从课题指南/前期数据/文献生成"已知-未知-待验证"缺口陈述，研究问题-目标-技术路线-阶段计划-风险-预期成果逐环对齐，里程碑落在给定周期与资源内，风险带触发信号与备选方案，主产物全文内嵌 result.json，每个论断可溯源。Use when the case asks to draft or revise a thesis-opening report / research proposal / research plan (研究背景、问题定义、目标、技术路线、阶段计划、风险、预期成果) from provided scientific materials with milestones, risk plans and auditable source mapping.
---

# acwrite-proposal — 开题报告（缺口立论 · 逐环对齐 · 主产物内嵌）

## 强制执行协议（最高优先级，先读本节再执行任何流程）

以下 7 条是硬性纪律，优先级高于本文档其余内容；与任何步骤冲突时以本节为准。

1. **第 1 步抄契约**：读完 /input/case.json 与题面后，先把 output_contract 的**全部键名逐字抄下**（含嵌套字段），同时记下 case_id。不跳过、不改名、不猜测。
2. **第 2 步落骨架**：第一个写盘动作就是向 /app/output/result.json 写入骨架——case_id + output_contract 全部键（当前无法完成的字段填 unknown 或空数组，绝不省略键），status="partial"。此后任何时刻 /app/output/result.json 必须存在且 JSON 可解析。
3. **字段一个不缺**：最终 result.json 必须含 output_contract 全部键。某项确实无法产出时保留键、填 unknown/空数组，原因写入 uncertainty；不得删键、不得编造数据。
4. **主产物全文内嵌**：开题报告全文（Markdown）必须作为字符串写入 result.json 的 deliverable_content 键（用 build_result.py --embed-file，脚本读文件回填，绕开模型响应 16384 token 截断——**绝不用模型响应直接拼全文 JSON**）。result.json 里只有文件指针而无正文 = 不完整交付。
5. **广度优先 + 熔断**：先让全部产物以最小合格版本存在，再加深。模型请求已用超过 48 次或运行超 700 秒时，立即停止新增处理，用现有中间结果收尾。每次写 result.json 都覆盖为当前最新完整状态。
6. **写盘前自检**：JSON 可解析 / 契约键一个不缺 / case_id 与输入一致 / 全文已嵌入 deliverable_content / status 如实。自检不过先修复再交付。
7. **失败也要交付**：任何中断或失败仍写 result.json（status="failed"，写明中断位置与已完成部分）。status 只用四级：complete / partial / failed / blocked。

## 流程（5 步线性执行）

脚本定位：`SD=$(find /skills -type d -name scripts 2>/dev/null | head -1)`；为空则用 `./scripts`。下文 `$SD/xxx.py` 均指此目录，绝不假设具体安装路径。

### Step 0 读契约、落骨架（最先做）
`cat /input/case.json` 与题面 → 抄 output_contract 全部键名与 case_id → **立即写 /app/output/result.json 骨架**（全部键 + case_id，未完成字段填 unknown，status="partial"）。

### Step 1 材料盘点与事实台账（2 次脚本）
```bash
python $SD/extract_materials.py --input /input --outdir /app/work/extracted
python $SD/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
```
constraints.json 记：研究周期（起止/总月数）、模板章节、培养或资助要求、可用资源（设备/经费/人员）、风险分类要求。周期信息缺失按 3 年默认并标 assumed。

### Step 2 七要素写作（2-3 次响应，分片产出防截断）
每次响应只写一个分片，最后合并；不要试图一次响应写完全文：
- /app/work/draft_p1.json — title/meta + 研究背景与意义 + 研究现状（含 gap 陈述）
- /app/work/draft_p2.json — 研究内容与目标 + 技术路线与方法 + 预期成果与创新点
- /app/work/draft_p3.json — 阶段计划（含进度表）+ 风险应对 + 参考文献 + notes_for_human

写作规则：
- **缺口三段式**：已知（引文献/前期数据，逐条挂 [SRC:mid:loc] locator）→ 未知（缺口）→ 待验证（本研究要做的）。不做文献罗列。
- **问题-目标对齐**：/app/work/plan.jsonl 逐条 `{"qid":"Q1","question":"可证伪的研究问题","objective":…,"gid":"G1","success_criteria":"指标+样本+对照+时间点"}`；1-3 个问题，每问必答、每目标必考。
- **里程碑**：/app/work/milestones.jsonl `{"mid":"MS1","period":"第1-6月","tasks":[…],"deliverable":…,"depends":[…],"resource_check":…}`——总周期不超给定年限；关键路径串行不重叠；资源逐项对照 constraints。
- **风险表**：/app/work/risk_table.jsonl `{"rid","category"(数据/方法/进度/伦理合规),"risk","trigger"(可观察触发信号),"impact","fallback","decision_point"}`——每条风险四件套齐全。
- **引用证据**：关键论断逐条带来源；材料不足处标"缺口/待导师确认"，写入 notes_for_human，不编造。

### Step 3 构建与机检（3-4 次脚本）
```bash
python $SD/docx_build.py /app/work/draft_p1.json /app/work/draft_p2.json /app/work/draft_p3.json \
  --out-docx /app/output/proposal.docx --out-md /app/output/proposal.md
python $SD/fact_ledger.py check --draft /app/output/proposal.md --ledger /app/work/fact_ledger.jsonl \
  --allow /app/work/plan.jsonl /app/work/milestones.jsonl /app/work/risk_table.jsonl \
  --out /app/output/fact_check.json
python $SD/plan_check.py --plan /app/work/plan.jsonl --milestones /app/work/milestones.jsonl \
  --risks /app/work/risk_table.jsonl --constraints /app/work/constraints.json --out /app/output/plan_check.json
```
fail 项修复一轮后重跑；仍 fail 的如实写 uncertainty。计划类数字经 --allow 白名单放行，不再误报。

### Step 4 渲染、组装、自检（2 次脚本 + 自检）
```bash
python $SD/render_preview.py --src /app/output/proposal.docx --outdir /app/output/previews
python $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact proposal.docx --artifact-md proposal.md \
  --embed-file /app/output/proposal.md --embed-key deliverable_content \
  --evidence /app/work/plan.jsonl --fact-check /app/output/fact_check.json \
  --consistency /app/output/plan_check.json --render /app/output/previews/render_log.json \
  --status complete --changelog '七要素取舍与缺口登记记录'
```
自检（协议第 6 条）：看 build_result 输出的自检 JSON——contract_keys_empty 为空、embed_chars > 0、case_id 一致、status 如实。不过先修复重跑再收尾。

## 异常处置

| 情形 | 处置 |
|---|---|
| 无固定模板 | 按通用开题章节组织；模板项 unspecified 登记 |
| 周期信息缺失 | 按 3 年默认并标 assumed；uncertainty 说明 |
| 前期数据不足支撑缺口 | 缺口改写为可验证的初步方向；needs_supervisor 列出 |
| 里程碑资源超出 | 标 needs_adjust + 替代方案；不静默削减验证环节 |
| 材料含扫描件/不可提取 | extract_materials 如实标 extracted:false；缺口写 uncertainty，不猜测内容 |
| 分片损坏/写作被截断 | 重写该分片；仍失败则跳过并在 notes_for_human 与 uncertainty 登记 |
| 脚本缺失/报错 | 全部脚本三级容错不崩溃；仍报错时用现有中间结果按协议第 5/7 条收尾 |
| 接近预算上限 | 立即收尾：已有内容组装 result.json，缺口写 uncertainty，status=partial |

## 最小调用示例（示意，非正式案例结果）

```bash
SD=$(find /skills -type d -name scripts | head -1)
python $SD/extract_materials.py --input /input --outdir /app/work/extracted
# → {"ok":true,"summary":{"total":3,"extracted":3},"materials":[...M01 课题指南.md...]}
python $SD/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
# → {"ok":true,"facts":142,"by_type":{"number":118,"doi":9,"statistic":15}}
# （模型分片写 draft_p1/p2/p3.json + plan.jsonl + milestones.jsonl + risk_table.jsonl）
python $SD/docx_build.py /app/work/draft_p1.json /app/work/draft_p2.json /app/work/draft_p3.json \
  --out-docx /app/output/proposal.docx --out-md /app/output/proposal.md
# → {"ok":true,"builder":"python-docx","sections":9,"markdown":"/app/output/proposal.md"}
python $SD/plan_check.py --plan /app/work/plan.jsonl --milestones /app/work/milestones.jsonl \
  --risks /app/work/risk_table.jsonl --constraints /app/work/constraints.json --out /app/output/plan_check.json
# → {"verdict":"pass","goals":3,"milestones":6,"risks":8,"fail":0}
python $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact proposal.docx --artifact-md proposal.md \
  --embed-file /app/output/proposal.md --embed-key deliverable_content --status complete
# → {"ok":true,"status":"complete","contract_keys_total":8,"contract_keys_empty":[],
#    "embed_key":"deliverable_content","embed_chars":12480}
```

## 交付自查清单

- [ ] result.json 含 case_id 与 output_contract 全部键；deliverable_content 为报告全文字符串
- [ ] 七要素齐全：背景/问题/目标/路线/计划/风险/预期成果；边界写明
- [ ] 问题-目标-路线-里程碑闭环对齐（plan_check pass 或已说明）
- [ ] 里程碑落在周期/资源内；关键路径清晰
- [ ] 风险逐条带触发信号/影响/备选/决策时点；四类覆盖
- [ ] 引用与前期数据可溯（fact_check pass 或 skipped 已说明）
- [ ] proposal.docx/md 可编辑；status/uncertainty/changelog 如实
