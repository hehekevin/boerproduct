# 常见错误清单

生成 nanopublication 后逐条对照本清单自纠。每条给出错误现象、后果与修正方法。

## A. 论断拆分错误

| # | 错误 | 后果 | 修正 |
|-|-|-|-|
| A1 | 整段结论塞进一个 assertion 字段或一条 rdfs:label | 断言不可独立判真假，评分直接受损 | 按粒度判据拆成单主张断言，一 np 一主张 |
| A2 | 复合句漏拆（并列、因果、转折） | 断言混入第二主张 | 并列拆并列项，因果拆因与果，转折拆两方向 |
| A3 | 把摘要中的背景句或引用他人综述的句子当成本文论断 | 主体混淆，来源错位 | 只抽本文结果与结论；引用他人处不输出或注明 |
| A4 | 从方法句抽论断 | 方法不是可判断真假的科学论断 | 方法信息只进 provenance 的方法说明，不做断言 |

## B. 忠实性错误（最严重）

| # | 错误 | 后果 | 修正 |
|-|-|-|-|
| B1 | 删除 hedging 词：may increase 写成 increase | 夸大论断强度 | 断言文本逐字保留 hedging；核对 hedging_markers 字段 |
| B2 | 关联升格因果：associated with 写成 causes | 关系类型错误 | correlational 措辞映射到关联类谓词 |
| B3 | 方向颠倒：A decreases B 写成 B decreases A / B increases A | 断言为假 | 以原文语法主语为准重排三元组 |
| B4 | 量词丢失：some 写成 all，或反之 | 断言为假 | 量词逐字保留并入断言文本 |
| B5 | 条件丢失：in mice、under hypoxia 被删 | 断言超出适用范围 | 限定词并入断言文本与 qualifiers |
| B6 | 数值改写：区间取中值、p 值四舍五入、单位换算 | 数值失真 | 数值与单位逐字保留，进 numeric_items 核对 |
| B7 | 引文改写不逐字 | 证据不可核 | evidence_quote 逐字抄录，省略用 [...] 标注 |
| B8 | 主体混淆：A 对 B 的作用写成 B 对 A | 主体错位 | 核对动作发出者与承受者 |

## C. 证据与定位错误

| # | 错误 | 后果 | 修正 |
|-|-|-|-|
| C1 | evidence_location 四字段缺一 | 不可回溯，强制降级 | 补齐 page/section/paragraph/sentence；真缺页码则 page 填 unknown 并降级 degraded |
| C2 | 证据片段过大（整段复制） | 违反最小充分性 | 裁到单独足以支撑断言的最小片段 |
| C3 | 证据片段不足（比断言更弱的句子） | 证据不支撑断言 | 扩片段或标 inferred 加 inference_note |
| C4 | inferred 未标注，推论写成直接陈述 | 忠实性缺陷 | evidence_type=inferred 且 inference_note 必填 |
| C5 | 页码基准混用（正文页与 PDF 页混填） | 定位错位 | page_basis 全局一致 |
| C6 | 证据引用了另一篇论文的句子 | 来源错绑 | provenance 只绑直接支撑本文断言的来源 |
| C7 | 断言找不到任何支撑片段仍输出 | 编造 | 该条 dropped，进 unreported |

## D. RDF 与序列化错误

| # | 错误 | 后果 | 修正 |
|-|-|-|-|
| D1 | 四图缺一或图块为空 | 非法 nanopublication | validate_np.py 检查；空图必补内容 |
| D2 | head 缺 np:has* 属性 | 结构非法 | 按模板补全三条属性与类型声明 |
| D3 | 谓词用字面量 | RDF 非法 | 谓词一律 URI |
| D4 | 花括号不配平或图块缺 URI | TriG 解析失败 | 每块 `{ }` 前有图 URI |
| D5 | 一个 np 塞多条独立主张 | 粒度违规 | 拆成多个 np |
| D6 | 前缀未声明或每 np 重复声明 | 解析失败或冗余 | 文件顶部统一声明一次 |
| D7 | 字面量引号未转义 | 解析失败 | 转义 `\"` `\\`，换行用三引号 |
| D8 | 伪造 purl.org/np 正式 URI | 来源不实 | 用 LOCAL 占位 URI 并在 result.json 注明 |
| D9 | blank node 做主体 | 不可引用 | 实体统一 ex: URI |
| D10 | provenance 写成 pubinfo 的内容（或反之） | 图职责错乱 | 论断来路进 provenance，发布元数据进 pubinfo |

## E. 流程与状态错误

| # | 错误 | 后果 | 修正 |
|-|-|-|-|
| E1 | status 一律写 success | 不可靠体验 | 按实际降级写 partial/failed，写明人工接管位置 |
| E2 | uncertainties/unreported 留空或缺失 | 隐匿不确定性 | 有疑必记，无则写明确无 |
| E3 | result.json 缺 case_id 或 output_contract 字段 | 交付不合规 | 对照模板与 case.json 逐字段核对 |
| E4 | 对照表条数与 trig 不一致 | 复核链断裂 | 收尾时数字对账 |
| E5 | change_log 缺失 | 无运行留痕 | 记录写入时间、动作、影响条目 |
