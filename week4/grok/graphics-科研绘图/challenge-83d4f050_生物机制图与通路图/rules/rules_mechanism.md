# DOMAIN RULES — Biological mechanism & pathway diagrams
(kind = `mechanism_pathway`)

A mechanism diagram is a set of falsifiable claims. Every arrow is a statement.
Apply these rules when extracting the IR; they target the rubric's correctness
points (entities right, interactions right, direction right, compartments right).

## 1. Entity naming & disambiguation
- **Gene vs protein**: gene symbols italic (category `gene`), protein upright
  (category `protein`). Human gene symbols uppercase (TP53); mouse first-letter
  capital (Trp53). Keep the source's species convention; add species prefix only
  if the source uses it. Do not mix gene and protein as one node.
- **Complex vs family**: a complex (e.g. mTORC1) is one node listing subunits in
  `attributes`; a family (e.g. "AKT isoforms") is either one node labelled as
  family or separate nodes per isoform — follow the source, never invent members.
- **Synonyms/old names**: use the name in the source; record aliases in
  `attributes.aliases`; do not silently rename to a "preferred" symbol.
- **Compartments are entities too** when the text localizes them (membrane,
  cytosol, nucleus, mitochondrion): model as `groups` with kind `compartment`.

## 2. Interaction semantics (verb → relation type)
| Source verb | type | arrow |
|-|-|-|
| activates / promotes / induces / stimulates / upregulates | activates | filled head → |
| inhibits / suppresses / represses / blocks / downregulates | inhibits | flat bar ⊣ |
| binds / interacts / associates / recruits | binds | plain line |
| phosphorylates / ubiquitinates / acetylates / cleaves | modifies (+modifiers[]) | dashed head |
| translocates / imports / exports / shuttles | transports | open/dashed head |
| contains / comprises / consists of | contains | dashed boundary |
| feedback (negative/positive loop) | feedback | dashed head, label loop |
- **Never collapse inhibition into activation.** A repressor drawn with an
  activation head is a wrong claim.
- **Direction**: `from` = regulator, `to` = target. "A is activated by B" ⇒
  from=B,to=A. Read carefully; reversed upstream/downstream is a fatal error.
- **Evidence strength**: established/supported/hypothesized/uncertain from the
  source's hedging ("may", "suggests" ⇒ hypothesized/uncertain).

## 3. Compartment topology & layout
- Receptors at the **membrane** band; signaling kinases in **cytoplasm**;
  transcription factors in **nucleus**. The renderer's compartment bands enforce
  this; assign `group` accordingly so a receptor is never drawn inside the nucleus.
- Order the cascade by pathway rank (upstream left → downstream right) within a
  band; feedback edges bow away from the forward chain (renderer handles routing).
- Parallel branches = separate ranks/rows, not a single merged node.

## 4. Legend & data encoding
- Legend is auto-generated from the relation types and categories actually used;
  do not hand-write a legend that disagrees with the arrows.
- If color/size/width encodes data (expression, confidence), put the mapping in
  `legend.items[].meaning` + `source`, and keep it consistent with the data table.

## 5. Self-check before render
- [ ] every node label appears verbatim in a source span
- [ ] every edge type matches the source verb; inhibition ≠ activation
- [ ] direction matches regulator→target; no reversed cascade
- [ ] compartments assigned; receptor not nuclear, TF not membrane
- [ ] feedback/parallel branches present if in source
- [ ] legend matches arrows; uncertain edges flagged