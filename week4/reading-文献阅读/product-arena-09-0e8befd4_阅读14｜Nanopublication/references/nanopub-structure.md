# Nanopublication 结构说明

## 1. 概念

Nanopublication 是把一条科学论断连同其出处与发布信息打包为机器可读 RDF 单元的出版方式。一个 nanopublication 由四个命名图（named graph）组成，采用 TriG 序列化（每个 `{ }` 块前带图 URI）。

## 2. 四命名图

| 图 | URI 约定 | 内容 |
|-|-|-|
| head | `this:`（即 nanopub 基 URI） | 四条三元组：声明类型并链接其余三图 |
| assertion | `this:#assertion` | 论断本体，核心三元组加保留限定词的 label |
| provenance | `this:#provenance` | 论断如何产生：来源论文、证据片段、定位、强度、方法 |
| pubinfo | `this:#pubinfo` | nanopub 本身的发布元数据：创建者、时间、许可、主题 |

结构约束（缺一即无效）：

1. head 中 `this: a np:Nanopublication` 且三条 `np:has*` 属性齐全。
2. assertion、provenance、pubinfo 三图都存在且非空（空断言图能解析但不是有效 nanopublication）。
3. 一条 nanopublication 只装一条主张；多条相关主张拆成多个 nanopublication。

## 3. 前缀规范

```turtle
@prefix np:      <http://www.nanopub.org/nschema#> .
@prefix prov:    <http://www.w3.org/ns/prov#> .
@prefix pav:     <http://purl.org/pav/> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix foaf:    <http://xmlns.com/foaf/0.1/> .
@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .
```

本 Skill 的扩展前缀（证据绑定字段，本地命名空间）：

```turtle
@prefix npex: <https://w3id.org/np/LOCAL/ns#> .
```

`npex:` 字段清单（写入 provenance 图）：

| 字段 | 取值 | 说明 |
|-|-|-|
| npex:evidenceQuote | 字面量 | 逐字证据引文，不超过 300 字符 |
| npex:evidenceLocation | 字面量 | 形如 `page 4, section 3.2, paragraph 2, sentence 1` |
| npex:pageBasis | `paper` 或 `pdf` | 页码基准声明 |
| npex:assertionStrength | definitive / suggestive / conditional / correlational | 论断强度 |
| npex:hedgingMarkers | 字面量 | 命中的 hedging 标记，逗号分隔，无则写 `none` |
| npex:evidenceType | direct / inferred | 直接证据或间接推论 |
| npex:inferenceNote | 字面量 | evidenceType 为 inferred 时必填的推理说明 |

## 4. 各图职责边界

- **assertion 只放论断**：核心三元组（主语、谓词、宾语）与保留限定词的 `rdfs:label`。证据、方法、作者一律不放 assertion。
- **provenance 描述论断的来路**：`prov:wasDerivedFrom` 指向来源论文；`npex:` 证据字段；必要时 `prov:wasAttributedTo` 指向论文作者。
- **pubinfo 描述 nanopub 整体**：`pav:createdBy`（本 Skill 运行主体，写作抽取代理而非论文作者）、`prov:generatedAtTime`、`dcterms:license`、`foaf:primaryTopic`。

## 5. URI 与占位说明

- 正式发布环境 nanopub URI 形如 `http://purl.org/np/RA...`（内容哈希 trusty URI，签名后生成）。
- 本 Skill 离线运行不签名，基 URI 用 `https://w3id.org/np/LOCAL/{case_id}/{NP编号}` 占位，并在 result.json 的 `nanopub_uri_note` 字段注明“占位 URI，未签名，未注册”。不得伪造 purl.org/np 正式 URI。
- 来源论文 URI：有 DOI 用 `https://doi.org/{doi}`；无 DOI 时用 `npex:{case_id}-source` 节点并挂 `dcterms:title` 与 `dcterms:creator` 等题录信息。

## 6. 最小完整骨架

```turtle
this: {
  this: a np:Nanopublication ;
    np:hasAssertion this:assertion ;
    np:hasProvenance this:provenance ;
    np:hasPublicationInfo this:pubinfo .
}
this:assertion {
  npex:s1 npex:p1 npex:o1 .
  npex:s1 rdfs:label "断言全文，保留 hedging 与限定词" .
}
this:provenance {
  this:assertion prov:wasDerivedFrom npex:sourcePaper ;
    npex:evidenceQuote "逐字引文" ;
    npex:evidenceLocation "page 4, section 3.2, paragraph 2, sentence 1" ;
    npex:pageBasis "paper" ;
    npex:assertionStrength "suggestive" ;
    npex:hedgingMarkers "may" ;
    npex:evidenceType "direct" .
}
this:pubinfo {
  this: pav:createdBy npex:extractionAgent ;
    prov:generatedAtTime "2026-01-01T00:00:00Z"^^xsd:dateTime ;
    dcterms:license <https://creativecommons.org/licenses/by/4.0/> ;
    foaf:primaryTopic npex:s1 .
}
```

规范参考：nanopub.org 社区规范（np:nschema）与 Nanopublications 综述文献（NanoWeb, PeerJ CS 2020 等）所述四命名图结构。本 Skill 不要求密码学签名，签名与 trusty URI 属发布环节，超出本流程范围。
