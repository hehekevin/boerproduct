# paper2deck-edit-skill — 学术 PPT 生成与编辑（week4 slides 赛道）

读工单（mode/页数/受众/保真/模板继承）→ 材料提取 → 排页与证据映射（逐字 quote 回证）→ 双闸门 → 构建（generate 模板克隆 / edit 原位编辑保真其余页）→ 模板对账 → 三级渲染 → 双臂消融真跑增益。产出原生可编辑 presentation.pptx 与 result.json 全契约字段。

## 一、用途与适用场景

把一篇论文/研究材料组织成可上台讲的学术演示稿，或按工单编辑已有起始稿（改标题/要点/备注/删页/重排），每页内容可回溯到材料原文。适用于组会汇报、开题中期、答辩、项目评审。**不负责**：论文精读与文献综述、数据可视化算法本身、文字润色、PPT 软件开发。

## 二、资源清单

```
SKILL.md            执行协议 + 线性 6 步主流程 + 降级链 + 最小示例 + 自查清单（144 行）
README.md           本文件
worklog.md          真实对照数字 + 诚实边界
scripts/            8 个，纯 Python（优先标准库，零外部依赖）
  probe_input.py      契约抓取 + slide-workorder 解析 + 模板/起始稿探查
  extract_source.py   材料提取：PyMuPDF→pdftotext→material.json→起始稿四级降级
  gate_verify.py      双模式校验器：PLAN 构建前闸门 / 构建后校验
                      （内容对齐闸门：quote 逐字回证+数字回证；结构闸门：页数/备注/要点/密度/布局预算）
  deck_build.py       构建：generate（python-pptx 模板克隆 / pptx_minimal stdlib 兜底）
                      edit（工单逐条原位编辑，applied/fallback/skipped 全记 change_log）
  pptx_minimal.py     stdlib OOXML 兜底构建器（无 python-pptx 时保持可编辑性）
  fit_audit.py        模板合规对账：字体/配色/继承链，compliance_checks 数据源
  render_preview.py   渲染：soffice PDF+PNG → COM → stdlib 逐页 SVG 三级降级
  ablate_gain.py      增益层：--ablate 双臂消融 + 污染反例注入（写 gain_evidence/efficiency）
examples/           示意数据（非正式案例）：material.json / deck.json / evidence.jsonl
```

## 三、依赖与安装

- Python 3.8+，**零外部依赖**：全部脚本优先标准库；预装 python-pptx / PyMuPDF 时自动走增强路径（模板克隆、图片提取），缺失时自动降级 stdlib 兜底并如实登记，产物仍可交付。
- 无网络 / CDN / 浏览器 / node 依赖；渲染无 Office 时自动落到手写 SVG 逐页预览。
- 运行路径按平台契约：输入 `/input`，工作区 `/app/work`，产物 `/app/output`。

## 四、调用方式（一段话版）

Agent 读 `/input/case.json` 抄 output_contract → 写 result.json 骨架 → `probe_input.py`（契约+工单+模板+起始稿）→ `extract_source.py`（材料文本基线）→ 模型产出 deck.json + evidence_map.jsonl（每条事实带逐字 quote）→ `gate_verify.py PLAN` 构建前双闸（fail 必须修）→ `deck_build.py`（generate 或 edit 模式）→ `gate_verify.py` 构建后校验 → `fit_audit.py` 模板对账 → `render_preview.py` 导出渲染 → `ablate_gain.py --write` 双臂消融增益 → slides_embed 全量内嵌 result.json 定稿。

## 五、输入输出说明

| 方向 | 内容 |
|---|---|
| 输入 | `/input/case.json`（契约）、material.json（科研材料）、`artifacts/slide-workorder.json`（工单：mode/受众/页数/保真/继承）、target-template.pptx、starting-deck.pptx（edit 模式） |
| 输出 | `/app/output/presentation.pptx`（原生可编辑）、previews/（PDF/PNG/SVG）、layout_log.json、change_log.json、fit_audit.json、render_log.json、verify_report.json、result.json |

result.json 保留契约全部字段不删键：`case_id / status / editable_source / export_artifact / content_map / compliance_checks / exceptions`，另加 `gain_evidence / efficiency / uncertainty / changelog`。材料缺失、无法判断、运行失败在 exceptions 三类分开登记。

## 六、参数表（主要脚本）

| 脚本 | 关键参数 |
|---|---|
| probe_input.py | `--input-dir`（默认 /input）、`--case/--workorder/--template/--starting-deck` 显式路径、`--out` |
| extract_source.py | `source`（pdf/json/文本）、`--outdir`、`--starting-deck`、`--min-size` |
| gate_verify.py | `pptx`（或字面量 PLAN）、`deck`、`--source`、`--evidence`、`--constraints`、`--out`；消融专用 `--skip-content-gate --skip-structure-gate` |
| deck_build.py | `spec`、`out`、`--mode generate|edit`、`--template`、`--starting-deck`、`--report`、`--log` |
| render_preview.py | `pptx`、`--outdir`、`--log` |
| ablate_gain.py | `--deck/--evidence/--source/--result/--workdir/--write` |

## 七、最小调用示例（示意，非正式案例结果）

```bash
python3 scripts/probe_input.py --input-dir examples/fake_input --out /tmp/probe.json
python3 scripts/extract_source.py examples/fake_input/material.json --outdir /tmp/extracted
python3 scripts/gate_verify.py PLAN examples/deck.json --source /tmp/extracted/source_text.txt \
    --evidence examples/evidence.jsonl --out /tmp/gate.json            # → verdict:pass
python3 scripts/deck_build.py examples/deck.json /tmp/presentation.pptx --mode generate --log /tmp/log.json
python3 scripts/render_preview.py /tmp/presentation.pptx --outdir /tmp/previews        # → status:svg_only_no_pdf(无Office时)
python3 scripts/ablate_gain.py --deck examples/deck.json --evidence examples/evidence.jsonl \
    --source /tmp/extracted/source_text.txt --result /tmp/result.json --workdir /tmp/abl --write
```

## 八、页数与导出限制

- 页数上限由工单 `slide_count` 驱动（结构闸门强制）；无工单时按 task.md，超限先砍方法细节页，结果页/限制页不砍。
- 导出：有 LibreOffice/PowerPoint 时出真 PDF+PNG；两者皆无时 stdlib 生成逐页 SVG 预览（status=svg_only_no_pdf，如实登记），绝不伪造 PDF。
- 版面预算：字号阶梯 18→16→14→12→11→10，10pt 仍溢出删内容不再缩。

## 九、已知问题与诚实边界

- 消融差值仅在本包示例输入上实测（见 worklog.md）；不同论文类型（综述/实验/理论）、不同模板下的增益需平台三案例三重复对照确认。
- stdlib 编辑兜底不支持 delete_slide/move_slide（如实记 skipped，不谎报已改）；有 python-pptx 时支持全部工单操作。
- 位图无法取数时不重绘数值，引用原图并登记；扫描件走页码定位。
- 渲染 SVG 预览是文本级近似版式（无图形元素还原），只用于开箱可核验，不替代真 PDF 导出审查。

## 十、复用与扩展

- 校验器 `gate_verify.py` 是独立可复用组件（任何 deck.json+evidence_map.jsonl+材料文本均可跑双闸）；`pptx_minimal.py` 可独立当 stdlib PPTX 构建库；`ablate_gain.py` 的污染注入/双臂框架可迁移到其它生成类题目。
- 页级金标准扩展：新增案例只需 material.json + deck.json + evidence.jsonl 三件套（schema 见 examples/ 与 SKILL.md 第 2 步）。
- 自检清单（SKILL.md 末尾 6 条）逐条 exit 0 实测通过，复制即跑。

## 最小可运行自检清单（逐条实测 exit 0）

```bash
python3 -c "import sys;print(sys.version)"                    # 1) 解释器可用
test -f scripts/gate_verify.py && echo scripts_ok             # 2) 脚本在位（校验式命中）
python3 scripts/pptx_minimal.py examples/deck.json /tmp/_self.pptx   # 3) 兜底构建器
python3 scripts/gate_verify.py PLAN examples/deck.json --out /tmp/_self_gate.json  # 4) 校验器
python3 scripts/ablate_gain.py --help >/dev/null              # 5) 增益脚本
python3 -c "import json;print(json.load(open('/tmp/_self_gate.json'))['summary']['verdict'])"  # 6) 报告可解析
```
