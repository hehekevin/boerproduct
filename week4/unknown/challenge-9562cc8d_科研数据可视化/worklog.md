# worklog — challenge-9562cc8d 科研数据可视化 Skill（research-data-visualizer）

日期：2026-11-19 ｜ 作者：w7-ana3 ｜ 赛道：analysis ｜ 提交窗口：11-25 21:00

## 版本

| 版本 | 内容 |
|---|---|
| v1.0 | 本保底版+增益层：7 脚本 + SKILL.md(126 行) + README + examples(示意) + worklog |

## 开发时间线（真实过程）

1. 读题面（week4-dl/challenge-9562cc8d/task.md）：评分五维——实际效果40/使用增益25/
   创新增益15/可靠体验10/生态贡献10；机检要点=图型选择依据、数据-图形一致性
   （逐点复算）、轴/图例/单位完备、渲染产物存在。
2. 参照第3周绘图赛道冠军包（challenge-9034312d）骨架：强制协议（先骨架后完善、
   预算护栏、失败也交卷）、脚本校验式命中（CHARTVIZ-MARKER）、渲染降级链、
   增益证据脚本模式全部沿用；机检对象从"装置图 element_id"换成本题的
   "data-x/data-y 数值锚点 + 轴刻度元数据"。
3. 开发中实测并修复的真实缺陷（均有复现记录）：
   - build_skeleton：契约键含 "exceptions"/"status" 时被 unknown 覆盖导致
     AttributeError → 结构键白名单修复；
   - plot_svg：histogram y 轴误用占位 y 值而非频数（y_axis max 错为"1"）→ 分箱计数
     提前到定标前；data-* 属性用 %.4g 造成复算假阴性 → fattr %.10g 全精度；
     分类列被 num() 转 float 导致与 CSV 类别对不上 → numeric_x 仅限折线/散点；
   - verify_check：聚合后的折线/散点误走逐点存在性模式（6 假阳性）→ 增加
     agg_mean/agg_sum 模式并做 xnorm 数值归一化（"2.10"↔"2.1"）。

## 真实对照数字（examples/example_data.csv 18 行合成数据，本地 Python 3.13.14 实跑）

**全链路（bar 柱状图）**
- chart_select：recommended=bar，candidates=1，rejected=4（pie/time_series_plot/
  line/scatter 均附不推荐理由），rationale_coverage=1.0，n_rows=18
- verify_check：status=pass，fail_count=0，completeness_score=1.0，
  pixel_recompute 3/3（容差 1.5px），data_consistency mode=agg_mean 3/3
- render_export：本机无渲染器 → RENDER DEGRADED 如实降级，exit=0（SVG 3,505 字节
  照常交付；评测沙箱有 cairosvg 时输出 PNG 300dpi+PDF 并回填 render_evidence）
- schema_guard：status=pass，missing_keys=[]，case_id_match=true，status_honest=true
- 各脚本退出码实测全部为 0（含 --help、失败路径、降级路径）

**消融双跑（gain_probe，同输入 line 图 12 标记）**
| 能力 | 完整模式 | 消融模式 | delta |
|---|---|---|---|
| 图型选择理由 | rationale_coverage=1.0 | 0.0 | **1.0** |
| 自描述字段 | completeness_score=1.0 | 0.5 | **0.5** |
| 逐点一致性校验 | 注入篡改检出 2 处（status=fail） | 检出 0 处（status=pass） | **2** |

**污染反例注入（同一校验器双跑 FAIL 差）**
- P1 篡改 data-y(+10%)：clean=pass → polluted=fail，pixel_recompute 捕获
  pt-000 pixel_offset（期望 378.52 实际 387.75）
- P2 剥离 y 轴标注：clean=pass → polluted=fail，self_description 捕获
  ylabel_with_unit
- detection_rate_full=1.0（注入 1 处检出 ≥1）

**基线对照与效率**
- baseline：12 个标记全部需人工核对 → skill 路径 0 项，reduction=12
- efficiency：mechanical_check_items=19，manual_checks_avoided=24
  （12 几何复算 + 12 源值回查），rerun_avoided_items=7

## 诚实边界（限制与不做的事）

- 本机无 cairosvg/rsvg/inkscape/chrome，PNG/PDF 产物在本机为降级路径；
  渲染证据（宽高/nonbg_ratio/PDF 字节）需在评测沙箱真跑后回填，本包不预填假数字。
- examples 为 18 行合成示意数据，标注"示意"，非正式案例结果；正式三案例
  （UCI Concrete/Iris/Wine）由平台提供，不预置答案。
- 逐点复算容差 1.5px、data 属性 %.10g 全精度，理论上有极小概率边界假阳性；
  篡改幅度小于 %.10g 精度或像素容差内的注入无法检出（已知边界）。
- gain_probe 的 P1/P2 覆盖"数值不一致"与"标注缺失"两类注入；未覆盖字体缺失、
  权限不足等环境类故障（SKILL.md 第2节已列人工处置）。
- 不做统计检验、不拟合模型、不做期刊排版适配。
