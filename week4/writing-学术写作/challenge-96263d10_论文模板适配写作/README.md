# acfmt-template — 学术格式与模板适配 Skill（v1）

「学术效率」产品赛 · 学术写作赛道 · 学术格式与模板适配（challenge-96263d10）参赛 Skill。

## 用途

把目标模板/格式要求抽取成可逐项机器核对的规格清单，将稿件按清单机械适配为可编辑成品（标题重编号、题注前缀重编号、交叉引用同步、docx 落页边距/栏数/字号/行距），再由同一机检器逐项复验并做内容单元保真对比与同输入双臂消融取证。

## 快速开始（Harness 执行环境）

1. 读 `/input/case.json` 与 `task.md`，**逐字抄下 output_contract 全部字段名与 case_id**。
2. 立即落骨架 result.json（`build_result.py --status in_progress`），此后每步只回填不覆盖。
3. 按 SKILL.md 线性 5 步执行：模板识别 → 原稿清单 → 适配组稿 → 双校验（格式机检+保真对比）→ 收尾（build_result → render_preview → gain_evidence --write）。
4. **顺序**：result.json 由 build_result 先产出，gain_evidence 最后 `--write` 追加（该键唯一写入方）。

## 依赖

- Python 3.8+，仅标准库，零外部依赖，无需 pip 安装。
- 可选增强：LibreOffice（soffice，用于 PDF 预览渲染）；缺失时如实记 `no_renderer`，不阻塞交付。
- 所有命令用 `python3` 调用。

## 文件清单（8 个脚本，符合 ≤8 限制）

| 文件 | 作用 |
|---|---|
| `scripts/extract_template.py` | 模板识别：从模板/格式要求文件抽取规格清单（页边距按边/栏数/字号/行距/题注/文献样式/导出格式/摘要字数/必需章节），每条带来源锚点，冲突检测 |
| `scripts/inventory.py` | 内容单元清单（标题/段落/表格/图/公式/脚注/引用）+ 转换保真对比（missing/changed/added） |
| `scripts/adapt_build.py` | 按清单适配组稿：标题连续重编号（摘要/文献等前置后置章节不编号）、题注重编号+交叉引用同步、docx 落 sectPr 页边距/栏数/字号/行距，全程留痕 adapt_log |
| `scripts/format_check.py` | 逐项格式机检：md 级（章节/标题编号/题注/交叉引用/引用样式/摘要字数）+ docx 级（页边距/栏数/字号/行距，解析 XML），逐项三元组，`--ablate` 退化模式 |
| `scripts/render_preview.py` | docx→PDF 预览；无渲染器如实记 no_renderer |
| `scripts/build_result.py` | result.json 骨架/回填/收尾（契约字段保留+三桶语义+contract_coverage+efficiency） |
| `scripts/gain_evidence.py` | 增益证据：同输入双臂消融（FAIL 数差机器判定）+ 污染反例注入副本验证 + 基线人工核对量削减 + `--selftest` |
| `scripts/_rlog.py` | 运行日志（效率计数自动采集源） |

## 方法要点

- **认得准**：规格条目全部带 `source{file,line,quote}` 锚点，可逐条回溯模板原文；抽取结果必须经 Agent 逐条人工复核后使用（规则抽取会漏抓/误抓）。
- **排得对**：机械适配（重编号/题注/页面参数）→ 机检复验逐项三元组 `{item, template_value, applied, match}`；docx 级规格通过解析 XML 实测，不是自述。
- **转得全**：inventory 保真对比逐单元对齐，标题剥离编号前缀后比对（重编号不算改写）；missing/changed/added 逐条留痕。
- **交得出**：docx 为合法可编辑文件（stdlib 精确 XML，零依赖构建）；渲染预览器缺失如实记录。
- **增益可验证**：双臂消融 fail 数差为机器判定；污染反例注入副本（不触碰正式稿）验证抓错能力；baseline（全人工）vs 当前模式人工核对量削减。
- **诚实状态**：status 四级 complete/partial/failed/blocked；闸门枚举 enforced/skipped_not_provided/not_found/unreadable/skipped_ablation；所有失败路径 exit 0。

## 最小示例（标注示意）

输入章节文件（即 `examples/example_input.json`，标注为示意结构，非正式案例结果）：

```json
{
  "order": "03",
  "heading": "2 方法",
  "level": 1,
  "paragraphs": [
    "示意段落……",
    {"type": "table", "caption": "表1（示意）三线表", "rows": [["方法", "耗时"], ["人工", "高"]]}
  ]
}
```

checklist 形态见 `examples/example_checklist.json`（示意）。

调用与示意输出：

```bash
python3 scripts/extract_template.py --input /input --out /app/work/checklist.json
# → {"ok":true,"items":11,"conflicts":0,"required_sections":["摘要","参考文献"]}
python3 scripts/adapt_build.py --sections-dir /app/work/sections --checklist /app/work/checklist.json --out-docx /app/output/adapted.docx --out-md /app/output/adapted.md
# → {"ok":true,"builder":"stdlib-spec-docx","spec_applied":{"margin_sides":{"top":2.54,...},"columns":2}}
python3 scripts/format_check.py --draft /app/output/adapted.md --checklist /app/work/checklist.json --docx /app/output/adapted.docx
# → {"verdict":"pass","fail":0,"items":["sections_complete:pass",...,"docx_spec:pass"]}
```

## 适用边界

- 聚焦一个方向：模板规格抽取 + 逐项机检 + 机械适配 + 保真核验；不做完整排版引擎（页眉页脚/分节符/域代码的适配未覆盖，缺规格时如实登记）。
- 机检覆盖 md 层与本包自建 docx 的 XML 层；外来 docx 的复杂对象（OLE/嵌入图表）只做保真清点。
- 机制消融 ≠ 平台白板：增益对照为同输入自比，白板由组织方固定。

## 失败处理

任一步异常：写盘已有产出保留、status 如实降级、闸门/异常在 result.json 记录失败点；校验失败修复一轮后仍不过则如实登记（fail 计数+条目）；**退出码恒 0**，不阻断交付链。

## 生态贡献：依赖、安装运行、目标用户与验收

| 项目 | 说明 |
|---|---|
| 依赖与版本 | Python 3（评测沙箱 3.12；仅标准库）；可选 LibreOffice 用于 PDF 预览；所有命令 `python3` 调用。 |
| 安装与运行 | 平台把提交目录装入 `/skills/weekly-skill`；输入 `/input/case.json` + task.md + 材料，产物写 `/app/output/result.json`（+ adapted.docx/md、format_report、fidelity_report）。 |
| 输入 / 输出解释 | 输入=案例标识+模板/格式要求+原稿；输出=result.json（契约全字段 + spec_claims 逐条锚点 + format_check 三元组 + fidelity_check + gain_evidence + efficiency + uncertainty）。 |
| 目标用户与场景 | 需「按目标模板交付稿件、且每条格式决定可回溯核对」的作者、编辑与研究生；用于投稿/学位论文格式审查与转换验收。 |
| 验收方式 | ①契约键一个不缺且 JSON 可解析；②每条规格带来源锚点；③format_check 逐项三元组且非 enforced 项有 gate_note；④fidelity 无意外 missing/changed；⑤gain_evidence 含双臂差+污染捕获+基线削减的真跑数字。 |
| 常见问题 | 规格漏抓/误抓→Agent 逐条复核并手改 checklist；模板冲突→并列记录+uncertainty；题注歧义→adapt_log.crossref_ambiguous 留痕人工处理；机检不过→修一轮并如实登记。 |
| 已知限制 | 增益对照为同输入自比，量化核对工作量与检出力，不等同跨模型横向评测；污染反例仅覆盖 md 层；页眉页脚/分节符/域代码未做适配。 |
| 失败处理 | 全脚本退出码恒 0；argparse 错误/文件缺失/渲染失败均如实记 JSON 并继续交付；任何时刻 result.json 完整可解析。 |
| 复用建议 | 直接复用 scripts/；checklist 条目结构与三元组机检模式可套用到同类「规格抽取+逐项核对」任务（如代码规范检查、合同条款核对）。 |
| 版本与维护 | v1 见 worklog.md；新增模板字段时扩展 extract_template.py 的 RULES/MARGIN_PATS 并同步 format_check 的核对分支。 |

## 最小可运行自检清单（复制即跑，逐条实测 exit 0）

```bash
python3 -c "import sys;print(sys.version)"        # 1) 解释器可用
ls scripts/                                        # 2) 脚本在位（8 个）
python3 scripts/gain_evidence.py --selftest        # 3) 内存自检：selftest=PASS（exit 0）
python3 scripts/extract_template.py --help >/dev/null  # 4) 帮助可执行（exit 0）
python3 scripts/format_check.py --draft no.md --checklist no.json  # 5) 失败路径 verdict=fail 且 exit 0
python3 scripts/inventory.py scan --doc no.md --out /tmp/i.json    # 6) 不可读稿如实 gate=unreadable（exit 0）
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(sorted(d))"  # 7) 产物可解析且键齐全
```
