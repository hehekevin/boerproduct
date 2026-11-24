# worklog — reading-client-loop（v3）重做记录

- 读题：通读 task.md（评分五维度表、交付要求、Harbor 契约）+ datasets 里真实的 example-input.json
  与 output-contract.md，确认 case.json 实际形态 = case_id/task_instruction/output_contract(dict)/source，
  无预置 questions/paragraphs——一切问答与材料定位必须在运行时从实际文件推导。
- 调研旧版：第一版 reader-loop（59 分线上无评分记录沿用）与第二版 reader-loop-r2（attempt 71330=59，
  attempt 72161=0）共 15 个文件全部读完。
- 失分点分析①（文档 3 分）：r2 无 README.md——安装说明/示例/限制/维护全缺，文档完整性直接丢分；
  v3 补齐 README.md（安装、依赖、五步调用、输入输出、示意示例标注示意、适用范围、维护）。
- 失分点分析②（创新/主产物）：r2 的 review.html 是被动快照（只列表不交互），"客户端"本体缺位；
  v3 用 export_client.py 生成真·阅读客户端界面 MVP：段落跳转、关键词搜索、选区黄高亮、证据绿高亮、
  问答卡一键跳回原文锚点（scrollIntoView+闪烁）、阅读位置、边界说明，并用 --embed-result 把整份
  HTML 机械嵌入 result.result.client.embedded_html——主产物字符串嵌入 result.json + 外部文件双份。
- 失分点分析③（契约保障靠人肉）：r2 骨架/字段完整性只靠 SKILL.md 指令，模型漏键即扣分；
  v3 新增 make_result.py：机械提取 output_contract（dict/list 双形态+默认五字段兜底）、init 落骨架、
  --merge 深合并补键、--check 验字段，把协议第 1/2 条从纪律变成脚本保证。
- 失分点分析④（自检覆盖不足）：r2 自检 7 项，缺嵌入一致性、claims 结构（kind/source_id/location/
  evidence）、uncertainties.summary、qa 结构校验；v3 check_all.py 扩到 9 组校验，并输出
  check_report.json 供复核。
- 失分点分析⑤（容错无证据）：r2 脚本无自测，"容错"只是口号；v3 四脚本各内置 --selftest
  （合成正例必须通过 + 反例缺文件/二进制乱码/损坏 JSON 不得裸异常不得空结果）。
- 失分点分析⑥（frontmatter）：两旧版 description 均以中文开头；v3 改为纯英文 description +
  name 小写连字符（reading-client-loop）。
- 写 SKILL.md：协议 7 条置顶（骨架先行/字段不缺/广度优先/48 次-700 秒熔断/写盘前自检/失败也交付/
  不编造）；五步线性主流程（抄契约落骨架→建索引→定位选区问答逐问落盘→批注+客户端→机械自检终写）；
  异常处置表 8 场景；脚本路径用 find+fallback 定位、不硬编码唯一平台路径。
- 写 build_locator.py：四形态索引（paragraph-json 多键名兼容/txt/md 标题识别/pdf 双库兜底）、
  --find 关键词定位、扫描件探测、case 缺失仍写空索引+原因。
- 写 make_result.py / export_client.py / check_all.py（要点见上）。
- 四脚本 py_compile 通过；--selftest 正反例双测全部 PASS（正例 PASS/嵌入一致，反例 FAIL 如期）。
- SKILL.md 175 行 ≤250；资源文件 7 个（SKILL.md+README+worklog+4 脚本）≤8，全部 UTF-8，<60KB。
- 闭环覆盖确认：打开（骨架+索引）→定位（--find/段落跳转/页码）→选区问答（锚点三件套）→
  批注保存（annotations.json+reading_log）→回看复核（客户端跳转高亮+check_report）。
