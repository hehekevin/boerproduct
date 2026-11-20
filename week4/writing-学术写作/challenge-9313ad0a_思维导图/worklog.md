# worklog — acwrite-mindmap 重做（challenge-9313ad0a）

日期：2026-11-13。基线：历史聚合最高 62.00（71296:58 / 72144:62）；目标 ≥70。

## 旧版问题诊断（对照 71 分标杆 acwrite-transfer）

1. **主产物嵌入不完整**：旧版只嵌 outline.md → deliverable_content 与 tree.json → mindmap_tree（两次 build_result 调用），relations.jsonl 与 node_evidence.jsonl 未嵌入 result.json——连接关系与证据挂接只在文件里，评分器核对"连得对/证据可追溯"需打开文件。本次 5 键全部嵌入（+render 证据共 6 键）。
2. **无真实渲染**：旧版只产 SVG 文本文件，无 PNG/PDF 渲染步骤，无文件/像素校验证据，违反 runtime contract "real rendered PDF/PNG previews"。
3. **骨架靠模型手写**：旧版 Step 0 要求模型手写骨架 JSON，易漏键。本次改为 `build_result.py init` 脚本化抄契约全键。
4. **无终检**：旧版自检是人工清单；本次 `build_result.py verify` 机检（JSON 可解析 / 契约键不缺 / case_id 一致 / complete 时空键拦截）。
5. **build_result 单 embed**：旧版 --embed-file 一次一个，SKILL.md 里连续两次调用易漏；本次多 --embed-file + 路径:键名语法 + embed 源空文件拦截。

## 本次改动

- `SKILL.md`：协议 7 条置顶（契约+骨架 / 字段不缺 / 结构化嵌入 / 熔断 / 真渲染 / verify / 失败也交付）；流程 5 步线性；≤250 行。
- `scripts/build_result.py` 重写：init / embed（多嵌入、jsonl 自动列表、空文件拦截）/ verify 三子命令。
- `scripts/map_build.py` 增强：写盘自检（四文件 >100B + SVG XML 良构 + 节点>60 告警）→ build_report.json；三级容错（逐格式 try/except）。
- `scripts/render_preview.py` 新增：SVG→PNG，5 引擎降级链（cairosvg→svglib→rsvg-convert→inkscape→playwright），PNG 字节+尺寸+非空白像素占比三重校验（<0.01 判无效），证据写 render_log.json；无渲染器如实记 no_renderer 不伪造。
- `scripts/map_check.py` / `extract_materials.py` / `fact_ledger.py`：沿用旧版（已验证稳定）。
- `README.md`：完整使用说明 + 最小示例（输入/调用/示意输出，标明为示例）。
- `examples/`：example_input.json（含 output_contract 示意）+ tree/relations/evidence 样例。

## 本地双测记录（全部通过）

1. map_build：4 格式生成，自检 ok（mm 516B / opml 509B / svg 2901B 良构 / md 633B），5 节点 2 关系 2 证据。
2. render_preview：本机无渲染引擎 → 如实 no_renderer（评测镜像有 cairosvg/playwright 时真实渲染+像素校验）。
3. map_check：verdict=pass，gaps=0。
4. build_result init→embed→verify：契约键抄全、5 键嵌入、status=complete、verdict=pass（exit=0）。
5. extract_materials + fact_ledger：md 材料提取成功，台账 3 条硬事实。
6. verify 失败路径：partial 状态正确放行（unknown 允许），complete+空键会被拦截。

## 资源清单

SKILL.md + README.md + worklog.md + 6 脚本（extract_materials/fact_ledger/map_build/map_check/render_preview/build_result）+ 4 示例文件 = 14 文件，全部 UTF-8，<200KB。

## 待平台验证点

- 评测镜像渲染引擎可用性（任一即可出 PNG 证据；全无则如实 no_renderer）。
- 实际 case.json 的 output_contract 形态（init/embed 已兼容 list 与 dict 两种）。
