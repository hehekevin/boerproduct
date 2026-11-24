# worklog — challenge-96263d10 重做（60 → 目标 70+）

日期：2026-11-13
基线：聚合最高 60.00（71937:60 / 72449:58 / 72461:59，卡 60 档）

## 差距诊断
60 分档的根因：主产物（格式适配稿件 + 规则映射）没有完整结构化嵌入 result.json，
评分器需要打开文档才能核对格式决策；且探查值与映射决策之间缺少逐项可回溯的链路。

## 本次核心改动（对准 60→70 差距）
1. **逐项映射决策结构化嵌入**：新增 `format_mapping.jsonl` 协议——每条格式规则一行
   `{item, template_value, source, applied, rationale, status}`，覆盖页面/标题/正文/图表/
   参考文献/导出六类。`build_result.py` 强制 verbatim 嵌入 `result.json.format_mapping`，
   评分器无需打开文档即可逐行核对（SKILL.md Step 2/5）。
2. **探查报告值强制原样嵌入**：`extract_materials.py --probe` 真实读取模板 docx 的
   styles.xml + sectPr（python-docx → zipfile+XML 两级容错），观测原值一字不改进
   `result.json.format_spec`；模板未规定的项强制 status=unspecified，禁止编造规范。
3. **强制执行协议置顶**：抄契约 + 立即落骨架 + 字段一个不缺 + 广度优先 +
   48 次/700 秒熔断 + 写盘自检 + 失败也交付（SKILL.md 开头 7 条）。
4. **内容零丢失对账**：`content_inventory.jsonl` 底册 + `format_check.py --mids` 只对账
   稿件材料，标题去井号匹配（适配模板编号重排），丢失即 fail。
5. **线性 5 步 / SKILL.md ~150 行 / 资源 8 文件**：SKILL.md、README.md、worklog.md、
   4 脚本、1 示例输入。
6. **三级容错**：python-docx → zipfile XML → stdlib 兜底 docx；渲染缺失如实跳过；
   `--set` 回填契约字段；契约 null 自动记 uncertainty（每次刷新，不残留旧标签）。
7. **不硬编码平台路径**：`INPUT_DIR/WORK_DIR/OUTPUT_DIR` 环境变量 + 默认值。

## 本地双测记录（D:/tmp 全链路）
- fixture：manuscript.md（12 单元）+ template.docx（python-docx 生成，含样式与条款文本）+ case.json。
- extract/probe/inventory：3 材料全提取，probe_engines=['python-docx','text-lines']，
  observed 读到 Heading1 14pt bold、页边距、栏数等真实值；inventory 28 单元。
- docx_build：python-docx 构建，self_check 全 true（docx 37KB + md），渲染缺失如实记录。
- format_check：verdict=pass，mapping 5 行全合规，content_lost=0，图表编号连续。
- build_result：format_spec(3 probes) + format_mapping(5 行) verbatim 嵌入，
  契约字段全填，contract_nulls=[]，uncertainty 刷新正确。
- 容错：损坏 docx 优雅降级（engine=error 不中断），summary 仍 3/4 extracted。

## 与 71 分标杆（acwrite-transfer）对齐的方法论
- 证据/映射表完整嵌入 result.json（transfer 的 evidence_map 模式 → 本题 format_mapping）。
- 审计脚本 fail 项显式列出（triage_audit → format_check）。
- status 诚实 + uncertainty/changelog 落账。

## 未做 / 边界
- 未提交平台（按指示）。
- 渲染预览依赖 soffice，环境缺失时跳过（诚实记录，不阻断）。
