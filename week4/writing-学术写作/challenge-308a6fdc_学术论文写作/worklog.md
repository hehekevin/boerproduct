# worklog — challenge-308a6fdc 学术论文写作 Skill 重做（v2）

日期：2026-11-13。目标：从历史聚合最高 62.33（波动 62.33/52.67/53.33/0）提升到 ≥70。

## 历史成绩与失分点分析

| attempt | 分数 | 推断的主要失分点 |
|---|---|---|
| 71936 | 62.33 | 基线版本可用但流程 7 阶段偏长，部分案例预算吃紧时后段产物（渲染/收尾）被挤压；result.json 只有最终一次成型，中途失败即全丢 |
| 72448 | 52.67 | 同上叠加：部分案例章节写得不全（广度不足），required_sections 覆盖率下降 |
| 72460 | 53.33 | 类似 52.67；fact_check unmatched 修复占用响应预算 |
| 72475 | **0** | **最高优先级疑案：单响应输出全文超过 16384 token 被截断 → result.json 残缺/不可解析 → 判 0**；或流程中途异常导致 /app/output 无有效 result.json |

## v2 针对性修复（每条对应上述失分点）

1. **逐章分批写盘回填（治 0 分）**：主产物不再一次响应输出全文；每次响应只写 1 个 `sections/S##.json`（≤1500 字），写盘后 `json.load` 自检，立即用 `build_result.py --status partial --set sections_done='[...]'` 回填。任何时刻中断，result.json 都完整可解析、已有章节已落盘。
2. **强制执行协议置顶**（治流程中断）：SKILL.md 首节 7 条硬协议——抄契约、立即落骨架（in_progress）、字段一个不缺、广度优先、48 次/700 秒熔断、写盘自检、失败也交付。模型先读协议再干活。
3. **线性 ≤5 步**（治预算挤压）：7 阶段压缩为 5 步；契约/提取/骨架合并为 Step 1，材料索引与台账合并为 Step 2。
4. **广度优先**（治章节不全）：先保证全部必需章节各有一版有据文本，再逐章充实；熔断前优先覆盖 required_sections。
5. **分章合并组稿 + 三级容错**：docx_build.py 新增 `--sections-dir`，逐文件解析、坏文件跳过留 skipped 痕、绝不因单个章节 JSON 损坏丢整稿；python-docx → stdlib 最小 docx → 占位文档三级降级（本地已双测）。
6. **修错不重写**：fact_check unmatched 只改对应 S##.json 后重跑合并，不重写全文，省响应预算。
7. **诚实状态**：status=complete/partial/failed 规则明确，渲染/解析降级如实入 changelog。

## 本地双测记录

- `docx_build.py --sections-dir`（含 1 个正常章节 + 1 个损坏 JSON）：正常章节合并成功，坏文件进 skipped，产出合法 docx+md。
- `docx_build.py examples/example_input.json`：python-docx 与 stdlib 兜底路径均产出可解析 docx 与 md。
- `build_result.py`：骨架 → --set 回填 sections_done → 收尾 complete，result.json 每一步均可解析。
- `fact_ledger.py build/check`、`consistency_check.py`：与 71 分标杆 skill 相同源码（diff 确认一致），沿用其已验证行为。

## 资源约束核对

- SKILL.md ≈ 170 行（≤250）；资源 7 个脚本 + 1 示例 = 8 文件（≤8）；线性 5 步（≤5）；无平台路径硬编码（全部 CLI 参数可覆盖，默认值仅为 Harness 约定路径）。
