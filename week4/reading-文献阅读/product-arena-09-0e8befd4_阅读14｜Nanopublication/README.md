# Nanopublication 论断抽取与打包 Skill

把科研论文中的科学论断抽取为符合 Nanopublication 规范的机器可读 RDF 单元（TriG 序列化），每条断言绑定逐字证据引文与精确定位（页码、章节、段落、句序），并输出可直接被下游程序解析的 result.json。

## 一、这是什么

本 Skill 实现从论文到 nanopublication 的完整流程：拆分断言、绑定证据、写入 RDF、机械校验、诚实标注状态。核心特征：

1. **两阶段流程**：先批量抽取候选论断，再逐条回原文核对忠实性、证据最小充分性与论断强度，核对通过才写 RDF。
2. **论断强度闸门（hedging 处理）**：论文写 `may increase`，断言就必须保留 `may`；关联措辞不得升格为因果；强度四档（definitive / suggestive / conditional / correlational）随断言落盘。
3. **证据定位强制字段**：每条断言的 page、section、paragraph、sentence 四字段必填，缺任一字段即降级为 partial 并如实标注。
4. **论断-原文对照表**：自动生成 assertion-source-table.md，供人工逐条复核。
5. **机械校验脚本**：scripts/validate_np.py（纯 Python 标准库）检查四图齐全、head 三元组完整、花括号配平与 provenance/pubinfo 必需字段。

## 二、文件清单

| 文件 | 作用 |
|-|-|
| SKILL.md | Skill 本体：工作流程、输入输出、异常分支、自检清单 |
| references/nanopub-structure.md | 四命名图结构与 np 前缀规范 |
| references/turtle-templates.md | 可直接套用的 TriG 模板与序列化红线 |
| references/assertion-extraction-spec.md | 粒度判据、hedging 词表、受控关系词表、证据定位规范 |
| references/common-errors.md | 常见错误清单（35 条，含修正方法） |
| references/result-json-template.md | result.json 字段字典与输出模板 |
| references/self-check.md | 自检清单详版 |
| references/example-case.md | 教学示例：虚构论文片段到 20 条断言样例（非正式案例结果） |
| scripts/validate_np.py | TriG 结构校验脚本（Python 3，无第三方依赖） |

## 三、使用步骤

1. 安装：把整个 submission 目录部署到 Skill 加载路径（评测平台为 /skills/weekly-skill）。
2. 触发：给 Agent 一份论文材料（PDF 或文本）与任务说明，要求生成 nanopublication、抽取断言、绑定证据。Skill 依据 SKILL.md 自动执行。
3. 运行时输入：/input/case.json（含 case_id、材料、output_contract）与 task.md；工作目录 /app/work；产出目录 /app/output。
4. 产出：
   - /app/output/result.json（含 case_id、status、断言数组、证据定位、uncertainties、change_log）
   - /app/output/nanopubs.trig（全部 nanopublication）
   - /app/output/assertion-source-table.md（论断-原文对照表）
5. 校验：`python scripts/validate_np.py /app/output/nanopubs.trig`，退出码 0 即结构通过；语义项按 SKILL.md 第 8 节自检清单人工或 Agent 复查。

## 四、最小调用示例

输入（示意，虚构论文）：

> 3.2 Results（page 4, paragraph 2, sentence 1）
> Treatment with drug X significantly reduced tumor volume in mice (p = 0.01).

调用：向加载本 Skill 的 Agent 提交任务“从以下论文片段生成 nanopublication 并输出 result.json”。

输出（**示意输出，非正式案例结果**，仅演示格式）：

nanopubs.trig 片段：

```turtle
this:assertion {
  ex:drugX npex:decreases ex:tumorVolume .
  ex:drugX rdfs:label "Treatment with drug X significantly reduced tumor volume in mice (p = 0.01)" .
}
this:provenance {
  this:assertion prov:wasDerivedFrom npex:sourcePaper ;
    npex:evidenceQuote "Treatment with drug X significantly reduced tumor volume in mice (p = 0.01)." ;
    npex:evidenceLocation "page 4, section 3.2 Results, paragraph 2, sentence 1" ;
    npex:pageBasis "paper" ;
    npex:assertionStrength "definitive" ;
    npex:hedgingMarkers "none" ;
    npex:evidenceType "direct" .
}
```

result.json 片段：

```json
{
  "case_id": "demo-001",
  "status": "success",
  "assertions": [
    {
      "id": "NP001",
      "statement": "Treatment with drug X significantly reduced tumor volume in mice (p = 0.01)",
      "predicate": "npex:decreases",
      "assertion_strength": "definitive",
      "evidence_quote": "Treatment with drug X significantly reduced tumor volume in mice (p = 0.01).",
      "evidence_location": {"page": "4", "page_basis": "paper", "section": "3.2 Results", "paragraph": 2, "sentence": 1},
      "evidence_type": "direct",
      "verification": "pass"
    }
  ]
}
```

对照表（assertion-source-table.md）示意：

| id | 断言 | 证据引文 | 定位 | 强度 |
|-|-|-|-|-|
| NP001 | Treatment with drug X significantly reduced tumor volume in mice (p = 0.01) | Treatment with drug X significantly reduced tumor volume in mice (p = 0.01). | p4, 3.2, para2, sent1 | definitive |

更多完整示例见 references/example-case.md（20 条断言样例与逐条强度判定）。

## 五、适用范围与限制

1. 适用：有文本层的论文 PDF、纯文本、Markdown、XML、内嵌文本；覆盖结果与结论段的断言抽取。
2. 不做：跨论文去重合并、密码学签名与 trusty URI（占位 URI 并在 result.json 注明）、无文本层 PDF 的自动 OCR（触发降级分支）。
3. 状态诚实：部分完成、无法判断、材料缺失分别以 partial / failed / refused 标注，写明原因与人工接管位置，不编造。
4. 资源占用：Skill 资源共 10 个 UTF-8 文本文件，总量远小于 2MB 限制；运行约 8 至 12 次模型请求，符合执行预算。

## 六、维护信息

- 版本 1.0；规范依据 nanopub.org 社区四命名图结构（np:nschema）。
- 变更方式：修改 SKILL.md 或 references 后，同步更新本 README 与 worklog.md。
- 已知边界：谓词词表允许经 relation_map 扩展；页码基准需按论文实际选择 paper 或 pdf。
