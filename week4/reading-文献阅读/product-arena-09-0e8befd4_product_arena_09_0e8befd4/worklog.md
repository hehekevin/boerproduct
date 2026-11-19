# worklog

- 读取 task.md 全文（题目介绍、评分维度、交付要求、Harbor 运行契约），确认输出契约（/input/case.json、/app/work、/app/output/result.json 含 case_id）与资源限制（50 文件、单文件 500KB、总量 2MB、纯文本）。
- 决策：聚焦单一突破方向，即 Nanopublication 生成链路（断言拆解 + 证据绑定 + 结构化导出），以两阶段流程（先抽候选再逐条回原文核对）作为质量增益主机制，不做完整 nanopub 系统。
- 用 WebFetch/WebSearch 核实 nanopublication 规范：确认四命名图结构（head 串联 assertion/provenance/pubinfo，np:hasAssertion 等三条属性）、np:nschema 命名空间、prov/pav/dcterms/foaf 常用前缀；nanopubs.github.io 与 nanopub.org 直接访问失败，改经 NanoWeb（PeerJ CS 2020）等文献交叉验证结构，保证 RDF 写法准确。
- 创建 submission/references/ 与 submission/scripts/ 目录。
- 创建 SKILL.md：YAML frontmatter（name: nanopub-assertion-extractor，英文 description 含触发词），正文七步流程（读输入、通读定位、阶段一候选、阶段二三项校验、写 TriG、机械校验写 result.json、收尾），预算内约 8 至 12 次请求；含 9 个异常分支与 11 项自检清单。
- 设计决策：三道创新闸门写入流程，即论断强度校验（hedging 词表，may 不得写成 increase，correlational 不得升格因果）、证据定位四字段强制（缺则降级）、论断-原文对照表强制输出；两阶段中间产物落盘 /app/work 留痕。
- 创建 references/nanopub-structure.md：四图职责边界、前缀规范、npex: 扩展字段（evidenceQuote/evidenceLocation/pageBasis/assertionStrength/hedgingMarkers/evidenceType/inferenceNote）、LOCAL 占位 URI 约定（不伪造正式 purl.org/np URI）。
- 创建 references/turtle-templates.md：单 np 完整模板、来源论文 DOI 分支、合并文件组织、五条序列化红线。
- 创建 references/assertion-extraction-spec.md：粒度五判据与复合句拆分规则（含正反例）、六类 hedging 词表与强度判定规则、受控关系词表（9 词）与方向主体规则、证据最小充分性判据与四字段定位、candidates.json 与 verified.json 字段定义（verification: pass/degraded/dropped）。
- 创建 references/common-errors.md：35 条错误清单，分拆分/忠实性/证据定位/RDF/流程五类，每条给后果与修正。
- 创建 references/result-json-template.md：基础模板与 output_contract 优先级规则、status 四档判据表、写入要求（空数组也不得缺字段）。
- 创建 references/self-check.md：自检清单详版，按断言质量/证据定位/RDF 结构/交付完整性四组给出核查方法。
- 创建 references/example-case.md：虚构论文教学示例，20 条断言样例覆盖 hedging 保留、关联不升格因果、否定句型、约量词、条件限定等分支，附完整 TriG 示例；明确标注非正式案例结果。
- 创建 scripts/validate_np.py：纯标准库 TriG 结构校验（四图齐全非空、head 三属性、provenance 七要素、pubinfo 三要素、花括号配平、谓词非字面量）。
- 调试 validate_np.py：修复两个缺陷，即 `:` 分隔片段时基 URI 丢冒号、注释截断误伤含 `#` 的 URI；以正反样例回归测试通过（合格样例 exit 0，缺项样例精确报出两处缺失）。
- 创建 README.md：完整使用说明、文件清单、五步使用流程、最小调用示例（明确标注示意输出，非正式案例结果）、适用范围与限制。
- 决策：输出为单个合并 nanopubs.trig 以控制单响应 token（可分批追加），断言数组与对照表作为人工复核层；status 诚实标注贯穿全部模板。
- 收尾核对：确认 submission 共 10 个文件（SKILL.md、README.md、worklog.md、7 个 references、1 个脚本），全部 UTF-8 文本，总量远小于限制。

- 根据首轮评分反馈（评语：refine for a more complete and rigorous solution；未找到完整真实推导的解）修订 SKILL.md：在 frontmatter 后新增「强制执行协议」节，明确第0步先落盘 result.json 骨架、output_contract 字段缺数据不省略、广度优先、预算阈值（48次请求/700秒）强制收尾、最终写盘自检、失败也交付六条硬性纪律。
