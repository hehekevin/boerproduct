# research-data-visualizer 使用说明

## 一、Skill 是什么
把科研数据表变成**可回证、可编辑、可复跑**的图表：
- 图型选择：数据画像 + 分析意图 → 候选图型与**推荐理由** + **不推荐理由**
- 图表渲染：手写 SVG（零第三方依赖、无 matplotlib），标题/来源/轴标目+单位/图例自描述
- 逐点回证：每个标记带原始数值锚点（data-x/data-y 等），verify_check.py 依据轴刻度
  元数据独立复算像素坐标（容差 1.5px）并回查源数据表
- 发表级导出：SVG + PNG(300dpi) + PDF（渲染器回退链，全缺失时如实降级）
- 交付：result.json（契约全字段）+ 图件 + 机检报告 + 增益证据

## 二、运行环境与调用方式
平台把本目录装入 /skills/weekly-skill 后，向 Agent 说明"按 SKILL.md 处理 /input 案例"。
运行时：输入 /input/case.json + task.md + 数据材料；工作目录 /app/work；
产物写 /app/output/（result.json + figure.svg/png/pdf + chart_selection.json + verify_report.json）。

## 三、5步主流程速览
1. 读 case.json/task.md/数据，抄 output_contract 全键与 case_id，确认清洗口径
2. build_skeleton.py 立即写 result.json 骨架（全键 + status=partial）
3. chart_select.py：列画像 → 意图 → 候选图型+推荐/不推荐理由 → chart_selection.json
4. plot_svg.py 渲染 SVG → verify_check.py 逐点复算+完备性机检 → render_export.py 导出 PNG/PDF
5. gain_probe.py 消融双跑+污染注入 → schema_guard.py 契约守卫 → 填全 result.json

## 四、可核验性设计（本 Skill 核心）
- **逐点复算**：轴组 data-min/max/px-min/px-max + 标记原始数值锚点 → 复算像素坐标；
  bar 复算矩形几何、stacked 复算分层上下沿、histogram 复算分箱计数。
- **数据-图形一致性四模式**：points（逐点存在性）/ agg_mean/sum（按类聚合）/
  stack_sum（按类+系列求和）/ hist_recount（重新分箱），与 plot_svg 的聚合方式
  一一对应（verify 需传与 plot 相同的 --agg / --series-col）。
- **自描述机检**：标题/来源/轴标目+单位/图例四项 + 刻度≥2 且单调，completeness_score 定量。
- **键归属唯一**：chart_selection/verify_report/render_evidence/gain_evidence/
  efficiency/schema_report 各由唯一脚本产出，schema_guard 登记归属告警。
- **脚本校验式命中**：find 定位后必须 grep CHARTVIZ-MARKER 标志再执行。
- **全部退出码 0**：成败结论写在 JSON（status/ok 字段），不用退出码表达语义。

## 五、输入约定
- 数据：CSV/TSV（SQLite 先用 python3 sqlite3 导出 CSV）；支持中文列名/类别、缺失值、
  日期文本横轴（按出现序等距映射）；数值判定用 ASCII 正则（防 str.isalpha 汉字陷阱）。
- 缺失/异常不静默剔除：plot_svg 记 n-note，exceptions 与 pipeline_log 留痕。

## 六、脚本清单
| 脚本 | 职责 | 关键用法 |
|---|---|---|
| build_skeleton.py | 契约骨架 | `--case /input/case.json --out /app/output/result.json` |
| chart_select.py | 图型选择引擎 | `--data data.csv --task task.md --out chart_selection.json`（--no-rationale 消融） |
| plot_svg.py | SVG 渲染（5 图型） | `--chart line/scatter/bar/stacked_bar/histogram --x --y [--series --agg --bins]` |
| verify_check.py | 逐点复算+完备性机检 | `figure.svg --data --xcol --ycol [--agg --series-col]`（--skip 消融） |
| render_export.py | PNG/PDF 导出+像素校验 | `figure.svg --outdir out --png --pdf --dpi 300`；`figure.png --check` |
| gain_probe.py | 消融双跑+污染注入 | `--data --x --y [--series --agg --chart] --result ... --write` |
| schema_guard.py | 契约守卫 | `--result ... --case ... --write` |

## 七、最小示意示例（标注为示意，非正式案例结果）
examples/：example_case.json + example_data.csv（18 行氮肥实验合成数据）+
example_task.md → example_expected_result.json（示意 result.json，字段结构与正式一致）。

## 八、异常与失败处理
见 SKILL.md 第2节异常表：缺失/异常不静默剔除；中文列名用 ASCII 正则判定；
无渲染器→SVG 交付+降级登记；脚本未命中标志→人工路径+登记；契约缺失→partial+missing_keys。

## 九、限制
- 不做统计检验、不拟合模型、不做期刊排版适配与图像美化。
- 渲染器仅支持 line/scatter/bar/stacked_bar/histogram 五种图型。
- 像素复算容差 1.5px，存在极小概率边界假阳性；data 属性以 %.10g 全精度输出缓解。

## 生态贡献：依赖、安装运行、目标用户与验收（十项）

| 项目 | 说明 |
|---|---|
| 依赖与版本 | Python ≥3.8（评测沙箱 3.12），仅标准库，零 pip 安装，无 matplotlib/cairosvg 硬依赖 |
| 安装与运行 | 平台装入 /skills/weekly-skill；输入 /input/case.json+task.md；产物写 /app/output/ |
| 输入/输出解释 | 输入=案例标识+数据表（CSV/TSV/SQLite）+任务说明；输出=result.json（契约全字段+chart_selection+verify_report+render_evidence+gain_evidence+efficiency+schema_report）+ SVG/PNG/PDF |
| 目标用户与场景 | 科研绘图作者与审稿复核者：需要「图上数值可回证到数据表、口径可复跑」的对比/趋势/构成/分布/关系图 |
| 验收方式 | ①契约键一个不缺且 JSON 可解析；②verify_report.status=pass 且逐点复算 mismatch=0；③自描述四项 completeness_score=1.0；④gain_evidence 消融 delta 与污染 FAIL 差齐全 |
| 常见问题 | 折线/散点聚合后 verify 须传相同 --agg；中文列名请直接用原名；单位不明留空+登记，勿臆造 |
| 已知限制 | 无渲染器环境只交付 SVG+降级记录；箱线/热图不支持（给替代建议）；不做统计检验 |
| 失败处理 | 任何一步异常：写盘已有产出、status 如实降级、exceptions 记录；脚本全部 exit 0，结论在 JSON |
| 复用建议 | scripts/ 七个脚本可直接复制复用；data-* 锚点+轴元数据+复算公式可套用到任何自绘 SVG 图表的可核验化改造 |
| 版本与维护 | 见 worklog.md 版本小节；规则变更时同步更新 SKILL.md 与本表 |

## 最小可运行自检清单（复制即跑，实测 exit 0）

```bash
python3 -c "import sys;print(sys.version)"                       # 1) 解释器可用
ls scripts/                                                       # 2) 七脚本在位
python3 scripts/chart_select.py --help                            # 3) 选型引擎可执行
python3 scripts/build_skeleton.py --case examples/example_case.json --out /tmp/r.json          # 4) 骨架生成
python3 scripts/plot_svg.py --chart bar --data examples/example_data.csv --x treatment --y biomass_g --out /tmp/f.svg   # 5) 渲染
python3 scripts/verify_check.py /tmp/f.svg --data examples/example_data.csv --xcol treatment --ycol biomass_g --agg mean --out /tmp/v.json  # 6) 机检
python3 scripts/gain_probe.py --data examples/example_data.csv --x week --y biomass_g --series treatment --chart line --agg mean --result /tmp/r.json --write  # 7) 增益
python3 scripts/schema_guard.py --result /tmp/r.json --case examples/example_case.json --write  # 8) 契约
python3 -c "import json;d=json.load(open('/tmp/r.json'));print(sorted(d.keys()))"              # 9) 产物可解析且键齐全
```
