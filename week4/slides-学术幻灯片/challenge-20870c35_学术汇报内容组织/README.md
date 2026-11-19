# talk-organizer — 学术汇报内容组织（挑战 challenge-20870c35）

把已完成的论文/研究材料组织成能上台讲的学术汇报：页级唯一主张、证据逐字回证源材料、叙事服务听众与时长、每页预判追问。区别于「论文压缩」：核心机制是**报告目标→听众画像→叙事取舍→重点信息→问答预演**五个组织机制，全部经机器闸门可判。

## 资源清单

```
SKILL.md                    执行协议 + 6 步主流程 + 闸门四态 + 降级链 + 自查清单（117 行）
README.md                   本文件：依赖、调用、复用、限制、验收
worklog.md                  差距分析 + 真实对照数字 + 诚实边界
scripts/                    5 个，纯 Python 标准库，零外部依赖
  probe_contract.py   第1步：契约抄录 + result.json 骨架 + 材料校验式探查 + 约束提取
  verify_gate.py      统一校验器：6 闸门（quote逐字/数字回证/唯一主张/问答备注/叙事骨架/证据覆盖），四态显式；evaluate() 供消融复用
  build_deck.py       纯标准库 OOXML pptx 构建（可编辑、含真实备注页）
  render_preview.py   手写 SVG 逐页预览 + index.html；检测 soffice 时顺带 PDF，否则如实 no_office_renderer
  ablate.py           增益层：三臂消融（skill/ablated/polluted）同一校验器判定，写 gain_evidence 与 efficiency
examples/example_plan.json  deck schema 示意输入（标注示意，非正式案例）
```

## 依赖与安装

- Python 3.8+，仅标准库（json/os/re/shutil/zipfile/xml/subprocess）；无 pip 安装、无网络、无 node/浏览器依赖。
- 提交目录装入 `/skills/weekly-skill`；输入 `/input/case.json` + task.md；工作区 `/app/work`；产物 `/app/output/result.json` + `deck.pptx` + `previews/`。
- 平台工具（pdf-text-tool / pdf-render-tool / office-renderer）可用时按 SKILL.md 第 1、4 步接入；不可用时走降级链并如实登记。

## 调用方式（一段话版）

Agent 读 `/input/case.json` 抄 `output_contract` → `probe_contract.py` 写骨架+约束 → 模型做组织决策产出 `deck.json`（目标/听众/叙事取舍记入 meta；每页唯一 claim+逐字 quote 证据+Q: 预判追问）→ `verify_gate.py` 构建前闸门（fail 必修）→ `build_deck.py` 出可编辑 pptx → `render_preview.py` 出 SVG 逐页预览（可选 PDF）→ `ablate.py --write` 写入消融增益 → slides 全量内嵌 result.json 定稿。

详细 schema 与异常处置见 SKILL.md；最小调用示例见 SKILL.md 第 4 节（标注示意，非正式案例结果）。

## 输入 / 输出

- 输入：`/input/case.json`（含 output_contract 与 case_id）、task.md、论文/研究材料（PDF 走平台工具）。
- 输出：`/app/output/result.json`（契约全字段 + deliverable.slides 全量内嵌 + gates + gain_evidence + efficiency + render + status/uncertainty/changelog）、`deck.pptx`（可编辑）、`previews/slide_pNN.svg` + `index.html`。

## 生态贡献

| 项目 | 说明 |
|---|---|
| 依赖与版本 | Python 3.8+ 标准库；评测沙箱 3.12/3.13 实测通过；不安装任何包。 |
| 安装与运行 | 目录装入 `/skills/weekly-skill` 即被 Harness 加载；5 个脚本均可独立 CLI 复用。 |
| 输入/输出解释 | 见上文；result.json 字段名以运行时 case.json 的 output_contract 为准（只增不减）。 |
| 目标用户与场景 | 需要把论文/研究材料转成组会/答辩/评审汇报并保证可回溯、可答问的科研人员。 |
| 验收方式 | ①契约键齐全且 JSON 可解析；②闸门 6 项 enforced 且 fail=0；③每页 claim 唯一、notes 含 Q:；④gain_evidence 含三臂消融与污染反例机器判定。 |
| 常见问题 | quote 回证失败→换原文短引文而非改写；源文本为空→闸门 skipped 并登记，不宣称已核对；页数超限→砍方法细节页并记取舍。 |
| 已知限制 | 消融 B 臂为同计划结构化改写，代表机制差而非基础 Agent 端到端复跑；闸门对结构敏感、对排版美观不敏感。 |
| 失败处理 | 全脚本退出码恒 0；错误写 JSON + uncertainty；闸门 fail 修一轮仍不过则如实记录继续交付。 |
| 复用建议 | `verify_gate.evaluate()` 可接任意「计划→闸门」场景；`ablate.py` 的机制→指标映射表可直接套用到其它内容组织任务。 |
| 版本与维护 | v1.0（2026-11-19）；结构变更须同步 SKILL.md 字段说明与 worklog 版本小节。 |

## 最小可运行自检清单（复制即跑，逐条实测 exit 0）

```bash
python3 -c "import sys;print(sys.version)"                                      # 1) 解释器可用
ls scripts/                                                                     # 2) 脚本在位（5个）
python3 scripts/verify_gate.py --plan examples/example_plan.json --source examples/example_plan.json --out /tmp/g.json   # 3) 校验器可执行（源缺失时四态 skipped）
python3 scripts/build_deck.py examples/example_plan.json /tmp/demo.pptx --log /tmp/b.json   # 4) 构建器可执行
python3 scripts/ablate.py --help                                                # 5) 消融脚本可执行
```
