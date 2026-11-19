# TriG 模板

## 1. 单条 nanopublication 完整模板（可直接套用）

把尖括号占位符替换为实际值；`NP编号` 与 case.json 的 case_id 保持一致命名。

```turtle
@prefix np:      <http://www.nanopub.org/nschema#> .
@prefix prov:    <http://www.w3.org/ns/prov#> .
@prefix pav:     <http://purl.org/pav/> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix foaf:    <http://xmlns.com/foaf/0.1/> .
@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .
@prefix npex:    <https://w3id.org/np/LOCAL/ns#> .
@prefix ex:      <https://w3id.org/np/LOCAL/entity/{case_id}#> .
@prefix this:    <https://w3id.org/np/LOCAL/{case_id}/{NP编号}> .

this: {
  this: a np:Nanopublication ;
    np:hasAssertion this:assertion ;
    np:hasProvenance this:provenance ;
    np:hasPublicationInfo this:pubinfo .
}

this:assertion {
  ex:{主体} npex:{关系词} ex:{客体} .
  ex:{主体} rdfs:label "{断言全文，保留 hedging 与限定词}"@en .
}

this:provenance {
  this:assertion prov:wasDerivedFrom npex:sourcePaper ;
    npex:evidenceQuote "{逐字引文}"@en ;
    npex:evidenceLocation "page {页}, section {章节}, paragraph {段}, sentence {句}" ;
    npex:pageBasis "{paper|pdf}" ;
    npex:assertionStrength "{definitive|suggestive|conditional|correlational}" ;
    npex:hedgingMarkers "{标记列表|none}" ;
    npex:evidenceType "{direct|inferred}" .
}

this:pubinfo {
  this: pav:createdBy npex:extractionAgent ;
    prov:generatedAtTime "{ISO8601时间}"^^xsd:dateTime ;
    dcterms:license <https://creativecommons.org/licenses/by/4.0/> ;
    foaf:primaryTopic ex:{主体} .
}

npex:sourcePaper {
  npex:sourcePaper a dcterms:BibliographicResource ;
    dcterms:title "{论文标题}" ;
    dcterms:creator ex:{作者编号} ;
    dcterms:issued "{年份}"^^xsd:gYear .
  npex:sourcePaperIdentifier dcterms:identifier "{DOI 或 题名标识}" .
  npex:extractionAgent a prov:SoftwareAgent ;
    rdfs:label "nanopub-assertion-extractor skill" .
}
```

要点：

1. 前缀声明放在整个 TriG 文件顶部一次即可，多个 np 合并一个文件时不要重复声明。
2. 每条 np 换不同的 `this:` 基 URI（`{NP编号}` 递增）；`ex:` 实体在同一 case 内统一复用，同一实体概念用同一 URI。
3. label 语言标签与原文一致（英文原文用 @en；材料无明确语言时省略语言标签）。
4. prov:generatedAtTime 用运行时实际 UTC 时间。

## 2. 来源论文写法分支

- 有 DOI：`this:assertion prov:wasDerivedFrom <https://doi.org/{doi}> .`，题录信息挂在同一 DOI 节点上。
- 无 DOI：用 `npex:sourcePaper` 节点，`dcterms:identifier` 写完整题名加期刊年份，允许 result.json 中 `uncertainties` 注明标识不可靠。
- 断言依赖图表：在 provenance 加 `npex:figureRef "Figure 2"`；图内数值不逐字引用时 evidenceType 必须 inferred 且写 inferenceNote。

## 3. 合并文件组织

全部 np 写入一个 `nanopubs.trig`：

```turtle
# 头部：全部 @prefix 声明一次
# 依次排列每个 np 的四个图块（this: 基 URI 不同）
```

合并文件的机械检查（scripts/validate_np.py 自动执行）：每个 np 均有独立的 `{ }` 四图块，head 三条 np:has* 属性齐全，无空图。

## 4. 序列化红线

1. 图块必须 `{ }` 括起且前面有图 URI；裸三元组不得与命名图混写。
2. 字面量含引号或反斜杠时用 `\"` 与 `\\` 转义；含换行写成单行加空格或用三引号 `"""..."""`。
3. 关系词（谓词）只能是 URI，不能是字面量。
4. 不使用空节点（blank node）做主体；实体一律给 `ex:` URI。
5. 数字时间等类型化字面量加 `^^xsd:` 类型。
