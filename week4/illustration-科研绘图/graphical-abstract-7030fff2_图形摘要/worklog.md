# worklog — graphical-abstract-builder v2.0（plotfix 重制版）

## 背景
- v1.0（71280/71994）两次 0 分；对标赛道最高 76.67（challenge-83d4f050，91 行/5 文件）。本次按已验证经验与 0 分残留隐患清单逐项修复重制。

## 逐项修复记录（对应 0 分隐患排查清单）
- ①绝对路径残留：协议第 3 条改为"路径不臆测"——工单与 render_svg.py 均动态定位（`ls -R /input`、`find /skills /app -name render_svg.py`），全文无任何写死路径。
- ②超长输出截断：新增协议第 4 条——SVG 先骨架后逐层充实、result.json 增量回写、单次写入 ≤200 行。
- ③渲染多步失败链卡死：明确"渲染是单点步骤，失败不回滚"——脚本内置回退链自动降级，全失败保留 SVG + exceptions + status=partial，照常走步骤⑤填 result.json（已在步骤④与异常表中双保险写明）。
- ④workorder 输入路径假设：步骤①改为"定位并读工单"，工单可能内嵌 case.json 或位于 /input 任意位置；找不到则按默认规范执行并登记 `workorder-missing`。
- ⑤result.json 字段名对齐：协议第 1 条升级为"逐键原样抄录 output_contract（不增不减不排序）"，本地无 case.json 样例，示例键名已在 README 标注"不构成契约"。

## 保留的已验证经验（全部继承 v1.0 与标杆）
- 强制执行协议置顶（5 条）；线性 ≤5 步；SKILL.md ≤120 行；资源 ≤5 文件。
- 第1步抄契约、第2步落骨架；content_map 逐元素溯源（摘要句 N / 结论段 / Figure N）。
- 真实渲染 PNG(300dpi)+PDF + `--check` 像素非空校验；画布/字号下限（34/20/16px @1200 宽）嵌入 compliance_checks 与自检清单。
- source-preserving edit + content_map 内 edit 记录。
- render_svg.py 三处健壮性修复随源文件继承：cairosvg 捕获 Exception（防 OSError 绕过回退链）、--check 缺文件返回码 2、浏览器回退 file:/// 规范化 URL + 绝对路径 screenshot。

## 对标差距修正
- 学标杆精简：正文压缩至 92 行（低于 v1.0 的 115 行与标杆 91 行量级）；资源文件从 5 降至 4（SKILL.md / README.md / scripts/render_svg.py / worklog.md），删除 ga-info-extraction-template.md（Agent 按步骤③直接产出 content_map，无需额外模板）。

## 交付清单
- [x] SKILL.md（92 行，wc -l 实测）
- [x] scripts/render_svg.py（185 行，原样复制已修复版）
- [x] README.md（依赖/调用/示意示例并标注"非正式案例结果"）
- [x] worklog.md（本文件）
- 共 4 文件，全 UTF-8 文本，总量 < 60KB（限额：50 文件/500KB 单文件/2MB 总量）。
- 未提交（按指令仅产出）。
