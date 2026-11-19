# worklog — paper2template-skill v4（w10-s3，ppt-710fbc72 周4版）

日期：2026-11-19 ｜ 执行者：w10-s3 ｜ 底座：第3周 83 分 ppt-710fbc72/ppt-c7b80f0d 脚本线（本地 Python 3.13.14 纯标准库环境实测，恰好复现评测沙箱降级链；以下全部为本地真跑数字，非正式案例结果）

## 一、差距分析：第3周骨架对照周4题面六要素

| # | 周4题面要素/硬约束 | 第3周骨架现状 | v4 处置 |
|---|---|---|---|
| 1 | 失败路径一律 exit 0（校验失败/main return/--selftest FAIL/argparse error） | fit_audit `sys.exit(1/5)`、extract_pdf `sys.exit(4)`、render_preview `sys.exit(2/3)` 共 5 处非零退出路径 | 全部改写为 `return 0` + JSON 如实登记（fit_audit/extract_pdf/render_export/verify/build）；实测 S7（缺 pptx）、S9（非法 deck.json）、S3（缺参）均 rc=0 |
| 2 | 模板套用（母版/版式/占位符真实继承） | probe_template 依赖 python-pptx，沙箱必走"探查失败"降级 | **probe_template 重写为纯 stdlib（zipfile+ET）**：实测探查自建 deck.pptx → ok:true, layouts:1, majorFont=Arial/ea=Noto Sans CJK SC，探查永不因缺库失败 |
| 3 | 批量一致性（页脚/页码/标题位置/字号层级整册统一） | 无整册一致性审计 | **新增 render_export.py**：页码逐页正确性、标题字号 ≤2 档、标题 x 跨页漂移 ≤0.05in、正文阶梯合规 |
| 4 | 图表适配（等比缩放、变形抓捕、图号与正文引用配对） | builder contain-fit 但无变形/错位审计 | render_export：image_aspect（框比 vs 源图比 >5% 即 fail）+ figure_ref_alignment（Fig.N 配对）；实测 N6 抓到 cx×2 注入（ratio_box 2.667 vs ratio_src 1.333）、N5 抓到悬空 Fig.99 |
| 5 | 导出渲染横切（导出与 pptx 一致、字体替换/图片丢失记录） | render_preview 只渲染不校验 | render_export：pdf 页数 vs pptx 页数对账 + image_loss（pic 引用 vs media 文件）+ 无渲染器如实记 pptx_only_no_renderer |
| 6 | 增益可验证性（公平对照 + 消融） | gain_evidence 只有 baseline 对比计数 | **gain_evidence 新增 --ablate 消融双臂真跑**：污染反例注入副本（quote 改写/证据行删除/悬空图号），同一校验器 run_gates 各跑一遍，逐闸门 FAIL 数差 + 机制→指标映射 + 边界 + 失效条件写入 gain_evidence/efficiency 两键 |
| 7 | 遗留缺陷 | 周3 layout_budget.measure_lines 恒返 0（`return 0` 死代码在正常路径上），字号预算实际失效；pptx_minimal 对 bullets+figure 混排不嵌图 | 修复合入 pptx_verify 内联版（阶梯预算恢复生效）；pptx_minimal bullets 带图自动升级 bullets+figure（实测修复后 verify fail 1→0） |
| 8 | isalpha 汉字陷阱 | 无显式防护 | CJK 判定一律用 `\u2E80-\u9FFF` 区段正则（text_em_width），不用 str.isalpha；SKILL.md 协议第 8 条禁 `find\|head -1` 式命中 |

保留第3周全部已验证机制：执行协议 7 条、闸门四态、quote/数字回证、slides_embed 全量内嵌、pptx_minimal 兜底、status 四级、degrade_chain。不推翻、不重构。

## 二、多脚本写键隔离

result.json 键位分配：`gain_evidence` 与 `efficiency` **仅** gain_evidence.py 写入（--write 时）；fit_audit 写 fit_audit.json 侧文件由 SKILL 指示内嵌为 format_fit_table/consistency_audit；verify 的 slides_embed 内嵌 deliverable.slides。无任何两脚本写同一键。

## 三、双测证据（本地 Python 3.13.14 纯 stdlib，非正式案例结果）

### 正例全链路（合成 case：4 页 deck + 论文原文 + 7 行 evidence + 1 张 400x300 PNG）
```
probe_template.py 自建 deck.pptx → {"ok":true,"layouts":1,"majorFont":{"latin":"Arial","ea":"Noto Sans CJK SC"}} rc=0
pptx_verify.py PLAN             → {"fail":0,"warn":0,"verdict":"pass", quote_gate:enforced, numeric_unbacked:{}} rc=0
pptx_build.py（无 python-pptx）  → builder: pptx_minimal(fallback, stdlib-only) | warnings:0 rc=0   ← 降级链实测
pptx_verify.py 构建后(raw-xml)   → {"fail":0,"warn":0,"verdict":"pass"} rc=0
render_export.py --audit-only   → {"consistency_fail":0,"verdict":"pass"} rc=0（页码/阶梯/位置/图号/变形全过）
render_export.py 完整渲染        → render.status=pptx_only_no_renderer rc=0（本机无 soffice/pdftoppm/fitz，如实登记不伪造）
fit_audit.py                    → {"fail":0,"warn":2,"verdict":"pass"}，gate 2 条 not_run notes（无模板报告/无基线）；加 --baseline 后 diff_changed_pages=0 rc=0
gain_evidence.py（skill 模式）    → pages_with_evidence 4/4=1.0；quote_verifiable_rate 1.0（6/6 逐字回证）；numeric 11/11=1.0；基线对照 12→0 条人工核对（削减 12，100%）rc=0
```

### 消融双臂（--ablate 真跑数字）
```
注入：quotes_reworded=2（存活行改写），证据行删除致 1 页失去覆盖，悬空 Fig.99 注入 slide3
臂A(full)  run_gates → quote_gate_fail=0, coverage_fail_slides=0, numeric_unbacked=0, total_fail=0
臂B(polluted) run_gates → quote_gate_fail=2, coverage_fail_slides=1, numeric_unbacked=4, total_fail=3
逐闸门差：quote +2（=改写数 2）、coverage +1（=失覆盖页数 1）、numeric +4   ← 全部机器判定
verdict.gates_catch_pollution=true；efficiency.ablation_gate_fail_diff=1（total 差）
--write 后 result.json 键：case_id/deliverable/efficiency/gain_evidence/gates/status，写盘成功
```

### 反例抓捕（闸门真的在抓）
```
N1 改写 quote（1.5x→1.9x）      → quote_not_found_in_paper fail=1 + 覆盖缺页 fail=3, verdict=fail, rc=0
N2 缺 --paper                   → quote_gate=skipped_not_provided, warn=1（未跑≠通过）, rc=0
N3 evidence 行损坏              → evidence_json_parse_error, rc=0
N5 悬空 Fig.99 引用             → figure_ref_alignment: reference_no_caption=[99], verdict=fail, rc=0
N6 图片拉伸（pic cx×2 注入）     → image_aspect: distorted=[{ratio_box:2.667, ratio_src:1.333}], verdict=fail, rc=0
S3 pptx_minimal 缺参            → usage 提示, rc=0
S5 extract_pdf 缺失文件         → {"ok":false,"error":"not_found:..."}, rc=0
S6 非 PDF 材料                  → plain_copy 降级, rc=0
S7 fit_audit 缺失 pptx          → {"verdict":"fail","note":"审计未执行，下游不得宣称已核对模板落点"}, rc=0
S8 无渲染器完整渲染             → pptx_only_no_renderer, rc=0
S9 非法 deck.json（main 崩溃）   → crash 如实登记 exit 0, rc=0
```

## 四、诚实边界与剩余风险

1. 模板真实继承路径（python-pptx 克隆填充 + fit_audit 全量对账）本机未端到端实跑——本地无 python-pptx；该代码与第3周 83 分包同源未改逻辑，其 worklog 有完整实测记录（fit_match_rate=1.0）。本包改动仅在失败退出码与 raw-xml 兜底路径。
2. raw-xml 对账模式不读母版名/占位符 idx/主题色继承值（python-pptx 可用时才全量）；raw 模式 format_fit 的 layout 维度仅校验"可解析"，已在 note 中写明。
3. 渲染链（soffice/PNG/pdf 页数对账）本机无渲染器，仅验证到 status=pptx_only_no_renderer 的如实登记路径；有渲染器环境的 ok 路径沿用第3周已验证代码。
4. 消融注入为程序化污染（数字取整/尾符改写/删行/悬空图号），未覆盖"同义改写保持逐字子串"场景——该场景逐字闸门原理上抓不到，已写入 mechanisms.boundary。
5. 拉伸变形抓捕依赖源图像素可读（png/jpg 头解析）；矢量图（svg/emf）无像素头时跳过该页检查（checked< pics），如实在 detail 中留空。

## 版本

- v4-w10s3（2026-11-19）：周4 参赛包。probe stdlib 重写；render_export 新增；gain_evidence --ablate；exit-0 全量修复；measure_lines/pptx_minimal 缺陷修复；8 脚本 13 文件。
