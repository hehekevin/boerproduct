# acwrite-transfer — 科研成果转化写作

「学术效率」比赛 · 学术写作赛道 · 科研成果转化写作 参赛 Skill。

## 用途与目标用户
科研成果转化写作技能：按目标读者画像做受众适配改写（论文→科普/新闻稿/申报材料），内容取舍三档清单（必须保留/可压缩/可删除+理由），术语表锁定与首次展开，关键结论/数据/限定条件完整保留，论断强度与源文匹配。
- **目标用户**：需要把论文/技术报告改写为科普文章、新闻稿、申报材料的科研人员、科研助理与写作 Agent。
- **典型场景**：同一成果面向不同读者（公众/媒体/评审）的多体裁改写，要求事实、数据、限定条件零丢失且可逐段复核。

## 依赖与版本
- Python 3.8+（实测 3.12/3.13 均通过）；脚本纯标准库，**零外部依赖**。
- python-docx/PyMuPDF/openpyxl 为可选增强：缺失时脚本自动降级（stdlib 兜底，docx 走 `stdlib-min-docx(fallback)`），降级事实写入 changelog，不阻塞交付。

## 安装与运行
1. 将本目录整体放入工作区（如 `/skills/weekly-skill`），保持 `scripts/`、`examples/` 相对结构不变。
2. 工作目录设为本目录，所有脚本以 `python3 scripts/<脚本>.py ...` 调用；无需安装步骤。
3. 完整流程按 `SKILL.md` Stage 0-6 执行；工作目录约定：输入 `/input`、中间产物 `/app/work`、交付 `/app/output`。

## 输入与输出
- **输入**：`/input/case.json`（含 `output_contract` 契约字段与 case_id）+ task.md + 源文材料（txt/md/json/docx/pdf）。
- **输出**（`/app/output`）：`transfer.docx`/`transfer.md`（改写稿）、`result.json`（契约字段 + `main_artifact_text` 全文分块嵌入 + gates 闸门区）、`evidence_map`/`fact_check`/`triage_audit`/`check_report`/previews 等证据文件。
- **中间产物**（`/app/work`）：audience.json（读者画像）、triage.jsonl（三档取舍清单）、evidence_map.jsonl（逐字证据）、fact_ledger.jsonl（事实台账）。

## 快速开始（Harness 执行环境）
1. 读取 `/input/case.json` 与 `task.md`，抄下 `output_contract` 全部字段名（含 case_id）。
2. **立即写 `/app/output/result.json` 骨架**（status=partial，契约字段全 null），此后每阶段回填。
3. 按 `SKILL.md` Stage 0-6 顺序执行；脚本调用统一为 `python3 scripts/<脚本>.py ...`。
4. 最终交付到 `/app/output`：主产物 + `result.json` + 证据/检查/渲染记录。

## 验收方式
- `triage_audit`/`fact_ledger check`/`consistency_check` 报告 pass（keep_missed=0、回证通过）。
- `result.json` 契约字段无缺、`status` 如实（complete/partial/failed/blocked 四级）、gates 全枚举。
- 增益验收：完整模式与 `--ablate` 消融模式同输入各跑一遍 `align_audit.py table`，两份 metrics 对照（示例见 `examples/ablation_gain_example.json`，示意非正式案例）。

## 最小可运行自检清单（逐条实测 exit 0，2026-11-17）
```bash
python3 scripts/align_audit.py selftest --work /tmp/acw_check/selftest
python3 scripts/extract_materials.py --input examples --outdir /tmp/acw_check/extracted --case examples/example_input.json
python3 scripts/docx_build.py examples/example_input.json --out-docx /tmp/acw_check/transfer.docx --out-md /tmp/acw_check/transfer.md
python3 scripts/fact_ledger.py build --sources /tmp/acw_check/extracted --out /tmp/acw_check/fact_ledger.jsonl
python3 scripts/fact_ledger.py check --draft /tmp/acw_check/transfer.md --ledger /tmp/acw_check/fact_ledger.jsonl
```

## 常见问题（FAQ）
- **校验脚本报问题数 >0 怎么办？** 逐条修复后重跑（数字回台账、补回 keep 落点、降级强度词）；脚本退出码恒 0，问题数才是信号，不许打印了事。
- **可选库缺失？** 自动降级为 stdlib 兜底，gate 标 `unreadable` + gate_note，改用人工核对清单并在 uncertainty 声明。
- **读者画像未指定？** 按体裁默认画像并在 audience.json 标 `assumed`。
- **源文是预印本/涉密？** 改写稿如实注明；涉密材料只做结构化整理不外发。

## 已知限制
- 不做论文精读综述、科研绘图算法本身；聚焦材料→成稿与溯源。
- 增益对照的 B 臂是脚本确定性派生的机制关闭基线，不等价于组织方正式基础 Agent，不替代官方对照。
- docx 渲染在无 python-docx 环境下为最小化 fallback（样式简单但内容完整）。

## 失败处理
- 任何阶段崩溃/超时：保证 `/app/output/result.json` 仍为合法 JSON（status=partial/failed，缺项写明）。
- 材料缺失、无法判断、运行失败分别登记，不静默跳过、不臆造。

## 复用建议
- `examples/terminology_seed.jsonl`（通用种子术语表）、triage 三档清单格式、evidence_map 逐字回证格式、改动清单（change_log）格式均可直接移植到其他写作类 Skill。
- `scripts/align_audit.py` 的 rubric/table/degrade/compare 子命令可独立用于任何"源文→改写稿"对照评测。
- 新材料格式：扩展 `scripts/extract_materials.py` 的 ext_map 与对应解析函数即可。

## 版本与维护
- 版本 1.2（1.1 基础上增量：`align_audit.py table --ablate` 消融开关、SKILL.md 增益证据与效率计数节、examples/ablation_gain_example.json 实测对照示例、README 自检清单）。
- 维护入口：改脚本后先跑上面 5 条自检命令（全部 exit 0 为过）；遇新格式材料扩展 extract_materials.py。
