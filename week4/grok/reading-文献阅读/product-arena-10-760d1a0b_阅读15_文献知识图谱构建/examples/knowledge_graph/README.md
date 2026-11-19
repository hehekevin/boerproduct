# SYNTHETIC example — knowledge_graph

Interface demonstration ONLY. The "paper" in input/material.md is fabricated toy
text, not a real publication and not a formal case answer. Real cases are supplied by
the platform at evaluation time.

Run from the package root:
```
PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir examples/knowledge_graph/ir.json --input examples/knowledge_graph/input --out /tmp/demo_kg
```
Expected: exit 0, validation ok, graph.json (4 nodes / 3 typed edges / 3 queries),
graph.svg editable layered SVG with data-source locators, graph_check.json
(n_components=1, no orphans), result.json status success.