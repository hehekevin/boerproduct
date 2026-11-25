# 示例案例：从论文片段到 20 条断言样例

**声明：本文件为教学示意，论文内容纯属虚构，仅演示流程与格式；不是正式案例结果，不得作为任何真实论文的抽取结论使用。**

## 1. 虚构输入

材料（虚构论文 ExPaper-2026，假想 case_id = demo-001，page_basis = paper）：

> **3.2 Results（page 4, paragraph 2）**
> (1) Treatment with drug X significantly reduced tumor volume in mice (p = 0.01). (2) Survival increased by approximately 40% compared with controls. (3) Mechanistically, X may inhibit kinase K1, as suggested by the in vitro assay. (4) Serum marker M1 was strongly associated with treatment response. (5) In cells lacking receptor R2, X showed no significant effect on tumor volume.

## 2. 阶段一候选（candidates.json）

| id | candidate_text | span | hedging_markers |
|-|-|-|-|
| NP001 | Treatment with drug X significantly reduced tumor volume in mice (p = 0.01) | 3.2, para 2, sent 1 | none |
| NP002 | Survival increased by approximately 40% compared with controls | sent 2 | approximately |
| NP003 | X may inhibit kinase K1 (as suggested by the in vitro assay) | sent 3 | may, suggest |
| NP004 | Serum marker M1 was strongly associated with treatment response | sent 4 | associated(关联措辞) |
| NP005 | In cells lacking receptor R2, X showed no significant effect on tumor volume | sent 5 | none（条件限定） |

拆分说明：本段五个句子各自单一主张，无需拆分；若原文为复合句则按粒度判据拆分。

## 3. 阶段二核对（verified.json 关键判定）

- NP001：definitive；数值 p = 0.01 进 numeric_items；谓词 npex:decreases（significantly reduced）；direct。
- NP002：approximately 命中，assertion_strength = suggestive，断言保留 approximately；谓词 npex:increases；direct。
- NP003：may + suggest，strength = suggestive，断言保留 may inhibit 与 as suggested by；谓词 npex:inhibits 映射到 npex:decreases 类但保留 may；evidence_type = direct（原文即此措辞）。
- NP004：associated with，strength = correlational，谓词 npex:associatedWith，不得用 npex:causes。
- NP005：条件限定 in cells lacking receptor R2 并入断言文本，strength = conditional，谓词 npex:increases 取否定形式改为 statement 保留 no significant effect，谓词用 npex:associatedWith 之外的自定义 npex:rel_no_effect 并在 relation_map 记录。

## 4. 20 条断言样例（跨多个虚构段落汇总，演示粒度）

以下样例覆盖常见句型；每条均给出证据引文与定位（虚构值仅供格式演示）。

| id | 断言（保留 hedging） | 强度 | 谓词 | 证据引文 | 定位 |
|-|-|-|-|-|-|
| NP001 | Treatment with drug X significantly reduced tumor volume in mice (p = 0.01) | definitive | npex:decreases | Treatment with drug X significantly reduced tumor volume in mice (p = 0.01). | p4, 3.2, para2, sent1 |
| NP002 | Survival increased by approximately 40% compared with controls | suggestive | npex:increases | Survival increased by approximately 40% compared with controls. | p4, 3.2, para2, sent2 |
| NP003 | X may inhibit kinase K1, as suggested by the in vitro assay | suggestive | npex:rel_inhibit | Mechanistically, X may inhibit kinase K1, as suggested by the in vitro assay. | p4, 3.2, para2, sent3 |
| NP004 | Serum marker M1 was strongly associated with treatment response | correlational | npex:associatedWith | Serum marker M1 was strongly associated with treatment response. | p4, 3.2, para2, sent4 |
| NP005 | In cells lacking receptor R2, X showed no significant effect on tumor volume | conditional | npex:rel_no_effect | In cells lacking receptor R2, X showed no significant effect on tumor volume. | p4, 3.2, para2, sent5 |
| NP006 | Dose D1 was well tolerated in all 24 mice | definitive | npex:rel_tolerated | Dose D1 was well tolerated in all 24 mice. | p5, 3.2, para1, sent1 |
| NP007 | Tumor volume in the high-dose group decreased by 35% at week 8 | definitive | npex:decreases | Tumor volume in the high-dose group decreased by 35% at week 8. | p5, 3.2, para1, sent2 |
| NP008 | Plasma half-life of X is approximately 4.5 h | suggestive | npex:measuredAs | Plasma half-life of X is approximately 4.5 h. | p5, 3.2, para1, sent3 |
| NP009 | K1 phosphorylation correlated with tumor size (r = 0.62) | correlational | npex:associatedWith | K1 phosphorylation correlated with tumor size (r = 0.62). | p6, 3.3, para1, sent1 |
| NP010 | X treatment did not alter body weight in mice | definitive | npex:rel_no_change | X treatment did not alter body weight in mice. | p6, 3.3, para1, sent2 |
| NP011 | M1 levels were elevated in responders versus non-responders | definitive | npex:increases | M1 levels were elevated in responders versus non-responders. | p6, 3.3, para2, sent1 |
| NP012 | Elevated M1 might identify patients likely to respond | suggestive | npex:rel_predict | Elevated M1 might identify patients likely to respond. | p6, 3.3, para2, sent2 |
| NP013 | X bound R2 in vitro (Kd = 12 nM) | definitive | npex:measuredAs | X bound R2 in vitro (Kd = 12 nM). | p7, 3.4, para1, sent1 |
| NP014 | Binding affinity was reduced when residue S3 was mutated | definitive | npex:decreases | Binding affinity was reduced when residue S3 was mutated. | p7, 3.4, para1, sent2 |
| NP015 | These findings suggest that R2 mediates the antitumor effect of X | suggestive | npex:rel_mediates | These findings suggest that R2 mediates the antitumor effect of X. | p7, 4 Discussion, para1, sent1 |
| NP016 | The antitumor effect required intact R2 signaling, as R2 knockout abolished it | conditional | npex:rel_requires | The antitumor effect required intact R2 signaling, as R2 knockout abolished it. | p7, 4, para1, sent2 |
| NP017 | No treatment-related deaths occurred during the study | definitive | npex:rel_none | No treatment-related deaths occurred during the study. | p5, 3.2, para2, sent4 |
| NP018 | X concentrations in liver were higher than in plasma at 2 h | definitive | npex:rel_higher_than | X concentrations in liver were higher than in plasma at 2 h. | p8, 3.4, para2, sent1 |
| NP019 | Long-term safety remains unclear beyond 12 weeks | suggestive | npex:rel_unclear | Long-term safety remains unclear beyond 12 weeks. | p8, 4, para3, sent1 |
| NP020 | Our results support further evaluation of X in humans | suggestive | npex:rel_support | Our results support further evaluation of X in humans. | p8, 4, para3, sent2 |

## 5. 对应的 nanopublication（示一条完整 TriG，其余同构）

```turtle
this: {
  this: a np:Nanopublication ;
    np:hasAssertion this:assertion ;
    np:hasProvenance this:provenance ;
    np:hasPublicationInfo this:pubinfo .
}
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
this:pubinfo {
  this: pav:createdBy npex:extractionAgent ;
    prov:generatedAtTime "2026-01-01T00:00:00Z"^^xsd:dateTime ;
    dcterms:license <https://creativecommons.org/licenses/by/4.0/> ;
    foaf:primaryTopic ex:drugX .
}
```

## 6. 本示例覆盖的异常分支

- NP003：hedging 保留（may 不升格）。
- NP004 / NP009：关联不升格因果。
- NP005 / NP010 / NP017：否定与零效应句型（自定义关系词并在 relation_map 记录）。
- NP002 / NP008：约量词保留。
- NP012 / NP015：suggestive 结论句。
- NP020：讨论段落的建议句（可输出为对作者立场的报告性断言，强度 suggestive）。
