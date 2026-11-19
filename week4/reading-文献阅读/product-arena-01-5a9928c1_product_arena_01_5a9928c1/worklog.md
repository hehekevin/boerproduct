# worklog

- 读取 task.md 全文，确认题目为阅读03文献翻译，评分含实际效果40、使用增益25、创新增益15、可靠体验10、生态贡献10，运行契约为 64 次模型请求、900 秒、单响应 16384 tokens、最多 50 个文本文件、单文件 500KB、总量 2MB。
- 读取 challenge.json，确认运行时输入为 /input/case.json 与 task.md，产物写入 /app/output 且必须含 result.json 与 case_id，平台提供 pdf-text-tool、ocr-tool 等资源。
- 设计决策：不单选一个突破方向，而是用一条七阶段流水线同时覆盖术语稳、段落全、关系准、可核验四个考察点，主攻术语表强制锁定与段落级双语对照。
- 设计决策：预算分配为模型请求不超过 20 次（分批翻译 8 到 12 次），全部核验交给零模型请求的 Python 脚本，为异常重试留余量，适配 64 次 900 秒预算。
- 设计决策：双语对照格式定为 `### 段号 | 定位 | 类型` 加 SRC/TGT/NOTE 三行，机器可解析，便于脚本核验与人工回看。
- 设计决策：创新机制定为四个：占位符保护回填（公式、引用、图表编号、数字单位翻译前替换为占位符）、术语表锁定与禁用变体扫描（status=locked 真正执行而非仅写在提示里）、数字单位自动核对表（脚本逐段比对原文数字）、诚实状态标注规则（[!UNCLEAR]、[!UNTRANSLATED]、[指代: xxx] 三类标记）。
- 创建 submission/SKILL.md，英文 frontmatter（name: academic-paper-translate），中文正文含七阶段流程、输入输出约定、八类异常分支、预算分配表、十项自检清单。
- 创建 submission/resources/terminology-template.csv（术语表模板，含 variant 禁用变体列）、segment-map-template.csv（段落对齐模板）、result-template.json（result.json 模板，含 status、uncertainty、change_log）、checklist.md（24 项核验清单加人工确认清单）。
- 创建 submission/scripts/verify_alignment.py，纯标准库，支持段落对齐、术语一致性、数字单位保留、占位符残留、result.json 字段五类检查，可整体或单项运行，支持 JSON 报告。
- 实测核验脚本正向用例（通过场景）与反向用例（缺段号、错数字、禁用变体、空译文、占位符残留），初版发现两个缺陷：NOTE 行被并入 TGT 导致空译文漏检，数字检查的占位符正则误判跳过全部数字；已修复并重测通过，反向用例五类问题全部命中。
- 创建 submission/README.md，含文件清单、环境要求、调用步骤、脚本用法、格式约定、最小调用示例（明确标注示意输出非正式案例结果）、适用限制与失败处理。
- 本文件 worklog.md 创建，记录开发轨迹。

- 根据首轮评分反馈（评语：refine for a more complete and rigorous solution；未找到完整真实推导的解）修订 SKILL.md：在 frontmatter 后新增「强制执行协议」节，明确第0步先落盘 result.json 骨架、output_contract 字段缺数据不省略、广度优先、预算阈值（48次请求/700秒）强制收尾、最终写盘自检、失败也交付六条硬性纪律。
