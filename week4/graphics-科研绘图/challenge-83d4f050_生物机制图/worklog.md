# worklog

- 2026-11-12 读取 task.md / output-contract.md / example-input.json，明确契约字段与运行时约束（64请求/900s/16K tokens，产物含 result.json）。
- 2026-11-12 确定设计基线：禁止编造 + 方向核对表为正确性主防线；SVG 分层（区室/实体/边/图例，语义化 id）为可编辑核心。
- 2026-11-12 编写 SKILL.md：强制执行协议（先写 result.json 骨架、预算熔断 48 请求/700s、失败也写盘）+ 线性五步主流程 + 异常处理 + 自检清单。
- 2026-11-12 复制官方 render_svg.py 到 submission/scripts/，--help 验证可运行（零第三方依赖）。
- 2026-11-12 编写 README.md（依赖/调用步骤/输入输出/最小示意示例，已标注示意）与 templates/relation-checklist-template.md（通路关系核对表模板）。
- 2026-11-12 自测渲染发现官方脚本 3 处回退链缺陷并做最小修复（Linux 行为不变）：① cairosvg 已装但缺原生 DLL 时抛 OSError 而非 ImportError，捕获 Exception 防止击穿回退链；② --check 对不存在文件优雅返回 2；③ 浏览器回退的 file URL 反斜杠/缺第三斜杠被 Chrome 拒绝 + 相对路径 screenshot 落到安装目录被拒，改为归一化 URL 与绝对路径。
- 2026-11-12 全链路自测通过：最小通路 SVG（区室/实体/边/图例分组）经 Chrome headless 渲染 PNG 4800x3600(300dpi)，--check 返回 CHECK OK nonbg_ratio=1.0。
- 2026-11-12 自检：文件数 5（≤6）、SKILL.md 行数 ≤250、全 UTF-8、总量 ≤150KB，通过。
- 同步修复 scripts/render_svg.py：cairosvg 已安装但缺原生 libcairo 时 import 抛 OSError（非 ImportError），已改为捕获 Exception，保证回退链（rsvg-convert/inkscape/chrome headless）不被绕过。
- 合并 scripts/render_svg.py 两处健壮性修复：(1) --check 对缺失输入文件优雅返回码2而非抛异常；(2) 浏览器回退渲染使用规范化 file:/// URL 与绝对路径 screenshot，避免路径解析失败。
