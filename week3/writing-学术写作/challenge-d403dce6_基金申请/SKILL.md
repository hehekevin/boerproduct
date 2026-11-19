---
name: acwrite-grant
description: 基金申请书写作技能：从申报指南/前期成果/文献材料逐章生成立项依据、科学问题、研究目标、研究内容、技术路线、创新点、研究基础与可行性、预算各节。四向对齐表（目标↔内容↔路线↔考核指标）保证逐条对应；创新点写实（vs_existing 对照，禁用"首次/国际领先/填补空白"裸用）；预算数字-来源核对表（无来源不写金额）；关键论断带来源映射，材料不足标缺口不编造；逐章分批写作防截断，主产物全文内嵌 result.json；同输入双跑（正常档 vs 退化档）产出 gain_evidence 使用增益证据。Use when the case asks to draft grant/proposal sections (立项依据/科学问题/研究目标/技术路线/创新点/可行性/预算) from guide texts and prior-work materials with objective-content-route-metric alignment and traceable evidence.
---

# acwrite-grant — 基金申请书写作（逐章分批 · 四向对齐 · 预算溯源 · 双跑增益证据）

申请书写作的最大风险是**一次性输出全稿被截断**、**数字编造**（预算金额、样本量、指标值），以及**自述"已核对"却拿不出证据**。本技能用**逐章分批写作 + 数字来源核对 + 同输入双跑对照**管住这三点。交付四件套：

1. **章节稿**：grant.docx + grant.md（七章逐章可编辑），全文内嵌 result.json
2. **溯源与对齐**：evidence_map.jsonl + alignment.jsonl/routes.jsonl（四向对齐）+ budget_ledger.jsonl + innovation_vs_existing.jsonl
3. **版本与边界**：notes_for_human（待确认项）+ 材料缺口 + changelog
4. **增益与效率证据**：gain_evidence.json（同输入正常档 vs 退化档逐项对照）+ efficiency.json（步骤数/人工核对条目/复现命令）

硬规则：**先立对齐表再动笔**；每章一次响应写完即落盘、即回填 result.json；实质性论断无来源不落稿；金额无来源不写数字（标 missing）；前期成果"已完成/拟开展"二态分清。

配套资源（可复用，也可直接用于他人自己的申请）：`resources/grant_toolkit.md`（七要素清单 + 四向对齐检查表 + 三张台账落盘格式 + 禁用修辞词表）、`resources/score_sheet.md`（五维自评评分表 + 交付前十问）、`resources/practice_set.md`（自建题集，无预制答案）。

## 强制执行协议（最高优先级，先读本节再执行任何流程）
以下 7 条是硬性纪律，优先级高于本文档其余内容；与任何流程步骤冲突时以本节为准。
1. **第 0 步落骨架**：读完 /input/case.json 与题面后，第一个写盘动作就是在 /app/output/result.json 写入骨架：case_id 取自 case.json；键名严格按 output_contract 声明的每个字段生成（暂无法完成的字段填 unknown/空数组，绝不省略键）；status 填 "partial"。此后任何时刻 /app/output/result.json 必须存在且 JSON 可解析。
2. **字段一个不缺**：最终 result.json 必须包含 output_contract 全部键。某项确实无法产出时，保留键并填 unknown/空数组/说明字符串，原因写入 uncertainty；不得删键、不得编造数据。
3. **逐章分批防截断**：申请书全文禁止在一次响应中写完。每章独立 1 次响应，写完立即落盘 /app/work/chapters/chNN_*.md，并立即用 build_result.py --embed-file --append 回填进 result.json。单章也不超过该章目标字数的 1.2 倍，写不下先落盘已写部分、下章响应续写。
4. **广度优先 + 熔断**：先让全部要求的章节/字段以最小合格版本存在，再对高价值章节加深。模型请求超过 48 次或运行超过 700 秒：立即停止新增写作，用现有章节组装 result.json 收尾（缺章在 uncertainty 说明）。每次写 result.json 都是覆盖保存当前最新完整状态。
5. **数字-来源核对**：预算金额、样本量、指标值、时间节点等一切数字，落稿前先入 budget_ledger.jsonl 或 evidence_map.jsonl（locator+逐字摘录）；无来源的金额只能标 status=missing 且正文写占位符；无来源的量写成"拟/约/按 X 估算"并挂账。机检不过的数字必须删除或降级为假设。
6. **最终写盘前自检**：JSON 可解析、output_contract 字段一个不缺、case_id 与输入一致、status 如实四级（complete/partial/failed/blocked）、**7 章全部出现在 embed_gate 且状态=embedded**、align_check verdict 与 fail 数一致、gain_evidence 两档记录齐全、output_contract_map.elements 全部 filled。自检不过先修复再交付。
7. **失败也要交付**：处理中断或失败时，仍写 result.json（status="failed"，写明中断位置与已完成部分），绝不让 /app/output 缺少 result.json。**所有脚本失败路径退出码恒为 0**（判定看报告里的 verdict/fail/problems，不得用退出码中断交付链）；脚本异常时如实登记到 uncertainty。

## 流程（5 步线性执行）

脚本定位（不假设安装路径，且**校验命中的是本技能自己的脚本目录**，避免多个 skills 挂载时选错）：
```bash
SD=""
# ① 平台约定挂载点（题面：evaluator 把 Skill 装入 /skills/weekly-skill）
[ -f "/skills/weekly-skill/scripts/align_check_grant.py" ] && SD="/skills/weekly-skill/scripts"
# ② 兜底扫描：命中条件是本技能独有标志文件 + 增益脚本，避免选到别的包的 scripts
SCRIPT_DIR=""
for d in /skills/weekly-skill/scripts ./scripts scripts; do
  if [ -f "$d/align_check_grant.py" ]; then SCRIPT_DIR="$d"; break; fi
done
if [ -z "$SCRIPT_DIR" ]; then
  SCRIPT_DIR=$(find /skills /app -type d -name scripts 2>/dev/null | while read -r d; do [ -f "$d/align_check_grant.py" ] && echo "$d" && break; done)
fi
[ -n "$SCRIPT_DIR" ] || SCRIPT_DIR="./scripts"   # 兜底：相对路径 + 如实登记，不臆造路径

  [ -f "$d/align_check_grant.py" ] && [ -f "$d/gain_evidence.py" ] && { SD="$d"; break; }
done; fi
# ③ 按标志文件反查目录；④ 相对路径兜底。仍找不到则按协议第 7 条如实登记，不臆造路径
if [ -z "$SD" ]; then SD=$(dirname "$(find /skills /app /opt . -name align_check_grant.py 2>/dev/null | head -1)"); [ -f "$SD/align_check_grant.py" ] || SD=""; fi
if [ -z "$SD" ] && [ -f "./scripts/align_check_grant.py" ]; then SD="./scripts"; fi
[ -n "$SD" ] || SD="scripts"
```
`align_check_grant.py` 是本技能独有的标志文件（别的 skill 不会同名），用它命中可避免选到别的包的 scripts。下文 `$SD/xxx.py` 均指此目录。**Step 1 前先确认 `$SD` 非空**（`ls "$SD"` 可见 8 个脚本），为空说明未正确挂载 → 按协议第 7 条如实登记，不要臆造路径。

### Step 0 读契约、落骨架（最先做）
`cat /input/case.json` 与题面 → 抄下 output_contract 全部键名与 case_id → **立即写 /app/output/result.json 骨架**（全部键+case_id，未完成字段填 unknown，status="partial"）。同时记 constraints：required_sections、word_range、citation_style、目标基金类型。

### Step 1 材料盘点与事实台账（3 次脚本）
```bash
python3 $SD/extract_materials.py --input /input --outdir /app/work/extracted
python3 $SD/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
python3 $SD/fact_ledger.py prior --evidence /app/work/evidence_map.jsonl --out /app/work/prior_work.jsonl
```
读 manifest 分类登记：指南条款（限项/格式/周期/资助强度）、前期成果（**已完成/拟开展二态**）、文献、团队平台；缺口记入 constraints.json。第三条（prior）待 evidence_map 就绪后再跑，未产出则跳过并写 uncertainty。

### Step 2 四向对齐表 → 逐章分批写作（每章 1 次响应，核心步）
先建 alignment.jsonl（每个 goal 含 contents/routes/metrics 与可考核指标）与 routes.jsonl（每条路线含 steps[input/out/节点/风险/备选]），均在 /app/work/。然后按顺序逐章写作，**每章一次响应**：先写 /app/work/chapters/chNN_xxx.md，随后立即回填：

```bash
python3 $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --embed-file /app/work/chapters/chNN_xxx.md --embed-key deliverable_content --append
```

各章写法要点：
- **ch01 立项依据**：按"别人做到哪（引文献）→还差什么→为什么是申请人→为什么是现在"组织；每句实质论断挂 evidence_map（**kind/逐字摘录≤40字/source_id/location** 四字段齐全）。
- **ch02 科学问题与研究目标**：科学问题收敛 1-3 个，各写判断标准（什么结果算回答）；目标数量与 alignment 的 goal 一一对应。
- **ch03 研究内容**：与 goal 的 contents 对应项逐条展开；**数字（样本量/周期/数据量）无来源标"拟"** 并挂账。
- **ch04 技术路线**：按 routes.jsonl 展开：输入/输出/关键节点/风险/备选；写可行性依据，不罗列方法名。
- **ch05 创新点**：**先写 /app/work/innovation_vs_existing.jsonl 结构化对照表**（每条：{claim, vs_existing_who, difference, why_can_win, evidence_locator}），再据表成文；正文与表同时落盘，终稿组装时嵌入 result.json；**无对照依据禁用"首次/国际领先/填补空白"**。
- **ch06 研究基础与可行性**：只写材料可证实的成果（二态分清）；**每条前期成果逐字摘录进 evidence_map**（kind=prior_work，evidence≤40字，location 到文件+页/段），正文挂 source_id；写能力-证据-与本研究的关系；缺口列 notes_for_human。
- **ch07 预算（如有要求）**：逐条先入 budget_ledger.jsonl：`{"item":"…","amount":45.0,"source_locator":"M02:p3","status":"sourced|assumed|missing"}`；无来源金额不写数字，正文写占位符标 missing。**与研究内容数字互核：预算口径与内容工作量一致**。

字数超限先压背景综述，不动技术路线与指标。

### Step 3 合稿与机检（4 次脚本）
```bash
python3 $SD/merge_chapters.py --chapters-dir /app/work/chapters --out /app/work/draft.json --title "…"
python3 $SD/docx_build.py /app/work/draft.json --out-docx /app/output/grant.docx --out-md /app/output/grant.md
python3 $SD/fact_ledger.py check --draft /app/output/grant.md --ledger /app/work/fact_ledger.jsonl --out /app/output/fact_check.json
python3 $SD/align_check_grant.py --alignment /app/work/alignment.jsonl --routes /app/work/routes.jsonl \
  --draft /app/output/grant.md --budget /app/work/budget_ledger.jsonl --out /app/output/align_check.json
```
fail 项修复一轮后重跑；仍 fail 的项如实写入 uncertainty（孤儿目标/不可考核指标/禁用断言/无来源预算必须修）。

### Step 4 双跑增益证据（2 次脚本，同输入两档）
```bash
python3 $SD/gain_evidence.py --work /app/work --out /app/output/gain_evidence.json \
  --efficiency-out /app/output/efficiency.json --case /input/case.json --draft /app/output/grant.md
```
该脚本对**同一份产物**跑两遍：正常档（全机制）与退化档（移除对照表/预算台账/逐字台账并 `--ablate innovation,budget` 关闭强制检查），输出逐项对照指标（章节完整率／创新点 vs_existing 覆盖数／预算可溯源率／需人工核对条目数／步骤数）、两遍真实运行记录、机制→指标映射与边界声明。**禁止手写这些数字**——必须由脚本实跑产生；退化档数字不得被当作平台 base-agent 对照结果宣传。

### Step 5 渲染、组装、自检（2 次脚本 + 自检）
```bash
python3 $SD/render_preview.py --src /app/output/grant.docx --outdir /app/output/previews
python3 $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --artifact grant.docx --artifact-md grant.md \
  --evidence /app/work/evidence_map.jsonl --fact-check /app/output/fact_check.json \
  --consistency /app/output/align_check.json --render /app/output/previews/render_log.json \
  --gain-evidence /app/output/gain_evidence.json --efficiency /app/output/efficiency.json \
  --prior-work /app/work/prior_work.jsonl --budget-ledger /app/work/budget_ledger.jsonl \
  --notes-file /app/work/notes_for_human.json \
  --embed-file /app/output/grant.md --embed-key deliverable_content \
  --embed-chapters-dir /app/work/chapters \
  --embed-file /app/work/innovation_vs_existing.jsonl --embed-key innovation_vs_existing \
  --status complete --changelog '取舍记录'
```
组装后 result.json 含：deliverable_content 全文 + chNN_* 七章独立键 + embed_gate（embedded/not_found/unreadable，缺章自动写入 uncertainty，下游不得宣称全稿已核对）+ innovation_vs_existing + budget_ledger + prior_work + notes_for_human + align_check 的 checks（{item,template_value,applied,match}）与 gates（enforced/skipped_not_provided/not_found/unreadable）+ gain_evidence + efficiency + **output_contract_map**（题面三行与 5 个点名要素逐条对照，filled 状态可见）。

## 异常处置

| 情形 | 处置 |
|---|---|
| 无申报指南/模板 | 按目标基金通用章节组织；模板项标 unspecified；uncertainty 说明 |
| 前期成果材料不全 | 只写可证实的；缺口列 gaps + uncertainty；已完成/拟开展绝不混淆 |
| 预算信息缺失 | 逐条标 status=missing，金额写占位符；不编造金额；notes_for_human 提示人工核定 |
| 科学问题过大 | 收窄并在 changelog 记依据 |
| 单章响应被截断 | 已写部分先落盘回填；下一响应只写余下小节再合并 |
| 熔断触发（48 次/700 秒） | 立即收尾：已有章节组装，缺章与未核数字写 uncertainty |
| 脚本缺失/报错 | 全部异常捕获、如实登记；用现有中间结果走协议第 4/7 条；退出码恒 0 不中断交付 |
| 平台不提供对照 | gain_evidence 照常产出退化档，boundary 注明"官方对照未提供，本对照仅为结构退化模拟" |

## 最小调用示例（示意，非正式案例结果）
`SD` 用上文"流程"节的定位块解析；全流程命令见 Step 1–5，关键调用与示意输出：
```bash
# （模型逐章响应：ch01.md 立项依据 4 段带 evidence_map / ch07.md 预算 6 条全部 status=sourced）
python3 $SD/build_result.py --case /input/case.json --out /app/output/result.json \
  --embed-file /app/work/chapters/ch01.md --embed-key deliverable_content --append
python3 $SD/align_check_grant.py --alignment /app/work/alignment.jsonl --routes /app/work/routes.jsonl \
  --draft /app/output/grant.md --budget /app/work/budget_ledger.jsonl --out /app/output/align_check.json
# → {"verdict":"pass","goals":3,"budget":6,"types":[],"checks":[{item,template_value,applied,match}...],"gates":[{"gate":"budget_check","status":"enforced"}]}
python3 $SD/gain_evidence.py --work /app/work --out /app/output/gain_evidence.json \
  --efficiency-out /app/output/efficiency.json --case /input/case.json --draft /app/output/grant.md
# → {"normal":{"innovation_vs_existing_covered":3,...},"degraded":{"innovation_vs_existing_covered":0,...}}
```

## 交付自查清单

- [ ] result.json 含 case_id 与 output_contract 全部键；deliverable_content 为申请书全文（逐章回填）
- [ ] output_contract_map.elements 五项（各章正文/创新点对照/前期基础/预算/待确认项）全部 filled
- [ ] 每章独立落盘且回填过（embedded_files 有记录）；**7 章 chNN_* 键 + embed_gate 全部 embedded**
- [ ] 四向对齐无孤儿项；指标可考核；路线含输入输出/风险/备选；align_check 含逐条 checks 三元组
- [ ] 创新点有 innovation_vs_existing 对照表且已嵌入 result.json；无"首次/领先/填补空白"裸用
- [ ] 研究基础每条前期成果有 kind=prior_work 逐字摘录（≤40字）+ location；已完成/拟开展二态清楚；prior_work 已嵌入
- [ ] 未运行的检查 gate=skipped_not_provided 且 gate_note 写明"下游不得宣称已核对"
- [ ] budget_ledger 逐条有 status；无来源金额未落数字；预算与内容口径一致；budget_ledger 已嵌入
- [ ] gain_evidence 两档（normal/degraded）记录齐全、指标为脚本实跑产生、含机制→指标映射与边界；efficiency 含步骤数与复现命令
- [ ] 引用真实可溯（fact_check pass）；grant.docx/grant.md 可编辑；渲染记录真实（无渲染器如实标 no_renderer）
- [ ] status/uncertainty/changelog 如实（complete/partial/failed/blocked 四级）
