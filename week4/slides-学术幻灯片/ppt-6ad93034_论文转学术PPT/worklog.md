# worklog — week4 ppt-6ad93034 参赛包（保底版 + 增益层）

日期：2026-11-19。全部数字来自本机真跑（Python 3.13.14，Windows 11，无 python-pptx / LibreOffice / pip 安装），复制 SKILL.md/README 自检清单即可复跑。

## 1. 与 week3 冠军骨架的差异（为何这么改）

| 变化 | 原因 |
|---|---|
| probe_template.py → probe_input.py | 本题输入新增 slide-workorder.json（mode/页数/受众/保真/继承）与 starting-deck.pptx，探查必须先解析工单并推断 mode |
| extract_pdf.py → extract_source.py | 材料可能是 material.json 而非 PDF；新增四级降级链（PyMuPDF→pdftotext→material_json→起始稿弱基线） |
| pptx_verify.py + layout_budget.py → gate_verify.py | 脚本数压缩到 8；布局预算内联；新增消融开关 `--skip-content-gate / --skip-structure-gate` 供双臂对照 |
| pptx_build.py → deck_build.py | 新增 **edit 模式**：对起始稿整份复制后逐条工单操作原位编辑，工单外页面零改动，applied/fallback/skipped 全记 change_log |
| gain_evidence.py → ablate_gain.py | 增益从"计数对照"升级为"同输入双臂消融 + 污染反例注入"，FAIL 数差是同一校验器机器判定 |
| 全部脚本退出码恒 0 | 硬约束：校验失败/argparse 错误/内部异常一律 exit 0，verdict 照实写 JSON |

## 2. 真跑对照数字（示例输入 examples/，非正式案例）

**主链路**
- probe_input：契约探查（示例目录无 case.json → 如实登记 warning，不臆造）
- extract_source：tool=material_json，pages=1，ok=true
- gate_verify PLAN：verdict=**pass**，fail=0，content_gate=enforced（3 条 quote 逐字回证），数字回证 6/6，structure_gate=enforced（备注/要点/密度/预算全过）
- deck_build generate：builder=pptx_minimal(stdlib)（本机无 python-pptx → 降级链如实登记），3 页产出可编辑 pptx
- gate_verify 构建后：verdict=**pass**，页数 3/3 match
- fit_audit：pages=3，font_match_rate=1.0，min_font_pt=10.0，verdict=**pass**
- render_preview：status=**svg_only_no_pdf**（本机无 soffice → stdlib 逐页 SVG 兜底 3 页，不伪造 PDF）
- deck_build edit：applied=2（set_title+set_notes 原位生效），skipped=1（越界页如实登记），fallback=0

**消融与污染（ablate_gain.py --write 真跑）**
- 同输入双臂（同一校验器 gate_verify 各跑一遍）：full 臂 total_fails=0，ablated 臂 total_fails=0，**干净输入差值=0（诚实结果）**
- 污染反例注入副本（原输入未动）：数字 37.5→37 取整 + 编造 quote → full 臂检出 **1 fail**（numeric_unbacked {"2":["37%"]}），ablated 臂 **0 fail** → **polluted_fail_delta=1，detector_sensitive=true（机器判定）**
- quote 可核验率 3/3=1.0；数字有据率 6/6=1.0
- baseline 对照：baseline_manual_review_items=9（3 页×3）vs skill=0，reduction=9（rate=1.0）——仅本示例规模
- gain_evidence / efficiency 两键已写入 result.json（本包唯一写这两个键的脚本）

**失败路径（逐条实测）**：8 条边界命令（badflag / 不存在输入 × 6 / 缺参数）退出码全为 0，verdict/report 照实落盘。

**自检清单**：SKILL.md 末尾 6 条 + README 十项，逐条 exit 0 实测通过；`test -f` 校验式命中，无 find|head -1；无 str.isalpha 分词（正则实现，规避汉字 isalpha 陷阱）。

## 3. 诚实边界

1. 以上增益数字只在**合成示例输入**上测得（3 页）；平台三固定案例（不同论文类型/模板/工单）上的差值需平台对照确认，本包不预置正式答案。
2. 本机无 python-pptx/LibreOffice，因此实测覆盖的是 **stdlib 兜底路径**（评测沙箱同样无 pip，路径一致）；python-pptx 增强路径（模板克隆填充）只在代码层校验，未本机实跑。
3. stdlib 编辑兜底不支持 delete_slide/move_slide（如实记 skipped）；标题启发式取最顶部文本框，对非常规版式可能 miss（记 fallback 不谎报）。
4. SVG 预览是文本级近似，不替代真 PDF 导出审查；无 Office 环境 export_artifact.status=svg_only_no_pdf。
5. SKILL.md 引用的正式案例契约字段（case_id 等 7 个）以 /input/case.json 运行时实抄为准。

## 4. 剩余风险

- 若正式案例的工单 schema 与示例键名差异大，probe_input 只能抓 raw_keys，mode/页数可能落 unknown（已按"缺键不臆测"设计，模型须回 task.md 补判）。
- fit_audit 字体对账在 python-pptx 缺失时走 raw-xml，模板原始值仅 theme_fonts/theme_colors，槽位几何对账不可用（如实由 inheritance 字段区分）。
