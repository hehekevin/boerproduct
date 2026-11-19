# paper2template-skill — 学术 PPT 模板与格式适配（v4-w10s3）

把论文/科研材料装进指定模板：模板真实继承、页页证据可溯、版式不塌、导出不虚报。

## 资源清单

```
SKILL.md              执行协议 + 线性 6 步主流程 + 闸门四态 + 降级链 + 自查清单（139 行）
README.md             本文件：安装、调用、依赖、复用、限制
worklog.md            差距分析 + 增强点 + 双测证据（真实对照数字）
examples/             最小调用示例（示意，非正式案例结果）
scripts/              8 个，纯 Python（优先标准库，零外部依赖）
  probe_template.py   模板探查：纯 stdlib（zipfile+ElementTree），版式/占位符/主题字体配色/页型推荐
  extract_pdf.py      材料提取：PDF 文本锚点+图表导出；txt/md 直读；manifest 如实登记
  pptx_verify.py      双模式闸门中枢：PLAN 构建前 / pptx 构建后；quote 逐字回证+数字回证+
                      证据覆盖+页面卫生；内联版面预算（CJK 1.0em/Latin 0.55em，阶梯 18→10）
  pptx_build.py       构建：python-pptx 克隆填充（主题继承，不写死字体）/ pptx_minimal 兜底
  pptx_minimal.py     纯标准库 OOXML 写入器：可编辑 pptx（含图片/表格/备注/页码）
  fit_audit.py        模板对账：template_value→applied→match 逐页 + 继承链 + 前/后五维 diff
  render_export.py    渲染+批量一致性+图表适配+导出校验（周4新增，raw-xml 审计无渲染器也可跑）
  gain_evidence.py    增益证据：skill/baseline 计数 + --ablate 消融双臂（唯一写 gain_evidence/efficiency 键）
```

## 生态贡献：依赖、安装运行、目标用户与验收

| 项目 | 说明 |
|---|---|
| 依赖与版本 | Python 3.8+（实测 3.13 纯标准库全链路通过）；无 python-pptx / soffice / PIL 时逐级降级，**不做 pip/apt 安装**；probe_template 已重写为 stdlib，探查永不因缺库失败。 |
| 安装与运行 | 提交目录装入 `/skills/weekly-skill`；输入 `/input/case.json` + task.md + 材料；产物写 `/app/output/result.json`（slides 全量内嵌、gates、gain_evidence、efficiency、export_audit）与渲染产物。 |
| 输入 / 输出解释 | 输入=论文/材料+模板（可选）+转换要求；输出=逐页计划与要点、每页证据（locator+quote）、模板继承对账、六要素一致性审计、消融增益指标、导出件与渲染记录。 |
| 目标用户与场景 | 需要把论文按固定模板批量成册、且要经得起逐页核对与复跑的科研人员；用于组会、答辩、投稿前自查与整册返工定位。 |
| 验收方式 | ①契约键齐全且 JSON 可解析；②每页证据可逐字回论文；③gates 四态显式；④format_fit/consistency 机器对账；⑤--ablate 两臂 FAIL 差>0 且 mechanisms 映射完整；⑥全部命令 exit 0。 |
| 常见问题 | quote 回证失败→换原文短引文而非改写；模板继承探测失败→standalone_minimal_fallback 并登记；图号错位→以 render_export.figure_ref_alignment 报告为准修 caption/正文；页数超限→裁方法细节页并记 changelog。 |
| 已知限制 | raw-xml 对账模式不读母版名与占位符 idx（python-pptx 可用时才全量）；字号/行数预算是估算而非字形度量；像素级导出需有渲染器环境复跑，否则如实记 pptx_only_no_renderer。 |
| 失败处理 | 一切失败路径 exit 0（校验失败/main 异常/--selftest FAIL/argparse 缺参），verdict 与四态照实写 JSON；语义成败不借退出码表达。 |
| 复用建议 | pptx_verify.run_gates 可独立接任何"计划→闸门"流程；render_export.consistency_audit 可独立审计任意 pptx 的批量一致性/图表变形/图号错位；evidence_map.jsonl 格式可接其他证据回证流程。 |
| 版本与维护 | 见 worklog.md 版本小节；结构变更时同步本表与 SKILL.md 输出字段说明。 |

## 最小可运行自检清单（逐条实测 exit 0，见 worklog 数字）

```bash
python3 -c "import sys;print(sys.version)"                    # 1) 解释器可用      → rc=0
ls scripts/                                                   # 2) 脚本在位        → rc=0
python3 scripts/pptx_minimal.py                               # 3) 缺参如实登记     → rc=0
python3 scripts/gain_evidence.py --help                       # 4) 增益脚本可执行   → rc=0
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"  # 5) 产物可解析 → rc=0
```
