# rules_knowledge_graph — entities, relations, alignment, queries

## 1. Sources
- Register every ACTUAL file read: {id, path}. Keep per-paper paragraph ids; a node
  merged across papers carries evidence from EACH paper (multi-locator).

## 2. Entity criteria (抽得准)
- Node = an object that actually appears in the material: researcher, material,
  method, task, metric, conclusion, concept, dataset, instrument, organization, other.
- label = the原文 expression (normalized casing only); aliases[] record abbreviations/
  variants AS PRINTED. evidence quote must contain the entity mention.
- Author self-report vs restatement of others' work: note in uncertainty/kind;
  do not attribute a cited claim to the citing paper's authors.
- No commonsense nodes: if it is not in the material, it does not exist in the graph.

## 3. Relation criteria (连得对)
- Edge = a typed, directed claim the material actually makes: {from, to, type,
  conditions?, evidence}. Co-occurrence in one sentence is NOT a relation.
- Controlled types: uses compares outperforms supports contradicts causes increases
  decreases inhibits activates binds part_of measures associated_with applied_to
  produces contains upstream_of reports. Direction matters: "A outperforms B" ≠
  "B outperforms A". Keep适用条件 in conditions (temperature, dataset, scope).
- Review restatement / speculation → kind=inferred + uncertainty, or do not create
  the edge; never upgrade to a reported direct finding.
- Conflicting edges across papers → both kept with status=source_conflict + conflict
  note + both locators (do not silently pick one).

## 4. Alias normalization (对得齐)
- Merge variants (case, abbreviation, full name) into ONE node only with a merge
  basis: same原文 referent, e.g. "XRD" and "X-ray diffraction" defined in the paper.
  Record merge_basis + aliases + evidence from each variant.
- Same-name different objects (e.g. two "Smith" authors) stay separate nodes with
  distinguishing evidence. Engine flags duplicate labels — resolve or justify.

## 5. Queries (查得到)
- Provide >=3 real queries from task.md (or derived from the material): each
  {id, question, answer, node_ids[]} where node_ids is the answer subgraph; the
  engine attaches the nodes' evidence to query results automatically.
- Unanswerable from the graph → answer="not_reported", node_ids=[], human_confirm.

## 6. Status vocabulary (mandatory per node/edge)
reported | not_reported | source_conflict | extraction_failed | insufficient_evidence.
Gap records: no fabricated label/type value, human_confirm:true, reason recorded.