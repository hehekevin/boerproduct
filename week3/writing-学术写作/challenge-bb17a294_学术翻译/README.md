# acwrite-translate — 学术翻译与双语写作 Skill

面向 Bohrium 产品赛 challenge-bb17a294「学术翻译与双语写作」。核心主张：**术语锁定 + 禁用变体扫描 + 段级对齐可回溯**。

## 用途与适用场景

- 学术论文/报告/学位论文的中英双向翻译，要求句段级双语对照、可逐段修改。
- 适用问题域：术语一致性、数字保真（万/亿 ↔ million/billion 换算留痕）、双语对齐、引用保留与语义边界（否定辖域、模糊限制语强度）。
- 不适用：文学翻译、营销文案、纯口译记录。

## 快速使用（完整流程）

1. 输入：`/input/case.json` + `/input/task.md` + 原文材料。读取真实文件。
2. 按 SKILL.md「线性流程」执行 Step 1-5（契约→术语锁定→切分翻译→组稿校验→嵌入收尾）。
3. 输出（`/app/output/`）：
   - `translation_aligned.md`：段号级中英对照表（含图表题注对照区）
   - `translation.docx`：可编辑译文成稿
   - `result.json`：**主产物完整嵌入**——`bilingual_pairs`（段号/locator/原句/译文/role 一一对应）、`glossary`（术语/译法/首现位置）、`fidelity_table`（数字·单位·公式·引用编号核对结果），另含 case_id、契约字段、status、uncertainty、changelog
   - `number_check.json` / `align_check.json`：校验报告
   - `previews/`：PDF/PNG 渲染预览

## 最小示例

输入见 `examples/example_input.json`（示意输入，非正式案例结果）。示意调用与示意输出见 SKILL.md 第 3 节。

## 资源清单

| 文件 | 用途 | 依赖 |
|---|---|---|
| scripts/extract_materials.py | 抽取 /input 材料为 M*.txt（含 locator 标记） | Python 3.8+，标准库 |
| scripts/fact_ledger.py | 硬事实台账（数字/统计量/DOI）build + check | 标准库 |
| scripts/docx_build.py | aligned_draft.json → docx + 对照 md | 标准库（无 python-docx 时自动降级为纯文本写入） |
| scripts/render_preview.py | docx/md → PDF/PNG 预览（尽力而为，失败不阻断） | 可选：LibreOffice/Word，缺失时跳过 |
| scripts/align_check.py | 段级对齐 + 数字/引用序列 + **禁用变体扫描** | 标准库 |
| scripts/build_result.py | 组装 result.json（含主产物嵌入 --embed-*） | 标准库 |

全部脚本仅依赖 Python 标准库；三级容错（文件缺失→skip 提示、坏行跳过、致命→partial 报告 exit 2），不硬编码平台路径（一律经 CLI 参数，默认值符合运行契约）。

## 关键方法（评分对应）

1. **术语锁定**：Step 2 建表，每条含 `forbidden` 禁用变体清单；Step 4 机械扫描全译文（含题注段），禁用变体出现即 fail，直接对应「术语稳」评分项。
2. **段级对齐可回溯**：segments.jsonl 逐段登记 locator + role；align_check 校验段数/段号/role 一一对应；`bilingual_pairs` 嵌入 result.json，逐段可回溯，对应「对得齐」与「可核验性」。
3. **数字保真**：fact_ledger 建源文硬事实台账，译文数字逐条回查；换算留痕。
4. **边界语不漂移**：翻译时逐段 hedge_check；associated with 不译作"由…引起"。

## 限制与异常处理

- 扫描件依赖 OCR，uncertainty 注明。
- 语向/编码异常时交付可读部分，status=partial + gap 说明。
- 预算熔断（48 请求/700 秒）触发时交付已有内容，绝不空手返回。
- status 如实：complete / partial（含 gap 列表）。

## 自查

交付前逐项过 SKILL.md 第 4 节自查清单；校验 verdict 必须 pass 或在 uncertainty 中逐条说明未修复原因。


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
