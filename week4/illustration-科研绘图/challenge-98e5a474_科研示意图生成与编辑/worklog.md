# worklog — challenge-98e5a474（科研示意图生成与编辑）提交包重构

## 本轮增强（对照 83 分公式，2026-11-16）

基线：`bohrium-week3-plotfix/challenge-98e5a474/submission/`（当前最优 72.00，平台第1为72.67，差 0.67）。本轮按「最小化改动」原则，保留全部已验证机制，只补 83 分公式缺失要素。

### 缺失要素清单（对照 83 公式六要素逐项检查）

| 要素 | 基线状态 | 判定 |
|---|---|---|
| 1. 强制执行协议置顶（骨架先行/每步写盘/熔断/失败也写） | 已具备 4 条 | 保留 |
| 2. 主产物结构化全量嵌入 | content_map 已嵌入；关系核对表、渲染证据未要求嵌入 | **补强** |
| 3. 机械校验器逐条三元组 {item, template_value, applied, match} | compliance_checks 只有汇总 pass/fail | **缺失，补** |
| 4. 闸门状态显式枚举 enforced/skipped_not_provided/not_found/unreadable | 完全缺失 | **缺失，补** |
| 5. 证据逐字摘录+定位（content_map evidence≤30字+source） | 已具备 | 保留 |
| 6. status 诚实四级 | 已具备 | 保留 |

### 补强点（4 处最小改动）

1. **SKILL.md 步骤③**：关系方向核对表后新增——每条关系以三元组 `{item, template_value, applied, match}` 全量嵌入 `compliance_checks.relation_checks` 数组；`match:false` 必须改图复检，改不动记 exceptions。
2. **SKILL.md 步骤④**：`PNG OK`/`PDF OK`/`CHECK OK` 渲染输出**逐字全文**嵌入 `export_artifact.render_evidence`（评分器不开文件即可核对渲染证据）。
3. **SKILL.md 步骤⑤**：compliance_checks 重构为三组逐条三元组（relation_checks / entity_checks / export_checks）；**闸门状态显式化**——每组带 `gate` 字段，只取 `enforced / skipped_not_provided / not_found / unreadable`，非 enforced 必加 `warn:true` + `gate_note:"下游不得宣称已核对"`（没跑≠通过）。
4. **SKILL.md 自检清单 + README 示意 result.json**：同步新结构，闸门语义写进 README。

未改动：scripts/render_svg.py（与平台副本逐字节一致）、五步主流程、异常处理表、协议第 1-4 条。SKILL.md 93 行（≤150 合规），资源仍为 4 文件。

### 本地双测证据

正例（合成 case 全链路，SVG 已标注「示意」）：
- 合成含抑制关系（T 端 marker）+ 图例的分层 SVG → Chrome headless 渲染 `PNG OK: {'width': 4800, 'height': 3600, 'sampled': 10000, 'nonbg_ratio': 1.0}`（300dpi）→ `--check` 输出 `CHECK OK`，退出码 0。
- PDF 在本机 FAIL（本机无 cairosvg/rsvg/inkscape，Chrome 回退链不产 PDF）——符合脚本「PNG/PDF 互相降级、失败如实登记」语义；平台环境渲染链已在往轮实测验证。
- result.json 自检正例：7 契约键齐全 → `MISSING: none`，PASS。

反例（注入脏数据，校验器必须抓到）：
- 纯白空白 PNG → `CHECK SUSPECT nonbg_ratio: 0.0`，退出码 1 ✅ 抓到
- 截断 1/3 的脏 PNG → `CHECK FAIL: cannot parse PNG`，退出码 2 ✅ 抓到
- 文本伪装 .png → `CHECK FAIL: cannot parse PNG`，退出码 2 ✅ 抓到
- result.json 删除 compliance_checks 键 → 自检报 `MISSING: ['compliance_checks']` ✅ 抓到

测试产物已清理，提交包仅含正式 4 文件。

## 0 分根因排查记录（历史轮）

背景：71431/71441/72116 三次 0 分，判词均为 "did not find a complete, genuinely-derived solution"；others 拿 70-75，说明题目可评分，问题出在重放执行链路而非题目本身。

对照排查清单逐项审查 0 分版 SKILL.md（106 行）：

| # | 排查项 | 0 分版现状 | 判定 | 处置 |
|---|---|---|---|---|
| ① | 绝对路径残留 | 正文仅 `/input`、`/app/output`、`/skills/weekly-skill`（运行时契约路径，非作者机器路径） | 无硬编码残留，但渲染命令是「find /skills /app/work . 三处联合查找 + head 取第一个」的复合命令，`find` 对多根目录任一失败即整链异常，且 `head -1` 可能选中错误文件 | **疑似主因之一**。改为标杆（76.67 版）验证过的简单形式 `python3 scripts/render_svg.py ...` 作主路径，find 定位降级为单行回退 |
| ② | 渲染命令多步易失败 | 步骤④的 bash 块含 3 条命令（find 定位 → 渲染 → 校验），外加内联回退说明 | 复合命令放大失败面；回退说明混在代码块注释里，agent 可能照抄整块执行导致中断 | 主路径压缩为 2 条简单命令；回退链移入异常处理表 |
| ③ | 流程分支可能跳过 result.json | 协议第 1 条要求读输入后立即写骨架，但正文未把「每步一个写盘动作」显式化 | 中风险：多分支异常路径下 agent 可能只改 SVG 不回填 | 新增强制协议第 2 条「每步一个写盘动作」，五步各有唯一写盘动作，任何时刻盘内可评分 |
| ④ | 正文字段超 16384 token | content_map evidence 已限 ≤30 字 | 低风险，保留约束 | 保留 evidence ≤30 字约束 |
| ⑤ | 输入路径假设 | 步骤①直接引用 `artifacts/figure-workorder.json` 示例路径 | 中风险：工单实际路径可能不同，agent 按示例找不到即空转 | 步骤①改为「先 `ls -R /input` 探测实际文件再读」，不按文件名假设内容 |

附加根因假设：0 分版 106 行 + templates/entity_relation_worksheet.csv 共 5+ 文件，流程描述比标杆多出「图例映射」「预算护栏」等交叉引用，指令密度高、易被模型执行时走样。标杆（同赛道最高 76.67）只有 91 行/5 文件/命令式五步/每步一个明确写盘动作。

## 本次重构改进点

1. **SKILL.md 精简**：106 行 → 约 100 行，删除交叉引用与重复说明，保持命令式五步。
2. **渲染主路径替换**：采用标杆验证过的 `python3 scripts/render_svg.py work/figure.svg --outdir /app/output --png --pdf --dpi 300` + `--check` 两条命令；find 定位降为单行回退，异常表承接回退链。
3. **输入探测前置**：步骤① 第一步 `ls -R /input`，杜绝工单路径假设。
4. **写盘动作显式化**：协议第 2 条标注每个步骤的写盘动作（骨架 → SVG → 导出件 → 终稿）。
5. **资源收敛**：去掉 templates/，仅 2 个资源文件（SKILL.md + scripts/render_svg.py），加 README.md、worklog.md 共 4 文件，远低于 50 文件上限。
6. **render_svg.py**：沿用三轮实战修复版（cairosvg OSError 捕获、file URL 正斜杠处理、非零退出码语义），未改动。
7. 保留全部已验证经验：output_contract 全键抄录、content_map 逐元素溯源、关系方向核对表、source-preserving edit + edit 记录、真实渲染 + --check、status 诚实、失败也写 result.json。

## 文件清单

- SKILL.md（Skill 本体）
- scripts/render_svg.py（渲染与校验工具，仅标准库）
- README.md（使用与方法说明 + 最小调用示例）
- worklog.md（本文件）
