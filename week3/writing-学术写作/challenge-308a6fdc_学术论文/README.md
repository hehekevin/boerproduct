# acwrite-paper — 学术论文写作 Skill（v2 重做版）

「学术效率」产品赛 · 学术写作赛道 · 学术论文写作（challenge-308a6fdc）参赛 Skill。

## 用途

把实验记录/数据表/图表/文献等固定科研材料写成结构完整、可编辑的论文章节稿（IMRaD），硬事实全部挂台账、逐条回溯到材料原文，交付可编辑 docx+md+证据映射+一致性检查报告。

## 快速开始（Harness 执行环境）

1. 读 `/input/case.json` 与 `task.md`，**逐字抄下 output_contract 全部字段名与 case_id**。
2. 立即落骨架 result.json（`build_result.py --status in_progress`），此后每步只回填不覆盖。
3. 按 SKILL.md 线性 5 步执行；**主产物逐章分批写**：每次响应只写 1 个 `/app/work/sections/S##.json`，写盘自检后立即回填 result.json（`--status partial --set sections_done='[...]'`）。
4. 收尾合并 `--sections-dir` → 双重校验 → 渲染 → `build_result.py --status complete`。

## 依赖

- Python 3.8+，仅用环境预装库。
- 可选增强：python-docx（docx 质量更好）、PyMuPDF（PDF 提取与 PNG）、openpyxl（xlsx）。
- 任一可选库缺失时脚本自动降级（stdlib 兜底仍产出合法可编辑 docx），降级事实写入 changelog，不阻塞交付。

## 文件清单（8 个资源文件，符合 ≤8 限制）

| 文件 | 作用 |
|---|---|
| `scripts/extract_materials.py` | 材料提取 → M01.txt…（带 `[SRC:Mxx:p|line]` 锚点）+ manifest |
| `scripts/fact_ledger.py` | 事实台账 build/check（数值/单位/n=/p/CI/DOI/年份抓取与机检，check 输出数字-来源全量核对表 checks[]） |
| `scripts/consistency_check.py` | 章节/术语/引用一致性检查 → check_report.json（逐项 {item, template_value, applied, match} 三元组 + 闸门枚举 enforced/skipped_not_provided/not_found/unreadable） |
| `scripts/docx_build.py` | 组稿构建：单 draft.json **或 --sections-dir 分章合并** → docx+md，三级容错 |
| `scripts/render_preview.py` | docx→PDF/PNG 预览，无渲染器如实记 no_renderer |
| `scripts/build_result.py` | result.json 骨架/回填/收尾（--set 支持逐章回填） |
| `examples/example_input.json` | S##.json 章节文件最小输入示意（仅示意结构，非正式案例结果） |

## 方法要点

- **逐章分批写盘回填**（v2 核心改动）：单响应只产 1 章小文件，规避 16384 token 截断；每章写完立即 `build_result.py` 回填 `sections_done`，任何时刻 result.json 完整可解析。
- **强制执行协议置顶**：抄契约 → 立即落骨架 → 字段一个不缺 → 广度优先 → 48 次/700 秒熔断 → 写盘自检 → 失败也交付。
- **事实挂账**：所有数值/引用/图注先入 evidence_map（locator+逐字原文）再落稿，fact_ledger check 机检 unmatched。
- **三级容错**：python-docx → stdlib 最小合法 docx → JSON 全坏时输出可编辑占位文档；section 文件损坏自动跳过并在 skipped 列表留痕。
- **诚实状态**：status/partial/failed 与降级事实如实记录，不伪造渲染或数据。

## 最小示例（标注示意）

输入章节文件（即 `examples/example_input.json`，标注为示意结构）：

```json
{
  "order": "03",
  "heading": "2 材料与方法",
  "level": 1,
  "paragraphs": [
    "示意段落：数值 12.3±1.1 mg/L 与样本量 n=212 均来自材料并在 evidence_map 挂账。"
  ]
}
```

调用与示意输出：

```bash
python3 scripts/docx_build.py --sections-dir /app/work/sections --out-docx /app/output/draft.docx --out-md /app/output/draft.md
# → {"ok":true,"builder":"python-docx","sections_merged":8,"markdown":"/app/output/draft.md"}
python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --status partial --set sections_done='["摘要","1 引言","2 材料与方法"]'
# → {"ok":true,"status":"partial","keys":["case_id","sections_done","status",...]}
```

## 适用边界

- 仅处理给定材料支撑的论文写作任务；材料外的学科惯例改动记 changelog。
- 不做科研绘图算法本身、不做全文翻译系统；聚焦材料→成稿→溯源→可编辑。

## 维护

- 版本 2.0（逐章分批写盘回填 + 执行协议置顶 + 分章合并组稿）。
- 新材料格式：扩展 `scripts/extract_materials.py` 的 ext_map 与对应解析函数。


## 生态贡献：依赖、安装运行、目标用户与验收

| 项目 | 说明 |
|---|---|
| 依赖与版本 | Python 3（评测沙箱 3.12；本 Skill 脚本仅用标准库，无需 pip 安装）；所有命令用 `python3` 调用。 |
| 安装与运行 | 平台把提交目录装入 `/skills/weekly-skill`；输入 `/input/case.json`（+ 材料），产物写 `/app/output/result.json`。 |
| 输入 / 输出解释 | 输入=案例标识与来源材料；输出=result.json（契约全字段 + 逐条证据 + 闸门状态 + gain_evidence + efficiency + exceptions）。 |
| 目标用户与场景 | 需「产出可直接用、且每条结论都能回到原文核对」的作者与审阅者；用于成稿前的自检与交付留痕。 |
| 验收方式 | ①契约键一个不缺且 JSON 可解析；②每条论断带可回证的 evidence 与来源位置；③闸门状态显式、非 enforced 有 gate_note；④gain_evidence 含基线与当前两套指标及削减量。 |
| 常见问题 | 证据回证失败→换原文短引文而非改写；材料缺失→按题面要求登记缺口而非补零；机检不过→修一轮并如实登记结论。 |
| 已知限制 | 增益对照为同输入自比，量化的是核对工作量与漏检率，不等同于跨模型横向评测。 |
| 失败处理 | 任一步异常：写盘已有产出、status 如实降级、exceptions 记录失败点与已尝试回退链；机检结论照实记录且退出码恒 0。 |
| 复用建议 | 直接复用 scripts/；证据与闸门的字段结构可套用到同类「产出+核对」任务。 |
| 版本与维护 | 见 worklog.md 版本小节；结构变更时同步本表与 SKILL.md 输出字段说明。 |

## 最小可运行自检清单（复制即跑）

```bash
python3 -c "import sys;print(sys.version)"   # 1) 解释器可用
ls scripts/                                   # 2) 脚本在位
python3 scripts/gain_evidence.py --help       # 3) 增益脚本可执行
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"  # 4) 产物可解析且键齐全
```
