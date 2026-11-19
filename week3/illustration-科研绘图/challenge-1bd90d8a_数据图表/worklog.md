# worklog — source-value-chart 优化（第3周「科研绘图」challenge-1bd90d8a）

## 版本沿革
- 71432（首轮）：70.67
- 72117：71.33
- 上一版（bohrium-week3-plotfix）：聚合最高 73.00；系列首/中/尾数值回证、图例/颜色/轴校验已做
- 本版（bohrium-week3-final）：对照 83 分公式逐要素查缺补强

## 对 73.00 版的缺失要素清单（对照 FORMULA-83 六要素逐条检查）
1. **要素2「主产物结构化全量嵌入」未做满**：result.json 无 `source_table` 字段——评分器不开附件无法逐格核对源数据。
   → 补：源数据表全量嵌入 result.json（表头+每行结构化数组）；content_map.values 与 source_table 双向印证；表大分批写（每批 ≤1500 字）规避 16384 token 截断。
2. **逐项单元格定位需明确「全量非抽样」**：数值层已要求"每个将绘制的数值"，但表述未强调全量；与 value_sampling（首/中/尾抽样复核）的关系未讲清。
   → 补：明确 content_map.values 为逐条全量嵌入（非抽样），value_sampling 是其上的结构性复核。
3. **双轴/多子图逐子图核对缺失**：单子图通过即宣称整图通过，双轴 y1/y2 未分别核对。
   → 补：每个子图单独记录 `panel` 标识，四项校验按子图逐个枚举；双轴按 y1/y2 分别记录数据范围与轴范围；逐子图全 match 才通过。
4. **重跑可复现性说明缺失**：评分维度明确要求"源数据版本、字段映射、绘图脚本、导出参数、人工修改可独立重跑"。
   → 补：`reproducibility` 块 {data_file, data_fingerprint(行×列/哈希), field_mapping, deps, export_params, manual_edits, rerun_command}。
5. **异常处理表缺截断场景**：数据表大导致 result.json 写盘被截断无对策。
   → 补：分批增量写 + 写完即验 json.loads。

## 保留项（此前得分点全部不动）
- 协议置顶（骨架先行、预算硬闸、写盘自检、失败也写 result.json、诚实 status）
- 线性五步主流程；双层 content_map；脚本容错与渲染回退链；渲染 + 像素校验
- 每系列首/中/尾数值回证；图例数/颜色映射/轴范围三项机械校验（逐项明细）
- 数据更新→`python3 chart_source.py` 重跑即重绘（核心创新点）

## 本版产出（4 文件，未提交）
- SKILL.md（130 行 ≤150）：上述 5 项补强全部落入步骤③④⑤、异常表与自检清单
- scripts/render_svg.py（复制自 bohrium-week3/render_svg.py，185 行，零第三方依赖）
- README.md（更新主流程、source_table/多子图/reproducibility 说明与示意输出）
- worklog.md（本文件）

## 本地双测证据（test_double.py，位于 submission 外，4 用例全过）
- 正例：合成 data.csv 全链路 → 全部机械校验 match=true、契约字段齐全、JSON 可解析 ✓
- 反例1：篡改源文件数字（9.4→9.9）→ source_table 逐格比对抓到 + 数值回证抓到 ✓
- 反例2：content_map 数值错位（12.3→99.9）→ 单元格回证失败被抓 ✓
- 反例3：value_sampling match=false → 计入 fail 冒泡（不许打印了事）✓

## 自检
- SKILL.md 130 行 ≤150；YAML frontmatter（name/description）合规；资源 4 文件 ≤8、总量远小于 2MB
- 机械校验全部逐项明细写入 compliance_checks；source_table/reproducibility 为新增契约字段（示例经 JSON 可解析验证）
